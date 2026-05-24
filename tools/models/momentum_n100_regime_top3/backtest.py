"""momentum_n100 + regime gate + top-K, with TRUE daily-equity drawdown.

Faithful to momentum_n100_top5_max1's signal (rank Nasdaq-100 by 30d return),
but adds the two DD levers the user asked for and measures DD honestly:

  --top K          hold top-K equal-weight instead of top-1 (cuts single-name variance)
  --regime         go 100% cash on rebalance when QQQ_close < QQQ 200d SMA
  --mid-month      add the day-15 rank check (matches the 94.65% config)

Engine rebuilds a DAILY mark-to-market equity curve (cash + sum(shares*close)),
so MaxDD is the real peak-to-trough — unlike the parent model's trade-snapshot DD
(which only sampled equity at trade exits and understated drawdown).

Costs: IBKR Lite $0 commission; 8bps slippage on traded notional (delta shares).
Data: data_source='yfinance', plain US tickers, 4yr stock history (2022-2026).
"""
from __future__ import annotations
import sys, os, csv, json, argparse
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

LOOKBACK = 30
N100_CSV = str(ROOT / "src/data/symbols/nasdaq100.csv")
SLIPPAGE_BPS = 8.0
DEFAULT_START = date(2022, 5, 24)
DEFAULT_END   = date(2026, 5, 24)
DEFAULT_CAP   = 1_000_000.0


def get_engine():
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system",
    )
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa: F401
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def load_n100(path=N100_CSV):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r.get("Series", "").strip() == "EQ":
                out.append(r["Symbol"].strip())
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def build_rebal(dates, start, end, mid_month):
    rebal = set()
    mid = set()
    y, m = start.year, start.month
    while True:
        t = pd.Timestamp(y, m, 1)
        fut = dates[dates >= t]
        if len(fut) == 0 or fut[0].date() > end:
            break
        if fut[0].date() >= start:
            rebal.add(fut[0])
        if mid_month:
            tm = pd.Timestamp(y, m, 15)
            fm = dates[dates >= tm]
            if len(fm) > 0 and fm[0].date() <= end:
                mid.add(fm[0])
        m += 1
        if m > 12:
            m = 1; y += 1
    sd = pd.Timestamp(start)
    if sd in dates:
        rebal.add(sd)
    return rebal | mid


def run(start, end, capital, top=3, regime=True, mid_month=False,
        trail=0.0, fast_sma=0, mom_mode="ret", universe_csv=N100_CSV, regime_sym="QQQ",
        label=None, out_dir=None, quiet=False):
    eng = get_engine()
    syms = load_n100(universe_csv)
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=400), "b": end})
        qq = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol=:rs "
            "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"rs": regime_sym, "a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    qq["date"] = pd.to_datetime(qq["date"])
    qq = qq.set_index("date")["close"]
    qq_sma = qq.rolling(200).mean()
    on = qq > qq_sma
    if fast_sma > 0:                       # faster secondary gate: must also be > fast SMA
        on = on & (qq > qq.rolling(fast_sma).mean())
    regime_on = on.reindex(cl.index).ffill().fillna(False)

    dates = cl.index
    present = [s for s in syms if s in cl.columns]
    rebal = build_rebal(dates, start, end, mid_month)
    # signal precompute (for blend / sharpe momentum modes)
    dret = cl.pct_change()
    vol63 = dret.rolling(63).std()

    def score_row(di):
        if mom_mode == "blend":   # multi-timeframe momentum, smoother
            s = None
            for lb in (21, 63, 126):
                if di - lb < 0:
                    continue
                r = cl.iloc[di] / cl.iloc[di - lb] - 1
                s = r if s is None else s + r
            return s / 3.0
        if mom_mode == "sharpe":  # 63d return / 63d vol (volatility-adjusted)
            if di - 63 < 0:
                return cl.iloc[di] * 0
            r = cl.iloc[di] / cl.iloc[di - 63] - 1
            return r / vol63.iloc[di].replace(0, pd.NA)
        # default: raw LOOKBACK return
        return cl.iloc[di] / cl.iloc[di - LOOKBACK] - 1

    start_ts = pd.Timestamp(start)
    run_dates = dates[dates >= start_ts]

    cash = capital
    pos: dict[str, float] = {}            # sym -> shares
    entry_px: dict[str, float] = {}
    peak_px: dict[str, float] = {}        # for per-position trailing stop
    equity = []
    trades = []
    txns = []
    slip = SLIPPAGE_BPS / 1e4
    trail_f = trail / 100.0

    def log(d, action, s, px, shares):
        txns.append({"date": d.date().isoformat(), "action": action, "symbol": s,
                     "price": round(px, 4), "shares": round(shares, 4),
                     "value": round(shares * px, 2)})

    for d in run_dates:
        di = dates.get_loc(d)
        # daily per-position trailing stop (checked every day, not just on rebalance)
        if trail_f > 0 and pos:
            for s in list(pos):
                px = cl[s].iloc[di]
                if pd.isna(px):
                    continue
                px = float(px)
                peak_px[s] = max(peak_px.get(s, px), px)
                if px <= peak_px[s] * (1 - trail_f):
                    cash += pos[s] * px * (1 - slip)
                    log(d, "SELL_TRAIL", s, px, pos[s])
                    if s in entry_px:
                        trades.append({"sym": s, "exit_date": d.date().isoformat(),
                                       "ret_pct": round((px / entry_px[s] - 1) * 100, 2)})
                    pos.pop(s, None); entry_px.pop(s, None); peak_px.pop(s, None)
        if d in rebal and di >= LOOKBACK:
            # current portfolio value at today's close
            pv = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                            if pd.notna(cl[s].iloc[di]))
            # target basket
            target: dict[str, float] = {}
            risk_on = (not regime) or bool(regime_on.iloc[di])
            if risk_on:
                univ = [s for s in present if pd.notna(cl[s].iloc[di])
                        and pd.notna(cl[s].iloc[di - LOOKBACK])]
                rets = score_row(di).reindex(univ)
                rk = rets.dropna().sort_values(ascending=False)
                picks = list(rk.index[:top])
                if picks:
                    w = 1.0 / len(picks)
                    for s in picks:
                        target[s] = w
            # desired shares per symbol
            desired = {s: (w * pv) / float(cl[s].iloc[di]) for s, w in target.items()}
            # trade deltas (sell drops + trims, buy adds) — slippage on |delta|*px
            for s in list(set(pos) | set(desired)):
                px = float(cl[s].iloc[di])
                cur = pos.get(s, 0.0)
                tgt = desired.get(s, 0.0)
                dsh = tgt - cur
                if abs(dsh) * px < 1e-6:
                    continue
                if dsh < 0:  # sell
                    sh = -dsh
                    cash += sh * px * (1 - slip)
                    log(d, "SELL", s, px, sh)
                    if s in entry_px:
                        trades.append({"sym": s, "exit_date": d.date().isoformat(),
                                       "ret_pct": round((px / entry_px[s] - 1) * 100, 2)})
                else:        # buy
                    cash -= dsh * px * (1 + slip)
                    log(d, "BUY", s, px, dsh)
                if tgt <= 1e-9:
                    pos.pop(s, None); entry_px.pop(s, None); peak_px.pop(s, None)
                else:
                    if s not in pos:
                        entry_px[s] = px; peak_px[s] = px
                    pos[s] = tgt
        # daily MTM
        val = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                         if pd.notna(cl[s].iloc[di]))
        equity.append(val)

    eq = pd.Series(equity, index=run_dates)
    yrs = (run_dates[-1] - run_dates[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    calmar = cagr / max(0.01, mdd)
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    losses = sum(1 for t in trades if t["ret_pct"] <= 0)
    tim = float((regime_on.reindex(run_dates).fillna(False)).mean() * 100) if regime else 100.0

    name = label or f"top{top} {'regime' if regime else 'no-regime'}{' +mid' if mid_month else ''}"
    res = {"label": name, "top": top, "regime": regime, "mid_month": mid_month,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "capital": capital, "final_nav": round(final, 0),
           "cagr_pct": round(cagr, 2), "max_dd_pct_daily": round(mdd, 2),
           "calmar": round(calmar, 2), "trades": len(trades),
           "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1),
           "regime_time_in_market_pct": round(tim, 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}")
        print(f"  Trades {len(trades)}  WR {res['win_rate_pct']}%  RegimeTIM {tim:.1f}%")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
        if txns:
            pd.DataFrame(txns).to_csv(out_dir / "transactions.csv", index=False)
    return res


SWEEP = [
    dict(top=1, regime=False, mid_month=True,  label="top1 no-regime +mid (orig)"),
    dict(top=1, regime=True,  mid_month=True,  label="top1 regime +mid"),
    dict(top=3, regime=False, mid_month=False, label="top3 no-regime"),
    dict(top=3, regime=True,  mid_month=False, label="top3 regime"),
    dict(top=5, regime=True,  mid_month=False, label="top5 regime"),
    dict(top=3, regime=True,  mid_month=True,  label="top3 regime +mid"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--no-regime", dest="regime", action="store_false")
    ap.add_argument("--mid-month", action="store_true")
    ap.add_argument("--trail", type=float, default=0.0, help="per-position trailing stop %% (0=off)")
    ap.add_argument("--fast-sma", type=int, default=0, help="faster secondary regime gate, e.g. 50 (0=off)")
    ap.add_argument("--mom-mode", choices=["ret", "blend", "sharpe"], default="ret",
                    help="ranking signal: ret=30d return, blend=21/63/126 avg, sharpe=63d ret/vol")
    ap.add_argument("--universe-csv", default=N100_CSV, help="universe CSV (default Nasdaq-100)")
    ap.add_argument("--regime-sym", default="QQQ", help="regime index symbol (QQQ or SPY)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.set_defaults(regime=True)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== momentum_n100 regime/top-K sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<28} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7} {'WR%':>6}")
        print("-" * 70)
        for r in rows:
            print(f"{r['label']:<28} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7} {r['win_rate_pct']:>6.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, top=a.top, regime=a.regime, mid_month=a.mid_month,
            trail=a.trail, fast_sma=a.fast_sma, mom_mode=a.mom_mode,
            universe_csv=a.universe_csv, regime_sym=a.regime_sym,
            out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

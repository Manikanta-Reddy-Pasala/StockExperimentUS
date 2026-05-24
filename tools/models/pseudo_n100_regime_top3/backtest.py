"""pseudo_n100 (yearly-PIT ADV universe) + regime gate + top-K, TRUE daily DD.

Why this model matters: it is the LEAST survivorship-biased momentum model we can
run on free data. The held universe is rebuilt every year-start from a point-in-time
20-day ADV ranking (top-100 of the Nasdaq-500 pool) + a close>200d-SMA uptrend filter,
so it never "knows" which names won later. (Caveat: the 500-name POOL is still the
*current* Nasdaq-500, so pool-membership survivorship remains — this is "less biased",
not bias-free.)

Adds the two DD levers proven on momentum_n100:
  --top K     hold top-K equal-weight (default 3)
  --regime    100% cash on rebalance when QQQ_close < QQQ 200d SMA

Daily mark-to-market equity -> TRUE MaxDD. Costs: $0 commission (IBKR Lite), 8bps slippage.
If this lands ~50-60% CAGR / sub-35% DD it is the HONEST forward expectation for the
whole momentum family (vs n100-regime-top3's survivorship-inflated 87%).
"""
from __future__ import annotations
import sys, os, json, argparse
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.shared.universes import nasdaq500_symbols  # noqa: E402

LOOKBACK = 30
ADV_WIN = 20
UNIV_SIZE = 100
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


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def run(start, end, capital, top=3, regime=True, label=None, out_dir=None, quiet=False):
    eng = get_engine()
    n500 = [s for s, _ in nasdaq500_symbols()]
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": n500, "a": start - timedelta(days=400), "b": end})
        qq = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol='QQQ' "
            "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    df["adv"] = df["close"].astype(float) * df["volume"].astype(float)
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    adv = df.pivot(index="date", columns="symbol", values="adv").fillna(0)
    adv20 = adv.rolling(ADV_WIN).mean()
    sma200 = cl.rolling(200).mean()
    dates = cl.index

    qq["date"] = pd.to_datetime(qq["date"])
    qqc = qq.set_index("date")["close"]
    regime_on = (qqc > qqc.rolling(200).mean()).reindex(dates).ffill().fillna(False)

    # Yearly PIT universe (top-100 ADV at each year-start)
    year_starts, cur = [], start
    while cur <= end:
        year_starts.append(pd.Timestamp(cur)); cur = cur.replace(year=cur.year + 1)
    year_univ = {}
    for ys in year_starts:
        fut = dates[dates >= ys]
        if len(fut) == 0:
            continue
        di = dates.get_loc(fut[0])
        year_univ[ys] = adv20.iloc[di].dropna().sort_values(ascending=False).head(UNIV_SIZE).index.tolist()

    def pick_univ(d):
        chosen = year_starts[0]
        for ys in year_starts:
            if d >= ys:
                chosen = ys
        return year_univ.get(chosen, [])

    # monthly rebalance calendar
    rebal, y, m = set(), start.year, start.month
    while True:
        t = pd.Timestamp(y, m, 1)
        fut = dates[dates >= t]
        if len(fut) == 0 or fut[0].date() > end:
            break
        if fut[0].date() >= start:
            rebal.add(fut[0])
        m += 1
        if m > 12:
            m = 1; y += 1
    if pd.Timestamp(start) in dates:
        rebal.add(pd.Timestamp(start))

    run_dates = dates[dates >= pd.Timestamp(start)]
    cash = capital
    pos: dict[str, float] = {}
    entry_px: dict[str, float] = {}
    equity, trades = [], []
    slip = SLIPPAGE_BPS / 1e4

    for d in run_dates:
        di = dates.get_loc(d)
        if d in rebal and di >= max(LOOKBACK, 200):
            pv = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                            if pd.notna(cl[s].iloc[di]))
            target: dict[str, float] = {}
            risk_on = (not regime) or bool(regime_on.iloc[di])
            if risk_on:
                up = sma200.iloc[di] < cl.iloc[di]
                univ = [s for s in pick_univ(d)
                        if bool(up.get(s, False)) and pd.notna(cl[s].iloc[di])
                        and pd.notna(cl[s].iloc[di - LOOKBACK])]
                rets = cl.iloc[di].reindex(univ) / cl.iloc[di - LOOKBACK].reindex(univ) - 1
                rk = rets.dropna().sort_values(ascending=False)
                picks = list(rk.index[:top])
                if picks:
                    w = 1.0 / len(picks)
                    target = {s: w for s in picks}
            desired = {s: (w * pv) / float(cl[s].iloc[di]) for s, w in target.items()}
            for s in list(set(pos) | set(desired)):
                px = float(cl[s].iloc[di])
                dsh = desired.get(s, 0.0) - pos.get(s, 0.0)
                if abs(dsh) * px < 1e-6:
                    continue
                if dsh < 0:
                    cash += (-dsh) * px * (1 - slip)
                    if s in entry_px:
                        trades.append({"sym": s, "ret_pct": round((px / entry_px[s] - 1) * 100, 2)})
                else:
                    cash -= dsh * px * (1 + slip)
                if desired.get(s, 0.0) <= 1e-9:
                    pos.pop(s, None); entry_px.pop(s, None)
                else:
                    entry_px.setdefault(s, px)
                    pos[s] = desired[s]
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

    name = label or f"pseudo top{top} {'regime' if regime else 'no-regime'}"
    res = {"label": name, "top": top, "regime": regime,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "final_nav": round(final, 0),
           "cagr_pct": round(cagr, 2), "max_dd_pct_daily": round(mdd, 2),
           "calmar": round(calmar, 2), "trades": len(trades),
           "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}")
        print(f"  Trades {len(trades)}  WR {res['win_rate_pct']}%")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
    return res


SWEEP = [
    dict(top=1, regime=False, label="pseudo top1 no-regime (orig-like)"),
    dict(top=1, regime=True,  label="pseudo top1 regime"),
    dict(top=3, regime=False, label="pseudo top3 no-regime"),
    dict(top=3, regime=True,  label="pseudo top3 regime"),
    dict(top=5, regime=True,  label="pseudo top5 regime"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--no-regime", dest="regime", action="store_false")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.set_defaults(regime=True)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== pseudo_n100 (PIT) regime/top-K sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<34} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7} {'WR%':>6}")
        print("-" * 76)
        for r in rows:
            print(f"{r['label']:<34} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7} {r['win_rate_pct']:>6.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, top=a.top, regime=a.regime,
            out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

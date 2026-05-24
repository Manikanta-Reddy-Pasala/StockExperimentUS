"""Broad momentum on the full Nasdaq-500 + regime gate + top-K. TRUE daily DD.

Same engine as momentum_n100_regime_top3 but over the wider Nasdaq-500 universe
(more mid/large names => a deeper pool of momentum winners). Higher-CAGR candidate
for "a better model"; note it is MORE survivorship-biased than the N100 version
(current top-500 constituents).

  --top K     hold top-K equal-weight (default 5; wider universe wants more names)
  --regime    cash on rebalance when QQQ < 200d SMA
  --min-adv   skip names below this 20d ADV ($) to avoid illiquid picks (default 5e6)

Costs: $0 commission (IBKR Lite), 8 bps slippage. Daily MTM equity.
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


def run(start, end, capital, top=5, regime=True, min_adv=5e6,
        label=None, out_dir=None, quiet=False):
    eng = get_engine()
    syms = [s for s, _ in nasdaq500_symbols()]
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=400), "b": end})
        qq = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol='QQQ' "
            "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    df["adv"] = df["close"].astype(float) * df["volume"].astype(float)
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    adv20 = df.pivot(index="date", columns="symbol", values="adv").fillna(0).rolling(ADV_WIN).mean()
    dates = cl.index
    present = [s for s in syms if s in cl.columns]

    qq["date"] = pd.to_datetime(qq["date"])
    qqc = qq.set_index("date")["close"]
    regime_on = (qqc > qqc.rolling(200).mean()).reindex(dates).ffill().fillna(False)

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
        if d in rebal and di >= LOOKBACK:
            pv = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                            if pd.notna(cl[s].iloc[di]))
            target = {}
            risk_on = (not regime) or bool(regime_on.iloc[di])
            if risk_on:
                univ = [s for s in present
                        if pd.notna(cl[s].iloc[di]) and pd.notna(cl[s].iloc[di - LOOKBACK])
                        and float(adv20.iloc[di].get(s, 0)) >= min_adv]
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
                    entry_px.setdefault(s, px); pos[s] = desired[s]
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

    name = label or f"n500 top{top} {'regime' if regime else 'no-regime'}"
    res = {"label": name, "top": top, "regime": regime, "min_adv": min_adv,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "final_nav": round(final, 0), "cagr_pct": round(cagr, 2),
           "max_dd_pct_daily": round(mdd, 2), "calmar": round(calmar, 2), "trades": len(trades),
           "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}  Trades {len(trades)}")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
    return res


SWEEP = [
    dict(top=5,  regime=True,  label="n500 top5 regime"),
    dict(top=3,  regime=True,  label="n500 top3 regime"),
    dict(top=10, regime=True,  label="n500 top10 regime"),
    dict(top=5,  regime=False, label="n500 top5 no-regime"),
    dict(top=3,  regime=False, label="n500 top3 no-regime"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--no-regime", dest="regime", action="store_false")
    ap.add_argument("--min-adv", type=float, default=5e6)
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.set_defaults(regime=True)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== Nasdaq-500 momentum sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<24} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7}")
        print("-" * 60)
        for r in rows:
            print(f"{r['label']:<24} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, top=a.top, regime=a.regime, min_adv=a.min_adv,
            out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

"""VCP / Minervini-style volatility-contraction breakout. TRUE daily DD.

A distinct setup from the plain Donchian breakout (BRK): it stacks Minervini's
price-based Trend Template + a relative-strength-leader filter + a volatility
CONTRACTION test + a volume-expansion breakout trigger. (Earnings/fundamentals are
not available from yfinance, so this is the PRICE+VOLUME proxy of VCP — Minervini's
Trend Template is itself largely price-based.)

Entry — ALL must hold on the day:
  Trend template:
    close > SMA50 > SMA150 > SMA200, SMA200 rising (> its value 20d ago),
    close within 25% of 252d high, close > 30% above 252d low
  RS leader:      126d return in the top `rs_pct` of the universe that day
  Contraction:    ATR10/close < ATR50/close  AND  close within `tight`% of its 50d high
  Breakout:       close == max(close, last `pivot` days)  AND  volume > `vmult` x 50d avg vol
Exit:
  close <= peak_since_entry x (1 - trail)    [ATR-free % trailing stop, default 12%]
  OR close < SMA50

Universe default Nasdaq-500 (more growth/AI/semi/small-mid setups). Top-K equal weight.
Costs: $0 commission (IBKR Lite) + 8 bps slippage. Daily mark-to-market drawdown.
"""
from __future__ import annotations
import sys, os, json, argparse
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.shared.universes import nasdaq500_symbols  # noqa: E402

SLIP = 8e-4
DEFAULT_START = date(2022, 5, 24)
DEFAULT_END   = date(2026, 5, 24)
DEFAULT_CAP   = 1_000_000.0


def get_engine():
    url = os.environ.get("DATABASE_URL",
                         "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system")
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def max_drawdown(eq):
    peak = eq.cummax()
    return float(-((eq - peak) / peak).min() * 100)


def run(start, end, capital, universe="n500", maxn=8, rs_pct=0.30, tight=8.0,
        pivot=15, vmult=1.4, trail=12.0, label=None, out_dir=None, quiet=False):
    eng = get_engine()
    if universe == "n100":
        import csv as _c
        syms = []
        with open(ROOT / "src/data/symbols/nasdaq100.csv") as f:
            for r in _c.DictReader(f):
                if r.get("Series", "").strip() == "EQ":
                    syms.append(r["Symbol"].strip())
    else:
        syms = [s for s, _ in nasdaq500_symbols()]

    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,high,low,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=500), "b": end})
    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    hi = df.pivot(index="date", columns="symbol", values="high").ffill()
    lo = df.pivot(index="date", columns="symbol", values="low").ffill()
    vo = df.pivot(index="date", columns="symbol", values="volume").fillna(0)
    dates = cl.index
    present = [s for s in syms if s in cl.columns]
    cl, hi, lo, vo = cl[present], hi[present], lo[present], vo[present]

    sma50, sma150, sma200 = cl.rolling(50).mean(), cl.rolling(150).mean(), cl.rolling(200).mean()
    hi252, lo252 = cl.rolling(252).max(), cl.rolling(252).min()
    hi50 = cl.rolling(50).max()
    pivot_high = cl.rolling(pivot).max()
    vavg50 = vo.rolling(50).mean()
    ret126 = cl / cl.shift(126) - 1
    prev_close = cl.shift(1)
    tr = pd.concat([(hi - lo), (hi - prev_close).abs(), (lo - prev_close).abs()]).groupby(level=0).max()
    atr10 = tr.rolling(10).mean()
    atr50 = tr.rolling(50).mean()

    run_dates = dates[dates >= pd.Timestamp(start)]
    cash = capital
    pos: dict[str, float] = {}
    entry_px: dict[str, float] = {}
    peak: dict[str, float] = {}
    equity, trades = [], []
    trail_f = trail / 100.0

    for d in run_dates:
        di = dates.get_loc(d)
        if di < 252:
            equity.append(cash); continue
        pc = cl.iloc[di]

        # EXITS
        for s in list(pos):
            px = float(pc[s])
            peak[s] = max(peak.get(s, px), px)
            if px <= peak[s] * (1 - trail_f) or px < float(sma50.iloc[di][s]):
                cash += pos[s] * px * (1 - SLIP)
                trades.append({"sym": s, "ret_pct": round((px / entry_px[s] - 1) * 100, 2)})
                pos.pop(s); entry_px.pop(s); peak.pop(s, None)

        slots = maxn - len(pos)
        if slots > 0:
            # RS leader threshold for the day
            rrow = ret126.iloc[di].dropna()
            if len(rrow) > 20:
                rs_thresh = rrow.quantile(1 - rs_pct)
            else:
                rs_thresh = -1e9
            cand = []
            c50, c150, c200 = sma50.iloc[di], sma150.iloc[di], sma200.iloc[di]
            c200_20 = sma200.iloc[di - 20]
            h252, l252, h50, pv, va = hi252.iloc[di], lo252.iloc[di], hi50.iloc[di], pivot_high.iloc[di], vavg50.iloc[di]
            a10, a50 = atr10.iloc[di], atr50.iloc[di]
            for s in present:
                if s in pos:
                    continue
                px = pc[s]
                if pd.isna(px) or pd.isna(c200[s]) or pd.isna(h252[s]) or pd.isna(a50[s]) or a50[s] == 0:
                    continue
                px = float(px)
                # trend template
                if not (px > c50[s] > c150[s] > c200[s]):
                    continue
                if not (c200[s] > c200_20[s]):
                    continue
                if px < 0.75 * float(h252[s]):       # within 25% of 52w high
                    continue
                if px < 1.30 * float(l252[s]):       # >30% above 52w low
                    continue
                # RS leader
                if pd.isna(ret126.iloc[di][s]) or float(ret126.iloc[di][s]) < rs_thresh:
                    continue
                # contraction: short ATR below long ATR, price tight near 50d high
                if not (float(a10[s]) < float(a50[s])):
                    continue
                if px < (1 - tight / 100.0) * float(h50[s]):
                    continue
                # breakout + volume expansion
                if px < float(pv[s]) - 1e-9:
                    continue
                if pd.isna(va[s]) or va[s] == 0 or float(vo.iloc[di][s]) < vmult * float(va[s]):
                    continue
                cand.append((float(ret126.iloc[di][s]), s))   # rank entrants by RS
            cand.sort(reverse=True)
            pv_total = cash + sum(sh * float(pc[s]) for s, sh in pos.items() if pd.notna(pc[s]))
            budget = pv_total / maxn
            for _, s in cand[:slots]:
                px = float(pc[s]); sh = budget / px
                cost = sh * px * (1 + SLIP)
                if cost <= cash and sh > 0:
                    cash -= cost; pos[s] = sh; entry_px[s] = px; peak[s] = px

        val = cash + sum(sh * float(pc[s]) for s, sh in pos.items() if pd.notna(pc[s]))
        equity.append(val)

    eq = pd.Series(equity, index=run_dates)
    yrs = (run_dates[-1] - run_dates[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    calmar = cagr / max(0.01, mdd)
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    losses = sum(1 for t in trades if t["ret_pct"] <= 0)
    avgw = np.mean([t["ret_pct"] for t in trades if t["ret_pct"] > 0]) if wins else 0
    avgl = np.mean([t["ret_pct"] for t in trades if t["ret_pct"] <= 0]) if losses else 0

    name = label or f"VCP {universe} N{maxn} trail{trail:g}"
    res = {"label": name, "universe": universe, "maxn": maxn, "rs_pct": rs_pct, "tight": tight,
           "pivot": pivot, "vmult": vmult, "trail": trail,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "final_nav": round(final, 0), "cagr_pct": round(cagr, 2),
           "max_dd_pct_daily": round(mdd, 2), "calmar": round(calmar, 2), "trades": len(trades),
           "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1),
           "avg_win_pct": round(float(avgw), 1), "avg_loss_pct": round(float(avgl), 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}")
        print(f"  Trades {len(trades)}  WR {res['win_rate_pct']}%  avgW {avgw:+.1f}% avgL {avgl:+.1f}%")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
    return res


SWEEP = [
    dict(universe="n500", maxn=8, trail=12, label="VCP n500 N8 trail12"),
    dict(universe="n500", maxn=8, trail=10, label="VCP n500 N8 trail10"),
    dict(universe="n500", maxn=5, trail=12, label="VCP n500 N5 trail12"),
    dict(universe="n500", maxn=10, trail=15, label="VCP n500 N10 trail15"),
    dict(universe="n100", maxn=5, trail=12, label="VCP n100 N5 trail12"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--universe", choices=["n100", "n500"], default="n500")
    ap.add_argument("--maxn", type=int, default=8)
    ap.add_argument("--rs-pct", type=float, default=0.30)
    ap.add_argument("--tight", type=float, default=8.0)
    ap.add_argument("--pivot", type=int, default=15)
    ap.add_argument("--vmult", type=float, default=1.4)
    ap.add_argument("--trail", type=float, default=12.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== VCP / Minervini sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<22} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7} {'WR%':>6}")
        print("-" * 64)
        for r in rows:
            print(f"{r['label']:<22} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7} {r['win_rate_pct']:>6.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, universe=a.universe, maxn=a.maxn, rs_pct=a.rs_pct, tight=a.tight,
            pivot=a.pivot, vmult=a.vmult, trail=a.trail, out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

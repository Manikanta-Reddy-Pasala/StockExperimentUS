"""Breakout momentum on Nasdaq-100 (Donchian high + trailing stop). TRUE daily DD.

Different mechanism from the monthly-rebalance momentum model: it is EVENT-DRIVEN.
Enter when price breaks to a new N-day high inside an uptrend; ride it with a
trailing stop; exit only when the trail is hit (not on a calendar). This produces
a different trade timing + DD profile (let winners run, cut losers via the trail),
so it diversifies the monthly-rotation momentum sleeve.

Rules (daily):
  entry  = close == max(close, last `donchian` days)   [new N-day high]
           AND close > 200d SMA                          [trend filter]
           AND (regime off OR QQQ > its 200d SMA)
  size   = equal-weight up to maxN open names; if more breakouts than free slots,
           take the highest `mom` -day return
  exit   = close <= peak_since_entry * (1 - trail)       [% trailing stop]
           OR close < 100d SMA                            [structural backstop]

Costs: $0 commission (IBKR Lite), 8bps slippage.
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


def load_n100():
    import csv
    out = []
    with open(N100_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("Series", "").strip() == "EQ":
                out.append(r["Symbol"].strip())
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def run(start, end, capital, donchian=100, trail=20.0, maxn=5, mom=60,
        regime=False, label=None, out_dir=None, quiet=False):
    eng = get_engine()
    syms = load_n100()
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=500), "b": end})
        qq = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol='QQQ' "
            "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"a": start - timedelta(days=500), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    dates = cl.index
    present = [s for s in syms if s in cl.columns]

    roll_high = cl.rolling(donchian).max()
    sma200 = cl.rolling(200).mean()
    sma100 = cl.rolling(100).mean()

    qq["date"] = pd.to_datetime(qq["date"])
    qqc = qq.set_index("date")["close"]
    regime_on = (qqc > qqc.rolling(200).mean()).reindex(dates).ffill().fillna(False)

    run_dates = dates[dates >= pd.Timestamp(start)]
    cash = capital
    pos: dict[str, float] = {}        # sym -> shares
    entry_px: dict[str, float] = {}
    peak_px: dict[str, float] = {}
    equity, trades = [], []
    slip = SLIPPAGE_BPS / 1e4
    trail_f = trail / 100.0

    for d in run_dates:
        di = dates.get_loc(d)
        if di < max(donchian, 200):
            equity.append(cash)
            continue
        px_row = cl.iloc[di]

        # 1) EXITS — trailing stop / structural backstop
        for s in list(pos):
            px = float(px_row[s])
            peak_px[s] = max(peak_px.get(s, px), px)
            stop = peak_px[s] * (1 - trail_f)
            if px <= stop or px < float(sma100.iloc[di][s]):
                cash += pos[s] * px * (1 - slip)
                trades.append({"sym": s, "ret_pct": round((px / entry_px[s] - 1) * 100, 2)})
                pos.pop(s); entry_px.pop(s); peak_px.pop(s, None)

        # 2) ENTRIES — new donchian high in uptrend
        risk_on = (not regime) or bool(regime_on.iloc[di])
        slots = maxn - len(pos)
        if risk_on and slots > 0:
            cand = []
            for s in present:
                if s in pos:
                    continue
                px = px_row[s]
                if pd.isna(px) or pd.isna(roll_high.iloc[di][s]) or pd.isna(sma200.iloc[di][s]):
                    continue
                # new N-day high (close at/above rolling high) and uptrend
                if float(px) >= float(roll_high.iloc[di][s]) - 1e-9 and float(px) > float(sma200.iloc[di][s]):
                    r = float(px) / float(cl.iloc[di - mom][s]) - 1 if di >= mom and pd.notna(cl.iloc[di - mom][s]) else 0.0
                    cand.append((r, s))
            cand.sort(reverse=True)  # strongest momentum first
            pv = cash + sum(sh * float(px_row[s]) for s, sh in pos.items() if pd.notna(px_row[s]))
            budget_per = pv / maxn
            for _, s in cand[:slots]:
                px = float(px_row[s])
                sh = budget_per / px
                cost = sh * px * (1 + slip)
                if cost <= cash and sh > 0:
                    cash -= cost
                    pos[s] = sh; entry_px[s] = px; peak_px[s] = px

        val = cash + sum(sh * float(px_row[s]) for s, sh in pos.items() if pd.notna(px_row[s]))
        equity.append(val)

    eq = pd.Series(equity, index=run_dates)
    yrs = (run_dates[-1] - run_dates[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    calmar = cagr / max(0.01, mdd)
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    losses = sum(1 for t in trades if t["ret_pct"] <= 0)

    name = label or f"breakout D{donchian} trail{trail:g} N{maxn}{' regime' if regime else ''}"
    res = {"label": name, "donchian": donchian, "trail": trail, "maxn": maxn, "mom": mom,
           "regime": regime, "start": run_dates[0].date().isoformat(),
           "end": run_dates[-1].date().isoformat(), "years": round(yrs, 2),
           "final_nav": round(final, 0), "cagr_pct": round(cagr, 2),
           "max_dd_pct_daily": round(mdd, 2), "calmar": round(calmar, 2),
           "trades": len(trades), "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1)}
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
    dict(donchian=100, trail=20, maxn=5, label="D100 trail20 N5"),
    dict(donchian=50,  trail=20, maxn=5, label="D50 trail20 N5"),
    dict(donchian=100, trail=15, maxn=5, label="D100 trail15 N5"),
    dict(donchian=100, trail=25, maxn=3, label="D100 trail25 N3"),
    dict(donchian=50,  trail=20, maxn=3, label="D50 trail20 N3"),
    dict(donchian=100, trail=20, maxn=5, regime=True, label="D100 trail20 N5 regime"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--donchian", type=int, default=100)
    ap.add_argument("--trail", type=float, default=20.0)
    ap.add_argument("--maxn", type=int, default=5)
    ap.add_argument("--mom", type=int, default=60)
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== breakout N100 sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<28} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7} {'WR%':>6}")
        print("-" * 72)
        for r in rows:
            print(f"{r['label']:<28} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7} {r['win_rate_pct']:>6.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, donchian=a.donchian, trail=a.trail, maxn=a.maxn, mom=a.mom,
            regime=a.regime, out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

"""Mean-reversion swing model (Connors RSI-2 style) on Nasdaq-100. TRUE daily DD.

A DIFFERENT mechanism from the momentum models: it buys short-term OVERSOLD names
(not winners), inside a longer uptrend, and sells on the bounce. Counter-trend, so
its returns are largely uncorrelated with — often anti-correlated to — momentum,
which is the point: blend it with momentum to cut portfolio drawdown.

Rules (daily):
  candidate  = close > 200d SMA  (only mean-revert inside an uptrend; no falling knives)
               AND RSI(2) < entry_rsi (default 10, deeply oversold)
  rank       = most oversold first (lowest RSI2)
  hold       = up to N names equal-weight (default 5)
  exit       = close > 5d SMA  OR  RSI(2) > exit_rsi (default 70)  OR  max_hold days
  regime     = optional: no NEW entries when QQQ < its 200d SMA (still allows exits)

Short holds (2-6 days typical). Costs: $0 commission (IBKR Lite), 8bps slippage.
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


def rsi(series: pd.Series, period: int) -> pd.Series:
    d = series.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def run(start, end, capital, maxn=5, entry_rsi=10.0, exit_rsi=70.0,
        max_hold=6, regime=False, label=None, out_dir=None, quiet=False):
    eng = get_engine()
    syms = load_n100()
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=400), "b": end})
        qq = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol='QQQ' "
            "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    dates = cl.index
    present = [s for s in syms if s in cl.columns]

    sma200 = cl.rolling(200).mean()
    sma5 = cl.rolling(5).mean()
    rsi2 = cl.apply(lambda col: rsi(col, 2))

    qq["date"] = pd.to_datetime(qq["date"])
    qqc = qq.set_index("date")["close"]
    regime_on = (qqc > qqc.rolling(200).mean()).reindex(dates).ffill().fillna(False)

    run_dates = dates[dates >= pd.Timestamp(start)]
    cash = capital
    pos: dict[str, float] = {}        # sym -> shares
    entry_px: dict[str, float] = {}
    held_days: dict[str, int] = {}
    equity, trades = [], []
    slip = SLIPPAGE_BPS / 1e4

    for d in run_dates:
        di = dates.get_loc(d)
        if di < 200:
            equity.append(cash)
            continue
        px_row = cl.iloc[di]

        # 1) EXITS
        for s in list(pos):
            held_days[s] = held_days.get(s, 0) + 1
            px = float(px_row[s])
            exit_sig = (px > float(sma5.iloc[di][s])) or (float(rsi2.iloc[di][s]) > exit_rsi) \
                or (held_days[s] >= max_hold)
            if exit_sig:
                cash += pos[s] * px * (1 - slip)
                trades.append({"sym": s, "ret_pct": round((px / entry_px[s] - 1) * 100, 2),
                               "days": held_days[s]})
                pos.pop(s); entry_px.pop(s); held_days.pop(s, None)

        # 2) ENTRIES (fill open slots with most-oversold qualifying names)
        risk_on = (not regime) or bool(regime_on.iloc[di])
        slots = maxn - len(pos)
        if risk_on and slots > 0:
            cand = []
            for s in present:
                if s in pos:
                    continue
                px = px_row[s]
                if pd.isna(px) or pd.isna(sma200.iloc[di][s]):
                    continue
                if float(px) > float(sma200.iloc[di][s]) and float(rsi2.iloc[di][s]) < entry_rsi:
                    cand.append((float(rsi2.iloc[di][s]), s))
            cand.sort()
            pv = cash + sum(sh * float(px_row[s]) for s, sh in pos.items() if pd.notna(px_row[s]))
            budget_per = pv / maxn
            for _, s in cand[:slots]:
                px = float(px_row[s])
                sh = (budget_per / px)
                cost = sh * px * (1 + slip)
                if cost <= cash and sh > 0:
                    cash -= cost
                    pos[s] = sh; entry_px[s] = px; held_days[s] = 0

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
    avg_hold = np.mean([t["days"] for t in trades]) if trades else 0

    name = label or f"rsi2 N={maxn} e{entry_rsi:g}/{exit_rsi:g}{' regime' if regime else ''}"
    res = {"label": name, "maxn": maxn, "entry_rsi": entry_rsi, "exit_rsi": exit_rsi,
           "max_hold": max_hold, "regime": regime,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "final_nav": round(final, 0),
           "cagr_pct": round(cagr, 2), "max_dd_pct_daily": round(mdd, 2),
           "calmar": round(calmar, 2), "trades": len(trades),
           "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1),
           "avg_hold_days": round(float(avg_hold), 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}")
        print(f"  Trades {len(trades)}  WR {res['win_rate_pct']}%  avgHold {avg_hold:.1f}d")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
    return res


SWEEP = [
    dict(maxn=5, entry_rsi=10, exit_rsi=70, label="rsi2 N5 10/70"),
    dict(maxn=5, entry_rsi=5,  exit_rsi=70, label="rsi2 N5 5/70 (deeper dip)"),
    dict(maxn=3, entry_rsi=10, exit_rsi=70, label="rsi2 N3 10/70"),
    dict(maxn=10, entry_rsi=10, exit_rsi=70, label="rsi2 N10 10/70"),
    dict(maxn=5, entry_rsi=10, exit_rsi=70, regime=True, label="rsi2 N5 10/70 regime"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--maxn", type=int, default=5)
    ap.add_argument("--entry-rsi", type=float, default=10.0)
    ap.add_argument("--exit-rsi", type=float, default=70.0)
    ap.add_argument("--max-hold", type=int, default=6)
    ap.add_argument("--regime", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== mean-reversion RSI2 sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<28} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Trades':>7} {'WR%':>6} {'Hold':>5}")
        print("-" * 76)
        for r in rows:
            print(f"{r['label']:<28} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['trades']:>7} {r['win_rate_pct']:>6.1f} {r['avg_hold_days']:>5.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, maxn=a.maxn, entry_rsi=a.entry_rsi, exit_rsi=a.exit_rsi,
            max_hold=a.max_hold, regime=a.regime, out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

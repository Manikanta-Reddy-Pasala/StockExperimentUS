"""Sector / asset-class momentum rotation (cross-asset, the diversifier). TRUE daily DD.

Different exposure from the three tech-beta sleeves: it rotates across the 11 S&P
sectors PLUS bonds (TLT), gold (GLD), small-caps (IWM), and international (EEM/EFA),
so in a tech drawdown it can rotate into energy/defensives/bonds/gold. Built to be a
LOW-CORRELATION sleeve that lifts the blended book's Calmar, not to win on raw CAGR.

Rules (monthly):
  score   = mean(3-month return, 6-month return)  per ETF
  rank    = highest score first
  absolute gate (default on): only hold names with score > 0; empty slots -> risk-off
  hold    = top-K equal-weight (default 3); risk-off asset = BIL (T-bills) or cash

Daily mark-to-market equity -> true MaxDD. Costs: $0 commission, 8 bps slippage.
"""
from __future__ import annotations
import sys, os, csv, json, argparse
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

ETF_CSV = str(ROOT / "src/data/symbols/rotation_etfs.csv")
ETF_CSV_OVERRIDE: str | None = None
LB_SHORT = 63    # ~3 months
LB_LONG = 126    # ~6 months
SLIPPAGE_BPS = 8.0
DEFAULT_START = date(2011, 1, 3)
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


def load_etfs():
    out = []
    with open(ETF_CSV_OVERRIDE or ETF_CSV) as f:
        for r in csv.DictReader(f):
            out.append(r["Symbol"].strip())
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def run(start, end, capital, top=3, abs_gate=True, riskoff="bil",
        label=None, out_dir=None, quiet=False):
    eng = get_engine()
    syms = load_etfs()
    allsyms = syms + (["BIL"] if riskoff == "bil" else [])
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,adj_close,close FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": allsyms, "a": start - timedelta(days=400), "b": end})
    df["date"] = pd.to_datetime(df["date"])
    df["px"] = df["adj_close"].fillna(df["close"])
    cl = df.pivot(index="date", columns="symbol", values="px").ffill()
    dates = cl.index
    present = [s for s in syms if s in cl.columns]

    ro_ret = cl["BIL"].pct_change().fillna(0.0) if riskoff == "bil" and "BIL" in cl else pd.Series(0.0, index=dates)

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
    ro_units = 0.0          # notional $ parked in risk-off (grows at ro_ret)
    equity = []
    slip = SLIPPAGE_BPS / 1e4
    weights_hist = []

    prev_ro_px = None
    for d in run_dates:
        di = dates.get_loc(d)
        # accrue risk-off sleeve daily
        if riskoff == "bil" and "BIL" in cl:
            ro_units *= (1 + float(ro_ret.iloc[di]))
        if d in rebal and di >= LB_LONG:
            pv = cash + ro_units + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                                       if pd.notna(cl[s].iloc[di]))
            rs = cl.iloc[di].reindex(present) / cl.iloc[di - LB_SHORT].reindex(present) - 1
            rl = cl.iloc[di].reindex(present) / cl.iloc[di - LB_LONG].reindex(present) - 1
            score = ((rs + rl) / 2).dropna().sort_values(ascending=False)
            picks = [s for s in score.index if (not abs_gate) or score[s] > 0][:top]
            w = (1.0 / top)
            target = {s: w for s in picks}              # remaining (top - len) -> risk-off
            ro_target_w = 1.0 - w * len(picks)

            desired = {s: (wt * pv) / float(cl[s].iloc[di]) for s, wt in target.items()}
            # liquidate names not in target / trim, then buy
            for s in list(set(pos) | set(desired)):
                px = float(cl[s].iloc[di])
                dsh = desired.get(s, 0.0) - pos.get(s, 0.0)
                if abs(dsh) * px < 1e-6:
                    continue
                if dsh < 0:
                    cash += (-dsh) * px * (1 - slip)
                else:
                    cash -= dsh * px * (1 + slip)
                if desired.get(s, 0.0) <= 1e-9:
                    pos.pop(s, None)
                else:
                    pos[s] = desired[s]
            # rebalance risk-off sleeve to target $ (from cash)
            ro_target = ro_target_w * pv
            cash += ro_units - ro_target
            ro_units = ro_target
            weights_hist.append((d, len(picks)))
        val = cash + ro_units + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                                    if pd.notna(cl[s].iloc[di]))
        equity.append(val)

    eq = pd.Series(equity, index=run_dates)
    yrs = (run_dates[-1] - run_dates[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    calmar = cagr / max(0.01, mdd)
    avg_held = (sum(n for _, n in weights_hist) / len(weights_hist)) if weights_hist else 0

    name = label or f"sector top{top}{' absgate' if abs_gate else ''} {riskoff}"
    res = {"label": name, "top": top, "abs_gate": abs_gate, "riskoff": riskoff,
           "start": run_dates[0].date().isoformat(), "end": run_dates[-1].date().isoformat(),
           "years": round(yrs, 2), "final_nav": round(final, 0), "cagr_pct": round(cagr, 2),
           "max_dd_pct_daily": round(mdd, 2), "calmar": round(calmar, 2),
           "avg_names_held": round(avg_held, 1)}
    if not quiet:
        print(f"\n## {name} ({res['start']} -> {res['end']}, {yrs:.2f}y)")
        print(f"  Final ${final:,.0f}  CAGR {cagr:+.2f}%  TrueDailyDD {mdd:.2f}%  Calmar {calmar:.2f}  avgHeld {avg_held:.1f}")
    if out_dir:
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(res, indent=2))
        eq.rename("equity").to_csv(out_dir / "equity_curve.csv")
    return res


SWEEP = [
    dict(top=3, abs_gate=True,  riskoff="bil",  label="sector top3 absgate BIL"),
    dict(top=2, abs_gate=True,  riskoff="bil",  label="sector top2 absgate BIL"),
    dict(top=4, abs_gate=True,  riskoff="bil",  label="sector top4 absgate BIL"),
    dict(top=3, abs_gate=False, riskoff="bil",  label="sector top3 no-gate"),
    dict(top=3, abs_gate=True,  riskoff="cash", label="sector top3 absgate cash"),
    dict(top=1, abs_gate=True,  riskoff="bil",  label="sector top1 absgate BIL"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--no-gate", dest="abs_gate", action="store_false")
    ap.add_argument("--riskoff", choices=["cash", "bil"], default="bil")
    ap.add_argument("--etf-csv", default=None, help="override ETF universe CSV")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.set_defaults(abs_gate=True)
    a = ap.parse_args()
    if a.etf_csv:
        global ETF_CSV_OVERRIDE
        ETF_CSV_OVERRIDE = a.etf_csv
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.sweep:
        rows = [run(s, e, a.capital, quiet=True, **cfg) for cfg in SWEEP]
        print(f"\n=== sector/asset rotation sweep ({rows[0]['start']} -> {rows[0]['end']}, {rows[0]['years']}y) ===")
        print(f"{'variant':<28} {'CAGR%':>8} {'TrueDD%':>8} {'Calmar':>7} {'Held':>5}")
        print("-" * 62)
        for r in rows:
            print(f"{r['label']:<28} {r['cagr_pct']:>8.2f} {r['max_dd_pct_daily']:>8.2f} "
                  f"{r['calmar']:>7.2f} {r['avg_names_held']:>5.1f}")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2))
    else:
        run(s, e, a.capital, top=a.top, abs_gate=a.abs_gate, riskoff=a.riskoff,
            out_dir=Path(a.out) if a.out else None)


if __name__ == "__main__":
    main()

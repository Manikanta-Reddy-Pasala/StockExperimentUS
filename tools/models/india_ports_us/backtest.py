"""US ports of three India models — emerging_momentum, retest (n500), n40 archetypes.

Exploratory: "apply the India selection rules to US Nasdaq and see CAGR/DD."
Self-contained on the proven US daily-MTM engine (same accounting as
momentum_n100_regime_top3): rebuild a DAILY cash+positions equity curve so MaxDD
is the true peak-to-trough.

Universes (static CSV, survivorship-accepted — consistent with the US v2 book;
US has no point-in-time Nasdaq membership data, unlike India's PIT eligible_at):
  n100  = src/data/symbols/nasdaq100.csv          (large caps)
  n500  = src/data/symbols/nasdaq500.csv          (broad pool)
  emerging pool = top-POOL by 20d ADV from (n500 MINUS n100)  -> mid/small leaders

Models:
  emerging : single-position rotation. Rank emerging pool by 15d return (>0).
             Hold 1 name; rotate only when held drops out of top-RETAIN. Monthly
             + mid-month(15-18) check; mid-month switch needs >=5pp 15d-ret lead.
  retest   : top-120-ADV n500 pool. Monthly pick top-K (=2) by 126d momentum that
             sit within 20% above their 20-EMA (pullback/retest). Hold while in
             top-4 rank. Equal weight.
  n40      : top-40-ADV ∩ n100 large caps, WEEKLY top-1 rotation (see also the
             standalone tools/models/n20_daily_large_only).

Costs: 8bps slippage on traded notional (IBKR Lite $0 commission).
Data : data_source='yfinance', plain US tickers.
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

N100_CSV = str(ROOT / "src/data/symbols/nasdaq100.csv")
N500_CSV = str(ROOT / "src/data/symbols/nasdaq500.csv")
SLIPPAGE_BPS = 8.0
DEFAULT_START = date(2021, 3, 1)
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


def load_csv(path):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r.get("Series", "EQ").strip() == "EQ":
                out.append(r["Symbol"].strip())
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(-((equity - peak) / peak).min() * 100)


def load_panels(syms, start, end):
    """Return (close, dollar_vol) pivots, ffilled, indexed by date."""
    eng = get_engine()
    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": syms, "a": start - timedelta(days=400), "b": end})
    df["date"] = pd.to_datetime(df["date"])
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    dv = df.assign(dv=df["close"] * df["volume"]).pivot(
        index="date", columns="symbol", values="dv").ffill()
    return cl, dv


def load_regime(sym, index, start, end):
    """QQQ (or other) > 200d SMA gate, reindexed to `index`."""
    eng = get_engine()
    with eng.connect() as c:
        q = pd.read_sql(text(
            "SELECT date,close FROM historical_data WHERE symbol=:s AND data_source='yfinance' "
            "AND date BETWEEN :a AND :b ORDER BY date"
        ), c, params={"s": sym, "a": start - timedelta(days=400), "b": end})
    q["date"] = pd.to_datetime(q["date"])
    q = q.set_index("date")["close"]
    on = q > q.rolling(200).mean()
    return on.reindex(index).ffill().fillna(False)


def build_rebal(dates, start, end, mid_month=False, weekly=False):
    rebal, mid = set(), set()
    if weekly:                                   # first trading day each ISO week
        cur = None
        for t in dates:
            if t.date() < start or t.date() > end:
                continue
            wk = (t.isocalendar().year, t.isocalendar().week)
            if wk != cur:
                rebal.add(t); cur = wk
        return rebal
    y, m = start.year, start.month
    while True:
        t = pd.Timestamp(y, m, 1)
        fut = dates[dates >= t]
        if len(fut) == 0 or fut[0].date() > end:
            break
        if fut[0].date() >= start:
            rebal.add(fut[0])
        if mid_month:
            fm = dates[dates >= pd.Timestamp(y, m, 15)]
            if len(fm) > 0 and fm[0].date() <= end:
                mid.add(fm[0])
        m += 1
        if m > 12:
            m = 1; y += 1
    return rebal, mid


# --------------------------------------------------------------------------- #
# generic daily-MTM driver: a strategy supplies target weights at rebalances
# --------------------------------------------------------------------------- #
def simulate(cl, run_dates, dates, capital, target_fn, rebal_days, mid_days=None,
             regime_on=None, regime=False):
    slip = SLIPPAGE_BPS / 1e4
    cash = capital
    pos: dict[str, float] = {}
    entry_px, entry_date, entry_di = {}, {}, {}
    equity, trades, txns = [], [], []

    def close_trade(s, d, px, sh, di):
        ep = entry_px.get(s)
        if ep is None:
            return
        trades.append({"symbol": s, "entry_date": entry_date.get(s),
                       "entry_px": round(ep, 4), "shares": round(sh, 4),
                       "exit_date": d.date().isoformat(), "exit_px": round(px, 4),
                       "pnl": round(sh * (px - ep), 2),
                       "ret_pct": round((px / ep - 1) * 100, 2),
                       "bars_held": int(di - entry_di.get(s, di))})

    for d in run_dates:
        di = dates.get_loc(d)
        is_rebal = d in rebal_days or (mid_days is not None and d in mid_days)
        if is_rebal:
            pv = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                            if pd.notna(cl[s].iloc[di]))
            risk_on = (not regime) or (regime_on is not None and bool(regime_on.iloc[di]))
            target = target_fn(di, d, pos, risk_on) if risk_on else {}
            desired = {s: (w * pv) / float(cl[s].iloc[di]) for s, w in target.items()
                       if pd.notna(cl[s].iloc[di]) and float(cl[s].iloc[di]) > 0}
            for s in list(set(pos) | set(desired)):
                px = float(cl[s].iloc[di]) if pd.notna(cl[s].iloc[di]) else None
                if px is None or px <= 0:
                    continue
                cur, tgt = pos.get(s, 0.0), desired.get(s, 0.0)
                dsh = tgt - cur
                if abs(dsh) * px < 1e-6:
                    continue
                if dsh < 0:
                    sh = -dsh; cash += sh * px * (1 - slip)
                    txns.append({"date": d.date().isoformat(), "action": "SELL", "symbol": s,
                                 "price": round(px, 4), "shares": round(sh, 4)})
                    close_trade(s, d, px, sh, di)
                else:
                    cash -= dsh * px * (1 + slip)
                    txns.append({"date": d.date().isoformat(), "action": "BUY", "symbol": s,
                                 "price": round(px, 4), "shares": round(dsh, 4)})
                if tgt <= 1e-9:
                    pos.pop(s, None); entry_px.pop(s, None)
                    entry_date.pop(s, None); entry_di.pop(s, None)
                else:
                    if s not in pos:
                        entry_px[s] = px; entry_date[s] = d.date().isoformat(); entry_di[s] = di
                    pos[s] = tgt
        val = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                         if pd.notna(cl[s].iloc[di]))
        equity.append(val)

    eq = pd.Series(equity, index=run_dates)
    yrs = (run_dates[-1] - run_dates[0]).days / 365.25
    final = float(eq.iloc[-1])
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    tot = len(trades)
    return {"eq": eq, "cagr": cagr, "mdd": mdd, "calmar": cagr / max(0.01, mdd),
            "final": final, "yrs": yrs, "trades": tot,
            "wr": round(wins / max(1, tot) * 100, 1)}, trades, txns


def adv_pool(dv, di, candidates, topn):
    """top-N symbols by trailing 20d ADV among candidates, present at di."""
    win = dv.iloc[max(0, di - 19):di + 1]
    adv = win.mean().reindex(candidates).dropna()
    return list(adv.sort_values(ascending=False).index[:topn])


# --------------------------------------------------------------------------- #
# model selection rules
# --------------------------------------------------------------------------- #
def run_emerging(cl, dv, dates, start, end, capital, pool=100, retain=3,
                 lead_pp=5.0, out_dir=None, regime_on=None, regime=False):
    n100 = set(load_csv(N100_CSV))
    emerging = [s for s in cl.columns if s not in n100]
    rebal, mid = build_rebal(dates, start, end, mid_month=True)
    run_dates = dates[dates >= pd.Timestamp(start)]

    def ret15(di):
        if di - 15 < 0:
            return cl.iloc[di] * np.nan
        return cl.iloc[di] / cl.iloc[di - 15] - 1

    def target_fn(di, d, pos, risk_on):
        cand = adv_pool(dv, di, emerging, pool)
        r = ret15(di).reindex(cand)
        rk = r[r > 0].dropna().sort_values(ascending=False)
        if rk.empty:
            return {}
        held = next(iter(pos), None)
        leader = rk.index[0]
        if held is None:
            return {leader: 1.0}
        top_set = set(rk.index[:retain])
        if held not in top_set:                      # dropped out of top-RETAIN -> rotate
            return {leader: 1.0}
        if d in mid:                                  # mid-month: switch only on strong lead
            hr = rk.get(held, -9)
            if leader != held and rk.iloc[0] - hr >= lead_pp / 100.0:
                return {leader: 1.0}
        return {held: 1.0}                            # keep

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal, mid,
                                 regime_on=regime_on, regime=regime)
    _report("emerging_momentum" + ("_regime" if regime else ""), res, trades, txns, out_dir)
    return res


def run_retest(cl, dv, dates, start, end, capital, pool=120, k=2, retain=4,
               mom_lb=126, ema=20, band=0.20, out_dir=None, regime_on=None, regime=False):
    n500 = [s for s in cl.columns]
    rebal, _ = build_rebal(dates, start, end, mid_month=False)
    run_dates = dates[dates >= pd.Timestamp(start)]
    ema20 = cl.ewm(span=ema, adjust=False).mean()

    def mom(di):
        if di - mom_lb < 0:
            return cl.iloc[di] * np.nan
        return cl.iloc[di] / cl.iloc[di - mom_lb] - 1

    def target_fn(di, d, pos, risk_on):
        cand = adv_pool(dv, di, n500, pool)
        m = mom(di).reindex(cand).dropna()
        rk = m.sort_values(ascending=False)
        top_set = set(rk.index[:retain])
        # retest filter: price within `band` above its 20-EMA (pullback, not extended)
        px = cl.iloc[di]; e = ema20.iloc[di]
        retest_ok = {s for s in rk.index
                     if pd.notna(px.get(s)) and pd.notna(e.get(s)) and e.get(s) > 0
                     and px[s] <= e[s] * (1 + band)}
        keep = [s for s in pos if s in top_set]      # hold while in top-RETAIN
        slots = k - len(keep)
        for s in rk.index:
            if slots <= 0:
                break
            if s in keep or s not in retest_ok:
                continue
            keep.append(s); slots -= 1
        if not keep:
            return {}
        w = 1.0 / len(keep)
        return {s: w for s in keep}

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal,
                                 regime_on=regime_on, regime=regime)
    _report("momentum_retest_n500" + ("_regime" if regime else ""), res, trades, txns, out_dir)
    return res


def run_n40(cl, dv, dates, start, end, capital, topadv=40, mom_lb=63, out_dir=None,
            regime_on=None, regime=False):
    n100 = [s for s in cl.columns if s in set(load_csv(N100_CSV))]
    rebal = build_rebal(dates, start, end, weekly=True)
    run_dates = dates[dates >= pd.Timestamp(start)]

    def mom(di):
        if di - mom_lb < 0:
            return cl.iloc[di] * np.nan
        return cl.iloc[di] / cl.iloc[di - mom_lb] - 1

    def target_fn(di, d, pos, risk_on):
        cand = adv_pool(dv, di, n100, topadv)        # top-40 ADV large caps
        m = mom(di).reindex(cand)
        rk = m[m > 0].dropna().sort_values(ascending=False)
        if rk.empty:
            return {}
        return {rk.index[0]: 1.0}                     # weekly top-1

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal,
                                 regime_on=regime_on, regime=regime)
    _report("n40_large_weekly" + ("_regime" if regime else ""), res, trades, txns, out_dir)
    return res


def _report(name, res, trades, txns, out_dir):
    print(f"\n## {name} ({res['eq'].index[0].date()} -> {res['eq'].index[-1].date()}, {res['yrs']:.2f}y)")
    print(f"  Final ${res['final']:,.0f}  CAGR {res['cagr']:+.2f}%  TrueDailyDD {res['mdd']:.2f}%  "
          f"Calmar {res['calmar']:.2f}  Trades {res['trades']}  WR {res['wr']}%")
    if out_dir:
        d = Path(out_dir) / name; d.mkdir(parents=True, exist_ok=True)
        summary = {k: (round(v, 2) if isinstance(v, float) else v)
                   for k, v in res.items() if k != "eq"}
        summary["model"] = name
        (d / "summary.json").write_text(json.dumps(summary, indent=2))
        res["eq"].rename("equity").to_csv(d / "equity_curve.csv")
        if trades:
            pd.DataFrame(trades).to_csv(d / "trade_ledger.csv", index=False)
        if txns:
            pd.DataFrame(txns).to_csv(d / "transactions.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["emerging", "retest", "n40", "all"], default="all")
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to", dest="end", default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--regime", action="store_true", help="QQQ 200d cash gate (cuts DD)")
    ap.add_argument("--regime-sym", default="QQQ")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    s, e = date.fromisoformat(a.start), date.fromisoformat(a.end)

    # one panel load for the broad universe (covers all three models)
    n500 = load_csv(N500_CSV)
    n100 = load_csv(N100_CSV)
    syms = sorted(set(n500) | set(n100))
    cl, dv = load_panels(syms, s, e)
    dates = cl.index
    reg = load_regime(a.regime_sym, dates, s, e) if a.regime else None

    if a.model in ("emerging", "all"):
        run_emerging(cl, dv, dates, s, e, a.capital, out_dir=a.out, regime_on=reg, regime=a.regime)
    if a.model in ("retest", "all"):
        run_retest(cl, dv, dates, s, e, a.capital, out_dir=a.out, regime_on=reg, regime=a.regime)
    if a.model in ("n40", "all"):
        run_n40(cl, dv, dates, s, e, a.capital, out_dir=a.out, regime_on=reg, regime=a.regime)


if __name__ == "__main__":
    main()

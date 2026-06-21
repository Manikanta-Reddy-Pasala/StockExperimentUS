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
def momscore(cl, di, mode="ret", lb=15):
    """Momentum score row at bar di. mode: 'ret'=lb-day return, 'blend'=avg(21/63/126)."""
    if mode == "blend":
        s = None
        for w in (21, 63, 126):
            if di - w < 0:
                continue
            r = cl.iloc[di] / cl.iloc[di - w] - 1
            s = r if s is None else s + r
        return s / 3.0 if s is not None else cl.iloc[di] * np.nan
    if di - lb < 0:
        return cl.iloc[di] * np.nan
    return cl.iloc[di] / cl.iloc[di - lb] - 1


def simulate(cl, run_dates, dates, capital, target_fn, rebal_days, mid_days=None,
             regime_on=None, regime=False, trail=0.0, lev=1.0, margin_apr=0.0):
    """lev>1 = apply margin to the target weights (cash goes negative = borrowing).
    margin_apr = annual borrow cost charged daily on negative cash (e.g. 0.06 = IBKR-ish)."""
    slip = SLIPPAGE_BPS / 1e4
    trail_f = trail / 100.0
    daily_borrow = margin_apr / 252.0
    cash = capital
    pos: dict[str, float] = {}
    entry_px, entry_date, entry_di, peak_px = {}, {}, {}, {}
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
        # daily per-position trailing stop (checked every bar, cuts DD)
        if trail_f > 0 and pos:
            for s in list(pos):
                px = cl[s].iloc[di]
                if pd.isna(px):
                    continue
                px = float(px)
                peak_px[s] = max(peak_px.get(s, px), px)
                if px <= peak_px[s] * (1 - trail_f):
                    cash += pos[s] * px * (1 - slip)
                    txns.append({"date": d.date().isoformat(), "action": "SELL_TRAIL",
                                 "symbol": s, "price": round(px, 4), "shares": round(pos[s], 4)})
                    close_trade(s, d, px, pos[s], di)
                    pos.pop(s, None); entry_px.pop(s, None); peak_px.pop(s, None)
                    entry_date.pop(s, None); entry_di.pop(s, None)
        is_rebal = d in rebal_days or (mid_days is not None and d in mid_days)
        if is_rebal:
            pv = cash + sum(sh * float(cl[s].iloc[di]) for s, sh in pos.items()
                            if pd.notna(cl[s].iloc[di]))
            risk_on = (not regime) or (regime_on is not None and bool(regime_on.iloc[di]))
            target = target_fn(di, d, pos, risk_on) if risk_on else {}
            desired = {s: (w * lev * pv) / float(cl[s].iloc[di]) for s, w in target.items()
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
                    pos.pop(s, None); entry_px.pop(s, None); peak_px.pop(s, None)
                    entry_date.pop(s, None); entry_di.pop(s, None)
                else:
                    if s not in pos:
                        entry_px[s] = px; peak_px[s] = px
                        entry_date[s] = d.date().isoformat(); entry_di[s] = di
                    pos[s] = tgt
        if daily_borrow > 0 and cash < 0:        # margin interest on borrowed cash
            cash += cash * daily_borrow
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
def run_emerging(cl, dv, dates, start, end, capital, pool=100, top=1, retain=3,
                 lead_pp=5.0, signal="ret", siglb=15, trail=0.0,
                 out_dir=None, regime_on=None, regime=False, tag="",
                 membership_csv=None):
    """top=1 = faithful single-position India spec. top>1 = IMPROVED diversified
    top-K equal-weight rotation (cuts the 80% single-name DD).

    `membership_csv` (optional): PIT index membership CSV. When provided, the
    emerging pool (panel MINUS n100) is restricted at EACH rebalance to symbols
    that were index members on that date (survivorship-correct). When None,
    behavior is byte-for-byte unchanged (full current-panel emerging pool)."""
    n100 = set(load_csv(N100_CSV))
    emerging = [s for s in cl.columns if s not in n100]
    rebal, mid = build_rebal(dates, start, end, mid_month=True)
    run_dates = dates[dates >= pd.Timestamp(start)]

    intervals = None
    if membership_csv is not None:
        from tools.shared.us_index_membership import load_membership, eligible_at
        intervals = load_membership(membership_csv)

    def target_fn(di, d, pos, risk_on):
        pool_syms = emerging
        if intervals is not None:
            members = eligible_at(intervals, dates[di])
            pool_syms = [s for s in emerging if s in members]
        cand = adv_pool(dv, di, pool_syms, pool)
        rk = momscore(cl, di, signal, siglb).reindex(cand)
        rk = rk[rk > 0].dropna().sort_values(ascending=False)
        if rk.empty:
            return {}
        if top > 1:                                  # diversified top-K, fresh each rebalance
            picks = list(rk.index[:top])
            w = 1.0 / len(picks)
            return {s: w for s in picks}
        held = next(iter(pos), None)                 # single-position retention (faithful)
        leader = rk.index[0]
        if held is None:
            return {leader: 1.0}
        if held not in set(rk.index[:retain]):
            return {leader: 1.0}
        if d in mid and leader != held and rk.iloc[0] - rk.get(held, -9) >= lead_pp / 100.0:
            return {leader: 1.0}
        return {held: 1.0}

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal, mid,
                                 regime_on=regime_on, regime=regime, trail=trail)
    _report(f"emerging{tag}", res, trades, txns, out_dir)
    return res


def pick_retest_holdings(cl, dv, ema20, di, universe, pos=None, pool=120, k=2,
                         retain=4, mom_lb=126, band=0.20, signal="ret"):
    """The retest selection rule, factored out for reuse by live_signal.py.

    Given the close panel `cl`, dollar-volume panel `dv`, the precomputed EMA
    panel `ema20` (= cl.ewm(span=ema).mean()), the integer bar index `di`, and
    the candidate `universe` (list of symbols present in cl.columns), return
    {symbol: weight} for the target retest holdings:
      1. take the top-`pool` symbols of `universe` by trailing-20d ADV
      2. score them by `signal` momentum over `mom_lb` days, rank desc
      3. retain held names that are still inside the top-`retain` rank
      4. fill remaining slots (up to `k`) with the highest-ranked names that are
         in a "retest" zone: price <= EMA20 * (1 + band)
      5. equal-weight the survivors (empty dict if none qualify)

    `pos` is the current holdings dict ({symbol: weight} or {symbol: shares});
    only its KEYS are used (which names are currently held). Pass {} or None for
    a fresh basket (live observer has no positions to retain).

    This is the SAME logic the backtest's run_retest target_fn uses — keep them
    in sync (the regime gate lives in `simulate`, not here).
    """
    pos = pos or {}
    cand = adv_pool(dv, di, universe, pool)
    sig = momscore(cl, di, signal, mom_lb) if signal == "blend" else \
        (cl.iloc[di] / cl.iloc[di - mom_lb] - 1 if di - mom_lb >= 0 else cl.iloc[di] * np.nan)
    rk = sig.reindex(cand).dropna().sort_values(ascending=False)
    top_set = set(rk.index[:retain])
    px = cl.iloc[di]
    e = ema20.iloc[di]
    retest_ok = {s for s in rk.index
                 if pd.notna(px.get(s)) and pd.notna(e.get(s)) and e.get(s) > 0
                 and px[s] <= e[s] * (1 + band)}
    keep = [s for s in pos if s in top_set]
    slots = k - len(keep)
    for s in rk.index:
        if slots <= 0:
            break
        if s in keep or s not in retest_ok:
            continue
        keep.append(s)
        slots -= 1
    if not keep:
        return {}
    w = 1.0 / len(keep)
    return {s: w for s in keep}


def run_retest(cl, dv, dates, start, end, capital, pool=120, k=2, retain=4,
               mom_lb=126, ema=20, band=0.20, signal="ret", trail=0.0,
               out_dir=None, regime_on=None, regime=False, tag="",
               membership_csv=None):
    """`membership_csv` (optional): PIT index membership CSV. When provided, the
    broad candidate pool (full panel) is restricted at EACH rebalance to symbols
    that were index members on that date (survivorship-correct). When None,
    behavior is byte-for-byte unchanged (full current panel)."""
    n500 = [s for s in cl.columns]
    rebal, _ = build_rebal(dates, start, end, mid_month=False)
    run_dates = dates[dates >= pd.Timestamp(start)]
    ema20 = cl.ewm(span=ema, adjust=False).mean()

    intervals = None
    if membership_csv is not None:
        from tools.shared.us_index_membership import load_membership, eligible_at
        intervals = load_membership(membership_csv)

    def target_fn(di, d, pos, risk_on):
        pool_syms = n500
        if intervals is not None:
            members = eligible_at(intervals, dates[di])
            pool_syms = [s for s in n500 if s in members]
        return pick_retest_holdings(cl, dv, ema20, di, pool_syms, pos=pos,
                                    pool=pool, k=k, retain=retain, mom_lb=mom_lb,
                                    band=band, signal=signal)

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal,
                                 regime_on=regime_on, regime=regime, trail=trail)
    _report(f"retest{tag}", res, trades, txns, out_dir)
    return res


def pick_n40_holdings(cl, dv, di, universe, topadv=40, top=3, mom_lb=63,
                      signal="blend"):
    """The n40 selection rule, factored out for reuse by live_signal.py.

    Given the close panel `cl`, dollar-volume panel `dv`, and the integer bar
    index `di`, return {symbol: weight} for the target top-`top` holdings:
      1. take the top-`topadv` symbols of `universe` by trailing-20d ADV
      2. score them by `signal` momentum (blend = avg(21/63/126d return))
      3. keep only strictly-positive scores, sort desc, take top-`top`
      4. equal-weight the survivors (empty dict if none qualify)

    `universe` is the list of candidate symbols present in `cl.columns`.
    This is the SAME logic the backtest's target_fn uses — keep them in sync
    (the regime gate + leverage live in `simulate`, not here).
    """
    cand = adv_pool(dv, di, universe, topadv)
    rk = momscore(cl, di, signal, mom_lb).reindex(cand)
    rk = rk[rk > 0].dropna().sort_values(ascending=False)
    if rk.empty:
        return {}
    picks = list(rk.index[:top])
    w = 1.0 / len(picks)
    return {s: w for s in picks}


def run_n40(cl, dv, dates, start, end, capital, topadv=40, top=1, mom_lb=63,
            signal="ret", trail=0.0, out_dir=None, regime_on=None, regime=False, tag="",
            lev=1.0, margin_apr=0.0, membership_csv=None):
    """`membership_csv` (optional): path to a point-in-time index membership CSV
    (schema symbol,start_date,end_date). When provided, the selection universe is
    the FULL panel (cl.columns) restricted at EACH rebalance to the symbols that
    were index members on that date (survivorship-correct). When None, behavior is
    byte-for-byte unchanged: the universe is cl.columns ∩ Nasdaq-100."""
    rebal = build_rebal(dates, start, end, weekly=True)
    run_dates = dates[dates >= pd.Timestamp(start)]

    if membership_csv is None:
        # legacy / non-PIT path — DO NOT CHANGE (existing models/results depend on it)
        n100 = [s for s in cl.columns if s in set(load_csv(N100_CSV))]

        def target_fn(di, d, pos, risk_on):
            return pick_n40_holdings(cl, dv, di, n100, topadv=topadv, top=top,
                                     mom_lb=mom_lb, signal=signal)
    else:
        # PIT path — full panel universe, gated to actual members at each bar's date
        from tools.shared.us_index_membership import load_membership, eligible_at
        intervals = load_membership(membership_csv)
        panel = list(cl.columns)

        def eligible_set_for_di(di):
            members = eligible_at(intervals, dates[di])
            return [s for s in panel if s in members]

        def target_fn(di, d, pos, risk_on):
            universe = eligible_set_for_di(di)
            return pick_n40_holdings(cl, dv, di, universe, topadv=topadv, top=top,
                                     mom_lb=mom_lb, signal=signal)

    res, trades, txns = simulate(cl, run_dates, dates, capital, target_fn, rebal,
                                 regime_on=regime_on, regime=regime, trail=trail,
                                 lev=lev, margin_apr=margin_apr)
    _report(f"n40{tag}", res, trades, txns, out_dir)
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
    ap.add_argument("--top", type=int, default=1, help="diversify: hold top-K (>1 = improved)")
    ap.add_argument("--signal", choices=["ret", "blend"], default="ret",
                    help="blend = avg(21/63/126d return), the US v2 alpha signal")
    ap.add_argument("--trail", type=float, default=0.0, help="per-position trailing stop %%")
    ap.add_argument("--sweep", action="store_true", help="grid search improved configs")
    ap.add_argument("--membership-csv", default=None,
                    help="PIT index membership CSV (survivorship-correct universe gating); "
                         "applies to whichever model(s) run")
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

    if a.sweep:
        return sweep(cl, dv, dates, s, e, a.capital, reg)

    if a.model in ("emerging", "all"):
        run_emerging(cl, dv, dates, s, e, a.capital, top=a.top, signal=a.signal, trail=a.trail,
                     out_dir=a.out, regime_on=reg, regime=a.regime,
                     membership_csv=a.membership_csv,
                     tag=f"_top{a.top}_{a.signal}" + ("_reg" if a.regime else ""))
    if a.model in ("retest", "all"):
        run_retest(cl, dv, dates, s, e, a.capital, k=max(2, a.top), signal=a.signal, trail=a.trail,
                   out_dir=a.out, regime_on=reg, regime=a.regime,
                   membership_csv=a.membership_csv,
                   tag=f"_k{max(2,a.top)}_{a.signal}" + ("_reg" if a.regime else ""))
    if a.model in ("n40", "all"):
        run_n40(cl, dv, dates, s, e, a.capital, top=a.top, signal=a.signal, trail=a.trail,
                out_dir=a.out, regime_on=reg, regime=a.regime,
                membership_csv=a.membership_csv,
                tag=f"_top{a.top}_{a.signal}" + ("_reg" if a.regime else ""))


def sweep(cl, dv, dates, s, e, capital, reg):
    """Grid-search improved configs; flag those clearing 60% CAGR."""
    rows = []
    for top in (3, 5):
        for sig in ("ret", "blend"):
            for tr in (0.0, 20.0):
                r = run_emerging(cl, dv, dates, s, e, capital, top=top, signal=sig, trail=tr,
                                 regime_on=reg, regime=reg is not None, tag="")
                rows.append((f"emerging top{top} {sig} trail{tr:.0f} reg", r))
                r = run_n40(cl, dv, dates, s, e, capital, top=top, signal=sig, trail=tr,
                            regime_on=reg, regime=reg is not None, tag="")
                rows.append((f"n40 top{top} {sig} trail{tr:.0f} reg", r))
    for k in (3, 4, 6):
        for sig in ("ret", "blend"):
            r = run_retest(cl, dv, dates, s, e, capital, k=k, signal=sig,
                           regime_on=reg, regime=reg is not None, tag="")
            rows.append((f"retest k{k} {sig} reg", r))
    print("\n================ SWEEP (>=60% CAGR flagged ***) ================")
    print(f"{'config':<34}{'CAGR%':>9}{'DD%':>8}{'Calmar':>8}")
    for name, r in sorted(rows, key=lambda x: -x[1]["cagr"]):
        flag = " ***" if r["cagr"] >= 60 else ""
        print(f"{name:<34}{r['cagr']:>9.1f}{r['mdd']:>8.1f}{r['calmar']:>8.2f}{flag}")


if __name__ == "__main__":
    main()

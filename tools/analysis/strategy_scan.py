"""Breadth scan of DISTINCT US-equity strategy archetypes (not momentum reskins).

Tests genuinely different mechanisms on the data we have (QQQ OHLC + Nasdaq-100 closes)
and reports CAGR / true daily MaxDD / Calmar / #trades / correlation-to-MOM, so we can
see whether any non-momentum edge is worth turning into a model.

Archetypes:
  1. overnight_qqq   - hold QQQ close->next-open only (the US "overnight return" anomaly)
  2. intraday_qqq    - hold QQQ open->close only (the mirror; usually weak in the US)
  3. turn_of_month   - hold QQQ only last trading day + first 3 of each month, else cash
  4. sell_in_may     - hold QQQ Nov-Apr, cash May-Oct (Halloween/seasonality effect)
  5. index_meanrev   - QQQ RSI(2)<10 dip-buy in a 200d uptrend, exit on bounce
  6. lowvol_n100     - monthly: hold 10 lowest-90d-vol Nasdaq-100 names above 200d SMA

Costs: 8 bps slippage per position change (overnight/intraday trade daily -> heavy).
"""
from __future__ import annotations
import sys, os, csv
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
N100_CSV = str(ROOT / "src/data/symbols/nasdaq100.csv")
SLIP = 8e-4


def get_engine():
    url = os.environ.get("DATABASE_URL",
                         "postgresql+psycopg2://trader:trader_password@localhost:5432/trading_system")
    if url.startswith("postgresql+psycopg://"):
        try:
            import psycopg  # noqa
        except ImportError:
            url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def stats(eq):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1) * 100
    mdd = float(-((eq - eq.cummax()) / eq.cummax()).min() * 100)
    return cagr, mdd, cagr / max(0.01, mdd)


def load_n100():
    out = []
    with open(N100_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("Series", "").strip() == "EQ":
                out.append(r["Symbol"].strip())
    return out


def run(start, end):
    eng = get_engine()
    with eng.connect() as c:
        q = pd.read_sql(text("SELECT date,open,close FROM historical_data WHERE symbol='QQQ' "
                             "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY date"),
                        c, params={"a": start - timedelta(days=400), "b": end})
        n = pd.read_sql(text("SELECT symbol,date,close FROM historical_data WHERE symbol=ANY(:s) "
                             "AND data_source='yfinance' AND date BETWEEN :a AND :b ORDER BY symbol,date"),
                        c, params={"s": load_n100(), "a": start - timedelta(days=400), "b": end})
    q["date"] = pd.to_datetime(q["date"]); q = q.set_index("date")
    n["date"] = pd.to_datetime(n["date"])
    cl = n.pivot(index="date", columns="symbol", values="close").ffill()

    full = q.index
    rd = full[full >= pd.Timestamp(start)]
    o, c_ = q["open"], q["close"]
    co_ret = (o / c_.shift(1) - 1).reindex(rd).fillna(0)      # overnight
    oc_ret = (c_ / o - 1).reindex(rd).fillna(0)               # intraday
    cc_ret = c_.pct_change().reindex(rd).fillna(0)            # close-to-close

    res = {}

    def eq_from(daily_ret, cost=0.0):
        r = daily_ret - cost
        return (1 + r).cumprod()

    # 1 overnight, 2 intraday (trade daily -> 2x slip/day)
    res["overnight_qqq"] = (eq_from(co_ret, SLIP * 2), int(len(rd)))
    res["intraday_qqq"]  = (eq_from(oc_ret, SLIP * 2), int(len(rd)))

    # 3 turn-of-month: in market last trading day + first 3 of month
    tom = pd.Series(False, index=rd)
    bym = pd.Series(rd, index=rd).groupby([rd.year, rd.month])
    for _, grp in bym:
        days = list(grp)
        for d in days[:3]:
            tom[d] = True
    # last trading day of each month
    month_id = pd.Series([(d.year, d.month) for d in rd], index=rd)
    last_days = rd.to_series().groupby(month_id.values).max()
    for d in last_days:
        tom[d] = True
    held = tom.shift(1).fillna(False)
    sw = held.ne(held.shift()).sum()
    res["turn_of_month"] = (eq_from(cc_ret * held.astype(float), 0).rename("e"), int(sw))
    res["turn_of_month"] = (((1 + cc_ret * held.astype(float) - held.ne(held.shift()).astype(float) * SLIP).cumprod()), int(sw))

    # 4 sell in may: hold Nov-Apr
    inmkt = pd.Series([d.month in (11, 12, 1, 2, 3, 4) for d in rd], index=rd)
    held4 = inmkt.shift(1).fillna(False)
    res["sell_in_may"] = (((1 + cc_ret * held4.astype(float) - held4.ne(held4.shift()).astype(float) * SLIP).cumprod()),
                          int(held4.ne(held4.shift()).sum()))

    # 5 index mean-reversion on QQQ: RSI2<10 & >200d, exit RSI2>50 or close>5d SMA
    def rsi(s, p):
        d = s.diff(); g = d.clip(lower=0).rolling(p).mean(); l = (-d.clip(upper=0)).rolling(p).mean()
        return (100 - 100 / (1 + g / l.replace(0, np.nan))).fillna(50)
    r2 = rsi(c_, 2); sma200 = c_.rolling(200).mean(); sma5 = c_.rolling(5).mean()
    pos = False; e = 1.0; eqs = []; trades = 0
    for d in rd:
        prev = e
        if pos:
            e *= (1 + cc_ret[d])
        if pos and (float(r2[d]) > 50 or c_[d] > sma5[d]):
            e *= (1 - SLIP); pos = False
        elif (not pos) and float(r2[d]) < 10 and c_[d] > sma200[d]:
            e *= (1 - SLIP); pos = True; trades += 1
        eqs.append(e)
    res["index_meanrev"] = (pd.Series(eqs, index=rd), trades)

    # 6 low-vol N100: monthly hold 10 lowest 90d-vol names above 200d SMA
    rets = cl.pct_change()
    vol90 = rets.rolling(90).std()
    sma200n = cl.rolling(200).mean()
    rebal = set()
    y, m = start.year, start.month
    while True:
        t = pd.Timestamp(y, m, 1); fut = full[full >= t]
        if len(fut) == 0 or fut[0].date() > end: break
        if fut[0].date() >= start: rebal.add(fut[0])
        m += 1
        if m > 12: m = 1; y += 1
    cash = 1.0; held_w = {}; eqs = []; trades = 0
    for d in rd:
        if d not in cl.index:
            eqs.append(cash); continue
        ci = cl.index.get_loc(d)
        if d in rebal and ci >= 200:
            vrow, srow, prow = vol90.loc[d], sma200n.loc[d], cl.loc[d]
            cand = [(float(vrow[s]), s) for s in cl.columns
                    if pd.notna(vrow[s]) and pd.notna(srow[s]) and prow[s] > srow[s]]
            cand.sort()
            picks = [s for _, s in cand[:10]]
            held_w = {s: 1.0 / len(picks) for s in picks} if picks else {}
            trades += 1
        if held_w:
            rrow = rets.loc[d]
            pr = sum(w * float(rrow[s]) for s, w in held_w.items() if pd.notna(rrow[s]))
        else:
            pr = 0.0
        cash *= (1 + pr)
        eqs.append(cash)
    res["lowvol_n100"] = (pd.Series(eqs, index=rd), trades)

    # MOM curve for correlation
    mom_path = ROOT / "exports/backtests/us/blend3/mom/equity_curve.csv"
    mom = None
    if mom_path.exists():
        mdf = pd.read_csv(mom_path, index_col=0, parse_dates=True)["equity"]
        mom = mdf.pct_change()

    print(f"\n=== US strategy-archetype scan ({rd[0].date()} -> {rd[-1].date()}, "
          f"{(rd[-1]-rd[0]).days/365.25:.2f}y, 8bps slip) ===")
    print(f"{'archetype':<16} {'CAGR%':>8} {'MaxDD%':>8} {'Calmar':>7} {'trades':>7} {'corrMOM':>8}")
    print("-" * 64)
    for k, (eq, tr) in res.items():
        cg, dd, cal = stats(eq)
        if mom is not None:
            j = pd.concat([eq.pct_change(), mom], axis=1, join="inner").dropna()
            cm = j.corr().iloc[0, 1] if len(j) > 2 else float("nan")
        else:
            cm = float("nan")
        print(f"{k:<16} {cg:>8.2f} {dd:>8.2f} {cal:>7.2f} {tr:>7} {cm:>8.2f}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2023-05-24")
    ap.add_argument("--to", dest="end", default="2026-05-24")
    a = ap.parse_args()
    run(date.fromisoformat(a.start), date.fromisoformat(a.end))

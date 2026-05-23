"""Standalone backtest: pseudo-N100 (ADV-rank from N500, yearly PIT rebuild, MINUS Small).

Reproduces +136.39% CAGR (10L -> 1.32 Cr) over 2023-05-15 to 2026-05-12.

Same strategy as momentum_n100_top5_max1 (lb=30, mc=1, monthly, top-1) but
universe = top-100 by 20-day ADV at each year-start instead of NSE Nifty 100.
"""
import sys, json, argparse
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pandas as pd
from sqlalchemy import text
from tools.shared.ohlcv_cache import _get_engine
from tools.shared.universes import nasdaq500_symbols


LOOKBACK = 30
ADV_WIN  = 20
UNIV_SIZE = 100
MAX_PRICE = 1e9  # off for $1M backtest (was Rs.3000 share-count floor for Rs.30k live)
# No US small-cap exclusion list built; keep empty for parity with the India model.
_SMALLCAP = set()
DEFAULT_START = date(2022, 5, 24)
DEFAULT_END   = date(2026, 5, 24)
DEFAULT_CAP   = 1_000_000.0


def run(start: date, end: date, capital: float, out_dir: Path | None = None):
    eng = _get_engine()
    n500 = [s for s, _ in nasdaq500_symbols()]
    print(f"Nasdaq 500 pool: {len(n500)}")

    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' "
            "ORDER BY symbol,date"
        ), c, params={"s": n500, "a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    df["adv_rs"] = df["close"].astype(float) * df["volume"].astype(float)
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    adv_rs = df.pivot(index="date", columns="symbol", values="adv_rs").fillna(0)
    adv20 = adv_rs.rolling(ADV_WIN).mean()
    sma200 = cl.rolling(200).mean()  # uptrend filter
    dates = cl.index

    # Yearly-PIT universe rebuild
    year_starts = []
    cur = start
    while cur <= end:
        year_starts.append(pd.Timestamp(cur))
        cur = cur.replace(year=cur.year + 1)

    year_universes = {}
    for ys in year_starts:
        fut = dates[dates >= ys]
        if len(fut) == 0: continue
        di = dates.get_loc(fut[0])
        pit_adv = adv20.iloc[di].dropna().sort_values(ascending=False)
        top = pit_adv.head(UNIV_SIZE).index.tolist()
        # Drop Small-cap names from top-100 (sweep showed +2pp CAGR, DD unchanged)
        year_universes[ys] = [s for s in top if s.replace("NSE:","").replace("-EQ","") not in _SMALLCAP]

    def pick_universe(d):
        chosen = year_starts[0]
        for ys in year_starts:
            if d >= ys:
                chosen = ys
        return year_universes.get(chosen, [])

    rebal_set = set()
    y, m = start.year, start.month
    while True:
        target = pd.Timestamp(y, m, 1)
        fut = dates[dates >= target]
        if len(fut) == 0 or fut[0].date() > end: break
        if fut[0].date() >= start:
            rebal_set.add(fut[0])
        m += 1
        if m > 12: m = 1; y += 1
    sd = pd.Timestamp(start)
    if sd in dates: rebal_set.add(sd)
    rebal = sorted(rebal_set)

    cap = capital
    hold = None; qty = 0; entry_px = 0.0; entry_date = None
    trades = []

    for d in rebal:
        di = dates.get_loc(d)
        if di < max(LOOKBACK, 200): continue
        univ = pick_universe(d)
        # Uptrend filter: keep only stocks with close > 200d SMA
        up = sma200.iloc[di] < cl.iloc[di]
        univ = [s for s in univ if bool(up.get(s, False))]
        # Max-price filter — high-px (>₹3000) stocks were net-loss in backtest (DIXON/MARUTI)
        univ = [s for s in univ if pd.notna(cl[s].iloc[di]) and float(cl[s].iloc[di]) <= MAX_PRICE]
        if not univ: continue
        rets = cl.iloc[di].reindex(univ) / cl.iloc[di - LOOKBACK].reindex(univ) - 1
        rk = rets.dropna().sort_values(ascending=False)
        if rk.empty: continue
        top = rk.index[0]

        if top != hold:
            if hold and qty > 0:
                sx = cl[hold].iloc[di]
                if pd.notna(sx):
                    sx = float(sx)
                    proc = qty * sx
                    cap += proc
                    pnl = proc - qty * entry_px
                    pct = (sx / entry_px - 1) * 100
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date":  d.date().isoformat(),
                        "sym":        hold.replace("NSE:", "").replace("-EQ", ""),
                        "qty":        qty,
                        "entry_px":   round(entry_px, 2),
                        "exit_px":    round(sx, 2),
                        "pnl":        round(pnl, 0),
                        "ret_pct":    round(pct, 2),
                        "cap_after":  round(cap, 0),
                    })
                    hold = None; qty = 0

            bx = cl[top].iloc[di]
            if pd.notna(bx):
                bx = float(bx)
                q = int(cap / bx)
                if q >= 1 and q * bx <= cap:
                    cap -= q * bx
                    qty = q; hold = top
                    entry_px = bx
                    entry_date = d.date().isoformat()

    final = cap
    open_pos = None
    if hold:
        last = float(cl[hold].iloc[-1])
        final = cap + qty * last
        open_pos = {
            "sym": hold.replace("NSE:", "").replace("-EQ", ""),
            "qty": qty,
            "entry_px": round(entry_px, 2),
            "entry_date": entry_date,
            "last_px": round(last, 2),
            "mtm_value": round(qty * last, 0),
            "unrealized_pnl": round(qty * (last - entry_px), 0),
        }

    wins   = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    yrs    = (end - start).days / 365.25
    cagr   = ((final / capital) ** (1 / yrs) - 1) * 100

    # Rebal-day cap_after DD (realized only; matches old reporting)
    peak = capital; mdd = 0.0
    for t in trades:
        peak = max(peak, t["cap_after"])
        dd = (peak - t["cap_after"]) / peak * 100
        mdd = max(mdd, dd)
    calmar = cagr / max(0.01, mdd)

    print(f"\nFinal NAV: ${final:,.0f}")
    print(f"Total: {(final/capital-1)*100:+.2f}%  CAGR: {cagr:+.2f}%")
    print(f"Trades: {len(trades)} (W={wins} L={losses}, WR={wins/max(1,wins+losses)*100:.1f}%)")
    print(f"Max DD (rebal cap_after): {mdd:.2f}%  Calmar: {calmar:.2f}")

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trade_ledger.json").write_text(json.dumps(trades, indent=2))
        summary = {
            "model": "momentum_pseudo_n100_adv",
            "start": start.isoformat(), "end": end.isoformat(),
            "years": round(yrs, 3),
            "capital": capital, "final_nav": round(final, 0),
            "total_return_pct": round((final / capital - 1) * 100, 2),
            "cagr_pct": round(cagr, 2),
            "max_dd_pct": round(mdd, 2),
            "calmar": round(calmar, 2),
            "trades": len(trades),
            "wins": wins, "losses": losses,
            "win_rate_pct": round(wins / max(1, wins + losses) * 100, 1),
            "open_position": open_pos,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    return final, cagr, trades


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=DEFAULT_START.isoformat())
    ap.add_argument("--to",   dest="end",   default=DEFAULT_END.isoformat())
    ap.add_argument("--capital", type=float, default=DEFAULT_CAP)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    run(date.fromisoformat(a.start), date.fromisoformat(a.end), a.capital,
        Path(a.out) if a.out else None)

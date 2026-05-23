"""n20_daily_large_only v3: sell-on-evening-3pp-threshold + next-day-open buy.

Variant of v2 with two rule changes:
  1. Sell rule: only rotate if (new_top1_30d_return) - (held_30d_return) >= 3pp.
     Else continue holding. Sell decision uses day-d close (~3:20pm proxy
     since data is EOD bars).
  2. Buy execution: next day OPEN (not same-day close).

Compare CAGR/DD vs v2 baseline (+140.78% CAGR, 26.92% NAV-DD).
"""
import sys, json, csv, argparse
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, "/app")
import pandas as pd
from sqlalchemy import text
from tools.shared.ohlcv_cache import _get_engine
from tools.shared.universes import nifty500_symbols


UNIV_SIZE = 20
LOOKBACK  = 30
ADV_WIN   = 20
SMA_LONG  = 200
N100_CSV  = "/app/src/data/symbols/nifty100.csv"
DEFAULT_START = date(2023, 5, 15)
DEFAULT_END   = date(2026, 5, 12)
DEFAULT_CAP   = 1_000_000.0
ROT_THRESH_PP = 0.03  # 3 percentage points momentum gap to trigger rotation


def load_n100():
    out = set()
    with open(N100_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("Series","").strip()=="EQ":
                out.add(r["Symbol"].strip())
    return out


def run(start: date, end: date, capital: float, threshold_pp: float = ROT_THRESH_PP,
        out_dir: Path | None = None):
    n100 = load_n100()
    print(f"NSE Nifty 100 filter: {len(n100)} stocks | threshold={threshold_pp*100:.1f}pp")

    eng = _get_engine()
    n500 = [f"NSE:{s}-EQ" for s, _ in nifty500_symbols()]

    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,open,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='fyers' "
            "ORDER BY symbol,date"
        ), c, params={"s": n500, "a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])
    df["adv_rs"] = df["close"].astype(float) * df["volume"].astype(float)
    cl = df.pivot(index="date", columns="symbol", values="close").ffill()
    op = df.pivot(index="date", columns="symbol", values="open").ffill()
    adv_rs = df.pivot(index="date", columns="symbol", values="adv_rs").fillna(0)
    adv20 = adv_rs.rolling(ADV_WIN).mean()
    sma200 = cl.rolling(SMA_LONG).mean()
    dates = cl.index

    trading = [d for d in dates if start <= d.date() <= end]
    cap = capital
    hold = None; qty = 0; entry_px = 0.0; entry_date = None
    trades = []
    nav_series = [capital]

    # Pending order from previous day's evening decision: executes at next open
    pending_buy: str | None = None
    pending_sell: bool = False

    for d in trading:
        di = dates.get_loc(d)
        if di < max(LOOKBACK, SMA_LONG): continue

        # 1) Morning open: execute pending orders from yesterday's evening
        if pending_sell and hold and qty > 0:
            ox = op[hold].iloc[di]
            if pd.notna(ox):
                ox = float(ox)
                proc = qty * ox
                cap += proc
                pnl = proc - qty * entry_px
                pct = (ox / entry_px - 1) * 100
                trades.append({
                    "entry_date": entry_date,
                    "exit_date":  d.date().isoformat(),
                    "sym":        hold.replace("NSE:", "").replace("-EQ", ""),
                    "qty":        qty,
                    "entry_px":   round(entry_px, 2),
                    "exit_px":    round(ox, 2),
                    "exit_type":  "open",
                    "pnl":        round(pnl, 0),
                    "ret_pct":    round(pct, 2),
                    "cap_after":  round(cap, 0),
                })
                hold = None; qty = 0
            pending_sell = False

        if pending_buy and not hold:
            bx = op[pending_buy].iloc[di]
            if pd.notna(bx):
                bx = float(bx)
                q = int(cap / bx)
                if q >= 1 and q * bx <= cap:
                    cap -= q * bx
                    qty = q; hold = pending_buy
                    entry_px = bx
                    entry_date = d.date().isoformat()
            pending_buy = None

        # NAV mark using current close (post-open exec)
        nav = cap + (qty*float(cl[hold].iloc[di]) if hold and pd.notna(cl[hold].iloc[di]) else 0)
        nav_series.append(nav)

        # 2) Evening 3:20pm-proxy decision (using day-d close data)
        pit_adv = adv20.iloc[di].dropna().sort_values(ascending=False)
        pit_univ = pit_adv.head(UNIV_SIZE).index.tolist()
        up = sma200.iloc[di] < cl.iloc[di]
        pit_univ = [s for s in pit_univ if bool(up.get(s, False))]
        pit_univ = [s for s in pit_univ if s.replace("NSE:","").replace("-EQ","") in n100]
        if not pit_univ: continue

        rets = cl.iloc[di].reindex(pit_univ) / cl.iloc[di - LOOKBACK].reindex(pit_univ) - 1
        rk = rets.dropna().sort_values(ascending=False)
        if rk.empty: continue
        top = rk.index[0]
        top_ret = float(rk.iloc[0])

        if not hold:
            # No position → schedule buy of current top-1 for next day open
            pending_buy = top
        elif top != hold:
            # Compute held's same-window momentum
            held_ret_series = cl.iloc[di].get(hold)
            held_lb = cl.iloc[di - LOOKBACK].get(hold)
            if pd.notna(held_ret_series) and pd.notna(held_lb) and float(held_lb) > 0:
                held_ret = float(held_ret_series) / float(held_lb) - 1
                gap = top_ret - held_ret
                if gap >= threshold_pp:
                    pending_sell = True
                    pending_buy = top

    final = cap
    open_pos = None
    if hold:
        last = float(cl[hold].iloc[-1])
        final = cap + qty * last
        open_pos = {
            "sym": hold.replace("NSE:", "").replace("-EQ", ""),
            "qty": qty, "entry_px": round(entry_px, 2),
            "entry_date": entry_date,
            "last_px": round(last, 2),
            "mtm_value": round(qty * last, 0),
            "unrealized_pnl": round(qty * (last - entry_px), 0),
        }

    wins   = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    yrs    = (end - start).days / 365.25
    cagr   = ((final / capital) ** (1 / yrs) - 1) * 100

    nav_arr = pd.Series(nav_series)
    roll_max = nav_arr.cummax()
    dd_series = (roll_max - nav_arr) / roll_max
    mdd_nav = float(dd_series.max()) * 100
    peak = capital; mdd_realized = 0.0
    for t in trades:
        peak = max(peak, t["cap_after"])
        dd = (peak - t["cap_after"]) / peak * 100
        mdd_realized = max(mdd_realized, dd)
    calmar = cagr / max(0.01, mdd_nav)

    print(f"\n## v3 (3pp threshold + next-day open) RESULTS")
    print(f"  Final NAV:    Rs.{final:,.0f}")
    print(f"  Total return: {(final/capital-1)*100:+.2f}%")
    print(f"  CAGR ({yrs:.2f}y): {cagr:+.2f}%")
    print(f"  Trades: {len(trades)} (wins={wins}, losses={losses}, WR={wins/max(1,wins+losses)*100:.1f}%)")
    print(f"  Max DD (NAV MTM): {mdd_nav:.2f}%  (rebal cap_after: {mdd_realized:.2f}%)")
    print(f"  Calmar: {calmar:.2f}")

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trade_ledger.json").write_text(json.dumps(trades, indent=2))
        summary = {
            "model": "n20_daily_large_only_v3",
            "rule": f"sell if top1-held momentum gap >= {threshold_pp*100:.1f}pp; buy next-day open",
            "threshold_pp": threshold_pp,
            "start": start.isoformat(), "end": end.isoformat(),
            "years": round(yrs, 3),
            "capital": capital, "final_nav": round(final, 0),
            "total_return_pct": round((final / capital - 1) * 100, 2),
            "cagr_pct": round(cagr, 2),
            "max_dd_pct": round(mdd_nav, 2),
            "max_dd_realized_pct": round(mdd_realized, 2),
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
    ap.add_argument("--threshold", type=float, default=ROT_THRESH_PP*100,
                    help="rotation threshold in percentage points (default 3.0)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    run(date.fromisoformat(a.start), date.fromisoformat(a.end), a.capital,
        threshold_pp=a.threshold/100.0,
        out_dir=Path(a.out) if a.out else None)

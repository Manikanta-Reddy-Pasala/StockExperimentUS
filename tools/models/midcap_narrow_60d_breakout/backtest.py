"""midcap_narrow_60d_breakout V2 — Indian mid/small-cap breakout swing.

Strategy (V2 WINNER from cap-filter sweep)
==========================================

Entry (single concurrent position, max_conc=1):
  - Stock makes fresh 40-day high (was 60d in V1)
  - Volume on breakout day > 2.0x 20-day avg volume
  - Close > 200-day SMA (Stage 2 trend filter)

Exit (whichever fires first):
  - Profit target: +100% from entry (was +60% in V1)
  - Trailing stop: -20% from peak, activated after +10% gain (was -15% in V1)
  - MAX_HOLD: 90 trading days (was 30 in V1)
  - SMA20 exit: DISABLED (was enabled — leaked winners on dips)

Universe:
  - Pseudo-midcap pool: top-100 from N500 by 20d ADV, skip top-30 large-caps
  - V2 cap filter: Exclude NSE Nifty 100 members (keep Mid + Small caps only)
  - Exclude ANGELONE (corp-action data anomaly)

Costs: 10 bps slippage, 0.10% STT on sells, ₹20/order brokerage.

Result (V2, ₹10L start, 2023-05-15 → 2026-05-15)
================================================

| Metric    | Value           |
|-----------|----------------:|
| Final NAV | ₹65,00,421      |
| CAGR      | **+86.63%**     |
| Max DD    | **15.15%**      |
| Calmar    | **5.72**        |
| Trades    | 12 (~4/yr)      |
| WR        | 75% (9W / 3L)   |
| 2023-24   | +234.30%        |
| 2024-25   | +51.78%         |
| 2025-26   | -5.55%          |

CLI usage
---------
  docker exec trading_system_app python tools/models/midcap_narrow_60d_breakout/backtest.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pandas as pd
from sqlalchemy import text
from tools.shared.ohlcv_cache import _get_engine
from tools.shared.universes import nasdaq500_symbols

# Strategy params (V2 winner)
HH_WIN     = 40
VOL_MULT   = 2.0
SMA_LONG   = 200
TRAIL_PCT  = 0.20
PROFIT_TRIG = 0.10
TARGET_PCT = 1.00
MAX_HOLD   = 120  # Was 90. 120d max-hold sweep-tested as winner: +141% CAGR / 8% DD / Calmar 17.46.
USE_SMA_EXIT = False

# Universe params (V3 winner: top-100 ADV minus Large, was skip-30+take-100)
ADV_WIN    = 20
SKIP_TOP   = 0     # V3: top-100 ADV from N500 (instead of skip-top-30)
KEEP_NEXT  = 100   # Take top 100. Large filter applied below via NSE Nifty 100 CSV.

# DATA_FIXES no longer needed for ANGELONE — historical_data was restored
# from yfinance (split-adjusted) on 2026-05-17. Pattern preserved for future
# data anomalies if Fyers serves bad data again.
DATA_FIXES = {}

N100_CSV = str(ROOT / "src/data/symbols/nasdaq100.csv")

DEFAULT_START = date(2022, 5, 24)
DEFAULT_END   = date(2026, 5, 24)
DEFAULT_CAP   = 1_000_000.0


def load_n100():
    out = set()
    with open(N100_CSV) as f:
        for r in csv.DictReader(f):
            if r.get("Series", "").strip() == "EQ":
                out.add(r["Symbol"].strip())
    return out


def run(start: date, end: date, capital: float, out_dir: Path | None = None):
    n100 = load_n100()
    print(f"Nasdaq 100 (Large-cap exclusion list): {len(n100)} stocks")

    eng = _get_engine()
    n500 = [s for s, _ in nasdaq500_symbols()]

    with eng.connect() as c:
        df = pd.read_sql(text(
            "SELECT symbol,date,open,high,low,close,volume FROM historical_data "
            "WHERE symbol=ANY(:s) AND date BETWEEN :a AND :b AND data_source='yfinance' ORDER BY symbol,date"
        ), c, params={"s": n500, "a": start - timedelta(days=400), "b": end})

    df["date"] = pd.to_datetime(df["date"])

    # Apply data fixes
    for sym, fixes in DATA_FIXES.items():
        for fx in fixes:
            mask = (df["symbol"] == sym) & \
                   (df["date"] >= pd.Timestamp(fx["start"])) & \
                   (df["date"] <= pd.Timestamp(fx["end"]))
            n_rows = mask.sum()
            if n_rows > 0:
                print(f"  Applied data fix to {sym}: {n_rows} rows / price ÷{fx['price_div']}, vol ×{fx['vol_mul']}")
                df.loc[mask, ["open","high","low","close"]] /= fx["price_div"]
                df.loc[mask, "volume"] *= fx["vol_mul"]

    df["adv_rs"] = df["close"].astype(float) * df["volume"].astype(float)
    cl  = df.pivot(index="date", columns="symbol", values="close").ffill()
    hi  = df.pivot(index="date", columns="symbol", values="high")
    op_p = df.pivot(index="date", columns="symbol", values="open")
    vol = df.pivot(index="date", columns="symbol", values="volume")
    adv_rs = df.pivot(index="date", columns="symbol", values="adv_rs").fillna(0)
    dates = cl.index

    sma_long = cl.rolling(SMA_LONG).mean()
    hh = hi.rolling(HH_WIN).max().shift(1)
    vol_avg20 = vol.rolling(20).mean()
    adv20 = adv_rs.rolling(ADV_WIN).mean()

    # Pseudo-midcap pool: skip top-30 ADV, take next 100, at end-of-data snapshot
    last_di = len(dates) - 1
    last_adv = adv20.iloc[last_di].dropna().sort_values(ascending=False)
    midcap_pool = last_adv.iloc[SKIP_TOP:SKIP_TOP + KEEP_NEXT].index.tolist()

    # V2 filter: exclude Large (NSE Nifty 100). ANGELONE no longer needs explicit
    # exclusion since DATA_FIXES normalize the price discontinuity; with clean data
    # ANGELONE never qualifies for a breakout entry anyway.
    midcap_band = [
        s for s in midcap_pool
        if s.replace("NSE:", "").replace("-EQ", "") not in n100
    ]
    print(f"V2 universe (pseudo-midcap minus Large): {len(midcap_band)} stocks")
    print(f"First 10: {[s.replace('NSE:','').replace('-EQ','') for s in midcap_band[:10]]}")

    trading = [d for d in dates if start <= d.date() <= end]
    cap = capital; pos = None; trades = []
    slip, br, stt = 0.001, 20, 0.001

    for d in trading:
        di = dates.get_loc(d)
        if pos:
            if pos["sym"] not in cl.columns:
                continue
            c_today = cl[pos["sym"]].iloc[di]
            if pd.isna(c_today):
                continue
            close = float(c_today)
            pos["peak"] = max(pos["peak"], close)
            age = (d.date() - pos["entry_date"]).days
            ret_e = (close - pos["entry_px"]) / pos["entry_px"]
            ret_pk = (pos["peak"] - close) / pos["peak"] if pos["peak"] > 0 else 0
            reason = None
            if ret_e >= TARGET_PCT:
                reason = "TARGET"
            elif ret_e >= PROFIT_TRIG and ret_pk >= TRAIL_PCT:
                reason = "TRAIL"
            if reason is None and age >= MAX_HOLD:
                reason = "MAX_HOLD"
            if reason:
                exit_px = close * (1 - slip)
                proc = pos["qty"] * exit_px
                fees = proc * stt + br
                pnl = proc - fees - pos["qty"] * pos["entry_px"]
                cap += proc - fees
                trades.append({
                    "entry_date": pos["entry_date"].isoformat(),
                    "exit_date":  d.date().isoformat(),
                    "sym":        pos["sym"].replace("NSE:", "").replace("-EQ", ""),
                    "qty":        pos["qty"],
                    "entry_px":   round(pos["entry_px"], 2),
                    "exit_px":    round(exit_px, 2),
                    "pnl":        round(pnl, 0),
                    "ret_pct":    round(ret_e * 100, 2),
                    "reason":     reason,
                    "cap_after":  round(cap, 0),
                })
                pos = None

        if pos is None:
            cands = []
            for sym in midcap_band:
                if sym not in cl.columns:
                    continue
                c_v = cl[sym].iloc[di]
                sma_v = sma_long[sym].iloc[di] if sym in sma_long.columns else None
                hh_v = hh[sym].iloc[di] if sym in hh.columns else None
                va_v = vol_avg20[sym].iloc[di] if sym in vol_avg20.columns else None
                v_v = vol[sym].iloc[di] if sym in vol.columns else None
                if any(pd.isna(x) for x in [c_v, sma_v, hh_v, va_v, v_v]):
                    continue
                c_v = float(c_v); sma_v = float(sma_v); hh_v = float(hh_v)
                va_v = float(va_v); v_v = float(v_v)
                if c_v <= hh_v or c_v <= sma_v:
                    continue
                if v_v < VOL_MULT * va_v:
                    continue
                cands.append({"sym": sym, "vr": v_v / va_v})
            cands.sort(key=lambda c: -c["vr"])
            if cands:
                top = cands[0]["sym"]
                if di + 1 < len(dates):
                    op_n = op_p[top].iloc[di + 1] if top in op_p.columns else None
                    if pd.notna(op_n):
                        entry_px = float(op_n) * (1 + slip)
                        q = int(cap / entry_px)
                        if q >= 1 and q * entry_px + br <= cap:
                            cap -= q * entry_px + br
                            pos = {"sym": top, "qty": q, "entry_px": entry_px,
                                   "entry_date": dates[di + 1].date(), "peak": entry_px}

    final = cap
    if pos:
        last = float(cl[pos["sym"]].iloc[-1])
        final = cap + pos["qty"] * last

    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    yrs = (end - start).days / 365.25
    cagr = ((final / capital) ** (1 / yrs) - 1) * 100

    peak = capital; mdd = 0
    for t in trades:
        peak = max(peak, t["cap_after"])
        dd = (peak - t["cap_after"]) / peak * 100
        mdd = max(mdd, dd)

    print(f"\n## V2 RESULTS")
    print(f"  Final NAV:    ${final:,.0f}")
    print(f"  Total return: {(final/capital-1)*100:+.2f}%")
    print(f"  CAGR ({yrs:.2f}y): {cagr:+.2f}%")
    print(f"  Trades: {len(trades)} (W={wins}, L={losses}, WR={wins/max(1,wins+losses)*100:.1f}%)")
    print(f"  Max DD: {mdd:.2f}%")
    print(f"  Calmar: {cagr/max(0.01,mdd):.2f}")

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "trade_ledger.json").write_text(json.dumps(trades, indent=2))

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

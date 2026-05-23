"""Universal NSE FO bhavcopy ingester — NIFTY, BANKNIFTY, FINNIFTY, stocks.

Extends prefetch_bhav.py to support any underlying via --underlying flag.

Usage:
    python tools/shared/prefetch_bhav.py \
        --from 2023-05-15 --to 2026-05-15 \
        --underlying BANKNIFTY --instrument OPTIDX
    python tools/shared/prefetch_bhav.py \
        --from 2023-05-15 --to 2026-05-15 \
        --underlying RELIANCE,TCS,INFY --instrument OPTSTK

Instruments: OPTIDX (index options), OPTSTK (stock options)
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import _get_engine  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Accept": "*/*"}
OLD_URL = "https://archives.nseindia.com/content/historical/DERIVATIVES/{yyyy}/{mon3u}/fo{dd}{mon3u}{yyyy}bhav.csv.zip"
NEW_URL = "https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
OLD_CUTOFF = date(2024, 7, 7)

MON3U = {1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
         7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"}
MONTH_CODE_WEEKLY = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
                     7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D"}


def fetch_zip(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers=UA)
    try:
        return urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_old(txt: str, underlying_set: set, instrument_set: set) -> List[dict]:
    rows = list(csv.reader(io.StringIO(txt)))
    out = []
    for r in rows[1:]:
        if len(r) < 15:
            continue
        if r[0].strip() not in instrument_set:
            continue
        if r[1].strip() not in underlying_set:
            continue
        try:
            exp = datetime.strptime(r[2].strip(), "%d-%b-%Y").date()
            td = datetime.strptime(r[14].strip(), "%d-%b-%Y").date()
            strike = int(float(r[3]))
            ot = r[4].strip()
            if ot not in ("CE", "PE"):
                continue
            # r[11] = VAL_INLAKH (total turnover in rupees-lakhs)
            try:
                turnover_lakh = float(r[11]) if r[11].strip() else None
            except (ValueError, IndexError):
                turnover_lakh = None
            out.append({
                "underlying": r[1].strip(), "expiry": exp, "strike": strike,
                "opt_type": ot, "trade_date": td,
                "open": float(r[5]), "high": float(r[6]),
                "low": float(r[7]), "close": float(r[8]),
                "volume": int(float(r[10])), "oi": int(float(r[12])),
                # Old bhavcopy does NOT provide num_trades — leave NULL.
                "num_trades": None,
                "turnover_lakh": turnover_lakh,
            })
        except (ValueError, IndexError):
            continue
    return out


def parse_new(txt: str, underlying_set: set, instrument_set: set) -> List[dict]:
    """New UDiFF: FinInstrmTp IDF=Future Index, IDO=Option Index,
                  STF=Future Stock, STO=Option Stock."""
    rows = list(csv.reader(io.StringIO(txt)))
    if not rows:
        return []
    header = rows[0]
    def idx(n):
        try: return header.index(n)
        except ValueError: return -1
    iSym = idx("TckrSymb"); iTp = idx("FinInstrmTp"); iXpry = idx("XpryDt")
    iK = idx("StrkPric"); iOT = idx("OptnTp"); iO = idx("OpnPric")
    iH = idx("HghPric"); iL = idx("LwPric"); iC = idx("ClsPric")
    iV = idx("TtlTradgVol"); iOI = idx("OpnIntrst"); iTD = idx("TradDt")
    iNT = idx("TtlNbOfTxsExctd")   # number of distinct trades
    iTO = idx("TtlTrfVal")         # total traded value in lakhs of rupees

    # Map old OPTIDX -> new IDO, OPTSTK -> STO
    new_instr_set = set()
    for inst in instrument_set:
        if inst == "OPTIDX":
            new_instr_set.add("IDO")
        elif inst == "OPTSTK":
            new_instr_set.add("STO")
        else:
            new_instr_set.add(inst)

    out = []
    for r in rows[1:]:
        try:
            if r[iSym] not in underlying_set:
                continue
            if r[iTp] not in new_instr_set:
                continue
            ot = r[iOT]
            if ot not in ("CE", "PE"):
                continue
            exp = datetime.strptime(r[iXpry], "%Y-%m-%d").date()
            td = datetime.strptime(r[iTD], "%Y-%m-%d").date()
            strike = int(float(r[iK]))
            num_trades = None
            if iNT >= 0 and r[iNT]:
                try: num_trades = int(float(r[iNT]))
                except ValueError: pass
            turnover_lakh = None
            if iTO >= 0 and r[iTO]:
                try: turnover_lakh = float(r[iTO])
                except ValueError: pass
            out.append({
                "underlying": r[iSym], "expiry": exp, "strike": strike,
                "opt_type": ot, "trade_date": td,
                "open": float(r[iO]) if r[iO] else 0.0,
                "high": float(r[iH]) if r[iH] else 0.0,
                "low":  float(r[iL]) if r[iL] else 0.0,
                "close": float(r[iC]) if r[iC] else 0.0,
                "volume": int(float(r[iV])) if r[iV] else 0,
                "oi":     int(float(r[iOI])) if r[iOI] else 0,
                "num_trades": num_trades,
                "turnover_lakh": turnover_lakh,
            })
        except (ValueError, IndexError):
            continue
    return out


def is_monthly(exp: date) -> bool:
    import calendar
    last = calendar.monthrange(exp.year, exp.month)[1]
    return (last - exp.day) <= 6 and exp.weekday() in (1, 2, 3)


def build_symbol(underlying: str, exp: date, strike: int, opt_type: str, mn: bool) -> str:
    yy = exp.strftime("%y")
    if mn:
        return f"NSE:{underlying}{yy}{MON3U[exp.month]}{strike}{opt_type}"
    m = MONTH_CODE_WEEKLY[exp.month]
    return f"NSE:{underlying}{yy}{m}{exp.day:02d}{strike}{opt_type}"


def fetch_day(d: date) -> Optional[str]:
    if d <= OLD_CUTOFF:
        url = OLD_URL.format(yyyy=d.year, mon3u=MON3U[d.month], dd=f"{d.day:02d}")
    else:
        url = NEW_URL.format(yyyymmdd=d.strftime("%Y%m%d"))
    b = fetch_zip(url)
    if b is None:
        return None
    z = zipfile.ZipFile(io.BytesIO(b))
    return z.read(z.namelist()[0]).decode("utf-8", errors="ignore")


def bulk_insert(eng, rows: List[dict]) -> int:
    if not rows:
        return 0
    opt_payload = []
    uni_payload = []
    for r in rows:
        mn = is_monthly(r["expiry"])
        sym = build_symbol(r["underlying"], r["expiry"], r["strike"],
                           r["opt_type"], mn)
        ts = int(datetime(r["trade_date"].year, r["trade_date"].month,
                          r["trade_date"].day, 15, 30).timestamp())
        ct = datetime(r["trade_date"].year, r["trade_date"].month,
                      r["trade_date"].day, 15, 30)
        opt_payload.append((
            sym, r["underlying"], r["expiry"], r["strike"], r["opt_type"],
            "D", ts, ct, r["open"], r["high"], r["low"], r["close"],
            r["volume"], r["oi"],
            r.get("num_trades"), r.get("turnover_lakh"),
        ))
        uni_payload.append((
            sym, r["underlying"], r["expiry"],
            "monthly" if mn else "weekly", r["strike"], r["opt_type"],
        ))
    raw = eng.raw_connection()
    try:
        cur = raw.cursor()
        cur.executemany(
            "INSERT INTO historical_options "
            "(symbol, underlying, expiry, strike, opt_type, interval, "
            " timestamp, candle_time, open, high, low, close, volume, oi, "
            " num_trades, turnover_lakh) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (symbol, interval, timestamp) DO UPDATE SET "
            "  num_trades = EXCLUDED.num_trades, "
            "  turnover_lakh = EXCLUDED.turnover_lakh",
            opt_payload,
        )
        inserted = cur.rowcount or len(opt_payload)
        cur.executemany(
            "INSERT INTO option_universe "
            "(symbol, underlying, expiry, expiry_kind, strike, opt_type, fetched_d) "
            "VALUES (%s,%s,%s,%s,%s,%s,TRUE) "
            "ON CONFLICT (symbol) DO UPDATE SET fetched_d = TRUE",
            uni_payload,
        )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    return inserted


def daterange(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--underlying", required=True,
                    help="Comma-separated. e.g. BANKNIFTY  or  RELIANCE,TCS")
    ap.add_argument("--instrument", default="OPTIDX",
                    help="OPTIDX (index opt) or OPTSTK (stock opt)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    underlying_set = set(u.strip() for u in args.underlying.split(","))
    instrument_set = set(args.instrument.split(","))
    start = datetime.strptime(args.frm, "%Y-%m-%d").date()
    end = datetime.strptime(args.to, "%Y-%m-%d").date()
    days = list(daterange(start, end))
    if args.limit:
        days = days[: args.limit]
    print(f"Days={len(days)} underlying={underlying_set} instrument={instrument_set}", flush=True)

    eng = _get_engine()
    t0 = time.time()
    total_bars = 0
    misses = 0
    for i, d in enumerate(days, 1):
        try:
            txt = fetch_day(d)
            if txt is None:
                misses += 1
                continue
            if d <= OLD_CUTOFF:
                rows = parse_old(txt, underlying_set, instrument_set)
            else:
                rows = parse_new(txt, underlying_set, instrument_set)
            if not rows:
                misses += 1
                continue
            nb = bulk_insert(eng, rows)
            total_bars += nb
            if i % 25 == 0:
                rate = i / max(time.time() - t0, 1e-6)
                print(f"  [{i}/{len(days)}] {d} rows+={len(rows)} "
                      f"total_bars={total_bars} miss={misses} {rate:.1f}d/s",
                      flush=True)
        except Exception as e:
            misses += 1
            print(f"  [{i}/{len(days)}] {d} ERR {e}", flush=True)
    print(f"DONE days={len(days)} bars={total_bars} miss={misses} "
          f"elapsed={(time.time()-t0)/60:.1f}min", flush=True)


if __name__ == "__main__":
    main()

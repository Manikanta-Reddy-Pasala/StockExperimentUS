"""Indian equity broker charge calculator.

Computes per-trade charges (brokerage + STT + exchange + SEBI + stamp + GST + DP)
using SEBI-published rates. Charges differ between BUY (no STT, has stamp duty)
and SELL (has STT + DP charges, no stamp).

Currently models CNC (delivery) only. INTRADAY rates differ (lower STT 0.025%,
no DP charges, no stamp duty) — if/when an INTRADAY model is wired, branch on
product.

Reference rates (Indian equity, mid-2026, calibrated against user's
actual Fyers ledger 14/18/19 May 2026):
  - Brokerage (Fyers):
      CNC delivery:   Rs.20 flat per executed order  (observed: HFCL ~Rs.40 = 2 fills × Rs.20, ADANI Rs.20)
      INTRADAY/MIS:   min(Rs.20, 0.03% × turnover) per executed order
  - STT (Securities Transaction Tax): 0.10% on sell-side turnover only
  - NSE/BSE Exchange Transaction Charges: ~0.00345% turnover (NSE)
  - SEBI Charges: 0.0001% turnover (Rs.10 per crore)
  - Stamp Duty: 0.015% on buy-side turnover only (capped at Rs.1500)
  - GST: 18% on (brokerage + exchange + SEBI)
  - DP Charges (CDSL): Rs.13.5 + 18% GST = Rs.15.93 per sell scrip per day

These rates can change if SEBI/exchanges revise schedules. Update here and
all downstream audit + UI updates automatically.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict


# Rate constants — kept as Decimal for precision
BROKERAGE_FLAT = Decimal("20.00")        # per order
STT_SELL_CNC_PCT = Decimal("0.0010")     # 0.10% delivery sell-side
STT_SELL_MIS_PCT = Decimal("0.00025")    # 0.025% intraday sell-side
EXCHANGE_TXN_PCT = Decimal("0.0000345")  # 0.00345% both sides
SEBI_PCT = Decimal("0.000001")           # 0.0001% both sides
STAMP_BUY_CNC_PCT = Decimal("0.00015")   # 0.015% delivery buy-side
STAMP_BUY_MIS_PCT = Decimal("0.00003")   # 0.003% intraday buy-side
STAMP_BUY_CAP = Decimal("1500.00")
GST_PCT = Decimal("0.18")                # 18%
DP_CHARGES_INCL_GST = Decimal("15.93")   # CDSL Rs.13.5 + 18% GST (CNC sell only)


def compute_charges(side: str, qty: int, price: float,
                    product: str = "CNC") -> Dict[str, float]:
    """Return all charge components + total for a single equity trade.

    side: "BUY" or "SELL"
    qty: integer shares
    price: average fill price per share
    product: "CNC" (delivery) — only mode currently supported

    Returns dict with all sub-components (rupees) + 'total'.
    All numeric values cast to float for JSON serialisation.
    """
    if not qty or not price or qty < 0 or price <= 0:
        return _zero_breakdown()

    prod_u = product.upper()
    is_intraday = prod_u in ("INTRADAY", "MIS")
    is_cnc = prod_u in ("CNC", "DELIVERY", "MARGIN")
    if not (is_intraday or is_cnc):
        return _zero_breakdown(note=f"unsupported product: {product}")

    side_u = (side or "").upper()
    turnover = Decimal(str(qty)) * Decimal(str(price))

    # Brokerage — Fyers schedule (calibrated mid-2026):
    #   CNC delivery: Rs.20 flat per executed order
    #     (observed: HFCL Rs.40.90 = 2 fills × Rs.20 + paise rounding;
    #      ADANI single fill Rs.20.00 exact)
    #   INTRADAY/MIS: min(Rs.20, 0.03% × turnover) per executed order
    #     (observed: ADANI Rs.4.47-4.49 per 14.9K turnover fill ≈ 0.03%)
    if is_cnc:
        brokerage = BROKERAGE_FLAT  # Rs.20 flat
    else:
        brokerage = min(BROKERAGE_FLAT, turnover * Decimal("0.0003"))
        brokerage = max(brokerage, Decimal("0"))

    # STT: SELL only. CNC=0.10%, INTRADAY=0.025%
    if side_u == "SELL":
        stt_rate = STT_SELL_MIS_PCT if is_intraday else STT_SELL_CNC_PCT
        stt = turnover * stt_rate
    else:
        stt = Decimal("0")

    # Exchange transaction charges (both sides, same rate for CNC/MIS)
    exchange = turnover * EXCHANGE_TXN_PCT

    # SEBI charges (both sides)
    sebi = turnover * SEBI_PCT

    # Stamp duty: BUY only. CNC=0.015%, INTRADAY=0.003%
    if side_u == "BUY":
        stamp_rate = STAMP_BUY_MIS_PCT if is_intraday else STAMP_BUY_CNC_PCT
        stamp = min(turnover * stamp_rate, STAMP_BUY_CAP)
    else:
        stamp = Decimal("0")

    # GST on brokerage + exchange + SEBI
    gst_base = brokerage + exchange + sebi
    gst = gst_base * GST_PCT

    # DP charges: CNC sell only (no demat involvement for intraday)
    dp = DP_CHARGES_INCL_GST if (side_u == "SELL" and is_cnc) else Decimal("0")

    total = brokerage + stt + exchange + sebi + stamp + gst + dp

    return {
        "brokerage": _r(brokerage),
        "stt": _r(stt),
        "exchange": _r(exchange),
        "sebi": _r(sebi),
        "stamp": _r(stamp),
        "gst": _r(gst),
        "dp": _r(dp),
        "total": _r(total),
        "turnover": _r(turnover),
        "rate_total_pct": _r((total / turnover) * 100) if turnover > 0 else 0.0,
        "side": side_u,
        "product": product.upper(),
    }


def _r(d: Decimal) -> float:
    return float(round(d, 4))


def _zero_breakdown(note: str = "") -> Dict[str, float]:
    out = {k: 0.0 for k in ["brokerage", "stt", "exchange", "sebi",
                            "stamp", "gst", "dp", "total", "turnover",
                            "rate_total_pct"]}
    out["side"] = ""
    out["product"] = ""
    if note:
        out["note"] = note
    return out


if __name__ == "__main__":
    # Quick smoke test — mirrors today's ADANIPOWER fill
    import json
    print("BUY ADANIPOWER x68 @ 220.31:")
    print(json.dumps(compute_charges("BUY", 68, 220.31), indent=2))
    print("\nSELL ADANIPOWER x68 @ 220.31 (hypothetical):")
    print(json.dumps(compute_charges("SELL", 68, 220.31), indent=2))

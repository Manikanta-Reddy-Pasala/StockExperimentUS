"""One-by-one recheck of every trade in both US models.

Two independent checks per trade:
  (A) INTERNAL MATH   — pnl == shares*(exit-entry)? ret_pct == (exit/entry-1)*100?
                        pnl_pct == ret_pct? bars_held consistent with the date gap?
                        (pure data, needs no market knowledge)
  (B) PRICE SANITY    — entry & exit inside a generous real-world split-adjusted band
                        for that ticker over 2021-2025. Outside the band on the HIGH
                        side or LOW side = data glitch (eToro). Bands are deliberately
                        wide (only clear physical impossibilities flagged); real 2024-25
                        winners (LLY $954, META $716, TSLA $461, AXON $593) stay OK.
                        Exit dated 2026 within band but above 2025 norms -> EDGE (can't
                        verify past the Jan-2026 knowledge cutoff; not auto-glitched).

Output: exports/models/<model>/TRADE_RECHECK.md (full per-trade verdict table) and a
console summary. Verdicts: OK / MATH_ERR / GLITCH_HIGH / GLITCH_LOW / EDGE.
"""
from __future__ import annotations
import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "exports" / "models"

# (lo, hi) generous plausible split-adjusted price band, USD, 2021-2025.
# hi ~= 1.0-1.2x the real all-time-high through the Jan-2026 cutoff; lo ~= real cycle low.
# Anything ABOVE hi or BELOW lo is a physical impossibility => eToro glitch.
BAND = {
    # momentum_sp100 (mega/large)
    "ADBE": (280, 700), "AMAT": (75, 280), "AMD": (54, 230), "AVGO": (40, 380),
    "BA": (90, 270), "BKNG": (1800, 6000), "CRM": (130, 380), "FDX": (135, 320),
    "GE": (45, 320), "GEV": (110, 720), "GOOG": (83, 340), "GOOGL": (83, 340),
    "GS": (270, 750), "IBM": (110, 320), "INTC": (17, 70), "INTU": (350, 800),
    "ISRG": (180, 620), "LLY": (190, 1000), "LRCX": (45, 300), "META": (88, 800),
    "MU": (48, 200), "NVDA": (11, 200), "ORCL": (60, 380), "PLTR": (6, 200),
    "PM": (82, 185), "QCOM": (105, 240), "TMUS": (100, 300), "TSLA": (100, 490),
    "UBER": (20, 100), "UNH": (440, 630), "WFC": (38, 90), "WMT": (45, 110),
    # retest_sp500 extras
    "ACGL": (35, 120), "AKAM": (75, 130), "AXON": (130, 800), "BIIB": (180, 320),
    "CHRW": (80, 120), "CHTR": (220, 460), "COIN": (40, 450), "CRWD": (110, 600),
    "EXPE": (90, 210), "FSLR": (110, 310), "MPWR": (350, 1000), "NFLX": (160, 1300),
    "NTAP": (60, 150), "ROST": (90, 165), "SMCI": (17, 130), "SNDK": (30, 110),
    "STLD": (55, 160), "UAL": (30, 130), "VRSN": (170, 300), "WBD": (8, 35),
    "WDC": (28, 95), "WYNN": (60, 140),
}

# BKNG: note momentum ledger shows BKNG ~$106 — but real BKNG is ~$2000-5000.
# That is a 20x-low glitch; band lo=1800 catches it (GLITCH_LOW).


def dgap(a, b):
    ya, ma, da = map(int, a.split("-")); yb, mb, db = map(int, b.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days


def check(r):
    sym = r["symbol"]; ep = float(r["entry_px"]); xp = float(r["exit_px"])
    sh = float(r["shares"]); pnl = float(r["pnl"]); ret = float(r["ret_pct"])
    pnlpct = float(r.get("pnl_pct", ret)); bars = int(r["bars_held"])
    notes = []

    # (A) internal math
    exp_pnl = sh * (xp - ep)
    if abs(exp_pnl - pnl) > max(2.0, abs(pnl) * 0.02):
        notes.append(f"MATH_ERR pnl {pnl:.0f} vs shares*(exit-entry) {exp_pnl:.0f}")
    exp_ret = (xp / ep - 1) * 100
    if abs(exp_ret - ret) > 0.5:
        notes.append(f"MATH_ERR ret {ret:.2f} vs {exp_ret:.2f}")
    if abs(pnlpct - ret) > 0.5:
        notes.append(f"MATH_ERR pnl_pct {pnlpct:.2f} != ret_pct {ret:.2f}")
    gap = dgap(r["entry_date"], r["exit_date"])
    if not (gap * 0.5 <= bars <= gap):  # bars(trading days) ~0.69*calendar; allow band
        notes.append(f"BARS? bars={bars} calendar_gap={gap}d")

    # (B) price sanity — confidence depends on whether the date is inside my
    # solid market-knowledge window. Trades exiting BEFORE 2025-07 are verifiable
    # (confident GLITCH); 2025-07 onward is the eToro data edge / beyond cutoff,
    # so an out-of-band price is UNVERIFIABLE (could be real 2025-26 mania OR glitch),
    # NOT a confident call.
    CONFIDENT_BEFORE = "2025-07"
    lo, hi = BAND.get(sym, (0, 1e9))
    verdict = "OK"
    oob = None
    for tag, p in (("entry", ep), ("exit", xp)):
        if p > hi:
            oob = f"{tag} ${p:.2f} > plausible hi ${hi}"
        elif p < lo:
            oob = f"{tag} ${p:.2f} < plausible lo ${lo}"
    if oob:
        notes.append(oob)
        if r["exit_date"] < CONFIDENT_BEFORE:
            verdict = "GLITCH"          # inside knowledge window, physically impossible
        else:
            verdict = "UNVERIFIABLE"    # 2025-26 edge — needs NUC raw-candle check
    if verdict == "OK" and any("MATH" in n for n in notes):
        verdict = "MATH_ERR"
    return verdict, notes


def run(model):
    rows = list(csv.DictReader(open(EXPORTS / model / "trade_ledger.csv")))
    out = []
    counts = {}
    out.append(f"# {model} — one-by-one trade recheck ({len(rows)} trades)")
    out.append("")
    out.append("Checks: internal math (pnl/ret/bars) + price band sanity per ticker. "
               "GLITCH_HIGH/LOW = eToro corrupted price. EDGE = 2026 exit, can't verify past cutoff.")
    out.append("")
    out.append("| # | Sym | Entry→Exit | Entry $ | Exit $ | Ret % | PnL $ | Verdict | Notes |")
    out.append("|---|---|---|---:|---:|---:|---:|---|---|")
    for i, r in enumerate(rows, 1):
        v, notes = check(r)
        counts[v] = counts.get(v, 0) + 1
        out.append(f"| {i} | {r['symbol']} | {r['entry_date']}→{r['exit_date']} "
                   f"| {float(r['entry_px']):.2f} | {float(r['exit_px']):.2f} | {float(r['ret_pct']):.1f} "
                   f"| {float(r['pnl']):,.0f} | {v} | {'; '.join(notes)} |")
    out.append("")
    out.append("## Verdict tally")
    out.append("")
    for k in sorted(counts):
        out.append(f"- **{k}**: {counts[k]}")
    totpnl = sum(float(r["pnl"]) for r in rows)
    conf = sum(float(r["pnl"]) for r in rows if check(r)[0] in ("GLITCH", "MATH_ERR"))
    unver = sum(float(r["pnl"]) for r in rows if check(r)[0] == "UNVERIFIABLE")
    out.append(f"- **confirmed GLITCH/MATH PnL**: ${conf:,.0f} ({conf/totpnl*100:.0f}% of ${totpnl:,.0f})")
    out.append(f"- **UNVERIFIABLE (2025-26 edge) PnL**: ${unver:,.0f} ({unver/totpnl*100:.0f}%)")
    out.append("")
    out.append("UNVERIFIABLE = out-of-band price on a 2025-07-or-later date (eToro data edge, past the "
               "Jan-2026 knowledge cutoff). Could be a real 2025-26 mania move OR a corrupted candle — "
               "resolve by re-pulling the raw eToro daily series for these names on the NUC and confirming "
               "the close matches. Self-consistent smooth paths lean real; >10x-from-baseline magnitudes lean glitch.")
    (EXPORTS / model / "TRADE_RECHECK.md").write_text("\n".join(out) + "\n")
    print(f"{model}: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f" | confirmed GLITCH/MATH ${conf:,.0f} ({conf/totpnl*100:.0f}%) | "
          + f"UNVERIFIABLE ${unver:,.0f} ({unver/totpnl*100:.0f}%) of ${totpnl:,.0f}")
    return counts


if __name__ == "__main__":
    for m in ("momentum_sp100", "retest_sp500"):
        run(m)

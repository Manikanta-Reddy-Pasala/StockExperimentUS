"""Regenerate exports/models/*/SUMMARY.md + TRADE_LEDGER.md + top-level SUMMARY.md
from each model's model_info.json / trade_ledger.csv / equity_curve.csv, so the
human-readable docs always match the real ledger (no stale hand-edited numbers).

Mirrors the India repo's exports format (StockExperiment/exports/models/*/{SUMMARY,TRADE_LEDGER}.md).

It ALSO runs a data-integrity audit on every trade and writes DATA_AUDIT.md, because the
eToro candle feed has corrupted price levels at the 2025-2026 data edge that inflate the
headline CAGR. Pure formatting + audit, no backtest.

Run: python3 tools/analysis/refresh_export_docs.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "exports" / "models"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import recheck_trades as RC  # per-trade calibrated verdicts (single source of truth)

# Per-model descriptors (title, universe, one-line strategy, status).
DESC = {
    "momentum_sp100": {
        "title": "S&P 100 Momentum (n40 top-3 blend)", "status": "LIVE (observer)",
        "universe": "Top-40 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate",
        "strategy": "Weekly rotation, top-3 by 30d return, blend weights .8/.1/.1 (70/30 conviction), single sleeve. QQQ-200d regime gate (risk-off → cash).",
    },
    "retest_sp500": {
        "title": "S&P 500 Retest Momentum (top-2 blend)", "status": "LIVE (observer)",
        "universe": "S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate",
        "strategy": "Monthly retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate.",
    },
}

# ---------------------------------------------------------------------------
# DATA-INTEGRITY AUDIT  (delegates per-trade verdicts to recheck_trades.py)
# ---------------------------------------------------------------------------
# Two buckets, honestly separated by confidence:
#   glitch (CONFIRMED)   — price impossible AND on a date inside the solid market-
#                          knowledge window (e.g. NFLX Dec-2022 $29, BKNG $107).
#   unver  (UNVERIFIABLE) — out-of-band price on a 2025-07+ date (eToro data edge,
#                          past the Jan-2026 cutoff). Could be a real 2025-26 mania
#                          move OR a corrupted candle — needs a NUC raw-candle check.
def audit_trades(rows):
    glitch, unver = [], []
    for r in rows:
        v = RC.check(r)[0]
        if v in ("GLITCH", "MATH_ERR"):
            glitch.append(r)
        elif v == "UNVERIFIABLE":
            unver.append(r)
    return glitch, unver


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------
def load_equity(path):
    pts = []
    with open(path) as f:
        for row in csv.DictReader(f):
            pts.append((row["date"], float(row["equity"])))
    return pts


def max_drawdown(pts):
    peak, mdd = -1e18, 0.0
    for _, e in pts:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak)
    return mdd * 100


def year_breakdown(pts):
    """Per-calendar-year return % and intra-year max DD %, from the daily curve."""
    by_year = {}
    for d, e in pts:
        by_year.setdefault(d[:4], []).append((d, e))
    out = []
    for yr in sorted(by_year):
        seq = by_year[yr]
        ret = (seq[-1][1] / seq[0][1] - 1) * 100
        out.append((yr, ret, max_drawdown(seq)))
    return out


def fmt_usd(x):
    return f"${x:,.0f}"


# ---------------------------------------------------------------------------
# DOC WRITERS
# ---------------------------------------------------------------------------
def _pnl(rows):
    return sum(float(r["pnl"]) for r in rows)


def write_summary(model, info, eq, glitch, unver):
    d = DESC[model]
    m = info["metrics"]
    final = eq[-1][1]
    start = eq[0][1]
    tot_ret = (final / start - 1) * 100
    mdd = max_drawdown(eq)
    yb = year_breakdown(eq)

    tot_pnl = _pnl(_all_rows[model])
    g_pnl, u_pnl = _pnl(glitch), _pnl(unver)
    g_share = (g_pnl / tot_pnl * 100) if tot_pnl else 0.0
    u_share = (u_pnl / tot_pnl * 100) if tot_pnl else 0.0

    L = []
    L.append(f"# {d['title']} (`{model}`)")
    L.append("")
    L.append(f"**Status:** {d['status']}  ")
    L.append(d["strategy"])
    L.append("")
    L.append(f"**Universe:** {d['universe']}")
    L.append("")
    L.append(
        f"Backtest window: **{info['window'].replace('..',' → ')}** "
        f"(~{m['yrs']:.2f} years; ${start:,.0f} start). "
        f"OBSERVER (cash, no leverage), net of $1/txn, next-close fills, "
        f"PIT survivorship-corrected, **eToro** daily data. {info['regime']} regime gate."
    )
    L.append("")

    if unver or glitch:
        L.append("## ⚠️ DATA-INTEGRITY NOTE — verify before trusting headline")
        L.append("")
        if unver:
            names = ", ".join(sorted({r["symbol"] for r in unver}))
            L.append(
                f"**{len(unver)} trade(s) ({fmt_usd(u_pnl)} = {u_share:.0f}% of PnL) sit on UNVERIFIABLE "
                f"2025-26 edge prices** ({names}) — out-of-band vs pre-2026 norms, on dates past the "
                "Jan-2026 knowledge cutoff. Could be real 2025-26 AI/memory mania OR corrupted eToro "
                "candles; the price paths are smooth & self-consistent (lean real) but magnitudes are "
                "extreme. **Re-pull the raw eToro daily series for these names on the NUC to confirm.** "
                "Until then treat CAGR / Final NAV as UNVERIFIED. See `DATA_AUDIT.md` / `TRADE_RECHECK.md`."
            )
            L.append("")
        if glitch:
            L.append(
                f"**{len(glitch)} CONFIRMED data error(s)** ({fmt_usd(g_pnl)} = {g_share:.0f}% of PnL): "
                + ", ".join("{} {} ${:,.0f}".format(r["symbol"], r["exit_date"], float(r["exit_px"]))
                            for r in glitch)
                + " — price impossible on a date inside the verifiable window."
            )
            L.append("")

    L.append("## Results (as-is, net of $1/txn) — see audit before trusting")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Final NAV (${start:,.0f} start) | {fmt_usd(final)} |")
    L.append(f"| Total return | {tot_ret:+.1f}% |")
    L.append(f"| CAGR (annualized) | {m['cagr']:+.1f}% |")
    L.append(f"| Max drawdown | {mdd:.1f}% |")
    L.append(f"| Calmar | {m['calmar']:.2f} |")
    L.append(f"| Trades | {m['trades']} · {m.get('wr','—')}% win |")
    L.append(f"| PnL on UNVERIFIABLE edge prices | {fmt_usd(u_pnl)} ({u_share:.0f}% of total) |")
    L.append(f"| PnL on CONFIRMED data errors | {fmt_usd(g_pnl)} ({g_share:.0f}% of total) |")
    L.append("")

    L.append("## Year-by-year breakdown")
    L.append("")
    L.append("| Year | Return % | Intra-yr DD % |")
    L.append("|---|---:|---:|")
    for yr, ret, dd in yb:
        L.append(f"| {yr} | {ret:+.1f}% | {dd:.1f}% |")
    L.append("")

    L.append("## Cap mix")
    L.append("")
    cm = info.get("cap_mix", {})
    L.append(", ".join(f"{k}={v}" for k, v in cm.items()) or "—")
    L.append("")

    L.append("---")
    L.append("*Auto-generated from model_info.json + trade_ledger.csv by "
             "tools/analysis/refresh_export_docs.py — do not hand-edit.*")
    (EXPORTS / model / "SUMMARY.md").write_text("\n".join(L) + "\n")


def write_ledger(model, info, rows, glitch, unver):
    g_ids = {id(r) for r in glitch}
    u_ids = {id(r) for r in unver}
    L = []
    L.append(f"# {model} — trade ledger ({info['window'].replace('..',' → ')})")
    L.append("")
    L.append("Flag: 🛑 = CONFIRMED data error (price impossible, verifiable date); "
             "❓ = UNVERIFIABLE 2025-26 edge price (needs NUC raw-candle check).")
    L.append("")
    L.append("| # | Symbol | Cap | Entry date | Exit date | Entry $ | Exit $ | Shares | PnL $ | Return % | Bars | Flag |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for i, r in enumerate(rows, 1):
        flag = "🛑" if id(r) in g_ids else ("❓" if id(r) in u_ids else "")
        L.append(
            f"| {i} | {r['symbol']} | {r['cap_tag']} | {r['entry_date']} | {r['exit_date']} "
            f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} | {float(r['shares']):,.2f} "
            f"| {float(r['pnl']):,.0f} | {float(r['ret_pct']):.2f} | {r['bars_held']} | {flag} |"
        )
    L.append("")
    (EXPORTS / model / "TRADE_LEDGER.md").write_text("\n".join(L) + "\n")


def write_audit(model, info, rows, glitch, unver):
    tot_pnl = _pnl(rows)
    L = []
    L.append(f"# {model} — DATA AUDIT")
    L.append("")
    L.append(f"Total trades: **{len(rows)}** · total PnL: **{fmt_usd(tot_pnl)}**. "
             "Per-trade verdicts in `TRADE_RECHECK.md`.")
    L.append("")
    L.append("## 🛑 CONFIRMED data errors (price impossible, date inside verifiable window)")
    L.append("")
    if glitch:
        L.append(f"{len(glitch)} trade(s), {fmt_usd(_pnl(glitch))} ({_pnl(glitch)/tot_pnl*100:.0f}% of PnL). "
                 "High confidence — the price is impossible for that ticker and the date predates the "
                 "knowledge cutoff (e.g. NFLX Dec-2022 ~$30 when real Netflix was ~$300; BKNG ~$107 when "
                 "Booking trades $2,000-5,000).")
        L.append("")
        L.append("| Symbol | Entry date | Exit date | Entry $ | Exit $ | Return % | PnL $ |")
        L.append("|---|---|---|---:|---:|---:|---:|")
        for r in sorted(glitch, key=lambda r: -float(r["pnl"])):
            L.append(f"| {r['symbol']} | {r['entry_date']} | {r['exit_date']} "
                     f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} "
                     f"| {float(r['ret_pct']):.1f} | {float(r['pnl']):,.0f} |")
    else:
        L.append("None.")
    L.append("")
    L.append("## ❓ UNVERIFIABLE 2025-26 edge prices (real mania OR glitch — needs NUC check)")
    L.append("")
    if unver:
        L.append(f"{len(unver)} trade(s), **{fmt_usd(_pnl(unver))} = {_pnl(unver)/tot_pnl*100:.0f}% of PnL**. "
                 "Out-of-band vs pre-2026 norms, on 2025-07-or-later dates past the Jan-2026 cutoff. "
                 "Self-consistent smooth price paths (entries chain from prior exits) lean REAL; "
                 ">10x-from-baseline magnitudes (e.g. SanDisk to $1,761) lean GLITCH. "
                 "**Resolve by re-pulling the raw eToro daily candles for these names on the NUC.**")
        L.append("")
        L.append("| Symbol | Entry date | Exit date | Entry $ | Exit $ | Return % | PnL $ |")
        L.append("|---|---|---|---:|---:|---:|---:|")
        for r in sorted(unver, key=lambda r: -float(r["pnl"])):
            L.append(f"| {r['symbol']} | {r['entry_date']} | {r['exit_date']} "
                     f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} "
                     f"| {float(r['ret_pct']):.1f} | {float(r['pnl']):,.0f} |")
    else:
        L.append("None.")
    L.append("")
    L.append("---")
    L.append("*Auto-generated by tools/analysis/refresh_export_docs.py.*")
    (EXPORTS / model / "DATA_AUDIT.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
_all_rows = {}


def write_top_summary(infos, equities, audits):
    L = []
    L.append("# Model Exports — US Observer System (2 models)")
    L.append("")
    L.append("Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.")
    L.append("Window 2021-06-01 → 2026-06-18 (~5yr). QQQ 200d SMA regime gate. Net of $1/txn.")
    L.append("")
    L.append("> ⚠️ **DATA-INTEGRITY NOTE:** a large share of PnL rides on 2025-26 price moves that are "
             "UNVERIFIABLE past the Jan-2026 knowledge cutoff (out-of-band vs pre-2026 norms). They may be "
             "real AI/memory-mania moves or corrupted eToro candles — the paths are smooth & self-consistent "
             "but the magnitudes are extreme. Per-model `TRADE_RECHECK.md` has every trade's verdict; resolve "
             "the ❓ names by re-pulling raw eToro candles on the NUC. `retest_sp500` is **85% UNVERIFIABLE** "
             "(WDC + SNDK), so its +112% CAGR is unconfirmed. Only 2 CONFIRMED data errors exist (NFLX 2022, "
             "BKNG 2023) and neither inflates returns.")
    L.append("")
    L.append("| Model | CAGR | MaxDD | Calmar | Final NAV | Trades | WR | ❓ unverif. PnL | 🛑 confirmed-err PnL |")
    L.append("|-------|------|-------|--------|-----------|--------|----|----|----|")
    for model in DESC:
        m = infos[model]["metrics"]
        eq = equities[model]
        mdd = max_drawdown(eq)
        glitch, unver = audits[model]
        tot_pnl = _pnl(_all_rows[model])
        ushare = _pnl(unver) / tot_pnl * 100 if tot_pnl else 0
        gshare = _pnl(glitch) / tot_pnl * 100 if tot_pnl else 0
        L.append(f"| {model} | {m['cagr']:+.1f}% | {mdd:.1f}% | {m['calmar']:.2f} "
                 f"| {fmt_usd(eq[-1][1])} | {m['trades']} | {m.get('wr','—')}% | {ushare:.0f}% | {gshare:.0f}% |")
    L.append("")
    L.append("Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, "
             "`TRADE_RECHECK.md`, `trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.")
    L.append("")
    (EXPORTS / "SUMMARY.md").write_text("\n".join(L) + "\n")


def main():
    infos, equities, audits = {}, {}, {}
    for model in DESC:
        mdir = EXPORTS / model
        info = json.loads((mdir / "model_info.json").read_text())
        with open(mdir / "trade_ledger.csv") as f:
            rows = list(csv.DictReader(f))
        _all_rows[model] = rows
        eq = load_equity(mdir / "equity_curve.csv")
        glitch, unver = audit_trades(rows)
        infos[model], equities[model], audits[model] = info, eq, (glitch, unver)

        write_summary(model, info, eq, glitch, unver)
        write_ledger(model, info, rows, glitch, unver)
        write_audit(model, info, rows, glitch, unver)
        print(f"{model}: {len(rows)} trades | 🛑 confirmed={len(glitch)} ❓ unverifiable={len(unver)} "
              f"| unverif PnL ${_pnl(unver):,.0f}")

    write_top_summary(infos, equities, audits)
    print("wrote per-model SUMMARY.md / TRADE_LEDGER.md / DATA_AUDIT.md + top SUMMARY.md")


if __name__ == "__main__":
    main()

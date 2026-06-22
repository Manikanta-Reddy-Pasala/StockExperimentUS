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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "exports" / "models"

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
# DATA-INTEGRITY AUDIT
# ---------------------------------------------------------------------------
# The eToro candle feed produces impossible price LEVELS for some names at the
# 2025-2026 data edge (bad split adjustment / stale-quote glitches). Those trades
# show absurd exit prices and dominate PnL. We hard-flag them with a manual
# per-ticker sanity ceiling (the highest plausible traded price in-window) and
# also surface every single-position move >= REVIEW_RET for manual eyeballing.
#
# CEILINGS are deliberately generous — anything ABOVE is physically impossible for
# that ticker in this window, so it is a confirmed data glitch, not a judgement call.
PRICE_CEILING = {
    "WDC": 200.0,    # Western Digital traded ~$40-90; $546 exit = glitch
    "SNDK": 120.0,   # SanDisk (2025 WDC spin) ~$40-90; $573-$1761 exits = glitch
    "MU": 300.0,     # Micron ~$60-160; $793-$1080 exits = glitch
    "INTC": 110.0,   # Intel ~$18-50; $119-$125 exits = glitch
}
REVIEW_RET = 80.0    # single-position ret% >= this -> list for manual review


def audit_trades(rows):
    """Return (confirmed_glitch, review_only) lists. Confirmed = exit/entry price
    above the ticker's physical ceiling. Review = big winner, ceiling OK (likely real)."""
    glitch, review = [], []
    for r in rows:
        sym = r["symbol"]
        ep, xp = float(r["entry_px"]), float(r["exit_px"])
        ceil = PRICE_CEILING.get(sym)
        if ceil and (xp > ceil or ep > ceil):
            glitch.append(r)
        elif abs(float(r["ret_pct"])) >= REVIEW_RET:
            review.append(r)
    return glitch, review


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
def write_summary(model, info, eq, glitch, review):
    d = DESC[model]
    m = info["metrics"]
    final = eq[-1][1]
    start = eq[0][1]
    tot_ret = (final / start - 1) * 100
    mdd = max_drawdown(eq)
    yb = year_breakdown(eq)

    glitch_pnl = sum(float(r["pnl"]) for r in glitch)
    tot_pnl = sum(float(r["pnl"]) for r in _all_rows[model])
    glitch_share = (glitch_pnl / tot_pnl * 100) if tot_pnl else 0.0

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

    if glitch:
        L.append("## ⚠️ DATA-INTEGRITY WARNING — headline metrics are NOT trustworthy")
        L.append("")
        L.append(
            f"**{len(glitch)} trade(s) use corrupted eToro price levels** "
            "(impossible exit prices, e.g. "
            + ", ".join(sorted({"{} ${:,.0f}".format(r["symbol"], float(r["exit_px"])) for r in glitch}))
            + "). They contribute "
            f"**{fmt_usd(glitch_pnl)} = {glitch_share:.0f}% of all PnL**. "
            "Until the underlying eToro candles are re-pulled and validated on the NUC, "
            "treat CAGR / Final NAV below as an UPPER bound, not a real result. "
            "See `DATA_AUDIT.md`."
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
    if glitch:
        L.append(f"| **PnL from corrupted trades** | **{fmt_usd(glitch_pnl)} ({glitch_share:.0f}% of total)** |")
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


def write_ledger(model, info, rows, glitch, review):
    glitch_ids = {id(r) for r in glitch}
    review_ids = {id(r) for r in review}
    L = []
    L.append(f"# {model} — trade ledger ({info['window'].replace('..',' → ')})")
    L.append("")
    L.append("Flag column: 🛑 = confirmed corrupted price (excluded from trustworthy stats); "
             "👀 = big winner, price plausible (review).")
    L.append("")
    L.append("| # | Symbol | Cap | Entry date | Exit date | Entry $ | Exit $ | Shares | PnL $ | Return % | Bars | Flag |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for i, r in enumerate(rows, 1):
        flag = "🛑" if id(r) in glitch_ids else ("👀" if id(r) in review_ids else "")
        L.append(
            f"| {i} | {r['symbol']} | {r['cap_tag']} | {r['entry_date']} | {r['exit_date']} "
            f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} | {float(r['shares']):,.2f} "
            f"| {float(r['pnl']):,.0f} | {float(r['ret_pct']):.2f} | {r['bars_held']} | {flag} |"
        )
    L.append("")
    (EXPORTS / model / "TRADE_LEDGER.md").write_text("\n".join(L) + "\n")


def write_audit(model, info, rows, glitch, review):
    tot_pnl = sum(float(r["pnl"]) for r in rows)
    glitch_pnl = sum(float(r["pnl"]) for r in glitch)
    review_pnl = sum(float(r["pnl"]) for r in review)
    L = []
    L.append(f"# {model} — DATA AUDIT")
    L.append("")
    L.append(f"Total trades: **{len(rows)}** · total PnL: **{fmt_usd(tot_pnl)}**")
    L.append("")
    L.append("## 🛑 Confirmed corrupted prices (eToro glitch — exit price physically impossible)")
    L.append("")
    if glitch:
        L.append(f"{len(glitch)} trade(s), **{fmt_usd(glitch_pnl)} = {glitch_pnl/tot_pnl*100:.0f}% of total PnL**. "
                 "Exit price exceeds the ticker's highest plausible in-window level "
                 "(ceiling in `PRICE_CEILING`). These are split-adjust / stale-quote glitches at the "
                 "2025-2026 data edge and must be re-pulled on the NUC before the model is trusted.")
        L.append("")
        L.append("| Symbol | Entry date | Exit date | Entry $ | Exit $ | Ceiling $ | Return % | PnL $ |")
        L.append("|---|---|---|---:|---:|---:|---:|---:|")
        for r in sorted(glitch, key=lambda r: -float(r["pnl"])):
            L.append(f"| {r['symbol']} | {r['entry_date']} | {r['exit_date']} "
                     f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} "
                     f"| {PRICE_CEILING[r['symbol']]:,.0f} | {float(r['ret_pct']):.1f} | {float(r['pnl']):,.0f} |")
    else:
        L.append("None.")
    L.append("")
    L.append(f"## 👀 Big winners with plausible prices (likely REAL — listed for review)")
    L.append("")
    if review:
        L.append(f"{len(review)} trade(s) with |ret| ≥ {REVIEW_RET:.0f}%, exit price within sanity ceiling "
                 f"(e.g. NVDA 2024 split-adjusted run, PLTR 2024-25). Contributes {fmt_usd(review_pnl)}. "
                 "Plausible but verify against the eToro series.")
        L.append("")
        L.append("| Symbol | Entry date | Exit date | Entry $ | Exit $ | Return % | PnL $ |")
        L.append("|---|---|---|---:|---:|---:|---:|")
        for r in sorted(review, key=lambda r: -float(r["pnl"])):
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
    L.append("> ⚠️ **DATA-INTEGRITY WARNING:** the eToro candle feed has corrupted price levels at the "
             "2025-2026 edge that inflate headline CAGR/NAV. Per-model `DATA_AUDIT.md` lists the flagged "
             "trades. Headline numbers below are an UPPER bound until the eToro candles are re-pulled and "
             "validated on the NUC. Especially `retest_sp500`, where one corrupted WDC trade alone is ~67% of PnL.")
    L.append("")
    L.append("| Model | CAGR | MaxDD | Calmar | Final NAV | Trades | WR | 🛑 corrupt PnL share |")
    L.append("|-------|------|-------|--------|-----------|--------|----|----|")
    for model in DESC:
        m = infos[model]["metrics"]
        eq = equities[model]
        mdd = max_drawdown(eq)
        glitch, _ = audits[model]
        tot_pnl = sum(float(r["pnl"]) for r in _all_rows[model])
        gshare = sum(float(r["pnl"]) for r in glitch) / tot_pnl * 100 if tot_pnl else 0
        L.append(f"| {model} | {m['cagr']:+.1f}% | {mdd:.1f}% | {m['calmar']:.2f} "
                 f"| {fmt_usd(eq[-1][1])} | {m['trades']} | {m.get('wr','—')}% | {gshare:.0f}% |")
    L.append("")
    L.append("Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, "
             "`trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.")
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
        glitch, review = audit_trades(rows)
        infos[model], equities[model], audits[model] = info, eq, (glitch, review)

        write_summary(model, info, eq, glitch, review)
        write_ledger(model, info, rows, glitch, review)
        write_audit(model, info, rows, glitch, review)
        print(f"{model}: {len(rows)} trades | 🛑 glitch={len(glitch)} 👀 review={len(review)} "
              f"| glitch PnL ${sum(float(r['pnl']) for r in glitch):,.0f}")

    write_top_summary(infos, equities, audits)
    print("wrote per-model SUMMARY.md / TRADE_LEDGER.md / DATA_AUDIT.md + top SUMMARY.md")


if __name__ == "__main__":
    main()

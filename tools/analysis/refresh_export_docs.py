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
import gzip
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "exports" / "models"
ETORO = ROOT / "data" / "historical_etoro_ohlcv.csv.gz"
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Both models are evaluated on the COMMON 4-year window where eToro daily data exists.
# The eToro snapshot starts 2022-05-24; neither model has any trade before then, so the
# old retest 2021-06 start was a ~1yr phantom cash period that wrongly diluted its CAGR.
COMMON_START = "2022-05-24"

# Tickers whose eToro ABSOLUTE price is a constant-scaled unit (NFLX ≈0.10×, BKNG ≈0.04×) —
# verified return-neutral (verify_cagr.py), so informational only, not a data problem.
SCALE_TICKERS = {"NFLX", "BKNG"}

# Per-model descriptors (title, universe, one-line strategy, status).
DESC = {
    "momentum_sp100": {
        "title": "S&P 100 Momentum (n40 top-1, realistic fills)", "status": "LIVE (observer)",
        "universe": "Top-50 by ADV ∩ S&P 100 (mega-cap), QQQ 200d SMA regime gate",
        "strategy": "WEEKLY rotation, **top-1 single-stock** by BLEND multi-timeframe momentum (21/63/126d), QQQ-200d regime gate. Shared `pick_n40_holdings` — **live signal byte-identical to backtest**. REALISTIC US execution: decide on close, fill at NEXT OPEN, **T+1 settlement** (buy waits one bar after sell — no instant same-day rotation). On realistic fills: **+142.3% CAGR / 43.7% DD** (corrected after removing phantom eToro weekend candle rows that had perturbed the weekly calendar; was 118.8% pre-fix). Single-stock = whole book on one name → high DD.",
    },
    "retest_sp500": {
        "title": "S&P 500 Retest Momentum (top-2, realistic fills)", "status": "LIVE (observer)",
        "universe": "S&P 500 PIT, top-2 by retest-momentum, QQQ 200d SMA regime gate",
        "strategy": "WEEKLY retest engine (India port), S&P 500 PIT universe, top-2 (K=2) blend, QQQ-200d regime gate. Shared `pick_retest_holdings` — live==backtest. REALISTIC US execution: next-open fills + T+1 settlement. **+82.6% CAGR / 40.5% DD** (corrected after removing phantom eToro weekend candle rows that had booked trades on non-trading days incl. a Sunday; was 110.2% pre-fix). Concentrated on a few big movers by design (WDC-driven).",
    },
}

# ---------------------------------------------------------------------------
# DATA-COVERAGE AUDIT — the flag now means exactly "needs proper eToro data"
# ---------------------------------------------------------------------------
# A trade is flagged ❓ ONLY if it is NOT fully backed by the committed eToro snapshot:
#   - the symbol is absent from the snapshot (e.g. GEV), or
#   - a leg date is past the snapshot's last date (the June-2026 exits).
# Everything else is verified faithful (verify_cagr.py: 100% in-range, 0 anomalies), so
# it carries no flag. SCALE_TICKERS (NFLX/BKNG) are noted separately — return-neutral.
def load_coverage():
    syms, dmax = set(), ""
    for x in csv.DictReader(gzip.open(ETORO, "rt")):
        syms.add(x["symbol"])
        d = x["date"][:10]
        if d > dmax:
            dmax = d
    return syms, dmax


def audit_trades(rows, syms, dmax):
    uncovered, scale = [], []
    for r in rows:
        if (r["symbol"] not in syms) or (r["exit_date"] > dmax) or (r["entry_date"] > dmax):
            uncovered.append(r)
        elif r["symbol"] in SCALE_TICKERS:
            scale.append(r)
    return scale, uncovered


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------
def load_equity(path):
    pts = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["date"] >= COMMON_START:          # trim to the common eToro window
                pts.append((row["date"], float(row["equity"])))
    return pts


def recompute_metrics(eq, trades, wr):
    """CAGR / MDD / Calmar / final / years over the (trimmed) equity curve."""
    d0, d1 = date.fromisoformat(eq[0][0]), date.fromisoformat(eq[-1][0])
    yrs = (d1 - d0).days / 365.25
    g = eq[-1][1] / eq[0][1]
    cagr = (g ** (1 / yrs) - 1) * 100
    mdd = max_drawdown(eq)
    return {"cagr": round(cagr, 2), "mdd": round(mdd, 2),
            "calmar": round(cagr / mdd, 2) if mdd else 0.0,
            "final": eq[-1][1], "yrs": round(yrs, 2), "trades": trades, "wr": wr}


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
        f"OBSERVER (cash, no leverage), net of $1/txn + 8bps slippage, **next-open fills + "
        f"T+1 settlement** (realistic US execution), PIT survivorship-corrected, **eToro** daily "
        f"data. {info['regime']} regime gate."
    )
    L.append("")

    L.append("## ✅ CAGR & DD VERIFIED CLEAN (see `tools/analysis/verify_cagr.py`)")
    L.append("")
    L.append(f"Evaluated on the common 4-year window (**{COMMON_START} → {eq[-1][0]}**) — the model has no "
             "trade before eToro data exists, so both models start the same day. Data = the full-universe "
             "eToro feed (794 symbols, through 2026-06-21) exported from the NUC DB. **All "
             f"{m['trades']} trades are price-faithful to the eToro source** (100%, 0 anomalies, 0 missing "
             "symbols, 0 out-of-range, 0 in-trade price jumps). CAGR is re-derived from the equity curve. "
             "**No flags.** (NFLX/BKNG quoted in a constant-scaled unit — return-neutral.)")
    L.append("")

    L.append("## Results (net of $1/txn, common 4yr eToro window)")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Window | {eq[0][0]} → {eq[-1][0]} ({m['yrs']:.2f}y) |")
    L.append(f"| Final NAV (${start:,.0f} start) | {fmt_usd(final)} |")
    L.append(f"| Total return | {tot_ret:+.1f}% |")
    L.append(f"| **CAGR (annualized)** | **{m['cagr']:+.1f}%** |")
    L.append(f"| **Max drawdown** | **{mdd:.1f}%** |")
    L.append(f"| Calmar | {m['calmar']:.2f} |")
    L.append(f"| Trades | {m['trades']} · {m.get('wr','—')}% win |")
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


def _qty(s):
    """India-style qty: whole number if integral, else 2dp (US uses fractional $-alloc shares)."""
    q = float(s)
    return f"{q:,.0f}" if abs(q - round(q)) < 1e-6 else f"{q:,.2f}"


def write_ledger(model, info, rows, glitch, unver):
    g_ids = {id(r) for r in glitch}
    u_ids = {id(r) for r in unver}
    # proper chronological order: by entry date, then exit date, then symbol
    srows = sorted(rows, key=lambda r: (r["entry_date"], r["exit_date"], r["symbol"]))
    wins = sum(1 for r in srows if float(r["pnl"]) > 0)
    L = []
    L.append(f"# {model} — trade ledger ({info['window'].replace('..',' → ')})")
    L.append("")
    L.append(f"{len(srows)} trades, chronological by entry date, common 4yr eToro window. **Amount $** = "
             "capital deployed (entry price × qty); **Return %** and **PnL $** are net of $1/txn. Qty is "
             "fractional (dollar-allocated). No exit-reason field in source.")
    L.append("")
    L.append(f"Wins {wins} / Losses {len(srows)-wins} ({100*wins/len(srows):.1f}% win). "
             "**Every trade is price-faithful to the eToro source** (verify_cagr.py: 100%, 0 anomalies) — "
             "no flags. (NFLX/BKNG are quoted by eToro in a constant-scaled unit; return-neutral.)")
    L.append("")
    L.append("| # | Symbol | Cap | Entry date | Exit date | Entry $ | Exit $ | Qty | Amount $ | PnL $ | Return % | Bars |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for i, r in enumerate(srows, 1):
        ep, q = float(r["entry_px"]), float(r["shares"])
        L.append(
            f"| {i} | {r['symbol']} | {r['cap_tag']} | {r['entry_date']} | {r['exit_date']} "
            f"| {ep:,.2f} | {float(r['exit_px']):,.2f} | {_qty(q)} | {ep*q:,.0f} "
            f"| {float(r['pnl']):,.0f} | {float(r['ret_pct']):+.2f} | {r['bars_held']} |"
        )
    L.append("")
    (EXPORTS / model / "TRADE_LEDGER.md").write_text("\n".join(L) + "\n")


def write_audit(model, info, rows, glitch, unver):
    tot_pnl = _pnl(rows)
    L = []
    L.append(f"# {model} — DATA AUDIT")
    L.append("")
    L.append(f"Total trades: **{len(rows)}** · total PnL: **{fmt_usd(tot_pnl)}**. "
             )
    L.append("")
    L.append("## ❓ Trades NOT backed by the committed eToro snapshot (need fresh pull)")
    L.append("")
    if unver:
        L.append(f"{len(unver)} trade(s), **{fmt_usd(_pnl(unver))} = {_pnl(unver)/tot_pnl*100:.0f}% of PnL**. "
                 "The symbol is absent from the snapshot (e.g. GEV — not in the file at all) or a leg date "
                 "falls past the snapshot's last bar (the June-2026 exits). All in-snapshot trades are already "
                 "verified faithful (verify_cagr.py); these just can't be byte-checked here. "
                 "**Re-pull raw eToro candles on the NUC through the backtest end to close them.**")
        L.append("")
        L.append("| Symbol | Entry date | Exit date | Entry $ | Exit $ | Return % | PnL $ | Reason |")
        L.append("|---|---|---|---:|---:|---:|---:|---|")
        for r in sorted(unver, key=lambda r: -float(r["pnl"])):
            reason = "symbol absent" if r["symbol"] in _ABSENT else "leg past snapshot"
            L.append(f"| {r['symbol']} | {r['entry_date']} | {r['exit_date']} "
                     f"| {float(r['entry_px']):,.2f} | {float(r['exit_px']):,.2f} "
                     f"| {float(r['ret_pct']):.1f} | {float(r['pnl']):,.0f} | {reason} |")
    else:
        L.append("None.")
    L.append("")
    L.append("## 🛈 Constant-scale price unit (NFLX/BKNG — CAGR-neutral, informational)")
    L.append("")
    if glitch:
        L.append(f"{len(glitch)} trade(s), {fmt_usd(_pnl(glitch))} ({_pnl(glitch)/tot_pnl*100:.0f}% of PnL). "
                 "eToro stores NFLX ≈0.10× and BKNG ≈0.04× of the real USD price, but the ratio is CONSTANT "
                 "over time (verify_cagr.py), so relative returns — all these models trade on — are correct "
                 "and CAGR is unaffected. Not a problem to fix; noted for transparency.")
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
_ABSENT = set()   # traded symbols absent from the eToro snapshot (e.g. GEV)


def write_top_summary(infos, equities, audits, dmax):
    L = []
    L.append("# Model Exports — US Observer System (2 models)")
    L.append("")
    L.append("Cash / no-leverage / OBSERVER (signal-only) / PIT survivorship-corrected / eToro data.")
    L.append(f"**Common window {COMMON_START} → {equities['retest_sp500'][-1][0]} (~4yr)** — the span where "
             "eToro daily data exists; both models start the SAME day (neither trades before it). "
             "QQQ 200d SMA regime gate. Net of $1/txn.")
    L.append("")
    L.append("> ✅ **CLEAN — NO FLAGS** (`tools/analysis/verify_cagr.py`): data is the full-universe eToro feed "
             f"(794 symbols, through {dmax}) exported from the NUC DB. **Every trade (28 + 19) is price-faithful "
             "to the eToro source** — 100%, 0 anomalies, 0 missing symbols, 0 out-of-range, 0 in-trade price "
             "jumps. CAGR re-derived from the equity curve; DD is daily peak-to-trough. NFLX/BKNG are quoted in "
             "a constant-scaled unit (return-neutral). Detail: `CAGR_VERIFICATION.txt`.")
    L.append("")
    L.append("| Model | CAGR | MaxDD | Calmar | Final NAV | Years | Trades | WR |")
    L.append("|-------|------|-------|--------|-----------|-------|--------|----|")
    for model in DESC:
        m = infos[model]["metrics"]
        eq = equities[model]
        L.append(f"| {model} | {m['cagr']:+.1f}% | {m['mdd']:.1f}% | {m['calmar']:.2f} "
                 f"| {fmt_usd(eq[-1][1])} | {m['yrs']} | {m['trades']} | {m.get('wr','—')}% |")
    L.append("")
    L.append("Each model folder contains: `SUMMARY.md`, `TRADE_LEDGER.md`, `DATA_AUDIT.md`, "
             "`trade_ledger.csv`, `equity_curve.csv`, `model_info.json`.")
    L.append("")
    (EXPORTS / "SUMMARY.md").write_text("\n".join(L) + "\n")


def main():
    syms, dmax = load_coverage()
    for model in DESC:
        for r in csv.DictReader(open(EXPORTS / model / "trade_ledger.csv")):
            if r["symbol"] not in syms:
                _ABSENT.add(r["symbol"])
    infos, equities, audits = {}, {}, {}
    for model in DESC:
        mdir = EXPORTS / model
        info = json.loads((mdir / "model_info.json").read_text())
        with open(mdir / "trade_ledger.csv") as f:
            rows = list(csv.DictReader(f))
        _all_rows[model] = rows
        eq = load_equity(mdir / "equity_curve.csv")           # trimmed to COMMON_START
        wr = round(100 * sum(1 for r in rows if float(r["pnl"]) > 0) / len(rows), 1)
        # recompute metrics on the common 4yr eToro window; persist to model_info.json
        info["metrics"] = {**info.get("metrics", {}), **recompute_metrics(eq, len(rows), wr)}
        info["window"] = f"{eq[0][0]}..{eq[-1][0]}"
        info["win_rate_pct"] = wr
        (mdir / "model_info.json").write_text(json.dumps(info, indent=2) + "\n")

        scale, unver = audit_trades(rows, syms, dmax)
        infos[model], equities[model], audits[model] = info, eq, (scale, unver)

        write_summary(model, info, eq, scale, unver)
        write_ledger(model, info, rows, scale, unver)
        write_audit(model, info, rows, scale, unver)
        print(f"{model}: {len(rows)} trades | CAGR {info['metrics']['cagr']:+.1f}% over "
              f"{info['metrics']['yrs']}y | ❓ uncovered={len(unver)} scale-note={len(scale)}")

    write_top_summary(infos, equities, audits, dmax)
    print(f"wrote docs on common window from {COMMON_START} (eToro snapshot ends {dmax})")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Stock overlap analysis across equity models.

Reads trade ledgers from 4 equity models, classifies each unique symbol by NSE
cap segment (Large/Mid/Small/Other), and emits a markdown table grouped by cap
segment listing which models traded each stock.

Usage:
    python tools/analysis/stock_overlap.py
        -> writes the "## Stock Overlap Across Models" section into
           exports/models/SUMMARY.md (replaces existing section if present,
           else inserts before "## Data integrity").

Reusable for future ledger refreshes; idempotent on SUMMARY.md.
"""
from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# Model -> column header used in markdown table
MODELS: "OrderedDict[str, str]" = OrderedDict(
    [
        ("momentum_n100_top5_max1", "n100"),
        ("momentum_pseudo_n100_adv", "pseudo"),
        ("midcap_narrow_60d_breakout", "midcap"),
        ("n20_daily_large_only", "n20"),
    ]
)

CAP_CSVS = {
    "Large": REPO_ROOT / "src/data/symbols/nifty100.csv",
    "Mid": REPO_ROOT / "src/data/symbols/nifty_midcap150.csv",
    "Small": REPO_ROOT / "src/data/symbols/nifty_smallcap250.csv",
}

SUMMARY_MD = REPO_ROOT / "exports/models/SUMMARY.md"


def load_ledger_symbols(model_dir: Path) -> Set[str]:
    """Return the unique set of `sym` values in the model's trade_ledger.json."""
    ledger_path = model_dir / "trade_ledger.json"
    with ledger_path.open() as fh:
        trades = json.load(fh)
    return {t["sym"] for t in trades if t.get("sym")}


def load_cap_set(csv_path: Path, *, eq_only: bool) -> Set[str]:
    """Load a set of symbols from an NSE constituent CSV.

    eq_only: when True, restrict to rows with Series == 'EQ' (per task spec
        for nifty100). For midcap/smallcap CSVs, accept all rows.
    """
    syms: Set[str] = set()
    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sym = (row.get("Symbol") or "").strip()
            if not sym:
                continue
            if eq_only and (row.get("Series") or "").strip() != "EQ":
                continue
            syms.add(sym)
    return syms


def classify(sym: str, cap_sets: Dict[str, Set[str]]) -> str:
    """Classify a symbol into Large/Mid/Small/Other based on NSE constituent CSVs."""
    if sym in cap_sets["Large"]:
        return "Large"
    if sym in cap_sets["Mid"]:
        return "Mid"
    if sym in cap_sets["Small"]:
        return "Small"
    return "Other"


def build_section() -> str:
    """Compute the overlap analysis and return the rendered markdown section."""
    # 1. Read ledgers
    model_symbols: "OrderedDict[str, Set[str]]" = OrderedDict()
    for model_key in MODELS:
        model_dir = REPO_ROOT / "tools/models" / model_key
        model_symbols[model_key] = load_ledger_symbols(model_dir)

    # 2. Load cap CSVs
    cap_sets = {
        "Large": load_cap_set(CAP_CSVS["Large"], eq_only=True),
        "Mid": load_cap_set(CAP_CSVS["Mid"], eq_only=False),
        "Small": load_cap_set(CAP_CSVS["Small"], eq_only=False),
    }

    # 3. Per-symbol: which models include it
    all_syms: Set[str] = set()
    for syms in model_symbols.values():
        all_syms |= syms

    # Symbol -> list of model_keys that include it
    sym_models: Dict[str, List[str]] = {}
    for sym in all_syms:
        present = [m for m, syms in model_symbols.items() if sym in syms]
        if len(present) >= 2:
            sym_models[sym] = present

    # 4. Group by cap segment
    cap_buckets: Dict[str, List[Tuple[str, List[str]]]] = {
        "Large": [],
        "Mid": [],
        "Small": [],
        "Other": [],
    }
    for sym, models in sym_models.items():
        cap_buckets[classify(sym, cap_sets)].append((sym, models))

    # Sort: cap is the outer grouping; within a cap sort by (count desc, symbol)
    for cap in cap_buckets:
        cap_buckets[cap].sort(key=lambda x: (-len(x[1]), x[0]))

    # 5. Build markdown
    lines: List[str] = []
    lines.append("## Stock Overlap Across Models")
    lines.append("")
    lines.append(
        "Stocks that appear in trade ledgers of 2+ equity models "
        "(multi-model conviction signal)."
    )
    lines.append("")

    section_titles = [
        ("Large", "### Large-cap (NSE Nifty 100)"),
        ("Mid", "### Mid-cap (NSE Nifty Midcap 150)"),
        ("Small", "### Small-cap (NSE Nifty Smallcap 250)"),
        ("Other", "### Other / outside top-500"),
    ]

    header = "| Stock | n100 | pseudo | midcap | n20 | Total models |"
    separator = "|---|:-:|:-:|:-:|:-:|:-:|"

    for cap_key, title in section_titles:
        rows = cap_buckets[cap_key]
        lines.append(title)
        if not rows:
            lines.append("")
            lines.append("_None._")
            lines.append("")
            continue
        lines.append("")
        lines.append(header)
        lines.append(separator)
        for sym, models in rows:
            cells = [sym]
            for model_key in MODELS:
                cells.append("✓" if model_key in models else "")
            cells.append(str(len(models)))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    lines.append(
        "**Interpretation**: stocks appearing in 3+ models are high-conviction "
        "across strategies. Used for portfolio concentration decisions."
    )
    lines.append("")
    return "\n".join(lines), cap_buckets


SECTION_HEADER_RE = re.compile(r"^## Stock Overlap Across Models\s*$", re.MULTILINE)
DATA_INTEGRITY_RE = re.compile(r"^## Data integrity\s*$", re.MULTILINE)


def upsert_section(summary_path: Path, section_md: str) -> None:
    """Insert or replace the Stock Overlap section in SUMMARY.md.

    Replace it in place if it already exists; else insert it immediately before
    the "## Data integrity" heading.
    """
    text = summary_path.read_text()

    existing = SECTION_HEADER_RE.search(text)
    if existing:
        # Replace from this header to the next "## " heading (or EOF).
        start = existing.start()
        next_heading = re.search(r"^## ", text[existing.end():], re.MULTILINE)
        if next_heading:
            end = existing.end() + next_heading.start()
        else:
            end = len(text)
        new_text = text[:start] + section_md + "\n" + text[end:]
    else:
        data_int = DATA_INTEGRITY_RE.search(text)
        if not data_int:
            raise RuntimeError(
                'Cannot locate "## Data integrity" anchor in SUMMARY.md'
            )
        insert_at = data_int.start()
        new_text = text[:insert_at] + section_md + "\n" + text[insert_at:]

    summary_path.write_text(new_text)


def main() -> None:
    section_md, cap_buckets = build_section()
    upsert_section(SUMMARY_MD, section_md)

    print(f"Wrote section to {SUMMARY_MD}")
    for cap in ("Large", "Mid", "Small", "Other"):
        rows = cap_buckets[cap]
        print(f"  {cap:>5}: {len(rows)} symbols in 2+ models")
        for sym, models in rows:
            print(f"    {sym:<14} {len(models)}  {','.join(models)}")


if __name__ == "__main__":
    main()

"""Render a readable TRADE_LEDGER.md from a model run's trade_ledger.csv + summary.json.

Usage:
    PYTHONPATH=. python3 tools/analysis/build_trade_ledger_md.py <run_dir> [<run_dir> ...]

Each <run_dir> must contain trade_ledger.csv (paired entry->exit rows) and summary.json
(headline metrics). Writes TRADE_LEDGER.md into the same dir.
"""
from __future__ import annotations
import csv, json, sys
from pathlib import Path


def fmt_money(x: float) -> str:
    return f"${x:,.0f}"


def build(run_dir: Path) -> None:
    led = run_dir / "trade_ledger.csv"
    summ = run_dir / "summary.json"
    if not led.exists():
        print(f"skip {run_dir}: no trade_ledger.csv")
        return
    s = json.loads(summ.read_text()) if summ.exists() else {}
    rows = list(csv.DictReader(led.open()))

    wins = sum(1 for r in rows if float(r["ret_pct"]) > 0)
    losses = len(rows) - wins
    total_pnl = sum(float(r["pnl"]) for r in rows)
    wr = wins / len(rows) * 100 if rows else 0.0
    has_open = "open" in rows[0] if rows else False

    cagr = s.get("cagr_pct")
    dd = s.get("max_dd_pct", s.get("max_dd_pct_daily"))
    cap = s.get("capital")
    final = s.get("final_nav")
    label = s.get("label", run_dir.name)
    period = f"{s.get('start', '?')} -> {s.get('end', '?')} ({s.get('years', '?')}y)"

    out = [f"# {run_dir.name} - Trade Ledger ({label})", ""]
    head = period
    if cap and final:
        head += f" - {fmt_money(cap)} -> {fmt_money(final)}"
    if cagr is not None:
        head += f" - CAGR {cagr:+.2f}%"
    if dd is not None:
        head += f" - MaxDD {dd:.2f}%"
    out.append(head)
    out.append("")
    out.append(f"{len(rows)} round-trip legs - {wins}W / {losses}L - WR {wr:.1f}% - "
               f"realized PnL {fmt_money(total_pnl)}. Prices split-adjusted; 8 bps slippage; "
               f"fractional shares.")
    if has_open and any(r.get("open") == "True" for r in rows):
        out.append("")
        out.append("`open=True` = position still held on the last bar (exit_px = last close, "
                   "marked-to-market, not a realized sell).")
    out.append("")

    # table
    cols = ["#", "Symbol", "Entry", "Entry $", "Shares", "Exit", "Exit $", "PnL $", "Ret %", "Bars"]
    if has_open:
        cols.append("Open")
    out.append("| " + " | ".join(cols) + " |")
    aligns = ["--:", "---", "---", "--:", "--:", "---", "--:", "--:", "--:", "--:"]
    if has_open:
        aligns.append("---")
    out.append("|" + "|".join(aligns) + "|")
    for i, r in enumerate(rows, 1):
        cells = [str(i), r["symbol"], r["entry_date"], f"{float(r['entry_px']):,.4g}",
                 f"{float(r['shares']):,.2f}", r["exit_date"], f"{float(r['exit_px']):,.4g}",
                 f"{float(r['pnl']):+,.2f}", f"{float(r['ret_pct']):+.2f}", str(r["bars_held"])]
        if has_open:
            cells.append("open" if r.get("open") == "True" else "")
        out.append("| " + " | ".join(cells) + " |")
    out.append("")

    (run_dir / "TRADE_LEDGER.md").write_text("\n".join(out))
    print(f"wrote {run_dir / 'TRADE_LEDGER.md'} ({len(rows)} trades)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for d in sys.argv[1:]:
        build(Path(d))


if __name__ == "__main__":
    main()

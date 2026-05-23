"""Daily Telegram summary for momentum rotation.

Sends a single short message with:
  - Portfolio NAV + total P&L %
  - Day P&L (vs yesterday's close)
  - Current holding + entry-anchored % return
  - Top-1 momentum pick + 60d return
  - Rebalance status (HOLD / REBALANCED / FAILED / NO_DATA)

State is read from /app/logs/momrot/ledger/momrot_ledger.json and
universe from /app/logs/momrot/universes/n100_current.json.

Usage:
  python tools/live/daily_summary.py [--status REBALANCED|HOLD|FAILED] \
                                      [--detail "extra detail line"]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.shared.ohlcv_cache import read_cached  # noqa: E402
from tools.live.telegram_notify import send  # noqa: E402

LEDGER = Path("/app/logs/momrot/ledger/momrot_ledger.json")
UNIVERSE = Path("/app/logs/momrot/universes/n100_current.json")
HISTORY = Path("/app/logs/momrot/ledger/trade_history.jsonl")
STATE_FILE = Path("/app/logs/momrot/ledger/daily_nav.json")
STARTING_CAPITAL = 1_000_000.0


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _close(symbol: str, target_ts: int, days_back: int = 90) -> float:
    df = read_cached(symbol, "D", target_ts - days_back * 86400, target_ts)
    if df.empty:
        return 0.0
    return float(df.iloc[-1]["close"])


def _ret_60d(symbol: str, ts: int) -> float:
    cur = _close(symbol, ts)
    past = _close(symbol, ts - 60 * 86400)
    if cur > 0 and past > 0:
        return (cur / past - 1) * 100
    return 0.0


def _portfolio_nav(ledger: Dict, history: List[Dict], today_ts: int) -> Dict:
    """Read NAV from LIVE Fyers account (funds + holdings)."""
    try:
        from src.services.brokers.fyers_service import FyersService
        svc = FyersService()
        funds = (svc.funds(1) or {}).get("data") or {}
        holdings = (svc.holdings(1) or {}).get("data") or []
    except Exception:
        funds = {}
        holdings = []

    cash = float(funds.get("available_cash") or 0)
    pos_cost = 0.0
    mv = 0.0
    held_str = "None"
    held_pct = 0.0
    unrealized = 0.0

    for p in holdings:
        qty = float(p.get("quantity") or 0)
        if qty <= 0:
            continue
        sym = (p.get("symbol") or "").replace("NSE:", "").replace("-EQ", "")
        avg = float(p.get("average_price") or 0)
        ltp = float(p.get("last_price") or 0)
        pnl = float(p.get("pnl") or (ltp - avg) * qty)
        pos_cost += avg * qty
        mv += ltp * qty
        unrealized += pnl
        if held_str == "None":
            pct = (ltp / avg - 1) * 100 if avg > 0 else 0
            held_str = f"{sym} ({pct:+.1f}%)"
            held_pct = pct

    total = cash + mv
    total_pct = (unrealized / pos_cost * 100) if pos_cost > 0 else 0.0
    return {
        "nav": total, "total_pct": total_pct,
        "cash": cash, "market_value": mv,
        "held_str": held_str, "held_pct": held_pct,
        "realized": 0.0,
    }


def _day_pnl(today_nav: float) -> float:
    """Day P&L = today NAV - yesterday NAV (from STATE_FILE)."""
    s = _load(STATE_FILE, {})
    yesterday_nav = s.get("nav", today_nav)
    return today_nav - yesterday_nav


def _save_nav(nav: float):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"nav": nav, "ts": datetime.now().isoformat()}, f)


def _top_n(today_ts: int, n: int = 5) -> List[Dict]:
    uni = _load(UNIVERSE, {}).get("stocks", [])
    if not uni:
        return []
    rows = []
    for s in uni:
        sym = s["symbol"]
        r = _ret_60d(sym, today_ts)
        if r != 0:
            rows.append({"symbol": sym, "name": s.get("name", sym),
                         "return_60d": r, "price": _close(sym, today_ts)})
    if not rows:
        return []
    rows.sort(key=lambda r: -r["return_60d"])
    return rows[:n]


def _next_rebalance(today: datetime) -> str:
    if today.day <= 7 and today.weekday() < 5:
        return today.date().isoformat()
    if today.month == 12:
        nxt = datetime(today.year + 1, 1, 1)
    else:
        nxt = datetime(today.year, today.month + 1, 1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt.date().isoformat()


def build_message(status: str = "HOLD", detail: str = "") -> str:
    today = datetime.now()
    today_ts = int(today.timestamp())
    ledger = _load(LEDGER, {"open": []})
    history = []
    if HISTORY.exists():
        with open(HISTORY) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history.append(json.loads(line))
                    except Exception:
                        pass

    nav = _portfolio_nav(ledger, history, today_ts)
    day_pnl = _day_pnl(nav["nav"])
    _save_nav(nav["nav"])
    top5 = _top_n(today_ts, 5)
    next_reb = _next_rebalance(today)

    status_emoji = {
        "REBALANCED": "🔄",
        "HOLD": "⏸️",
        "FAILED": "❌",
        "NO_DATA": "⚠️",
    }.get(status, "ℹ️")

    # Held symbol now from Fyers (held_str format "SYM (+X%)" or "None")
    held_sym = nav["held_str"].split(" ")[0] if nav["held_str"] != "None" else ""

    lines = [
        f"*Momrot {today.strftime('%Y-%m-%d')}* {status_emoji} {status}",
        f"NAV ₹{nav['nav']:,.0f}  ({nav['total_pct']:+.2f}%)",
        f"Day P&L ₹{day_pnl:+,.0f}",
        f"Hold {nav['held_str']}",
        f"Next rebalance: {next_reb}",
    ]

    if top5:
        lines.append("")
        lines.append("*Top 5 N100 (60d):*")
        for i, p in enumerate(top5, 1):
            marker = " ✓" if p["symbol"] == held_sym else ""
            lines.append(f"{i}. `{p['symbol']}` {p['return_60d']:+.1f}% @ ₹{p['price']:.2f}{marker}")

    if detail:
        lines.append("")
        lines.append(f"_{detail}_")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", default="HOLD",
                    choices=["REBALANCED", "HOLD", "FAILED", "NO_DATA"])
    ap.add_argument("--detail", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print message but don't send")
    args = ap.parse_args()

    msg = build_message(args.status, args.detail)
    if args.dry_run:
        print(msg)
        return 0
    res = send(msg, "Markdown")
    if not res.get("ok"):
        print(f"FAIL: {res}", file=sys.stderr)
        return 2
    print(f"sent: id={res['result']['message_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

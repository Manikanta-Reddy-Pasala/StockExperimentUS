"""Telegram notification helper for momentum rotation alerts.

Sends messages to a Telegram chat via Bot API. Reads credentials from env:
  TG_BOT_TOKEN  - bot token from @BotFather
  TG_CHAT_ID    - group/channel chat_id (negative for groups)

Usage:
  python tools/live/telegram_notify.py "Rebalance: SELL HFCL, BUY BSE"
  python tools/live/telegram_notify.py --markdown "*Bold text*"
  python tools/live/telegram_notify.py --test
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib import parse, request


API_BASE = "https://api.telegram.org"


def _post(token: str, chat_id: str, text: str, parse_mode: str = None) -> dict:
    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = parse.urlencode(payload).encode()
    try:
        req = request.Request(url, data=data, method="POST")
        with request.urlopen(req, timeout=10) as r:
            import json
            return json.loads(r.read().decode())
    except Exception as e:
        # On 400 (Markdown parse error etc), surface body
        import json
        try:
            body = e.read().decode() if hasattr(e, "read") else ""
        except Exception:
            body = ""
        return {"ok": False, "error": str(e), "body": body}


def notify_signals(model_name: str, signals_file: str) -> dict:
    """Read a signals JSON file and send a TG summary. No-op if empty.

    Returns the send() result or {"ok": True, "skipped": True} when nothing
    to notify (file missing / empty array / read error).
    """
    import json
    from pathlib import Path
    try:
        p = Path(signals_file)
        if not p.exists():
            return {"ok": True, "skipped": True, "reason": "file_missing"}
        sigs = json.loads(p.read_text() or "[]")
        if not sigs:
            return {"ok": True, "skipped": True, "reason": "empty"}
        lines = [f"*Signal* `{model_name}`"]
        for s in sigs[:5]:
            sig_t = s.get("signal", "?")
            sym = s.get("symbol", "?")
            side = s.get("side", "?")
            price = s.get("price")
            reason = s.get("reason", "")
            px_txt = f" @ ₹{float(price):,.2f}" if price else ""
            r_txt = f" ({reason})" if reason else ""
            lines.append(f"`{sig_t}` {side} `{sym}`{px_txt}{r_txt}")
        if len(sigs) > 5:
            lines.append(f"_…+{len(sigs)-5} more_")
        return send("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        return {"ok": False, "error": f"notify_signals: {e}"}


def send(text: str, parse_mode: str = "Markdown",
         token: str = None, chat_id: str = None) -> dict:
    """Send Telegram message. On Markdown parse failure, retry as plain text."""
    token = token or os.environ.get("TG_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TG_CHAT_ID", "")
    if not token or not chat_id:
        return {"ok": False, "error": "TG_BOT_TOKEN or TG_CHAT_ID not set"}

    res = _post(token, chat_id, text, parse_mode=parse_mode)
    if not res.get("ok") and parse_mode:
        # Likely a Markdown parse error — retry as plain text
        res2 = _post(token, chat_id, text, parse_mode=None)
        if res2.get("ok"):
            return res2
        return res
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default=None)
    ap.add_argument("--markdown", action="store_true", default=True)
    ap.add_argument("--plain", dest="markdown", action="store_false")
    ap.add_argument("--test", action="store_true",
                    help="Send a test message")
    args = ap.parse_args()

    text = args.text
    if args.test:
        text = "🤖 momrot test: bot wired, channel reachable."
    if not text:
        print("error: no text supplied", file=sys.stderr)
        sys.exit(1)

    res = send(text, "Markdown" if args.markdown else None)
    if not res.get("ok"):
        print(f"FAIL: {res.get('error') or res}", file=sys.stderr)
        sys.exit(2)
    print(f"sent: message_id={res['result']['message_id']}")


if __name__ == "__main__":
    main()

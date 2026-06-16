# IBKR broker (US) — history + orders

Interactive Brokers integration for the US book. **Scope: history + orders module**
(not the full Fyers-style dashboard/provider stack).

## One core, two consumers (KISS)

History is fetched in exactly one place — `src/services/data/price_history_provider.py`
`fetch_daily_bars(symbol, start, end, prefer="ibkr")` — which tries IBKR first and
falls back to yfinance. Both the **backtest data loader** and the **live IBKR broker**
call it, so backtest data and live history share identical logic.

```
fetch_daily_bars()  ── IBKR (TWS/Gateway) ──┐
                    └─ yfinance (fallback) ──┴─► yfinance-shaped DataFrame
        ▲                                   ▲
        │                                   │
tools/pull_etoro_history.py     IBKRBrokerService.get_history()
   (--source ibkr|auto)                (live broker)
```

## Connection

TWS or IB Gateway must be running with the API enabled. Defaults to **paper port 7497**.

| Env var | Default | Note |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | |
| `IBKR_PORT` | `7497` | paper=7497, live=7496 |
| `IBKR_CLIENT_ID` | `11` | unique per connection |
| `IBKR_TIMEOUT` | `8` | connect timeout (s) |

If TWS is unreachable, history/quotes fall back to yfinance; trading calls return a
clear `{"status":"error"}` instead of throwing.

## Usage

```python
from src.services.brokers.ibkr import IBKRBrokerService
b = IBKRBrokerService()                 # paper 7497
b.test_connection()
b.get_history("AAPL", range_from="2024-01-01", range_to="2024-06-01")
b.get_quotes("AAPL,MSFT")
b.place_order({"symbol": "AAPL", "side": "BUY", "qty": 10, "type": "MKT"})
b.get_positions(); b.get_funds()
```

Load backtest data through the shared core (IBKR primary, yfinance fallback):

```bash
PYTHONPATH=. python tools/pull_etoro_history.py \
    --universe src/data/symbols/nasdaq100.csv \
    --start 2016-05-24 --end 2026-05-24 --source ibkr
```

Tests (run without TWS — exercise the fallback): `pytest tests/test_ibkr_history.py`

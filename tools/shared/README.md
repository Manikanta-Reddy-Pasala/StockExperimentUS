# Shared Infrastructure

Generic data layer shared by all models.

| File | Purpose |
|---|---|
| `ohlcv_cache.py` | Postgres OHLCV cache reader/writer (historical_data_*) |
| `universes.py` | NIFTY 50 / NIFTY 500 universe lists + Fyers fetcher helpers |
| `prefetch_ohlcv.py` | Bulk-prefetch equity OHLC into Postgres cache |
| `fetch_index_spot.py` | Fetch index spot daily into historical_data (NIFTY/BANKNIFTY/FINNIFTY) |
| `prefetch_bhav.py` | Bulk-ingest NSE FO bhavcopy into historical_options (any underlying) |

Not model-specific. Used by `tools/models/*` strategies.

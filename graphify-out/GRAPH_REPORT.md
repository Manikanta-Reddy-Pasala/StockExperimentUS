# Graph Report - StockExperimentUS  (2026-06-20)

## Corpus Check
- 167 files · ~248,255 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2077 nodes · 5624 edges · 72 communities detected
- Extraction: 49% EXTRACTED · 51% INFERRED · 0% AMBIGUOUS · INFERRED: 2854 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]

## God Nodes (most connected - your core abstractions)
1. `Stock` - 186 edges
2. `get_session()` - 151 edges
3. `ModelLedger` - 131 edges
4. `ModelSettings` - 127 edges
5. `SymbolMaster` - 116 edges
6. `HistoricalData` - 97 edges
7. `get_database_manager()` - 91 edges
8. `User` - 90 edges
9. `ModelTrade` - 78 edges
10. `BrokerConfiguration` - 72 edges

## Surprising Connections (you probably didn't know these)
- `Get the last expected trading day (accounting for weekends).` --uses--> `BrokerConfiguration`  [INFERRED]
  scheduler.py → src/models/models.py
- `Check if historical data is fresh enough for technical indicator calculations.` --uses--> `BrokerConfiguration`  [INFERRED]
  scheduler.py → src/models/models.py
- `Delete suggested-stocks rows older than 90 days (runs Sunday at 03:00).` --uses--> `BrokerConfiguration`  [INFERRED]
  scheduler.py → src/models/models.py
- `Check Fyers broker token status and warn if expiring soon.` --uses--> `BrokerConfiguration`  [INFERRED]
  scheduler.py → src/models/models.py
- `Initialize token monitoring for all Fyers users.` --uses--> `BrokerConfiguration`  [INFERRED]
  scheduler.py → src/models/models.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (138): admin_model_ranking(), Batch-resolve LTP for the given symbols (any mix of 'HFCL' or     'NSE:HFCL-EQ'), _resolve_live_prices(), BaseBrokerService, Base class for all broker services., BaseBrokerService, BrokerService, Get a value from cache.                  Args:             key (str): Cache key (+130 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (178): admin_backfill_history(), admin_dashboard(), admin_data_coverage(), admin_model_rebalance(), admin_run_execute(), admin_run_signal(), admin_toggle_enabled(), audit_charges_summary() (+170 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (110): Database Manager for the Automated Trading System, APIResponseType, get_historical_data_service(), HistoricalDataService, Historical Data Service Fetches and stores comprehensive historical OHLCV data f, Fetch historical data for a single stock incrementally.          Args:, API response classification for intelligent handling., Fetch historical data for market benchmarks (NIFTY, SENSEX).         Essential f (+102 more)

### Community 3 - "Community 3"
Cohesion: 0.02
Nodes (123): compute_adv(), main(), Build midcap_narrow universe from N500 by ADV ranking.  Method:   1. Compute 20-, Avg daily ₹ value traded over last `days` calendar days, in lakh., Return avg daily ₹ value traded over last `days` calendar days, in lakh., FundamentalDataService, get_fundamental_data_service(), Fundamental Data Service Fetches real fundamental data (P/E, P/B, ROE, etc.) fro (+115 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (158): Read the per-model ranking JSON written by live_signal.py.      Query:       ?to, Flask Web Application for the Automated Trading System with Swagger Documentatio, Create Flask application., AuditConfigChange, AuditDataQuality, AuditModelRanking, AuditModelSignal, AuditOrder (+150 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (68): ABC, AlertPriority, AlertType, Consolidated Alert Management Service Combines functionality from alerts/ and em, BrokerFeatureFactory, get_broker_feature_factory(), Broker Feature Factory  Implements the Factory and Strategy patterns to provide, Get the global broker feature factory instance. (+60 more)

### Community 6 - "Community 6"
Cohesion: 0.03
Nodes (68): delete_credential(), list_credentials(), Authentication Routes  Handles WebAuthn/Passkey registration and authentication., Begin WebAuthn passkey authentication.      Can be called with or without userna, Complete WebAuthn passkey authentication.      Verifies the authentication respo, Begin WebAuthn passkey registration.      Returns registration options for the b, List all passkey credentials for the current user., Delete a passkey credential. (+60 more)

### Community 7 - "Community 7"
Cohesion: 0.03
Nodes (81): adv_pool(), build_rebal(), get_engine(), load_csv(), load_n100(), load_panels(), load_regime(), load_series() (+73 more)

### Community 8 - "Community 8"
Cohesion: 0.04
Nodes (86): load_n100(), n20_daily_large_only v3: sell-on-evening-3pp-threshold + next-day-open buy.  Var, run(), build_message(), _close(), _day_pnl(), _load(), main() (+78 more)

### Community 9 - "Community 9"
Cohesion: 0.03
Nodes (58): backfill_full_history(), cleanup_old_csv_files(), daily_universe_csv_check(), export_daily_csv(), generate_us_book_signal(), pre_market_data_quality_gate(), No-op: IBKR auth is managed by TWS/Gateway (no TOTP token refresh)., Daily 06:00 IST check: any universe CSV >7d stale → refresh now.      Saturday-o (+50 more)

### Community 10 - "Community 10"
Cohesion: 0.03
Nodes (51): APILogger, log_api_call(), log_error(), log_flask_route(), log_request(), log_response(), API Logging Utility  Comprehensive logging for all API calls, requests, and resp, Decorator to automatically log API calls.          Usage:         @log_api_call( (+43 more)

### Community 11 - "Community 11"
Cohesion: 0.05
Nodes (53): emit_mid_month_signal(), emit_signal(), execute_mid_month_orders(), execute_orders(), _monthly_universe(), _quarterly_universe(), Cron registration for midcap_narrow_60d_breakout.  Data side:   register_data_jo, Daily OHLCV + monthly universe refresh. (+45 more)

### Community 12 - "Community 12"
Cohesion: 0.06
Nodes (28): AlertService, Send portfolio alert to user., Send strategy performance alert to user., Send daily summary to user., Get alerts for a user., Mark an alert as read., Mark all alerts as read for a user., Get alert statistics for a user. (+20 more)

### Community 13 - "Community 13"
Cohesion: 0.06
Nodes (23): OrderService, Execute an order (simulate order execution)., Get orders for a user., Get positions for a user., Get trades for a user., Create order record in database., Create trade record in database., Update user position after trade execution. (+15 more)

### Community 14 - "Community 14"
Cohesion: 0.08
Nodes (20): get_order_sync_service(), OrderSyncService, Order Synchronization Service  Handles efficient syncing of orders between Fyers, Get orders from database., Parse Fyers API response into standardized order format., Map Fyers order status to standardized status., Service to sync orders between Fyers API and database efficiently., Check if database order needs updating based on Fyers data. (+12 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (15): get_trading_engine(), MultiUserTradingEngine, Multi-User Trading Engine Integration, Trading loop for a specific user., Multi-user trading engine integration., Process orders for a specific user., Update positions for a specific user., Check alerts for a specific user. (+7 more)

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (14): DatabaseManager, Manages database connections and sessions., Initialize the database manager.                  Args:             database_url, Create all tables defined in the models., get_user_settings_service(), User Settings Service Handles user-specific settings storage and retrieval, Get a specific setting for a user., Set a specific setting for a user. (+6 more)

### Community 17 - "Community 17"
Cohesion: 0.15
Nodes (5): Holding, Data class for holding information., Convert to dictionary format., get_portfolio_sync_service(), PortfolioSyncService

### Community 18 - "Community 18"
Cohesion: 0.13
Nodes (20): annotate_caps(), cap_for(), cap_summary(), Tag each trade with its market-cap segment (large/mid/other).  Mirrors the India, Coerce a date/datetime/ISO-str/epoch into a date (None on failure)., Cap segment for `sym` -> large|mid|other.      Accepts a date, datetime, ISO str, In-place: set t['cap'] on every trade (from t['sym'] or t['symbol'] and     t['e, Count of trades per cap segment (for summary.json / displays). (+12 more)

### Community 19 - "Community 19"
Cohesion: 0.1
Nodes (4): BrokerDataProcessor, get_order_status_color(), Base Broker Service Interface Defines the common interface that all broker servi, Common data processing utilities for all brokers.

### Community 20 - "Community 20"
Cohesion: 0.2
Nodes (12): fetch(), insert(), main(), Bulk-fetch index spot daily OHLC into historical_data (Fyers API).  Required by, buyAllStocks(), buyStock(), loadTripleModelData(), populateAllTables() (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.39
Nodes (5): for_model_or_env(), from_env(), from_model(), RiskConfig, RiskManager

### Community 22 - "Community 22"
Cohesion: 0.22
Nodes (3): DailySnapshotService, Daily Suggested Stocks Snapshot Service.  Slim helper around the ``daily_suggest, Reader/writer for ``daily_suggested_stocks`` (current schema).

### Community 23 - "Community 23"
Cohesion: 0.39
Nodes (7): buy_time(), emit_time(), is_split(), Per-model execution timing (US RTH, America/New_York).  India ran a walk-forward, True if SELL and BUY times differ (needs two execute jobs)., When to emit the signal: lead_min before the earliest exec time, floor 09:00., sell_time()

### Community 24 - "Community 24"
Cohesion: 0.32
Nodes (7): load_nifty500(), load_nifty500_with_meta(), Nifty 500 universe loader.  Source: NSE archives CSV at ``https://nsearchives.ns, ``RELIANCE`` -> ``NSE:RELIANCE-EQ``., Read the cached Nifty 500 CSV and return a list of symbols., Return ``(fyers_symbol, company_name, industry)`` triples., to_fyers_symbol()

### Community 25 - "Community 25"
Cohesion: 0.47
Nodes (4): load_curve(), main(), Grid-search blend weights over N model equity curves to maximize an objective (C, weight_grid()

### Community 26 - "Community 26"
Cohesion: 0.6
Nodes (4): main(), _mktcap(), Refresh nasdaq500.csv = top 500 Nasdaq-listed stocks by market cap.  Mirrors nif, _sanitize()

### Community 27 - "Community 27"
Cohesion: 0.6
Nodes (4): load_curve(), main(), Blend N model equity curves into a daily-rebalanced portfolio; report combined C, stats()

### Community 28 - "Community 28"
Cohesion: 0.67
Nodes (2): main(), Main entry point for the application runner.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Configuration management for the trading system

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): WSGI entry for gunicorn: `gunicorn -w 4 -b 0.0.0.0:5001 wsgi:app`.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Log API call with comprehensive details.                  Args:             serv

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Remove sensitive information from data.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Context manager for database sessions.                  Yields:             Sess

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Test broker connection.

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Get user profile information.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Get current holdings.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Get current positions.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Modify an existing order.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Calculate P&L for a position.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Format currency with proper Indian notation.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Format quantity with proper notation.

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Get Bootstrap color class for order status.

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Get Bootstrap color class for P&L.

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Get market overview data for major indices.                  Args:             u

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Get portfolio summary metrics.                  Args:             user_id: The u

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Get top holdings by value.                  Args:             user_id: The user

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Get recent trading activity.                  Args:             user_id: The use

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Get account balance and available funds.                  Args:             user

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Get daily P&L data for charting.                  Args:             user_id: The

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Get performance metrics for a given period.                  Args:             u

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Get real-time quotes for watchlist symbols.                  Args:             u

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Get current holdings.                  Args:             user_id: The user ID fo

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Get current positions.                  Args:             user_id: The user ID f

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Get portfolio summary and metrics.                  Args:             user_id: T

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Get portfolio allocation by sector/asset class.                  Args:

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Get portfolio performance metrics.                  Args:             user_id: T

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Get dividend history.                  Args:             user_id: The user ID fo

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Get portfolio risk analysis.                  Args:             user_id: The use

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Generate P&L report for a given period.                  Args:             user_

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Generate tax report for a financial year.                  Args:             use

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Generate portfolio performance report.                  Args:             user_i

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Generate trading activity summary report.                  Args:             use

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Get previously generated reports.                  Args:             user_id: Th

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Download a previously generated report.                  Args:             user_

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Get orders history.                  Args:             user_id: The user ID for

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Get pending orders.                  Args:             user_id: The user ID for

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): Get trades history.                  Args:             user_id: The user ID for

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Place a new order.                  Args:             user_id: The user ID for b

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Modify an existing order.                  Args:             user_id: The user I

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): Cancel an order.                  Args:             user_id: The user ID for bro

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): Get detailed information for a specific order.                  Args:

## Knowledge Gaps
- **413 isolated node(s):** `Main entry point for the application runner.`, `Configuration management for the trading system`, `Refresh all 4 Nifty universe CSVs (nifty100, nifty500, midcap150, smallcap250)`, `Run the complete data pipeline.`, `WSGI entry for gunicorn: `gunicorn -w 4 -b 0.0.0.0:5001 wsgi:app`.` (+408 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 28`** (3 nodes): `main()`, `run.py`, `Main entry point for the application runner.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `config.py`, `Configuration management for the trading system`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `wsgi.py`, `WSGI entry for gunicorn: `gunicorn -w 4 -b 0.0.0.0:5001 wsgi:app`.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Log API call with comprehensive details.                  Args:             serv`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Remove sensitive information from data.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Context manager for database sessions.                  Yields:             Sess`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Test broker connection.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Get user profile information.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Get current holdings.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Get current positions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Modify an existing order.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Calculate P&L for a position.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Format currency with proper Indian notation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Format quantity with proper notation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Get Bootstrap color class for order status.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Get Bootstrap color class for P&L.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Get market overview data for major indices.                  Args:             u`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Get portfolio summary metrics.                  Args:             user_id: The u`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Get top holdings by value.                  Args:             user_id: The user`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Get recent trading activity.                  Args:             user_id: The use`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Get account balance and available funds.                  Args:             user`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Get daily P&L data for charting.                  Args:             user_id: The`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Get performance metrics for a given period.                  Args:             u`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Get real-time quotes for watchlist symbols.                  Args:             u`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Get current holdings.                  Args:             user_id: The user ID fo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Get current positions.                  Args:             user_id: The user ID f`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Get portfolio summary and metrics.                  Args:             user_id: T`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Get portfolio allocation by sector/asset class.                  Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Get portfolio performance metrics.                  Args:             user_id: T`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Get dividend history.                  Args:             user_id: The user ID fo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Get portfolio risk analysis.                  Args:             user_id: The use`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `Generate P&L report for a given period.                  Args:             user_`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Generate tax report for a financial year.                  Args:             use`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `Generate portfolio performance report.                  Args:             user_i`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Generate trading activity summary report.                  Args:             use`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `Get previously generated reports.                  Args:             user_id: Th`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `Download a previously generated report.                  Args:             user_`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Get orders history.                  Args:             user_id: The user ID for`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Get pending orders.                  Args:             user_id: The user ID for`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `Get trades history.                  Args:             user_id: The user ID for`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Place a new order.                  Args:             user_id: The user ID for b`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Modify an existing order.                  Args:             user_id: The user I`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `Cancel an order.                  Args:             user_id: The user ID for bro`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `Get detailed information for a specific order.                  Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_session()` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 16`, `Community 17`, `Community 21`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Why does `Stock` connect `Community 4` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 6`, `Community 9`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `get_database_manager()` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 16`, `Community 21`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Are the 182 inferred relationships involving `Stock` (e.g. with `User` and `WebAuthnCredential`) actually correct?**
  _`Stock` has 182 INFERRED edges - model-reasoned connections that need verification._
- **Are the 150 inferred relationships involving `get_session()` (e.g. with `export_daily_csv()` and `update_symbol_master()`) actually correct?**
  _`get_session()` has 150 INFERRED edges - model-reasoned connections that need verification._
- **Are the 128 inferred relationships involving `ModelLedger` (e.g. with `Recompute ModelTrade.value + pnl + ModelLedger.cash + realized_pnl using the cur` and `Reset a single model (or all 4 equity models) to a clean seed state.  Usage:`) actually correct?**
  _`ModelLedger` has 128 INFERRED edges - model-reasoned connections that need verification._
- **Are the 124 inferred relationships involving `ModelSettings` (e.g. with `Reset a single model (or all 4 equity models) to a clean seed state.  Usage:` and `Mirror Fyers positions → model_ledger to catch drift.  Background: record_buy /`) actually correct?**
  _`ModelSettings` has 124 INFERRED edges - model-reasoned connections that need verification._
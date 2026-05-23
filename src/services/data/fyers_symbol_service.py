"""
Fyers Symbol Service

Downloads and manages official Fyers symbol master files for stock discovery.
Provides search functionality over real NSE/BSE symbol data.
"""

import logging
import pandas as pd
import requests
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class FyersSymbolService:
    """Service to manage Fyers symbol master files for stock discovery."""

    def __init__(self):
        self.symbol_urls = {
            'NSE_CM': 'https://public.fyers.in/sym_details/NSE_CM.csv',
            'BSE_CM': 'https://public.fyers.in/sym_details/BSE_CM.csv',
            'NSE_FO': 'https://public.fyers.in/sym_details/NSE_FO.csv',
            'BSE_FO': 'https://public.fyers.in/sym_details/BSE_FO.csv',
        }

        # Cache directory
        self.cache_dir = os.path.join(os.path.dirname(__file__), '../../data/symbols')
        os.makedirs(self.cache_dir, exist_ok=True)

        # Cache duration: 24 hours
        self.cache_duration = timedelta(hours=24)

        self._symbols_cache = {}
        self._cache_timestamps = {}

        # Initialize database service
        self._db_service = None

    def _get_db_service(self):
        """Lazy load database service to avoid circular imports."""
        if self._db_service is None:
            try:
                from .symbol_database_service import get_symbol_database_service
                self._db_service = get_symbol_database_service()
            except Exception as e:
                logger.warning(f"Could not initialize database service: {e}")
                self._db_service = False  # Mark as unavailable
        return self._db_service if self._db_service is not False else None

    def get_nse_symbols(self, force_refresh: bool = False, use_database: bool = True) -> List[Dict]:
        """Get NSE capital market symbols."""
        # Try database first if available and not forcing refresh
        if use_database and not force_refresh:
            db_service = self._get_db_service()
            if db_service:
                db_symbols = db_service.get_symbols_from_database('NSE')
                if db_symbols:
                    logger.info(f"Retrieved {len(db_symbols)} NSE symbols from database")
                    return db_symbols

        # Fall back to CSV download/cache
        return self._get_symbols('NSE_CM', force_refresh)

    def get_bse_symbols(self, force_refresh: bool = False, use_database: bool = True) -> List[Dict]:
        """Get BSE capital market symbols."""
        # Try database first if available and not forcing refresh
        if use_database and not force_refresh:
            db_service = self._get_db_service()
            if db_service:
                db_symbols = db_service.get_symbols_from_database('BSE')
                if db_symbols:
                    logger.info(f"Retrieved {len(db_symbols)} BSE symbols from database")
                    return db_symbols

        # Fall back to CSV download/cache
        return self._get_symbols('BSE_CM', force_refresh)

    def search_symbols(self, query: str, exchange: str = 'NSE', limit: int = 100, use_database: bool = True) -> List[Dict]:
        """Search for symbols by name or symbol."""
        try:
            # Try database search first if available
            if use_database:
                db_service = self._get_db_service()
                if db_service:
                    db_results = db_service.search_symbols_in_database(query, exchange, limit)
                    if db_results:
                        logger.info(f"Found {len(db_results)} symbols matching '{query}' on {exchange} from database")
                        return db_results

            # Fall back to memory/file cache search
            if exchange.upper() == 'NSE':
                symbols = self.get_nse_symbols(use_database=False)
            elif exchange.upper() == 'BSE':
                symbols = self.get_bse_symbols(use_database=False)
            else:
                logger.warning(f"Unsupported exchange: {exchange}")
                return []

            if not symbols:
                logger.warning(f"No symbols available for {exchange}")
                return []

            # Filter symbols based on query
            query_upper = query.upper()
            matching_symbols = []

            for symbol_data in symbols:
                # Search in symbol name and company name
                symbol = symbol_data.get('symbol', '')
                name = symbol_data.get('name', '')

                if (query_upper in symbol.upper() or
                    query_upper in name.upper()):
                    matching_symbols.append(symbol_data)

                if len(matching_symbols) >= limit:
                    break

            logger.info(f"Found {len(matching_symbols)} symbols matching '{query}' on {exchange} from cache")
            return matching_symbols

        except Exception as e:
            logger.error(f"Error searching symbols: {e}")
            return []

    def get_equity_symbols(self, exchange: str = 'NSE') -> List[Dict]:
        """Get only equity symbols (excluding derivatives)."""
        try:
            if exchange.upper() == 'NSE':
                symbols = self.get_nse_symbols()
            elif exchange.upper() == 'BSE':
                symbols = self.get_bse_symbols()
            else:
                return []

            # Filter for equity symbols (symbol ends with -EQ)
            equity_symbols = []
            for symbol_data in symbols:
                symbol = symbol_data.get('symbol', '')
                if symbol.endswith('-EQ'):
                    equity_symbols.append(symbol_data)

            logger.info(f"Found {len(equity_symbols)} equity symbols on {exchange}")
            return equity_symbols

        except Exception as e:
            logger.error(f"Error getting equity symbols: {e}")
            return []

    def _get_symbols(self, exchange_type: str, force_refresh: bool = False) -> List[Dict]:
        """Get symbols for a specific exchange type."""
        try:
            # Check cache first
            if not force_refresh and self._is_cache_valid(exchange_type):
                return self._symbols_cache.get(exchange_type, [])

            # Download fresh data
            symbols = self._download_symbols(exchange_type)
            if symbols:
                self._symbols_cache[exchange_type] = symbols
                self._cache_timestamps[exchange_type] = datetime.now()

                # Save to disk cache
                self._save_to_disk_cache(exchange_type, symbols)

            return symbols

        except Exception as e:
            logger.error(f"Error getting symbols for {exchange_type}: {e}")
            # Try to load from disk cache as fallback
            return self._load_from_disk_cache(exchange_type)

    def _download_symbols(self, exchange_type: str) -> List[Dict]:
        """Download symbols from official Fyers URL."""
        try:
            url = self.symbol_urls.get(exchange_type)
            if not url:
                logger.error(f"No URL configured for {exchange_type}")
                return []

            logger.info(f"Downloading {exchange_type} symbols from {url}")

            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Parse CSV data without headers
            from io import StringIO
            df = pd.read_csv(StringIO(response.text), header=None)

            # Convert to list of dictionaries based on known column positions
            symbols = []
            for _, row in df.iterrows():
                # Based on analysis: col 0=fytoken, col 1=name, col 9=symbol, col 4=tick, col 5=isin
                raw_symbol = str(row.iloc[9]) if len(row) > 9 else ''
                symbol_name = str(row.iloc[1]) if len(row) > 1 else ''
                fytoken = str(row.iloc[0]) if len(row) > 0 else ''
                tick_size = float(row.iloc[4]) if len(row) > 4 and pd.notna(row.iloc[4]) else 0.05
                isin = str(row.iloc[5]) if len(row) > 5 else ''

                # Only include equity symbols (ending with -EQ)
                if raw_symbol and '-EQ' in raw_symbol:
                    symbol_data = {
                        'fytoken': fytoken,
                        'symbol': raw_symbol,
                        'name': symbol_name,
                        'exchange': exchange_type.split('_')[0],  # NSE or BSE
                        'segment': 'CM',  # Capital Market
                        'instrument_type': 'EQ',  # Equity
                        'lot': 1,  # Standard lot size for equity
                        'tick': tick_size,
                        'isin': isin,
                        'last_updated': ''
                    }
                    symbols.append(symbol_data)

            logger.info(f"Downloaded {len(symbols)} symbols for {exchange_type}")
            return symbols

        except Exception as e:
            logger.error(f"Error downloading symbols for {exchange_type}: {e}")
            return []

    def _is_cache_valid(self, exchange_type: str) -> bool:
        """Check if cache is still valid."""
        if exchange_type not in self._cache_timestamps:
            return False

        cache_time = self._cache_timestamps[exchange_type]
        return datetime.now() - cache_time < self.cache_duration

    def _save_to_disk_cache(self, exchange_type: str, symbols: List[Dict]):
        """Save symbols to disk cache."""
        try:
            cache_file = os.path.join(self.cache_dir, f"{exchange_type}_symbols.json")
            cache_data = {
                'symbols': symbols,
                'timestamp': datetime.now().isoformat(),
                'exchange_type': exchange_type
            }

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Saved {len(symbols)} symbols to disk cache: {cache_file}")

        except Exception as e:
            logger.error(f"Error saving symbols to disk cache: {e}")

    def _load_from_disk_cache(self, exchange_type: str) -> List[Dict]:
        """Load symbols from disk cache."""
        try:
            cache_file = os.path.join(self.cache_dir, f"{exchange_type}_symbols.json")

            if not os.path.exists(cache_file):
                return []

            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            # Check if cache is not too old (7 days max for disk cache)
            cache_time = datetime.fromisoformat(cache_data['timestamp'])
            if datetime.now() - cache_time > timedelta(days=7):
                logger.warning(f"Disk cache for {exchange_type} is too old, ignoring")
                return []

            symbols = cache_data.get('symbols', [])
            logger.info(f"Loaded {len(symbols)} symbols from disk cache for {exchange_type}")
            return symbols

        except Exception as e:
            logger.error(f"Error loading symbols from disk cache: {e}")
            return []

    def sync_symbols_to_database(self, force_refresh: bool = False) -> Dict[str, Dict[str, int]]:
        """Sync symbols from Fyers to database for both NSE and BSE."""
        db_service = self._get_db_service()
        if not db_service:
            logger.warning("Database service not available, cannot sync symbols")
            return {}

        logger.info("Starting symbol sync to database")
        return db_service.sync_all_exchanges(force_refresh=force_refresh)

    def refresh_all_symbols(self, sync_to_database: bool = True):
        """Force refresh of all symbol caches and optionally sync to database."""
        logger.info("Refreshing all symbol caches")

        # Refresh CSV cache first
        for exchange_type in self.symbol_urls.keys():
            self._get_symbols(exchange_type, force_refresh=True)

        # Sync to database if requested
        if sync_to_database:
            self.sync_symbols_to_database(force_refresh=True)


# Global service instance
_fyers_symbol_service = None

def get_fyers_symbol_service() -> FyersSymbolService:
    """Get the global Fyers symbol service instance."""
    global _fyers_symbol_service
    if _fyers_symbol_service is None:
        _fyers_symbol_service = FyersSymbolService()
    return _fyers_symbol_service
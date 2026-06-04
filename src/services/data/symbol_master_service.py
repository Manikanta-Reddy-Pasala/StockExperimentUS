"""SymbolMasterService — US symbol master (replaces the India NSE/BSE Fyers master).

The US universe is defined by static CSVs (src/data/symbols/*.csv) loaded from the
yfinance/IBKR data pipeline, so there is no live exchange symbol-master to fetch.
These methods are no-ops kept for interface parity with the schedulers/services
that used to call the old Fyers symbol service.
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class SymbolMasterService:
    def get_nse_symbols(self, *args, **kwargs) -> List[Dict]:
        return []

    def get_bse_symbols(self, *args, **kwargs) -> List[Dict]:
        return []

    def get_equity_symbols(self, *args, **kwargs) -> List[Dict]:
        return []

    def search_symbols(self, *args, **kwargs) -> List[Dict]:
        return []

    def sync_symbols_to_database(self, *args, **kwargs) -> Dict:
        return {"status": "skipped", "reason": "US uses static CSV universes"}

    def refresh_all_symbols(self, *args, **kwargs):
        logger.info("SymbolMasterService.refresh_all_symbols: no-op (US static CSV universes)")
        return {"status": "skipped"}


_symbol_master_service = None


def get_symbol_master_service() -> SymbolMasterService:
    global _symbol_master_service
    if _symbol_master_service is None:
        _symbol_master_service = SymbolMasterService()
    return _symbol_master_service

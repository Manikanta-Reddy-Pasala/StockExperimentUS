from .ibkr_service import IBKRBrokerService

_ibkr_singleton = None


def get_ibkr_service() -> IBKRBrokerService:
    """Process-wide IBKR service (one TWS/Gateway connection)."""
    global _ibkr_singleton
    if _ibkr_singleton is None:
        _ibkr_singleton = IBKRBrokerService()
    return _ibkr_singleton


__all__ = ["IBKRBrokerService", "get_ibkr_service"]

"""
Portfolio Synchronization Service

Handles efficient syncing of portfolio data (positions and holdings) between Fyers API and cache.
Uses Redis for caching and provides real-time portfolio metrics.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from src.models.database import get_database_manager
from src.models.models import Position, Holding
from src.services.utils.cache_service import get_cache_service
from src.services.core.broker_service import get_broker_service

logger = logging.getLogger(__name__)


class PortfolioSyncService:
    """Service to sync portfolio data between Fyers API and cache efficiently."""

    def __init__(self):
        """Initialize the portfolio sync service."""
        self.db_manager = get_database_manager()
        self.cache_service = get_cache_service()
        self.broker_service = get_broker_service()

        # Cache keys
        self.POSITIONS_CACHE_KEY = "user_positions:{user_id}"
        self.HOLDINGS_CACHE_KEY = "user_holdings:{user_id}"
        self.PORTFOLIO_SUMMARY_KEY = "portfolio_summary:{user_id}"
        self.LAST_SYNC_KEY = "last_portfolio_sync:{user_id}"

        # Cache expiration times
        self.PORTFOLIO_CACHE_TTL = 120  # 2 minutes for positions (more volatile)
        self.HOLDINGS_CACHE_TTL = 300   # 5 minutes for holdings (less volatile)
        self.SYNC_INTERVAL = 30         # 30 seconds minimum between syncs

    def get_portfolio_data(self, user_id: int, force_refresh: bool = False) -> Dict:
        """
        Get complete portfolio data with intelligent caching.

        Args:
            user_id: User ID
            force_refresh: Force refresh from API

        Returns:
            Dict containing positions, holdings, and summary metrics
        """
        try:
            # Check if we should use cached data
            if not force_refresh:
                if self._should_use_cache(user_id):
                    cached_portfolio = self._get_cached_portfolio(user_id)
                    if cached_portfolio is not None:
                        logger.info(f"Returning cached portfolio for user {user_id}")
                        return cached_portfolio
                else:
                    # If cache is slightly stale, return immediately and refresh in background
                    cached_portfolio = self._get_cached_portfolio(user_id)
                    if cached_portfolio is not None:
                        logger.info(f"Returning stale cached portfolio for user {user_id} and refreshing in background")
                        threading.Thread(target=self._background_refresh, args=(user_id,), daemon=True).start()
                        return cached_portfolio

            # Try to get data from database first
            db_portfolio = self._get_db_portfolio(user_id)

            # Sync with Fyers API
            portfolio_data = self._sync_portfolio_from_fyers(user_id, db_portfolio)

            # Cache the results
            self._cache_portfolio(user_id, portfolio_data)

            return portfolio_data

        except Exception as e:
            logger.error(f"Error getting portfolio data: {e}")
            # Try to return cached data as fallback
            cached_portfolio = self._get_cached_portfolio(user_id)
            return cached_portfolio if cached_portfolio is not None else {
                'positions': [],
                'holdings': [],
                'summary': {
                    'total_positions': 0,
                    'portfolio_value': 0.0,
                    'total_pnl': 0.0,
                    'pnl_percentage': 0.0
                }
            }

    def _sync_portfolio_from_fyers(self, user_id: int, db_portfolio: Dict = None) -> Dict:
        """Sync portfolio data from Fyers API."""
        try:
            logger.info(f"Syncing portfolio from Fyers for user {user_id}")

            # Fetch positions and holdings concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_positions = executor.submit(self.broker_service.get_fyers_positions, user_id)
                future_holdings = executor.submit(self.broker_service.get_fyers_holdings, user_id)
                positions_result = future_positions.result()
                holdings_result = future_holdings.result()

            # Parse positions
            positions = self._parse_fyers_positions(positions_result)
            logger.info(f"Parsed {len(positions)} positions for user {user_id}")

            # Parse holdings
            holdings = self._parse_fyers_holdings(holdings_result)
            logger.info(f"Parsed {len(holdings)} holdings for user {user_id}")

            # Update database with new data
            self._update_database(user_id, positions, holdings)

            # Calculate summary metrics
            summary = self._calculate_portfolio_summary(positions, holdings, positions_result, holdings_result)

            # Update sync timestamp
            self._update_last_sync(user_id)

            portfolio_data = {
                'positions': positions,
                'holdings': holdings,
                'summary': summary,
                'last_updated': datetime.utcnow().isoformat()
            }

            logger.info(f"Portfolio sync completed for user {user_id}: {len(positions)} positions, {len(holdings)} holdings")
            return portfolio_data

        except Exception as e:
            logger.error(f"Error syncing portfolio from Fyers: {e}")
            raise

    def _background_refresh(self, user_id: int):
        """Refresh portfolio data in background and update cache, swallowing errors."""
        try:
            db_portfolio = self._get_db_portfolio(user_id)
            portfolio_data = self._sync_portfolio_from_fyers(user_id, db_portfolio)
            self._cache_portfolio(user_id, portfolio_data)
        except Exception as e:
            logger.warning(f"Background refresh failed for user {user_id}: {e}")

    def _parse_fyers_positions(self, positions_result: Dict) -> List[Dict]:
        """Parse Fyers positions API response into standardized format."""
        try:
            if positions_result.get('code') != 200 or positions_result.get('s') != 'ok':
                logger.warning(f"Invalid positions response: {positions_result}")
                return []

            raw_positions = positions_result.get('netPositions', [])
            standardized_positions = []

            for raw_position in raw_positions:
                try:
                    # Extract symbol name (remove NSE: prefix if present)
                    symbol = raw_position.get('symbol', '')
                    if ':' in symbol:
                        symbol = symbol.split(':')[1]
                    if '-EQ' in symbol:
                        symbol = symbol.replace('-EQ', '')

                    standardized_position = {
                        'symbol': symbol,
                        'full_symbol': raw_position.get('symbol', ''),
                        'quantity': int(raw_position.get('netQty', 0)),
                        'avg_price': float(raw_position.get('netAvg', 0)),
                        'last_price': float(raw_position.get('ltp', 0)),
                        'pnl': float(raw_position.get('pl', 0)),
                        'unrealized_pnl': float(raw_position.get('unrealized_profit', 0)),
                        'realized_pnl': float(raw_position.get('realized_profit', 0)),
                        'product_type': raw_position.get('productType', 'CNC'),
                        'side': raw_position.get('side', 1),  # 1 = long, -1 = short
                        'exchange': raw_position.get('exchange', 10),
                        'fy_token': raw_position.get('fyToken', ''),
                        'current_value': float(raw_position.get('netQty', 0)) * float(raw_position.get('ltp', 0)),
                        'investment_value': float(raw_position.get('netQty', 0)) * float(raw_position.get('netAvg', 0)),
                        'pnl_percentage': (float(raw_position.get('pl', 0)) / (float(raw_position.get('netQty', 0)) * float(raw_position.get('netAvg', 0))) * 100) if raw_position.get('netQty', 0) != 0 and raw_position.get('netAvg', 0) != 0 else 0
                    }

                    if standardized_position['quantity'] != 0:  # Only add positions with non-zero quantity
                        standardized_positions.append(standardized_position)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing position {raw_position}: {e}")
                    continue

            return standardized_positions

        except Exception as e:
            logger.error(f"Error parsing Fyers positions: {e}")
            return []

    def _parse_fyers_holdings(self, holdings_result: Dict) -> List[Dict]:
        """Parse Fyers holdings API response into standardized format."""
        try:
            if holdings_result.get('code') != 200 or holdings_result.get('s') != 'ok':
                logger.warning(f"Invalid holdings response: {holdings_result}")
                return []

            raw_holdings = holdings_result.get('holdings', [])
            standardized_holdings = []

            for raw_holding in raw_holdings:
                try:
                    # Extract symbol name (remove NSE: prefix if present)
                    symbol = raw_holding.get('symbol', '')
                    if ':' in symbol:
                        symbol = symbol.split(':')[1]
                    if '-EQ' in symbol:
                        symbol = symbol.replace('-EQ', '')

                    standardized_holding = {
                        'symbol': symbol,
                        'full_symbol': raw_holding.get('symbol', ''),
                        'quantity': int(raw_holding.get('quantity', 0)),
                        'avg_price': float(raw_holding.get('costPrice', 0)),
                        'last_price': float(raw_holding.get('ltp', 0)),
                        'pnl': float(raw_holding.get('pl', 0)),
                        'market_value': float(raw_holding.get('marketVal', 0)),
                        'invested_value': float(raw_holding.get('quantity', 0)) * float(raw_holding.get('costPrice', 0)),
                        'pnl_percentage': float(raw_holding.get('plPerc', 0)),
                        'fy_token': raw_holding.get('fyToken', ''),
                        'exchange': raw_holding.get('ex', ''),
                        'holding_type': 'T1'  # Default to T1 for holdings
                    }

                    if standardized_holding['quantity'] > 0:  # Only add holdings with positive quantity
                        standardized_holdings.append(standardized_holding)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing holding {raw_holding}: {e}")
                    continue

            return standardized_holdings

        except Exception as e:
            logger.error(f"Error parsing Fyers holdings: {e}")
            return []

    def _calculate_portfolio_summary(self, positions: List[Dict], holdings: List[Dict],
                                   positions_result: Dict, holdings_result: Dict) -> Dict:
        """Calculate portfolio summary metrics."""
        try:
            # Get overall data from API responses if available
            positions_overall = positions_result.get('overall', {})
            holdings_overall = holdings_result.get('overall', {})

            # Calculate from positions
            total_positions = len(positions)
            positions_value = sum(pos.get('current_value', 0) for pos in positions)
            positions_pnl = sum(pos.get('pnl', 0) for pos in positions)

            # Calculate from holdings
            total_holdings = len(holdings)
            holdings_value = sum(holding.get('market_value', 0) for holding in holdings)
            holdings_pnl = sum(holding.get('pnl', 0) for holding in holdings)

            # Combined totals
            total_portfolio_value = positions_value + holdings_value
            total_pnl = positions_pnl + holdings_pnl
            total_investment = sum(pos.get('investment_value', 0) for pos in positions) + \
                             sum(holding.get('invested_value', 0) for holding in holdings)

            # Calculate percentage
            pnl_percentage = (total_pnl / total_investment * 100) if total_investment > 0 else 0

            return {
                'total_positions': total_positions + total_holdings,
                'active_positions': total_positions,
                'total_holdings': total_holdings,
                'portfolio_value': round(total_portfolio_value, 2),
                'total_pnl': round(total_pnl, 2),
                'pnl_percentage': round(pnl_percentage, 2),
                'total_investment': round(total_investment, 2),
                'positions_value': round(positions_value, 2),
                'holdings_value': round(holdings_value, 2),
                'positions_pnl': round(positions_pnl, 2),
                'holdings_pnl': round(holdings_pnl, 2),
                'unrealized_pnl': sum(pos.get('unrealized_pnl', 0) for pos in positions),
                'realized_pnl': sum(pos.get('realized_pnl', 0) for pos in positions)
            }

        except Exception as e:
            logger.error(f"Error calculating portfolio summary: {e}")
            return {
                'total_positions': 0,
                'portfolio_value': 0.0,
                'total_pnl': 0.0,
                'pnl_percentage': 0.0
            }

    def _should_use_cache(self, user_id: int) -> bool:
        """Check if we should use cached data or refresh from API."""
        try:
            last_sync_str = self.cache_service.get(self.LAST_SYNC_KEY.format(user_id=user_id))
            if not last_sync_str:
                return False

            last_sync = datetime.fromisoformat(last_sync_str)
            time_since_sync = datetime.utcnow() - last_sync

            # Use cache if last sync was within interval
            return time_since_sync.total_seconds() < self.SYNC_INTERVAL

        except Exception as e:
            logger.warning(f"Error checking cache validity: {e}")
            return False

    def _get_cached_portfolio(self, user_id: int) -> Optional[Dict]:
        """Get portfolio data from cache."""
        try:
            cache_key = self.PORTFOLIO_SUMMARY_KEY.format(user_id=user_id)
            cached_data = self.cache_service.get(cache_key)

            if cached_data:
                return json.loads(cached_data)
            return None

        except Exception as e:
            logger.warning(f"Error getting cached portfolio: {e}")
            return None

    def _cache_portfolio(self, user_id: int, portfolio_data: Dict):
        """Cache portfolio data in Redis."""
        try:
            cache_key = self.PORTFOLIO_SUMMARY_KEY.format(user_id=user_id)
            self.cache_service.set(
                cache_key,
                json.dumps(portfolio_data, default=str),
                expire_seconds=self.PORTFOLIO_CACHE_TTL
            )

        except Exception as e:
            logger.warning(f"Error caching portfolio: {e}")

    def _update_last_sync(self, user_id: int):
        """Update last sync timestamp."""
        try:
            sync_key = self.LAST_SYNC_KEY.format(user_id=user_id)
            self.cache_service.set(
                sync_key,
                datetime.utcnow().isoformat(),
                expire_seconds=self.PORTFOLIO_CACHE_TTL * 2  # Keep sync time longer than cache
            )

        except Exception as e:
            logger.warning(f"Error updating last sync time: {e}")

    def clear_user_cache(self, user_id: int):
        """Clear cached data for a user (useful for testing or manual refresh)."""
        try:
            keys_to_clear = [
                self.POSITIONS_CACHE_KEY.format(user_id=user_id),
                self.HOLDINGS_CACHE_KEY.format(user_id=user_id),
                self.PORTFOLIO_SUMMARY_KEY.format(user_id=user_id),
                self.LAST_SYNC_KEY.format(user_id=user_id)
            ]

            for key in keys_to_clear:
                self.cache_service.delete(key)

            logger.info(f"Cleared portfolio cache for user {user_id}")

        except Exception as e:
            logger.warning(f"Error clearing portfolio cache for user {user_id}: {e}")

    def _get_db_portfolio(self, user_id: int) -> Dict:
        """Get portfolio data from database."""
        try:
            with self.db_manager.get_session() as session:
                # Get positions
                positions = session.query(Position).filter(
                    Position.user_id == user_id
                ).all()

                # Get holdings
                holdings = session.query(Holding).filter(
                    Holding.user_id == user_id
                ).all()

                return {
                    'positions': [self._db_position_to_dict(pos) for pos in positions],
                    'holdings': [self._db_holding_to_dict(hold) for hold in holdings]
                }

        except Exception as e:
            logger.error(f"Error getting portfolio from database: {e}")
            return {'positions': [], 'holdings': []}

    def _update_database(self, user_id: int, positions: List[Dict], holdings: List[Dict]):
        """Update database with new position and holding data."""
        try:
            with self.db_manager.get_session() as session:
                # Clear existing positions and holdings for user
                session.query(Position).filter(Position.user_id == user_id).delete()
                session.query(Holding).filter(Holding.user_id == user_id).delete()

                # Insert new positions
                for position_data in positions:
                    db_position = self._create_db_position(user_id, position_data)
                    session.add(db_position)

                # Insert new holdings
                for holding_data in holdings:
                    db_holding = self._create_db_holding(user_id, holding_data)
                    session.add(db_holding)

                session.commit()
                logger.info(f"Updated database with {len(positions)} positions and {len(holdings)} holdings for user {user_id}")

        except Exception as e:
            logger.error(f"Error updating database: {e}")
            raise

    def _create_db_position(self, user_id: int, position_data: Dict):
        """Create database position from standardized position data."""
        return Position(
            user_id=user_id,
            tradingsymbol=position_data['symbol'],
            exchange=position_data.get('exchange', ''),
            instrument_token=position_data.get('fy_token', ''),
            product=position_data.get('product_type', 'CNC'),
            quantity=position_data['quantity'],
            average_price=position_data['avg_price'],
            last_price=position_data['last_price'],
            value=position_data['current_value'],
            pnl=position_data['pnl'],
            unrealised=position_data.get('unrealized_pnl', 0),
            realised=position_data.get('realized_pnl', 0),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _create_db_holding(self, user_id: int, holding_data: Dict):
        """Create database holding from standardized holding data."""
        return Holding(
            user_id=user_id,
            tradingsymbol=holding_data['symbol'],
            exchange=holding_data.get('exchange', ''),
            instrument_token=holding_data.get('fy_token', ''),
            quantity=holding_data['quantity'],
            average_price=holding_data['avg_price'],
            last_price=holding_data['last_price'],
            market_value=holding_data['market_value'],
            invested_value=holding_data['invested_value'],
            pnl=holding_data['pnl'],
            pnl_percentage=holding_data['pnl_percentage'],
            holding_type=holding_data.get('holding_type', 'T1'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    def _db_position_to_dict(self, position) -> Dict:
        """Convert database Position object to dictionary."""
        return {
            'symbol': position.tradingsymbol,
            'quantity': position.quantity or 0,
            'avg_price': position.average_price or 0,
            'last_price': position.last_price or 0,
            'pnl': position.pnl or 0,
            'current_value': position.value or 0,
            'investment_value': (position.quantity or 0) * (position.average_price or 0),
            'pnl_percentage': ((position.pnl or 0) / ((position.quantity or 1) * (position.average_price or 1)) * 100) if position.quantity and position.average_price else 0,
            'type': 'position'
        }

    def _db_holding_to_dict(self, holding) -> Dict:
        """Convert database Holding object to dictionary."""
        return {
            'symbol': holding.tradingsymbol,
            'quantity': holding.quantity or 0,
            'avg_price': holding.average_price or 0,
            'last_price': holding.last_price or 0,
            'pnl': holding.pnl or 0,
            'market_value': holding.market_value or 0,
            'invested_value': holding.invested_value or 0,
            'pnl_percentage': holding.pnl_percentage or 0,
            'type': 'holding'
        }


# Singleton pattern for service
_portfolio_sync_service = None

def get_portfolio_sync_service() -> PortfolioSyncService:
    """Get the portfolio sync service singleton."""
    global _portfolio_sync_service
    if _portfolio_sync_service is None:
        _portfolio_sync_service = PortfolioSyncService()
    return _portfolio_sync_service
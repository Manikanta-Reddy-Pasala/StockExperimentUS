"""
Symbol Database Service

Manages symbol master data in PostgreSQL with daily scheduled updates.
Syncs data from FyersSymbolService to database for better performance and consistency.
"""

import logging
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

try:
    from src.models.stock_models import SymbolMaster, Stock, MarketCapCategory
    from src.models.database import get_database_manager
    from .symbol_master_service import get_symbol_master_service
except ImportError:
    from models.stock_models import SymbolMaster, Stock, MarketCapCategory
    from models.database import get_database_manager
    from .symbol_master_service import get_symbol_master_service


class SymbolDatabaseService:
    """Service to manage symbol data in PostgreSQL database."""

    def __init__(self):
        self.db_manager = get_database_manager()
        self.symbol_service = get_symbol_master_service()

    def sync_symbols_to_database(self, exchange: str = 'NSE', force_refresh: bool = False) -> Dict[str, int]:
        """
        Sync symbol master data from Fyers to database.
        Returns count of added, updated, deactivated symbols.
        """
        try:
            logger.info(f"Starting symbol sync for {exchange} exchange")

            # Get fresh symbols from Fyers
            if exchange.upper() == 'NSE':
                symbols = self.symbol_service.get_nse_symbols(force_refresh=force_refresh)
            elif exchange.upper() == 'BSE':
                symbols = self.symbol_service.get_bse_symbols(force_refresh=force_refresh)
            else:
                logger.error(f"Unsupported exchange: {exchange}")
                return {'added': 0, 'updated': 0, 'deactivated': 0, 'errors': 1}

            if not symbols:
                logger.warning(f"No symbols received from Fyers for {exchange}")
                return {'added': 0, 'updated': 0, 'deactivated': 0, 'errors': 1}

            with self.db_manager.get_session() as session:
                # Get ALL existing symbols (active + inactive) — fytoken is the PK,
                # so we MUST consider inactive rows too or INSERT will UniqueViolation
                # when a previously-deactivated symbol relists.
                existing_symbols = {}
                db_symbols = session.query(SymbolMaster).filter(
                    SymbolMaster.exchange == exchange.upper()
                ).all()

                for db_symbol in db_symbols:
                    existing_symbols[db_symbol.fytoken] = db_symbol

                # Track statistics
                stats = {'added': 0, 'updated': 0, 'deactivated': 0, 'reactivated': 0, 'errors': 0}
                active_tokens = set()

                # Process each symbol from Fyers
                for symbol_data in symbols:
                    try:
                        fytoken = symbol_data.get('fytoken', '')
                        if not fytoken:
                            stats['errors'] += 1
                            continue

                        active_tokens.add(fytoken)

                        if fytoken in existing_symbols:
                            db_symbol = existing_symbols[fytoken]
                            was_inactive = not db_symbol.is_active
                            updated = self._update_symbol_record(db_symbol, symbol_data)
                            if was_inactive:
                                db_symbol.is_active = True
                                db_symbol.updated_at = datetime.utcnow()
                                stats['reactivated'] += 1
                            elif updated:
                                stats['updated'] += 1
                        else:
                            # Add new symbol
                            new_symbol = self._create_symbol_record(symbol_data)
                            if new_symbol:
                                session.add(new_symbol)
                                stats['added'] += 1

                    except Exception as e:
                        logger.error(f"Error processing symbol {symbol_data.get('symbol', 'unknown')}: {e}")
                        stats['errors'] += 1
                        continue

                # Deactivate symbols not in current Fyers data (skip already-inactive)
                for fytoken, db_symbol in existing_symbols.items():
                    if fytoken not in active_tokens and db_symbol.is_active:
                        db_symbol.is_active = False
                        db_symbol.updated_at = datetime.utcnow()
                        stats['deactivated'] += 1

                # Commit all changes
                session.commit()

                logger.info(f"Symbol sync completed for {exchange}: {stats}")
                return stats

        except Exception as e:
            logger.error(f"Error syncing symbols to database: {e}")
            return {'added': 0, 'updated': 0, 'deactivated': 0, 'errors': 1}

    def _create_symbol_record(self, symbol_data: Dict) -> Optional[SymbolMaster]:
        """Create new SymbolMaster record from Fyers data."""
        try:
            return SymbolMaster(
                symbol=symbol_data.get('symbol', ''),
                fytoken=symbol_data.get('fytoken', ''),
                name=symbol_data.get('name', ''),
                exchange=symbol_data.get('exchange', 'NSE'),
                segment=symbol_data.get('segment', 'CM'),
                instrument_type=symbol_data.get('instrument_type', 'EQ'),
                lot_size=symbol_data.get('lot', 1),
                tick_size=symbol_data.get('tick', 0.05),
                isin=symbol_data.get('isin', ''),
                data_source='fyers',
                source_updated=symbol_data.get('last_updated', ''),
                download_date=datetime.utcnow(),
                is_active=True,
                is_equity=True
            )
        except Exception as e:
            logger.error(f"Error creating symbol record: {e}")
            return None

    def _update_symbol_record(self, db_symbol: SymbolMaster, symbol_data: Dict) -> bool:
        """Update existing SymbolMaster record. Returns True if updated."""
        try:
            updated = False

            # Check if any field needs updating
            if db_symbol.name != symbol_data.get('name', ''):
                db_symbol.name = symbol_data.get('name', '')
                updated = True

            if db_symbol.lot_size != symbol_data.get('lot', 1):
                db_symbol.lot_size = symbol_data.get('lot', 1)
                updated = True

            if db_symbol.tick_size != symbol_data.get('tick', 0.05):
                db_symbol.tick_size = symbol_data.get('tick', 0.05)
                updated = True

            if db_symbol.source_updated != symbol_data.get('last_updated', ''):
                db_symbol.source_updated = symbol_data.get('last_updated', '')
                updated = True

            if updated:
                db_symbol.updated_at = datetime.utcnow()

            return updated

        except Exception as e:
            logger.error(f"Error updating symbol record: {e}")
            return False

    def get_symbols_from_database(self, exchange: str = 'NSE', limit: int = None) -> List[Dict]:
        """Get symbols from database instead of Fyers API."""
        try:
            with self.db_manager.get_session() as session:
                query = session.query(SymbolMaster).filter(
                    SymbolMaster.exchange == exchange.upper(),
                    SymbolMaster.is_active == True,
                    SymbolMaster.is_equity == True
                ).order_by(SymbolMaster.name)

                if limit:
                    query = query.limit(limit)

                db_symbols = query.all()

                # Convert to dictionary format compatible with existing code
                symbols = []
                for db_symbol in db_symbols:
                    symbol_dict = {
                        'fytoken': db_symbol.fytoken,
                        'symbol': db_symbol.symbol,
                        'name': db_symbol.name,
                        'exchange': db_symbol.exchange,
                        'segment': db_symbol.segment,
                        'instrument_type': db_symbol.instrument_type,
                        'lot': db_symbol.lot_size,
                        'tick': db_symbol.tick_size,
                        'isin': db_symbol.isin or '',
                        'last_updated': db_symbol.source_updated or ''
                    }
                    symbols.append(symbol_dict)

                logger.info(f"Retrieved {len(symbols)} symbols from database for {exchange}")
                return symbols


        except Exception as e:
            logger.error(f"Error getting symbols from database: {e}")
            return []

    def search_symbols_in_database(self, query: str, exchange: str = 'NSE', limit: int = 100) -> List[Dict]:
        """Search symbols in database using SQL LIKE queries."""
        try:
            with self.db_manager.get_session() as session:
                # Create case-insensitive search
                search_pattern = f"%{query.upper()}%"

                db_query = session.query(SymbolMaster).filter(
                    SymbolMaster.exchange == exchange.upper(),
                    SymbolMaster.is_active == True,
                    SymbolMaster.is_equity == True,
                    or_(
                        SymbolMaster.symbol.ilike(search_pattern),
                        SymbolMaster.name.ilike(search_pattern)
                    )
                ).order_by(SymbolMaster.name).limit(limit)

                db_symbols = db_query.all()

                # Convert to dictionary format
                symbols = []
                for db_symbol in db_symbols:
                    symbol_dict = {
                        'fytoken': db_symbol.fytoken,
                        'symbol': db_symbol.symbol,
                        'name': db_symbol.name,
                        'exchange': db_symbol.exchange,
                        'segment': db_symbol.segment,
                        'instrument_type': db_symbol.instrument_type,
                        'lot': db_symbol.lot_size,
                        'tick': db_symbol.tick_size,
                        'isin': db_symbol.isin or '',
                        'last_updated': db_symbol.source_updated or ''
                    }
                    symbols.append(symbol_dict)

                logger.info(f"Found {len(symbols)} symbols matching '{query}' in database")
                return symbols


        except Exception as e:
            logger.error(f"Error searching symbols in database: {e}")
            return []

    def get_database_stats(self) -> Dict[str, int]:
        """Get statistics about symbols in database."""
        try:
            with self.db_manager.get_session() as session:
                stats = {}

                # Total symbols
                stats['total_symbols'] = session.query(SymbolMaster).count()

                # Active symbols
                stats['active_symbols'] = session.query(SymbolMaster).filter(
                    SymbolMaster.is_active == True
                ).count()

                # By exchange
                stats['nse_symbols'] = session.query(SymbolMaster).filter(
                    SymbolMaster.exchange == 'NSE',
                    SymbolMaster.is_active == True
                ).count()

                stats['bse_symbols'] = session.query(SymbolMaster).filter(
                    SymbolMaster.exchange == 'BSE',
                    SymbolMaster.is_active == True
                ).count()

                # Last update
                last_updated = session.query(SymbolMaster.updated_at).order_by(
                    SymbolMaster.updated_at.desc()
                ).first()

                if last_updated:
                    stats['last_updated'] = last_updated[0].isoformat()
                else:
                    stats['last_updated'] = None

                return stats


        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}

    def sync_all_exchanges(self, force_refresh: bool = False) -> Dict[str, Dict[str, int]]:
        """Sync symbols for all supported exchanges."""
        results = {}

        for exchange in ['NSE', 'BSE']:
            try:
                result = self.sync_symbols_to_database(exchange, force_refresh)
                results[exchange] = result
                # Add delay between exchanges to avoid rate limiting
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error syncing {exchange}: {e}")
                results[exchange] = {'added': 0, 'updated': 0, 'deactivated': 0, 'errors': 1}

        return results

    def cleanup_old_symbols(self, days_old: int = 90) -> int:
        """Remove symbols that have been inactive for specified days."""
        try:
            with self.db_manager.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days_old)

                # Delete symbols that have been inactive for too long
                deleted_count = session.query(SymbolMaster).filter(
                    SymbolMaster.is_active == False,
                    SymbolMaster.updated_at < cutoff_date
                ).delete()

                session.commit()

                logger.info(f"Cleaned up {deleted_count} old symbols")
                return deleted_count

        except Exception as e:
            logger.error(f"Error in cleanup_old_symbols: {e}")
            return 0


# Global service instance
_symbol_database_service = None

def get_symbol_database_service() -> SymbolDatabaseService:
    """Get the global symbol database service instance."""
    global _symbol_database_service
    if _symbol_database_service is None:
        _symbol_database_service = SymbolDatabaseService()
    return _symbol_database_service
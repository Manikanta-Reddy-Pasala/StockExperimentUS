"""
Enhanced FYERS Portfolio Provider Implementation

Implements comprehensive portfolio management with search and sort capabilities.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from ..interfaces.portfolio_interface import IPortfolioProvider, Holding, Position
from ..brokers.fyers_service import get_fyers_service

logger = logging.getLogger(__name__)


class FyersPortfolioProvider(IPortfolioProvider):
    """Enhanced FYERS implementation of portfolio provider with search and sort."""
    
    def __init__(self):
        self.fyers_service = get_fyers_service()
    
    def holdings(self, user_id: int, search: str = None, sort_by: str = None,
                sort_order: str = 'desc', filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get current holdings - alias for get_holdings."""
        return self.get_holdings(user_id, search, sort_by, sort_order, filters)
    
    def get_holdings(self, user_id: int, search: str = None, sort_by: str = None,
                    sort_order: str = 'desc', filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get current holdings with advanced search, sort, and filter capabilities."""
        try:
            holdings_response = self.fyers_service.holdings(user_id)
            
            if holdings_response.get('s') != 'ok' or holdings_response.get('code') != 200:
                return {
                    'success': False,
                    'error': holdings_response.get('message', 'Failed to fetch holdings'),
                    'data': [],
                    'total_value': 0,
                    'total_pnl': 0,
                    'search': search,
                    'sort_by': sort_by,
                    'sort_order': sort_order,
                    'last_updated': datetime.now().isoformat()
                }
            
            holdings_data = holdings_response.get('holdings', [])
            
            # Apply additional filters if provided
            if filters:
                holdings_data = self._apply_holdings_filters(holdings_data, filters)
            
            # Calculate totals
            total_value = sum(holding.get('market_value', 0) for holding in holdings_data)
            total_pnl = sum(holding.get('pnl', 0) for holding in holdings_data)
            total_investment = sum(holding.get('quantity', 0) * holding.get('avg_price', 0) for holding in holdings_data)
            
            # Add percentage allocations
            for holding in holdings_data:
                holding['allocation_percent'] = round(
                    (holding.get('market_value', 0) / total_value * 100) if total_value > 0 else 0, 2
                )
            
            # Get sector-wise allocation
            sector_allocation = self._calculate_sector_allocation(holdings_data)
            
            return {
                'success': True,
                'data': holdings_data,
                'total_value': round(total_value, 2),
                'total_pnl': round(total_pnl, 2),
                'total_pnl_percent': round((total_pnl / total_investment * 100) if total_investment > 0 else 0, 2),
                'total_investment': round(total_investment, 2),
                'holdings_count': len(holdings_data),
                'sector_allocation': sector_allocation,
                'search': search,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'filters_applied': filters,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching holdings for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total_value': 0,
                'total_pnl': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def get_positions(self, user_id: int, search: str = None, sort_by: str = None,
                     sort_order: str = 'desc', filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get current positions with advanced search, sort, and filter capabilities."""
        try:
            positions_response = self.fyers_service.positions(user_id)
            
            if positions_response.get('s') != 'ok' or positions_response.get('code') != 200:
                return {
                    'success': False,
                    'error': positions_response.get('message', 'Failed to fetch positions'),
                    'data': [],
                    'total_value': 0,
                    'total_pnl': 0,
                    'search': search,
                    'sort_by': sort_by,
                    'sort_order': sort_order,
                    'last_updated': datetime.now().isoformat()
                }
            
            positions_data = positions_response.get('netPositions', [])
            
            # Apply additional filters if provided
            if filters:
                positions_data = self._apply_positions_filters(positions_data, filters)
            
            # Calculate totals and metrics
            total_pnl = sum(pos.get('pnl', 0) for pos in positions_data)
            total_day_change = sum(pos.get('day_change', 0) for pos in positions_data)
            long_positions = [pos for pos in positions_data if pos.get('side') == 1 and pos.get('quantity', 0) > 0]
            short_positions = [pos for pos in positions_data if pos.get('side') == -1 or pos.get('quantity', 0) < 0]
            
            # Add position analysis
            position_analysis = {
                'total_positions': len(positions_data),
                'long_positions': len(long_positions),
                'short_positions': len(short_positions),
                'profitable_positions': len([pos for pos in positions_data if pos.get('pnl', 0) > 0]),
                'losing_positions': len([pos for pos in positions_data if pos.get('pnl', 0) < 0]),
                'largest_gain': max([pos.get('pnl', 0) for pos in positions_data]) if positions_data else 0,
                'largest_loss': min([pos.get('pnl', 0) for pos in positions_data]) if positions_data else 0
            }
            
            return {
                'success': True,
                'data': positions_data,
                'total_pnl': round(total_pnl, 2),
                'total_day_change': round(total_day_change, 2),
                'position_analysis': position_analysis,
                'search': search,
                'sort_by': sort_by,
                'sort_order': sort_order,
                'filters_applied': filters,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching positions for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total_pnl': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def get_portfolio_summary(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive portfolio summary."""
        try:
            # Get data from individual API endpoints
            logger.info(f"Getting portfolio summary for user {user_id}")
            holdings_response = self.fyers_service.holdings(user_id)
            positions_response = self.fyers_service.positions(user_id)
            funds_response = self.fyers_service.funds(user_id)

            # Initialize default values
            holdings = []
            positions = []
            funds = []

            # Process holdings
            if holdings_response.get('s') == 'ok' and holdings_response.get('code') == 200:
                holdings = holdings_response.get('holdings', [])

            # Process positions
            if positions_response.get('s') == 'ok' and positions_response.get('code') == 200:
                positions = positions_response.get('netPositions', [])

            # Process funds
            if funds_response.get('s') == 'ok' and funds_response.get('code') == 200:
                funds = funds_response.get('fund_limit', [])
            
            # Calculate summary metrics
            total_portfolio_value = sum(h.get('market_value', 0) for h in holdings) + sum(p.get('ltp', 0) * abs(p.get('netQty', 0)) for p in positions)
            total_pnl = sum(h.get('pnl', 0) for h in holdings) + sum(p.get('unrealized_profit', 0) for p in positions)

            # Enhanced summary with additional metrics
            enhanced_summary = {
                'holdings': holdings,
                'positions': positions,
                'funds': funds,
                'total_portfolio_value': total_portfolio_value,
                'total_pnl': total_pnl,
                'holdings_count': len(holdings),
                'positions_count': len(positions),
                'portfolio_diversity': self._calculate_portfolio_diversity(holdings),
                'risk_metrics': self._calculate_risk_metrics(holdings, positions),
                'performance_metrics': self._calculate_performance_metrics(holdings, positions),
                'asset_allocation': self._calculate_asset_allocation(holdings, positions),
                'top_holdings': sorted(holdings, key=lambda x: x.get('market_value', 0), reverse=True)[:5]
            }
            
            return {
                'success': True,
                'data': enhanced_summary,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching portfolio summary for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {},
                'last_updated': datetime.now().isoformat()
            }
    
    def get_portfolio_allocation(self, user_id: int, allocation_type: str = 'sector') -> Dict[str, Any]:
        """Get portfolio allocation breakdown by sector, market cap, or asset class."""
        try:
            holdings_response = self.holdings(user_id)
            
            if not holdings_response.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to fetch holdings for allocation analysis',
                    'data': [],
                    'last_updated': datetime.now().isoformat()
                }
            
            holdings = holdings_response.get('data', [])
            total_value = holdings_response.get('total_value', 0)
            
            if allocation_type == 'sector':
                allocation = self._calculate_sector_allocation(holdings, total_value)
            elif allocation_type == 'market_cap':
                allocation = self._calculate_market_cap_allocation(holdings, total_value)
            elif allocation_type == 'asset_class':
                allocation = self._calculate_asset_class_allocation(holdings, total_value)
            else:
                allocation = self._calculate_sector_allocation(holdings, total_value)  # Default
            
            return {
                'success': True,
                'data': allocation,
                'allocation_type': allocation_type,
                'total_portfolio_value': total_value,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio allocation for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'last_updated': datetime.now().isoformat()
            }
    
    def get_portfolio_performance(self, user_id: int, period: str = '1M') -> Dict[str, Any]:
        """Get portfolio performance metrics for specified period."""
        try:
            # Get current portfolio data
            portfolio_summary = self.get_portfolio_summary(user_id)
            
            if not portfolio_summary.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to fetch portfolio data for performance analysis',
                    'data': {},
                    'last_updated': datetime.now().isoformat()
                }
            
            summary_data = portfolio_summary.get('data', {})
            
            # Calculate period-specific performance
            period_performance = self._calculate_period_performance(user_id, period, summary_data)
            
            # Get benchmark comparison
            benchmark_comparison = self._get_benchmark_comparison(user_id, period)
            
            performance_data = {
                'period': period,
                'portfolio_return': period_performance.get('return_percent', 0),
                'portfolio_value': summary_data.get('total_portfolio_value', 0),
                'total_pnl': summary_data.get('total_pnl', 0),
                'best_performing_stock': period_performance.get('best_performer'),
                'worst_performing_stock': period_performance.get('worst_performer'),
                'volatility': period_performance.get('volatility', 0),
                'sharpe_ratio': period_performance.get('sharpe_ratio', 0),
                'max_drawdown': period_performance.get('max_drawdown', 0),
                'win_rate': period_performance.get('win_rate', 0),
                'benchmark_comparison': benchmark_comparison,
                'risk_adjusted_return': period_performance.get('risk_adjusted_return', 0)
            }
            
            return {
                'success': True,
                'data': performance_data,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio performance for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {},
                'last_updated': datetime.now().isoformat()
            }

    def _calculate_performance_metrics(self, holdings: List[Dict], positions: List[Dict]) -> Dict[str, Any]:
        """Compute basic performance metrics from current holdings/positions."""
        try:
            total_value = sum(h.get('market_value', 0) for h in holdings)
            total_pnl = sum(h.get('pnl', 0) for h in holdings) + sum(p.get('pnl', 0) for p in positions)
            day_change = sum(p.get('day_change', 0) for p in positions)

            return {
                'total_value': round(total_value, 2),
                'total_pnl': round(total_pnl, 2),
                'total_pnl_percent': round((total_pnl / total_value * 100) if total_value > 0 else 0, 2),
                'day_change': round(day_change, 2)
            }
        except Exception as e:
            logger.warning(f"Error calculating performance metrics: {e}")
            return {
                'total_value': 0,
                'total_pnl': 0,
                'total_pnl_percent': 0,
                'day_change': 0
            }
    
    def get_dividend_history(self, user_id: int, start_date: datetime = None, 
                           end_date: datetime = None) -> Dict[str, Any]:
        """Get dividend history for portfolio holdings."""
        try:
            # Note: FYERS API doesn't provide dividend history directly
            # This would need to be implemented using external data sources
            # For now, providing a placeholder structure
            
            holdings_response = self.holdings(user_id)
            
            if not holdings_response.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to fetch holdings for dividend analysis',
                    'data': [],
                    'total_dividends': 0,
                    'last_updated': datetime.now().isoformat()
                }
            
            # No dividend data available - requires external data source
            dividend_records = []
            total_dividends = 0

            return {
                'success': True,
                'data': dividend_records,
                'total_dividends': round(total_dividends, 2),
                'period': {
                    'start_date': start_date.strftime('%Y-%m-%d') if start_date else None,
                    'end_date': end_date.strftime('%Y-%m-%d') if end_date else None
                },
                'note': 'Dividend data not available. Requires external data source.',
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching dividend history for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'total_dividends': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def get_portfolio_risk_metrics(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive portfolio risk analysis."""
        try:
            holdings_response = self.holdings(user_id)
            positions_response = self.positions(user_id)
            
            if not holdings_response.get('success'):
                return {
                    'success': False,
                    'error': 'Failed to fetch portfolio data for risk analysis',
                    'data': {},
                    'last_updated': datetime.now().isoformat()
                }
            
            holdings = holdings_response.get('data', [])
            positions = positions_response.get('data', []) if positions_response.get('success') else []
            
            # Calculate various risk metrics
            risk_metrics = {
                'portfolio_beta': self._calculate_portfolio_beta(holdings),
                'value_at_risk': self._calculate_var(holdings, positions),
                'concentration_risk': self._calculate_concentration_risk(holdings),
                'sector_risk': self._calculate_sector_risk(holdings),
                'correlation_risk': self._calculate_correlation_risk(holdings),
                'leverage_ratio': self._calculate_leverage_ratio(holdings, positions),
                'max_position_size': max([h.get('allocation_percent', 0) for h in holdings]) if holdings else 0,
                'diversification_ratio': self._calculate_diversification_ratio(holdings),
                'risk_rating': self._calculate_overall_risk_rating(holdings, positions)
            }
            
            # Risk recommendations
            risk_recommendations = self._generate_risk_recommendations(risk_metrics, holdings)
            
            return {
                'success': True,
                'data': {
                    **risk_metrics,
                    'recommendations': risk_recommendations,
                    'risk_summary': self._generate_risk_summary(risk_metrics)
                },
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio risk metrics for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': {},
                'last_updated': datetime.now().isoformat()
            }
    
    # Helper Methods for Portfolio Analysis
    
    def _apply_holdings_filters(self, holdings: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Apply additional filters to holdings data."""
        if not filters:
            return holdings
        
        filtered_holdings = []
        for holding in holdings:
            # PnL filter
            if 'min_pnl' in filters and holding.get('pnl', 0) < filters['min_pnl']:
                continue
            if 'max_pnl' in filters and holding.get('pnl', 0) > filters['max_pnl']:
                continue
            
            # Value filter
            if 'min_value' in filters and holding.get('market_value', 0) < filters['min_value']:
                continue
            if 'max_value' in filters and holding.get('market_value', 0) > filters['max_value']:
                continue
            
            # Sector filter
            if 'sector' in filters and filters['sector']:
                holding_sector = self.fyers_service._get_sector_for_symbol(holding.get('symbol', ''))
                if holding_sector.lower() != filters['sector'].lower():
                    continue
            
            # Exchange filter
            if 'exchange' in filters and filters['exchange']:
                if filters['exchange'].upper() not in holding.get('exchange', '').upper():
                    continue
            
            filtered_holdings.append(holding)
        
        return filtered_holdings
    
    def _apply_positions_filters(self, positions: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """Apply additional filters to positions data."""
        if not filters:
            return positions
        
        filtered_positions = []
        for position in positions:
            # Side filter (long/short)
            if 'side' in filters and filters['side']:
                if filters['side'].lower() == 'long' and position.get('side') != 1:
                    continue
                if filters['side'].lower() == 'short' and position.get('side') != -1:
                    continue
            
            # Product type filter
            if 'product_type' in filters and filters['product_type']:
                if position.get('product_type', '').lower() != filters['product_type'].lower():
                    continue
            
            # PnL filter
            if 'profitable_only' in filters and filters['profitable_only']:
                if position.get('pnl', 0) <= 0:
                    continue
            
            filtered_positions.append(position)
        
        return filtered_positions
    
    def _calculate_sector_allocation(self, holdings: List[Dict], total_value: float = None) -> List[Dict]:
        """Calculate sector-wise allocation of portfolio."""
        if not total_value:
            total_value = sum(holding.get('market_value', 0) for holding in holdings)
        
        sector_allocation = {}
        
        for holding in holdings:
            sector = self.fyers_service._get_sector_for_symbol(holding.get('symbol', ''))
            value = holding.get('market_value', 0)
            
            if sector not in sector_allocation:
                sector_allocation[sector] = {
                    'sector': sector,
                    'value': 0,
                    'percentage': 0,
                    'stocks': []
                }
            
            sector_allocation[sector]['value'] += value
            sector_allocation[sector]['stocks'].append({
                'symbol': holding.get('symbol', ''),
                'symbol_name': holding.get('symbol_name', ''),
                'value': value
            })
        
        # Calculate percentages and sort
        allocation_list = []
        for sector_data in sector_allocation.values():
            sector_data['percentage'] = round((sector_data['value'] / total_value * 100) if total_value > 0 else 0, 2)
            sector_data['value'] = round(sector_data['value'], 2)
            allocation_list.append(sector_data)
        
        return sorted(allocation_list, key=lambda x: x['value'], reverse=True)
    
    def _calculate_market_cap_allocation(self, holdings: List[Dict], total_value: float) -> List[Dict]:
        """Calculate market cap-wise allocation of portfolio."""
        cap_allocation = {'Large Cap': 0, 'Mid Cap': 0, 'Small Cap': 0}
        
        for holding in holdings:
            price = holding.get('current_price', 0)
            value = holding.get('market_value', 0)
            cap_category = self.fyers_service._get_market_cap_category(price)
            cap_allocation[cap_category] += value
        
        allocation_list = []
        for cap, value in cap_allocation.items():
            allocation_list.append({
                'category': cap,
                'value': round(value, 2),
                'percentage': round((value / total_value * 100) if total_value > 0 else 0, 2)
            })
        
        return sorted(allocation_list, key=lambda x: x['value'], reverse=True)
    
    def _calculate_asset_class_allocation(self, holdings: List[Dict], total_value: float) -> List[Dict]:
        """Calculate asset class allocation (equity, derivatives, etc.)."""
        asset_classes = {'Equity': 0, 'Derivatives': 0, 'Others': 0}
        
        for holding in holdings:
            symbol = holding.get('symbol', '')
            value = holding.get('market_value', 0)
            
            if 'FUT' in symbol or 'CE' in symbol or 'PE' in symbol:
                asset_classes['Derivatives'] += value
            elif 'EQ' in symbol:
                asset_classes['Equity'] += value
            else:
                asset_classes['Others'] += value
        
        allocation_list = []
        for asset_class, value in asset_classes.items():
            allocation_list.append({
                'asset_class': asset_class,
                'value': round(value, 2),
                'percentage': round((value / total_value * 100) if total_value > 0 else 0, 2)
            })
        
        return sorted(allocation_list, key=lambda x: x['value'], reverse=True)
    
    def _calculate_portfolio_diversity(self, holdings: List[Dict]) -> Dict[str, Any]:
        """Calculate portfolio diversity metrics."""
        if not holdings:
            return {'diversity_score': 0, 'herfindahl_index': 1, 'effective_stocks': 0}
        
        total_value = sum(h.get('market_value', 0) for h in holdings)
        
        # Calculate Herfindahl Index
        herfindahl_index = 0
        for holding in holdings:
            weight = (holding.get('market_value', 0) / total_value) if total_value > 0 else 0
            herfindahl_index += weight ** 2
        
        # Effective number of stocks
        effective_stocks = 1 / herfindahl_index if herfindahl_index > 0 else 0
        
        # Diversity score (0-100, higher is more diverse)
        diversity_score = min(100, (effective_stocks / len(holdings)) * 100) if holdings else 0
        
        return {
            'diversity_score': round(diversity_score, 2),
            'herfindahl_index': round(herfindahl_index, 4),
            'effective_stocks': round(effective_stocks, 2),
            'total_holdings': len(holdings)
        }
    
    def _calculate_period_performance(self, user_id: int, period: str, summary_data: Dict) -> Dict[str, Any]:
        """Calculate performance for specific period."""
        # This is simplified - in reality you'd need historical portfolio snapshots
        
        total_pnl = summary_data.get('total_pnl', 0)
        total_value = summary_data.get('total_portfolio_value', 0)
        
        # Estimate period return based on current data
        period_multiplier = {'1D': 1, '1W': 7, '1M': 30, '3M': 90, '6M': 180, '1Y': 365}
        days = period_multiplier.get(period, 30)
        
        # Simplified calculation
        estimated_return = (total_pnl / total_value * 100) if total_value > 0 else 0
        annualized_return = estimated_return * (365 / days) if days > 0 else 0
        
        return {
            'return_percent': round(estimated_return, 2),
            'annualized_return': round(annualized_return, 2),
            'volatility': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
            'risk_adjusted_return': 0.0
        }
    
    def _get_benchmark_comparison(self, user_id: int, period: str) -> Dict[str, Any]:
        """Compare portfolio performance with benchmarks."""
        # Get benchmark data (NIFTY 50 as primary benchmark)
        try:
            benchmark_response = self.fyers_service.quotes(user_id, 'NSE:NIFTY50-INDEX')
            
            benchmark_return = 0
            if benchmark_response.get('status') == 'success':
                benchmark_data = benchmark_response.get('data', {})
                benchmark_return = float(benchmark_data.get('change_percent', 0))
            
            return {
                'benchmark_name': 'NIFTY 50',
                'benchmark_return': benchmark_return,
                'relative_performance': 0,
                'beta': 0.0,
                'alpha': 0.0,
                'correlation': 0.0
            }

        except Exception:
            return {
                'benchmark_name': 'NIFTY 50',
                'benchmark_return': 0,
                'relative_performance': 0,
                'beta': 0.0,
                'alpha': 0.0,
                'correlation': 0.0
            }
    
    # Risk Calculation Methods
    def _calculate_risk_metrics(self, holdings: List[Dict], positions: List[Dict]) -> Dict[str, Any]:
        """Aggregate key risk metrics into a single structure."""
        try:
            return {
                'portfolio_beta': self._calculate_portfolio_beta(holdings),
                'value_at_risk': self._calculate_var(holdings, positions),
                'concentration_risk': self._calculate_concentration_risk(holdings),
                'sector_risk': self._calculate_sector_risk(holdings),
                'correlation_risk': self._calculate_correlation_risk(holdings),
                'leverage_ratio': self._calculate_leverage_ratio(holdings, positions),
                'diversification_ratio': self._calculate_diversification_ratio(holdings),
                'risk_rating': self._calculate_overall_risk_rating(holdings, positions)
            }
        except Exception as e:
            logger.warning(f"Error aggregating risk metrics: {e}")
            return {}
    def _calculate_portfolio_beta(self, holdings: List[Dict]) -> float:
        """Calculate portfolio beta (simplified)."""
        # In reality, this would require correlation analysis with market
        # Using simplified calculation based on sector weightings
        
        if not holdings:
            return 1.0
        
        total_value = sum(h.get('market_value', 0) for h in holdings)
        weighted_beta = 0
        
        # Sector beta estimates
        sector_betas = {
            'Technology': 1.2,
            'Banking': 1.1,
            'Energy': 0.9,
            'FMCG': 0.8,
            'Auto': 1.3,
            'Pharma': 0.7,
            'Others': 1.0
        }
        
        for holding in holdings:
            sector = self.fyers_service._get_sector_for_symbol(holding.get('symbol', ''))
            weight = (holding.get('market_value', 0) / total_value) if total_value > 0 else 0
            beta = sector_betas.get(sector, 1.0)
            weighted_beta += weight * beta
        
        return round(weighted_beta, 2)
    
    def _calculate_var(self, holdings: List[Dict], positions: List[Dict]) -> Dict[str, float]:
        """Calculate Value at Risk."""
        # Simplified VaR calculation
        total_value = sum(h.get('market_value', 0) for h in holdings)
        
        # Using simplified standard deviation approach
        portfolio_volatility = 0.15  # 15% assumed volatility
        confidence_levels = [0.95, 0.99]
        
        var_results = {}
        for confidence in confidence_levels:
            # Z-score for confidence level
            z_score = 1.645 if confidence == 0.95 else 2.33
            var_amount = total_value * portfolio_volatility * z_score
            
            var_results[f'var_{int(confidence*100)}'] = round(var_amount, 2)
        
        return var_results
    
    def _calculate_concentration_risk(self, holdings: List[Dict]) -> Dict[str, Any]:
        """Calculate portfolio concentration risk."""
        if not holdings:
            return {'risk_level': 'LOW', 'largest_position': 0, 'top_5_concentration': 0}
        
        total_value = sum(h.get('market_value', 0) for h in holdings)
        
        # Sort by value
        sorted_holdings = sorted(holdings, key=lambda x: x.get('market_value', 0), reverse=True)
        
        # Largest position percentage
        largest_position = (sorted_holdings[0].get('market_value', 0) / total_value * 100) if total_value > 0 else 0
        
        # Top 5 concentration
        top_5_value = sum(h.get('market_value', 0) for h in sorted_holdings[:5])
        top_5_concentration = (top_5_value / total_value * 100) if total_value > 0 else 0
        
        # Risk assessment
        if largest_position > 25:
            risk_level = 'HIGH'
        elif largest_position > 15:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        return {
            'risk_level': risk_level,
            'largest_position': round(largest_position, 2),
            'top_5_concentration': round(top_5_concentration, 2),
            'number_of_holdings': len(holdings)
        }
    
    def _calculate_sector_risk(self, holdings: List[Dict]) -> Dict[str, Any]:
        """Calculate sector concentration risk."""
        sector_allocation = self._calculate_sector_allocation(holdings)
        
        if not sector_allocation:
            return {'risk_level': 'LOW', 'max_sector_allocation': 0}
        
        max_allocation = max(s.get('percentage', 0) for s in sector_allocation)
        
        # Risk assessment
        if max_allocation > 40:
            risk_level = 'HIGH'
        elif max_allocation > 25:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        return {
            'risk_level': risk_level,
            'max_sector_allocation': max_allocation,
            'sector_count': len(sector_allocation)
        }
    
    def _calculate_correlation_risk(self, holdings: List[Dict]) -> float:
        """Calculate correlation risk (simplified)."""
        # In reality, this would require historical correlation matrix
        # Using simplified calculation based on sector diversity
        
        sectors = set()
        for holding in holdings:
            sector = self.fyers_service._get_sector_for_symbol(holding.get('symbol', ''))
            sectors.add(sector)
        
        # More sectors = lower correlation risk
        sector_count = len(sectors)
        holdings_count = len(holdings)
        
        if holdings_count == 0:
            return 0
        
        diversity_ratio = sector_count / holdings_count
        correlation_risk = max(0, 1 - diversity_ratio)  # 0 = low risk, 1 = high risk
        
        return round(correlation_risk, 2)
    
    def _calculate_leverage_ratio(self, holdings: List[Dict], positions: List[Dict]) -> float:
        """Calculate portfolio leverage ratio."""
        equity_value = sum(h.get('market_value', 0) for h in holdings)
        derivatives_exposure = sum(abs(p.get('quantity', 0) * p.get('market_price', 0)) for p in positions)
        
        if equity_value == 0:
            return 0
        
        leverage_ratio = (equity_value + derivatives_exposure) / equity_value
        return round(leverage_ratio, 2)
    
    def _calculate_diversification_ratio(self, holdings: List[Dict]) -> float:
        """Calculate diversification ratio."""
        if len(holdings) <= 1:
            return 0
        
        # Simplified diversification calculation
        total_holdings = len(holdings)
        effective_holdings = self._calculate_portfolio_diversity(holdings).get('effective_stocks', 0)
        
        diversification_ratio = effective_holdings / total_holdings if total_holdings > 0 else 0
        return round(diversification_ratio, 2)
    
    def _calculate_overall_risk_rating(self, holdings: List[Dict], positions: List[Dict]) -> str:
        """Calculate overall portfolio risk rating."""
        # Combine various risk factors
        concentration_risk = self._calculate_concentration_risk(holdings)
        sector_risk = self._calculate_sector_risk(holdings)
        correlation_risk = self._calculate_correlation_risk(holdings)
        leverage_ratio = self._calculate_leverage_ratio(holdings, positions)
        
        # Risk scoring (simplified)
        risk_score = 0
        
        # Concentration risk
        if concentration_risk['risk_level'] == 'HIGH':
            risk_score += 3
        elif concentration_risk['risk_level'] == 'MEDIUM':
            risk_score += 2
        else:
            risk_score += 1
        
        # Sector risk
        if sector_risk['risk_level'] == 'HIGH':
            risk_score += 3
        elif sector_risk['risk_level'] == 'MEDIUM':
            risk_score += 2
        else:
            risk_score += 1
        
        # Correlation and leverage
        if correlation_risk > 0.7:
            risk_score += 2
        if leverage_ratio > 2.0:
            risk_score += 2
        
        # Overall rating
        if risk_score >= 8:
            return 'HIGH'
        elif risk_score >= 5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _generate_risk_recommendations(self, risk_metrics: Dict, holdings: List[Dict]) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []
        
        # Concentration risk recommendations
        concentration = risk_metrics.get('concentration_risk', {})
        if concentration.get('risk_level') == 'HIGH':
            recommendations.append("Consider reducing position size in your largest holding to improve diversification")
        
        # Sector risk recommendations
        sector_risk = risk_metrics.get('sector_risk', {})
        if sector_risk.get('risk_level') == 'HIGH':
            recommendations.append("Your portfolio is heavily concentrated in one sector. Consider diversifying across sectors")
        
        # Leverage recommendations
        leverage = risk_metrics.get('leverage_ratio', 0)
        if leverage > 2.0:
            recommendations.append("High leverage detected. Consider reducing derivatives exposure")
        
        # Diversification recommendations
        if len(holdings) < 10:
            recommendations.append("Consider adding more holdings to improve diversification")
        
        # Beta recommendations
        beta = risk_metrics.get('portfolio_beta', 1.0)
        if beta > 1.5:
            recommendations.append("High beta portfolio detected. Consider adding defensive stocks to reduce volatility")
        
        return recommendations[:5]  # Limit to top 5 recommendations
    
    def _generate_risk_summary(self, risk_metrics: Dict) -> str:
        """Generate overall risk summary."""
        risk_rating = risk_metrics.get('risk_rating', 'MEDIUM')
        
        if risk_rating == 'HIGH':
            return "Your portfolio has elevated risk levels. Consider implementing risk management strategies."
        elif risk_rating == 'MEDIUM':
            return "Your portfolio has moderate risk levels. Monitor concentration and sector allocation."
        else:
            return "Your portfolio has well-managed risk levels. Continue monitoring for changes."
    
    def _calculate_volatility(self, returns: List[float]) -> float:
        """Calculate volatility from returns."""
        if not returns or len(returns) < 2:
            return 0
        
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5
        
        return round(volatility, 2)
    
    def _calculate_asset_allocation(self, holdings: List[Dict], positions: List[Dict]) -> Dict[str, Any]:
        """Calculate asset allocation breakdown."""
        try:
            # Calculate total portfolio value
            total_holdings_value = sum(h.get('market_value', 0) for h in holdings)
            total_positions_value = sum(abs(p.get('quantity', 0) * p.get('market_price', 0)) for p in positions)
            total_portfolio_value = total_holdings_value + total_positions_value
            
            if total_portfolio_value == 0:
                return {
                    'equity': 0,
                    'derivatives': 0,
                    'cash': 0,
                    'others': 0
                }
            
            # Calculate equity allocation from holdings
            equity_value = total_holdings_value
            
            # Calculate derivatives allocation from positions
            derivatives_value = total_positions_value
            
            # Calculate cash (this would need to come from funds data)
            cash_value = 0  # Placeholder - would need funds data
            
            # Calculate others
            others_value = max(0, total_portfolio_value - equity_value - derivatives_value - cash_value)
            
            return {
                'equity': round((equity_value / total_portfolio_value * 100), 2),
                'derivatives': round((derivatives_value / total_portfolio_value * 100), 2),
                'cash': round((cash_value / total_portfolio_value * 100), 2),
                'others': round((others_value / total_portfolio_value * 100), 2),
                'total_value': round(total_portfolio_value, 2)
            }
        except Exception as e:
            logger.warning(f"Error calculating asset allocation: {e}")
            return {
                'equity': 0,
                'derivatives': 0,
                'cash': 0,
                'others': 0,
                'total_value': 0
            }

"""
FYERS Reports Provider Implementation

Implements the IReportsProvider interface for FYERS broker.
"""

import logging
import json
import csv
import io
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from ..interfaces.reports_interface import IReportsProvider, Report, ReportType, ReportFormat
try:
    from ..brokers.fyers_service import get_fyers_service
except ImportError:
    from src.services.brokers.fyers_service import get_fyers_service

logger = logging.getLogger(__name__)


class FyersReportsProvider(IReportsProvider):
    """FYERS implementation of reports provider."""
    
    def __init__(self):
        self.fyers_service = get_fyers_service()
        self._report_storage = {}  # In-memory storage for demo
    
    def generate_pnl_report(self, user_id: int, start_date: datetime, 
                           end_date: datetime, report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """Generate P&L report for FYERS."""
        try:
            # Get trading data from broker service
            orders_response = self.fyers_service.orderbook(user_id)
            
            if orders_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Failed to fetch trading data for P&L report',
                    'data': None,
                    'report_id': None,
                    'generated_at': datetime.now().isoformat()
                }
            
            orders = orders_response.get('data', [])
            
            # Calculate P&L metrics
            total_trades = len(orders)
            winning_trades = sum(1 for order in orders if order.get('pnl', 0) > 0)
            losing_trades = sum(1 for order in orders if order.get('pnl', 0) < 0)
            
            total_pnl = sum(order.get('pnl', 0) for order in orders)
            total_volume = sum(order.get('quantity', 0) * order.get('price', 0) for order in orders)
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Group by symbol
            symbol_pnl = {}
            for order in orders:
                symbol = order.get('symbol', 'Unknown')
                if symbol not in symbol_pnl:
                    symbol_pnl[symbol] = {'pnl': 0, 'trades': 0, 'volume': 0}
                symbol_pnl[symbol]['pnl'] += order.get('pnl', 0)
                symbol_pnl[symbol]['trades'] += 1
                symbol_pnl[symbol]['volume'] += order.get('quantity', 0) * order.get('price', 0)
            
            # Create report data
            report_data = {
                'report_type': 'P&L Report',
                'period': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                },
                'summary': {
                    'total_trades': total_trades,
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'win_rate': round(win_rate, 2),
                    'total_pnl': round(total_pnl, 2),
                    'total_volume': round(total_volume, 2),
                    'average_trade_pnl': round(total_pnl / total_trades, 2) if total_trades > 0 else 0
                },
                'symbol_breakdown': symbol_pnl,
                'daily_pnl': self._calculate_daily_pnl(orders, start_date, end_date)
            }
            
            # Generate report ID
            report_id = f"PNL_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store report
            self._report_storage[report_id] = {
                'user_id': user_id,
                'report_type': 'P&L',
                'data': report_data,
                'format': report_format.value,
                'created_at': datetime.now(),
                'period': {'start_date': start_date, 'end_date': end_date}
            }
            
            return {
                'success': True,
                'data': report_data,
                'report_id': report_id,
                'generated_at': datetime.now().isoformat(),
                'format': report_format.value
            }
            
        except Exception as e:
            logger.error(f"Error generating P&L report: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to generate P&L report: {str(e)}',
                'data': None,
                'report_id': None,
                'generated_at': datetime.now().isoformat()
            }
    
    def generate_tax_report(self, user_id: int, financial_year: str, 
                          report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """Generate tax report for FYERS."""
        try:
            # Calculate financial year dates
            if financial_year == '2023-24':
                start_date = datetime(2023, 4, 1)
                end_date = datetime(2024, 3, 31)
            elif financial_year == '2024-25':
                start_date = datetime(2024, 4, 1)
                end_date = datetime(2025, 3, 31)
            else:
                # Default to current financial year
                current_year = datetime.now().year
                if datetime.now().month >= 4:
                    start_date = datetime(current_year, 4, 1)
                    end_date = datetime(current_year + 1, 3, 31)
                else:
                    start_date = datetime(current_year - 1, 4, 1)
                    end_date = datetime(current_year, 3, 31)
            
            # Get trading data for the financial year
            orders_response = self.fyers_service.orderbook(user_id)
            
            if orders_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Failed to fetch trading data for tax report',
                    'data': None,
                    'report_id': None,
                    'generated_at': datetime.now().isoformat()
                }
            
            orders = orders_response.get('data', [])
            
            # Calculate tax metrics
            total_realized_pnl = sum(order.get('pnl', 0) for order in orders if order.get('status') == 'COMPLETE')
            short_term_pnl = 0  # Trades held for less than 1 year
            long_term_pnl = 0   # Trades held for more than 1 year
            
            # Categorize P&L (simplified - in real implementation, need to track holding periods)
            for order in orders:
                if order.get('status') == 'COMPLETE':
                    pnl = order.get('pnl', 0)
                    # Simplified: assume all are short-term for demo
                    short_term_pnl += pnl
            
            # Calculate tax liability (simplified)
            short_term_tax = short_term_pnl * 0.15 if short_term_pnl > 0 else 0  # 15% STCG
            long_term_tax = long_term_pnl * 0.10 if long_term_pnl > 0 else 0    # 10% LTCG (over 1L)
            
            # Create tax report data
            report_data = {
                'report_type': 'Tax Report',
                'financial_year': financial_year,
                'period': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                },
                'summary': {
                    'total_realized_pnl': round(total_realized_pnl, 2),
                    'short_term_pnl': round(short_term_pnl, 2),
                    'long_term_pnl': round(long_term_pnl, 2),
                    'short_term_tax': round(short_term_tax, 2),
                    'long_term_tax': round(long_term_tax, 2),
                    'total_tax_liability': round(short_term_tax + long_term_tax, 2)
                },
                'monthly_breakdown': self._calculate_monthly_pnl(orders, start_date, end_date),
                'disclaimer': 'This is a simplified tax calculation. Please consult a tax advisor for accurate tax filing.'
            }
            
            # Generate report ID
            report_id = f"TAX_{user_id}_{financial_year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store report
            self._report_storage[report_id] = {
                'user_id': user_id,
                'report_type': 'Tax',
                'data': report_data,
                'format': report_format.value,
                'created_at': datetime.now(),
                'financial_year': financial_year
            }
            
            return {
                'success': True,
                'data': report_data,
                'report_id': report_id,
                'generated_at': datetime.now().isoformat(),
                'format': report_format.value
            }
            
        except Exception as e:
            logger.error(f"Error generating tax report: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to generate tax report: {str(e)}',
                'data': None,
                'report_id': None,
                'generated_at': datetime.now().isoformat()
            }
    
    def generate_portfolio_report(self, user_id: int, report_type: ReportType, 
                                 report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """Generate portfolio report for FYERS."""
        try:
            # Get portfolio data
            portfolio_response = self.fyers_service.generate_portfolio_summary_report(user_id)
            
            if portfolio_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Failed to fetch portfolio data for portfolio report',
                    'data': None,
                    'report_id': None,
                    'generated_at': datetime.now().isoformat()
                }
            
            portfolio_data = portfolio_response.get('data', {})
            
            # Get holdings data
            holdings_response = self.fyers_service.holdings(user_id)
            holdings = holdings_response.get('data', []) if holdings_response.get('status') == 'success' else []
            
            # Create portfolio report data
            report_data = {
                'report_type': f'Portfolio Report - {report_type.value}',
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'portfolio_summary': portfolio_data,
                'holdings_analysis': {
                    'total_holdings': len(holdings),
                    'top_holdings': sorted(holdings, key=lambda x: x.get('current_value', 0), reverse=True)[:10],
                    'sector_allocation': self._calculate_sector_allocation(holdings),
                    'market_cap_allocation': self._calculate_market_cap_allocation(holdings)
                },
                'performance_metrics': {
                    'total_return': portfolio_data.get('total_pnl_percent', 0),
                    'portfolio_value': portfolio_data.get('total_portfolio_value', 0),
                    'available_cash': portfolio_data.get('available_cash', 0)
                }
            }
            
            # Generate report ID
            report_id = f"PORT_{user_id}_{report_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store report
            self._report_storage[report_id] = {
                'user_id': user_id,
                'report_type': f'Portfolio_{report_type.value}',
                'data': report_data,
                'format': report_format.value,
                'created_at': datetime.now()
            }
            
            return {
                'success': True,
                'data': report_data,
                'report_id': report_id,
                'generated_at': datetime.now().isoformat(),
                'format': report_format.value
            }
            
        except Exception as e:
            logger.error(f"Error generating portfolio report: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to generate portfolio report: {str(e)}',
                'data': None,
                'report_id': None,
                'generated_at': datetime.now().isoformat()
            }
    
    def generate_trading_summary(self, user_id: int, start_date: datetime, 
                               end_date: datetime, report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """Generate trading summary for FYERS."""
        try:
            # Get trading data
            orders_response = self.fyers_service.orderbook(user_id)
            
            if orders_response.get('status') != 'success':
                return {
                    'success': False,
                    'error': 'Failed to fetch trading data for trading summary',
                    'data': None,
                    'report_id': None,
                    'generated_at': datetime.now().isoformat()
                }
            
            orders = orders_response.get('data', [])
            
            # Calculate trading metrics
            total_trades = len(orders)
            completed_trades = sum(1 for order in orders if order.get('status') == 'COMPLETE')
            pending_trades = sum(1 for order in orders if order.get('status') == 'PENDING')
            cancelled_trades = sum(1 for order in orders if order.get('status') == 'CANCELLED')
            
            total_volume = sum(order.get('quantity', 0) * order.get('price', 0) for order in orders)
            total_pnl = sum(order.get('pnl', 0) for order in orders)
            
            # Calculate daily trading activity
            daily_activity = self._calculate_daily_trading_activity(orders, start_date, end_date)
            
            # Most traded symbols
            symbol_stats = {}
            for order in orders:
                symbol = order.get('symbol', 'Unknown')
                if symbol not in symbol_stats:
                    symbol_stats[symbol] = {'trades': 0, 'volume': 0, 'pnl': 0}
                symbol_stats[symbol]['trades'] += 1
                symbol_stats[symbol]['volume'] += order.get('quantity', 0) * order.get('price', 0)
                symbol_stats[symbol]['pnl'] += order.get('pnl', 0)
            
            most_traded = sorted(symbol_stats.items(), key=lambda x: x[1]['trades'], reverse=True)[:10]
            
            # Create trading summary data
            report_data = {
                'report_type': 'Trading Summary',
                'period': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                },
                'trading_statistics': {
                    'total_trades': total_trades,
                    'completed_trades': completed_trades,
                    'pending_trades': pending_trades,
                    'cancelled_trades': cancelled_trades,
                    'completion_rate': round((completed_trades / total_trades * 100) if total_trades > 0 else 0, 2),
                    'total_volume': round(total_volume, 2),
                    'total_pnl': round(total_pnl, 2),
                    'average_trade_size': round(total_volume / total_trades, 2) if total_trades > 0 else 0
                },
                'daily_activity': daily_activity,
                'most_traded_symbols': [
                    {
                        'symbol': symbol,
                        'trades': stats['trades'],
                        'volume': round(stats['volume'], 2),
                        'pnl': round(stats['pnl'], 2)
                    }
                    for symbol, stats in most_traded
                ]
            }
            
            # Generate report ID
            report_id = f"TRADE_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Store report
            self._report_storage[report_id] = {
                'user_id': user_id,
                'report_type': 'Trading_Summary',
                'data': report_data,
                'format': report_format.value,
                'created_at': datetime.now(),
                'period': {'start_date': start_date, 'end_date': end_date}
            }
            
            return {
                'success': True,
                'data': report_data,
                'report_id': report_id,
                'generated_at': datetime.now().isoformat(),
                'format': report_format.value
            }
            
        except Exception as e:
            logger.error(f"Error generating trading summary: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to generate trading summary: {str(e)}',
                'data': None,
                'report_id': None,
                'generated_at': datetime.now().isoformat()
            }
    
    def get_report_history(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """Get report history for FYERS."""
        try:
            # Filter reports for the user
            user_reports = [
                {
                    'report_id': report_id,
                    'report_type': report_data['report_type'],
                    'format': report_data['format'],
                    'created_at': report_data['created_at'].isoformat(),
                    'status': 'completed'
                }
                for report_id, report_data in self._report_storage.items()
                if report_data['user_id'] == user_id
            ]
            
            # Sort by creation date (newest first)
            user_reports.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Apply limit
            user_reports = user_reports[:limit]
            
            return {
                'success': True,
                'data': user_reports,
                'total': len(user_reports),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting report history: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to get report history: {str(e)}',
                'data': [],
                'total': 0,
                'last_updated': datetime.now().isoformat()
            }
    
    def download_report(self, user_id: int, report_id: str) -> Dict[str, Any]:
        """Download report for FYERS."""
        try:
            if report_id not in self._report_storage:
                return {
                    'success': False,
                    'error': 'Report not found',
                    'file_path': None,
                    'content_type': None,
                    'filename': None
                }
            
            report_data = self._report_storage[report_id]
            
            # Check if user owns this report
            if report_data['user_id'] != user_id:
                return {
                    'success': False,
                    'error': 'Access denied',
                    'file_path': None,
                    'content_type': None,
                    'filename': None
                }
            
            # Generate filename
            report_type = report_data['report_type'].replace(' ', '_').lower()
            timestamp = report_data['created_at'].strftime('%Y%m%d_%H%M%S')
            filename = f"{report_type}_{user_id}_{timestamp}.{report_data['format'].lower()}"
            
            # For demo purposes, return the data as JSON
            # In a real implementation, you would save to file and return file path
            return {
                'success': True,
                'file_path': f'/tmp/{filename}',  # Simulated file path
                'content_type': 'application/json' if report_data['format'] == 'JSON' else 'text/csv',
                'filename': filename,
                'data': report_data['data']  # Include data for demo
            }
            
        except Exception as e:
            logger.error(f"Error downloading report: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to download report: {str(e)}',
                'file_path': None,
                'content_type': None,
                'filename': None
            }
    
    def _calculate_daily_pnl(self, orders: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
        """Calculate daily P&L from orders."""
        daily_pnl = {}
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            daily_pnl[date_str] = 0
            current_date += timedelta(days=1)
        
        # Add P&L from orders
        for order in orders:
            order_date = order.get('order_time', datetime.now())
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
            date_str = order_date.strftime('%Y-%m-%d')
            if date_str in daily_pnl:
                daily_pnl[date_str] += order.get('pnl', 0)
        
        return [
            {'date': date, 'pnl': round(pnl, 2)}
            for date, pnl in sorted(daily_pnl.items())
        ]
    
    def _calculate_monthly_pnl(self, orders: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
        """Calculate monthly P&L from orders."""
        monthly_pnl = {}
        
        for order in orders:
            order_date = order.get('order_time', datetime.now())
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
            month_key = order_date.strftime('%Y-%m')
            
            if month_key not in monthly_pnl:
                monthly_pnl[month_key] = 0
            monthly_pnl[month_key] += order.get('pnl', 0)
        
        return [
            {'month': month, 'pnl': round(pnl, 2)}
            for month, pnl in sorted(monthly_pnl.items())
        ]
    
    def _calculate_sector_allocation(self, holdings: List[Dict]) -> Dict[str, float]:
        """Calculate sector allocation from holdings."""
        sector_allocation = {}
        total_value = sum(holding.get('current_value', 0) for holding in holdings)
        
        for holding in holdings:
            sector = holding.get('sector', 'Others')
            value = holding.get('current_value', 0)
            
            if sector not in sector_allocation:
                sector_allocation[sector] = 0
            sector_allocation[sector] += value
        
        # Convert to percentages
        for sector in sector_allocation:
            sector_allocation[sector] = round((sector_allocation[sector] / total_value * 100) if total_value > 0 else 0, 2)
        
        return sector_allocation
    
    def _calculate_market_cap_allocation(self, holdings: List[Dict]) -> Dict[str, float]:
        """Calculate market cap allocation from holdings."""
        # Simplified market cap categorization
        market_cap_allocation = {'Large Cap': 0, 'Mid Cap': 0, 'Small Cap': 0}
        total_value = sum(holding.get('current_value', 0) for holding in holdings)
        
        for holding in holdings:
            value = holding.get('current_value', 0)
            # Simplified logic - in real implementation, use actual market cap data
            if value > 1000000:  # > 10L
                market_cap_allocation['Large Cap'] += value
            elif value > 100000:  # > 1L
                market_cap_allocation['Mid Cap'] += value
            else:
                market_cap_allocation['Small Cap'] += value
        
        # Convert to percentages
        for cap_type in market_cap_allocation:
            market_cap_allocation[cap_type] = round((market_cap_allocation[cap_type] / total_value * 100) if total_value > 0 else 0, 2)
        
        return market_cap_allocation
    
    def _calculate_daily_trading_activity(self, orders: List[Dict], start_date: datetime, end_date: datetime) -> List[Dict]:
        """Calculate daily trading activity."""
        daily_activity = {}
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            daily_activity[date_str] = {'trades': 0, 'volume': 0, 'pnl': 0}
            current_date += timedelta(days=1)
        
        # Add activity from orders
        for order in orders:
            order_date = order.get('order_time', datetime.now())
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
            date_str = order_date.strftime('%Y-%m-%d')
            
            if date_str in daily_activity:
                daily_activity[date_str]['trades'] += 1
                daily_activity[date_str]['volume'] += order.get('quantity', 0) * order.get('price', 0)
                daily_activity[date_str]['pnl'] += order.get('pnl', 0)
        
        return [
            {
                'date': date,
                'trades': activity['trades'],
                'volume': round(activity['volume'], 2),
                'pnl': round(activity['pnl'], 2)
            }
            for date, activity in sorted(daily_activity.items())
        ]

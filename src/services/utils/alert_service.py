"""
Consolidated Alert Management Service
Combines functionality from alerts/ and email_alerts/ modules
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
import os
from enum import Enum

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Alert types."""
    STOCK_PICK = "STOCK_PICK"
    PORTFOLIO = "PORTFOLIO"
    STRATEGY_PERFORMANCE = "STRATEGY_PERFORMANCE"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    RISK_ALERT = "RISK_ALERT"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class AlertPriority(Enum):
    """Alert priorities."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertService:
    """Consolidated alert management service."""
    
    def __init__(self, db_manager):
        """Initialize alert service."""
        self.db_manager = db_manager
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.sender_email = os.environ.get('SENDER_EMAIL', '')
        self.sender_password = os.environ.get('SENDER_PASSWORD', '')
        
        # Test email configuration
        self._test_email_config()
    
    def _test_email_config(self):
        """Test email configuration."""
        if not self.sender_email or not self.sender_password:
            logger.warning("Email configuration incomplete. Alerts will be logged only.")
            self.email_enabled = False
        else:
            self.email_enabled = True
            logger.info("Email alerts enabled")
    
    def create_alert(self, user_id: int, alert_type: AlertType, title: str, 
                    message: str, priority: AlertPriority = AlertPriority.MEDIUM,
                    data: Optional[Dict] = None) -> bool:
        """Create and store an alert."""
        try:
            with self.db_manager.get_session() as session:
                alert = self.db_manager.Alert(
                    user_id=user_id,
                    alert_type=alert_type.value,
                    title=title,
                    message=message,
                    priority=priority.value,
                    data=data,
                    created_at=datetime.utcnow(),
                    is_read=False
                )
                session.add(alert)
                session.commit()
                
                logger.info(f"Created alert for user {user_id}: {title}")
                return True
                
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return False
    
    def send_stock_pick_alert(self, user_id: int, stock_data: Dict, strategy_name: str, 
                             recommendation: str = "BUY") -> bool:
        """Send stock pick alert to user."""
        try:
            # Create alert record
            title = f"Stock Pick: {stock_data['symbol']} - {recommendation}"
            message = f"Strategy '{strategy_name}' recommends {recommendation} for {stock_data['symbol']}"
            
            self.create_alert(
                user_id=user_id,
                alert_type=AlertType.STOCK_PICK,
                title=title,
                message=message,
                priority=AlertPriority.HIGH,
                data=stock_data
            )
            
            # Send email if enabled
            if self.email_enabled:
                return self._send_stock_pick_email(user_id, stock_data, strategy_name, recommendation)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending stock pick alert: {e}")
            return False
    
    def send_portfolio_alert(self, user_id: int, portfolio_data: Dict, alert_type: str) -> bool:
        """Send portfolio alert to user."""
        try:
            title = f"Portfolio Alert: {alert_type.title()}"
            message = f"Your portfolio has triggered a {alert_type} alert"
            
            self.create_alert(
                user_id=user_id,
                alert_type=AlertType.PORTFOLIO,
                title=title,
                message=message,
                priority=AlertPriority.MEDIUM,
                data=portfolio_data
            )
            
            # Send email if enabled
            if self.email_enabled:
                return self._send_portfolio_email(user_id, portfolio_data, alert_type)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending portfolio alert: {e}")
            return False
    
    def send_strategy_performance_alert(self, user_id: int, strategy_results: Dict) -> bool:
        """Send strategy performance alert to user."""
        try:
            title = "Strategy Performance Report"
            message = "Your trading strategies have been evaluated and performance results are available"
            
            self.create_alert(
                user_id=user_id,
                alert_type=AlertType.STRATEGY_PERFORMANCE,
                title=title,
                message=message,
                priority=AlertPriority.LOW,
                data=strategy_results
            )
            
            # Send email if enabled
            if self.email_enabled:
                return self._send_strategy_performance_email(user_id, strategy_results)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending strategy performance alert: {e}")
            return False
    
    def send_daily_summary(self, user_id: int, daily_data: Dict) -> bool:
        """Send daily summary to user."""
        try:
            title = f"Daily Trading Summary - {datetime.now().strftime('%Y-%m-%d')}"
            message = "Here's your daily trading summary"
            
            self.create_alert(
                user_id=user_id,
                alert_type=AlertType.DAILY_SUMMARY,
                title=title,
                message=message,
                priority=AlertPriority.LOW,
                data=daily_data
            )
            
            # Send email if enabled
            if self.email_enabled:
                return self._send_daily_summary_email(user_id, daily_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
            return False
    
    def get_user_alerts(self, user_id: int, unread_only: bool = False, 
                       limit: int = 50) -> List[Dict]:
        """Get alerts for a user."""
        try:
            with self.db_manager.get_session() as session:
                query = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.user_id == user_id
                )
                
                if unread_only:
                    query = query.filter(self.db_manager.Alert.is_read == False)
                
                alerts = query.order_by(
                    self.db_manager.Alert.created_at.desc()
                ).limit(limit).all()
                
                return [self._alert_to_dict(alert) for alert in alerts]
                
        except Exception as e:
            logger.error(f"Error getting alerts for user {user_id}: {e}")
            return []
    
    def mark_alert_as_read(self, alert_id: int, user_id: int) -> bool:
        """Mark an alert as read."""
        try:
            with self.db_manager.get_session() as session:
                alert = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.id == alert_id,
                    self.db_manager.Alert.user_id == user_id
                ).first()
                
                if alert:
                    alert.is_read = True
                    alert.read_at = datetime.utcnow()
                    session.commit()
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error marking alert as read: {e}")
            return False
    
    def mark_all_alerts_as_read(self, user_id: int) -> bool:
        """Mark all alerts as read for a user."""
        try:
            with self.db_manager.get_session() as session:
                session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.user_id == user_id,
                    self.db_manager.Alert.is_read == False
                ).update({
                    'is_read': True,
                    'read_at': datetime.utcnow()
                })
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error marking all alerts as read: {e}")
            return False
    
    def delete_alert(self, alert_id: int, user_id: int) -> bool:
        """Delete an alert."""
        try:
            with self.db_manager.get_session() as session:
                alert = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.id == alert_id,
                    self.db_manager.Alert.user_id == user_id
                ).first()
                
                if alert:
                    session.delete(alert)
                    session.commit()
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error deleting alert: {e}")
            return False
    
    def get_alert_stats(self, user_id: int) -> Dict:
        """Get alert statistics for a user."""
        try:
            with self.db_manager.get_session() as session:
                total_alerts = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.user_id == user_id
                ).count()
                
                unread_alerts = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.user_id == user_id,
                    self.db_manager.Alert.is_read == False
                ).count()
                
                critical_alerts = session.query(self.db_manager.Alert).filter(
                    self.db_manager.Alert.user_id == user_id,
                    self.db_manager.Alert.priority == AlertPriority.CRITICAL.value,
                    self.db_manager.Alert.is_read == False
                ).count()
                
                return {
                    'total_alerts': total_alerts,
                    'unread_alerts': unread_alerts,
                    'critical_alerts': critical_alerts,
                    'read_alerts': total_alerts - unread_alerts
                }
                
        except Exception as e:
            logger.error(f"Error getting alert stats: {e}")
            return {
                'total_alerts': 0,
                'unread_alerts': 0,
                'critical_alerts': 0,
                'read_alerts': 0
            }
    
    def _get_user(self, user_id: int):
        """Get user by ID."""
        try:
            with self.db_manager.get_session() as session:
                user = session.query(self.db_manager.User).filter(
                    self.db_manager.User.id == user_id
                ).first()
                if user:
                    session.expunge(user)
                return user
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def _user_wants_email_alerts(self, user_id: int) -> bool:
        """Check if user wants email alerts."""
        try:
            # This would be stored in user settings
            # For now, assume all users want alerts
            return True
        except Exception as e:
            logger.error(f"Error checking user email preferences: {e}")
            return False
    
    def _send_email(self, recipient_email: str, subject: str, html_content: str, 
                   text_content: str) -> bool:
        """Send email to recipient."""
        if not self.email_enabled:
            logger.info(f"Email disabled - would send to {recipient_email}: {subject}")
            return True
        
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_content, "plain")
            html_part = MIMEText(html_content, "html")
            
            message.attach(text_part)
            message.attach(html_part)
            
            # Create secure connection and send email
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipient_email, message.as_string())
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending email to {recipient_email}: {e}")
            return False
    
    def _send_stock_pick_email(self, user_id: int, stock_data: Dict, strategy_name: str, 
                              recommendation: str) -> bool:
        """Send stock pick email."""
        user = self._get_user(user_id)
        if not user or not self._user_wants_email_alerts(user_id):
            return True
        
        subject = f"🎯 Stock Pick Alert: {stock_data['symbol']} - {recommendation}"
        html_content = self._create_stock_pick_email_html(stock_data, strategy_name, recommendation)
        text_content = self._create_stock_pick_email_text(stock_data, strategy_name, recommendation)
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def _send_portfolio_email(self, user_id: int, portfolio_data: Dict, alert_type: str) -> bool:
        """Send portfolio alert email."""
        user = self._get_user(user_id)
        if not user or not self._user_wants_email_alerts(user_id):
            return True
        
        subject = f"📊 Portfolio Alert: {alert_type.title()}"
        html_content = self._create_portfolio_alert_email_html(portfolio_data, alert_type)
        text_content = self._create_portfolio_alert_email_text(portfolio_data, alert_type)
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def _send_strategy_performance_email(self, user_id: int, strategy_results: Dict) -> bool:
        """Send strategy performance email."""
        user = self._get_user(user_id)
        if not user or not self._user_wants_email_alerts(user_id):
            return True
        
        subject = "📈 Strategy Performance Report"
        html_content = self._create_strategy_performance_email_html(strategy_results)
        text_content = self._create_strategy_performance_email_text(strategy_results)
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def _send_daily_summary_email(self, user_id: int, daily_data: Dict) -> bool:
        """Send daily summary email."""
        user = self._get_user(user_id)
        if not user or not self._user_wants_email_alerts(user_id):
            return True
        
        subject = f"📋 Daily Trading Summary - {datetime.now().strftime('%Y-%m-%d')}"
        html_content = self._create_daily_summary_email_html(daily_data)
        text_content = self._create_daily_summary_email_text(daily_data)
        
        return self._send_email(user.email, subject, html_content, text_content)
    
    def _create_stock_pick_email_html(self, stock_data: Dict, strategy_name: str, 
                                    recommendation: str) -> str:
        """Create HTML content for stock pick email."""
        color = "#28a745" if recommendation == "BUY" else "#dc3545" if recommendation == "SELL" else "#ffc107"
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background-color: {color}; color: white; padding: 15px; border-radius: 5px; text-align: center; margin-bottom: 20px; }}
                .stock-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .metric {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
                .metric-label {{ font-weight: bold; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🎯 Stock Pick Alert</h2>
                    <h3>{stock_data['symbol']} - {recommendation}</h3>
                </div>
                
                <div class="stock-info">
                    <h3>{stock_data['name']}</h3>
                    <div class="metric">
                        <span class="metric-label">Current Price:</span>
                        <span>₹{stock_data['current_price']:.2f}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Market Cap:</span>
                        <span>₹{stock_data['market_cap']:,.0f}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Sector:</span>
                        <span>{stock_data['sector']}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Strategy:</span>
                        <span>{strategy_name}</span>
                    </div>
                </div>
                
                <div class="footer">
                    <p>This alert was generated by your automated trading system.</p>
                    <p>Please do your own research before making investment decisions.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_stock_pick_email_text(self, stock_data: Dict, strategy_name: str, 
                                    recommendation: str) -> str:
        """Create text content for stock pick email."""
        return f"""
Stock Pick Alert: {stock_data['symbol']} - {recommendation}

Stock: {stock_data['name']}
Current Price: ₹{stock_data['current_price']:.2f}
Market Cap: ₹{stock_data['market_cap']:,.0f}
Sector: {stock_data['sector']}
Strategy: {strategy_name}

This alert was generated by your automated trading system.
Please do your own research before making investment decisions.
        """
    
    def _create_portfolio_alert_email_html(self, portfolio_data: Dict, alert_type: str) -> str:
        """Create HTML content for portfolio alert email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background-color: #007bff; color: white; padding: 15px; border-radius: 5px; text-align: center; margin-bottom: 20px; }}
                .alert-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📊 Portfolio Alert</h2>
                    <h3>{alert_type.title()}</h3>
                </div>
                
                <div class="alert-info">
                    <p>Your portfolio has triggered a {alert_type} alert.</p>
                    <p>Please review your positions and consider taking appropriate action.</p>
                </div>
                
                <div class="footer">
                    <p>This alert was generated by your automated trading system.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_portfolio_alert_email_text(self, portfolio_data: Dict, alert_type: str) -> str:
        """Create text content for portfolio alert email."""
        return f"""
Portfolio Alert: {alert_type.title()}

Your portfolio has triggered a {alert_type} alert.
Please review your positions and consider taking appropriate action.

This alert was generated by your automated trading system.
        """
    
    def _create_strategy_performance_email_html(self, strategy_results: Dict) -> str:
        """Create HTML content for strategy performance email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background-color: #28a745; color: white; padding: 15px; border-radius: 5px; text-align: center; margin-bottom: 20px; }}
                .strategy-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📈 Strategy Performance Report</h2>
                </div>
                
                <div class="strategy-info">
                    <p>Your trading strategies have been evaluated and performance results are available.</p>
                    <p>Please check your dashboard for detailed performance metrics.</p>
                </div>
                
                <div class="footer">
                    <p>This report was generated by your automated trading system.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_strategy_performance_email_text(self, strategy_results: Dict) -> str:
        """Create text content for strategy performance email."""
        return f"""
Strategy Performance Report

Your trading strategies have been evaluated and performance results are available.
Please check your dashboard for detailed performance metrics.

This report was generated by your automated trading system.
        """
    
    def _create_daily_summary_email_html(self, daily_data: Dict) -> str:
        """Create HTML content for daily summary email."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background-color: #6c757d; color: white; padding: 15px; border-radius: 5px; text-align: center; margin-bottom: 20px; }}
                .summary-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📋 Daily Trading Summary</h2>
                    <h3>{datetime.now().strftime('%Y-%m-%d')}</h3>
                </div>
                
                <div class="summary-info">
                    <p>Here's your daily trading summary:</p>
                    <ul>
                        <li>Stocks screened: {daily_data.get('stocks_screened', 0)}</li>
                        <li>Stocks selected: {daily_data.get('stocks_selected', 0)}</li>
                        <li>Strategies executed: {daily_data.get('strategies_executed', 0)}</li>
                        <li>Portfolio value: ₹{daily_data.get('portfolio_value', 0):,.2f}</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>This summary was generated by your automated trading system.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_daily_summary_email_text(self, daily_data: Dict) -> str:
        """Create text content for daily summary email."""
        return f"""
Daily Trading Summary - {datetime.now().strftime('%Y-%m-%d')}

Here's your daily trading summary:
- Stocks screened: {daily_data.get('stocks_screened', 0)}
- Stocks selected: {daily_data.get('stocks_selected', 0)}
- Strategies executed: {daily_data.get('strategies_executed', 0)}
- Portfolio value: ₹{daily_data.get('portfolio_value', 0):,.2f}

This summary was generated by your automated trading system.
        """
    
    def _alert_to_dict(self, alert) -> Dict:
        """Convert Alert object to dictionary."""
        return {
            'id': alert.id,
            'user_id': alert.user_id,
            'alert_type': alert.alert_type,
            'title': alert.title,
            'message': alert.message,
            'priority': alert.priority,
            'data': alert.data,
            'is_read': alert.is_read,
            'created_at': alert.created_at.isoformat() if alert.created_at else None,
            'read_at': alert.read_at.isoformat() if alert.read_at else None
        }

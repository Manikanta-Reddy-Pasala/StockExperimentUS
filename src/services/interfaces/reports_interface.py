"""
Reports Interface Definition

Defines the contract for reports generation features across different brokers.
Each broker implementation must provide these methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class ReportType(Enum):
    """Report types."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ReportFormat(Enum):
    """Report output formats."""
    JSON = "json"
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"


class IReportsProvider(ABC):
    """
    Interface for reports data providers.
    
    This interface defines all the methods that must be implemented
    by each broker to provide reporting functionality.
    """

    @abstractmethod
    def generate_pnl_report(self, user_id: int, start_date: datetime, 
                           end_date: datetime, report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """
        Generate P&L report for a given period.
        
        Args:
            user_id: The user ID for broker-specific authentication
            start_date: Report start date
            end_date: Report end date
            report_format: Output format for the report
            
        Returns:
            Dict containing:
            - success: bool
            - data: Report data or file path
            - report_id: Unique report identifier
            - generated_at: timestamp
        """
        pass

    @abstractmethod
    def generate_tax_report(self, user_id: int, financial_year: str, 
                          report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """
        Generate tax report for a financial year.
        
        Args:
            user_id: The user ID for broker-specific authentication
            financial_year: Financial year (e.g., "2023-24")
            report_format: Output format for the report
            
        Returns:
            Dict containing:
            - success: bool
            - data: Tax report data or file path
            - report_id: Unique report identifier
            - generated_at: timestamp
        """
        pass
    @abstractmethod
    def generate_portfolio_report(self, user_id: int, report_type: ReportType, 
                                 report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """
        Generate portfolio performance report.
        
        Args:
            user_id: The user ID for broker-specific authentication
            report_type: Type of report (daily, weekly, monthly, etc.)
            report_format: Output format for the report
            
        Returns:
            Dict containing:
            - success: bool
            - data: Portfolio report data or file path
            - report_id: Unique report identifier
            - generated_at: timestamp
        """
        pass

    @abstractmethod
    def generate_trading_summary(self, user_id: int, start_date: datetime, 
                               end_date: datetime, report_format: ReportFormat = ReportFormat.JSON) -> Dict[str, Any]:
        """
        Generate trading activity summary report.
        
        Args:
            user_id: The user ID for broker-specific authentication
            start_date: Report start date
            end_date: Report end date
            report_format: Output format for the report
            
        Returns:
            Dict containing:
            - success: bool
            - data: Trading summary data or file path
            - report_id: Unique report identifier
            - generated_at: timestamp
        """
        pass

    @abstractmethod
    def get_report_history(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """
        Get previously generated reports.
        
        Args:
            user_id: The user ID for broker-specific authentication
            limit: Maximum number of reports to return
            
        Returns:
            Dict containing:
            - success: bool
            - data: List of generated reports with metadata
            - total: Total number of reports
            - last_updated: timestamp
        """
        pass
    @abstractmethod
    def download_report(self, user_id: int, report_id: str) -> Dict[str, Any]:
        """
        Download a previously generated report.
        
        Args:
            user_id: The user ID for broker-specific authentication
            report_id: ID of the report to download
            
        Returns:
            Dict containing:
            - success: bool
            - file_path: Path to the report file
            - content_type: MIME type of the file
            - filename: Suggested filename for download
        """
        pass


class Report:
    """Data class for report information."""
    
    def __init__(self, report_id: str, report_type: ReportType, 
                 report_format: ReportFormat, user_id: int):
        self.report_id = report_id
        self.report_type = report_type
        self.report_format = report_format
        self.user_id = user_id
        self.generated_at = datetime.now()
        self.file_path: Optional[str] = None
        self.file_size: Optional[int] = None
        self.status: str = "generating"
        self.error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'report_id': self.report_id,
            'report_type': self.report_type.value,
            'report_format': self.report_format.value,
            'user_id': self.user_id,
            'generated_at': self.generated_at.isoformat(),
            'file_path': self.file_path,
            'file_size': self.file_size,
            'status': self.status,
            'error_message': self.error_message
        }

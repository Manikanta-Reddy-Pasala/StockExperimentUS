"""
Multi-broker Interface Package

This package provides the interface definitions for multi-broker support
using SOLID principles, specifically the Strategy and Interface Segregation patterns.
"""

from .dashboard_interface import IDashboardProvider
from .orders_interface import IOrdersProvider
from .portfolio_interface import IPortfolioProvider
from .reports_interface import IReportsProvider
from .broker_feature_factory import BrokerFeatureFactory, get_broker_feature_factory

__all__ = [
    'IDashboardProvider',
    'IOrdersProvider',
    'IPortfolioProvider',
    'IReportsProvider',
    'BrokerFeatureFactory',
    'get_broker_feature_factory'
]

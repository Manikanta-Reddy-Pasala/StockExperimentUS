from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from tools.shared.splice import trading_days


def test_trading_days_dedups_and_drops_weekends():
    raw = ["2024-01-05","2024-01-05","2024-01-06","2024-01-07","2024-01-08"]
    idx = trading_days(pd.to_datetime(pd.Series(raw)))
    assert list(idx.strftime("%Y-%m-%d")) == ["2024-01-05", "2024-01-08"]
    assert idx.is_monotonic_increasing

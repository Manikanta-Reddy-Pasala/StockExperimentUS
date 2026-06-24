from __future__ import annotations
import pandas as pd
import pytest
from tools.pull_yfinance_history import pit_symbols, build_rows


def test_pit_symbols_unique_from_membership(tmp_path):
    csv = tmp_path / "m.csv"
    csv.write_text(
        "symbol,start_date,end_date\n"
        "AAPL,2016-01-01,\n"
        "MSFT,2016-01-01,2020-01-01\n"
        "AAPL,2021-01-01,\n"
    )
    assert pit_symbols(str(csv)) == ["AAPL", "MSFT"]


def test_build_rows_maps_yf_columns():
    df = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5],
         "Adj Close": [1.4], "Volume": [1000]},
        index=pd.to_datetime(["2018-03-01"]),
    )
    rows = build_rows("AAPL", df)
    assert len(rows) == 1
    r = rows[0]
    assert r["sym"] == "AAPL" and r["c"] == 1.5 and r["ac"] == 1.4 and r["v"] == 1000
    assert str(r["d"]) == "2018-03-01"

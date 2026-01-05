import pandas as pd

from app.services import business_metrics


def test_safe_ratio_handles_zero():
    assert business_metrics._safe_ratio(10, 0) is None
    assert business_metrics._safe_ratio(10, None) is None
    assert business_metrics._safe_ratio(10, 5) == 2.0


def test_drawdown_calculation():
    navs = pd.Series([100000, 110000, 90000])
    current, dd = business_metrics._drawdown(navs)
    assert current == 90000
    assert round(dd, 4) == -0.1818


def test_consistency_last_13():
    dates = pd.date_range("2024-01-01", periods=20, freq="W")
    juice = [100] * 10 + [-50] * 10
    trades = pd.DataFrame({"date": dates, "juice": juice})
    pct, avg = business_metrics._consistency(trades, weeks=13)
    assert pct <= 100
    assert avg != 0


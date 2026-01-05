import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models.business import BasePosition, PositionMetrics, PillarSeriesPoint
from app.services import business_metrics
from main import app


def _pm(symbol: str, original: float, current: float, protection: float, net_juice: float) -> PositionMetrics:
    return PositionMetrics(
        position=BasePosition(
            position_id=f"{symbol}-1",
            account="Test",
            symbol=symbol,
            strategy="CFM",
            base_type="SHARES",
            opened_date=pd.Timestamp("2024-01-01").date(),
        ),
        base_value=current,
        base_cost=original,
        initial_base_cost=original,
        net_intrinsic_to_date=protection,
        net_juice_to_date=net_juice,
    )


@pytest.fixture
def mock_portfolio(monkeypatch):
    positions = [
        _pm("AAA", original=1000, current=1200, protection=100, net_juice=300),
        _pm("BBB", original=2000, current=1800, protection=0, net_juice=200),
    ]

    monkeypatch.setattr(business_metrics, "position_metrics", lambda account=None, include_closed=False: positions)
    monkeypatch.setattr(
        business_metrics.business_loader,
        "list_nav",
        lambda account=None: pd.DataFrame([{"date": "2024-05-01", "nav_total": 5000}]),
    )
    # Ledger income totals (align with Trades & Ledger)
    ledger_rows = [
        {"ticker": "AAA", "signed_juice_dollars": 300},
        {"ticker": "BBB", "signed_juice_dollars": 200},
    ]
    monkeypatch.setattr(business_metrics.excel_loader, "get_ledger_rows", lambda account=None: ledger_rows)
    trades = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=4, freq="W"), "juice": [100, -50, 0, 25], "ticker": ["AAA"] * 4})
    monkeypatch.setattr(business_metrics.excel_loader, "get_all_trades", lambda account=None: trades)
    monkeypatch.setattr(
        business_metrics,
        "_income_series_by_week",
        lambda account=None, symbol=None: [PillarSeriesPoint(period_start=pd.Timestamp("2024-01-01").date(), value=100.0)],
    )
    return positions


def test_portfolio_summary_weighted(mock_portfolio):
    summary = business_metrics.portfolio_summary("Test")
    # Weighted base strength: (1300 + 1800) / (1000 + 2000) = 1.0333
    assert round(summary.total_base_strength_ratio, 3) == pytest.approx(1.033, rel=1e-3)
    # Growth numerator cancels out (200 gain + 200 loss)
    assert summary.total_base_growth_pct == pytest.approx(0.0)
    # Income is gated to restore base: AAA covered, BBB shortfall consumes its income
    assert summary.total_income_realized == 300
    assert len(summary.stocks) == 2


def test_stock_detail_pillars(mock_portfolio):
    detail = business_metrics.stock_detail("AAA", account="Test")
    assert detail.ticker == "AAA"
    assert detail.base_strength_ratio == pytest.approx((1200 + 100) / 1000)
    assert detail.base_growth_pct == pytest.approx((1200 - 1000) / 1000)
    assert detail.income_total_realized == 300
    assert detail.income_series_weekly, "Expect placeholder income series"
    assert detail.positions, "Positions should be returned for the ticker"


def test_api_drilldown(monkeypatch, mock_portfolio):
    client = TestClient(app)
    response = client.get("/api/portfolio-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_income_realized"] == 500
    assert len(body["stocks"]) == 2

    stock_resp = client.get("/api/stocks/AAA")
    assert stock_resp.status_code == 200
    stock = stock_resp.json()
    assert stock["ticker"] == "AAA"
    assert stock["income_total_realized"] == 300

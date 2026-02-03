import pandas as pd

from app.services import business_metrics


def test_ticket_health_bands():
    assert business_metrics.compute_ticket_health(95, 0.9) == "A"
    assert business_metrics.compute_ticket_health(95, 0.8) == "A"
    assert business_metrics.compute_ticket_health(95, None) == "A"
    assert business_metrics.compute_ticket_health(75, 0.8) == "B"
    assert business_metrics.compute_ticket_health(75, None) == "B"
    assert business_metrics.compute_ticket_health(75, 0.7) == "C"
    assert business_metrics.compute_ticket_health(50, 0.9) == "C"


def test_conviction_mapping():
    assert business_metrics.compute_conviction("GREEN", "GREEN") == "HIGH"
    assert business_metrics.compute_conviction("YELLOW", "GREEN") == "MED"
    assert business_metrics.compute_conviction("GREEN", "YELLOW") == "MED"
    assert business_metrics.compute_conviction("RED", "GREEN") == "LOW"
    assert business_metrics.compute_conviction("GREEN", "RED") == "LOW"


def test_operating_posture_mapping():
    assert business_metrics.compute_operating_posture("LOW", "A") == "DEFEND"
    assert business_metrics.compute_operating_posture("HIGH", "A") == "ATTACK"
    assert business_metrics.compute_operating_posture("HIGH", "B") == "ATTACK"
    assert business_metrics.compute_operating_posture("MED", "A") == "MANAGE"
    assert business_metrics.compute_operating_posture("HIGH", "C") == "DEFEND"


def test_net_juice_current_month_grouping(monkeypatch):
    def fake_rows(account=None):
        return [
            {
                "account": "A",
                "date": "2026-01-05",
                "action": "CLOSE",
                "side": "CALL",
                "ticker": "NVDA",
                "contracts": 1,
                "strike": 100,
                "expiry": "2026-01-17",
                "premium_buyback": 2,
                "signed_juice_dollars": 50,
                "base_position_id": "P1",
            },
            {
                "account": "A",
                "date": "2026-01-05",
                "action": "CLOSE",
                "side": "CALL",
                "ticker": "NVDA",
                "contracts": 1,
                "strike": 100,
                "expiry": "2026-01-17",
                "premium_buyback": 2,
                "signed_juice_dollars": 25,
                "base_position_id": "P2",
            },
            {
                "account": "A",
                "date": "2026-01-05",
                "action": "CLOSE",
                "side": "CALL",
                "ticker": "NVDA",
                "contracts": 1,
                "strike": 100,
                "expiry": "2026-02-14",
                "premium_buyback": 2,
                "signed_juice_dollars": 100,
                "base_position_id": "P1",
            },
        ]

    monkeypatch.setattr(business_metrics.excel_loader, "get_ledger_rows", fake_rows)
    today = pd.Timestamp("2026-01-10").date()
    assert business_metrics.get_net_juice_current_month_by_expiry("A", "P1", today) == 50.0
    assert business_metrics.get_net_juice_current_month_by_expiry("A", "P2", today) == 25.0

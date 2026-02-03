import pandas as pd

from app.services import business_metrics


def _ledger_row(**kwargs):
    base = {
        "account": "A",
        "ticker": "XYZ",
        "action": "CLOSE",
        "side": "CALL",
        "contracts": 1,
        "strike": 100,
        "expiry": "2024-01-19",
        "premium_buyback": None,
        "signed_juice_dollars": 100.0,
        "base_position_id": "P1",
        "date": "2024-01-05",
    }
    base.update(kwargs)
    return base


def test_net_juice_current_month_by_expiry_month():
    rows = [
        _ledger_row(expiry="2024-01-19", signed_juice_dollars=100.0, base_position_id="P1"),
        _ledger_row(expiry="2024-02-16", signed_juice_dollars=200.0, base_position_id="P1"),
        _ledger_row(expiry="2024-01-26", signed_juice_dollars=50.0, base_position_id="P1", action="OPEN"),
        _ledger_row(expiry="2024-01-19", signed_juice_dollars=999.0, base_position_id=None),
    ]
    positions_df = pd.DataFrame(
        [
            {"position_id": "P1", "strategy": "CFM"},
        ]
    )
    today = pd.Timestamp("2024-01-10").date()
    result = business_metrics._net_juice_current_month_by_position(rows, positions_df, today)
    assert result["P1"] == 100.0


def test_net_juice_current_month_groups_by_position():
    rows = [
        _ledger_row(expiry="2024-01-19", signed_juice_dollars=100.0, base_position_id="P1"),
        _ledger_row(expiry="2024-01-19", signed_juice_dollars=40.0, base_position_id="P2"),
    ]
    positions_df = pd.DataFrame(
        [
            {"position_id": "P1", "strategy": "CFM"},
            {"position_id": "P2", "strategy": "CFM"},
        ]
    )
    today = pd.Timestamp("2024-01-10").date()
    result = business_metrics._net_juice_current_month_by_position(rows, positions_df, today)
    assert result["P1"] == 100.0
    assert result["P2"] == 40.0


def test_strength_status_rules():
    assert business_metrics._strength_status("GREEN", 100, None, False) == "Healthy"
    assert business_metrics._strength_status("GREEN", 70, None, False) == "Healthy"
    assert business_metrics._strength_status("GREEN", 70, 0.8, False) == "Watch"
    assert business_metrics._strength_status("GREEN", 50, None, False) == "Weak"

    assert business_metrics._strength_status("YELLOW", 100, None, False) == "Healthy"
    assert business_metrics._strength_status("YELLOW", 70, 0.7, False) == "Watch"
    assert business_metrics._strength_status("YELLOW", 50, None, False) == "Weak"

    assert business_metrics._strength_status("RED", 100, 0.9, False) == "Healthy"
    assert business_metrics._strength_status("RED", 100, 0.8, False) == "Watch"
    assert business_metrics._strength_status("RED", 70, 0.9, False) == "Watch"
    assert business_metrics._strength_status("RED", 70, None, False) == "Weak"

    assert business_metrics._strength_status("UNKNOWN", 100, None, False) == "Watch"
    assert business_metrics._strength_status("GREEN", None, None, False) == "Watch"


def test_active_long_leg_stats_uses_worst_case():
    legs = pd.DataFrame(
        [
            {
                "base_leg_id": "L1",
                "instrument_type": "CALL",
                "side": "BUY",
                "expiry": "2024-04-19",
                "delta": 0.9,
                "tag": "OPEN",
            },
            {
                "base_leg_id": "L2",
                "instrument_type": "CALL",
                "side": "BUY",
                "expiry": "2024-03-15",
                "delta": 0.7,
                "tag": "OPEN",
            },
        ]
    )
    today = pd.Timestamp("2024-01-10").date()
    dte_worst, delta_worst, dte_worst_dup, dte_avg, delta_avg, ambiguous = business_metrics._active_long_leg_stats(legs, today)
    assert ambiguous is False
    assert dte_worst == dte_worst_dup
    assert dte_worst == 65
    assert round(dte_avg, 1) == 82.5
    assert delta_worst == 0.7
    assert round(delta_avg, 2) == 0.8

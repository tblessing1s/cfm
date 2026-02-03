import pandas as pd

from app.services import business_metrics


def _open_instance(entry_credit, strike, underlying_entry, underlying_now, mark_premium, expiry):
    return {
        "open": {
            "premium_buyback": entry_credit,
            "strike": strike,
            "underlying": underlying_entry,
            "side": "CALL",
            "contracts": 1,
            "expiry": expiry,
        },
        "mark": {
            "premium_buyback": mark_premium,
            "underlying": underlying_now,
        },
    }


def test_yellow_otm_floor_hang(monkeypatch):
    open_instances = [
        _open_instance(
            entry_credit=8,
            strike=100,
            underlying_entry=105,
            underlying_now=98,
            mark_premium=4,
            expiry=pd.Timestamp.now().normalize() + pd.Timedelta(days=7),
        )
    ]
    plan_settings = {
        "capture_target_pct": 0.7,
        "min_dte_to_roll": 3,
        "cheap_buyback_threshold": 0.3,
        "hang_timer_max": 2,
    }
    monkeypatch.setattr(business_metrics, "_latest_stock_closes", lambda symbol: (98.0, 99.0))

    result = business_metrics._short_signals_for_position(
        open_instances,
        "AAPL",
        cushion=0.0,
        safety_reserve=0.0,
        plan_settings=plan_settings,
        regime_condition="YELLOW",
        breaker_status="None",
    )
    _, _, _, _, recommended_action, rule_triggered, _ = result
    assert recommended_action == "HANG_BY_JUICE"
    assert rule_triggered == "YELLOW_HANG_OK"


def test_capture_pct_roll_eligible(monkeypatch):
    open_instances = [
        _open_instance(
            entry_credit=10,
            strike=100,
            underlying_entry=100,
            underlying_now=100,
            mark_premium=2,
            expiry=pd.Timestamp.now().normalize() + pd.Timedelta(days=10),
        )
    ]
    plan_settings = {
        "capture_target_pct": 0.7,
        "min_dte_to_roll": 3,
        "cheap_buyback_threshold": 0.3,
        "hang_timer_max": 2,
    }
    monkeypatch.setattr(business_metrics, "_latest_stock_closes", lambda symbol: (100.0, 100.0))

    result = business_metrics._short_signals_for_position(
        open_instances,
        "AAPL",
        cushion=0.0,
        safety_reserve=0.0,
        plan_settings=plan_settings,
        regime_condition="GREEN",
        breaker_status="None",
    )
    _, _, _, _, recommended_action, rule_triggered, _ = result
    assert recommended_action == "ROLL_EARLY"
    assert "ROLL_EARLY_CAPTURE_80" in rule_triggered

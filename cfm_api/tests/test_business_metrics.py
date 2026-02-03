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


def _ledger_row(**kwargs):
    base = {
        "account": "A",
        "ticker": "XYZ",
        "side": "CALL",
        "contracts": 1,
        "strike": 100,
        "expiry": "2024-02-16",
        "premium_buyback": None,
        "underlying": 95,
        "base_position_id": "P1",
        "base_leg_id": "",
        "condition": "",
        "key": "",
        "row_number": None,
        "date": "2024-01-02",
    }
    base.update(kwargs)
    return base


def _layered_fixture_rows():
    rows = [
        _ledger_row(
            action="OPEN",
            base_leg_id="L1",
            contracts=1,
            premium_buyback=12,
            row_number=1,
            date="2024-01-01",
        ),
        _ledger_row(
            action="MARK",
            base_leg_id="L1",
            contracts=1,
            premium_buyback=10,
            row_number=2,
            date="2024-01-05",
        ),
        _ledger_row(
            action="OPEN",
            key="S1",
            contracts=1,
            premium_buyback=2,
            row_number=3,
            date="2024-01-02",
        ),
        _ledger_row(
            action="CLOSE",
            key="S1",
            contracts=1,
            premium_buyback=1,
            row_number=4,
            date="2024-01-03",
        ),
        _ledger_row(
            action="OPEN",
            key="S2",
            contracts=2,
            premium_buyback=2,
            row_number=5,
            date="2024-01-04",
        ),
        _ledger_row(
            action="MARK",
            key="S2",
            contracts=2,
            premium_buyback=1,
            row_number=6,
            date="2024-01-05",
        ),
    ]
    row_number = 10
    for i in range(10):
        rows.append(
            _ledger_row(
                action="OPEN",
                key=f"R{i}",
                contracts=1,
                premium_buyback=2,
                row_number=row_number,
                date="2024-01-06",
            )
        )
        rows.append(
            _ledger_row(
                action="CLOSE",
                key=f"R{i}",
                contracts=1,
                premium_buyback=2,
                row_number=row_number + 1,
                date="2024-01-06",
            )
        )
        rows.append(
            _ledger_row(
                action="OPEN",
                key=f"RN{i}",
                contracts=1,
                premium_buyback=1,
                row_number=row_number + 2,
                date="2024-01-06",
            )
        )
        row_number += 3
    return rows


def test_layered_snapshot_calculations():
    rows = _layered_fixture_rows()
    df = business_metrics._normalize_ledger_df(rows)
    base_leg_ids = ["L1"]
    principal_cost = business_metrics._base_open_cost_from_ledger(df, base_leg_ids)
    long_value = business_metrics._base_mark_value_from_ledger(df, base_leg_ids)
    week_start = pd.Timestamp("2024-01-01")
    week_end = week_start + pd.Timedelta(days=7)
    snapshot = business_metrics._position_layer_snapshot(
        df,
        base_leg_ids,
        principal_cost,
        long_value,
        week_bounds=(week_start, week_end),
    )

    assert principal_cost == 1200.0
    assert long_value == 1000.0
    assert snapshot["short_realized_pnl"] == 100.0
    assert snapshot["short_unrealized_pnl"] == 200.0
    assert snapshot["liquidation_value"] == 1300.0
    assert snapshot["protected_now"] is True

    short_snapshot = snapshot["short_snapshot"]
    assert short_snapshot["debit_cap"] == 150.0
    assert short_snapshot["safety_reserve"] == 300.0
    assert snapshot["withdrawable_now"] == 0.0
    assert short_snapshot["open_short_contracts"] == 2.0
    assert short_snapshot["weekly_defense_debit"] == 1000.0
    assert all(val == 100.0 for val in short_snapshot["last10_defense_debits"])


def test_protected_now_flips_with_mark_change():
    rows = _layered_fixture_rows()
    for row in rows:
        if row.get("action") == "MARK" and row.get("base_leg_id") == "L1":
            row["premium_buyback"] = 6
    df = business_metrics._normalize_ledger_df(rows)
    base_leg_ids = ["L1"]
    principal_cost = business_metrics._base_open_cost_from_ledger(df, base_leg_ids)
    long_value = business_metrics._base_mark_value_from_ledger(df, base_leg_ids)
    snapshot = business_metrics._position_layer_snapshot(df, base_leg_ids, principal_cost, long_value)
    assert snapshot["protected_now"] is False

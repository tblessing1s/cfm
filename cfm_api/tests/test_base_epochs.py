import pandas as pd

from app.services import business_metrics
from app.utils import business_loader, excel_loader
import pytest

pytest.skip("base epochs removed", allow_module_level=True)


def test_base_epoch_created_on_open(tmp_path, monkeypatch):
    legs_store = business_loader.CsvStore(tmp_path / "base_legs.csv", business_loader.legs_store.fieldnames)
    epochs_store = business_loader.CsvStore(tmp_path / "base_epochs.csv", business_loader.base_epochs_store.fieldnames)
    monkeypatch.setattr(business_loader, "legs_store", legs_store)
    monkeypatch.setattr(business_loader, "base_epochs_store", epochs_store)

    payload = {
        "base_leg_id": "L1",
        "position_id": "P1",
        "date": "2024-01-02",
        "instrument_type": "SHARES",
        "side": "BUY",
        "quantity": 10,
        "price": 100,
        "fees": 1,
        "amount": 1000,
        "tag": "OPEN",
    }
    row = business_loader.add_base_leg(payload)
    assert row.get("base_epoch_id")

    epochs = epochs_store.load()
    assert not epochs.empty
    epoch = epochs.iloc[0]
    assert str(epoch["position_id"]) == "P1"
    assert float(epoch["base_cost_basis_locked"]) == 1001.0


def test_weekly_engine_return_pct(monkeypatch):
    positions_df = pd.DataFrame(
        [
            {
                "position_id": "P1",
                "account": "Test",
                "symbol": "AAPL",
                "strategy": "CFM",
                "base_type": "SHARES",
                "opened_date": "2024-01-01",
                "closed_date": None,
            }
        ]
    )
    base_epochs_df = pd.DataFrame(
        [
            {
                "base_epoch_id": "E1",
                "position_id": "P1",
                "start_date": "2024-01-01",
                "end_date": None,
                "base_cost_basis_locked": 1000,
                "entry_base_leg_id": "L1",
                "note": None,
            }
        ]
    )
    legs_df = pd.DataFrame(
        columns=[
            "base_leg_id",
            "position_id",
            "date",
            "time",
            "instrument_type",
            "side",
            "quantity",
            "strike",
            "expiry",
            "price",
            "fees",
            "amount",
            "tag",
        ]
    )
    monkeypatch.setattr(business_loader, "list_positions", lambda account=None: positions_df)
    monkeypatch.setattr(business_loader, "list_reserves", lambda position_id=None: pd.DataFrame())
    monkeypatch.setattr(business_loader, "list_replacement_costs", lambda position_id=None: pd.DataFrame())
    monkeypatch.setattr(business_loader, "list_base_epochs", lambda position_id=None: base_epochs_df)
    monkeypatch.setattr(business_loader, "list_base_legs", lambda position_id=None: legs_df)

    ledger_rows = [
        {
            "account": "Test",
            "date": "2024-01-02",
            "action": "CLOSE",
            "side": "CALL",
            "ticker": "AAPL",
            "contracts": 1,
            "strike": 100,
            "expiry": "2024-02-16",
            "premium_buyback": 10,
            "underlying": 90,
            "base_position_id": "P1",
            "base_epoch_id": "E1",
            "base_leg_id": "L1",
        }
    ]
    monkeypatch.setattr(excel_loader, "get_ledger_rows", lambda account=None: ledger_rows)

    metrics = business_metrics.position_metrics(account="Test")
    assert metrics
    pm = metrics[0]
    assert pm.weekly_return_pct == 0.01

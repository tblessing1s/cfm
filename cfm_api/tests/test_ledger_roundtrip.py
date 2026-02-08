import datetime as dt

import openpyxl
import pytest

from app.models.trade import LedgerEntryCreate
from app.services import trade_service
from app.utils import excel_loader


def _make_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ledger"
    ws.append(
        [
            "Account",
            "Date",
            "Action",
            "Symbol",
            "Contracts",
            "Strike",
            "Expiry",
            "Premium/Buyback",
            "Underlying",
            "Side",
            "Key",
        ]
    )
    wb.save(path)


def test_ledger_roundtrip_underlying_fees_condition(monkeypatch, tmp_path):
    path = tmp_path / "Juice_Ledger_Test.xlsx"
    _make_workbook(path)

    descriptor = excel_loader._AccountInfo(name="Test", label="Test", path=path)
    monkeypatch.setattr(excel_loader, "_resolve_account", lambda account=None: descriptor)

    entries = [
        {
            "account": "Test",
            "ticker": "AAA",
            "action": "OPEN",
            "strategy": "CFM",
            "side": "Call",
            "contracts": 1,
            "strike": 100,
            "expiry": "2026-01-31",
            "trade_datetime": "2026-01-10T09:30:00",
            "premium": 2.5,
            "underlying": 101.0,
            "fees": 0.75,
            "condition": "OPEN_WEEKLY",
            "base_position_id": "pos-1",
            "base_leg_id": "leg-1",
        }
    ]

    excel_loader.append_ledger_entries(entries)
    rows = excel_loader.get_ledger_rows("Test")

    open_rows = [row for row in rows if (row.get("action") or "").upper() == "OPEN"]
    assert open_rows, "Expected an OPEN row in ledger"
    row = open_rows[0]
    assert row["underlying"] == pytest.approx(101.0)
    assert row["fees"] == pytest.approx(0.75)
    assert row["condition"] == "OPEN_WEEKLY"
    assert row["base_position_id"] == "pos-1"


def test_cfm_requires_base_position_and_underlying(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("append_ledger_entries should not be called when validation fails")

    monkeypatch.setattr(excel_loader, "append_ledger_entries", _fail_if_called)

    entry = LedgerEntryCreate(
        account="Test",
        ticker="AAA",
        action="Open",
        strategy="CFM",
        side="Call",
        contracts=1,
        strike=100,
        expiry=dt.date(2026, 1, 31),
        trade_datetime=dt.datetime(2026, 1, 10, 9, 30),
        premium=2.5,
        underlying=None,
        base_position_id=None,
    )

    with pytest.raises(RuntimeError):
        trade_service.append_ledger_entries([entry])

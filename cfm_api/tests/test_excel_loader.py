import openpyxl
from app.utils import excel_loader


def _make_ledger(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ledger"
    headers = [
        "Account",
        "Date",
        "Action",
        "Symbol",
        "Contracts",
        "Strike",
        "Expiry",
        "Premium/Buyback",
        "Underlying",
        "Base Position Id",
        "Base Leg Id",
        "Key",
        "Side",
    ]
    ws.append(headers)
    wb.save(path)


def test_ledger_roundtrip_underlying_base_ids(tmp_path, monkeypatch):
    ledger_path = tmp_path / "Juice_Ledger_Test.xlsx"
    _make_ledger(ledger_path)

    monkeypatch.setattr(excel_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(excel_loader, "JOURNAL_ROOT", tmp_path)
    monkeypatch.setattr(excel_loader, "ALPHA_CACHE_DIR", tmp_path / "alpha_cache")
    monkeypatch.setattr(excel_loader, "UI_TRADES_FILE", tmp_path / "ui_trades.csv")

    entry = {
        "account": "Juice_Ledger_Test",
        "ticker": "AAPL",
        "action": "Open",
        "strategy": "CFM",
        "side": "Call",
        "contracts": 1,
        "strike": 100,
        "expiry": "2024-02-16",
        "trade_datetime": "2024-01-02T09:30:00",
        "premium": 1.23,
        "underlying": 101.5,
        "base_position_id": "P1",
        "base_leg_id": "L1",
    }

    appended = excel_loader.append_ledger_entries([entry])
    assert appended

    rows = excel_loader.get_ledger_rows("Juice_Ledger_Test")
    assert rows
    latest = rows[-1]
    assert latest["underlying"] == 101.5
    assert latest["base_position_id"] == "P1"
    assert latest["base_leg_id"] == "L1"


def test_ledger_allows_missing_underlying(tmp_path, monkeypatch):
    ledger_path = tmp_path / "Juice_Ledger_Test.xlsx"
    _make_ledger(ledger_path)

    monkeypatch.setattr(excel_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(excel_loader, "JOURNAL_ROOT", tmp_path)
    monkeypatch.setattr(excel_loader, "ALPHA_CACHE_DIR", tmp_path / "alpha_cache")

    entry = {
        "account": "Juice_Ledger_Test",
        "ticker": "AAPL",
        "action": "Open",
        "strategy": "CFM",
        "side": "Call",
        "contracts": 1,
        "strike": 100,
        "expiry": "2024-02-16",
        "trade_datetime": "2024-01-02T09:30:00",
        "premium": 1.23,
        "base_position_id": "P1",
        "base_leg_id": "L1",
    }

    appended = excel_loader.append_ledger_entries([entry])
    assert appended

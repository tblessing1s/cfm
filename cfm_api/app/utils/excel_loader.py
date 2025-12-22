"""Helpers for loading trade data from per-account ledgers."""
from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Any, Dict, List, Union

import numpy as np
import pandas as pd
import openpyxl

BASE_DIR = Path(__file__).resolve().parents[3]
LEDGER_DIR = BASE_DIR / "cfm_journal"
LEDGER_PATTERN = "Juice_Ledger*.xlsx"
UI_TRADES_FILE = LEDGER_DIR / "ui_trades.csv"


@dataclass(frozen=True)
class _AccountInfo:
    name: str
    label: str
    path: Path


def _friendly_label(stem: str) -> str:
    normalized = stem.lower()
    prefix = "juice_ledger_"

    if normalized.startswith(prefix):
        label = stem[len(prefix):]
    elif normalized == "juice_ledger":
        label = ""
    else:
        label = stem

    label = label.replace("_", " ").strip()
    if not label:
        return "CFM Combined"
    return label.title()


def _discover_accounts() -> List[_AccountInfo]:
    if not LEDGER_DIR.exists():
        raise FileNotFoundError(f"Ledger directory not found at {LEDGER_DIR}")

    ledger_paths = [
        path
        for path in sorted(LEDGER_DIR.glob(LEDGER_PATTERN))
        if path.stem.lower() not in {"juice_ledger"}  # skip the template
    ]
    if not ledger_paths:
        raise FileNotFoundError(f"No ledger files found under {LEDGER_DIR}")

    return [_AccountInfo(name=path.stem, label=_friendly_label(path.stem), path=path) for path in ledger_paths]


def _resolve_account(account: str | None) -> _AccountInfo:
    descriptors = _discover_accounts()
    lookup: Dict[str, _AccountInfo] = {}

    for descriptor in descriptors:
        lookup[descriptor.name.lower()] = descriptor
        lookup[descriptor.label.lower()] = descriptor
        if descriptor.label.lower() == "cfm combined":
            for alias in ("combined", "all"):
                lookup[alias] = descriptor

    if account:
        normalized = account.strip().lower()
        candidate = lookup.get(normalized)
        if candidate:
            return candidate
        raise ValueError(f"No ledger matches account '{account}'")

    return descriptors[0]


def _normalize_columns(columns: List[str]) -> List[str]:
    return [col.strip().lower().replace(" ", "_") for col in columns]


def _serialize_date(value: pd.Timestamp | None) -> str | None:
    if value is pd.NaT or value is None:
        return None
    return value.date().isoformat()


def _load_trades(account: str | None = None) -> pd.DataFrame:
    account_descriptor = _resolve_account(account)
    df = pd.read_excel(account_descriptor.path, engine="openpyxl")
    df.columns = _normalize_columns(df.columns.tolist())

    if "date" not in df.columns:
        raise KeyError("Expected a 'date' column in trades Excel file")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    ui_trades = _load_ui_trades(account_descriptor.name)
    if not ui_trades.empty:
        df = pd.concat([df, ui_trades], ignore_index=True, sort=False)

    return df


def get_available_accounts() -> List[Dict[str, str]]:
    return [
        {"name": descriptor.name, "label": descriptor.label}
        for descriptor in _discover_accounts()
    ]


def get_all_trades(account: str | None = None) -> pd.DataFrame:
    df = _load_trades(account).copy()
    df = _ensure_core_columns(df)
    df = _normalize_missing(df)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.drop(columns=["notes"], errors="ignore")


def _ensure_core_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    column_defaults: Dict[str, Union[float, str, None]] = {
        "ticker": "",
        "strategy": "CFM",
        "juice": 0.0,
        "basis": 0.0,
        "premium_in": None,
        "premium_out": None,
        "dte": None,
        "itm": None,
    }

    for column, default in column_defaults.items():
        if column not in df.columns:
            df[column] = default

    df["juice"] = pd.to_numeric(df["juice"], errors="coerce").fillna(0.0)
    df["basis"] = pd.to_numeric(df["basis"], errors="coerce").fillna(0.0)
    df["premium_in"] = pd.to_numeric(df["premium_in"], errors="coerce")
    df["premium_out"] = pd.to_numeric(df["premium_out"], errors="coerce")
    df["dte"] = pd.to_numeric(df["dte"], errors="coerce").astype("Int64")

    return df


def _normalize_missing(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    return df.replace({np.nan: None})


def _compute_juice_fields(record: Dict[str, Any]) -> Dict[str, Any]:
    """Compute juice per contract and signed juice fields similar to the Excel formulas."""
    action = str(record.get("action") or "Open").upper()
    side = str(record.get("side") or "Call").strip().lower()
    strike = record.get("strike")
    underlying = record.get("underlying")
    premium = record.get("premium_buyback")
    contracts = record.get("contracts")

    def to_float(val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    strike_f = to_float(strike)
    underlying_f = to_float(underlying)
    premium_f = to_float(premium)
    contracts_i = None
    try:
        contracts_i = int(contracts) if contracts is not None else None
    except (TypeError, ValueError):
        contracts_i = None

    juice_per_contract = None

    if premium_f is not None:
        if strike_f is not None and underlying_f is not None:
            intrinsic = max(0, strike_f - underlying_f) if "put" in side else max(0, underlying_f - strike_f)
            extrinsic = premium_f - intrinsic
            if action == "CLOSE":
                juice_per_contract = abs(extrinsic) if extrinsic < 0 else -extrinsic
            else:
                juice_per_contract = extrinsic
        else:
            if action == "CLOSE":
                juice_per_contract = abs(premium_f) if premium_f < 0 else -premium_f
            else:
                juice_per_contract = premium_f

    signed_juice_dollars = None
    signed_juice_per_100 = None

    if juice_per_contract is not None and contracts_i is not None:
        signed_juice_dollars = round(juice_per_contract * contracts_i, 2)
        signed_juice_per_100 = round(signed_juice_dollars * 100, 2)

    def r2(val):
        return round(val, 2) if isinstance(val, (int, float)) else val

    return {
        "juice_per_contract": r2(juice_per_contract) if juice_per_contract is not None else None,
        "signed_juice_dollars": r2(signed_juice_dollars) if signed_juice_dollars is not None else None,
        "signed_juice_per_100": r2(signed_juice_per_100) if signed_juice_per_100 is not None else None,
    }


def resolve_account_name(account: str | None) -> str:
    """Return the canonical account name used on disk, validating the input."""
    descriptor = _resolve_account(account)
    return descriptor.name


def resolve_account(account: str | None) -> _AccountInfo:
    """Return the full account descriptor including the ledger path."""
    return _resolve_account(account)


def _load_ui_trades(account_name: str | None) -> pd.DataFrame:
    """Load UI-submitted trades stored in a lightweight CSV."""
    if not UI_TRADES_FILE.exists():
        return pd.DataFrame()

    df = pd.read_csv(UI_TRADES_FILE)
    if df.empty:
        return df

    df.columns = _normalize_columns(df.columns.tolist())
    if account_name and "account" in df.columns:
        df = df[df["account"].astype(str).str.lower() == account_name.lower()]

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def append_ui_trades(rows: List[Dict[str, Any]]) -> int:
    """Append UI-submitted trades to a simple CSV store under cfm_journal."""
    if not rows:
        return 0

    UI_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "account",
        "date",
        "ticker",
        "strategy",
        "premium_in",
        "premium_out",
        "juice",
        "basis",
        "dte",
        "itm",
    ]
    exists = UI_TRADES_FILE.exists()

    with UI_TRADES_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()

        for row in rows:
            normalized = {k: row.get(k) for k in fieldnames}
            writer.writerow(normalized)

    return len(rows)


def append_ledger_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Append ledger rows directly into the XLSX for each account."""
    if not entries:
        return []

    appended_rows: List[Dict[str, Any]] = []
    for entry in entries:
        descriptor = resolve_account(entry.get("account"))
        wb = openpyxl.load_workbook(descriptor.path)
        ws = wb["Ledger"]
        cols = _get_ledger_columns(ws)
        r = ws.max_row + 1

        ticker = str(entry.get("ticker") or "").upper()
        action = str(entry.get("action") or "Open").capitalize()
        side = str(entry.get("side") or "Call").capitalize()
        contracts = int(entry.get("contracts"))
        strike = entry.get("strike")
        premium = entry.get("premium")
        underlying = entry.get("underlying")
        expiry = pd.to_datetime(entry.get("expiry"), errors="coerce").date()
        trade_dt = pd.to_datetime(entry.get("trade_datetime"), errors="coerce").to_pydatetime()

        account_label = descriptor.label
        if "christie" in descriptor.name.lower():
            account_label = "Christie"
        elif "travis" in descriptor.name.lower():
            account_label = "Travis"

        key = _build_key(ticker, strike, expiry, side, action)

        if "Account" in cols:
            ws.cell(row=r, column=cols["Account"], value=account_label)
        if "Date" in cols:
            ws.cell(row=r, column=cols["Date"], value=trade_dt)
        if "Action" in cols:
            ws.cell(row=r, column=cols["Action"], value=action)
        if "Symbol" in cols:
            ws.cell(row=r, column=cols["Symbol"], value=ticker)
        if "Contracts" in cols:
            ws.cell(row=r, column=cols["Contracts"], value=contracts)
        if "Strike" in cols:
            ws.cell(row=r, column=cols["Strike"], value=strike)
        if "Expiry" in cols:
            ws.cell(row=r, column=cols["Expiry"], value=expiry)
        if "Premium/Buyback" in cols:
            ws.cell(row=r, column=cols["Premium/Buyback"], value=premium)
        if "Underlying" in cols:
            ws.cell(row=r, column=cols["Underlying"], value=underlying)
        if "Key" in cols:
            ws.cell(row=r, column=cols["Key"], value=key)
        if "Side" in cols:
            ws.cell(row=r, column=cols["Side"], value=side)

        wb.save(descriptor.path)

        appended_rows.append(
            {
                "account": descriptor.name,
                "date": trade_dt.date().isoformat() if hasattr(trade_dt, "date") else None,
                "action": action,
                "side": side,
                "ticker": ticker,
                "contracts": contracts,
                "strike": strike,
                "expiry": expiry.isoformat() if expiry else None,
                "premium_buyback": premium,
                "underlying": underlying,
                "juice_per_contract": None,
                "signed_juice_dollars": None,
                "signed_juice_per_100": None,
                "key": key,
                "notes": None,
            }
        )

    return appended_rows


def _get_ledger_columns(ws) -> Dict[str, int]:
    headers = {}
    for cell in ws[1]:
        if cell.value is None:
            continue
        headers[str(cell.value).strip().lower()] = cell.column

    aliases = {
        "account": "Account",
        "date": "Date",
        "action": "Action",
        "symbol": "Symbol",
        "contracts": "Contracts",
        "strike": "Strike",
        "expiry": "Expiry",
        "premium/buyback": "Premium/Buyback",
        "underlying": "Underlying",
        "key": "Key",
        "side": "Side",
    }
    return {target: headers[key] for key, target in aliases.items() if key in headers}


def _build_key(ticker: str, strike: Any, expiry: Any, side: str, action: str) -> str:
    expiry_str = ""
    if hasattr(expiry, "isoformat"):
        expiry_str = expiry.isoformat()
    elif expiry is not None:
        expiry_str = str(expiry)
    return f"{ticker}|{strike}|{expiry_str}|{side.upper()}|{action.upper()}".upper()


def update_ledger_row(account: str, row_number: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing ledger row in the Excel workbook and return the updated record."""
    descriptor = _resolve_account(account)
    wb = openpyxl.load_workbook(descriptor.path)
    ws = wb["Ledger"]
    cols = _get_ledger_columns(ws)

    r = int(row_number)
    if r < 2 or r > ws.max_row:
        raise ValueError(f"Row {r} is out of range for ledger {descriptor.path.name}")

    account_label = descriptor.label
    if "christie" in account_label.lower():
        account_label = "Christie"
    elif "travis" in account_label.lower():
        account_label = "Travis"

    # Write core fields
    if "Account" in cols:
        ws.cell(row=r, column=cols["Account"], value=account_label)
    if "Date" in cols:
        ws.cell(row=r, column=cols["Date"], value=data.get("trade_datetime"))
    if "Action" in cols:
        ws.cell(row=r, column=cols["Action"], value=data.get("action"))
    if "Symbol" in cols:
        ws.cell(row=r, column=cols["Symbol"], value=(data.get("ticker") or "").upper())
    if "Contracts" in cols:
        ws.cell(row=r, column=cols["Contracts"], value=data.get("contracts"))
    if "Strike" in cols:
        ws.cell(row=r, column=cols["Strike"], value=data.get("strike"))
    if "Expiry" in cols:
        ws.cell(row=r, column=cols["Expiry"], value=data.get("expiry"))
    if "Premium/Buyback" in cols:
        ws.cell(row=r, column=cols["Premium/Buyback"], value=data.get("premium"))
    if "Underlying" in cols:
        ws.cell(row=r, column=cols["Underlying"], value=data.get("underlying"))
    if "Side" in cols:
        ws.cell(row=r, column=cols["Side"], value=data.get("side") or "Call")
    if "Key" in cols:
        key = _build_key(
            (data.get("ticker") or "").upper(),
            data.get("strike"),
            data.get("expiry"),
            data.get("side") or "Call",
            data.get("action") or "Open",
        )
        ws.cell(row=r, column=cols["Key"], value=key)
    wb.save(descriptor.path)

    # Return the updated row as a dict matching LedgerRow schema
    updated = {
        "account": descriptor.name,
        "date": data.get("trade_datetime"),
        "action": data.get("action"),
        "side": data.get("side"),
        "ticker": (data.get("ticker") or "").upper(),
        "contracts": data.get("contracts"),
        "strike": data.get("strike"),
        "expiry": data.get("expiry"),
        "premium_buyback": data.get("premium"),
        "underlying": data.get("underlying"),
        "juice_per_contract": None,
        "signed_juice_dollars": None,
        "signed_juice_per_100": None,
        "key": None,
        "notes": None,
        "row_number": r,
    }
    return updated


def get_ledger_rows(account: str | None = None) -> List[Dict[str, Any]]:
    """Load raw ledger rows from the XLSX for display in the UI."""
    descriptor = _resolve_account(account)
    df = pd.read_excel(descriptor.path, engine="openpyxl")
    if df.empty:
        return []

    df.columns = _normalize_columns(df.columns.tolist())
    df = df.replace({np.nan: None})

    # Drop completely empty rows (no ticker)
    if "ticker" in df.columns:
        df = df[df["ticker"].astype(str).str.strip() != ""]

    # Excel row numbers (data starts at row 2 because row 1 is headers)
    df["row_number"] = df.index + 2

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    rename_map = {
        "symbol": "ticker",
        "premium/buyback": "premium_buyback",
        "juice/contract": "juice_per_contract",
        "signed_juice ($)": "signed_juice_dollars",
        "signed_juice (per 100)": "signed_juice_per_100",
    }
    for src, dest in rename_map.items():
        if src in df.columns:
            df[dest] = df[src]

    df["account"] = descriptor.name
    if "contracts" in df.columns:
        df["contracts"] = pd.to_numeric(df["contracts"], errors="coerce").astype("Int64")
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date

    columns = [
        "account",
        "date",
        "action",
        "side",
        "ticker",
        "contracts",
        "strike",
        "expiry",
        "premium_buyback",
        "underlying",
        "juice_per_contract",
        "signed_juice_dollars",
        "signed_juice_per_100",
        "key",
    ]

    available = [col for col in columns if col in df.columns]
    records = df[available].to_dict("records")
    # Ensure all keys exist for consumers
    normalized_records: List[Dict[str, Any]] = []
    for record in records:
        normalized: Dict[str, Any] = {col: record.get(col) for col in columns}
        def r2(val):
            return round(val, 2) if isinstance(val, (int, float)) else val
        contracts_val = normalized.get("contracts")
        if contracts_val is not None:
            try:
                normalized["contracts"] = int(contracts_val)
            except (TypeError, ValueError):
                normalized["contracts"] = None
        date_val = normalized.get("date")
        if hasattr(date_val, "isoformat"):
            try:
                normalized["date"] = date_val.isoformat()
            except Exception:
                normalized["date"] = None
        elif pd.isna(date_val):
            normalized["date"] = None
        expiry_val = normalized.get("expiry")
        if hasattr(expiry_val, "isoformat"):
            try:
                normalized["expiry"] = expiry_val.isoformat()
            except Exception:
                normalized["expiry"] = None
        elif pd.isna(expiry_val):
            normalized["expiry"] = None
        # Keep calculated fields as-is from the ledger (UI will compute display values).
        normalized["juice_per_contract"] = r2(normalized.get("juice_per_contract"))
        normalized["signed_juice_dollars"] = r2(normalized.get("signed_juice_dollars"))
        normalized["signed_juice_per_100"] = r2(normalized.get("signed_juice_per_100"))
        if normalized.get("row_number") is not None:
            try:
                normalized["row_number"] = int(normalized["row_number"])
            except (TypeError, ValueError):
                normalized["row_number"] = None
        else:
            normalized["row_number"] = None
        normalized_records.append(normalized)
    return normalized_records


def get_trades_for_current_week(account: str | None = None) -> pd.DataFrame:
    trades = get_all_trades(account)
    if trades.empty:
        return trades

    today = pd.Timestamp.now().normalize()
    start_of_week = today - pd.to_timedelta(today.weekday(), unit="D")
    end_of_week = start_of_week + pd.Timedelta(days=7)

    mask = (trades["date"] >= start_of_week) & (trades["date"] < end_of_week)
    return trades.loc[mask].copy()


def get_weekly_summary(account: str | None = None) -> pd.DataFrame:
    trades = get_all_trades(account)
    if trades.empty:
        return trades

    trades = trades.copy()
    trades["date"] = pd.to_datetime(trades["date"], errors="coerce")

    working = trades.copy()
    working["week_start"] = (
        working["date"] - pd.to_timedelta(working["date"].dt.weekday, unit="D")
    )

    summary = (
        working.groupby(["week_start", "strategy"], as_index=False)
        .agg(
            total_juice=("juice", "sum"),
            total_basis=("basis", "sum"),
            trade_count=("ticker", "count"),
        )
        .sort_values(["week_start", "strategy"])
    )

    return summary


def get_dashboard_metrics(account: str | None = None) -> Dict[str, Any]:
    trades = get_all_trades(account)
    current_week = get_trades_for_current_week(account)

    cumulative = float(trades["juice"].sum()) if not trades.empty else 0.0
    total_trades = len(trades)

    return {
        "total_trades": total_trades,
        "cumulative_juice": cumulative,
        "first_trade_date": _serialize_date(trades["date"].min()),
        "last_trade_date": _serialize_date(trades["date"].max()),
        "current_week_trade_count": len(current_week),
    }

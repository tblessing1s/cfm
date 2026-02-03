"""CSV-backed storage helpers for business scoreboard data."""
from __future__ import annotations

import csv
import uuid
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np
import shutil
import logging

from .excel_loader import BASE_DIR, JOURNAL_ROOT, DATA_DIR, _discover_accounts

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CsvStore:
    path: Path
    fieldnames: List[str]

    def ensure_exists(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _maybe_migrate(self.path)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()

    def load(self) -> pd.DataFrame:
        self.ensure_exists()
        df = pd.read_csv(self.path)
        if df.empty:
            return df
        df.columns = [c.strip().lower() for c in df.columns]
        return df

    def append_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        self.ensure_exists()
        normalized = [{k: row.get(k) for k in self.fieldnames} for row in rows]
        with self.path.open("a+", newline="", encoding="utf-8") as f:
            # Ensure we start on a new line if the file doesn't end with one
            f.seek(0, 2)  # move to end
            if f.tell() > 0:
                f.seek(max(0, f.tell() - 1))
                last_char = f.read(1)
                if last_char not in ("\n", "\r"):
                    f.write("\n")
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            for row in normalized:
                writer.writerow(row)
        return normalized

    def overwrite(self, rows: List[Dict[str, Any]]) -> None:
        """Rewrite the entire CSV with provided rows (expects normalized fieldnames)."""
        self.ensure_exists()
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k) for k in self.fieldnames})


def _maybe_migrate(target_path: Path) -> None:
    """
    If the target file is missing in the new data directory but exists in the old
    cfm_journal root, move it into the data directory to consolidate storage.
    """
    if target_path.exists():
        return
    legacy = JOURNAL_ROOT / target_path.name
    try:
        if legacy.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), target_path)
    except Exception:
        # Best-effort; ignore migration errors so callers can still create new files.
        pass


def _normalize_strategy(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    lowered = text.lower()
    if "cashflow" in lowered or "cfm" in lowered:
        return "CFM"
    if "juice" in lowered or "jl" in lowered:
        return "JL"
    return text


NAV_FIELDS = [
    "account",
    "date",
    "nav_total",
    "nav_cash",
    "nav_long_value",
    "nav_liabilities",
    "deposits",
    "withdrawals",
]

nav_store = CsvStore(
    DATA_DIR / "nav_snapshots.csv",
    NAV_FIELDS,
)

positions_store = CsvStore(
    DATA_DIR / "base_positions.csv",
    [
        "position_id",
        "account",
        "symbol",
        "strategy",
        "base_type",
        "opened_date",
        "closed_date",
        "capture_target_pct",
        "min_dte_to_roll",
        "cheap_buyback_threshold",
        "hang_timer_max",
    ],
)

legs_store = CsvStore(
    DATA_DIR / "base_legs.csv",
    [
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
        "condition",
        "underlying_price",
        "delta",
    ],
)

reserves_store = CsvStore(
    DATA_DIR / "reserves.csv",
    ["position_id", "as_of_date", "reserved_cash", "note_or_rule_text"],
)

replacement_store = CsvStore(
    DATA_DIR / "replacement_costs.csv",
    ["position_id", "as_of_date", "replacement_cost_same_size", "unit_replacement_cost", "method"],
)

regime_store = CsvStore(
    DATA_DIR / "regime_log.csv",
    [
        "date",
        "symbol",
        "stock_score",
        "market_score",
        "stock_condition",
        "market_condition",
    ],
)

cash_movements_store = CsvStore(
    DATA_DIR / "cash_movements.csv",
    [
        "movement_id",
        "account",
        "date",
        "direction",
        "purpose",
        "amount",
        "position_id",
        "note",
    ],
)

cash_allocations_store = CsvStore(
    DATA_DIR / "cash_allocations.csv",
    [
        "account",
        "ticker",
        "type",
        "amount",
        "updated_at",
    ],
)

circuit_breaker_store = CsvStore(
    DATA_DIR / "circuit_breaker_log.csv",
    [
        "date",
        "symbol",
        "market_regime",
        "stock_regime",
        "index_close",
        "index_ema21",
        "index_sma50",
        "index_ema8",
        "stock_close",
        "stock_ema21",
        "stock_sma50",
        "stock_ema8",
        "stock_sma200",
        "cushion_pct",
        "catastrophic_event",
        "earnings_days",
    ],
)

# Run a one-time migration on import to move any remaining CSVs in the root to data
def _migrate_legacy_csvs() -> None:
    if not JOURNAL_ROOT.exists():
        return
    for csv_path in JOURNAL_ROOT.glob("*.csv"):
        target = DATA_DIR / csv_path.name
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(csv_path), target)
        except Exception:
            pass


_migrate_legacy_csvs()


def list_regimes(symbol: Optional[str] = None) -> pd.DataFrame:
    df = regime_store.load()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if symbol:
        df["symbol"] = df["symbol"].astype(str).str.upper()
        df = df[df["symbol"] == symbol.upper()]
    return df


def add_regime(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "date": payload.get("date"),
        "symbol": (payload.get("symbol") or "").upper(),
        "stock_score": payload.get("stock_score"),
        "market_score": payload.get("market_score"),
        "stock_condition": payload.get("stock_condition"),
        "market_condition": payload.get("market_condition"),
    }
    regime_store.append_rows([row])
    return row


def list_circuit_breakers(symbol: Optional[str] = None) -> pd.DataFrame:
    df = circuit_breaker_store.load()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if symbol:
        df["symbol"] = df["symbol"].astype(str).str.upper()
        df = df[df["symbol"] == symbol.upper()]
    return df


def add_circuit_breaker(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "date": payload.get("date"),
        "symbol": (payload.get("symbol") or "").upper(),
        "market_regime": payload.get("market_regime"),
        "stock_regime": payload.get("stock_regime"),
        "index_close": payload.get("index_close"),
        "index_ema21": payload.get("index_ema21"),
        "index_sma50": payload.get("index_sma50"),
        "index_ema8": payload.get("index_ema8"),
        "stock_close": payload.get("stock_close"),
        "stock_ema21": payload.get("stock_ema21"),
        "stock_sma50": payload.get("stock_sma50"),
        "stock_ema8": payload.get("stock_ema8"),
        "stock_sma200": payload.get("stock_sma200"),
        "cushion_pct": payload.get("cushion_pct"),
        "catastrophic_event": payload.get("catastrophic_event"),
        "earnings_days": payload.get("earnings_days"),
    }
    circuit_breaker_store.append_rows([row])
    return row


def _require_account(account: str) -> str:
    labels = {d.name.lower(): d.name for d in _discover_accounts()}
    normalized = account.strip().lower()
    if normalized not in labels:
        raise ValueError(f"Unknown account '{account}'")
    return labels[normalized]


def _uuid() -> str:
    return uuid.uuid4().hex


def _upgrade_store_columns(store: CsvStore) -> None:
    """Rewrite an existing CSV to match the store's fieldnames (adds missing, drops extras)."""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    if not store.path.exists():
        return
    try:
        df = pd.read_csv(store.path)
    except Exception:
        return
    desired = [c.strip().lower() for c in store.fieldnames]
    existing = [c.strip().lower() for c in df.columns]
    if existing == desired:
        return
    # add missing columns
    for col in desired:
        if col not in existing:
            df[col] = pd.NA
    # drop extras
    for col in list(df.columns):
        if col.strip().lower() not in desired:
            df = df.drop(columns=[col])
    # reorder
    df = df[[col for col in df.columns if col.strip().lower() in desired]]
    # rename to canonical header order
    df.columns = store.fieldnames
    df.to_csv(store.path, index=False)


def _upgrade_nav_store_columns() -> None:
    """If the nav CSV exists but is missing new columns, rewrite it with the new header."""
    _upgrade_store_columns(nav_store)


def _upgrade_cash_movements_store_columns() -> None:
    """If the cash movements CSV exists but is missing new columns, rewrite it with the new header."""
    _upgrade_store_columns(cash_movements_store)


# NAV snapshots
def list_nav(account: Optional[str] = None) -> pd.DataFrame:
    _upgrade_nav_store_columns()
    df = nav_store.load()
    if df.empty:
        return df
    for col in ["nav_cash", "nav_long_value", "nav_liabilities"]:
        if col not in df.columns:
            df[col] = pd.NA
    if "nav_total" in df.columns:
        try:
            df["nav_total"] = df["nav_total"].fillna(
                df.get("nav_cash", 0).fillna(0) + df.get("nav_long_value", 0).fillna(0) - df.get("nav_liabilities", 0).fillna(0)
            )
        except Exception:
            pass
    if account:
        acct = _require_account(account)
        df = df[df["account"].str.lower() == acct.lower()]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def list_cash_movements(account: Optional[str] = None, position_id: Optional[str] = None) -> pd.DataFrame:
    _upgrade_cash_movements_store_columns()
    df = cash_movements_store.load()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    if account:
        normalized = _require_account(account)
        df["account"] = df["account"].astype(str)
        df = df[df["account"].str.lower() == normalized.lower()]
    if position_id:
        df["position_id"] = df["position_id"].astype(str)
        df = df[df["position_id"] == position_id]
    return df


def add_cash_movement(payload: Dict[str, Any]) -> Dict[str, Any]:
    account = payload.get("account")
    if not account:
        raise ValueError("Account is required for cash movement")
    normalized_account = _require_account(account)
    row = {
        "movement_id": payload.get("movement_id") or _uuid(),
        "account": normalized_account,
        "date": payload.get("date"),
        "direction": str(payload.get("direction") or "").upper(),
        "purpose": str(payload.get("purpose") or "").upper(),
        "amount": payload.get("amount"),
        "position_id": payload.get("position_id") or None,
        "note": payload.get("note") or "",
    }
    cash_movements_store.append_rows([row])
    return row


def add_nav_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    acct = _require_account(payload["account"])
    nav_cash = payload.get("nav_cash")
    nav_long = payload.get("nav_long_value")
    nav_liabilities = payload.get("nav_liabilities")
    nav_total = payload.get("nav_total")
    if nav_total in (None, ""):
        nav_total = (nav_cash or 0) + (nav_long or 0) - (nav_liabilities or 0)
    row = {
        "account": acct,
        "date": payload["date"],
        "nav_total": nav_total,
        "nav_cash": nav_cash,
        "nav_long_value": nav_long,
        "nav_liabilities": nav_liabilities,
        "deposits": payload.get("deposits", 0),
        "withdrawals": payload.get("withdrawals", 0),
    }
    _upgrade_nav_store_columns()
    nav_store.append_rows([row])
    return row


# Positions
def list_positions(account: Optional[str] = None) -> pd.DataFrame:
    _upgrade_store_columns(positions_store)
    df = positions_store.load()
    if df.empty:
        return df
    if account:
        acct = _require_account(account)
        df = df[df["account"].str.lower() == acct.lower()]
    df["opened_date"] = pd.to_datetime(df["opened_date"], errors="coerce")
    if "closed_date" in df.columns:
        df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    return df


def add_position(payload: Dict[str, Any]) -> Dict[str, Any]:
    acct = _require_account(payload["account"])
    row = {
        "position_id": payload.get("position_id") or _uuid(),
        "account": acct,
        "symbol": payload["symbol"].upper(),
        "strategy": _normalize_strategy(payload.get("strategy", "")),
        "base_type": payload.get("base_type", "").strip(),
        "opened_date": payload.get("opened_date"),
        "closed_date": payload.get("closed_date"),
        "capture_target_pct": payload.get("capture_target_pct", 0.70),
        "min_dte_to_roll": payload.get("min_dte_to_roll", 3),
        "cheap_buyback_threshold": payload.get("cheap_buyback_threshold", 0.30),
        "hang_timer_max": payload.get("hang_timer_max", 2),
    }
    positions_store.append_rows([row])
    return row


def update_position(position_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing position row by position_id."""
    df = positions_store.load()
    if df.empty:
        raise ValueError(f"Position {position_id} not found")
    mask = df["position_id"] == position_id
    if not mask.any():
        raise ValueError(f"Position {position_id} not found")
    # Update allowed fields
    for field in positions_store.fieldnames:
        if field in payload:
            if field == "strategy":
                df.loc[mask, field] = _normalize_strategy(payload.get(field))
            else:
                df.loc[mask, field] = payload.get(field)
    # Rewrite file
    df = df.where(pd.notna(df), None)
    positions_store.overwrite(df.to_dict("records"))

    return df[mask].to_dict("records")[0]


# Base legs
def list_base_legs(position_id: Optional[str] = None) -> pd.DataFrame:
    _upgrade_store_columns(legs_store)
    df = legs_store.load()
    if df.empty:
        return df
    if position_id:
        df = df[df["position_id"] == position_id]
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce", format="mixed")
    if "delta" in df.columns:
        df["delta"] = pd.to_numeric(df.get("delta"), errors="coerce")
    df = df.astype(object).where(pd.notna(df), None)
    return df



def list_cash_allocations(account: Optional[str] = None) -> pd.DataFrame:
    df = cash_allocations_store.load()
    if df.empty:
        return df
    if account:
        df = df[df["account"] == account]
    return df.replace({np.nan: None})


def upsert_cash_allocation(payload: Dict[str, Any]) -> Dict[str, Any]:
    account = payload.get("account")
    ticker = (payload.get("ticker") or "").upper()
    alloc_type = payload.get("type")
    amount = payload.get("amount")
    if not account or not ticker or not alloc_type:
        raise ValueError("Account, ticker, and type are required for cash allocation")

    row = {
        "account": account,
        "ticker": ticker,
        "type": alloc_type,
        "amount": amount,
        "updated_at": datetime.utcnow().isoformat(),
    }
    df = cash_allocations_store.load()
    if df.empty:
        cash_allocations_store.append_rows([row])
        return row
    mask = (df["account"] == account) & (df["ticker"].astype(str).str.upper() == ticker) & (df["type"] == alloc_type)
    if mask.any():
        df.loc[mask, "amount"] = amount
        df.loc[mask, "updated_at"] = row["updated_at"]
        df = df.where(pd.notna(df), None)
        cash_allocations_store.overwrite(df.to_dict("records"))
    else:
        cash_allocations_store.append_rows([row])
    return row


def add_base_leg(payload: Dict[str, Any]) -> Dict[str, Any]:
    qty = payload.get("quantity")
    price = payload.get("price")
    fees = payload.get("fees", 0)
    amount = payload.get("amount")
    instr = str(payload.get("instrument_type") or "").upper()
    underlying = payload.get("underlying_price")
    delta = payload.get("delta")
    option_tokens = {"", "OPTION", "CALL", "PUT", "OPTION_CALL", "OPTION_PUT", "CALL_OPTION", "PUT_OPTION"}
    is_option = instr in option_tokens
    is_put = instr in {"PUT", "OPTION_PUT", "PUT_OPTION"}
    mult = 100.0 if is_option else 1.0
    tag_val = str(payload.get("tag") or "").upper()
    if tag_val == "MARK":
        mult = 100.0
    # If this is a MARK and qty is missing, reuse qty from the last leg for this base_leg_id (or position)
    if (qty is None or qty == "" or qty == 0) and tag_val == "MARK":
        try:
            df_prev = legs_store.load()
            if not df_prev.empty:
                target = df_prev
                if "base_leg_id" in df_prev.columns and payload.get("base_leg_id"):
                    target = df_prev[df_prev["base_leg_id"] == payload.get("base_leg_id")]
                if (target.empty) and ("position_id" in df_prev.columns) and payload.get("position_id"):
                    target = df_prev[df_prev["position_id"] == payload.get("position_id")]
                if not target.empty:
                    prev = target.iloc[-1]
                    qty = prev.get("quantity") if prev.get("quantity") not in (None, "") else qty
                    if (instr == "" or instr is None) and prev.get("instrument_type"):
                        instr = str(prev.get("instrument_type")).upper()
                    mult = 100.0 if ((instr or "").upper() in ("", "OPTION")) else 1.0
                    if tag_val == "MARK":
                        mult = 100.0
        except Exception:
            pass
    try:
        qty = abs(float(qty)) if qty is not None else None
    except Exception:
        pass
    try:
        price = abs(float(price)) if price is not None else None
    except Exception:
        pass
    try:
        underlying = abs(float(underlying)) if underlying is not None else None
    except Exception:
        underlying = None
    try:
        delta = float(delta) if delta not in (None, "") else None
    except Exception:
        delta = None
    try:
        fees = abs(float(fees)) if fees is not None else 0
    except Exception:
        fees = 0
    try:
        amount = abs(float(amount)) if amount is not None else None
    except Exception:
        amount = None
    # For MARK, if price missing reuse last price for this leg/position
    if tag_val == "MARK" and (price is None or price == ""):
        try:
            df_prev = legs_store.load()
            if not df_prev.empty:
                target = df_prev
                if "base_leg_id" in df_prev.columns and payload.get("base_leg_id"):
                    target = df_prev[df_prev["base_leg_id"] == payload.get("base_leg_id")]
                if (target.empty) and ("position_id" in df_prev.columns) and payload.get("position_id"):
                    target = df_prev[df_prev["position_id"] == payload.get("position_id")]
                if not target.empty:
                    prev = target.iloc[-1]
                    price_prev = prev.get("price")
                    if price_prev not in (None, "") and not pd.isna(price_prev):
                        try:
                            price = abs(float(price_prev))
                        except Exception:
                            pass
        except Exception:
            pass

    # Auto-calc amount for marks or when missing
    if amount is None or tag_val == "MARK":
        if qty is not None and price is not None:
            amount = abs(qty * price * mult)
            logger.info(
                "[base_leg calc] tag=%s qty=%s price=%s mult=%s amount=%s base_leg_id=%s position_id=%s",
                tag_val,
                qty,
                price,
                mult,
                amount,
                payload.get("base_leg_id"),
                payload.get("position_id"),
            )
        else:
            logger.info(
                "[base_leg calc skipped] tag=%s qty=%s price=%s mult=%s base_leg_id=%s position_id=%s",
                tag_val,
                qty,
                price,
                mult,
                payload.get("base_leg_id"),
                payload.get("position_id"),
            )

    row = {
        "base_leg_id": payload.get("base_leg_id") or _uuid(),
        "position_id": payload["position_id"],
        "date": payload["date"],
        "time": payload.get("time"),
        "instrument_type": payload.get("instrument_type", "").upper(),
        "side": payload.get("side", "").upper(),
        "quantity": qty,
        "strike": payload.get("strike"),
        "expiry": payload.get("expiry"),
        "price": price,
        "fees": fees,
        "amount": amount,
        "tag": payload.get("tag"),
        "condition": payload.get("condition"),
        "underlying_price": underlying,
        "delta": delta,
    }

    # Manage MARK/CLOSE upsert so only one MARK exists per base_leg_id; for OPEN ensure a paired MARK row exists.
    df = legs_store.load()
    if "tag" in df.columns:
        df["tag"] = df["tag"].astype(str).str.upper()
    base_leg_id = row["base_leg_id"]

    if tag_val == "MARK":
        if not df.empty:
            df = df[~((df.get("base_leg_id") == base_leg_id) & (df.get("tag") == "MARK"))]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        legs_store.overwrite(df.where(pd.notna(df), None).to_dict("records"))
        return row

    if tag_val == "CLOSE":
        if not df.empty:
            df = df[~((df.get("base_leg_id") == base_leg_id) & (df.get("tag") == "MARK"))]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        legs_store.overwrite(df.where(pd.notna(df), None).to_dict("records"))
        return row

    # OPEN: append/overwrite OPEN and ensure a MARK exists
    if not df.empty:
        # remove any existing OPEN for this base_leg_id to avoid duplicates
        df = df[~((df.get("base_leg_id") == base_leg_id) & (df.get("tag") == "OPEN"))]
    mark_row = dict(row)
    mark_row["tag"] = "MARK"
    df_new = [row]
    # Only add mark_row if a MARK is not already present
    if df.empty or not ((df.get("base_leg_id") == base_leg_id) & (df.get("tag") == "MARK")).any():
        df_new.append(mark_row)
    df = pd.concat([df, pd.DataFrame(df_new)], ignore_index=True)
    legs_store.overwrite(df.where(pd.notna(df), None).to_dict("records"))
    return row


def update_base_leg(base_leg_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    df = legs_store.load()
    if df.empty:
        raise ValueError(f"Base leg {base_leg_id} not found")
    df["base_leg_id"] = df["base_leg_id"].astype(str)
    mask = df["base_leg_id"] == str(base_leg_id)
    if not mask.any():
        raise ValueError(f"Base leg {base_leg_id} not found")
    if "delta" in payload:
        val = payload.get("delta")
        try:
            val = float(val) if val not in (None, "") else None
        except Exception:
            val = None
        df.loc[mask, "delta"] = val
    df = df.where(pd.notna(df), None)
    legs_store.overwrite(df.to_dict("records"))
    row = df[mask].iloc[-1].to_dict()
    for key, val in list(row.items()):
        if pd.isna(val):
            row[key] = None
    return row


# Reserves
def list_reserves(position_id: Optional[str] = None) -> pd.DataFrame:
    df = reserves_store.load()
    if df.empty:
        return df
    if position_id:
        df = df[df["position_id"] == position_id]
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    return df


def add_reserve(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "position_id": payload["position_id"],
        "as_of_date": payload["as_of_date"],
        "reserved_cash": payload["reserved_cash"],
        "note_or_rule_text": payload.get("note_or_rule_text"),
    }
    reserves_store.append_rows([row])
    return row


def upsert_reserve(payload: Dict[str, Any], note_prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    Upsert a reserve row keyed by position/date and optional note prefix.
    Intended for computed reserves (ex: SafetyReserve) so duplicates are avoided.
    """
    row = {
        "position_id": payload["position_id"],
        "as_of_date": payload["as_of_date"],
        "reserved_cash": payload["reserved_cash"],
        "note_or_rule_text": payload.get("note_or_rule_text"),
    }
    df = reserves_store.load()
    if df.empty:
        reserves_store.append_rows([row])
        return row

    df["position_id"] = df.get("position_id").astype(str)
    df["as_of_date"] = pd.to_datetime(df.get("as_of_date"), errors="coerce")
    target_date = pd.to_datetime(row["as_of_date"], errors="coerce")
    mask = df["position_id"] == str(row["position_id"])
    if target_date is not None and not pd.isna(target_date):
        mask &= df["as_of_date"].dt.normalize() == target_date.normalize()
    if note_prefix:
        note_series = df.get("note_or_rule_text", "").fillna("").astype(str)
        mask &= note_series.str.startswith(note_prefix)

    if mask.any():
        df = df[~mask]

    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    reserves_store.overwrite(df.where(pd.notna(df), None).to_dict("records"))
    return row


# Replacement costs
def list_replacement_costs(position_id: Optional[str] = None) -> pd.DataFrame:
    df = replacement_store.load()
    if df.empty:
        return df
    if position_id:
        df = df[df["position_id"] == position_id]
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    return df


def add_replacement_cost(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "position_id": payload["position_id"],
        "as_of_date": payload["as_of_date"],
        "replacement_cost_same_size": payload["replacement_cost_same_size"],
        "unit_replacement_cost": payload["unit_replacement_cost"],
        "method": payload.get("method", "MANUAL"),
    }
    replacement_store.append_rows([row])
    return row

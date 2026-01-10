"""Pure calculation helpers for business scoreboard metrics."""
from __future__ import annotations

from datetime import timedelta, datetime
import logging
from typing import Optional, Tuple, List, Dict

import numpy as np
import pandas as pd

from ..utils import excel_loader, business_loader
from ..models.business import (
    BusinessDashboard,
    PositionMetrics,
    BasePosition,
    NavPoint,
    PortfolioSummary,
    StockSummaryRow,
    StockDetail,
    PillarSeriesPoint,
    RegimeEntry,
    ProtectionMetrics,
)

logger = logging.getLogger(__name__)


def _week_bounds(anchor: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start = anchor - pd.to_timedelta(anchor.weekday(), unit="D")
    end = start + pd.Timedelta(days=7)
    return start, end


def _current_week_window() -> Tuple[pd.Timestamp, pd.Timestamp]:
    today = pd.Timestamp.now().normalize()
    return _week_bounds(today)


def _current_month_window() -> Tuple[pd.Timestamp, pd.Timestamp]:
    today = pd.Timestamp.now().normalize()
    start = today.replace(day=1)
    end = (start + pd.offsets.MonthBegin(1)).normalize()
    return start, end


def _week_start(date_val: pd.Timestamp) -> pd.Timestamp:
    return date_val - pd.to_timedelta(date_val.weekday(), unit="D")


def _ledger_by_expiry(account: Optional[str] = None, ticker: Optional[str] = None, base_position_id: Optional[str] = None) -> pd.DataFrame:
    """Build a DataFrame of ledger rows keyed by expiry for juice aggregation."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    if "signed_juice_dollars" in df.columns:
        df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    else:
        df["signed_juice_dollars"] = None

    missing_mask = df["signed_juice_dollars"].isna()
    if missing_mask.any():
        df.loc[missing_mask, "signed_juice_dollars"] = df.loc[missing_mask].apply(_signed_juice_from_row, axis=1)

    if ticker:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
        df = df[df["ticker"] == ticker.upper()]
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]

    df = df.dropna(subset=["expiry", "signed_juice_dollars"])
    if "action" in df.columns:
        action = df["action"].astype(str).str.lower()
        df = df[action.str.contains("close", na=False)]
    return df


def _net_juice_by_expiry_window(
    account: Optional[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    ticker: Optional[str] = None,
    base_position_id: Optional[str] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    ledger = _ledger_by_expiry(account, ticker=ticker, base_position_id=base_position_id)
    if ledger.empty:
        return 0.0
    window_start = start
    window_end = end
    if expiry_start is not None:
        window_start = max(window_start, expiry_start)
    if expiry_end is not None:
        window_end = min(window_end, expiry_end + pd.Timedelta(days=1))
    if window_end <= window_start:
        return 0.0
    mask = (ledger["expiry"] >= window_start) & (ledger["expiry"] < window_end)
    return float(ledger.loc[mask, "signed_juice_dollars"].sum())


DEFAULT_RESERVE_PCT = 0.05
FLOOR_BUFFER = 1.05  # minimum portfolio replacement ratio before allowing income
CONTRACT_MULTIPLIER = 100  # options contract multiplier for full dollar amounts


def _signed_juice_from_row(row: pd.Series) -> float | None:
    """Compute signed juice dollars from a ledger row when missing."""
    premium = pd.to_numeric(row.get("premium_buyback"), errors="coerce")
    if pd.isna(premium):
        return None
    contracts = pd.to_numeric(row.get("contracts"), errors="coerce")
    if pd.isna(contracts):
        return None
    strike = pd.to_numeric(row.get("strike"), errors="coerce")
    underlying = pd.to_numeric(row.get("underlying"), errors="coerce")
    side = str(row.get("side") or "").lower()
    action = str(row.get("action") or "").lower()
    is_put = "put" in side
    is_close = "close" in action


    if not pd.isna(strike) and not pd.isna(underlying):
        intrinsic = max(0, strike - underlying) if is_put else max(0, underlying - strike)
        extrinsic = premium - intrinsic
    else:
        extrinsic = premium
    if is_close:
        extrinsic = max(0, extrinsic)
    juice_per_contract = extrinsic
    return round(float(juice_per_contract * contracts * CONTRACT_MULTIPLIER), 2)


def _net_juice_for_symbol(account: Optional[str], symbol: str) -> float:
    trades = excel_loader.get_all_trades(account)
    if trades.empty:
        return 0.0
    return float(trades[trades["ticker"].str.upper() == symbol.upper()]["juice"].sum())


def _net_ledger_juice_for_symbol(account: Optional[str], symbol: str) -> float:
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    df = df.dropna(subset=["signed_juice_dollars"])
    # Only include legs that close out shorts (no remaining open position for that leg)
    closed_mask = df["action"].astype(str).str.lower().str.contains("close")
    filtered = df[closed_mask & (df["ticker"] == symbol.upper())]
    return float(filtered["signed_juice_dollars"].sum())


def _normalize_expiry(expiry: Optional[str]) -> Optional[pd.Timestamp]:
    if not expiry:
        return None
    parsed = pd.to_datetime(expiry, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def _ledger_income(
    account: Optional[str] = None,
    ticker: Optional[str] = None,
    base_position_id: Optional[str] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """
    Realized income from the ledger (same source as Trades & Ledger view).
    Uses signed_juice_dollars or derives it per row; returns closed juice only.
    """
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0

    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    if (expiry_start is not None or expiry_end is not None) and "expiry" in df.columns:
        normalized = df["expiry"].dt.normalize()
        if expiry_start is not None:
            df = df[normalized >= expiry_start]
        if expiry_end is not None:
            df = df[normalized <= expiry_end]
    if ticker:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
        df = df[df["ticker"] == ticker.upper()]
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]
    df = df.dropna(subset=["signed_juice_dollars"])
    if df.empty:
        return 0.0
    action = df["action"].astype(str).str.lower()
    closed_juice = float(df.loc[action.str.contains("close", na=False), "signed_juice_dollars"].sum())
    return closed_juice


def _income_after_base_protection(original_base: Optional[float], current_base: Optional[float], protection: Optional[float], income: float) -> float:
    """Income is realized; do not allocate it to protection."""
    return float(income)


def _protection_allocation(original_base: Optional[float], current_base: Optional[float], protection: Optional[float], income: float) -> Tuple[float, float, float, float]:
    """Protection is structural; income is reported separately."""
    if original_base in (None, 0):
        return 0.0, 0.0, float(income), 0.0
    coverage = (current_base or 0.0) + (protection or 0.0)
    gap = max(0.0, float(original_base) - coverage)
    return gap, 0.0, float(income), gap


def _short_intrinsic_realized_for_position(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    opened_date: Optional[pd.Timestamp] = None,
    closed_date: Optional[pd.Timestamp] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Net short intrinsic protection = open intrinsic - close intrinsic."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]
    else:
        df["ticker"] = df["ticker"].astype(str).str.upper()
        df = df[df["ticker"] == symbol.upper()]
    if df.empty:
        return 0.0
    df["action"] = df.get("action", "").astype(str).str.lower()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    if opened_date is not None:
        df = df[df["date"] >= opened_date]
    if closed_date is not None:
        df = df[df["date"] <= closed_date]
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    if (expiry_start is not None or expiry_end is not None) and "expiry" in df.columns:
        normalized = df["expiry"].dt.normalize()
        if expiry_start is not None:
            df = df[normalized >= expiry_start]
        if expiry_end is not None:
            df = df[normalized <= expiry_end]
    if df.empty:
        return 0.0

    df["contracts"] = pd.to_numeric(df.get("contracts"), errors="coerce")
    df["strike"] = pd.to_numeric(df.get("strike"), errors="coerce")
    df["underlying"] = pd.to_numeric(df.get("underlying"), errors="coerce")
    df["side"] = df.get("side", "").astype(str).str.lower()

    def _row_intrinsic(row: pd.Series) -> float:
        contracts = row.get("contracts")
        strike = row.get("strike")
        underlying = row.get("underlying")
        if pd.isna(contracts) or pd.isna(strike) or pd.isna(underlying):
            return 0.0
        is_put = "put" in (row.get("side") or "")
        intrinsic_per = max(0.0, strike - underlying) if is_put else max(0.0, underlying - strike)
        return float(intrinsic_per) * float(contracts) * CONTRACT_MULTIPLIER
    open_intrinsic = float(df[df["action"].str.contains("open", na=False)].apply(_row_intrinsic, axis=1).sum())
    close_intrinsic = float(df[df["action"].str.contains("close", na=False)].apply(_row_intrinsic, axis=1).sum())
    return float(open_intrinsic - close_intrinsic)


def _long_extrinsic_loan_from_legs(
    legs: pd.DataFrame,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Compute long extrinsic loan from OPEN legs using underlying_price + strike + premium."""
    if legs.empty:
        return 0.0
    legs = legs.copy()
    if (expiry_start is not None or expiry_end is not None) and "expiry" in legs.columns:
        legs["expiry"] = pd.to_datetime(legs.get("expiry"), errors="coerce")
        normalized = legs["expiry"].dt.normalize()
        if expiry_start is not None:
            legs = legs[normalized >= expiry_start]
        if expiry_end is not None:
            legs = legs[normalized <= expiry_end]

    if legs.empty:
        return 0.0

    net: Dict[str, float] = {}
    for idx, row in legs.iterrows():
        tag = str(row.get("tag") or "").upper()
        leg_id = str(row.get("base_leg_id") or f"row-{idx}")
        if tag == "MARK":
            continue
        side = str(row.get("side") or "").upper()
        qty = pd.to_numeric(row.get("quantity"), errors="coerce")
        if pd.isna(qty):
            continue
        delta = qty if side == "BUY" else -qty
        net[leg_id] = net.get(leg_id, 0.0) + float(delta)

    open_ids = {lid for lid, qty in net.items() if qty > 0}
    if not open_ids:
        return 0.0

    opens = legs[(legs["tag"].astype(str).str.upper() == "OPEN") & legs["base_leg_id"].astype(str).isin(open_ids)]
    if opens.empty:
        return 0.0

    total = 0.0
    for leg_id, group in opens.groupby(opens["base_leg_id"].astype(str)):
        if leg_id not in open_ids:
            continue
        row = group.sort_values(["date", "time"], na_position="last").iloc[0]
        qty = net.get(leg_id, pd.to_numeric(row.get("quantity"), errors="coerce"))
        if qty is None or pd.isna(qty) or qty <= 0:
            continue
        strike = pd.to_numeric(row.get("strike"), errors="coerce")
        underlying = pd.to_numeric(row.get("underlying_price"), errors="coerce")
        price = pd.to_numeric(row.get("price"), errors="coerce")
        if pd.isna(strike) or pd.isna(underlying) or pd.isna(price):
            continue
        instr = str(row.get("instrument_type") or "").upper()
        if instr in {"PUT", "OPTION_PUT", "PUT_OPTION"}:
            intrinsic_per = max(0.0, strike - underlying)
        elif instr in {"", "OPTION", "CALL", "OPTION_CALL", "CALL_OPTION"} or (instr == "SHARES" and row.get("expiry")):
            intrinsic_per = max(0.0, underlying - strike)
        else:
            continue
        extrinsic_per = max(0.0, float(price) - float(intrinsic_per))
        total += float(extrinsic_per) * float(qty) * 100.0

    return float(round(total, 2))


def _initial_base_intrinsic_extrinsic_from_legs(
    legs: pd.DataFrame,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> Tuple[float, float]:
    """Compute initial intrinsic/extrinsic from OPEN legs at entry."""
    if legs.empty:
        return 0.0, 0.0
    legs = legs.copy()
    if (expiry_start is not None or expiry_end is not None) and "expiry" in legs.columns:
        legs["expiry"] = pd.to_datetime(legs.get("expiry"), errors="coerce")
        normalized = legs["expiry"].dt.normalize()
        if expiry_start is not None:
            legs = legs[normalized >= expiry_start]
        if expiry_end is not None:
            legs = legs[normalized <= expiry_end]
    if legs.empty:
        return 0.0, 0.0
    opens = legs[legs["tag"].astype(str).str.upper() == "OPEN"]
    if opens.empty:
        return 0.0, 0.0
    marks = legs[legs["tag"].astype(str).str.upper() == "MARK"]
    if marks.empty:
        return 0.0, 0.0
    valid_ids = set(marks["base_leg_id"].astype(str))
    opens = opens[opens["base_leg_id"].astype(str).isin(valid_ids)]
    if opens.empty:
        return 0.0, 0.0
    total_intrinsic = 0.0
    total_extrinsic = 0.0
    for _, row in opens.iterrows():
        qty = pd.to_numeric(row.get("quantity"), errors="coerce")
        strike = pd.to_numeric(row.get("strike"), errors="coerce")
        underlying = pd.to_numeric(row.get("underlying_price"), errors="coerce")
        price = pd.to_numeric(row.get("price"), errors="coerce")
        if pd.isna(qty) or pd.isna(strike) or pd.isna(underlying) or pd.isna(price):
            continue
        instr = str(row.get("instrument_type") or "").upper()
        if instr in {"PUT", "OPTION_PUT", "PUT_OPTION"}:
            intrinsic_per = max(0.0, strike - underlying)
        elif instr in {"", "OPTION", "CALL", "OPTION_CALL", "CALL_OPTION"} or (instr == "SHARES" and row.get("expiry")):
            intrinsic_per = max(0.0, underlying - strike)
        else:
            continue
        intrinsic_total = float(intrinsic_per) * float(qty) * 100.0
        extrinsic_per = max(0.0, float(price) - float(intrinsic_per))
        extrinsic_total = float(extrinsic_per) * float(qty) * 100.0
        total_intrinsic += intrinsic_total
        total_extrinsic += extrinsic_total
    return float(round(total_intrinsic, 2)), float(round(total_extrinsic, 2))


def _current_base_intrinsic_from_legs(
    legs: pd.DataFrame,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Compute current intrinsic from MARK legs for open positions."""
    if legs.empty:
        return 0.0
    legs = legs.copy()
    if (expiry_start is not None or expiry_end is not None) and "expiry" in legs.columns:
        legs["expiry"] = pd.to_datetime(legs.get("expiry"), errors="coerce")
        normalized = legs["expiry"].dt.normalize()
        if expiry_start is not None:
            legs = legs[normalized >= expiry_start]
        if expiry_end is not None:
            legs = legs[normalized <= expiry_end]
    if legs.empty:
        return 0.0

    net: Dict[str, float] = {}
    has_mark: Dict[str, bool] = {}
    for idx, row in legs.iterrows():
        tag = str(row.get("tag") or "").upper()
        leg_id = str(row.get("base_leg_id") or f"row-{idx}")
        if tag == "MARK":
            has_mark[leg_id] = True
            continue
        side = str(row.get("side") or "").upper()
        qty = pd.to_numeric(row.get("quantity"), errors="coerce")
        if pd.isna(qty):
            continue
        delta = qty if side == "BUY" else -qty
        net[leg_id] = net.get(leg_id, 0.0) + float(delta)

    open_ids = {lid for lid, qty in net.items() if qty > 0 and has_mark.get(lid)}
    if not open_ids:
        return 0.0

    marks = legs[(legs["tag"].astype(str).str.upper() == "MARK") & legs["base_leg_id"].astype(str).isin(open_ids)]
    if marks.empty:
        return 0.0

    total = 0.0
    for _, row in marks.iterrows():
        leg_id = str(row.get("base_leg_id") or "")
        qty = net.get(leg_id, pd.to_numeric(row.get("quantity"), errors="coerce"))
        if qty is None or pd.isna(qty) or qty <= 0:
            continue
        strike = pd.to_numeric(row.get("strike"), errors="coerce")
        underlying = pd.to_numeric(row.get("underlying_price"), errors="coerce")
        if pd.isna(strike) or pd.isna(underlying):
            continue
        instr = str(row.get("instrument_type") or "").upper()
        if instr in {"PUT", "OPTION_PUT", "PUT_OPTION"}:
            intrinsic_per = max(0.0, strike - underlying)
        elif instr in {"", "OPTION", "CALL", "OPTION_CALL", "CALL_OPTION"} or (instr == "SHARES" and row.get("expiry")):
            intrinsic_per = max(0.0, underlying - strike)
        else:
            continue
        total += float(intrinsic_per) * float(qty) * 100.0
    return float(round(total, 2))


def _short_extrinsic_net_for_position(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    opened_date: Optional[pd.Timestamp] = None,
    closed_date: Optional[pd.Timestamp] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Net short extrinsic = open extrinsic - close extrinsic (realized)."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]
    else:
        df["ticker"] = df["ticker"].astype(str).str.upper()
        df = df[df["ticker"] == symbol.upper()]
    if df.empty:
        return 0.0
    df["action"] = df.get("action", "").astype(str).str.lower()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    if opened_date is not None:
        df = df[df["date"] >= opened_date]
    if closed_date is not None:
        df = df[df["date"] <= closed_date]
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    if (expiry_start is not None or expiry_end is not None) and "expiry" in df.columns:
        normalized = df["expiry"].dt.normalize()
        if expiry_start is not None:
            df = df[normalized >= expiry_start]
        if expiry_end is not None:
            df = df[normalized <= expiry_end]
    if df.empty:
        return 0.0

    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    df = df.dropna(subset=["signed_juice_dollars"])
    if df.empty:
        return 0.0
    open_extrinsic = float(df[df["action"].str.contains("open", na=False)]["signed_juice_dollars"].sum())
    close_extrinsic = float(df[df["action"].str.contains("close", na=False)]["signed_juice_dollars"].sum())
    return float(open_extrinsic - close_extrinsic)


def _condition_from_score(score: int) -> str:
    if score >= 3:
        return "GREEN"
    if score == 2:
        return "YELLOW"
    return "RED"


def _overall_condition(stock_cond: str, market_cond: str) -> str:
    # Worse condition wins: RED > YELLOW > GREEN
    order = {"RED": 3, "YELLOW": 2, "GREEN": 1}
    if order.get(stock_cond, 0) >= order.get(market_cond, 0):
        return stock_cond
    return market_cond


def save_regime_entry(payload: Dict) -> RegimeEntry:
    """Persist a regime entry and return normalized conditions."""
    stock_cond = _condition_from_score(int(payload.get("stock_score", 0)))
    market_cond = _condition_from_score(int(payload.get("market_score", 0)))
    record = {
        "date": payload.get("date"),
        "symbol": (payload.get("symbol") or "").upper(),
        "stock_score": int(payload.get("stock_score", 0)),
        "market_score": int(payload.get("market_score", 0)),
        "stock_condition": stock_cond,
        "market_condition": market_cond,
    }
    stored = business_loader.add_regime(record)
    return RegimeEntry(**stored)


def list_regime_entries(symbol: Optional[str] = None) -> List[RegimeEntry]:
    df = business_loader.list_regimes(symbol)
    if df.empty:
        return []
    # Ensure NaN notes are treated as None for Pydantic validation
    # Also coerce scores to safe ints
    for col in ("stock_score", "market_score"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].fillna("").astype(str)
    df = df.sort_values("date")
    records = []
    for row in df.to_dict("records"):
        if not row.get("symbol"):
            row["symbol"] = ""
        records.append(RegimeEntry(**row))
    return records


def _income_series_by_week(account: Optional[str], symbol: Optional[str] = None, base_position_id: Optional[str] = None) -> List[PillarSeriesPoint]:
    """Weekly realized income series derived from ledger rows (date-based)."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    if "signed_juice_dollars" not in df.columns:
        df["signed_juice_dollars"] = None
    if symbol:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
        df = df[df["ticker"] == symbol.upper()]
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]
    if df.empty:
        return []

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df = df.dropna(subset=["date"])
    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    df = df.dropna(subset=["signed_juice_dollars"])
    if df.empty:
        return []

    df["week_start"] = df["date"].apply(_week_start)
    grouped = (
        df.groupby("week_start", as_index=False)["signed_juice_dollars"]
        .sum()
        .sort_values("week_start")
    )
    grouped["period_start"] = grouped["week_start"].dt.date
    return [
        PillarSeriesPoint(period_start=row["period_start"], value=float(row["signed_juice_dollars"]))
        for _, row in grouped.iterrows()
    ]


def _base_strength_series_placeholder(base_strength: Optional[float]) -> List[PillarSeriesPoint]:
    """
    Until we have per-symbol historical base values, expose a single-point
    series so the UI can render a chart without breaking.
    """
    if base_strength is None:
        return []
    today = pd.Timestamp.now().normalize().date()
    return [PillarSeriesPoint(period_start=today, value=base_strength)]


def _base_value_series_placeholder(base_value: Optional[float]) -> List[PillarSeriesPoint]:
    if base_value is None:
        return []
    today = pd.Timestamp.now().normalize().date()
    return [PillarSeriesPoint(period_start=today, value=base_value)]


def _nav_at_start(snapshots: pd.DataFrame, start: pd.Timestamp) -> Optional[float]:
    if snapshots.empty:
        return None
    before = snapshots[snapshots["date"] <= start]
    if before.empty:
        return None
    latest = before.sort_values("date").iloc[-1]
    return float(latest["nav_total"])


def _safe_ratio(numerator: float, denominator: Optional[float]) -> Optional[float]:
    if denominator in (None, 0, np.nan):
        return None
    return float(numerator) / float(denominator)


def _to_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _clean_number(value) -> Optional[float]:
    try:
        val = float(value)
        if not np.isfinite(val):
            return None
        return val
    except Exception:
        return None


def _contributed_capital(snapshots: pd.DataFrame) -> float:
    if snapshots.empty:
        return 0.0
    return float(snapshots["deposits"].fillna(0).sum() - snapshots["withdrawals"].fillna(0).sum())


def _drawdown(nav_series: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    if nav_series.empty:
        return None, None
    peak = float(nav_series.max())
    current = float(nav_series.iloc[-1])
    if not peak:
        return current, None
    dd = (current - peak) / peak
    return current, dd


def _consistency(trades: pd.DataFrame, weeks: int = 13) -> Tuple[float, float]:
    if trades.empty:
        return 0.0, 0.0
    working = trades.copy()
    working["week_start"] = working["date"] - pd.to_timedelta(working["date"].dt.weekday, unit="D")
    grouped = working.groupby("week_start")["juice"].sum().sort_index()
    recent = grouped.tail(weeks)
    if recent.empty:
        return 0.0, 0.0
    profitable_pct = (recent > 0).mean() * 100.0
    avg_weekly = recent.mean()
    return float(profitable_pct), float(avg_weekly)


def _latest(df: pd.DataFrame, date_col: str) -> Optional[pd.Series]:
    if df.empty or date_col not in df.columns:
        return None
    ordered = df.sort_values(date_col)
    return ordered.iloc[-1]


def _nav_series_weekly_monthly(snapshots: pd.DataFrame) -> Tuple[List[NavPoint], List[NavPoint]]:
    if snapshots.empty or "date" not in snapshots.columns:
        return [], []
    snaps = snapshots.copy()
    snaps["date"] = pd.to_datetime(snaps["date"], errors="coerce")
    snaps = snaps.dropna(subset=["date", "nav_total"])
    if snaps.empty:
        return [], []

    snaps = snaps.sort_values("date")

    points: List[NavPoint] = []
    for _, row in snaps.iterrows():
        nav_total = _clean_number(row.get("nav_total"))
        if nav_total is None:
            continue
        points.append(
            NavPoint(
                period_start=row["date"].date(),
                nav_total=nav_total,
                nav_cash=_clean_number(row.get("nav_cash")),
                nav_long_value=_clean_number(row.get("nav_long_value")),
                nav_liabilities=_clean_number(row.get("nav_liabilities")),
            )
        )

    # Use the same full series for both weekly and monthly consumers so every snapshot is plotted.
    return points, points


def _position_value_cost(legs: pd.DataFrame) -> Tuple[float, float]:
    """
    Base value/cost from leg quantities and prices.
    - BUY increases cost; SELL reduces cost.
    - Uses amount if it carries sign; otherwise derives from qty*price*(mult).
    """
    if legs.empty:
        return 0.0, 0.0
    legs = legs.copy()
    legs["quantity"] = pd.to_numeric(legs.get("quantity"), errors="coerce")
    legs["price"] = pd.to_numeric(legs.get("price"), errors="coerce")

    def row_cash(row: pd.Series) -> float:
        amt = row.get("amount")
        qty = row.get("quantity")
        price = row.get("price")
        side = str(row.get("side") or "").upper()
        instr = str(row.get("instrument_type") or "").upper()
        mult = 100.0 if instr == "OPTION" else 1.0
        # Prefer signed amount if present
        if amt is not None and pd.notna(amt):
            try:
                return float(amt)
            except Exception:
                pass
        if pd.isna(qty) or pd.isna(price):
            return 0.0
        cash = float(qty) * float(price) * mult
        return -cash if side == "BUY" else cash

    legs["cash"] = legs.apply(row_cash, axis=1)
    value = legs["cash"].sum()
    # Cost is cash outlay (buys) in absolute terms
    cost = abs(legs[legs["cash"] < 0]["cash"].sum())
    return float(value), float(cost)


def _position_value_cost_units(legs: pd.DataFrame) -> Tuple[float, float, float]:
    """Return base value, base cost, and current units (BUY adds, SELL subtracts)."""
    if legs.empty:
        return 0.0, 0.0, 0.0
    # Keep only leg_ids with net qty > 0 (OPEN minus CLOSE) and that have a MARK entry.
    if {"base_leg_id", "side", "quantity", "tag"}.issubset(legs.columns):
        net: Dict[str, float] = {}
        has_mark: Dict[str, bool] = {}
        for idx, row in legs.iterrows():
            tag = str(row.get("tag") or "").upper()
            leg_id = str(row.get("base_leg_id") or f"row-{idx}")
            if tag == "MARK":
                has_mark[leg_id] = True
                continue
            side = str(row.get("side") or "").upper()
            qty = pd.to_numeric(row.get("quantity"), errors="coerce")
            if pd.isna(qty):
                continue
            delta = qty if side == "BUY" else -qty
            net[leg_id] = net.get(leg_id, 0.0) + float(delta)
        open_ids = {lid for lid, qty in net.items() if qty > 0 and has_mark.get(lid)}
        if open_ids:
            legs = legs[legs["base_leg_id"].astype(str).isin(open_ids)]
        else:
            legs = legs.iloc[0:0]
    if legs.empty:
        return 0.0, 0.0, 0.0

    legs = legs.copy()
    legs = legs.sort_values(["date", "time"], na_position="last")
    legs["amount"] = pd.to_numeric(legs.get("amount"), errors="coerce").fillna(0)

    # Current base: sum MARK amounts for open legs (amounts stored positive)
    mark_amount = float(
        legs[legs["tag"].astype(str).str.upper() == "MARK"]["amount"].sum()
    )
    base_value = mark_amount

    # Units tracked from open legs (based on qty)
    current_units = 0.0
    if {"quantity"}.issubset(legs.columns):
        for _, row in legs.iterrows():
            qty = pd.to_numeric(row.get("quantity"), errors="coerce")
            if pd.isna(qty):
                continue
            tag = str(row.get("tag") or "").upper()
            side = str(row.get("side") or "").upper()
            if tag == "MARK":
                continue
            delta = qty if side == "BUY" else -qty
            current_units += float(delta)

    # Base cost: sum of amounts for remaining open legs using only OPEN rows
    cost = float(legs[legs["tag"].astype(str).str.upper() == "OPEN"]["amount"].sum())

    return float(base_value), float(cost), float(current_units)


def _initial_benchmark_cost(legs: pd.DataFrame, repl_rows: pd.DataFrame, base_value: float) -> float:
    """Derive the initial benchmark replacement cost (entry cost)."""
    # Prefer explicitly stored replacement cost (earliest)
    if not repl_rows.empty:
        first = repl_rows.sort_values("as_of_date").iloc[0]
        try:
            return float(first.get("replacement_cost_same_size"))
        except Exception:
            pass

    # Otherwise, use cumulative buy costs from legs (derived if amounts are unsigned)
    if not legs.empty:
        legs = legs.copy()
        legs["quantity"] = pd.to_numeric(legs.get("quantity"), errors="coerce")
        legs["price"] = pd.to_numeric(legs.get("price"), errors="coerce")
        legs["amount"] = pd.to_numeric(legs.get("amount"), errors="coerce")

        def row_cost(row: pd.Series) -> float:
            amt = row.get("amount")
            if amt is not None and pd.notna(amt):
                try:
                    # If amount was stored unsigned, treat BUY as cash out
                    if row.get("side", "").upper() == "BUY":
                        return abs(float(amt))
                    return -abs(float(amt))
                except Exception:
                    pass
            qty = row.get("quantity")
            price = row.get("price")
            if pd.isna(qty) or pd.isna(price):
                return 0.0
            instr = str(row.get("instrument_type") or "").upper()
            mult = 100.0 if instr == "OPTION" else 1.0
            cash = float(qty) * float(price) * mult
            return cash if str(row.get("side") or "").upper() == "BUY" else -cash

        legs["calc_cost"] = legs.apply(row_cost, axis=1)
        buys = legs[legs["calc_cost"] > 0]
        if not buys.empty:
            return float(buys["calc_cost"].sum())

    # Last resort: use current base value
    return float(abs(base_value))


def _roll_flags(legs: pd.DataFrame) -> Tuple[bool, bool]:
    if legs.empty or "expiry" not in legs.columns:
        return False, False
    legs = legs.dropna(subset=["expiry"])
    if legs.empty:
        return False, False
    latest = legs.sort_values("date").iloc[-1]
    expiry = pd.to_datetime(latest["expiry"], errors="coerce")
    if pd.isna(expiry):
        return False, False
    dte = (expiry - pd.Timestamp.now().normalize()).days
    return dte <= 45, dte <= 30


def position_metrics(
    account: Optional[str] = None,
    include_closed: bool = False,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> List[PositionMetrics]:
    positions_df = business_loader.list_positions(account)
    reserves_df = business_loader.list_reserves()
    repl_df = business_loader.list_replacement_costs()
    results: List[PositionMetrics] = []
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)

    for _, pos in positions_df.iterrows():
        # Skip closed bases unless explicitly requested
        if (not include_closed) and (not pd.isna(pos.get("closed_date"))):
            continue
        pid = pos["position_id"]
        legs = business_loader.list_base_legs(pid)
        base_value, base_cost, current_units = _position_value_cost_units(legs)

        # Replacement cost benchmark: initial entry cost
        r_subset = repl_df[repl_df["position_id"] == pid]
        benchmark_cost = _initial_benchmark_cost(legs, r_subset, base_value)
        replacement_cost = benchmark_cost  # repurposed as initial cost
        unit_replacement_cost = benchmark_cost / current_units if current_units else None

        # Net juice to date: align with ledger income (same as dashboard income)
        net_juice_symbol = _ledger_income(
            account,
            pos["symbol"],
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        opened = pd.to_datetime(pos.get("opened_date"), errors="coerce")
        closed = pd.to_datetime(pos.get("closed_date"), errors="coerce")
        initial_intrinsic, initial_extrinsic = _initial_base_intrinsic_extrinsic_from_legs(
            legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        current_base_intrinsic = _current_base_intrinsic_from_legs(
            legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        intrinsic_protection = _short_intrinsic_realized_for_position(
            account,
            pos["symbol"],
            base_position_id=pid,
            opened_date=opened if not pd.isna(opened) else None,
            closed_date=closed if not pd.isna(closed) else None,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        realized_flag = not pd.isna(closed)
        short_extrinsic_net = 0.0
        if realized_flag:
            short_extrinsic_net = _short_extrinsic_net_for_position(
                account,
                pos["symbol"],
                base_position_id=pid,
                opened_date=opened if not pd.isna(opened) else None,
                closed_date=closed if not pd.isna(closed) else None,
                expiry_start=expiry_start_ts,
                expiry_end=expiry_end_ts,
            )
        long_extrinsic_loan = float(initial_extrinsic)
        paydown_source = max(0.0, float(short_extrinsic_net))
        long_extrinsic_paid = min(long_extrinsic_loan, paydown_source)
        long_extrinsic_remaining = max(0.0, long_extrinsic_loan - long_extrinsic_paid)
        long_extrinsic_income = max(0.0, float(short_extrinsic_net) - long_extrinsic_loan)
        base_plus_protection = (current_base_intrinsic or 0.0) + (intrinsic_protection or 0.0)
        base_health_delta = base_plus_protection - (initial_intrinsic or 0.0)

        # Reserve: use explicit rows if present, otherwise default % of base value
        explicit_reserve = float(reserves_df[reserves_df["position_id"] == pid]["reserved_cash"].sum()) if not reserves_df.empty else 0.0
        reserve_cash = explicit_reserve if explicit_reserve else (base_value * DEFAULT_RESERVE_PCT)

        replacement_ratio = None  # now Base + Protection coverage vs initial cost
        if replacement_cost:
            replacement_ratio = _safe_ratio(base_plus_protection, initial_intrinsic or replacement_cost)

        base_growth = None
        if base_cost or net_juice_symbol:
            base_growth = (base_value - base_cost) + net_juice_symbol

        scale_capacity = None
        if unit_replacement_cost:
            scale_capacity = int((base_value + reserve_cash) // unit_replacement_cost)

        plan_flag, act_flag = _roll_flags(legs)

        def _clean(val):
            return val if val is not None and not pd.isna(val) else None

        results.append(
            PositionMetrics(
                position=BasePosition(
                    position_id=str(pid),
                    account=pos["account"],
                    symbol=pos["symbol"],
                    strategy=_clean(pos.get("strategy")),
                    base_type=_clean(pos.get("base_type")),
                    opened_date=_clean(pos.get("opened_date")),
                    closed_date=_clean(pos.get("closed_date")),
                ),
                base_value=base_value,
                base_cost=base_cost,
                initial_base_cost=base_cost,
                initial_base_intrinsic=_clean_number(initial_intrinsic),
                initial_base_extrinsic=_clean_number(initial_extrinsic),
                current_base_intrinsic=_clean_number(current_base_intrinsic),
                base_plus_protection=base_plus_protection,
                base_health_delta=base_health_delta,
                net_juice_to_date=net_juice_symbol,
                net_intrinsic_to_date=intrinsic_protection,
                short_extrinsic_net=_clean_number(short_extrinsic_net),
                long_extrinsic_loan=_clean_number(long_extrinsic_loan),
                long_extrinsic_paid=_clean_number(long_extrinsic_paid),
                long_extrinsic_remaining=_clean_number(long_extrinsic_remaining),
                long_extrinsic_income=_clean_number(long_extrinsic_income),
                replacement_cost=replacement_cost,
                unit_replacement_cost=unit_replacement_cost,
                reserve_cash=reserve_cash,
                replacement_ratio=replacement_ratio,
                base_growth=base_growth,
                scale_capacity_units=scale_capacity,
                roll_plan_flag=plan_flag,
                roll_action_flag=act_flag,
            )
        )
    return results


def _stock_income_rates(
    account: Optional[str],
    ticker: str,
    base_position_id: Optional[str] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Compute current week/month realized income for a ticker."""
    week_start, week_end = _current_week_window()
    month_start, month_end = _current_month_window()
    week_income = _net_juice_by_expiry_window(
        account,
        week_start,
        week_end,
        ticker=ticker,
        base_position_id=base_position_id,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )
    month_income = _net_juice_by_expiry_window(
        account,
        month_start,
        month_end,
        ticker=ticker,
        base_position_id=base_position_id,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )
    return week_income, month_income


def _stock_income_consistency(account: Optional[str], ticker: str) -> float:
    trades = excel_loader.get_all_trades(account)
    if trades.empty:
        return 0.0
    trades["ticker"] = trades["ticker"].astype(str).str.upper()
    filtered = trades[trades["ticker"] == ticker.upper()]
    if filtered.empty:
        return 0.0
    filtered["date"] = pd.to_datetime(filtered["date"], errors="coerce")
    pct, _ = _consistency(filtered, weeks=13)
    return pct


def stock_summary_rows(
    account: Optional[str] = None,
    include_closed: bool = False,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> List[StockSummaryRow]:
    """Aggregate per-stock rows for ranking tables."""
    pos_metrics = position_metrics(
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )
    rows: List[StockSummaryRow] = []
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)

    for pm in pos_metrics:
        initial_intrinsic = pm.initial_base_intrinsic or 0.0
        initial_extrinsic = pm.initial_base_extrinsic or 0.0
        original_base_value = (initial_intrinsic + initial_extrinsic) or pm.initial_base_cost or pm.base_cost
        current_base_value = pm.base_value
        protection = pm.net_intrinsic_to_date
        denom_intrinsic = initial_intrinsic or original_base_value
        base_strength_ratio = _safe_ratio((current_base_value or 0) + (protection or 0), denom_intrinsic)
        base_market_value_change = None
        base_growth_pct = None
        if denom_intrinsic:
            base_market_value_change = (current_base_value or 0) - original_base_value
            base_growth_pct = _safe_ratio(base_market_value_change, denom_intrinsic)
        raw_income = _ledger_income(
            account,
            pm.position.symbol,
            base_position_id=pm.position.position_id,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        income_total_realized = _income_after_base_protection(original_base_value, current_base_value, protection, raw_income)
        gap, applied, income_after, juice_needed = _protection_allocation(denom_intrinsic, current_base_value, protection, raw_income)
        current_intrinsic = pm.current_base_intrinsic or 0.0
        intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + (protection or 0.0)))
        income_efficiency = _safe_ratio(income_total_realized, denom_intrinsic)
        week_income, month_income = _stock_income_rates(
            account,
            pm.position.symbol,
            base_position_id=pm.position.position_id,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        consistency_pct = _stock_income_consistency(account, pm.position.symbol)

        rows.append(
            StockSummaryRow(
                ticker=pm.position.symbol,
                original_base_value=_clean_number(original_base_value),
                current_base_value=_clean_number(current_base_value),
                initial_base_intrinsic=_clean_number(pm.initial_base_intrinsic),
                initial_base_extrinsic=_clean_number(pm.initial_base_extrinsic),
                current_base_intrinsic=_clean_number(pm.current_base_intrinsic),
                total_protection_collected=_clean_number(protection),
                base_strength_ratio=_clean_number(base_strength_ratio),
                base_market_value_change=_clean_number(base_market_value_change),
                base_growth_pct=_clean_number(base_growth_pct),
                income_total_realized=float(income_total_realized),
                income_after_protection=_clean_number(income_after),
                protection_gap=_clean_number(intrinsic_gap),
                protection_juice_applied=_clean_number(applied),
                juice_needed_for_protection=_clean_number(juice_needed),
                income_rate_weekly=_clean_number(week_income),
                income_rate_monthly=_clean_number(month_income),
                income_efficiency=_clean_number(income_efficiency),
                income_consistency_pct=_clean_number(consistency_pct),
                short_extrinsic_net=_clean_number(pm.short_extrinsic_net),
                long_extrinsic_loan=_clean_number(pm.long_extrinsic_loan),
                long_extrinsic_paid=_clean_number(pm.long_extrinsic_paid),
                long_extrinsic_remaining=_clean_number(pm.long_extrinsic_remaining),
                long_extrinsic_income=_clean_number(pm.long_extrinsic_income),
            )
        )

    # Contribution scores
    total_income = sum(r.income_total_realized for r in rows)
    total_protection = sum((r.total_protection_collected or 0.0) for r in rows)
    total_growth = sum((r.base_market_value_change or 0.0) for r in rows)
    for row in rows:
        row.contribution_income_pct = _safe_ratio(row.income_total_realized, total_income)
        row.contribution_protection_pct = _safe_ratio(row.total_protection_collected or 0.0, total_protection)
        row.contribution_growth_pct = _safe_ratio(row.base_market_value_change or 0.0, total_growth)

    return rows


def portfolio_summary(
    account: Optional[str] = None,
    include_closed: bool = False,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> PortfolioSummary:
    """Compute portfolio-level KPIs and ranked stock rows."""
    rows = stock_summary_rows(
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )
    snapshots = business_loader.list_nav(account)
    latest_nav = _latest(snapshots, "date")
    total_account_value = _to_float(latest_nav["nav_total"]) if latest_nav is not None else None
    total_cash = _to_float(latest_nav["nav_cash"]) if latest_nav is not None else None

    total_income = sum(r.income_total_realized for r in rows)
    total_income_after_protection = sum((r.income_after_protection or 0.0) for r in rows)
    total_protection_gap = sum((r.protection_gap or 0.0) for r in rows)
    total_juice_needed = sum((r.juice_needed_for_protection or 0.0) for r in rows)
    total_current_base_value = sum((r.current_base_value or 0.0) for r in rows)
    total_initial_base_intrinsic = sum((r.initial_base_intrinsic or 0.0) for r in rows)
    total_initial_base_extrinsic = sum((r.initial_base_extrinsic or 0.0) for r in rows)
    total_current_base_intrinsic = sum((r.current_base_intrinsic or 0.0) for r in rows)
    total_protection_collected = sum((r.total_protection_collected or 0.0) for r in rows)
    total_short_extrinsic_net = sum((r.short_extrinsic_net or 0.0) for r in rows)
    total_long_extrinsic_loan = sum((r.long_extrinsic_loan or 0.0) for r in rows)
    total_long_extrinsic_paid = sum((r.long_extrinsic_paid or 0.0) for r in rows)
    total_long_extrinsic_remaining = sum((r.long_extrinsic_remaining or 0.0) for r in rows)
    total_long_extrinsic_income = sum((r.long_extrinsic_income or 0.0) for r in rows)

    # Weighted averages for base strength/growth (weight by original base)
    total_original = total_initial_base_intrinsic or sum((r.original_base_value or 0.0) for r in rows)
    base_strength_ratio = None
    base_growth_pct = None
    if total_original:
        num_strength = sum(((r.current_base_value or 0.0) + (r.total_protection_collected or 0.0)) for r in rows)
        num_growth = sum(((r.current_base_value or 0.0) - (r.original_base_value or 0.0)) for r in rows)
        base_strength_ratio = _safe_ratio(num_strength, total_original)
        base_growth_pct = _safe_ratio(num_growth, total_original)

    return PortfolioSummary(
        total_account_value=_clean_number(total_account_value),
        total_cash=_clean_number(total_cash),
        total_base_value_initial=_clean_number((total_initial_base_intrinsic + total_initial_base_extrinsic) or total_original),
        total_current_base_value=_clean_number(total_current_base_value),
        total_initial_base_intrinsic=_clean_number(total_initial_base_intrinsic),
        total_initial_base_extrinsic=_clean_number(total_initial_base_extrinsic),
        total_current_base_intrinsic=_clean_number(total_current_base_intrinsic),
        total_protection_collected=_clean_number(total_protection_collected),
        total_base_plus_protection=_clean_number((total_current_base_value or 0.0) + (total_protection_collected or 0.0)),
        total_income_realized=float(total_income),
        total_income_after_protection=_clean_number(total_income_after_protection),
        total_protection_gap=_clean_number(total_protection_gap),
        total_juice_needed_for_protection=_clean_number(total_juice_needed),
        total_base_strength_ratio=_clean_number(base_strength_ratio),
        total_base_growth_pct=_clean_number(base_growth_pct),
        total_short_extrinsic_net=_clean_number(total_short_extrinsic_net),
        total_long_extrinsic_loan=_clean_number(total_long_extrinsic_loan),
        total_long_extrinsic_paid=_clean_number(total_long_extrinsic_paid),
        total_long_extrinsic_remaining=_clean_number(total_long_extrinsic_remaining),
        total_long_extrinsic_income=_clean_number(total_long_extrinsic_income),
        stocks=rows,
    )


def stock_detail(
    ticker: str,
    account: Optional[str] = None,
    include_closed: bool = False,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> StockDetail:
    """Per-stock drillable detail including pillars and series."""
    ticker = ticker.upper()
    rows = [
        pm
        for pm in position_metrics(
            account,
            include_closed=include_closed,
            expiry_start=expiry_start,
            expiry_end=expiry_end,
        )
        if pm.position.symbol.upper() == ticker
    ]
    if not rows:
        return StockDetail(ticker=ticker)

    pm = rows[0]
    total_long_extrinsic_loan = sum((r.long_extrinsic_loan or 0.0) for r in rows)
    total_long_extrinsic_paid = sum((r.long_extrinsic_paid or 0.0) for r in rows)
    total_long_extrinsic_remaining = sum((r.long_extrinsic_remaining or 0.0) for r in rows)
    total_long_extrinsic_income = sum((r.long_extrinsic_income or 0.0) for r in rows)
    total_short_extrinsic_net = sum((r.short_extrinsic_net or 0.0) for r in rows)
    total_initial_base_intrinsic = sum((r.initial_base_intrinsic or 0.0) for r in rows)
    total_initial_base_extrinsic = sum((r.initial_base_extrinsic or 0.0) for r in rows)
    total_current_base_intrinsic = sum((r.current_base_intrinsic or 0.0) for r in rows)
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)
    initial_intrinsic = pm.initial_base_intrinsic or 0.0
    initial_extrinsic = pm.initial_base_extrinsic or 0.0
    original_base_value = (initial_intrinsic + initial_extrinsic) or pm.initial_base_cost or pm.base_cost
    current_base_value = pm.base_value
    protection = pm.net_intrinsic_to_date
    denom_intrinsic = initial_intrinsic or original_base_value
    base_strength_ratio = _safe_ratio((current_base_value or 0) + (protection or 0), denom_intrinsic)
    base_growth_pct = None
    if denom_intrinsic:
        base_growth_pct = _safe_ratio((current_base_value or 0) - denom_intrinsic, denom_intrinsic)

    raw_income = _ledger_income(
        account,
        ticker,
        base_position_id=pm.position.position_id,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    gap, applied, income_after, juice_needed = _protection_allocation(denom_intrinsic, current_base_value, protection, raw_income)
    current_intrinsic = pm.current_base_intrinsic or 0.0
    intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + (protection or 0.0)))
    income_total_realized = _income_after_base_protection(original_base_value, current_base_value, protection, raw_income)
    income_efficiency = _safe_ratio(income_total_realized, denom_intrinsic)
    income_series = _income_series_by_week(account, symbol=ticker, base_position_id=pm.position.position_id)
    base_strength_series = _base_strength_series_placeholder(_clean_number(base_strength_ratio))
    base_value_series = _base_value_series_placeholder(_clean_number(current_base_value))
    base_plus_protection = ((pm.current_base_intrinsic or 0.0) + (protection or 0.0))

    return StockDetail(
        ticker=ticker,
        base_strength_ratio=_clean_number(base_strength_ratio),
        base_growth_pct=_clean_number(base_growth_pct),
        income_total_realized=float(income_total_realized),
        income_after_protection=_clean_number(income_after),
        income_efficiency=_clean_number(income_efficiency),
        base_market_value=_clean_number(current_base_value),
        original_base_value=_clean_number(original_base_value),
        initial_base_intrinsic=_clean_number(total_initial_base_intrinsic),
        initial_base_extrinsic=_clean_number(total_initial_base_extrinsic),
        current_base_intrinsic=_clean_number(total_current_base_intrinsic),
        base_plus_protection=_clean_number(base_plus_protection),
        total_protection_collected=_clean_number(protection),
        protection_gap=_clean_number(intrinsic_gap),
        net_juice_total=_clean_number(raw_income),
        short_extrinsic_net=_clean_number(total_short_extrinsic_net),
        long_extrinsic_loan=_clean_number(total_long_extrinsic_loan),
        long_extrinsic_paid=_clean_number(total_long_extrinsic_paid),
        long_extrinsic_remaining=_clean_number(total_long_extrinsic_remaining),
        long_extrinsic_income=_clean_number(total_long_extrinsic_income),
        income_series_weekly=income_series,
        base_strength_series_weekly=base_strength_series,
        base_value_series_weekly=base_value_series,
        positions=rows,
    )


def _latest_cycle_income(
    account: Optional[str],
    symbol: str,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    df["ticker"] = df.get("ticker").astype(str).str.upper()
    df = df[df["ticker"] == symbol.upper()]
    if df.empty:
        return 0.0
    df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    if expiry_start is not None or expiry_end is not None:
        normalized = df["expiry"].dt.normalize()
        if expiry_start is not None:
            df = df[normalized >= expiry_start]
        if expiry_end is not None:
            df = df[normalized <= expiry_end]
    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    df = df.dropna(subset=["signed_juice_dollars"])
    if df.empty:
        return 0.0
    if df["expiry"].notna().any():
        df = df.dropna(subset=["expiry"])
        grouped = df.groupby("expiry")["signed_juice_dollars"].sum().reset_index().sort_values("expiry")
        latest = grouped.iloc[-1]
        return float(latest["signed_juice_dollars"])
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date")
        return float(df.iloc[-1]["signed_juice_dollars"])
    return 0.0


def protection_metrics(
    symbol: str,
    account: Optional[str] = None,
    target_income: float = 82.5,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> ProtectionMetrics:
    symbol = symbol.upper()
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)
    cumulative_income = _ledger_income(account, symbol, expiry_start=expiry_start_ts, expiry_end=expiry_end_ts)
    latest_cycle_income = _latest_cycle_income(
        account,
        symbol,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    shortfall = max(0.0, target_income - latest_cycle_income)
    defense_cost = shortfall
    estimated_break_even_drop = None
    try:
        estimated_break_even_drop = cumulative_income / 100.0
    except Exception:
        estimated_break_even_drop = None

    return ProtectionMetrics(
        symbol=symbol,
        account=account,
        target_income=target_income,
        latest_cycle_income=latest_cycle_income,
        shortfall=shortfall,
        defense_cost=defense_cost,
        cumulative_income=cumulative_income,
        estimated_break_even_drop=estimated_break_even_drop,
    )


def business_dashboard(
    account: Optional[str] = None,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> BusinessDashboard:
    trades = excel_loader.get_all_trades(account)
    snapshots = business_loader.list_nav(account)

    week_start, week_end = _current_week_window()
    month_start, month_end = _current_month_window()
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)

    week_juice = _net_juice_by_expiry_window(
        account,
        week_start,
        week_end,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    month_juice = _net_juice_by_expiry_window(
        account,
        month_start,
        month_end,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )

    nav_week_start = _nav_at_start(snapshots, week_start)
    nav_month_start = _nav_at_start(snapshots, month_start)

    weekly_yield = _safe_ratio(week_juice, nav_week_start)
    monthly_yield = _safe_ratio(month_juice, nav_month_start)

    profitable_pct, avg_weekly = _consistency(trades)

    contributed = _contributed_capital(snapshots)
    nav_current, drawdown = _drawdown(snapshots["nav_total"]) if "nav_total" in snapshots else (None, None)
    preservation = _safe_ratio(nav_current, contributed) if nav_current is not None else None

    pos_metrics = position_metrics(account, expiry_start=expiry_start, expiry_end=expiry_end)
    required_reserve = float(sum((pm.reserve_cash or 0) for pm in pos_metrics))
    free_cash = None
    nav_cash = None
    nav_long_value = None
    nav_liabilities = None
    latest_nav = _latest(snapshots, "date")
    if latest_nav is not None:
        nav_cash = _to_float(latest_nav.get("nav_cash"))
        nav_long_value = _to_float(latest_nav.get("nav_long_value"))
        nav_liabilities = _to_float(latest_nav.get("nav_liabilities"))
        # Treat cash as deployable for reserve coverage if nothing else is provided
        free_cash = nav_cash
    # If no long value stored, derive from bases (base_value sum)
    if nav_long_value is None:
        nav_long_value = float(sum((pm.base_value or 0.0) for pm in pos_metrics)) if pos_metrics else None
    reserve_coverage = _safe_ratio(free_cash, required_reserve) if free_cash is not None else None

    worst_replacement = None
    if pos_metrics:
        ratios = [pm.replacement_ratio for pm in pos_metrics if pm.replacement_ratio is not None]
        if ratios:
            worst_replacement = min(ratios)
    concentration = None
    if nav_current and pos_metrics:
        largest = max((pm.base_value or 0.0) for pm in pos_metrics)
        concentration = _safe_ratio(largest, nav_current)

    # Portfolio replacement ratio (replace-all)
    total_num = 0.0
    total_den = 0.0
    for pm in pos_metrics:
        base_value = pm.base_value or 0.0
        protection = pm.net_intrinsic_to_date or 0.0
        benchmark_cost = pm.replacement_cost or pm.base_cost or abs(base_value)
        if benchmark_cost:
            total_num += base_value + protection
            total_den += benchmark_cost
    portfolio_replacement_ratio = _safe_ratio(total_num, total_den) if total_den else None

    # Distributable income (weekly/monthly)
    required_reserve_pct = DEFAULT_RESERVE_PCT
    required_reserve_nav = (nav_current * required_reserve_pct) if nav_current else 0.0
    reserve_top_up_needed = 0.0
    if free_cash is not None:
        reserve_top_up_needed = max(0.0, required_reserve_nav - free_cash)
    base_top_up_needed = 0.0
    if portfolio_replacement_ratio is not None and portfolio_replacement_ratio < FLOOR_BUFFER and total_den:
        target_num = total_den * FLOOR_BUFFER
        base_top_up_needed = max(0.0, target_num - total_num)
    def _distributable(net_juice: float | None) -> float | None:
        if net_juice is None:
            return None
        return max(0.0, net_juice - reserve_top_up_needed - base_top_up_needed)
    distributable_week = _distributable(week_juice)
    distributable_month = _distributable(month_juice)
    income_allowed_weekly = (
        distributable_week is not None
        and distributable_week > 0
        and (reserve_coverage or 0) >= 1.0
        and (portfolio_replacement_ratio or 0) >= FLOOR_BUFFER
    )
    income_allowed_monthly = (
        distributable_month is not None
        and distributable_month > 0
        and (reserve_coverage or 0) >= 1.0
        and (portfolio_replacement_ratio or 0) >= FLOOR_BUFFER
    )

    # Mode flags
    scale_ready = (
        (reserve_coverage or 0) >= 1.0
        and (portfolio_replacement_ratio or 0) >= 1.10
        and (preservation or 0) >= 1.0
    )
    strengthen = (
        (reserve_coverage or 0) < 1.0
        or (worst_replacement or 0) < 1.0
        or (portfolio_replacement_ratio or 0) < FLOOR_BUFFER
    )
    if scale_ready:
        mode = "SCALE_READY"
    elif strengthen:
        mode = "STRENGTHEN"
    else:
        mode = "MAINTAIN"

    nav_weekly_points, nav_monthly_points = _nav_series_weekly_monthly(snapshots)

    return BusinessDashboard(
        weekly_net_juice=_clean_number(week_juice) or 0.0,
        monthly_net_juice=_clean_number(month_juice) or 0.0,
        weekly_juice_yield_pct=_clean_number((weekly_yield * 100) if weekly_yield is not None else 0.0) or 0.0,
        monthly_juice_yield_pct=_clean_number((monthly_yield * 100) if monthly_yield is not None else 0.0) or 0.0,
        consistency_profitable_weeks_pct=_clean_number(profitable_pct) or 0.0,
        consistency_avg_weekly_juice=_clean_number(avg_weekly) or 0.0,
        preservation_ratio=_clean_number(preservation),
        drawdown_pct=_clean_number(drawdown),
        reserve_coverage=_clean_number(reserve_coverage),
        worst_replacement_ratio=_clean_number(worst_replacement),
        concentration_pct=_clean_number(concentration),
        nav_current=_clean_number(nav_current),
        nav_peak=_clean_number(snapshots["nav_total"].max()) if not snapshots.empty else None,
        nav_cash=_clean_number(nav_cash),
        nav_long_value=_clean_number(nav_long_value),
        nav_liabilities=_clean_number(nav_liabilities),
        nav_contributed=_clean_number(contributed),
        portfolio_replacement_ratio=_clean_number(portfolio_replacement_ratio),
        distributable_income_weekly=_clean_number(distributable_week),
        distributable_income_monthly=_clean_number(distributable_month),
        income_allowed_weekly=income_allowed_weekly if distributable_week is not None else None,
        income_allowed_monthly=income_allowed_monthly if distributable_month is not None else None,
        mode=mode,
        nav_weekly=nav_weekly_points,
        nav_monthly=nav_monthly_points,
    )

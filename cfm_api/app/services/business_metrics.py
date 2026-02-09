"""Pure calculation helpers for business scoreboard metrics."""
from __future__ import annotations

from datetime import timedelta, datetime, date
import logging
from typing import Optional, Tuple, List, Dict

import numpy as np
import pandas as pd

from ..utils import excel_loader, business_loader
from ..models.business import (
    BusinessDashboard,
    PositionMetrics,
    BasePosition,
    MarkPositionRow,
    MinimalPositionStatus,
    ShortLegSignal,
    NavPoint,
    PortfolioSummary,
    StockSummaryRow,
    StockDetail,
    PillarSeriesPoint,
    RegimeEntry,
    ProtectionMetrics,
    AccountSummary,
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


def _month_window_for(day: date | datetime | pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    stamp = pd.Timestamp(day).normalize()
    start = stamp.replace(day=1)
    end = (start + pd.offsets.MonthBegin(1)).normalize()
    return start, end


def compute_ticket_health(long_dte_days: Optional[int], long_delta: Optional[float]) -> str:
    if long_dte_days is None:
        return "B"
    if long_dte_days >= 90:
        runway = "STRONG"
    elif long_dte_days >= 60:
        runway = "MEDIUM"
    else:
        runway = "LOW"

    if long_delta is None:
        delta_band = "SOFT"
    elif long_delta >= 0.85:
        delta_band = "HEALTHY"
    elif long_delta >= 0.75:
        delta_band = "SOFT"
    else:
        delta_band = "WEAK"

    if runway == "LOW" or delta_band == "WEAK":
        return "C"
    if runway == "STRONG" and delta_band in {"HEALTHY", "SOFT"}:
        return "A"
    return "B"


def compute_conviction(market_regime: str, stock_regime: str) -> str:
    m = _normalize_condition(market_regime)
    s = _normalize_condition(stock_regime)
    if not m or not s or m == "UNKNOWN" or s == "UNKNOWN":
        return "MED"
    if m == "RED" or s == "RED":
        return "LOW"
    if m == "YELLOW" or s == "YELLOW":
        return "MED"
    return "HIGH"


def compute_operating_posture(conviction: str, ticket_health: str) -> str:
    if conviction == "LOW" or ticket_health == "C":
        return "DEFEND"
    if conviction == "HIGH" and ticket_health in {"A", "B"}:
        return "ATTACK"
    return "MANAGE"


def _select_long_leg_for_position(legs: pd.DataFrame) -> Optional[pd.Series]:
    if legs.empty:
        return None
    df = legs.copy()
    df["instrument_type_norm"] = df.get("instrument_type").fillna("").astype(str).str.upper()
    df["side_norm"] = df.get("side").fillna("").astype(str).str.upper()
    df["tag_norm"] = df.get("tag").fillna("").astype(str).str.upper()
    df["base_leg_id"] = df.get("base_leg_id").fillna("").astype(str).str.strip()

    option_mask = df["instrument_type_norm"].str.contains("CALL") | df["instrument_type_norm"].str.contains("OPTION")
    candidates = df[option_mask & (df["side_norm"] == "BUY") & df.get("expiry").notna()].copy()
    if candidates.empty:
        return None

    closed_mask = df["tag_norm"].isin({"CLOSE", "REPLACE"}) | (df["side_norm"] == "SELL")
    closed_ids = set(df.loc[closed_mask, "base_leg_id"].dropna().astype(str).str.strip().tolist())
    if closed_ids:
        candidates = candidates[~candidates["base_leg_id"].isin(closed_ids)]
    if candidates.empty:
        return None

    candidates["date"] = pd.to_datetime(candidates.get("date"), errors="coerce")
    time_str = candidates.get("time", "").fillna("").astype(str).str.strip()
    date_str = candidates["date"].dt.strftime("%Y-%m-%d")
    combined = (date_str + " " + time_str).str.strip()
    candidates["sort_ts"] = pd.to_datetime(combined, errors="coerce")
    latest_ts = candidates["sort_ts"].max()
    latest = candidates[candidates["sort_ts"] == latest_ts]
    if len(latest) != 1:
        return None
    return latest.iloc[0]


def _long_leg_dte_delta(legs: pd.DataFrame, today: date) -> tuple[Optional[int], Optional[float]]:
    row = _select_long_leg_for_position(legs)
    if row is None:
        return None, None
    expiry = pd.to_datetime(row.get("expiry"), errors="coerce")
    if pd.isna(expiry):
        return None, None
    dte = (expiry.normalize() - pd.Timestamp(today).normalize()).days
    delta = _to_float_or_none(row.get("delta"))
    return int(dte), delta


def get_net_juice_current_month_by_expiry(
    account: Optional[str],
    base_position_id: str,
    today: date | datetime | pd.Timestamp | None = None,
) -> float:
    if not base_position_id:
        return 0.0
    today = pd.Timestamp(today).normalize() if today is not None else pd.Timestamp.now().normalize()
    start, end = _month_window_for(today)
    df = _normalize_ledger_df(excel_loader.get_ledger_rows(account))
    if df.empty:
        return 0.0
    df = _ensure_signed_juice(df)
    df = _coerce_expiry(df)
    df = df[df.get("base_position_id").astype(str) == str(base_position_id)]
    df = df.dropna(subset=["expiry", "signed_juice_dollars"])
    if df.empty:
        return 0.0
    action = df.get("action").astype(str).str.lower()
    df = df[action.str.contains("close", na=False)]
    side = df.get("side").astype(str).str.upper()
    df = df[side == "CALL"]
    mask = (df["expiry"] >= start) & (df["expiry"] < end)
    return float(df.loc[mask, "signed_juice_dollars"].sum())


def _week_start(date_val: pd.Timestamp) -> pd.Timestamp:
    return date_val - pd.to_timedelta(date_val.weekday(), unit="D")


def _normalize_condition(value: Optional[str]) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().upper()
    return normalized


def _to_float_or_none(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(parsed):
        return None
    return parsed


def _to_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "t"}


def _latest_regime_entry(regimes: pd.DataFrame, symbol: Optional[str]) -> Dict:
    if regimes.empty:
        return {}
    df = regimes.copy()
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    key = (symbol or "").strip().upper()
    df = df[df["symbol_norm"] == key]
    if df.empty:
        return {}
    if "date" in df.columns:
        df = df.sort_values("date")
    latest = df.iloc[-1]
    return latest.to_dict()


def _latest_regime_entry_on_or_before(regimes: pd.DataFrame, symbol: Optional[str], day: date) -> Dict:
    if regimes.empty:
        return {}
    df = regimes.copy()
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    key = (symbol or "").strip().upper()
    df = df[df["symbol_norm"] == key]
    if df.empty:
        return {}
    if "date" in df.columns:
        df = df[df["date"] <= pd.Timestamp(day)]
        if df.empty:
            return {}
        df = df.sort_values("date")
    latest = df.iloc[-1]
    return latest.to_dict()


def _latest_market_regime(regimes: pd.DataFrame, day: date) -> Dict:
    if regimes.empty:
        return {}
    df = regimes.copy()
    if "date" in df.columns:
        df = df[df["date"] <= pd.Timestamp(day)]
        if df.empty:
            return {}
        df = df.sort_values("date")
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    latest_overall = df.iloc[-1]
    market_rows = df[df["symbol_norm"] == ""]
    if market_rows.empty:
        return latest_overall.to_dict()
    latest_market = market_rows.iloc[-1]
    # Only prefer blank-symbol market rows if they're as recent as the latest overall entry.
    if "date" in df.columns:
        try:
            if pd.Timestamp(latest_market.get("date")) >= pd.Timestamp(latest_overall.get("date")):
                return latest_market.to_dict()
        except Exception:
            pass
    return latest_overall.to_dict()


def _initial_base_cost_for_position(
    legs: pd.DataFrame,
    ledger_scope: Optional[pd.DataFrame],
    open_base_leg_ids: List[str],
) -> Optional[float]:
    principal_cost = _initial_investment_from_marked_legs(legs)
    if principal_cost is None and ledger_scope is not None and open_base_leg_ids:
        principal_cost = _base_open_cost_from_ledger(ledger_scope, open_base_leg_ids)
    if principal_cost is None and legs is not None and not legs.empty:
        principal_cost = _base_entry_cost_from_legs(legs)
    return float(principal_cost) if principal_cost is not None else None


def _position_open_date_from_legs(legs: pd.DataFrame) -> Optional[pd.Timestamp]:
    if legs.empty:
        return None
    scoped = legs.copy()
    scoped["tag"] = scoped.get("tag").astype(str).str.upper()
    opens = scoped[scoped["tag"] == "OPEN"].copy()
    if opens.empty:
        opens = scoped.copy()
    opens.loc[:, "date"] = pd.to_datetime(opens.get("date"), errors="coerce")
    opens = opens.dropna(subset=["date"])
    if opens.empty:
        return None
    return opens["date"].min()


def _net_juice_since_open(
    ledger_df: pd.DataFrame,
    base_position_id: str,
    marked_base_leg_ids: List[str],
) -> float:
    if ledger_df.empty or not base_position_id or not marked_base_leg_ids:
        return 0.0
    df = ledger_df.copy()
    df = df[df.get("base_position_id").astype(str) == str(base_position_id)]
    if df.empty:
        return 0.0
    df = df[df["base_leg_id"].astype(str).isin(marked_base_leg_ids)]
    if df.empty:
        return 0.0
    snapshot = _short_position_snapshot(df, defense_df=df)
    return float(snapshot.get("short_realized_pnl") or 0.0)


def _weekly_net_income_for_position(
    ledger_df: pd.DataFrame,
    base_position_id: str,
    open_base_leg_ids: List[str],
) -> float:
    if ledger_df.empty or not base_position_id:
        return 0.0
    scoped = ledger_df[ledger_df["base_position_id"] == str(base_position_id)].copy()
    if scoped.empty:
        return 0.0
    if open_base_leg_ids:
        scoped = scoped[scoped["base_leg_id"].astype(str).isin(open_base_leg_ids)]
    snapshot = _short_position_snapshot(scoped, defense_df=scoped)
    weekly_locked = float(snapshot.get("weekly_locked_income") or 0.0)
    weekly_defense = float(snapshot.get("weekly_defense_debit") or 0.0)
    return float(round(weekly_locked - weekly_defense, 2))


def _weekly_net_juice_by_expiry_week(
    ledger_df: pd.DataFrame,
    base_position_id: str,
    week_start: pd.Timestamp,
    week_end: pd.Timestamp,
) -> float:
    if ledger_df.empty or not base_position_id:
        return 0.0
    df = ledger_df.copy()
    df = df[df.get("base_position_id").astype(str) == str(base_position_id)]
    if df.empty:
        return 0.0
    df = _coerce_expiry(df)
    df = df.dropna(subset=["expiry", "signed_juice_dollars"])
    if df.empty:
        return 0.0
    if "action" in df.columns:
        action = df["action"].astype(str).str.upper()
        df = df[action.str.contains("CLOSE", na=False)]
    if "side" in df.columns:
        side = df["side"].astype(str).str.upper()
        df = df[side == "CALL"]
    expiry_mask = (df["expiry"] >= week_start) & (df["expiry"] < week_end)
    df = df[expiry_mask]
    if df.empty:
        return 0.0
    target_expiry = df["expiry"].min()
    df = df[df["expiry"] == target_expiry]
    gains: List[float] = []
    for _, row in df.iterrows():
        signed = row.get("signed_juice_dollars")
        if signed is None or pd.isna(signed):
            signed = _signed_juice_from_row(row)
        if signed is None or pd.isna(signed):
            continue
        gains.append(-float(signed))
    return float(sum(gains))


def _regime_condition_series(
    regimes: pd.DataFrame,
    symbol: Optional[str],
    field: str,
    limit: int,
) -> List[str]:
    if regimes.empty or field not in regimes.columns:
        return []
    df = regimes.copy()
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    key = (symbol or "").strip().upper()
    df = df[df["symbol_norm"] == key]
    if df.empty:
        return []
    if "date" in df.columns:
        df = df.sort_values("date", ascending=False)
    series = df[field].dropna().astype(str).str.upper().tolist()
    return series[:limit]


def _count_consecutive_true(flags: List[bool]) -> int:
    count = 0
    for flag in flags:
        if not flag:
            break
        count += 1
    return count


def _latest_circuit_entry(entries: pd.DataFrame, symbol: Optional[str]) -> Dict:
    if entries.empty:
        return {}
    df = entries.copy()
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    key = (symbol or "").strip().upper()
    df = df[df["symbol_norm"] == key]
    if df.empty:
        return {}
    if "date" in df.columns:
        df = df.sort_values("date")
    latest = df.iloc[-1]
    return latest.to_dict()


def _circuit_series(entries: pd.DataFrame, symbol: Optional[str], limit: int) -> List[Dict]:
    if entries.empty:
        return []
    df = entries.copy()
    df["symbol_norm"] = df.get("symbol", "").fillna("").astype(str).str.upper()
    key = (symbol or "").strip().upper()
    df = df[df["symbol_norm"] == key]
    if df.empty:
        return []
    if "date" in df.columns:
        df = df.sort_values("date", ascending=False)
    return [row.to_dict() for _, row in df.head(limit).iterrows()]


def _market_breaker_from_entry(entry: Dict) -> Tuple[bool, bool, List[str]]:
    reasons: List[str] = []
    market_regime = _normalize_condition(entry.get("market_regime"))
    index_close = _to_float_or_none(entry.get("index_close"))
    index_ema21 = _to_float_or_none(entry.get("index_ema21"))
    index_sma50 = _to_float_or_none(entry.get("index_sma50"))
    index_ema8 = _to_float_or_none(entry.get("index_ema8"))

    market_soft = False
    market_hard = False

    if market_regime == "YELLOW":
        market_soft = True
        reasons.append("M_YELLOW")
    if market_regime == "RED":
        market_hard = True
        reasons.append("M_RED")
    if index_close is not None and index_ema21 is not None and index_close < index_ema21:
        market_soft = True
        reasons.append("M_<21")
    if index_close is not None and index_sma50 is not None and index_close < index_sma50:
        market_hard = True
        reasons.append("M_<50")
    if index_ema8 is not None and index_ema21 is not None and index_ema8 < index_ema21:
        market_hard = True
        reasons.append("M_8<21")

    return market_soft, market_hard, reasons


def _stock_breaker_from_entry(entry: Dict, cushion_min: float) -> Tuple[bool, bool, bool, bool, List[str]]:
    reasons: List[str] = []
    stock_regime = _normalize_condition(entry.get("stock_regime"))
    stock_close = _to_float_or_none(entry.get("stock_close"))
    stock_ema21 = _to_float_or_none(entry.get("stock_ema21"))
    stock_sma50 = _to_float_or_none(entry.get("stock_sma50"))
    stock_ema8 = _to_float_or_none(entry.get("stock_ema8"))
    stock_sma200 = _to_float_or_none(entry.get("stock_sma200"))
    cushion_pct = _to_float_or_none(entry.get("cushion_pct"))
    catastrophic_event = _to_bool(entry.get("catastrophic_event"))
    earnings_days = _to_float_or_none(entry.get("earnings_days"))

    stock_soft = False
    stock_hard = False
    stock_emergency = False
    earnings_risk = False

    if stock_regime == "YELLOW":
        stock_soft = True
        reasons.append("S_YELLOW")
    if stock_regime == "RED":
        stock_hard = True
        reasons.append("S_RED")
    if stock_close is not None and stock_ema21 is not None and stock_close < stock_ema21:
        stock_soft = True
        reasons.append("S_<21")
    if stock_ema8 is not None and stock_ema21 is not None and stock_ema8 < stock_ema21:
        stock_hard = True
        reasons.append("S_8<21")
    if stock_close is not None and stock_sma50 is not None and stock_close < stock_sma50:
        stock_hard = True
        reasons.append("S_<50")
    if stock_close is not None and stock_sma200 is not None and stock_close < stock_sma200:
        stock_emergency = True
        reasons.append("S_<200")
    if cushion_pct is not None and cushion_pct < cushion_min:
        stock_soft = True
        reasons.append("S_CUSHION")
    if catastrophic_event:
        stock_emergency = True
        reasons.append("S_CATA")
    if earnings_days is not None and earnings_days <= 10:
        earnings_risk = True
        reasons.append("EARN_10D")

    return stock_soft, stock_hard, stock_emergency, earnings_risk, reasons


def _circuit_breaker_from_regimes(ticker: str, regimes: pd.DataFrame) -> Dict[str, Optional[str] | List[str]]:
    if regimes.empty:
        return {
            "breaker_state": "NONE",
            "breaker_reasons": [],
            "breaker_action": "HOLD",
            "breaker_countdown": None,
        }
    market_entry = _latest_regime_entry(regimes, "")
    stock_entry = _latest_regime_entry(regimes, ticker)
    market_condition = _normalize_condition(market_entry.get("market_condition"))
    stock_condition = _normalize_condition(stock_entry.get("stock_condition"))

    market_soft = market_condition == "YELLOW"
    market_hard = market_condition == "RED"
    stock_soft = stock_condition == "YELLOW"
    stock_hard = stock_condition == "RED"

    stock_series = _regime_condition_series(regimes, ticker, "stock_condition", limit=7)
    hard_flags = [cond == "RED" for cond in stock_series]
    soft_flags = [cond == "YELLOW" for cond in stock_series]
    hard_consecutive = _count_consecutive_true(hard_flags)
    soft_count = sum(soft_flags)

    hard_persist = hard_consecutive >= 2
    soft_persist = soft_count >= 5

    reasons: List[str] = []
    if market_hard:
        reasons.append("M_RED")
    elif market_soft:
        reasons.append("M_YELLOW")
    if stock_hard:
        reasons.append("S_RED")
    elif stock_soft:
        reasons.append("S_YELLOW")
    if hard_persist:
        reasons.append("S_HARD_2D")
    elif soft_persist:
        reasons.append("S_SOFT_5_OF_7")

    breaker_countdown = None
    if hard_consecutive == 1:
        breaker_countdown = "Hard breaker day 1 of 2"
    elif hard_consecutive >= 2:
        breaker_countdown = "Hard breaker day 2 of 2"

    if stock_hard or market_hard or hard_persist or soft_persist:
        breaker_state = "HARD"
    elif stock_soft or market_soft:
        breaker_state = "SOFT"
    else:
        breaker_state = "NONE"

    if breaker_state == "HARD":
        breaker_action = "EXIT"
    elif breaker_state == "SOFT":
        breaker_action = "DEFEND"
    else:
        breaker_action = "GROW" if (market_condition == "GREEN" and stock_condition == "GREEN") else "HOLD"

    return {
        "breaker_state": breaker_state,
        "breaker_reasons": reasons,
        "breaker_action": breaker_action,
        "breaker_countdown": breaker_countdown,
    }


def _circuit_breaker_from_inputs(
    ticker: str,
    inputs: pd.DataFrame,
    regimes: pd.DataFrame,
) -> Dict[str, Optional[str] | List[str]]:
    if inputs.empty:
        return _circuit_breaker_from_regimes(ticker, regimes)

    market_entry = _latest_circuit_entry(inputs, "")
    stock_entry = _latest_circuit_entry(inputs, ticker)

    market_soft = False
    market_hard = False
    stock_soft = False
    stock_hard = False
    stock_emergency = False
    earnings_risk = False
    soft_persist = False
    reasons: List[str] = []

    if market_entry:
        market_soft, market_hard, market_reasons = _market_breaker_from_entry(market_entry)
        reasons.extend(market_reasons)
    else:
        fallback = _circuit_breaker_from_regimes(ticker, regimes)
        reasons.extend(fallback["breaker_reasons"])
        market_soft = "M_YELLOW" in fallback["breaker_reasons"]
        market_hard = "M_RED" in fallback["breaker_reasons"]

    if stock_entry:
        stock_soft, stock_hard, stock_emergency, earnings_risk, stock_reasons = _stock_breaker_from_entry(stock_entry, cushion_min=0.03)
        reasons.extend(stock_reasons)
    else:
        fallback = _circuit_breaker_from_regimes(ticker, regimes)
        reasons.extend([r for r in fallback["breaker_reasons"] if r.startswith("S_")])
        stock_soft = "S_YELLOW" in fallback["breaker_reasons"]
        stock_hard = "S_RED" in fallback["breaker_reasons"]

    series = _circuit_series(inputs, ticker, limit=7)
    hard_flags = []
    soft_flags = []
    if series:
        for row in series:
            row_soft, row_hard, row_emergency, _, _ = _stock_breaker_from_entry(row, cushion_min=0.03)
            hard_flags.append(row_hard or row_emergency)
            soft_flags.append(row_soft)
    else:
        regime_series = _regime_condition_series(regimes, ticker, "stock_condition", limit=7)
        hard_flags = [cond == "RED" for cond in regime_series]
        soft_flags = [cond == "YELLOW" for cond in regime_series]
    hard_consecutive = _count_consecutive_true(hard_flags)
    soft_count = sum(soft_flags)

    hard_persist = hard_consecutive >= 2
    soft_persist = soft_count >= 5

    if hard_persist:
        reasons.append("S_HARD_2D")
    elif soft_persist:
        reasons.append("S_SOFT_5_OF_7")
    if earnings_risk and "EARN_10D" not in reasons:
        reasons.append("EARN_10D")

    breaker_countdown = None
    if hard_consecutive == 1:
        breaker_countdown = "Hard breaker day 1 of 2"
    elif hard_consecutive >= 2:
        breaker_countdown = "Hard breaker day 2 of 2"

    if stock_emergency:
        breaker_state = "EMERGENCY"
    elif stock_hard or market_hard or hard_persist or soft_persist:
        breaker_state = "HARD"
    elif stock_soft or market_soft or earnings_risk:
        breaker_state = "SOFT"
    else:
        breaker_state = "NONE"

    market_regime = _normalize_condition(market_entry.get("market_regime")) if market_entry else ""
    stock_regime = _normalize_condition(stock_entry.get("stock_regime")) if stock_entry else ""
    index_close = _to_float_or_none(market_entry.get("index_close")) if market_entry else None
    index_ema21 = _to_float_or_none(market_entry.get("index_ema21")) if market_entry else None
    stock_close = _to_float_or_none(stock_entry.get("stock_close")) if stock_entry else None
    stock_ema21 = _to_float_or_none(stock_entry.get("stock_ema21")) if stock_entry else None
    stock_ema8 = _to_float_or_none(stock_entry.get("stock_ema8")) if stock_entry else None

    grow_ok = (
        market_regime == "GREEN"
        and stock_regime == "GREEN"
        and (index_close is None or index_ema21 is None or index_close >= index_ema21)
        and (stock_close is None or stock_ema21 is None or stock_close >= stock_ema21)
        and (stock_ema8 is None or stock_ema21 is None or stock_ema8 >= stock_ema21)
        and not (market_soft or market_hard or stock_soft or stock_hard or stock_emergency or earnings_risk or hard_persist or soft_persist)
    )
    reduce_ok = breaker_state == "SOFT" and (
        soft_persist or "S_CUSHION" in reasons or market_hard or earnings_risk
    )

    if breaker_state in {"HARD", "EMERGENCY"}:
        breaker_action = "EXIT"
    elif reduce_ok:
        breaker_action = "REDUCE"
    elif breaker_state == "SOFT":
        breaker_action = "DEFEND"
    else:
        breaker_action = "GROW" if grow_ok else "HOLD"

    return {
        "breaker_state": breaker_state,
        "breaker_reasons": sorted(set(reasons)),
        "breaker_action": breaker_action,
        "breaker_countdown": breaker_countdown,
    }


def _ledger_by_expiry(account: Optional[str] = None, ticker: Optional[str] = None, base_position_id: Optional[str] = None) -> pd.DataFrame:
    """Build a DataFrame of ledger rows keyed by expiry for juice aggregation."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = _ensure_signed_juice(df)
    df = _coerce_expiry(df)

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


def _normalize_strategy_label(value: object) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if "cashflow" in lowered:
        return "CFM"
    if "cfm" in lowered:
        return "CFM"
    if "juice" in lowered:
        return "JL"
    return text.upper() if text else ""


def _net_juice_current_month_by_position(
    rows: List[Dict[str, object]],
    positions_df: Optional[pd.DataFrame],
    today: date,
) -> Dict[str, float]:
    df = _normalize_ledger_df(rows)
    if df.empty:
        return {}
    df = _ensure_signed_juice(df)
    df = _coerce_expiry(df)
    df["base_position_id"] = df.get("base_position_id").fillna("").astype(str).str.strip()
    df = df[df["base_position_id"] != ""]
    if "action" in df.columns:
        action = df["action"].astype(str).str.upper()
        df = df[action.str.contains("CLOSE", na=False)]
    if "side" in df.columns:
        side = df["side"].astype(str).str.upper()
        df = df[side == "CALL"]

    if positions_df is not None and not positions_df.empty:
        positions_df = positions_df.copy()
        positions_df["strategy_norm"] = positions_df.get("strategy").apply(_normalize_strategy_label)
        cfm_ids = set(
            positions_df.loc[positions_df["strategy_norm"] == "CFM", "position_id"].astype(str).str.strip().tolist()
        )
        if cfm_ids:
            df = df[df["base_position_id"].isin(cfm_ids)]

    start, end = _month_window_for(today)
    df = df.dropna(subset=["expiry", "signed_juice_dollars"])
    if df.empty:
        return {}
    mask = (df["expiry"] >= start) & (df["expiry"] < end)
    df = df[mask]
    if df.empty:
        return {}
    grouped = df.groupby("base_position_id")["signed_juice_dollars"].sum()
    return {str(pid): float(val) for pid, val in grouped.items()}


def _active_long_leg_stats(
    legs: pd.DataFrame, today: date
) -> Tuple[Optional[int], Optional[float], Optional[int], Optional[float], Optional[float], bool]:
    if legs.empty:
        return None, None, None, None, None, True
    df = legs.copy()
    df["instrument_type_norm"] = df.get("instrument_type").fillna("").astype(str).str.upper()
    df["side_norm"] = df.get("side").fillna("").astype(str).str.upper()
    df["tag_norm"] = df.get("tag").fillna("").astype(str).str.upper()
    df["base_leg_id"] = df.get("base_leg_id").fillna("").astype(str).str.strip()
    candidates = df[(df["side_norm"] == "BUY") & df.get("expiry").notna()].copy()
    if candidates.empty:
        return None, None, None, None, None, True

    closed_mask = df["tag_norm"].isin({"CLOSE", "REPLACE"}) | (df["side_norm"] == "SELL")
    closed_ids = set(df.loc[closed_mask, "base_leg_id"].dropna().astype(str).str.strip().tolist())
    if closed_ids:
        candidates = candidates[~candidates["base_leg_id"].isin(closed_ids)]
    if candidates.empty:
        return None, None, None, None, None, True

    candidates["expiry"] = pd.to_datetime(candidates.get("expiry"), errors="coerce")
    candidates = candidates.dropna(subset=["expiry"])
    today_ts = pd.Timestamp(today).normalize()
    candidates = candidates[candidates["expiry"].dt.normalize() >= today_ts]
    if candidates.empty:
        return None, None, None, None, None, True
    dte_days = (candidates["expiry"].dt.normalize() - today_ts).dt.days
    dte_list = [int(val) for val in dte_days.dropna().astype(int).tolist()]
    if not dte_list:
        return None, None, None, None, None, True
    dte_worst = min(dte_list)
    dte_avg = float(np.mean(dte_list)) if dte_list else None

    deltas = []
    if "delta" in candidates.columns:
        for val in candidates["delta"].tolist():
            parsed = _to_float_or_none(val)
            if parsed is not None:
                deltas.append(parsed)
    delta_worst = min(deltas) if deltas else None
    delta_avg = float(np.mean(deltas)) if deltas else None
    return dte_worst, delta_worst, dte_worst, dte_avg, delta_avg, False


def _strength_status(
    stock_regime: Optional[str],
    long_dte_days: Optional[int],
    long_delta: Optional[float],
    ambiguous: bool,
) -> str:
    regime = _normalize_condition(stock_regime)
    if ambiguous or not regime:
        return "Watch"
    if long_dte_days is None:
        return "Watch"
    if long_dte_days >= 90:
        runway = "STRONG"
    elif long_dte_days >= 60:
        runway = "MEDIUM"
    else:
        runway = "LOW"

    delta_healthy = None
    if long_delta is not None:
        delta_healthy = long_delta >= 0.85

    if regime == "GREEN":
        if runway == "STRONG":
            return "Healthy"
        if runway == "MEDIUM":
            if delta_healthy is False:
                return "Watch"
            return "Healthy"
        return "Weak"
    if regime == "YELLOW":
        if runway == "STRONG" and delta_healthy is not False:
            return "Healthy"
        if runway == "MEDIUM":
            return "Watch"
        return "Weak"
    if regime == "RED":
        if runway == "STRONG" and delta_healthy is True:
            return "Healthy"
        if runway == "STRONG" and delta_healthy is False:
            return "Watch"
        if runway == "MEDIUM" and delta_healthy is True:
            return "Watch"
        return "Weak"
    return "Watch"


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
        if is_close:
            juice_per_contract = abs(extrinsic) if extrinsic < 0 else -extrinsic
        else:
            juice_per_contract = extrinsic
    else:
        if is_close:
            juice_per_contract = abs(premium) if premium < 0 else -premium
        else:
            juice_per_contract = premium
    juice_per_contract = round(float(juice_per_contract), 2)
    return round(float(juice_per_contract * contracts * CONTRACT_MULTIPLIER), 2)


def _ensure_signed_juice(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure signed_juice_dollars is present and numeric."""
    df = df.copy()
    df["signed_juice_dollars"] = pd.to_numeric(df.get("signed_juice_dollars"), errors="coerce")
    missing = df["signed_juice_dollars"].isna()
    if missing.any():
        df.loc[missing, "signed_juice_dollars"] = df.loc[missing].apply(_signed_juice_from_row, axis=1)
    return df


def _coerce_expiry(df: pd.DataFrame) -> pd.DataFrame:
    if "expiry" not in df.columns:
        return df
    df = df.copy()
    df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    return df


def _apply_expiry_filter(
    df: pd.DataFrame,
    expiry_start: Optional[pd.Timestamp],
    expiry_end: Optional[pd.Timestamp],
) -> pd.DataFrame:
    if expiry_start is None and expiry_end is None:
        return df
    if "expiry" not in df.columns:
        return df
    df = _coerce_expiry(df)
    normalized = df["expiry"].dt.normalize()
    if expiry_start is not None:
        df = df[normalized >= expiry_start]
    if expiry_end is not None:
        df = df[normalized <= expiry_end]
    return df


def _prepare_ledger_group_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["action"] = df.get("action", "").astype(str).str.lower()
    df = df[~df["action"].str.contains("mark", na=False)]
    df["contracts"] = pd.to_numeric(df.get("contracts"), errors="coerce").fillna(0.0)
    df["ticker"] = df.get("ticker").astype(str).str.upper()
    df["side"] = df.get("side").astype(str)
    df["strike"] = pd.to_numeric(df.get("strike"), errors="coerce")
    df["expiry"] = df.get("expiry")
    df["net_contracts_delta"] = df["contracts"].where(~df["action"].str.contains("close", na=False), -df["contracts"])
    return df


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
    base_leg_ids: Optional[List[str]] = None,
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
    df = _ensure_signed_juice(df)
    df = _apply_expiry_filter(df, expiry_start, expiry_end)
    if ticker:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
        df = df[df["ticker"] == ticker.upper()]
    if base_position_id:
        df = df[df.get("base_position_id") == base_position_id]
    if base_leg_ids is not None:
        if not base_leg_ids:
            return 0.0
        if "base_leg_id" not in df.columns:
            return 0.0
        ids = {str(val) for val in base_leg_ids if val}
        if not ids:
            return 0.0
        df["base_leg_id"] = df.get("base_leg_id").astype(str)
        df = df[df["base_leg_id"].isin(ids)]
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


def _rebalance_extrinsic_to_protection(
    initial_extrinsic: Optional[float],
    net_juice: float,
    protection_gap: float,
) -> float:
    """Move excess extrinsic into protection once extrinsic is paid off."""
    if initial_extrinsic is None:
        return 0.0
    remaining_extrinsic = float(initial_extrinsic) - float(net_juice)
    if remaining_extrinsic > 0 or protection_gap <= 0:
        return 0.0
    excess = abs(remaining_extrinsic)
    return min(excess, protection_gap)


def _short_intrinsic_realized_for_position(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    base_leg_ids: Optional[List[str]] = None,
    opened_date: Optional[pd.Timestamp] = None,
    closed_date: Optional[pd.Timestamp] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Net short intrinsic protection from ledger (realized only)."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    base_position_ids = [base_position_id] if base_position_id else None
    df = _filter_ledger_scope(df, base_leg_ids, base_position_ids, symbol)
    if df.empty:
        return 0.0
    df["action"] = df.get("action", "").astype(str).str.lower()
    df = df[~df["action"].str.contains("mark", na=False)]
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    if opened_date is not None:
        df = df[df["date"] >= opened_date]
    if closed_date is not None:
        df = df[df["date"] <= closed_date]
    df = _apply_expiry_filter(df, expiry_start, expiry_end)
    if df.empty:
        return 0.0

    return _net_protection_from_ledger(df)


def _short_intrinsic_unrealized_for_position(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    base_leg_ids: Optional[List[str]] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
    legs: Optional[pd.DataFrame] = None,
) -> float:
    """Unrealized short intrinsic for open shorts (negative protection)."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    base_position_ids = [base_position_id] if base_position_id else None
    df = _filter_ledger_scope(df, base_leg_ids, base_position_ids, symbol)
    if df.empty:
        return 0.0
    df = _apply_expiry_filter(df, expiry_start, expiry_end)
    if df.empty:
        return 0.0
    df["action"] = df.get("action", "").astype(str).str.lower()
    df = df[~df["action"].str.contains("mark", na=False)]
    df["contracts"] = pd.to_numeric(df.get("contracts"), errors="coerce").fillna(0.0)
    df["ticker"] = df.get("ticker").astype(str).str.upper()
    df["side"] = df.get("side").astype(str)
    df["strike"] = pd.to_numeric(df.get("strike"), errors="coerce")
    df["expiry"] = df.get("expiry")
    df["net_contracts_delta"] = df["contracts"].where(~df["action"].str.contains("close", na=False), -df["contracts"])

    group_cols = ["ticker", "side", "strike", "expiry"]
    if "base_leg_id" in df.columns:
        df["base_leg_id"] = df.get("base_leg_id").astype(str)
        group_cols = ["base_leg_id"] + group_cols

    grouped = (
        df.groupby(group_cols, dropna=False)
        .agg(net_contracts=("net_contracts_delta", "sum"))
        .reset_index()
    )
    open_groups = grouped[grouped["net_contracts"] > 0]
    if open_groups.empty:
        return 0.0

    if legs is None and base_position_id:
        legs = business_loader.list_base_legs(base_position_id)
    underlying_by_leg, fallback_underlying = _latest_underlying_by_leg(legs) if legs is not None else ({}, None)

    total = 0.0
    for _, row in open_groups.iterrows():
        base_leg_id = str(row.get("base_leg_id") or "").strip()
        underlying = underlying_by_leg.get(base_leg_id) or fallback_underlying
        if underlying is None:
            continue
        strike = _to_float_or_none(row.get("strike"))
        if strike is None:
            continue
        side = str(row.get("side") or "").lower()
        is_put = "put" in side
        intrinsic_per = max(0.0, strike - underlying) if is_put else max(0.0, underlying - strike)
        if intrinsic_per <= 0:
            continue

        # Skip long opens (debits) when possible.
        if "premium_buyback" in df.columns:
            match = df
            for col in group_cols:
                match = match[match[col] == row.get(col)]
            opens = match[match["action"].str.contains("open", na=False)]
            premium = pd.to_numeric(opens.get("premium_buyback"), errors="coerce").dropna()
            if not premium.empty and premium.mean() < 0:
                continue

        contracts = _to_float_or_none(row.get("net_contracts"))
        if contracts is None or contracts <= 0:
            continue
        total -= float(intrinsic_per) * float(contracts) * CONTRACT_MULTIPLIER

    return float(round(total, 2))


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


def _latest_underlying_by_leg(legs: pd.DataFrame) -> Tuple[Dict[str, float], Optional[float]]:
    """Return underlying by base_leg_id from MARK rows plus a fallback latest underlying."""
    if legs.empty or "underlying_price" not in legs.columns:
        return {}, None
    marks = legs[legs["tag"].astype(str).str.upper() == "MARK"].copy()
    if marks.empty:
        return {}, None
    # Normalize dates for stable ordering if multiple marks exist.
    if "date" in marks.columns:
        marks["date"] = pd.to_datetime(marks.get("date"), errors="coerce")
    if "time" in marks.columns:
        marks["time"] = marks.get("time").astype(str)
    marks = marks.dropna(subset=["underlying_price"])
    if marks.empty:
        return {}, None
    # Prefer most recent mark per base_leg_id.
    marks = marks.sort_values(["date", "time"], na_position="last")
    latest_by_leg: Dict[str, float] = {}
    for _, row in marks.iterrows():
        leg_id = str(row.get("base_leg_id") or "").strip()
        if not leg_id:
            continue
        underlying = _to_float_or_none(row.get("underlying_price"))
        if underlying is None:
            continue
        latest_by_leg[leg_id] = float(underlying)
    fallback = None
    if not marks.empty:
        fallback = _to_float_or_none(marks.iloc[-1].get("underlying_price"))
    return latest_by_leg, float(fallback) if fallback is not None else None


def _open_base_leg_ids(legs: pd.DataFrame) -> List[str]:
    """Return base_leg_ids for legs that remain open and have a MARK."""
    if legs.empty or not {"base_leg_id", "side", "quantity", "tag"}.issubset(legs.columns):
        return []
    net: Dict[str, float] = {}
    has_mark: Dict[str, bool] = {}
    for _, row in legs.iterrows():
        leg_id = str(row.get("base_leg_id") or "").strip()
        if not leg_id:
            continue
        tag = str(row.get("tag") or "").upper()
        if tag == "MARK":
            has_mark[leg_id] = True
            continue
        qty = pd.to_numeric(row.get("quantity"), errors="coerce")
        if pd.isna(qty):
            continue
        side = str(row.get("side") or "").upper()
        delta = qty if side == "BUY" else -qty
        net[leg_id] = net.get(leg_id, 0.0) + float(delta)
    return [lid for lid, qty in net.items() if qty > 0 and has_mark.get(lid)]


def _marked_base_leg_ids(legs: pd.DataFrame) -> List[str]:
    """Return base_leg_ids that have a MARK tag."""
    if legs.empty or not {"base_leg_id", "tag"}.issubset(legs.columns):
        return []
    marked = legs[legs["tag"].astype(str).str.upper() == "MARK"]
    if marked.empty:
        return []
    ids = marked["base_leg_id"].dropna().astype(str).str.strip()
    return [val for val in dict.fromkeys(ids.tolist()) if val]


def _filter_ledger_scope(
    df: pd.DataFrame,
    base_leg_ids: Optional[List[str]] = None,
    base_position_ids: Optional[List[str]] = None,
    ticker: Optional[str] = None,
) -> pd.DataFrame:
    """Filter ledger rows to the provided base leg ids only."""
    if df.empty:
        return df
    if base_leg_ids and "base_leg_id" in df.columns:
        ids = {str(val).strip().lower() for val in base_leg_ids if val}
        if ids:
            scoped = df[df["base_leg_id"].astype(str).str.strip().str.lower().isin(ids)]
            if not scoped.empty:
                return scoped
    if base_position_ids and "base_position_id" in df.columns:
        ids = {str(val).strip() for val in base_position_ids if val}
        if ids:
            scoped = df[df["base_position_id"].astype(str).str.strip().isin(ids)]
            if not scoped.empty:
                return scoped
    if ticker and "ticker" in df.columns:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
        scoped = df[df["ticker"] == ticker.upper()]
        if not scoped.empty:
            return scoped
    return df.iloc[0:0]


def _net_juice_for_base_legs(
    account: Optional[str],
    base_leg_ids: Optional[List[str]],
    base_position_ids: Optional[List[str]] = None,
    ticker: Optional[str] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Net short juice for closed shorts (open+close pairs) using base leg ids only."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    if not base_leg_ids:
        return 0.0
    df = _filter_ledger_scope(df, base_leg_ids)
    if df.empty:
        return 0.0
    df = _ensure_signed_juice(df)
    df = _apply_expiry_filter(df, expiry_start, expiry_end)
    df = df.dropna(subset=["signed_juice_dollars"])
    if df.empty:
        return 0.0
    df = _prepare_ledger_group_fields(df)
    grouped = (
        df.groupby(["ticker", "side", "strike", "expiry"], dropna=False)
        .agg(net_contracts=("net_contracts_delta", "sum"))
        .reset_index()
    )
    closed_groups = grouped[grouped["net_contracts"] == 0]
    if closed_groups.empty:
        return 0.0
    df = df.merge(closed_groups, on=["ticker", "side", "strike", "expiry"], how="inner")
    return float(df["signed_juice_dollars"].sum())


def _net_protection_from_ledger(df: pd.DataFrame) -> float:
    """Net protection for closed shorts (open+close pairs)."""
    if df.empty:
        return 0.0
    df = df.copy()
    df = _ensure_signed_juice(df)
    df["premium_buyback"] = pd.to_numeric(df.get("premium_buyback"), errors="coerce")
    df = df.dropna(subset=["premium_buyback", "signed_juice_dollars"])
    if df.empty:
        return 0.0

    def protection_delta(row: pd.Series) -> float:
        premium_total = float(row["premium_buyback"]) * float(row["contracts"]) * CONTRACT_MULTIPLIER
        protection = premium_total - abs(float(row["signed_juice_dollars"]))
        if "close" in str(row["action"]):
            return -abs(protection)
        return abs(protection)

    df = _prepare_ledger_group_fields(df)
    grouped = (
        df.groupby(["ticker", "side", "strike", "expiry"], dropna=False)
        .agg(net_contracts=("net_contracts_delta", "sum"))
        .reset_index()
    )
    closed_groups = grouped[grouped["net_contracts"] == 0]
    if closed_groups.empty:
        return 0.0
    df = df.merge(closed_groups, on=["ticker", "side", "strike", "expiry"], how="inner")
    df["protection_delta"] = df.apply(protection_delta, axis=1)
    return float(df["protection_delta"].sum())


def _net_protection_for_base_legs(
    account: Optional[str],
    base_leg_ids: Optional[List[str]],
    base_position_ids: Optional[List[str]] = None,
    ticker: Optional[str] = None,
    expiry_start: Optional[pd.Timestamp] = None,
    expiry_end: Optional[pd.Timestamp] = None,
) -> float:
    """Sum net protection for base leg ids (realized only)."""
    rows = excel_loader.get_ledger_rows(account)
    df = pd.DataFrame(rows)
    if df.empty:
        return 0.0
    df = _filter_ledger_scope(df, base_leg_ids, base_position_ids, ticker)
    if df.empty:
        return 0.0
    df = _apply_expiry_filter(df, expiry_start, expiry_end)
    return _net_protection_from_ledger(df)


def _short_extrinsic_net_for_position(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    base_leg_ids: Optional[List[str]] = None,
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
    if base_leg_ids is not None:
        if not base_leg_ids:
            return 0.0
        if "base_leg_id" in df.columns:
            ids = {str(val) for val in base_leg_ids if val}
            if not ids:
                return 0.0
            df["base_leg_id"] = df.get("base_leg_id").astype(str)
            df = df[df["base_leg_id"].isin(ids)]
        else:
            return 0.0
    elif base_position_id:
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


def _normalize_ledger_df(rows: List[Dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "action" in df.columns:
        df["action"] = df.get("action").astype(str).str.upper()
    else:
        df["action"] = ""
    if "side" in df.columns:
        df["side"] = df.get("side").astype(str).str.upper()
    else:
        df["side"] = ""
    if "ticker" in df.columns:
        df["ticker"] = df.get("ticker").astype(str).str.upper()
    else:
        df["ticker"] = ""
    df["contracts"] = pd.to_numeric(df.get("contracts"), errors="coerce")
    df["strike"] = pd.to_numeric(df.get("strike"), errors="coerce")
    df["premium_buyback"] = pd.to_numeric(df.get("premium_buyback"), errors="coerce")
    df["underlying"] = pd.to_numeric(df.get("underlying"), errors="coerce")
    df["expiry"] = pd.to_datetime(df.get("expiry"), errors="coerce")
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
    df["row_number"] = pd.to_numeric(df.get("row_number"), errors="coerce")
    if "condition" in df.columns:
        df["condition_norm"] = df.get("condition").apply(_normalize_condition)
    else:
        df["condition_norm"] = ""
    if "base_position_id" in df.columns:
        df["base_position_id"] = df.get("base_position_id").astype(str)
    else:
        df["base_position_id"] = ""
    if "base_leg_id" in df.columns:
        df["base_leg_id"] = df.get("base_leg_id").astype(str)
    else:
        df["base_leg_id"] = ""
    if "key" in df.columns:
        df["key"] = df.get("key").fillna("").astype(str)
    else:
        df["key"] = ""
    df["order"] = df["row_number"]
    missing = df["order"].isna()
    if missing.any():
        date_order = pd.to_datetime(df.loc[missing, "date"], errors="coerce").view("int64")
        df.loc[missing, "order"] = date_order
    return df


def _normalize_short_key(raw_key: str) -> str:
    if not raw_key:
        return ""
    parts = [part.strip().upper() for part in raw_key.split("|") if part.strip()]
    while parts and parts[-1] in {"OPEN", "CLOSE", "MARK"}:
        parts.pop()
    return "|".join(parts)


def _short_pair_key(row: pd.Series) -> str:
    ticker = str(row.get("ticker") or "").upper()
    side = str(row.get("side") or "").upper()
    strike = row.get("strike")
    strike_str = f"{float(strike):.4f}" if strike is not None and pd.notna(strike) else ""
    expiry = row.get("expiry")
    expiry_str = ""
    if isinstance(expiry, pd.Timestamp) and not pd.isna(expiry):
        expiry_str = expiry.date().isoformat()
    base_leg_id = str(row.get("base_leg_id") or "").strip()
    base_position_id = str(row.get("base_position_id") or "").strip()
    raw_key = _normalize_short_key(str(row.get("key") or "").strip())
    anchor = base_leg_id or base_position_id
    if raw_key:
        return f"{raw_key}|{anchor}"
    return f"{ticker}|{side}|{strike_str}|{expiry_str}|{anchor}"


def _filter_ledger_as_of(df: pd.DataFrame, as_of: Optional[pd.Timestamp]) -> pd.DataFrame:
    if df.empty or as_of is None:
        return df
    cutoff = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(cutoff):
        return df
    if "date" not in df.columns:
        return df
    mask = df["date"].isna() | (df["date"] <= cutoff)
    return df[mask]


def _short_instances_for_position(
    df: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    if df.empty:
        return [], []
    working = df.copy()
    working = _filter_ledger_as_of(working, as_of)
    working = working[working["action"].isin({"OPEN", "CLOSE", "MARK"})]
    working["side"] = working.get("side").astype(str).str.upper()
    working = working[working["side"].isin({"CALL", "PUT"})]
    if working.empty:
        return [], []
    working["pair_key"] = working.apply(_short_pair_key, axis=1)
    working = working.sort_values(["order", "row_number"], na_position="last")

    open_instances: List[Dict[str, object]] = []
    closed_instances: List[Dict[str, object]] = []

    for key, group in working.groupby("pair_key", dropna=False):
        opens = group[group["action"] == "OPEN"].sort_values(["order", "row_number"], na_position="last")
        closes = group[group["action"] == "CLOSE"].sort_values(["order", "row_number"], na_position="last")
        marks = group[group["action"] == "MARK"].sort_values(["order", "row_number"], na_position="last")
        closed_open_ids: set[object] = set()
        close_idx = 0
        for _, open_row in opens.iterrows():
            open_order = open_row.get("order")
            while close_idx < len(closes) and (
                _to_float_or_none(closes.iloc[close_idx].get("order")) is not None
                and _to_float_or_none(open_order) is not None
                and closes.iloc[close_idx].get("order") <= open_order
            ):
                close_idx += 1
            if close_idx < len(closes):
                close_row = closes.iloc[close_idx]
                close_idx += 1
                closed_instances.append(
                    {
                        "pair_key": key,
                        "open": open_row.to_dict(),
                        "close": close_row.to_dict(),
                    }
                )
                closed_open_ids.add(open_row.name)
                continue
        used_open_ids: set[object] = set()
        if not marks.empty:
            for _, mark_row in marks.iterrows():
                mark_order = mark_row.get("order")
                open_row = None
                if not opens.empty:
                    candidates = opens
                    if mark_order is not None and pd.notna(mark_order):
                        candidates = opens[opens["order"] <= mark_order]
                        if candidates.empty:
                            candidates = opens
                    open_row = candidates.iloc[-1]
                    used_open_ids.add(open_row.name)
                open_instances.append(
                    {
                        "pair_key": key,
                        "open": open_row.to_dict() if open_row is not None else None,
                        "mark": mark_row.to_dict(),
                    }
                )
        for _, open_row in opens.iterrows():
            open_id = open_row.name
            if open_id in closed_open_ids or open_id in used_open_ids:
                continue
            open_instances.append(
                {
                    "pair_key": key,
                    "open": open_row.to_dict(),
                    "mark": None,
                }
            )
    return open_instances, closed_instances


def _instance_contracts(instance: Dict[str, object]) -> Optional[float]:
    for key in ("close", "mark", "open"):
        row = instance.get(key)
        if isinstance(row, dict):
            contracts = _to_float_or_none(row.get("contracts"))
            if contracts is not None:
                return contracts
    return None


def _intrinsic_per_contract(underlying: Optional[float], strike: Optional[float], side: str) -> Optional[float]:
    if underlying is None or strike is None:
        return None
    if "PUT" in side.upper():
        return max(0.0, float(strike) - float(underlying))
    return max(0.0, float(underlying) - float(strike))


def _defense_debits_for_position(
    df: pd.DataFrame,
    closed_instances: List[Dict[str, object]],
    max_gap: int = 5,
    week_bounds: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> Tuple[List[float], Optional[float], Optional[float], float]:
    if df.empty:
        return [], None, None, 0.0
    closes = df[df["action"] == "CLOSE"].sort_values(["order", "row_number"], na_position="last")
    opens = df[df["action"] == "OPEN"].sort_values(["order", "row_number"], na_position="last")
    if closes.empty:
        return [], None, None, 0.0

    open_by_close: Dict[object, Dict[str, object]] = {}
    open_by_key: Dict[str, Dict[str, object]] = {}
    for inst in closed_instances:
        close_row = inst.get("close")
        open_row = inst.get("open")
        if isinstance(close_row, dict) and isinstance(open_row, dict):
            key = close_row.get("row_number") or close_row.get("order")
            open_by_close[key] = open_row
            key_val = str(close_row.get("key") or "").strip()
            if key_val:
                open_by_key[key_val] = open_row

    events: List[Tuple[float, float]] = []
    weekly_total = 0.0
    week_start, week_end = week_bounds or _current_week_window()

    for _, close_row in closes.iterrows():
        key_val = str(close_row.get("key") or "").strip()
        close_order = close_row.get("order")
        close_row_number = close_row.get("row_number")
        close_premium = _to_float_or_none(close_row.get("premium_buyback"))
        close_contracts = _to_float_or_none(close_row.get("contracts"))
        if close_premium is None or close_contracts in (None, 0):
            continue

        cond = _normalize_condition(close_row.get("condition_norm") or close_row.get("condition") or "")
        has_condition = bool(cond)
        is_defense_tag = "DEFENSE" in cond
        is_income_tag = "INCOME" in cond

        roll_open = None
        if not opens.empty:
            subset = opens
            if "base_position_id" in opens.columns:
                subset = subset[opens["base_position_id"] == close_row.get("base_position_id")]
            if "account" in opens.columns:
                subset = subset[opens["account"] == close_row.get("account")]
            subset = subset[subset["ticker"] == close_row.get("ticker")]
            subset = subset[subset["side"] == "CALL"]
            if close_row_number is not None and pd.notna(close_row_number):
                subset = subset[subset["row_number"] > close_row_number]
            elif close_order is not None and pd.notna(close_order):
                subset = subset[subset["order"] > close_order]
            if not subset.empty:
                candidate = subset.iloc[0]
                gap = None
                if close_row_number is not None and pd.notna(close_row_number):
                    gap = candidate.get("row_number") - close_row_number
                close_date = close_row.get("date")
                open_date = candidate.get("date")
                date_ok = True
                if pd.notna(close_date) and pd.notna(open_date):
                    date_ok = (open_date.date() == close_date.date()) or ((open_date - close_date).days <= 1)
                if (gap is None or gap <= max_gap) and date_ok:
                    roll_open = candidate.to_dict()

        debit_total = None
        if roll_open:
            open_credit = _to_float_or_none(roll_open.get("premium_buyback"))
            if open_credit is not None:
                debit_total = max(0.0, (close_premium - open_credit) * close_contracts * CONTRACT_MULTIPLIER)
        else:
            open_row = None
            key_val = str(close_row.get("key") or "").strip()
            if key_val:
                open_row = open_by_key.get(key_val)
            if open_row is None:
                open_row = open_by_close.get(close_row_number or close_order)
            if open_row:
                open_credit = _to_float_or_none(open_row.get("premium_buyback"))
                if open_credit is not None:
                    debit_total = max(0.0, (close_premium - open_credit) * close_contracts * CONTRACT_MULTIPLIER)

        if debit_total is None:
            continue

        realized_pnl = None
        open_row = None
        if key_val:
            open_row = open_by_key.get(key_val)
        if open_row is None:
            open_row = open_by_close.get(close_row_number or close_order)
        if open_row:
            open_credit = _to_float_or_none(open_row.get("premium_buyback"))
            if open_credit is not None:
                realized_pnl = (open_credit - close_premium) * close_contracts * CONTRACT_MULTIPLIER

        is_defense = False
        if has_condition:
            if is_income_tag:
                is_defense = False
            else:
                is_defense = is_defense_tag
        else:
            if roll_open and debit_total > 0:
                is_defense = True
            elif realized_pnl is not None and realized_pnl < 0:
                is_defense = True

        if is_defense:
            per_contract = debit_total / close_contracts if close_contracts else 0.0
            order_val = _to_float_or_none(close_order) or 0.0
            events.append((order_val, per_contract))
            close_date = pd.to_datetime(close_row.get("date"), errors="coerce")
            if pd.notna(close_date) and week_start <= close_date < week_end:
                weekly_total += debit_total

    if not events:
        return [], None, None, float(round(weekly_total, 2))

    events_sorted = sorted(events, key=lambda item: item[0])
    last10 = [item[1] for item in events_sorted[-10:]]
    avg_dd = float(np.mean(last10)) if last10 else None
    p90 = float(np.percentile(last10, 90)) if last10 else None
    if avg_dd is None:
        debit_cap = None
    else:
        debit_cap = max(avg_dd * 1.5, p90 or 0.0)
    return last10, avg_dd, debit_cap, float(round(weekly_total, 2))


def _latest_stock_closes(symbol: str) -> Tuple[Optional[float], Optional[float]]:
    df = business_loader.list_circuit_breakers(symbol)
    if df.empty or "date" not in df.columns:
        return None, None
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        return None, None
    close_today = _to_float_or_none(df.iloc[-1].get("stock_close"))
    close_yesterday = None
    if len(df) > 1:
        close_yesterday = _to_float_or_none(df.iloc[-2].get("stock_close"))
    return close_today, close_yesterday


def _short_position_snapshot(
    df: pd.DataFrame,
    as_of: Optional[pd.Timestamp] = None,
    week_bounds: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
    defense_df: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    open_instances, closed_instances = _short_instances_for_position(df, as_of=as_of)
    week_start, week_end = week_bounds or _current_week_window()
    realized_total = 0.0
    unrealized_total = 0.0
    working_juice = 0.0
    locked_juice = 0.0
    weekly_locked = 0.0
    open_short_contracts = 0.0
    capture_pcts: List[float] = []

    for inst in closed_instances:
        open_row = inst.get("open") if isinstance(inst.get("open"), dict) else None
        close_row = inst.get("close") if isinstance(inst.get("close"), dict) else None
        if not open_row or not close_row:
            continue
        credit_open = _to_float_or_none(open_row.get("premium_buyback"))
        debit_close = _to_float_or_none(close_row.get("premium_buyback"))
        contracts = _instance_contracts(inst)
        if credit_open is None or debit_close is None or not contracts:
            continue
        if credit_open < 0:
            continue
        pnl = (credit_open - debit_close) * contracts * CONTRACT_MULTIPLIER
        realized_total += pnl
        close_date = pd.to_datetime(close_row.get("date"), errors="coerce")
        if pd.notna(close_date) and week_start <= close_date < week_end:
            weekly_locked += pnl

        side = str(open_row.get("side") or "").upper()
        strike = _to_float_or_none(open_row.get("strike"))
        underlying_open = _to_float_or_none(open_row.get("underlying"))
        underlying_close = _to_float_or_none(close_row.get("underlying"))
        intrinsic_open = _intrinsic_per_contract(underlying_open, strike, side)
        intrinsic_close = _intrinsic_per_contract(underlying_close, strike, side)
        if intrinsic_open is None or intrinsic_close is None:
            continue
        extrinsic_open = credit_open - intrinsic_open
        extrinsic_close = debit_close - intrinsic_close
        locked_juice += (extrinsic_open - extrinsic_close) * contracts * CONTRACT_MULTIPLIER

    for inst in open_instances:
        open_row = inst.get("open") if isinstance(inst.get("open"), dict) else None
        mark_row = inst.get("mark") if isinstance(inst.get("mark"), dict) else None
        if not mark_row:
            continue
        contracts = _to_float_or_none(mark_row.get("contracts")) or _instance_contracts(inst)
        if contracts:
            open_short_contracts += contracts
        credit_open = _to_float_or_none(open_row.get("premium_buyback")) if open_row else None
        if credit_open is None or not contracts:
            continue
        if credit_open < 0:
            continue
        mark_premium = _to_float_or_none(mark_row.get("premium_buyback")) if mark_row else credit_open
        if mark_premium is None:
            continue
        pnl = (credit_open - mark_premium) * contracts * CONTRACT_MULTIPLIER
        unrealized_total += pnl

        side = str((open_row or mark_row).get("side") or "").upper()
        strike = _to_float_or_none((open_row or mark_row).get("strike"))
        underlying_open = _to_float_or_none(open_row.get("underlying")) if open_row else None
        underlying_mark = _to_float_or_none(mark_row.get("underlying")) if mark_row else None
        intrinsic_open = _intrinsic_per_contract(underlying_open, strike, side)
        intrinsic_now = _intrinsic_per_contract(underlying_mark, strike, side) if underlying_mark is not None else None
        if intrinsic_open is None or intrinsic_now is None:
            continue
        extrinsic_open = credit_open - intrinsic_open
        extrinsic_now = mark_premium - intrinsic_now
        working_juice += (extrinsic_open - extrinsic_now) * contracts * CONTRACT_MULTIPLIER
        if extrinsic_open:
            capture_pcts.append((extrinsic_open - extrinsic_now) / extrinsic_open)

    defense_scope = defense_df if defense_df is not None else df
    last10, avg_dd, debit_cap, weekly_defense = _defense_debits_for_position(
        defense_scope,
        closed_instances,
        week_bounds=week_bounds,
    )
    safety_reserve = (debit_cap or 0.0) * open_short_contracts if open_short_contracts else 0.0
    avg_capture_pct = float(np.mean(capture_pcts)) if capture_pcts else None

    return {
        "open_instances": open_instances,
        "closed_instances": closed_instances,
        "short_realized_pnl": float(round(realized_total, 2)),
        "short_unrealized_pnl": float(round(unrealized_total, 2)),
        "working_juice": float(round(working_juice, 2)),
        "locked_juice": float(round(locked_juice, 2)),
        "weekly_locked_income": float(round(weekly_locked, 2)),
        "weekly_defense_debit": float(round(weekly_defense, 2)),
        "open_short_contracts": float(round(open_short_contracts, 2)) if open_short_contracts else 0.0,
        "last10_defense_debits": [float(round(val, 4)) for val in last10],
        "avg_defense_debit": _clean_number(avg_dd),
        "debit_cap": _clean_number(debit_cap),
        "safety_reserve": float(round(safety_reserve, 2)) if safety_reserve else 0.0,
        "avg_capture_pct": _clean_number(avg_capture_pct),
    }


def _base_leg_ids_from_legs(legs: pd.DataFrame) -> List[str]:
    if legs.empty or "base_leg_id" not in legs.columns:
        return []
    ids = legs["base_leg_id"].astype(str).str.strip()
    return [val for val in ids.tolist() if val]


def _open_base_leg_ids_from_ledger(df: pd.DataFrame) -> List[str]:
    if df.empty or "base_leg_id" not in df.columns:
        return []
    marks = df[df["action"] == "MARK"]
    if marks.empty:
        return []
    ids = marks["base_leg_id"].astype(str).str.strip()
    return [val for val in ids.tolist() if val]


def _base_open_cost_from_ledger(df: pd.DataFrame, base_leg_ids: List[str]) -> Optional[float]:
    if df.empty or not base_leg_ids:
        return None
    subset = df[(df["action"] == "OPEN") & (df["base_leg_id"].isin(base_leg_ids))]
    if "key" in subset.columns:
        subset = subset[subset["key"].astype(str).str.strip() == ""]
    if subset.empty:
        return None
    subset = subset.dropna(subset=["premium_buyback", "contracts"])
    if subset.empty:
        return None
    cost = (subset["premium_buyback"].abs() * subset["contracts"] * CONTRACT_MULTIPLIER).sum()
    return float(cost) if pd.notna(cost) else None


def _base_mark_value_from_ledger(
    df: pd.DataFrame,
    base_leg_ids: List[str],
    as_of: Optional[pd.Timestamp] = None,
) -> Optional[float]:
    if df.empty or not base_leg_ids:
        return None
    subset = df[(df["action"] == "MARK") & (df["base_leg_id"].isin(base_leg_ids))]
    if "key" in subset.columns:
        subset = subset[subset["key"].astype(str).str.strip() == ""]
    subset = _filter_ledger_as_of(subset, as_of)
    if subset.empty:
        return None
    subset = subset.dropna(subset=["premium_buyback", "contracts"])
    if subset.empty:
        return None
    if "row_number" in subset.columns and subset["row_number"].notna().any():
        subset = subset.sort_values("row_number")
    elif "date" in subset.columns:
        subset = subset.sort_values("date")
    latest = subset.groupby("base_leg_id", dropna=False).tail(1)
    value = (latest["premium_buyback"].abs() * latest["contracts"] * CONTRACT_MULTIPLIER).sum()
    return float(value) if pd.notna(value) else None


def _position_layer_snapshot(
    ledger_df: pd.DataFrame,
    base_leg_ids: List[str],
    principal_cost: Optional[float],
    long_value_fallback: Optional[float],
    as_of: Optional[pd.Timestamp] = None,
    week_bounds: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> Dict[str, object]:
    short_snapshot = _short_position_snapshot(ledger_df, as_of=as_of, week_bounds=week_bounds)
    principal = principal_cost if principal_cost is not None else _base_open_cost_from_ledger(ledger_df, base_leg_ids)
    if long_value_fallback is not None:
        long_value = long_value_fallback
    else:
        long_value = _base_mark_value_from_ledger(ledger_df, base_leg_ids, as_of=as_of)
    short_realized = float(short_snapshot.get("short_realized_pnl") or 0.0)
    short_unrealized = float(short_snapshot.get("short_unrealized_pnl") or 0.0)
    # Liquidation = long MTM + realized short + unrealized short.
    liquidation_value = (long_value or 0.0) + short_realized + short_unrealized
    cushion = liquidation_value - (principal or 0.0)
    safety_reserve = float(short_snapshot.get("safety_reserve") or 0.0)
    withdrawable_now = max(0.0, cushion - safety_reserve)
    protected_now = None if not principal else (liquidation_value >= principal)
    return {
        "principal_cost": principal,
        "long_value_now": long_value,
        "short_snapshot": short_snapshot,
        "short_realized_pnl": short_realized,
        "short_unrealized_pnl": short_unrealized,
        "liquidation_value": liquidation_value,
        "cushion": cushion,
        "safety_reserve": safety_reserve,
        "withdrawable_now": withdrawable_now,
        "protected_now": protected_now,
    }


def _maturity_flags_for_position(
    ledger_df: pd.DataFrame,
    base_leg_ids: List[str],
    principal_cost: Optional[float],
    long_value_fallback: Optional[float],
    weeks: int = 6,
) -> List[bool]:
    anchor = pd.Timestamp.now().normalize()
    flags: List[bool] = []
    for offset in range(weeks):
        week_anchor = anchor - pd.Timedelta(days=7 * offset)
        week_start, week_end = _week_bounds(week_anchor)
        as_of = week_end - pd.Timedelta(seconds=1)
        snapshot = _position_layer_snapshot(
            ledger_df,
            base_leg_ids,
            principal_cost,
            long_value_fallback,
            as_of=as_of,
            week_bounds=(week_start, week_end),
        )
        cushion = snapshot.get("cushion") or 0.0
        safety = snapshot.get("safety_reserve") or 0.0
        flags.append(cushion >= (2.0 * safety))
    return flags


def _account_maturity_flags(
    position_inputs: List[Dict[str, object]],
    weeks: int = 6,
) -> List[bool]:
    if not position_inputs:
        return []
    anchor = pd.Timestamp.now().normalize()
    flags: List[bool] = []
    for offset in range(weeks):
        week_anchor = anchor - pd.Timedelta(days=7 * offset)
        week_start, week_end = _week_bounds(week_anchor)
        as_of = week_end - pd.Timedelta(seconds=1)
        account_cushion = 0.0
        account_safety = 0.0
        for info in position_inputs:
            snapshot = _position_layer_snapshot(
                info["ledger_df"],
                info["base_leg_ids"],
                info["principal_cost"],
                info["long_value_fallback"],
                as_of=as_of,
                week_bounds=(week_start, week_end),
            )
            account_cushion += snapshot.get("cushion") or 0.0
            account_safety += snapshot.get("safety_reserve") or 0.0
        flags.append(account_cushion >= (2.0 * account_safety))
    return flags


def _short_signals_for_position(
    open_instances: List[Dict[str, object]],
    symbol: str,
    cushion: float,
    safety_reserve: float,
    plan_settings: Dict[str, float | int],
    regime_condition: str,
    breaker_status: str,
) -> Tuple[List[ShortLegSignal], bool, bool, bool, Optional[str], Optional[str], Optional[str]]:
    close_today, close_yesterday = _latest_stock_closes(symbol)
    emergency = safety_reserve > 0 and cushion < (0.5 * safety_reserve)
    signals: List[ShortLegSignal] = []
    income_roll = False
    protection_roll = False

    capture_target = float(plan_settings.get("capture_target_pct", 0.70))
    min_dte = int(plan_settings.get("min_dte_to_roll", 3))
    cheap_buyback = float(plan_settings.get("cheap_buyback_threshold", 0.30))

    primary_open = None
    primary_mark = None
    primary_expiry = None

    for inst in open_instances:
        open_row = inst.get("open") if isinstance(inst.get("open"), dict) else None
        mark_row = inst.get("mark") if isinstance(inst.get("mark"), dict) else None
        if not open_row:
            continue
        expiry = open_row.get("expiry")
        if isinstance(expiry, str):
            expiry = pd.to_datetime(expiry, errors="coerce")
        if primary_open is None:
            primary_open = open_row
            primary_mark = mark_row
            primary_expiry = expiry
        elif isinstance(expiry, pd.Timestamp) and isinstance(primary_expiry, pd.Timestamp):
            if expiry < primary_expiry:
                primary_open = open_row
                primary_mark = mark_row
                primary_expiry = expiry

        strike = _to_float_or_none(open_row.get("strike"))
        side = str(open_row.get("side") or "").upper()
        contracts = _to_float_or_none(open_row.get("contracts"))
        entry_credit = _to_float_or_none(open_row.get("premium_buyback"))
        current_buyback = _to_float_or_none(mark_row.get("premium_buyback")) if mark_row else None
        underlying_now = _to_float_or_none(mark_row.get("underlying")) if mark_row else _to_float_or_none(open_row.get("underlying"))
        intrinsic_open = _intrinsic_per_contract(_to_float_or_none(open_row.get("underlying")), strike, side)
        intrinsic_now = _intrinsic_per_contract(underlying_now, strike, side)
        extrinsic_now = None
        capture_pct = None
        if entry_credit is not None and intrinsic_open is not None:
            extrinsic_open = entry_credit - intrinsic_open
            if current_buyback is not None and entry_credit:
                capture_pct = (entry_credit - current_buyback) / entry_credit
            if current_buyback is not None and intrinsic_now is not None:
                extrinsic_now = current_buyback - intrinsic_now

        dte = None
        if isinstance(expiry, pd.Timestamp) and not pd.isna(expiry):
            dte = (expiry.normalize() - pd.Timestamp.now().normalize()).days

        near_atm = None
        if underlying_now is not None and strike is not None and underlying_now:
            near_atm = abs(float(underlying_now) - float(strike)) / float(underlying_now) <= 0.01

        roll_eligible = bool(
            capture_pct is not None
            and capture_pct >= capture_target
            and dte is not None
            and dte >= min_dte
        )
        income_flag = roll_eligible or (current_buyback is not None and current_buyback <= cheap_buyback)
        income_roll = income_roll or income_flag

        close_price = close_today if close_today is not None else None
        buffer_val = 0.01 * close_price if close_price is not None else None
        trigger = False
        confirm_down = False
        if buffer_val is not None and strike is not None and close_price is not None and close_yesterday is not None:
            trigger = close_price < (float(strike) - buffer_val)
            confirm_down = (close_price < (float(strike) - buffer_val)) and (close_yesterday < (float(strike) - buffer_val))
        protection_trigger = (cushion < safety_reserve) or trigger
        protection_flag = protection_trigger and (confirm_down or emergency or (close_today is None))
        protection_roll = protection_roll or protection_flag

        signals.append(
            ShortLegSignal(
                key=str(inst.get("pair_key") or ""),
                strike=_clean_number(strike),
                expiry=expiry.date() if isinstance(expiry, pd.Timestamp) and not pd.isna(expiry) else None,
                contracts=int(contracts) if contracts is not None else None,
                extrinsic_now=_clean_number(extrinsic_now),
                capture_pct=_clean_number(capture_pct),
                dte=dte,
                near_atm=near_atm,
                income_roll=income_flag,
                protection_roll=protection_flag,
                emergency=emergency,
            )
        )

    recommended = "HOLD"
    rule_triggered = "HOLD"
    explanation = "Hold current position."

    if breaker_status == "ExitNow":
        return signals, income_roll, protection_roll, emergency, "EXIT_NOW", "BREAKER_EXIT_NOW", "Circuit breaker signals exit now."
    if breaker_status == "ExitCandidate":
        return signals, income_roll, protection_roll, emergency, "EXIT_CANDIDATE", "BREAKER_EXIT_CANDIDATE", "Circuit breaker elevates exit readiness."

    primary_open = primary_open or (open_instances[0].get("open") if open_instances else None)
    primary_mark = primary_mark or (open_instances[0].get("mark") if open_instances else None)
    entry_credit = _to_float_or_none(primary_open.get("premium_buyback")) if isinstance(primary_open, dict) else None
    current_buyback = _to_float_or_none(primary_mark.get("premium_buyback")) if isinstance(primary_mark, dict) else None
    current_price = _to_float_or_none(primary_mark.get("underlying")) if isinstance(primary_mark, dict) else None
    if current_price is None:
        current_price = close_today

    roll_eligible = False
    capture_pct = None
    dte = None
    if isinstance(primary_expiry, pd.Timestamp) and not pd.isna(primary_expiry):
        dte = (primary_expiry.normalize() - pd.Timestamp.now().normalize()).days
    if entry_credit is not None and current_buyback is not None and entry_credit:
        capture_pct = (entry_credit - current_buyback) / entry_credit
        roll_eligible = capture_pct >= capture_target and (dte is not None and dte >= min_dte)

    if roll_eligible:
        pct = int(round(capture_pct * 100)) if capture_pct is not None else 0
        return signals, income_roll, protection_roll, emergency, "ROLL_EARLY", f"ROLL_EARLY_CAPTURE_{pct}", "Credit capture meets target and DTE gate."

    if regime_condition == "YELLOW":
        if current_price is None or not isinstance(primary_open, dict):
            return signals, income_roll, protection_roll, emergency, "UNKNOWN_PRICE", "UNKNOWN_PRICE", "No current price available to evaluate yellow band."
        strike = _to_float_or_none(primary_open.get("strike"))
        underlying_entry = _to_float_or_none(primary_open.get("underlying"))
        side = str(primary_open.get("side") or "").upper()
        if strike is None or underlying_entry is None or "CALL" not in side:
            return signals, income_roll, protection_roll, emergency, "UNKNOWN_PRICE", "UNKNOWN_PRICE", "Missing entry inputs for yellow band."
        intrinsic_entry = max(0.0, float(underlying_entry) - float(strike))
        e0 = (entry_credit or 0.0) - intrinsic_entry
        otm_floor = float(strike) - float(e0)
        if current_price < otm_floor:
            return signals, income_roll, protection_roll, emergency, "RECENTER_REQUIRED", "YELLOW_FLOOR_BREACH", "Price broke the yellow E0 floor; recenter required."
        return signals, income_roll, protection_roll, emergency, "HANG_BY_JUICE", "YELLOW_HANG_OK", "Price holds above yellow E0 floor; hang by juice."

    if regime_condition == "RED":
        return signals, income_roll, protection_roll, emergency, "RECOVER_BASE", "RED_ATM_FLOOR", "Red regime: prioritize base recovery and exit readiness."

    if regime_condition == "GREEN":
        return signals, income_roll, protection_roll, emergency, "ALLOW_OTM_DRIFT", "GREEN_ALLOW_DRIFT", "Green regime: allow OTM drift and manage normally."

    return signals, income_roll, protection_roll, emergency, recommended, rule_triggered, explanation


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


def _consistency(trades: pd.DataFrame, account: Optional[str], weeks: int = 13) -> Tuple[float, float]:
    """Compute average weekly net juice using expiry-week net juice from ledger rows.

    Net juice follows the Trades & Ledger logic: sum signed extrinsic by short pair,
    then include only fully paired positions (net contracts == 0). Filter to open
    base positions using base_leg_id first.
    """
    ledger_rows = excel_loader.get_ledger_rows(account)
    if not ledger_rows:
        return 0.0, 0.0

    open_leg_ids: set[str] = set()
    try:
        legs_df = business_loader.list_base_legs()
        if not legs_df.empty and "tag" in legs_df.columns:
            legs_df = legs_df[legs_df["tag"].astype(str).str.upper() == "MARK"]
        if not legs_df.empty and "base_leg_id" in legs_df.columns:
            open_leg_ids = set(legs_df["base_leg_id"].astype(str).str.strip())
    except Exception:
        open_leg_ids = set()

    def _pair_key(row: Dict[str, object]) -> str:
        ticker = str(row.get("ticker") or "").upper()
        side = str(row.get("side") or "").upper()
        strike = row.get("strike")
        try:
            strike_str = f"{float(strike):.4f}" if strike is not None else ""
        except Exception:
            strike_str = ""
        expiry = str(row.get("expiry") or "")
        base_leg_id = str(row.get("base_leg_id") or "").strip()
        return f"{ticker}|{side}|{strike_str}|{expiry}|{base_leg_id}"

    def _signed_juice_dict(row: Dict[str, object]) -> float | None:
        premium = row.get("premium_buyback")
        contracts = row.get("contracts")
        if premium is None or contracts is None:
            return None
        try:
            premium = float(premium)
            contracts = float(contracts)
        except Exception:
            return None
        strike = row.get("strike")
        underlying = row.get("underlying")
        side = str(row.get("side") or "").lower()
        action = str(row.get("action") or "").lower()
        is_put = "put" in side
        is_close = "close" in action
        try:
            strike_f = float(strike) if strike is not None else None
        except Exception:
            strike_f = None
        try:
            underlying_f = float(underlying) if underlying is not None else None
        except Exception:
            underlying_f = None
        if strike_f is not None and underlying_f is not None:
            intrinsic = max(0, strike_f - underlying_f) if is_put else max(0, underlying_f - strike_f)
            extrinsic = premium - intrinsic
            if is_close:
                juice_per_contract = abs(extrinsic) if extrinsic < 0 else -extrinsic
            else:
                juice_per_contract = extrinsic
        else:
            if is_close:
                juice_per_contract = abs(premium) if premium < 0 else -premium
            else:
                juice_per_contract = premium
        return round(float(juice_per_contract * contracts * CONTRACT_MULTIPLIER), 2)

    # Filter ledger rows for open base legs and usable data.
    filtered: list[Dict[str, object]] = []
    for row in ledger_rows:
        if "MARK" in str(row.get("action") or "").upper():
            continue
        base_leg_id = str(row.get("base_leg_id") or "").strip()
        if open_leg_ids and base_leg_id not in open_leg_ids:
            continue
        if not row.get("expiry") or not row.get("contracts"):
            continue
        filtered.append(row)
    if not filtered:
        return 0.0, 0.0

    # Group by short pair key.
    pairs: dict[str, list[Dict[str, object]]] = {}
    for row in filtered:
        key = _pair_key(row)
        pairs.setdefault(key, []).append(row)

    # Weekly totals (expiry week), only fully paired positions.
    weekly: dict[str, float] = {}
    for rows in pairs.values():
        net_contracts = 0.0
        for row in rows:
            try:
                contracts = float(row.get("contracts") or 0)
            except Exception:
                contracts = 0.0
            action = str(row.get("action") or "").lower()
            net_contracts += -contracts if "close" in action else contracts
        if abs(net_contracts) > 1e-6:
            continue
        expiry = str(rows[0].get("expiry") or "")
        try:
            exp_dt = datetime.fromisoformat(expiry)
        except Exception:
            continue
        week_start = exp_dt - timedelta(days=exp_dt.weekday())
        net_juice = sum((_signed_juice_dict(row) or 0.0) for row in rows)
        week_key = week_start.date().isoformat()
        weekly[week_key] = weekly.get(week_key, 0.0) + net_juice

    if not weekly:
        return 0.0, 0.0
    sorted_weeks = sorted(weekly.items())
    recent = sorted_weeks[-weeks:]
    avg_weekly = sum(v for _, v in recent) / len(recent)
    profitable_pct = (sum(1 for _, v in recent if v > 0) / len(recent)) * 100.0
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


def _base_entry_cost_from_legs(legs: pd.DataFrame) -> float:
    """Sum entry debit for OPEN base legs (C0)."""
    if legs.empty:
        return 0.0
    legs = legs.copy()
    legs["tag"] = legs.get("tag").astype(str).str.upper()
    legs["side"] = legs.get("side").astype(str).str.upper()
    legs["quantity"] = pd.to_numeric(legs.get("quantity"), errors="coerce")
    legs["price"] = pd.to_numeric(legs.get("price"), errors="coerce")
    legs["amount"] = pd.to_numeric(legs.get("amount"), errors="coerce")
    legs["fees"] = pd.to_numeric(legs.get("fees"), errors="coerce").fillna(0.0)

    opens = legs[legs["tag"] == "OPEN"]
    if opens.empty:
        return 0.0

    total = 0.0
    for _, row in opens.iterrows():
        if row.get("side") != "BUY":
            continue
        amt = row.get("amount")
        if amt is not None and pd.notna(amt):
            total += abs(float(amt))
        else:
            qty = row.get("quantity")
            price = row.get("price")
            instr = str(row.get("instrument_type") or "").upper()
            mult = 100.0 if instr == "OPTION" else 1.0
            if pd.isna(qty) or pd.isna(price):
                continue
            total += abs(float(qty) * float(price) * mult)
        fees = row.get("fees") or 0.0
        total += abs(float(fees))

    return float(round(total, 2))


def _initial_investment_from_marked_legs(legs: pd.DataFrame) -> Optional[float]:
    """Sum OPEN amounts for base_leg_ids that have a MARK tag."""
    if legs.empty or "base_leg_id" not in legs.columns or "tag" not in legs.columns:
        return None
    marks = legs[legs["tag"].astype(str).str.upper() == "MARK"]
    if marks.empty:
        return None
    marked_ids = marks["base_leg_id"].dropna().astype(str).str.strip().unique().tolist()
    if not marked_ids:
        return None
    opens = legs[
        (legs["tag"].astype(str).str.upper() == "OPEN")
        & (legs["base_leg_id"].astype(str).str.strip().isin(marked_ids))
    ].copy()
    if opens.empty:
        return None
    opens["amount"] = pd.to_numeric(opens.get("amount"), errors="coerce")
    total = opens["amount"].abs().sum()
    return float(round(total, 2)) if pd.notna(total) else None


def _base_mark_value_from_legs(legs: pd.DataFrame, base_leg_ids: List[str]) -> Optional[float]:
    if legs.empty or not base_leg_ids:
        return None
    marks = legs[
        (legs["tag"].astype(str).str.upper() == "MARK")
        & (legs["base_leg_id"].astype(str).str.strip().isin(base_leg_ids))
    ].copy()
    if marks.empty:
        return None
    marks["amount"] = pd.to_numeric(marks.get("amount"), errors="coerce")
    total = marks["amount"].abs().sum()
    return float(round(total, 2)) if pd.notna(total) else None


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
    regimes_df = business_loader.list_regimes()
    breaker_inputs = business_loader.list_circuit_breakers()
    ledger_df = _normalize_ledger_df(excel_loader.get_ledger_rows(account))
    snapshot_date = pd.Timestamp.now().normalize().date()
    results: List[PositionMetrics] = []
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)

    for _, pos in positions_df.iterrows():
        # Skip closed bases unless explicitly requested
        if (not include_closed) and (not pd.isna(pos.get("closed_date"))):
            continue
        pid = pos["position_id"]
        legs = business_loader.list_base_legs(pid)
        open_leg_ids = _open_base_leg_ids(legs)
        if not open_leg_ids:
            open_leg_ids = _marked_base_leg_ids(legs)
        open_legs = legs
        has_leg_ids = "base_leg_id" in legs.columns and legs["base_leg_id"].astype(str).str.strip().ne("").any()
        if has_leg_ids:
            if open_leg_ids:
                open_legs = legs[legs["base_leg_id"].astype(str).isin(open_leg_ids)]
            else:
                open_legs = legs.iloc[0:0]
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
            base_position_id=str(pid),
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        opened = pd.to_datetime(pos.get("opened_date"), errors="coerce")
        closed = pd.to_datetime(pos.get("closed_date"), errors="coerce")
        initial_intrinsic, initial_extrinsic = _initial_base_intrinsic_extrinsic_from_legs(
            open_legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        current_base_intrinsic = _current_base_intrinsic_from_legs(
            open_legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        base_leg_scope = open_leg_ids
        intrinsic_realized = _short_intrinsic_realized_for_position(
            account,
            pos["symbol"],
            base_position_id=pid,
            base_leg_ids=base_leg_scope,
            opened_date=opened if not pd.isna(opened) else None,
            closed_date=closed if not pd.isna(closed) else None,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        intrinsic_unrealized = _short_intrinsic_unrealized_for_position(
            account,
            pos["symbol"],
            base_position_id=pid,
            base_leg_ids=base_leg_scope,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
            legs=legs,
        )
        intrinsic_protection = intrinsic_realized + intrinsic_unrealized
        short_extrinsic_net = _short_extrinsic_net_for_position(
            account,
            pos["symbol"],
            base_position_id=pid,
            base_leg_ids=base_leg_scope,
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

        base_leg_ids = _base_leg_ids_from_legs(legs)
        open_base_leg_ids = _open_base_leg_ids(legs)
        if not open_base_leg_ids:
            open_base_leg_ids = _marked_base_leg_ids(legs)
        ledger_scope = ledger_df
        if not ledger_df.empty:
            ledger_scope = ledger_df[ledger_df["base_position_id"] == str(pid)]
        short_scope = ledger_scope
        if short_scope is not None and open_base_leg_ids:
            short_scope = short_scope[short_scope["base_leg_id"].astype(str).isin(open_base_leg_ids)]
        if not open_base_leg_ids:
            open_base_leg_ids = _open_base_leg_ids_from_ledger(ledger_scope) if ledger_scope is not None else []
        short_snapshot = _short_position_snapshot(
            short_scope,
            defense_df=ledger_scope,
        ) if short_scope is not None else {
            "open_instances": [],
            "closed_instances": [],
            "short_realized_pnl": 0.0,
            "short_unrealized_pnl": 0.0,
            "working_juice": 0.0,
            "locked_juice": 0.0,
            "weekly_locked_income": 0.0,
            "weekly_defense_debit": 0.0,
            "open_short_contracts": 0.0,
            "last10_defense_debits": [],
            "avg_defense_debit": None,
            "debit_cap": None,
            "safety_reserve": 0.0,
            "avg_capture_pct": None,
        }
        principal_cost = _initial_investment_from_marked_legs(legs)
        if principal_cost is None and ledger_scope is not None and open_base_leg_ids:
            principal_cost = _base_open_cost_from_ledger(
                ledger_scope,
                open_base_leg_ids,
            )
        if principal_cost is None and open_legs is not None and not open_legs.empty:
            principal_cost = _base_entry_cost_from_legs(open_legs)
        long_value_now = _base_mark_value_from_legs(open_legs, open_base_leg_ids)
        if long_value_now is None and ledger_scope is not None:
            long_value_now = _base_mark_value_from_ledger(ledger_scope, open_base_leg_ids)
        layer_snapshot = _position_layer_snapshot(
            ledger_scope,
            open_base_leg_ids,
            principal_cost,
            long_value_now,
        )
        short_realized = float(layer_snapshot.get("short_realized_pnl") or 0.0)
        short_unrealized = float(layer_snapshot.get("short_unrealized_pnl") or 0.0)
        liquidation_value = float(layer_snapshot.get("liquidation_value") or 0.0)
        cushion = float(layer_snapshot.get("cushion") or 0.0)
        safety_reserve = float(layer_snapshot.get("safety_reserve") or 0.0)
        open_short_contracts = float(short_snapshot.get("open_short_contracts") or 0.0)
        protected_now = layer_snapshot.get("protected_now")
        withdrawable_now = float(layer_snapshot.get("withdrawable_now") or 0.0)

        capture_target_pct = _to_float_or_none(pos.get("capture_target_pct")) or 0.70
        min_dte_to_roll = int(_to_float_or_none(pos.get("min_dte_to_roll")) or 3)
        cheap_buyback_threshold = _to_float_or_none(pos.get("cheap_buyback_threshold")) or 0.30
        hang_timer_max = int(_to_float_or_none(pos.get("hang_timer_max")) or 2)
        plan_settings = {
            "capture_target_pct": capture_target_pct,
            "min_dte_to_roll": min_dte_to_roll,
            "cheap_buyback_threshold": cheap_buyback_threshold,
            "hang_timer_max": hang_timer_max,
        }

        stock_entry = _latest_regime_entry(regimes_df, pos["symbol"]) if not regimes_df.empty else {}
        market_entry = _latest_regime_entry(regimes_df, "") if not regimes_df.empty else {}
        regime_condition = _overall_condition(
            _normalize_condition(stock_entry.get("stock_condition")),
            _normalize_condition(market_entry.get("market_condition")),
        )
        breaker_info = _circuit_breaker_from_inputs(pos["symbol"], breaker_inputs, regimes_df)
        breaker_action = str(breaker_info.get("breaker_action") or "")
        breaker_status = "ExitNow" if breaker_action == "EXIT" else ("ExitCandidate" if breaker_action == "DEFEND" else "None")

        signals, income_roll, protection_roll, emergency_roll, recommended_action, rule_triggered, rule_explanation = _short_signals_for_position(
            short_snapshot.get("open_instances") or [],
            pos["symbol"],
            cushion,
            safety_reserve,
            plan_settings,
            regime_condition,
            breaker_status,
        )

        maturity_flags = _maturity_flags_for_position(
            ledger_scope,
            open_base_leg_ids,
            principal_cost,
            long_value_now,
        ) if ledger_scope is not None else []
        maturity_streak = _count_consecutive_true(maturity_flags)
        is_mature = maturity_streak >= 3
        stage = "BUILDING"
        if is_mature and withdrawable_now > 0:
            stage = "PAYCHECK_MODE"
        elif is_mature:
            stage = "MATURE"
        elif protected_now:
            stage = "PROTECTED"

        if safety_reserve or open_short_contracts:
            try:
                business_loader.upsert_reserve(
                    {
                        "position_id": str(pid),
                        "as_of_date": snapshot_date,
                        "reserved_cash": float(round(safety_reserve, 2)),
                        "note_or_rule_text": "SafetyReserve = DebitCap(last10 defense avg * 1.5) * open_short_contracts",
                    },
                    note_prefix="SafetyReserve",
                )
            except Exception:
                logger.debug("SafetyReserve upsert failed", exc_info=True)

        # Reserve: use explicit rows if present, otherwise default % of base value
        explicit_reserve = float(reserves_df[reserves_df["position_id"] == pid]["reserved_cash"].sum()) if not reserves_df.empty else 0.0
        reserve_cash = explicit_reserve if explicit_reserve else (safety_reserve or (base_value * DEFAULT_RESERVE_PCT))

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

        current_epoch_id = None
        base_cost_basis_locked = None
        net_juice_week = None
        weekly_return_pct = None
        rolling_4w_avg_return_pct = None
        on_target_flag = None

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
                    capture_target_pct=_clean(_to_float_or_none(pos.get("capture_target_pct"))),
                    min_dte_to_roll=_clean(_to_float_or_none(pos.get("min_dte_to_roll"))),
                    cheap_buyback_threshold=_clean(_to_float_or_none(pos.get("cheap_buyback_threshold"))),
                    hang_timer_max=_clean(_to_float_or_none(pos.get("hang_timer_max"))),
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
                principal_cost=_clean_number(principal_cost),
                long_value_now=_clean_number(long_value_now),
                short_realized_pnl=_clean_number(short_realized),
                short_unrealized_pnl=_clean_number(short_unrealized),
                liquidation_value=_clean_number(liquidation_value),
                protected_now=protected_now,
                cushion=_clean_number(cushion),
                working_juice=_clean_number(short_snapshot.get("working_juice")),
                locked_juice=_clean_number(short_snapshot.get("locked_juice")),
                weekly_locked_income=_clean_number(short_snapshot.get("weekly_locked_income")),
                weekly_defense_debit=_clean_number(short_snapshot.get("weekly_defense_debit")),
                avg_defense_debit=_clean_number(short_snapshot.get("avg_defense_debit")),
                debit_cap=_clean_number(short_snapshot.get("debit_cap")),
                open_short_contracts=_clean_number(open_short_contracts),
                safety_reserve=_clean_number(safety_reserve),
                withdrawable_now=_clean_number(withdrawable_now),
                avg_capture_pct=_clean_number(short_snapshot.get("avg_capture_pct")),
                maturity_streak_weeks=maturity_streak,
                is_mature=is_mature,
                stage=stage,
                income_roll=income_roll,
                protection_roll=protection_roll,
                emergency_roll=emergency_roll,
                recommended_action=recommended_action,
                rule_triggered=rule_triggered,
                rule_explanation=rule_explanation,
                circuit_breaker_status=breaker_status,
                circuit_breaker_reasons=breaker_info.get("breaker_reasons") or [],
                last10_defense_debits=short_snapshot.get("last10_defense_debits") or [],
                open_short_signals=signals,
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


def _average_weekly_income(
    account: Optional[str],
    symbol: str,
    base_position_id: Optional[str] = None,
    lookback_weeks: int = 13,
) -> float:
    series = _income_series_by_week(account, symbol=symbol, base_position_id=base_position_id)
    if not series:
        return 0.0
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(weeks=lookback_weeks)
    values = [
        point.value
        for point in series
        if pd.Timestamp(point.period_start) >= cutoff
    ]
    if not values:
        return 0.0
    return float(np.mean(values))


def _open_marked_portfolio_totals(
    account: Optional[str],
    include_closed: bool = False,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
) -> Dict[str, float]:
    positions_df = business_loader.list_positions(account)
    expiry_start_ts = _normalize_expiry(expiry_start)
    expiry_end_ts = _normalize_expiry(expiry_end)
    total_initial_intrinsic = 0.0
    total_initial_extrinsic = 0.0
    total_current_intrinsic = 0.0
    open_leg_ids: List[str] = []

    for _, pos in positions_df.iterrows():
        if (not include_closed) and (not pd.isna(pos.get("closed_date"))):
            continue
        pid = pos["position_id"]
        legs = business_loader.list_base_legs(pid)
        if legs.empty:
            continue
        open_ids = _open_base_leg_ids(legs)
        if not open_ids:
            continue
        open_leg_ids.extend(open_ids)
        open_legs = legs[legs["base_leg_id"].astype(str).isin(open_ids)]
        if open_legs.empty:
            continue
        initial_intrinsic, initial_extrinsic = _initial_base_intrinsic_extrinsic_from_legs(
            open_legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        current_intrinsic = _current_base_intrinsic_from_legs(
            open_legs,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        total_initial_intrinsic += float(initial_intrinsic or 0.0)
        total_initial_extrinsic += float(initial_extrinsic or 0.0)
        total_current_intrinsic += float(current_intrinsic or 0.0)

    open_leg_ids = list(dict.fromkeys(open_leg_ids))
    if not open_leg_ids:
        return {
            "initial_intrinsic": 0.0,
            "initial_extrinsic": 0.0,
            "current_intrinsic": 0.0,
            "protection_collected": 0.0,
            "protection_gap": 0.0,
            "net_juice": 0.0,
        }

    net_juice = _net_juice_for_base_legs(
        account,
        open_leg_ids,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    protection_collected = _net_protection_for_base_legs(
        account,
        open_leg_ids,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    protection_gap = max(
        0.0,
        total_initial_intrinsic - (total_current_intrinsic + protection_collected),
    )
    return {
        "initial_intrinsic": float(total_initial_intrinsic),
        "initial_extrinsic": float(total_initial_extrinsic),
        "current_intrinsic": float(total_current_intrinsic),
        "protection_collected": float(protection_collected),
        "protection_gap": float(protection_gap),
        "net_juice": float(net_juice),
    }


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
    regimes = business_loader.list_regimes()
    breaker_inputs = business_loader.list_circuit_breakers()
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
        current_intrinsic = pm.current_base_intrinsic or 0.0
        intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + (protection or 0.0)))
        rebalance = _rebalance_extrinsic_to_protection(initial_extrinsic, raw_income, intrinsic_gap)
        protection_effective = (protection or 0.0) + rebalance
        base_strength_ratio = _safe_ratio((current_base_value or 0) + protection_effective, denom_intrinsic)
        income_adjusted = float(raw_income) - rebalance
        income_total_realized = _income_after_base_protection(original_base_value, current_base_value, protection_effective, income_adjusted)
        gap, applied, income_after, juice_needed = _protection_allocation(denom_intrinsic, current_base_value, protection_effective, income_adjusted)
        intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + protection_effective))
        income_efficiency = _safe_ratio(income_total_realized, denom_intrinsic)
        week_income, month_income = _stock_income_rates(
            account,
            pm.position.symbol,
            base_position_id=pm.position.position_id,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
        )
        avg_weekly_income = _average_weekly_income(
            account,
            pm.position.symbol,
            base_position_id=pm.position.position_id,
        )
        consistency_pct = _stock_income_consistency(account, pm.position.symbol)
        breaker = _circuit_breaker_from_inputs(pm.position.symbol, breaker_inputs, regimes)

        rows.append(
            StockSummaryRow(
                ticker=pm.position.symbol,
                original_base_value=_clean_number(original_base_value),
                current_base_value=_clean_number(current_base_value),
                initial_base_intrinsic=_clean_number(pm.initial_base_intrinsic),
                initial_base_extrinsic=_clean_number(pm.initial_base_extrinsic),
                current_base_intrinsic=_clean_number(pm.current_base_intrinsic),
                total_protection_collected=_clean_number(protection_effective),
                base_strength_ratio=_clean_number(base_strength_ratio),
                base_market_value_change=_clean_number(base_market_value_change),
                base_growth_pct=_clean_number(base_growth_pct),
                income_total_realized=float(income_total_realized),
                income_after_protection=_clean_number(income_after),
                protection_gap=_clean_number(intrinsic_gap),
                protection_juice_applied=_clean_number((applied or 0.0) + rebalance),
                juice_needed_for_protection=_clean_number(juice_needed),
                income_rate_weekly=_clean_number(week_income),
                income_rate_monthly=_clean_number(month_income),
                avg_weekly_income=_clean_number(avg_weekly_income),
                income_efficiency=_clean_number(income_efficiency),
                income_consistency_pct=_clean_number(consistency_pct),
                short_extrinsic_net=_clean_number(pm.short_extrinsic_net),
                long_extrinsic_loan=_clean_number(pm.long_extrinsic_loan),
                long_extrinsic_paid=_clean_number(pm.long_extrinsic_paid),
                long_extrinsic_remaining=_clean_number(pm.long_extrinsic_remaining),
                long_extrinsic_income=_clean_number(pm.long_extrinsic_income),
                breaker_state=breaker["breaker_state"],
                breaker_reasons=breaker["breaker_reasons"],
                breaker_action=breaker["breaker_action"],
                breaker_countdown=breaker["breaker_countdown"],
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
    open_mark = _open_marked_portfolio_totals(account, include_closed, expiry_start, expiry_end)
    open_mark_initial_base_value = open_mark["initial_intrinsic"] + open_mark["initial_extrinsic"]

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
        open_mark_initial_base_value=_clean_number(open_mark_initial_base_value),
        open_mark_initial_intrinsic=_clean_number(open_mark["initial_intrinsic"]),
        open_mark_initial_extrinsic=_clean_number(open_mark["initial_extrinsic"]),
        open_mark_current_base_intrinsic=_clean_number(open_mark["current_intrinsic"]),
        open_mark_protection_collected=_clean_number(open_mark["protection_collected"]),
        open_mark_protection_gap=_clean_number(open_mark["protection_gap"]),
        open_mark_net_juice=_clean_number(open_mark["net_juice"]),
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
    breaker_inputs = business_loader.list_circuit_breakers()
    regimes = business_loader.list_regimes()
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
    marked_leg_ids: List[str] = []
    for row in rows:
        legs = business_loader.list_base_legs(row.position.position_id)
        marked_leg_ids.extend(_marked_base_leg_ids(legs))
    if marked_leg_ids:
        marked_leg_ids = list(dict.fromkeys(marked_leg_ids))
    base_position_ids = [row.position.position_id for row in rows]
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
    protection = _net_protection_for_base_legs(
        account,
        marked_leg_ids,
        base_position_ids=base_position_ids,
        ticker=ticker,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    realized_short_intrinsic = protection or 0.0
    unrealized_short_intrinsic = 0.0
    for row in rows:
        legs = business_loader.list_base_legs(row.position.position_id)
        open_leg_ids = _open_base_leg_ids(legs)
        if not open_leg_ids:
            continue
        unrealized_short_intrinsic += _short_intrinsic_unrealized_for_position(
            account,
            ticker,
            base_position_id=row.position.position_id,
            base_leg_ids=open_leg_ids,
            expiry_start=expiry_start_ts,
            expiry_end=expiry_end_ts,
            legs=legs,
        )
    opened = pd.to_datetime(pm.position.opened_date, errors="coerce")
    closed = pd.to_datetime(pm.position.closed_date, errors="coerce")
    raw_income = _ledger_income(
        account,
        ticker,
        base_position_id=pm.position.position_id,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    net_juice_total = _net_juice_for_base_legs(
        account,
        marked_leg_ids,
        base_position_ids=base_position_ids,
        ticker=ticker,
        expiry_start=expiry_start_ts,
        expiry_end=expiry_end_ts,
    )
    current_intrinsic = pm.current_base_intrinsic or 0.0
    intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + (protection or 0.0)))
    protection_effective = realized_short_intrinsic + unrealized_short_intrinsic
    income_adjusted = float(raw_income)
    denom_intrinsic = initial_intrinsic or original_base_value
    base_strength_ratio = _safe_ratio((current_base_value or 0) + protection_effective, denom_intrinsic)
    base_growth_pct = None
    if denom_intrinsic:
        base_growth_pct = _safe_ratio((current_base_value or 0) - denom_intrinsic, denom_intrinsic)
    gap, applied, income_after, juice_needed = _protection_allocation(denom_intrinsic, current_base_value, protection_effective, income_adjusted)
    intrinsic_gap = max(0.0, (initial_intrinsic or 0.0) - (current_intrinsic + protection_effective))
    income_total_realized = _income_after_base_protection(original_base_value, current_base_value, protection_effective, income_adjusted)
    income_efficiency = _safe_ratio(income_total_realized, denom_intrinsic)
    income_series = _income_series_by_week(account, symbol=ticker, base_position_id=pm.position.position_id)
    base_strength_series = _base_strength_series_placeholder(_clean_number(base_strength_ratio))
    base_value_series = _base_value_series_placeholder(_clean_number(current_base_value))
    base_plus_protection = ((pm.current_base_intrinsic or 0.0) + protection_effective)
    breaker = _circuit_breaker_from_inputs(ticker, breaker_inputs, regimes)

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
        total_protection_collected=_clean_number(protection_effective),
        short_intrinsic_realized=_clean_number(realized_short_intrinsic),
        short_intrinsic_unrealized=_clean_number(unrealized_short_intrinsic),
        protection_gap=_clean_number(intrinsic_gap),
        net_juice_total=_clean_number(net_juice_total),
        short_extrinsic_net=_clean_number(total_short_extrinsic_net),
        long_extrinsic_loan=_clean_number(total_long_extrinsic_loan),
        long_extrinsic_paid=_clean_number(total_long_extrinsic_paid),
        long_extrinsic_remaining=_clean_number(total_long_extrinsic_remaining),
        long_extrinsic_income=_clean_number(total_long_extrinsic_income),
        income_series_weekly=income_series,
        base_strength_series_weekly=base_strength_series,
        base_value_series_weekly=base_value_series,
        positions=rows,
        breaker_state=breaker["breaker_state"],
        breaker_reasons=breaker["breaker_reasons"],
        breaker_action=breaker["breaker_action"],
        breaker_countdown=breaker["breaker_countdown"],
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

    profitable_pct, avg_weekly = _consistency(trades, account)

    contributed = _contributed_capital(snapshots)
    nav_current, drawdown = _drawdown(snapshots["nav_total"]) if "nav_total" in snapshots else (None, None)
    preservation = _safe_ratio(nav_current, contributed) if nav_current is not None else None

    pos_metrics = position_metrics(account, expiry_start=expiry_start, expiry_end=expiry_end)
    ledger_df = _normalize_ledger_df(excel_loader.get_ledger_rows(account))
    position_inputs: List[Dict[str, object]] = []
    for pm in pos_metrics:
        pid = pm.position.position_id
        legs = business_loader.list_base_legs(pid)
        ledger_scope = ledger_df[ledger_df["base_position_id"] == str(pid)] if not ledger_df.empty else ledger_df
        base_leg_ids = _open_base_leg_ids(legs)
        if not base_leg_ids:
            base_leg_ids = _marked_base_leg_ids(legs)
        if not base_leg_ids:
            base_leg_ids = _open_base_leg_ids_from_ledger(ledger_scope) if ledger_scope is not None else []
        position_inputs.append(
            {
                "ledger_df": ledger_scope,
                "base_leg_ids": base_leg_ids,
                "principal_cost": pm.principal_cost,
                "long_value_fallback": pm.long_value_now,
            }
        )

    account_principal = float(sum((pm.principal_cost or 0.0) for pm in pos_metrics))
    account_liquidation = float(sum((pm.liquidation_value or 0.0) for pm in pos_metrics))
    account_cushion = account_liquidation - account_principal
    account_safety = float(sum((pm.safety_reserve or 0.0) for pm in pos_metrics))
    account_withdrawable = max(0.0, account_cushion - account_safety)
    account_protected = account_liquidation >= account_principal if account_principal else False
    account_weekly_locked = float(sum((pm.weekly_locked_income or 0.0) for pm in pos_metrics))
    account_weekly_defense = float(sum((pm.weekly_defense_debit or 0.0) for pm in pos_metrics))
    account_net_weekly = account_weekly_locked - account_weekly_defense
    account_working_juice = float(sum((pm.working_juice or 0.0) for pm in pos_metrics))
    account_locked_juice = float(sum((pm.locked_juice or 0.0) for pm in pos_metrics))
    account_flags = _account_maturity_flags(position_inputs)
    account_streak = _count_consecutive_true(account_flags)
    account_is_mature = account_streak >= 3
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
        account_summary=AccountSummary(
            account=account,
            principal_cost=_clean_number(account_principal) or 0.0,
            liquidation_value=_clean_number(account_liquidation) or 0.0,
            cushion=_clean_number(account_cushion) or 0.0,
            protected_now=account_protected,
            safety_reserve=_clean_number(account_safety) or 0.0,
            withdrawable_now=_clean_number(account_withdrawable) or 0.0,
            maturity_streak_weeks=account_streak,
            is_mature=account_is_mature,
            weekly_locked_income=_clean_number(account_weekly_locked) or 0.0,
            weekly_defense_debits=_clean_number(account_weekly_defense) or 0.0,
            net_weekly_income=_clean_number(account_net_weekly) or 0.0,
            working_juice=_clean_number(account_working_juice) or 0.0,
            locked_juice=_clean_number(account_locked_juice) or 0.0,
        ),
        positions=pos_metrics,
    )


def mark_dashboard(account: Optional[str] = None) -> List[MarkPositionRow]:
    today = datetime.now().date()
    positions_df = business_loader.list_positions(account)
    if positions_df.empty:
        return []
    positions_df = positions_df.copy()
    positions_df["strategy_norm"] = positions_df.get("strategy").apply(_normalize_strategy_label)
    positions_df = positions_df[positions_df["strategy_norm"] == "CFM"]
    if "closed_date" in positions_df.columns:
        closed = positions_df["closed_date"]
        open_mask = closed.isna() | (closed.astype(str).str.strip() == "")
        positions_df = positions_df[open_mask]
    if positions_df.empty:
        return []

    ledger_rows = excel_loader.get_ledger_rows(account)
    net_by_position = _net_juice_current_month_by_position(ledger_rows, positions_df, today)
    regimes_df = business_loader.list_regimes()

    results: List[MarkPositionRow] = []
    for _, pos in positions_df.iterrows():
        position_id = str(pos.get("position_id"))
        symbol = str(pos.get("symbol") or "").upper()
        regime_entry = _latest_regime_entry_on_or_before(regimes_df, symbol, today)
        stock_regime = _normalize_condition(regime_entry.get("stock_condition")) if regime_entry else ""
        if not stock_regime:
            stock_regime = "Unknown"
        legs_df = business_loader.list_base_legs(position_id)
        long_dte, long_delta, dte_worst, dte_avg, delta_avg, ambiguous = _active_long_leg_stats(legs_df, today)
        strength = _strength_status(stock_regime, long_dte, long_delta, ambiguous)
        results.append(
            MarkPositionRow(
                position_id=position_id,
                symbol=symbol,
                stock_regime=stock_regime,
                long_dte_days=long_dte,
                long_dte_avg=dte_avg,
                long_dte_worst=dte_worst,
                long_delta=long_delta,
                long_delta_avg=delta_avg,
                long_delta_worst=long_delta,
                strength_status=strength,
                net_juice_current_month=net_by_position.get(position_id, 0.0),
            )
        )
    return results


def minimal_position_status(account: Optional[str] = None) -> List[MinimalPositionStatus]:
    today = datetime.now().date()
    positions_df = business_loader.list_positions(account)
    if positions_df.empty:
        return []
    positions_df = positions_df.copy()
    positions_df["strategy_norm"] = positions_df.get("strategy").apply(_normalize_strategy_label)
    positions_df = positions_df[positions_df["strategy_norm"] == "CFM"]
    if "closed_date" in positions_df.columns:
        closed = positions_df["closed_date"]
        open_mask = closed.isna() | (closed.astype(str).str.strip() == "")
        positions_df = positions_df[open_mask]
    if positions_df.empty:
        return []

    regimes_df = business_loader.list_regimes()
    ledger_rows = excel_loader.get_ledger_rows(account)
    ledger_df = _normalize_ledger_df(ledger_rows)
    if not ledger_df.empty:
        ledger_df = _ensure_signed_juice(ledger_df)
    results: List[MinimalPositionStatus] = []
    for _, pos in positions_df.iterrows():
        position_id = str(pos.get("position_id"))
        symbol = str(pos.get("symbol") or "").upper()
        stock_entry = _latest_regime_entry_on_or_before(regimes_df, symbol, today)
        market_entry = _latest_market_regime(regimes_df, today)
        stock_regime = _normalize_condition(stock_entry.get("stock_condition")) if stock_entry else ""
        market_regime = _normalize_condition(market_entry.get("market_condition")) if market_entry else ""
        if not stock_regime:
            stock_regime = "Unknown"
        if not market_regime:
            market_regime = "Unknown"

        legs_df = business_loader.list_base_legs(position_id)
        long_dte, long_delta, _, _, _, _ = _active_long_leg_stats(legs_df, today)
        open_base_leg_ids = _open_base_leg_ids(legs_df)
        if not open_base_leg_ids:
            open_base_leg_ids = _marked_base_leg_ids(legs_df)

        ticket_health = compute_ticket_health(long_dte, long_delta)
        conviction = compute_conviction(market_regime, stock_regime)
        posture = compute_operating_posture(conviction, ticket_health)

        if stock_regime == "Unknown" or market_regime == "Unknown":
            conviction = "MED"
            posture = "MANAGE"

        net_juice = get_net_juice_current_month_by_expiry(account, position_id, today)
        week_start, week_end = _current_week_window()
        weekly_net_income = _weekly_net_juice_by_expiry_week(
            ledger_df,
            position_id,
            week_start,
            week_end,
        )
        ledger_scope = ledger_df[ledger_df["base_position_id"] == str(position_id)] if not ledger_df.empty else ledger_df
        initial_base_cost = _initial_base_cost_for_position(legs_df, ledger_scope, open_base_leg_ids)
        weekly_return_pct = _safe_ratio(weekly_net_income, initial_base_cost)
        weekly_return_pct = float(round(weekly_return_pct * 100, 2)) if weekly_return_pct is not None else None
        marked_ids = _marked_base_leg_ids(legs_df)
        net_juice_since_open = _net_juice_since_open(ledger_df, position_id, marked_ids)

        results.append(
            MinimalPositionStatus(
                position_id=position_id,
                symbol=symbol,
                market_regime=market_regime,
                stock_regime=stock_regime,
                long_dte_days=long_dte,
                long_delta=long_delta,
                ticket_health=ticket_health,
                conviction=conviction,
                operating_posture=posture,
                net_juice_current_month=net_juice,
                weekly_net_income_avg=float(round(weekly_net_income, 2)),
                weekly_return_pct=weekly_return_pct,
                net_juice_since_open=float(round(net_juice_since_open, 2)) if net_juice_since_open is not None else None,
            )
        )
    return results

"""Schema definitions for business scoreboard data and metrics."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class NavSnapshot(BaseModel):
    account: str
    date: date
    nav_total: float
    nav_cash: Optional[float] = None
    nav_long_value: Optional[float] = None
    nav_liabilities: Optional[float] = None
    deposits: float = 0.0
    withdrawals: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class BasePosition(BaseModel):
    position_id: str
    account: str
    symbol: str
    strategy: str
    base_type: str
    opened_date: date
    closed_date: Optional[date] = None
    capture_target_pct: Optional[float] = None
    min_dte_to_roll: Optional[int] = None
    cheap_buyback_threshold: Optional[float] = None
    hang_timer_max: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class BaseLeg(BaseModel):
    base_leg_id: str
    position_id: str
    date: date
    time: Optional[str] = None
    instrument_type: str
    side: str
    quantity: float
    strike: Optional[float] = None
    expiry: Optional[date] = None
    price: float
    underlying_price: Optional[float] = None
    delta: Optional[float] = None
    fees: float = 0.0
    amount: float
    tag: Optional[str] = None
    condition: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BaseLegUpdate(BaseModel):
    delta: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class Reserve(BaseModel):
    position_id: str
    as_of_date: date
    reserved_cash: float
    note_or_rule_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReplacementCost(BaseModel):
    position_id: str
    as_of_date: date
    replacement_cost_same_size: float
    unit_replacement_cost: float
    method: str = "MANUAL"

    model_config = ConfigDict(from_attributes=True)


class ShortLegSignal(BaseModel):
    key: str
    strike: Optional[float] = None
    expiry: Optional[date] = None
    contracts: Optional[int] = None
    extrinsic_now: Optional[float] = None
    capture_pct: Optional[float] = None
    dte: Optional[int] = None
    near_atm: Optional[bool] = None
    income_roll: bool = False
    protection_roll: bool = False
    emergency: bool = False

    model_config = ConfigDict(from_attributes=True)


class PositionMetrics(BaseModel):
    position: BasePosition
    base_value: Optional[float] = None
    base_cost: Optional[float] = None
    initial_base_cost: Optional[float] = None
    initial_base_intrinsic: Optional[float] = None
    initial_base_extrinsic: Optional[float] = None
    current_base_intrinsic: Optional[float] = None
    base_plus_protection: Optional[float] = None
    base_health_delta: Optional[float] = None
    net_juice_to_date: float = 0.0
    net_intrinsic_to_date: float = 0.0
    short_extrinsic_net: Optional[float] = None
    long_extrinsic_loan: Optional[float] = None
    long_extrinsic_paid: Optional[float] = None
    long_extrinsic_remaining: Optional[float] = None
    long_extrinsic_income: Optional[float] = None
    replacement_cost: Optional[float] = None
    unit_replacement_cost: Optional[float] = None
    reserve_cash: float = 0.0
    replacement_ratio: Optional[float] = None
    base_growth: Optional[float] = None
    scale_capacity_units: Optional[int] = None
    roll_plan_flag: bool = False
    roll_action_flag: bool = False
    principal_cost: Optional[float] = None
    long_value_now: Optional[float] = None
    short_realized_pnl: Optional[float] = None
    short_unrealized_pnl: Optional[float] = None
    liquidation_value: Optional[float] = None
    protected_now: Optional[bool] = None
    cushion: Optional[float] = None
    working_juice: Optional[float] = None
    locked_juice: Optional[float] = None
    weekly_locked_income: Optional[float] = None
    weekly_defense_debit: Optional[float] = None
    avg_defense_debit: Optional[float] = None
    debit_cap: Optional[float] = None
    open_short_contracts: Optional[float] = None
    safety_reserve: Optional[float] = None
    withdrawable_now: Optional[float] = None
    avg_capture_pct: Optional[float] = None
    maturity_streak_weeks: Optional[int] = None
    is_mature: Optional[bool] = None
    stage: Optional[str] = None
    income_roll: bool = False
    protection_roll: bool = False
    emergency_roll: bool = False
    recommended_action: Optional[str] = None
    rule_triggered: Optional[str] = None
    rule_explanation: Optional[str] = None
    circuit_breaker_status: Optional[str] = None
    circuit_breaker_reasons: List[str] = Field(default_factory=list)
    last10_defense_debits: List[float] = Field(default_factory=list)
    open_short_signals: List[ShortLegSignal] = Field(default_factory=list)


class MarkPositionRow(BaseModel):
    position_id: str
    symbol: str
    stock_regime: Optional[str] = None
    long_dte_days: Optional[int] = None
    long_dte_avg: Optional[float] = None
    long_dte_worst: Optional[int] = None
    long_delta: Optional[float] = None
    long_delta_avg: Optional[float] = None
    long_delta_worst: Optional[float] = None
    strength_status: str
    net_juice_current_month: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class MinimalPositionStatus(BaseModel):
    position_id: str
    symbol: str
    market_regime: str
    stock_regime: str
    long_dte_days: Optional[int] = None
    long_delta: Optional[float] = None
    ticket_health: str
    conviction: str
    operating_posture: str
    net_juice_current_month: float = 0.0
    weekly_net_income_avg: Optional[float] = None
    weekly_return_pct: Optional[float] = None
    net_juice_since_open: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class BusinessDashboard(BaseModel):
    weekly_net_juice: float
    monthly_net_juice: float
    weekly_juice_yield_pct: float
    monthly_juice_yield_pct: float
    consistency_profitable_weeks_pct: float
    consistency_avg_weekly_juice: float
    preservation_ratio: Optional[float]
    drawdown_pct: Optional[float]
    reserve_coverage: Optional[float]
    worst_replacement_ratio: Optional[float]
    concentration_pct: Optional[float] = None
    nav_current: Optional[float] = None
    nav_cash: Optional[float] = None
    nav_long_value: Optional[float] = None
    nav_liabilities: Optional[float] = None
    nav_peak: Optional[float] = None
    nav_contributed: Optional[float] = None
    portfolio_replacement_ratio: Optional[float] = None
    distributable_income_weekly: Optional[float] = None
    distributable_income_monthly: Optional[float] = None
    income_allowed_weekly: Optional[bool] = None
    income_allowed_monthly: Optional[bool] = None
    mode: Optional[str] = None  # SCALE_READY / MAINTAIN / STRENGTHEN
    nav_weekly: List["NavPoint"] = Field(default_factory=list)
    nav_monthly: List["NavPoint"] = Field(default_factory=list)
    account_summary: Optional["AccountSummary"] = None
    positions: List[PositionMetrics] = Field(default_factory=list)


class AccountSummary(BaseModel):
    account: Optional[str] = None
    principal_cost: float = 0.0
    liquidation_value: float = 0.0
    cushion: float = 0.0
    protected_now: bool = False
    safety_reserve: float = 0.0
    withdrawable_now: float = 0.0
    maturity_streak_weeks: int = 0
    is_mature: bool = False
    weekly_locked_income: float = 0.0
    weekly_defense_debits: float = 0.0
    net_weekly_income: float = 0.0
    working_juice: float = 0.0
    locked_juice: float = 0.0


class NavPoint(BaseModel):
    period_start: date
    nav_total: float
    nav_cash: Optional[float] = None
    nav_long_value: Optional[float] = None
    nav_liabilities: Optional[float] = None


class PillarSeriesPoint(BaseModel):
    """Time-series point for pillar charts (weekly cadence)."""

    period_start: date
    value: float


class StockSummaryRow(BaseModel):
    ticker: str
    original_base_value: Optional[float] = None
    current_base_value: Optional[float] = None
    initial_base_intrinsic: Optional[float] = None
    initial_base_extrinsic: Optional[float] = None
    current_base_intrinsic: Optional[float] = None
    total_protection_collected: Optional[float] = None
    base_strength_ratio: Optional[float] = None
    base_market_value_change: Optional[float] = None
    base_growth_pct: Optional[float] = None
    income_total_realized: float = 0.0
    income_after_protection: Optional[float] = None
    protection_gap: Optional[float] = None
    protection_juice_applied: Optional[float] = None
    juice_needed_for_protection: Optional[float] = None
    income_rate_weekly: Optional[float] = None
    income_rate_monthly: Optional[float] = None
    avg_weekly_income: Optional[float] = None
    income_efficiency: Optional[float] = None
    income_consistency_pct: Optional[float] = None
    short_extrinsic_net: Optional[float] = None
    long_extrinsic_loan: Optional[float] = None
    long_extrinsic_paid: Optional[float] = None
    long_extrinsic_remaining: Optional[float] = None
    long_extrinsic_income: Optional[float] = None
    contribution_income_pct: Optional[float] = None
    contribution_protection_pct: Optional[float] = None
    contribution_growth_pct: Optional[float] = None
    breaker_state: Optional[str] = None
    breaker_reasons: List[str] = Field(default_factory=list)
    breaker_action: Optional[str] = None
    breaker_countdown: Optional[str] = None


class StockDetail(BaseModel):
    ticker: str
    base_strength_ratio: Optional[float] = None
    base_growth_pct: Optional[float] = None
    income_total_realized: float = 0.0
    income_after_protection: Optional[float] = None
    income_efficiency: Optional[float] = None
    base_market_value: Optional[float] = None
    original_base_value: Optional[float] = None
    initial_base_intrinsic: Optional[float] = None
    initial_base_extrinsic: Optional[float] = None
    current_base_intrinsic: Optional[float] = None
    base_plus_protection: Optional[float] = None
    total_protection_collected: Optional[float] = None
    short_intrinsic_realized: Optional[float] = None
    short_intrinsic_unrealized: Optional[float] = None
    protection_gap: Optional[float] = None
    net_juice_total: Optional[float] = None
    short_extrinsic_net: Optional[float] = None
    long_extrinsic_loan: Optional[float] = None
    long_extrinsic_paid: Optional[float] = None
    long_extrinsic_remaining: Optional[float] = None
    long_extrinsic_income: Optional[float] = None
    income_series_weekly: list[PillarSeriesPoint] = Field(default_factory=list)
    base_strength_series_weekly: list[PillarSeriesPoint] = Field(default_factory=list)
    base_value_series_weekly: list[PillarSeriesPoint] = Field(default_factory=list)
    positions: list[PositionMetrics] = Field(default_factory=list)
    short_leg_matches: list["ShortLegMatch"] = Field(default_factory=list)
    breaker_state: Optional[str] = None
    breaker_reasons: List[str] = Field(default_factory=list)
    breaker_action: Optional[str] = None
    breaker_countdown: Optional[str] = None


class ShortLegMatch(BaseModel):
    base_leg_id: str
    base_position_id: Optional[str] = None
    base_leg_date: Optional[date] = None
    base_leg_time: Optional[str] = None
    short_count: int = 0
    latest_short_date: Optional[datetime] = None


class PortfolioSummary(BaseModel):
    total_account_value: Optional[float] = None
    total_cash: Optional[float] = None
    total_base_value_initial: Optional[float] = None
    total_current_base_value: Optional[float] = None
    total_initial_base_intrinsic: Optional[float] = None
    total_initial_base_extrinsic: Optional[float] = None
    total_current_base_intrinsic: Optional[float] = None
    total_protection_collected: Optional[float] = None
    total_base_plus_protection: Optional[float] = None
    total_income_realized: float = 0.0
    total_income_after_protection: Optional[float] = None
    total_protection_gap: Optional[float] = None
    total_juice_needed_for_protection: Optional[float] = None
    total_base_strength_ratio: Optional[float] = None
    total_base_growth_pct: Optional[float] = None
    total_short_extrinsic_net: Optional[float] = None
    total_long_extrinsic_loan: Optional[float] = None
    total_long_extrinsic_paid: Optional[float] = None
    total_long_extrinsic_remaining: Optional[float] = None
    total_long_extrinsic_income: Optional[float] = None
    open_mark_initial_base_value: Optional[float] = None
    open_mark_initial_intrinsic: Optional[float] = None
    open_mark_initial_extrinsic: Optional[float] = None
    open_mark_current_base_intrinsic: Optional[float] = None
    open_mark_protection_collected: Optional[float] = None
    open_mark_protection_gap: Optional[float] = None
    open_mark_net_juice: Optional[float] = None
    stocks: list[StockSummaryRow] = Field(default_factory=list)


class RegimeEntry(BaseModel):
    date: date
    symbol: str
    stock_score: int
    market_score: int
    stock_condition: str
    market_condition: str

    model_config = ConfigDict(from_attributes=True)


class ProtectionMetrics(BaseModel):
    symbol: str
    account: Optional[str] = None
    target_income: float
    latest_cycle_income: float
    shortfall: float
    defense_cost: float
    cumulative_income: float
    estimated_break_even_drop: Optional[float] = None


class CashMovement(BaseModel):
    movement_id: str
    account: str
    date: date
    direction: str
    purpose: str
    amount: float
    position_id: Optional[str] = None
    note: Optional[str] = None


class CashAllocation(BaseModel):
    account: str
    ticker: str
    type: str
    amount: float
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

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
    fees: float = 0.0
    amount: float
    tag: Optional[str] = None
    condition: Optional[str] = None

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

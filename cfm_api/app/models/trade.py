"""Schema definitions for trade data and analytics."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict
from datetime import date, datetime


class Trade(BaseModel):
    date: datetime
    ticker: str
    strategy: str
    premium_in: Optional[float] = None
    premium_out: Optional[float] = None
    juice: float
    basis: Optional[float] = None
    dte: Optional[int] = None
    itm: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class AccountInfo(BaseModel):
    name: str
    label: str


class WeeklySummary(BaseModel):
    week_start: date
    week_end: date
    strategy: str
    total_juice: float
    total_basis: float
    percent_return: float
    trade_count: int


class CombinedWeeklyJuicePoint(BaseModel):
    week_start: date
    total_juice: float


class WeeklyPercentReturnPoint(BaseModel):
    week_start: date
    percent_return: float


class RollingAverageJuicePoint(BaseModel):
    week_start: date
    rolling_average: float


class JuicePerTicker(BaseModel):
    ticker: str
    total_juice: float


class DashboardMetrics(BaseModel):
    weekly_juice_by_strategy: List[WeeklySummary]
    combined_weekly_juice: List[CombinedWeeklyJuicePoint]
    weekly_percent_returns: List[WeeklyPercentReturnPoint]
    rolling_average_juice: List[RollingAverageJuicePoint]
    juice_per_ticker: List[JuicePerTicker]
    win_rate: float
    cumulative_juice: float
    total_trades: int


class TradeCreate(BaseModel):
    account: str | None = None
    date: date
    ticker: str
    strategy: str
    premium_in: Optional[float] = None
    premium_out: Optional[float] = None
    juice: float
    basis: Optional[float] = None
    dte: Optional[int] = None
    itm: Optional[bool] = None


class LedgerRow(BaseModel):
    account: str
    date: Optional[datetime]
    action: Optional[str]
    side: Optional[str]
    ticker: str
    contracts: Optional[int]
    strike: Optional[float]
    expiry: Optional[str]
    premium_buyback: Optional[float]
    underlying: Optional[float]
    juice_per_contract: Optional[float]
    signed_juice_dollars: Optional[float]
    signed_juice_per_100: Optional[float]
    key: Optional[str]
    notes: Optional[str] = None
    row_number: Optional[int] = None


class LedgerEntryCreate(BaseModel):
    account: str
    ticker: str
    action: str  # Open / Close
    strategy: str
    side: Optional[str] = "Call"
    contracts: int
    strike: float
    expiry: date
    trade_datetime: datetime
    premium: float
    underlying: Optional[float] = None


class LedgerUpdate(BaseModel):
    row_number: int
    account: str
    ticker: str
    action: str
    strategy: str
    side: Optional[str] = "Call"
    contracts: int
    strike: float
    expiry: date
    trade_datetime: datetime
    premium: float

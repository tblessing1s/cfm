"""API routes for business scoreboard data and metrics."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.business import (
    NavSnapshot,
    BasePosition,
    BaseLeg,
    Reserve,
    ReplacementCost,
    BusinessDashboard,
    PositionMetrics,
    PortfolioSummary,
    StockSummaryRow,
    StockDetail,
    RegimeEntry,
    ProtectionMetrics,
    CashMovement,
)
from ..services import business_metrics
from ..utils import business_loader

router = APIRouter(tags=["business"])


@router.get("/business-dashboard", response_model=BusinessDashboard)
async def read_business_dashboard(
    account: str | None = Query(None, description="Account name or label"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> BusinessDashboard:
    return business_metrics.business_dashboard(
        account,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )


@router.get("/portfolio-summary", response_model=PortfolioSummary)
async def read_portfolio_summary(
    account: str | None = Query(None, description="Account name or label"),
    include_closed: bool = Query(False, description="Include closed base positions"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> PortfolioSummary:
    return business_metrics.portfolio_summary(
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )


@router.get("/stocks", response_model=List[StockSummaryRow])
async def list_stock_rows(
    account: str | None = Query(None, description="Account name or label"),
    include_closed: bool = Query(False, description="Include closed base positions"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> List[StockSummaryRow]:
    return business_metrics.stock_summary_rows(
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )


@router.get("/stocks/{ticker}", response_model=StockDetail)
async def get_stock_detail(
    ticker: str,
    account: str | None = Query(None, description="Account name or label"),
    include_closed: bool = Query(False, description="Include closed base positions"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> StockDetail:
    detail = business_metrics.stock_detail(
        ticker,
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )
    if not detail.positions:
        raise HTTPException(status_code=404, detail=f"No stock data found for {ticker}")
    return detail


@router.post("/regime", response_model=RegimeEntry, status_code=201)
async def create_regime_entry(payload: RegimeEntry) -> RegimeEntry:
    return business_metrics.save_regime_entry(payload.model_dump())


@router.get("/regime", response_model=List[RegimeEntry])
async def list_regime_entries(symbol: str | None = Query(None, description="Filter by symbol")) -> List[RegimeEntry]:
    return business_metrics.list_regime_entries(symbol)


@router.get("/protection-metrics", response_model=ProtectionMetrics)
async def read_protection_metrics(
    symbol: str = Query(..., description="Symbol to compute protection metrics for"),
    account: str | None = Query(None, description="Account name or label"),
    target_income: float = Query(82.5, description="Target income per cycle"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> ProtectionMetrics:
    return business_metrics.protection_metrics(
        symbol,
        account,
        target_income=target_income,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )


@router.get("/positions", response_model=List[PositionMetrics])
async def list_positions(
    account: str | None = Query(None, description="Account name or label"),
    include_closed: bool = Query(False, description="Include closed base positions"),
    expiry_start: str | None = Query(None, description="Filter income metrics from this option expiry (YYYY-MM-DD)"),
    expiry_end: str | None = Query(None, description="Filter income metrics through this option expiry (YYYY-MM-DD)"),
) -> List[PositionMetrics]:
    return business_metrics.position_metrics(
        account,
        include_closed=include_closed,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
    )


@router.get("/positions/raw", response_model=List[BasePosition])
async def list_positions_raw(account: str | None = Query(None, description="Account name or label")) -> List[BasePosition]:
    df = business_loader.list_positions(account)
    return [BasePosition(**record) for record in df.to_dict("records")]


@router.post("/positions", response_model=BasePosition, status_code=201)
async def create_position(payload: BasePosition) -> BasePosition:
    created = business_loader.add_position(payload.model_dump())
    return BasePosition(**created)


@router.put("/positions/{position_id}", response_model=BasePosition)
async def update_position(position_id: str, payload: BasePosition) -> BasePosition:
    updated = business_loader.update_position(position_id, payload.model_dump())
    return BasePosition(**updated)


@router.get("/nav-snapshots", response_model=List[NavSnapshot])
async def list_nav_snapshots(account: str | None = Query(None, description="Account name or label")) -> List[NavSnapshot]:
    df = business_loader.list_nav(account)
    return [NavSnapshot(**record) for record in df.to_dict("records")]


@router.post("/nav-snapshots", response_model=NavSnapshot, status_code=201)
async def create_nav_snapshot(payload: NavSnapshot) -> NavSnapshot:
    created = business_loader.add_nav_snapshot(payload.model_dump())
    return NavSnapshot(**created)


@router.get("/cash-movements", response_model=List[CashMovement])
async def list_cash_movements(
    account: str | None = Query(None, description="Account name or label"),
    position_id: str | None = Query(None, description="Filter by base position id"),
) -> List[CashMovement]:
    df = business_loader.list_cash_movements(account, position_id=position_id)
    return [CashMovement(**record) for record in df.to_dict("records")]


@router.post("/cash-movements", response_model=CashMovement, status_code=201)
async def create_cash_movement(payload: CashMovement) -> CashMovement:
    created = business_loader.add_cash_movement(payload.model_dump())
    return CashMovement(**created)


@router.get("/base-legs", response_model=List[BaseLeg])
async def list_base_legs(position_id: str | None = Query(None)) -> List[BaseLeg]:
    df = business_loader.list_base_legs(position_id)
    return [BaseLeg(**record) for record in df.to_dict("records")]


@router.post("/base-legs", response_model=BaseLeg, status_code=201)
async def create_base_leg(payload: BaseLeg) -> BaseLeg:
    created = business_loader.add_base_leg(payload.model_dump())
    return BaseLeg(**created)


@router.get("/reserves", response_model=List[Reserve])
async def list_reserves(position_id: str | None = Query(None)) -> List[Reserve]:
    df = business_loader.list_reserves(position_id)
    return [Reserve(**record) for record in df.to_dict("records")]


@router.post("/reserves", response_model=Reserve, status_code=201)
async def create_reserve(payload: Reserve) -> Reserve:
    created = business_loader.add_reserve(payload.model_dump())
    return Reserve(**created)


@router.get("/replacement-costs", response_model=List[ReplacementCost])
async def list_replacement_costs(position_id: str | None = Query(None)) -> List[ReplacementCost]:
    df = business_loader.list_replacement_costs(position_id)
    return [ReplacementCost(**record) for record in df.to_dict("records")]


@router.post("/replacement-costs", response_model=ReplacementCost, status_code=201)
async def create_replacement_cost(payload: ReplacementCost) -> ReplacementCost:
    created = business_loader.add_replacement_cost(payload.model_dump())
    return ReplacementCost(**created)

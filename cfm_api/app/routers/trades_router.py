"""API routes for trade analytics."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from ..models.trade import AccountInfo, DashboardMetrics, LedgerEntryCreate, LedgerRow, LedgerUpdate, Trade, TradeCreate, WeeklySummary
from ..services.trade_service import (
    get_all_trades,
    get_dashboard_metrics,
    append_ledger_entries,
    get_ledger_rows,
    update_ledger_entry,
    record_trades,
    get_weekly_summary,
)
from ..utils import excel_loader

router = APIRouter(tags=["trades"])


def _handle_account(func, account: str | None):
    try:
        return func(account)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/accounts", response_model=List[AccountInfo])
async def list_accounts() -> List[AccountInfo]:
    available = excel_loader.get_available_accounts()
    return [AccountInfo(**account) for account in available]


@router.get("/trades", response_model=List[Trade])
async def read_trades(account: str | None = Query(None, description="Account name or label")) -> List[Trade]:
    return _handle_account(get_all_trades, account)


@router.get("/ledger", response_model=List[LedgerRow])
async def read_ledger(account: str | None = Query(None, description="Account name or label")) -> List[LedgerRow]:
    return _handle_account(get_ledger_rows, account)


@router.post("/trades", status_code=201)
async def create_trades(payload: List[TradeCreate]) -> dict:
    created = record_trades(payload)
    return {"created": created}


@router.post("/ledger/append", response_model=List[LedgerRow])
async def append_ledger(payload: List[LedgerEntryCreate]) -> List[LedgerRow]:
    """
    Append ledger entries synchronously using the same pipeline as the CLI.
    Errors bubble back to the UI as a 422 with details.
    """
    try:
        return append_ledger_entries(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/ledger/update", response_model=LedgerRow)
async def update_ledger(payload: LedgerUpdate) -> LedgerRow:
    try:
        return update_ledger_entry(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/weekly-summary", response_model=List[WeeklySummary])
async def read_weekly_summary(
    account: str | None = Query(None, description="Account name or label")
) -> List[WeeklySummary]:
    return _handle_account(get_weekly_summary, account)


@router.get("/dashboard-metrics", response_model=DashboardMetrics)
async def read_dashboard_metrics(
    account: str | None = Query(None, description="Account name or label")
) -> DashboardMetrics:
    return _handle_account(get_dashboard_metrics, account)

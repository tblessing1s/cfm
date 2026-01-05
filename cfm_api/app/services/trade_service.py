"""Business logic for extrapolating analytics from trades."""
from __future__ import annotations

from typing import List, Optional
import subprocess
import sys
import logging
import os
from datetime import datetime
from pathlib import Path
import time

import pandas as pd

logger = logging.getLogger(__name__)

from ..models.trade import (
    CombinedWeeklyJuicePoint,
    DashboardMetrics,
    JuicePerTicker,
    LedgerRow,
    LedgerEntryCreate,
    LedgerUpdate,
    RollingAverageJuicePoint,
    Trade,
    TradeCreate,
    WeeklyPercentReturnPoint,
    WeeklySummary,
)
from ..utils import excel_loader


def _week_start(df: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(df["date"], errors="coerce")
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


def _safe_percent(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return (numerator / denominator) * 100.0


def _weekly_combined_frame(account: Optional[str] = None) -> pd.DataFrame:
    trades = excel_loader.get_all_trades(account)
    if trades.empty:
        return pd.DataFrame(columns=["week_start", "total_juice", "total_basis"])

    working = trades.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"])
    if working.empty:
        return pd.DataFrame(columns=["week_start", "total_juice", "total_basis"])
    working["week_start"] = _week_start(working)

    grouped = (
        working.groupby("week_start", as_index=False)
        .agg(total_juice=("juice", "sum"), total_basis=("basis", "sum"))
        .sort_values("week_start")
    )
    return grouped


def get_all_trades(account: Optional[str] = None) -> List[Trade]:
    trades = excel_loader.get_all_trades(account)
    ordered = trades.sort_values("date", ascending=False)
    return [Trade(**record) for record in ordered.to_dict("records")]


def get_weekly_summary(account: Optional[str] = None) -> List[WeeklySummary]:
    summary = excel_loader.get_weekly_summary(account)
    if summary.empty:
        return []

    frame = summary.copy()
    frame["week_end"] = frame["week_start"] + pd.Timedelta(days=6)
    frame["percent_return"] = frame.apply(
        lambda row: _safe_percent(row["total_juice"], row["total_basis"]), axis=1
    )
    frame["week_start"] = frame["week_start"].dt.date
    frame["week_end"] = frame["week_end"].dt.date

    records = frame[
        [
            "week_start",
            "week_end",
            "strategy",
            "total_juice",
            "total_basis",
            "percent_return",
            "trade_count",
        ]
    ].to_dict("records")

    return [WeeklySummary(**record) for record in records]


def weekly_juice_totals_by_strategy(account: Optional[str] = None) -> List[WeeklySummary]:
    return get_weekly_summary(account)


def combined_weekly_juice(account: Optional[str] = None) -> List[CombinedWeeklyJuicePoint]:
    frame = _weekly_combined_frame(account)
    if frame.empty:
        return []

    frame["week_start"] = frame["week_start"].dt.date
    records = frame[["week_start", "total_juice"]].to_dict("records")
    return [CombinedWeeklyJuicePoint(**record) for record in records]


def weekly_percent_returns(account: Optional[str] = None) -> List[WeeklyPercentReturnPoint]:
    frame = _weekly_combined_frame(account)
    if frame.empty:
        return []

    frame["percent_return"] = frame.apply(
        lambda row: _safe_percent(row["total_juice"], row["total_basis"]), axis=1
    )
    frame["week_start"] = frame["week_start"].dt.date

    records = frame[["week_start", "percent_return"]].to_dict("records")
    return [WeeklyPercentReturnPoint(**record) for record in records]


def rolling_average_juice(lookback_weeks: int = 8, account: Optional[str] = None) -> List[RollingAverageJuicePoint]:
    frame = _weekly_combined_frame(account)
    if frame.empty:
        return []

    frame = frame.sort_values("week_start").reset_index(drop=True)
    frame["rolling_average"] = (
        frame["total_juice"].rolling(window=lookback_weeks, min_periods=1).mean()
    )
    frame["week_start"] = frame["week_start"].dt.date

    records = frame[["week_start", "rolling_average"]].to_dict("records")
    return [RollingAverageJuicePoint(**record) for record in records]


def juice_per_ticker(account: Optional[str] = None) -> List[JuicePerTicker]:
    trades = excel_loader.get_all_trades(account)
    if trades.empty:
        return []

    grouped = (
        trades.groupby("ticker", as_index=False)
        .agg(total_juice=("juice", "sum"))
        .sort_values("total_juice", ascending=False)
    )
    records = grouped.to_dict("records")
    return [JuicePerTicker(**record) for record in records]


def win_rate(account: Optional[str] = None) -> float:
    trades = excel_loader.get_all_trades(account)
    if trades.empty:
        return 0.0
    wins = (trades["juice"] > 0).sum()
    return float(wins) / len(trades)


def cumulative_juice(account: Optional[str] = None) -> float:
    trades = excel_loader.get_all_trades(account)
    return float(trades["juice"].sum()) if not trades.empty else 0.0


def get_dashboard_metrics(account: Optional[str] = None) -> DashboardMetrics:
    summary = weekly_juice_totals_by_strategy(account)
    combined = combined_weekly_juice(account)
    returns = weekly_percent_returns(account)
    rolling = rolling_average_juice(account=account)
    per_ticker = juice_per_ticker(account)
    metrics = excel_loader.get_dashboard_metrics(account)

    return DashboardMetrics(
        weekly_juice_by_strategy=summary,
        combined_weekly_juice=combined,
        weekly_percent_returns=returns,
        rolling_average_juice=rolling,
        juice_per_ticker=per_ticker,
        win_rate=win_rate(account),
        cumulative_juice=cumulative_juice(account),
        total_trades=metrics.get("total_trades", len(excel_loader.get_all_trades(account))),
    )


def record_trades(trades: List[TradeCreate]) -> int:
    """Persist a batch of UI-submitted trades into the journal store."""
    if not trades:
        return 0

    prepared_rows = []
    for trade in trades:
        account_name = excel_loader.resolve_account_name(trade.account)
        prepared_rows.append(
            {
                "account": account_name,
                "date": trade.date.isoformat(),
                "ticker": trade.ticker.strip().upper(),
                "strategy": trade.strategy.strip(),
                "premium_in": trade.premium_in,
                "premium_out": trade.premium_out,
                "juice": float(trade.juice),
                "basis": trade.basis,
                "dte": trade.dte,
                "itm": trade.itm,
            }
        )

    return excel_loader.append_ui_trades(prepared_rows)


def get_ledger_rows(account: Optional[str] = None) -> List[LedgerRow]:
    logger.info(f"get_ledger_rows start for account={account}")
    start = time.time()
    try:
        rows = excel_loader.get_ledger_rows(account)
    except Exception as exc:
        logger.exception(f"Error in excel_loader.get_ledger_rows for account={account}: {exc}")
        raise
    duration = time.time() - start
    logger.info(f"get_ledger_rows returned {len(rows) if rows is not None else 0} rows in {duration:.2f}s for account={account}")
    return [LedgerRow(**row) for row in rows]


def append_ledger_entries(entries: List[LedgerEntryCreate]) -> List[LedgerRow]:
    # Use direct Excel writer to support base_position_id and avoid CLI dependencies
    try:
        appended = excel_loader.append_ledger_entries([entry.model_dump() for entry in entries])
        return [LedgerRow(**row) for row in appended]
    except Exception as exc:
        raise RuntimeError(str(exc))
    base_dir = Path(__file__).resolve().parents[3]
    journal_dir = base_dir / "cfm_journal"
    script_path = journal_dir / "cfm_ledger_autotemplate.py"
    if not script_path.exists():
        raise RuntimeError(f"Ledger script not found at {script_path}")

    logger.info(f"Processing {len(entries)} ledger entries")
    results: List[LedgerRow] = []
    for i, entry in enumerate(entries):
        logger.info(f"Processing entry {i+1}/{len(entries)}: {entry.action} {entry.contracts} {entry.side} {entry.ticker} @ ${entry.strike}")
        
        # Resolve account to Travis/Christie label expected by CLI
        descriptor = excel_loader.resolve_account(entry.account)
        account_label = descriptor.label
        if "travis" in account_label.lower():
            account_label = "Travis"
        elif "christie" in account_label.lower():
            account_label = "Christie"

        action = entry.action.lower()
        cmd = [
            sys.executable,
            str(script_path),
            action,
            "--file",
            str(descriptor.path),
            "--account",
            account_label,
            "--symbol",
            entry.ticker.upper(),
            "--contracts",
            str(entry.contracts),
            "--strike",
            str(entry.strike),
            "--expiry",
            entry.expiry.isoformat(),
            "--date",
            entry.trade_datetime.date().isoformat(),
            "--time",
            entry.trade_datetime.strftime("%H:%M"),
            "--side",
            entry.side or "Call",
        ]

        if action == "open":
            cmd.extend(["--premium", str(entry.premium)])
            if entry.underlying is not None:
                cmd.extend(["--underlying", str(entry.underlying)])
                logger.info(f"  Open position with underlying price: ${entry.underlying}")
            else:
                cmd.append("--auto-price")
                logger.info("  Open position using auto-price feature")
        else:
            cmd.extend(["--buyback", str(entry.premium)])
            if entry.underlying is not None:
                cmd.extend(["--underlying-close", str(entry.underlying)])
                logger.info(f"  Close position with underlying price: ${entry.underlying}")
            else:
                cmd.append("--auto-price")
                logger.info(f"  Close position using auto-price feature")

        if entry.condition:
            cmd.extend(["--condition", entry.condition])

        logger.debug(f"Command: {' '.join(cmd)}")
        
        try:
            logger.info(f"Executing ledger command for {entry.ticker} (cwd={journal_dir})...")
            logger.debug(f"Environment keys: {list(os.environ.keys())}")
            # Run subprocess with a timeout to avoid indefinite hangs; capture output even on failure.
            completed = subprocess.run(
                cmd,
                check=False,
                cwd=journal_dir,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                timeout=300,
            )

            logger.info(f"Ledger process exit code: {completed.returncode} for {entry.ticker}")
            if completed.stdout:
                logger.debug(f"STDOUT:\n{completed.stdout}")
            if completed.stderr:
                logger.debug(f"STDERR:\n{completed.stderr}")

            if completed.returncode != 0:
                logger.error(f"Ledger CLI failed for {entry.ticker} with returncode {completed.returncode}")
                raise RuntimeError(
                    f"Ledger CLI failed for {entry.ticker}: returncode={completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
                )
            logger.info(f"Successfully processed {entry.ticker}")

        except subprocess.TimeoutExpired as exc:
            logger.error(f"Ledger command timed out after {exc.timeout} seconds for {entry.ticker}")
            # Attempt to capture partial output
            stdout = getattr(exc, 'stdout', None) or ''
            stderr = getattr(exc, 'stderr', None) or ''
            logger.error(f"Partial STDOUT:\n{stdout}")
            logger.error(f"Partial STDERR:\n{stderr}")
            raise RuntimeError(f"Ledger CLI timed out for {entry.ticker} after {exc.timeout} seconds") from exc
        except Exception as exc:
            # Log unexpected exceptions and re-raise
            logger.exception(f"Unexpected error running ledger CLI for {entry.ticker}: {exc}")
            raise

        # Append the newly added row from the ledger for confirmation
        updated_rows = excel_loader.get_ledger_rows(entry.account)
        if updated_rows:
            results.append(LedgerRow(**updated_rows[-1]))
            logger.info(f"Ledger entry confirmed for {entry.ticker}")

    return results


def append_ledger_entries_background(entries: List[LedgerEntryCreate]) -> None:
    """Background wrapper for `append_ledger_entries` that logs start, success, and errors.

    This function is safe to schedule with FastAPI BackgroundTasks so failures
    are recorded in the application logs for diagnosis.
    """
    try:
        logger.info(f"Background ledger task starting for {len(entries) if entries is not None else 0} entries")
        results = append_ledger_entries(entries)
        logger.info(f"Background ledger task completed: appended {len(results) if results is not None else 0} rows")
    except Exception as exc:
        logger.exception(f"Background ledger task failed: {exc}")


def update_ledger_entry(entry: LedgerUpdate) -> LedgerRow:
    """Update an existing ledger row by row_number."""
    updated = excel_loader.update_ledger_row(entry.account, entry.row_number, entry.model_dump())
    return LedgerRow(**updated)

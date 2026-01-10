#!/usr/bin/env python3
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "cfm_journal" / "data"
ALPHA_CACHE_DIR = ROOT / "cfm_journal" / "alpha_cache"
BASE_LEGS_PATH = DATA_DIR / "base_legs.csv"
BASE_POSITIONS_PATH = DATA_DIR / "base_positions.csv"
OLD_BASE_LEG_FIELDS = [
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
]
NEW_BASE_LEG_FIELDS = OLD_BASE_LEG_FIELDS + ["underlying_price"]


def _load_positions() -> Dict[str, str]:
    if not BASE_POSITIONS_PATH.exists():
        raise FileNotFoundError(f"Missing {BASE_POSITIONS_PATH}")
    mapping: Dict[str, str] = {}
    with BASE_POSITIONS_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = (row.get("position_id") or "").strip()
            sym = (row.get("symbol") or "").strip().upper()
            if pid and sym:
                mapping[pid] = sym
    return mapping


def _parse_qty(value: Optional[str]) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _load_alpha_cache(symbol: str, month_str: str) -> Optional[dict]:
    path = ALPHA_CACHE_DIR / f"{symbol}_{month_str}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        data = __import__("json").load(f)
    if "Time Series (1min)" in data:
        return data["Time Series (1min)"]
    return data


def _nearest_minute_price(time_series: dict, target: datetime) -> Tuple[Optional[float], Optional[str]]:
    target_date = target.strftime("%Y-%m-%d")
    target_key = target.strftime("%Y-%m-%d %H:%M:00")
    daily = {k: v for k, v in time_series.items() if k.startswith(target_date)}
    if not daily:
        return _nearest_any_day_price(time_series, target)
    if target_key in daily:
        minute_data = daily[target_key]
        return _mid_price(minute_data), target_key
    closest_key = None
    closest_diff = None
    for key in daily.keys():
        try:
            dt = datetime.strptime(key, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        diff = abs((dt - target).total_seconds())
        if closest_diff is None or diff < closest_diff:
            closest_diff = diff
            closest_key = key
    if closest_key is None:
        return _nearest_any_day_price(time_series, target)
    minute_data = daily[closest_key]
    return _mid_price(minute_data), closest_key


def _nearest_any_day_price(time_series: dict, target: datetime) -> Tuple[Optional[float], Optional[str]]:
    closest_key = None
    closest_diff = None
    for key in time_series.keys():
        try:
            dt = datetime.strptime(key, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        diff = abs((dt - target).total_seconds())
        if closest_diff is None or diff < closest_diff:
            closest_diff = diff
            closest_key = key
    if closest_key is None:
        return None, None
    minute_data = time_series[closest_key]
    return _mid_price(minute_data), closest_key


def _mid_price(minute_data: dict) -> Optional[float]:
    try:
        high_price = float(minute_data["2. high"])
        low_price = float(minute_data["3. low"])
    except (KeyError, ValueError, TypeError):
        return None
    return round((high_price + low_price) / 2, 2)


def _target_datetime(row: dict) -> datetime:
    date_str = (row.get("date") or "").strip()
    time_str = (row.get("time") or "16:00").strip()
    if len(time_str) == 5:
        time_str = f"{time_str}:00"
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")


def _group_open_leg_ids(rows: Iterable[dict]) -> set[str]:
    grouped: Dict[str, Dict[str, float]] = {}
    for row in rows:
        leg_id = (row.get("base_leg_id") or "").strip()
        if not leg_id:
            continue
        tag = (row.get("tag") or "").strip().upper()
        if leg_id not in grouped:
            grouped[leg_id] = {"open": 0.0, "mark": 0.0}
        if tag == "OPEN":
            grouped[leg_id]["open"] += 1
        elif tag == "MARK":
            grouped[leg_id]["mark"] += 1
    return {leg_id for leg_id, info in grouped.items() if info["open"] > 0}


def _normalize_header_and_rows() -> tuple[list[str], list[dict], bool]:
    with BASE_LEGS_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows_raw = list(reader)
    if not rows_raw:
        return NEW_BASE_LEG_FIELDS, [], False
    header = [h.strip() for h in rows_raw[0]]
    data_rows = rows_raw[1:]

    needs_rewrite = header != NEW_BASE_LEG_FIELDS
    normalized_rows: list[dict] = []

    for row in data_rows:
        if not row:
            continue
        if needs_rewrite:
            # Treat existing rows as if they followed the old header order.
            values = row[: len(OLD_BASE_LEG_FIELDS)]
            record = dict(zip(OLD_BASE_LEG_FIELDS, values))
            record["underlying_price"] = ""
        else:
            record = {col: (row[idx] if idx < len(row) else "") for idx, col in enumerate(NEW_BASE_LEG_FIELDS)}
        normalized_rows.append(record)

    return NEW_BASE_LEG_FIELDS, normalized_rows, needs_rewrite


def main() -> None:
    if not BASE_LEGS_PATH.exists():
        raise FileNotFoundError(f"Missing {BASE_LEGS_PATH}")

    positions = _load_positions()
    fieldnames, rows, needs_rewrite = _normalize_header_and_rows()

    open_ids = _group_open_leg_ids(rows)
    mark_ids = {
        (row.get("base_leg_id") or "").strip()
        for row in rows
        if (row.get("tag") or "").strip().upper() == "MARK"
    }
    updated = 0
    skipped = 0
    missing_cache = 0

    for row in rows:
        leg_id = (row.get("base_leg_id") or "").strip()
        if leg_id not in open_ids:
            continue
        tag = (row.get("tag") or "").strip().upper()
        if tag not in {"OPEN", "MARK"}:
            continue
        if tag == "MARK" and leg_id not in mark_ids:
            continue
        if (row.get("underlying_price") or "").strip():
            skipped += 1
            continue
        position_id = (row.get("position_id") or "").strip()
        symbol = positions.get(position_id)
        if not symbol:
            skipped += 1
            continue
        dt = _target_datetime(row)
        month_str = f"{dt.year}-{dt.month:02d}"
        series = _load_alpha_cache(symbol, month_str)
        if not series:
            missing_cache += 1
            continue
        price, matched = _nearest_minute_price(series, dt)
        if price is None:
            skipped += 1
            continue
        row["underlying_price"] = f"{price:.2f}"
        updated += 1

    if updated or needs_rewrite:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BASE_LEGS_PATH.with_suffix(f".csv.bak-{timestamp}")
        BASE_LEGS_PATH.replace(backup)
        with BASE_LEGS_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        if needs_rewrite and not updated:
            print(f"Rewrote header order. Backup saved to {backup}")
        else:
            print(f"Updated {updated} rows. Backup saved to {backup}")
    else:
        print("No rows updated.")
    print(f"Skipped: {skipped} | Missing cache: {missing_cache}")


if __name__ == "__main__":
    main()

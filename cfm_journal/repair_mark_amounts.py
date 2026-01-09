#!/usr/bin/env python3
import csv
import datetime as dt
import os
import shutil
import sys


def to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except Exception:
        return None


def normalize_tag(value):
    return str(value or "").strip().upper()


def main() -> int:
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = os.path.join(os.path.dirname(__file__), "data", "base_legs.csv")

    if not os.path.exists(csv_path):
        print(f"Missing file: {csv_path}", file=sys.stderr)
        return 1

    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    last_qty = {}
    last_price = {}
    last_instr = {}
    for row in rows:
        leg_id = str(row.get("base_leg_id") or "").strip()
        if not leg_id:
            continue
        qty = to_float(row.get("quantity"))
        price = to_float(row.get("price"))
        instr = str(row.get("instrument_type") or "").strip().upper()
        if qty is not None:
            last_qty[leg_id] = qty
        if price is not None:
            last_price[leg_id] = price
        if instr:
            last_instr[leg_id] = instr

    updated = 0
    skipped = 0
    for row in rows:
        tag = normalize_tag(row.get("tag"))
        if tag != "MARK":
            continue
        leg_id = str(row.get("base_leg_id") or "").strip()
        if not leg_id:
            skipped += 1
            continue
        qty = to_float(row.get("quantity"))
        price = to_float(row.get("price"))
        if qty is None:
            qty = last_qty.get(leg_id)
        if price is None:
            price = last_price.get(leg_id)
        if qty is None or price is None:
            skipped += 1
            continue
        amount = abs(qty * price * 100.0)
        row["amount"] = str(round(amount, 2))
        updated += 1

    if updated == 0:
        print("No MARK rows updated.")
        return 0

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{csv_path}.bak-{timestamp}"
    shutil.copy2(csv_path, backup_path)

    tmp_path = f"{csv_path}.tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, csv_path)

    print(f"Updated MARK rows: {updated} (skipped {skipped})")
    print(f"Backup saved: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline adapter for authorized DTS conversion-order exports; no API calls.

Source: https://dtcc-da.com/api/tokenization-service/api-reference-guide/content
Guide published 2026-10-14, checked 2026-11-17: OrderStatus is case-sensitive
Processing / Completed / Failed. Activity status Confirmed and an async operation
Completed are not evidence that a conversion order completed. HTTP 202 only
acknowledges submission. The guide documents updatedAt, not a completion-time
field. confirmed_completed_at is an OPTIONAL, separately verified audit timestamp
supplied by the data owner; this adapter never substitutes updatedAt for it.

Observation cohort: orders created in [window_start, window_end). Only snapshots
updated before window_end enter the as-of state. Snapshots cannot reconstruct a
state that was not exported. Latest snapshots are deduplicated by order identifier;
conflicting latest snapshots are quarantined. Outcomes are sample operating
metrics, not internal protective buffers or calibrated risk scores.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping

SOURCE_URL = "https://dtcc-da.com/api/tokenization-service/api-reference-guide/content"
SOURCE_CHECKED_ON = "2026-11-17"
CANONICAL_FIELDS = (
    "order_id", "created_at", "updated_at", "status", "quantity", "network",
    "confirmed_completed_at",
)
ORDER_STATUS = {"Processing": "processing", "Completed": "completed", "Failed": "failed"}
ALIASES = {"order_id": "orderId", "created_at": "createdAt", "updated_at": "updatedAt"}


def _timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: timezone-aware ISO timestamp required")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}: invalid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}: timezone required; local time is not assumed")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def normalize_order(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map canonical fields or documented order-detail aliases; reject other feeds.

    Raw API order detail can carry fromWallet/toWallet. Its one non-DTC_Classic
    network is retained when unambiguous; missing/ambiguous networks stay null.
    Async operations have resourceId/id rather than orderId and are rejected.
    """
    result = {field: row.get(field, row.get(ALIASES.get(field, ""))) for field in CANONICAL_FIELDS}
    order_id = result["order_id"]
    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("order_id/orderId required; async-operation IDs are not order IDs")
    result["order_id"] = order_id.strip()
    created = _timestamp(result["created_at"], field="created_at")
    updated = _timestamp(result["updated_at"], field="updated_at")
    if updated < created:
        raise ValueError("updated_at precedes created_at")
    result["created_at"], result["updated_at"] = _iso(created), _iso(updated)
    status = result["status"]
    result["status"] = status if isinstance(status, str) else ("" if status is None else str(status))
    quantity = result["quantity"]
    if quantity in (None, ""):
        result["quantity"] = None
    else:
        if isinstance(quantity, bool):
            raise ValueError("quantity must be a non-negative finite number")
        try:
            quantity = float(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("quantity must be a non-negative finite number") from exc
        if not math.isfinite(quantity) or quantity < 0:
            raise ValueError("quantity must be a non-negative finite number")
        result["quantity"] = quantity
    network = result["network"]
    if not network:
        networks = {
            wallet["network"] for key in ("fromWallet", "toWallet")
            if isinstance(wallet := row.get(key), Mapping)
            and isinstance(wallet.get("network"), str)
            and wallet["network"] not in ("", "DTC_Classic")
        }
        network = next(iter(networks)) if len(networks) == 1 else None
    result["network"] = str(network) if network else None
    result["confirmed_completed_at"] = result["confirmed_completed_at"] or None
    return result


def load_orders(path: str | Path) -> list[dict[str, Any]]:
    """Read a local CSV or flat JSON array; do not accept URLs or API envelopes."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return []
            required = set(CANONICAL_FIELDS) - {"confirmed_completed_at"}
            if not required.issubset(reader.fieldnames):
                raise ValueError("CSV must contain canonical columns: " + ", ".join(sorted(required)))
            return list(reader)
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8-sig") as handle:
            rows = json.load(handle)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("JSON must be a flat array of conversion-order records")
        return rows
    raise ValueError("Only local .csv and .json exports are supported")


def summarize_orders(
    records: Iterable[Mapping[str, Any]], *,
    window_start: str | None = None, window_end: str | None = None,
) -> dict[str, Any]:
    start = _timestamp(window_start, field="window_start") if window_start else None
    end = _timestamp(window_end, field="window_end") if window_end else None
    if start and end and start >= end:
        raise ValueError("window_start must precede window_end")
    rows = list(records)
    result: dict[str, Any] = {
        "availability": "awaiting_authorized_data",
        "metric_kind": "observed_operating_outcomes_not_internal_buffer",
        "source_url": SOURCE_URL,
        "source_checked_on": SOURCE_CHECKED_ON,
        "window": {"start_inclusive": _iso(start), "end_exclusive": _iso(end),
                   "cohort": "created_at", "state_cutoff": "updated_at < end_exclusive"},
        "scope": "provided_authorized_export_only; completeness_not_established",
        "input_rows": len(rows), "invalid_rows": 0, "excluded_rows": 0,
        "duplicate_rows_removed": 0, "conflicting_order_ids": [],
        "data_quality_issues": [], "orders": [], "unknown_status_counts": {},
        "metrics": {key: None for key in (
            "order_count", "completed_count", "failed_count", "processing_count",
            "unknown_status_count", "completed_share_of_observed_orders",
            "failed_share_of_observed_orders", "terminal_failure_rate",
            "completed_duration_sample_count", "mean_completed_duration_seconds",
            "median_completed_duration_seconds", "observed_completion_over_15m_count",
        )},
        "duration_policy": "Completed plus separately verified confirmed_completed_at only; updated_at is never completion time",
        "target_policy": "15 minutes is a published service target, not an established SLA or internal V",
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        try:
            order = normalize_order(row)
        except (ValueError, TypeError, AttributeError) as exc:
            result["invalid_rows"] += 1
            result["data_quality_issues"].append({"row": index + 1, "issue": str(exc)})
            continue
        created = _timestamp(order["created_at"], field="created_at")
        updated = _timestamp(order["updated_at"], field="updated_at")
        if (start and created < start) or (end and (created >= end or updated >= end)):
            result["excluded_rows"] += 1
            continue
        grouped.setdefault(order["order_id"], []).append(order)
    for order_id, snapshots in sorted(grouped.items()):
        # Canonical timestamps are UTC, so timestamp comparison is unambiguous.
        latest_time = max(_timestamp(row["updated_at"], field="updated_at") for row in snapshots)
        latest = [row for row in snapshots if _timestamp(row["updated_at"], field="updated_at") == latest_time]
        fingerprints = {json.dumps(row, sort_keys=True) for row in latest}
        result["duplicate_rows_removed"] += len(snapshots) - 1
        if len(fingerprints) != 1 or len({row["created_at"] for row in snapshots}) != 1:
            result["conflicting_order_ids"].append(order_id)
            continue
        result["orders"].append(latest[0])
    if not result["orders"]:
        if rows:
            result["availability"] = "no_usable_orders_in_window"
        return result
    result["availability"] = "authorized_export_loaded"
    counts = {"completed": 0, "failed": 0, "processing": 0, "unknown": 0}
    durations = []
    for order in result["orders"]:
        category = ORDER_STATUS.get(order["status"], "unknown")
        counts[category] += 1
        if category == "unknown":
            unknown = result["unknown_status_counts"]
            unknown[order["status"]] = unknown.get(order["status"], 0) + 1
        if order["confirmed_completed_at"] is None:
            continue
        try:
            completed = _timestamp(order["confirmed_completed_at"], field="confirmed_completed_at")
            created = _timestamp(order["created_at"], field="created_at")
            updated = _timestamp(order["updated_at"], field="updated_at")
            if category != "completed" or completed < created or completed > updated or (end and completed >= end):
                raise ValueError("completion evidence inconsistent with order state/timestamps")
            durations.append((completed - created).total_seconds())
        except ValueError as exc:
            result["data_quality_issues"].append({"order_id": order["order_id"], "issue": str(exc)})
    n = len(result["orders"])
    terminal = counts["completed"] + counts["failed"]
    result["metrics"].update({
        "order_count": n, "completed_count": counts["completed"], "failed_count": counts["failed"],
        "processing_count": counts["processing"], "unknown_status_count": counts["unknown"],
        "completed_share_of_observed_orders": counts["completed"] / n,
        "failed_share_of_observed_orders": counts["failed"] / n,
        "terminal_failure_rate": counts["failed"] / terminal if terminal else None,
        "completed_duration_sample_count": len(durations),
        "mean_completed_duration_seconds": statistics.mean(durations) if durations else None,
        "median_completed_duration_seconds": statistics.median(durations) if durations else None,
        "observed_completion_over_15m_count": sum(value > 900 for value in durations) if durations else None,
    })
    return result


def analyze_authorized_orders(
    input_path: str | Path | None = None, *,
    window_start: str | None = None, window_end: str | None = None,
) -> dict[str, Any]:
    return summarize_orders(load_orders(input_path) if input_path else [], window_start=window_start, window_end=window_end)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Authorized local CSV/JSON; omitted means awaiting data")
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(analyze_authorized_orders(args.input, window_start=args.window_start, window_end=args.window_end), indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()

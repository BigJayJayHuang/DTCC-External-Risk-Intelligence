#!/usr/bin/env python3
"""Check a Risk Horizon output file before committing it.

Usage: python3 docs/data/validate_output.py docs/data/risk_output.json
Exit code 0 = OK, 1 = errors found. Standard library only.
"""
import json
import sys
from datetime import datetime

LINES = {"FICC", "ECS", "RDS", "WIS", "ITP", "Asset Services", "DAS", "DDA", "Data Services", "Consulting"}
FAMILIES = {"Credit", "Liquidity", "Market", "Operational", "Cyber", "Regulatory", "Strategic"}


def is_date(s):
    try:
        datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def score_ok(v, allow_none=False):
    if v is None:
        return allow_none
    return isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5


def main(path):
    errors, warnings = [], []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    snaps = data.get("snapshots", [])
    snap_ids = set()
    for n, s in enumerate(snaps):
        if not s.get("id"):
            errors.append(f"snapshots[{n}]: missing id")
        elif not is_date(s.get("date", s["id"])):
            errors.append(f"snapshots[{n}]: date is not ISO (YYYY-MM-DD)")
        snap_ids.add(s.get("id"))

    seen = set()
    for n, it in enumerate(data.get("items", [])):
        tag = f"items[{n}] ({it.get('id', '?')})"
        for k in ("id", "snapshot", "business_line", "title", "risk_family"):
            if not it.get(k):
                errors.append(f"{tag}: missing {k}")
        if it.get("snapshot") and it["snapshot"] not in snap_ids:
            warnings.append(f"{tag}: snapshot {it['snapshot']} not listed in snapshots (page will add it)")
        if it.get("business_line") and it["business_line"] not in LINES:
            errors.append(f"{tag}: business_line '{it['business_line']}' is not one of the 10 lines")
        if it.get("risk_family") and it["risk_family"] not in FAMILIES:
            warnings.append(f"{tag}: risk_family '{it['risk_family']}' is not a standard family")
        if not score_ok(it.get("shock")):
            errors.append(f"{tag}: shock must be an integer 1-5")
        if not score_ok(it.get("vulnerability"), allow_none=True):
            errors.append(f"{tag}: vulnerability must be an integer 1-5 or null (never 0)")
        if it.get("updated_at") and not is_date(it["updated_at"]):
            errors.append(f"{tag}: updated_at is not ISO 8601")
        key = (it.get("id"), it.get("snapshot"))
        if key in seen:
            errors.append(f"{tag}: duplicate id within snapshot {it.get('snapshot')}")
        seen.add(key)
        tr = it.get("transmission")
        if tr is not None and not all(k in tr for k in ("event", "mechanism", "dtcc_process")):
            warnings.append(f"{tag}: transmission should have event, mechanism, dtcc_process")

    for line in data.get("lines", {}):
        if line not in LINES:
            errors.append(f"lines: '{line}' is not one of the 10 lines")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(data.get('items', []))} items, {len(snaps)} snapshots: "
          f"{'OK' if not errors else str(len(errors)) + ' error(s)'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/risk_output.json"))

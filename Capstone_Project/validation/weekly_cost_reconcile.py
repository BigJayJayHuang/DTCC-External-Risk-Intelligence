"""Record an unresolved weekly classifier cost reservation as charged (upper-bound reconciliation).

    python -m validation.weekly_cost_reconcile --summary data/events/weekly/<Monday>/<run>/classifier_runs/<id>/summary.json \
        --reconciled-by "Name" --reason "why the exact bill cannot be confirmed"

The classifier receipt (summary.json) is never edited. One row is appended to data/events/weekly/cost_reconciliations.csv
with the receipt's sha256 and the whole reserved amount recorded as spent; weekly_news_run.unresolved_reservations()
then treats that reservation as resolved. If the receipt changes later, the row no longer matches and the guard blocks
again. No model calls, no AWS.
"""
import argparse, csv, hashlib, json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from . import weekly_news_run as W


def reconcile(summary: Path, reconciled_by: str, reason: str, ledger: Path = W.RECONCILIATIONS, now: str | None = None) -> dict:
    summary = Path(summary)
    value = json.loads(summary.read_text())
    if value.get("status") == "running":
        raise SystemExit("The run is still marked running; reconcile only a stopped run")
    reserve = max(Decimal(str(value.get("unreported_cost_reserve_usd", "0"))), Decimal(str(value.get("inflight_reservation_usd", "0"))))
    if reserve <= 0:
        raise SystemExit(f"No unresolved reservation in {summary}")
    if not reconciled_by.strip() or not reason.strip():
        raise SystemExit("--reconciled-by and --reason are required")
    key, digest = W.receipt_key(summary), hashlib.sha256(summary.read_bytes()).hexdigest()
    if (key, digest) in W.load_reconciliations(ledger):
        raise SystemExit(f"Already reconciled: {key}")
    row = {"summary_file": key, "summary_sha256": digest, "reserved_usd": str(reserve), "recorded_charge_usd": str(reserve),
           "basis": "upper_bound_recorded_as_charged", "reconciled_by": reconciled_by.strip(),
           "reconciled_utc": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "reason": reason.strip()}
    new = not Path(ledger).exists()
    Path(ledger).parent.mkdir(parents=True, exist_ok=True)
    with Path(ledger).open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=W.RECONCILIATION_FIELDS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--reconciled-by", required=True)
    p.add_argument("--reason", required=True)
    a = p.parse_args(argv)
    print(json.dumps(reconcile(a.summary, a.reconciled_by, a.reason), indent=2))


if __name__ == "__main__":
    main()

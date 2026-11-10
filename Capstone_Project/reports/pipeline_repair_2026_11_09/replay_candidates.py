"""Reproduce the repaired candidate merge from frozen public metadata; no network/model calls."""
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))
from validation import publisher_feeds as P
from validation import google_news as G


def main():
    official_path = HERE / "data/official_news_in_window.csv"
    google_path = HERE / "data/google_candidates.csv"
    start, end = date(2026, 11, 2), date(2026, 11, 8)
    official, dropped, audit = P.official_rows(official_path, G.load_queries(), start, end)
    for row in official:
        row.update(content_scope="summary" if row.get("summary") else "headline_only",
                   fulltext_status="not_requested_offline_replay")
    with google_path.open(encoding="utf-8", newline="") as handle:
        google = list(csv.DictReader(handle))
    rows, duplicates = P.dedupe(official + google, json.loads(P.CONFIG.read_text())["title_similarity_threshold"])
    rows.sort(key=lambda r: ((r.get("publication_date") or r.get("published_at_utc") or "")[:10], r["document_id"]))
    dates = [(r.get("publication_date") or r.get("published_at_utc") or "")[:10] for r in rows]
    assert all(start.isoformat() <= when <= end.isoformat() for when in dates)
    queue = HERE / "data/candidate_review_queue.csv"
    with queue.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=P.FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    exclusions = HERE / "data/official_keyword_exclusions.csv"
    G.write_csv(exclusions, dropped, ["document_id", "source_id", "publication_date", "title", "url", "reason"])
    receipt = {
        "mode": "offline_replay_of_real_collected_metadata", "window": [start.isoformat(), end.isoformat()],
        "new_network_requests": 0, "aws_calls": 0, "accepted_events": 0, "scores_recomputed": False,
        "official": {k: v for k, v in audit.items() if k != "scope_exclusions"},
        "google_candidates": len(google), "duplicates_merged": duplicates, "review_candidates": len(rows),
        "scopes": dict(sorted(Counter(r["content_scope"] for r in rows).items())),
        "source_counts": dict(sorted(Counter(r["source_id"] for r in rows).items())),
        "publication_range": [min(dates), max(dates)],
        "interpretation": "Broad keyword hits are review candidates, not confirmed relevance, risk events or final card assignments.",
        "hashes": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [official_path, google_path, queue, exclusions]},
        "queries_sha256": hashlib.sha256(G.QUERIES.read_bytes()).hexdigest(),
        "publisher_config_sha256": hashlib.sha256(P.CONFIG.read_bytes()).hexdigest(),
    }
    (HERE / "evidence/candidate_replay.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return receipt


if __name__ == "__main__":
    main()

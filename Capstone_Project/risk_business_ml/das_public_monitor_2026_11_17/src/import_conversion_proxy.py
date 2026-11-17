"""Import only labelled public DAS-05 research proxies; never import scenarios."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from conversion_window_proxy import ROOT, POLICY_ID
from import_monitor_db import import_into_database, validate_existing

METRIC_IDS = {'das05_conversion_access_hourly', 'das05_conversion_access_daily_0800_et',
              'das05_conversion_access_snapshot'}


def validate_payload(payload):
    rows = payload.get('metrics')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Expected nonempty public research proxy metrics')
    for row in rows:
        if row.get('policy_id') != POLICY_ID or row.get('metric_id') not in METRIC_IDS:
            raise ValueError('Unexpected policy or metric')
        if (row.get('measurement_type') != 'PUBLIC_RULE_DERIVED_WEEKLY_BASELINE'
                or row.get('state') != 'RESEARCH_BASELINE_ONLY'
                or row.get('internal_V') is not None or row.get('accepted_proxy_V') is not None
                or row.get('risk_score') is not None or row.get('operating_telemetry') is not False
                or row.get('quarterly_internal_v_replacement') is not False
                or any(k in row for k in ('scenario_id', 'assumed_shock_score', 'illustrative_priority_index'))):
            raise ValueError('Research proxy import cannot contain accepted V, risk scores, or scenarios')
    if any(payload.get(key) for key in ('findings', 'facts', 'scope', 'networks', 'deadlines')):
        raise ValueError('Only proxy metrics and source manifests may be imported')


def fingerprint_unrelated(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        digest = hashlib.sha256()
        count = 0
        for row in c.execute('SELECT dataset_id,record_key,payload,content_hash FROM records '
                "WHERE COALESCE(json_extract(payload,'$.policy_id'),'') != ? "
                'ORDER BY dataset_id,record_key', (POLICY_ID,)):
            digest.update(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode())
            digest.update(b'\n')
            count += 1
        return dict(records=count, sha256=digest.hexdigest())
    finally:
        c.close()


def import_proxy(target_db=None):
    output = ROOT / 'proxy_v/results'
    payload = json.loads((output / 'database_payload.json').read_text())
    validate_payload(payload)
    portable = ROOT / 'proxy_v/data/das05_proxy.sqlite3'
    if target_db is not None:
        target_db = Path(target_db).resolve()
        if target_db == portable.resolve():
            raise ValueError('Existing project target must differ from the portable proxy database')
        validate_existing(target_db)
        before = fingerprint_unrelated(target_db)
        master = target_db.with_suffix(target_db.suffix + '.gz')
        master_sha = hashlib.sha256(master.read_bytes()).hexdigest() if master.exists() else None
    portable.parent.mkdir(parents=True, exist_ok=True)
    receipt = dict(policy_id=POLICY_ID, scope='Research proxy metrics only; scenarios excluded',
                   portable=import_into_database(ROOT, payload, portable, make_snapshot=True),
                   production_scoring_modified=False, official_event_register_modified=False,
                   paid_api_calls=0)
    if target_db is not None:
        receipt['project_database'] = import_into_database(ROOT, payload, target_db, require_existing=True)
        after = fingerprint_unrelated(target_db)
        receipt['unrelated_record_preservation'] = dict(before=before, after=after, unchanged=before == after)
        after_master = hashlib.sha256(master.read_bytes()).hexdigest() if master.exists() else None
        receipt['master_snapshot_unchanged'] = master_sha == after_master
        if before != after or master_sha != after_master:
            raise RuntimeError('Unexpected change outside the intended proxy records')
    (output / 'database_import_receipt.json').write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-db', type=Path, help='Optional existing local project database')
    args = parser.parse_args()
    print(json.dumps(import_proxy(args.target_db), ensure_ascii=False, indent=2))

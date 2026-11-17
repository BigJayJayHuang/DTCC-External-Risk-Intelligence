"""Import a public DAS monitor without changing unrelated project datasets.

No network/API calls. The portable snapshot excludes raw source bodies. An optional
existing project database receives only the seven das_monitor_* datasets and their
disabled, URL-deduplicated sources; its master snapshot is never rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
DATASETS = {
    'sources': ('source_id', 'Official public DAS monitor source inventory', 'source document'),
    'findings': ('finding_id', 'Public DAS monitor findings and limitations', 'finding'),
    'facts': ('fact_id', 'Source-backed public DAS facts', 'fact'),
    'scope': ('card_id', 'DAS chain scope and implementation status', 'card'),
    'networks': ('network_id', 'DAS network relevance and deployment evidence', 'network'),
    'metrics': ('metric_id', 'Public DAS monitor metrics; not inferred internal V', 'metric and observation period'),
    'deadlines': ('deadline_id', 'Source-backed DAS dates and deadline limitations', 'deadline'),
}
RETRIEVED = {'retrieved', 'downloaded', 'success', 'available', 'ok'}
INTERPRETATION = ('Public evidence monitor, not measured DAS internal vulnerability or an '
                  'empirically validated risk score. Missing values are not zero.')


def database_module():
    spec = importlib.util.spec_from_file_location('das_monitor_shared_db', PROJECT / 'capstone_database/db.py')
    if spec is None or spec.loader is None:
        raise ImportError('Shared project database module unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be a nonempty string')
    return value


def source_key(url):
    return 'das_monitor_' + hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]


def evidence_bytes(root, row):
    relative = row.get('raw_file')
    if not relative:
        if row.get('status', '').lower() in RETRIEVED:
            raise ValueError('Retrieved source lacks raw_file: ' + row['source_id'])
        return None
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('raw_file must be a relative evidence path')
    allowed = (root / 'evidence').resolve()
    raw = (root / relative).resolve(strict=True)
    try:
        raw.relative_to(allowed)
    except ValueError as exc:
        raise ValueError('raw_file escapes evidence directory') from exc
    if not raw.is_file():
        raise ValueError('raw_file is not a regular file')
    body = raw.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    expected = row.get('raw_sha256') or row.get('sha256')
    if expected and expected != digest:
        raise ValueError('Raw evidence SHA-256 mismatch: ' + row['source_id'])
    return body


def referenced_sources(row):
    result = []
    if row.get('source_id'):
        result.append(nonempty(row['source_id'], 'source_id'))
    ids = row.get('source_ids', [])
    if not isinstance(ids, list):
        raise ValueError('source_ids must be a list')
    for value in ids:
        sid = nonempty(value, 'source_ids entry')
        if sid not in result:
            result.append(sid)
    return result


def prepare_rows(root, monitor, db):
    """Validate every identity, reference, and raw file before database mutation."""
    if not isinstance(monitor, dict):
        raise ValueError('Monitor must be a JSON object')
    source_rows = monitor.get('sources')
    if not isinstance(source_rows, list) or not source_rows:
        raise ValueError('sources must contain at least one manifest row')
    sources, bodies = {}, {}
    for row in source_rows:
        if not isinstance(row, dict):
            raise ValueError('Source manifest rows must be objects')
        sid = nonempty(row.get('source_id'), 'source_id')
        url = nonempty(row.get('url'), 'source url')
        if not url.startswith('https://'):
            raise ValueError('Source URL must use HTTPS')
        if sid in sources:
            raise ValueError('Duplicate source_id: ' + sid)
        nonempty(row.get('status'), 'source status')
        sources[sid] = dict(row)
        body = evidence_bytes(root, row)
        if body is not None:
            bodies[sid] = body
            sources[sid]['raw_sha256'] = db.sha(body)
        sources[sid]['registered_source_id'] = source_key(url)

    records, identities = [], {}
    for category, (id_field, _, _) in DATASETS.items():
        rows = list(sources.values()) if category == 'sources' else monitor.get(category, [])
        if not isinstance(rows, list):
            raise ValueError(category + ' must be a list')
        for incoming in rows:
            if not isinstance(incoming, dict):
                raise ValueError(category + ' rows must be objects')
            row = dict(incoming)
            identifier = nonempty(row.get(id_field), category + '.' + id_field)
            refs = [identifier] if category == 'sources' else referenced_sources(row)
            if category in {'findings', 'facts', 'deadlines'} and not refs:
                raise ValueError(category + ' requires source_id or source_ids')
            for sid in refs:
                if sid not in sources:
                    raise ValueError('Unknown source reference: ' + sid)
            row.setdefault('business_line', 'DAS')
            if row['business_line'] != 'DAS':
                raise ValueError('Only DAS rows may enter monitor datasets')
            key = identifier
            if category == 'metrics':
                # A metric series retains every dated observation on future imports.
                period = next((row.get(k) for k in ('observation_date', 'quarter',
                    'reference_as_of_date', 'as_of_date', 'date') if row.get(k)), None)
                if period is not None:
                    key = db.dumps([identifier, str(period)])
            dataset = 'das_monitor_' + category
            identity = (dataset, key)
            canonical = db.dumps(row)  # Also rejects NaN/infinite values.
            if identity in identities:
                if identities[identity] != canonical:
                    raise ValueError('Conflicting duplicate record identity: ' + str(identity))
                continue
            identities[identity] = canonical
            records.append((dataset, key, row, refs))
    return sources, bodies, records


def validate_existing(path):
    if not path.is_file():
        raise FileNotFoundError('Target project database must already exist: ' + str(path))
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        required = {'records', 'record_versions', 'record_evidence', 'evidence_blobs',
                    'datasets', 'sources', 'source_business', 'business_lines', 'runs'}
        found = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= found:
            raise ValueError('Target lacks existing project database schema')
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Existing target failed integrity check')
        if list(connection.execute('PRAGMA foreign_key_check')):
            raise ValueError('Existing target has foreign-key errors')
    finally:
        connection.close()


def import_into_database(root, monitor, path, *, make_snapshot=False, require_existing=False):
    root, path = Path(root).resolve(), Path(path).resolve()
    db = database_module()
    sources, bodies, records = prepare_rows(root, monitor, db)
    if require_existing:
        validate_existing(path)
    with db.writer_lock(path):
        c = db.connect(path)
        try:
            if make_snapshot and c.execute(
                    "SELECT 1 FROM records WHERE dataset_id NOT LIKE 'das_monitor_%' LIMIT 1").fetchone():
                raise ValueError('Portable monitor database must not contain unrelated datasets')
            changes, counts = Counter(), Counter()
            run_id = db.now() + '_' + uuid.uuid4().hex[:8]
            c.execute('BEGIN IMMEDIATE')
            try:
                # All metadata and evidence writes share the record transaction.
                c.execute('INSERT INTO runs VALUES(?,?,NULL,?,?,NULL)',
                          (run_id, db.now(), 'das_public_monitor_import', 'running'))
                c.execute('INSERT OR IGNORE INTO business_lines VALUES(?,?,?)',
                          ('DAS', 'DTC Digital Asset Solutions',
                           'DTC tokenization service; distinct from DDA technology provider'))
                registered = set()
                for sid, source in sources.items():
                    registered_id = source['registered_source_id']
                    if registered_id in registered:
                        continue
                    registered.add(registered_id)
                    config = dict(id=registered_id, name='DAS public monitor: ' + sid,
                                  url=source['url'], kind='das_public_monitor_batch',
                                  enabled=False, refresh_hours=None, business_lines=['DAS'])
                    c.execute('INSERT INTO sources(source_id,name,url,kind,refresh_hours,enabled,config) '
                              'VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET '
                              'name=excluded.name,url=excluded.url,kind=excluded.kind,'
                              'refresh_hours=excluded.refresh_hours,enabled=excluded.enabled,config=excluded.config',
                              (registered_id, config['name'], config['url'], config['kind'],
                               None, 0, db.dumps(config)))
                    c.execute('INSERT OR IGNORE INTO source_business VALUES(?,?)', (registered_id, 'DAS'))
                for category, (_, description, grain) in DATASETS.items():
                    c.execute('INSERT INTO datasets VALUES(?,?,?,?) ON CONFLICT(dataset_id) '
                              'DO UPDATE SET description=excluded.description,grain=excluded.grain,'
                              'interpretation=excluded.interpretation',
                              ('das_monitor_' + category, description, grain, INTERPRETATION))
                hashes = {sid: db.put_blob(c, body) for sid, body in bodies.items()}
                for dataset, key, payload, refs in records:
                    primary = refs[0] if refs else None
                    source = sources[primary]['registered_source_id'] if primary else None
                    observed = payload.get('collected_at_utc') or None
                    change = db.upsert(c, dataset, key, payload, run_id, source,
                                       hashes.get(primary), observed,
                                       'Public DAS source; mechanism monitoring is not measured internal V')
                    changes[change] += 1
                    counts[dataset] += 1
                    for sid in refs[1:]:
                        if sid in hashes:
                            c.execute('INSERT OR IGNORE INTO record_evidence VALUES(?,?,?,?,?)',
                                      (dataset, key, sources[sid]['registered_source_id'], hashes[sid],
                                       'Additional public DAS source'))
                integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
                foreign_keys = list(c.execute('PRAGMA foreign_key_check'))
                if integrity != 'ok' or foreign_keys:
                    raise ValueError('Database validation failed; import rolled back')
                receipt = dict(run_id=run_id, changes=dict(changes), rows_imported=dict(counts),
                               integrity_check=integrity, foreign_key_errors=0,
                               registered_sources=len(registered), paid_api_calls=0,
                               master_snapshot_rewritten=False)
                c.execute('UPDATE runs SET finished_at=?,status=?,summary=? WHERE run_id=?',
                          (db.now(), 'completed', db.dumps(receipt), run_id))
                c.commit()
            except BaseException:
                c.rollback()
                raise
            if make_snapshot:
                receipt['snapshot'] = db.snapshot(c, path, public=True)
            return receipt
        finally:
            c.close()


def import_monitor(monitor_path=ROOT / 'results/monitor.json', target_db=None):
    monitor_path = Path(monitor_path).resolve()
    root = monitor_path.parent.parent
    monitor = json.loads(monitor_path.read_text(encoding='utf-8'))
    portable = root / 'data/das_monitor.sqlite3'
    if target_db is not None and Path(target_db).resolve() == portable.resolve():
        raise ValueError('Optional project target must differ from portable monitor database')
    # Reject an invalid optional target before creating the portable output.
    if target_db is not None:
        validate_existing(Path(target_db).resolve())
    receipt = dict(imported_at_utc=datetime.now(timezone.utc).isoformat(),
                   scope='Only das_monitor_* datasets; no score or event-register writes',
                   portable=import_into_database(root, monitor, portable, make_snapshot=True))
    if target_db is not None:
        receipt['project_database'] = import_into_database(root, monitor, target_db, require_existing=True)
    output = root / 'results/database_import_receipt.json'
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(output)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor', type=Path, default=ROOT / 'results/monitor.json')
    parser.add_argument('--target-db', type=Path, help='Optional existing project SQLite file; master .gz remains unchanged')
    args = parser.parse_args()
    print(json.dumps(import_monitor(args.monitor, args.target_db), ensure_ascii=False, indent=2))

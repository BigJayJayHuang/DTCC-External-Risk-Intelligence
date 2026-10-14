PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS business_lines (
  business_line TEXT PRIMARY KEY, full_name TEXT NOT NULL, scope_note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
  kind TEXT NOT NULL, refresh_hours REAL, enabled INTEGER NOT NULL,
  config TEXT NOT NULL, last_checked TEXT, last_success TEXT, last_status TEXT,
  last_error TEXT, etag TEXT, last_modified TEXT, last_blob_hash TEXT
);
CREATE TABLE IF NOT EXISTS source_business (
  source_id TEXT REFERENCES sources(source_id), business_line TEXT REFERENCES business_lines(business_line),
  PRIMARY KEY(source_id,business_line)
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
  kind TEXT NOT NULL, status TEXT NOT NULL, summary TEXT
);
CREATE TABLE IF NOT EXISTS evidence_blobs (
  sha256 TEXT PRIMARY KEY, compression TEXT NOT NULL DEFAULT 'zlib',
  byte_count INTEGER NOT NULL, content BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS fetches (
  fetch_id INTEGER PRIMARY KEY, run_id TEXT REFERENCES runs(run_id),
  source_id TEXT REFERENCES sources(source_id), requested_url TEXT NOT NULL,
  checked_at TEXT NOT NULL, status TEXT NOT NULL, http_status INTEGER,
  blob_hash TEXT REFERENCES evidence_blobs(sha256), error TEXT,
  record_count INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS datasets (
  dataset_id TEXT PRIMARY KEY, description TEXT NOT NULL, grain TEXT NOT NULL,
  interpretation TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
  dataset_id TEXT REFERENCES datasets(dataset_id), record_key TEXT,
  source_id TEXT, measurement_date TEXT, payload TEXT NOT NULL,
  content_hash TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  PRIMARY KEY(dataset_id,record_key)
);
CREATE INDEX IF NOT EXISTS records_date ON records(dataset_id,measurement_date);
CREATE INDEX IF NOT EXISTS records_source ON records(source_id);
CREATE TABLE IF NOT EXISTS record_versions (
  version_id INTEGER PRIMARY KEY, dataset_id TEXT, record_key TEXT,
  content_hash TEXT NOT NULL, observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL, run_id TEXT REFERENCES runs(run_id),
  blob_hash TEXT REFERENCES evidence_blobs(sha256), payload TEXT NOT NULL,
  FOREIGN KEY(dataset_id,record_key) REFERENCES records(dataset_id,record_key)
);
CREATE INDEX IF NOT EXISTS versions_identity ON record_versions(dataset_id,record_key,version_id);
CREATE TABLE IF NOT EXISTS record_evidence (
  dataset_id TEXT, record_key TEXT, source_id TEXT,
  blob_hash TEXT REFERENCES evidence_blobs(sha256), evidence_label TEXT NOT NULL,
  PRIMARY KEY(dataset_id,record_key,source_id,blob_hash,evidence_label),
  FOREIGN KEY(dataset_id,record_key) REFERENCES records(dataset_id,record_key)
);
CREATE TABLE IF NOT EXISTS document_business (
  document_id TEXT, business_line TEXT REFERENCES business_lines(business_line),
  rule TEXT, evidence TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'candidate_unreviewed',
  PRIMARY KEY(document_id,business_line,rule)
);
CREATE VIEW IF NOT EXISTS market_daily AS
 SELECT json_extract(payload,'$.series_id') series_id, measurement_date observation_date,
        json_extract(payload,'$.value') value, json_extract(payload,'$.units') units,
        json_extract(payload,'$.frequency') frequency, source_id, last_seen checked_at
 FROM records WHERE dataset_id='market_observations';
CREATE VIEW IF NOT EXISTS news AS
 SELECT record_key document_id,json_extract(payload,'$.title') title,
        json_extract(payload,'$.url') url,json_extract(payload,'$.publication_date') publication_date,
        json_extract(payload,'$.published_at_utc') published_at_utc,
        json_extract(payload,'$.source_summary') summary,source_id,last_seen
 FROM records WHERE dataset_id='news';
CREATE VIEW IF NOT EXISTS pqd_quarterly AS
 SELECT json_extract(payload,'$.entity') entity,json_extract(payload,'$.quarter') quarter,
        json_extract(payload,'$.initial_margin_required_usd') initial_margin_required_usd,
        json_extract(payload,'$.stress_payment_obligation_usd') stress_payment_obligation_usd,
        json_extract(payload,'$.qlr_quantified_sum_usd') qlr_quantified_sum_usd,
        json_extract(payload,'$.top5_open_share') top5_open_share,payload
 FROM records WHERE dataset_id='pqd_quarterly';
CREATE VIEW IF NOT EXISTS source_health AS
 SELECT s.source_id,s.name,s.kind,s.enabled,s.last_checked,s.last_success,s.last_status,s.last_error,
        (SELECT count(*) FROM source_business b WHERE b.source_id=s.source_id) linked_businesses
 FROM sources s;

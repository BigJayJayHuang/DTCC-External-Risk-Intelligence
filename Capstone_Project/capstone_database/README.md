# Capstone shared public-data database

One database snapshot for the team's public news, market history and business data. Shared inputs are stored once and linked to the ten business lines. This is a daily **read-only snapshot workflow**, not a live SQL server.

## Team access

1. Open [Complete project download](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/releases/tag/data-latest) and download **`Capstone_Project_Complete.zip`**. Inside its single `Capstone_Project` folder, the database, manifest, CSV exports and update logs are under `capstone_database/`. Inspect `capstone_database/logs/latest_update.json` for failures and the collection date.
2. For a repeatable local workflow, clone this repository and run:

```bash
git clone https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence.git
cd DTCC-External-Risk-Intelligence
cd Capstone_Project/capstone_database
python3 download_latest.py
python3 query.py
```

The query/download commands use Python's standard library and `curl`. No collection API key is required. `download_latest.py` downloads the single project ZIP and extracts only the database and its manifest into your local copy. To use the database already included in a downloaded ZIP, run `python3 query.py` directly from this folder. Do not run `bootstrap.py` on a teammate's computer; it is only for the original project migration.

Example SQL:

```bash
python3 query.py --sql "SELECT * FROM market_daily WHERE series_id='SOFR' ORDER BY observation_date DESC LIMIT 10"
python3 query.py --sql "SELECT DISTINCT n.publication_date,n.title,b.business_line,n.url FROM news n JOIN document_business b ON n.document_id=b.document_id WHERE b.business_line='FICC' ORDER BY n.publication_date DESC LIMIT 20"
python3 query.py --sql "SELECT entity,quarter,initial_margin_required_usd FROM pqd_quarterly ORDER BY quarter DESC,entity LIMIT 9"
```

In a notebook, use a read-only connection:

```python
import sqlite3
import pandas as pd  # optional, for a DataFrame
connection = sqlite3.connect('file:data/capstone.sqlite3?mode=ro', uri=True)
sofr = pd.read_sql_query(
    "SELECT * FROM market_daily WHERE series_id='SOFR' ORDER BY observation_date",
    connection,
)
```

All other datasets are in `records`; `payload` is JSON with the original dimensions and definitions. For example:

```sql
SELECT json_extract(payload,'$.division') AS division,
       json_extract(payload,'$.reporting_month') AS month,
       json_extract(payload,'$.metric_code') AS metric,
       json_extract(payload,'$.value_raw_source_units') AS value
FROM records WHERE dataset_id='ficc_monthly';
```

## Daily operation

[Daily public-data update](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/actions/workflows/daily-data.yml) runs at **22:17 UTC daily**: 18:17 in New York during daylight saving time, 17:17 in winter. GitHub can delay scheduled jobs; this is not an exact-time service. The workflow must exist on the default branch, and Actions must be enabled. An authorized repository member can also select **Actions → Daily public-data update → Run workflow**.

The job also runs when this project or its workflow is changed on `main`. It restores the last released database, fetches due sources, validates records and raw evidence, and republishes **one complete project ZIP** containing the refreshed database and all archived project work. It preserves a recovery artifact for 30 days. Daily database binaries are release assets, not new binary commits each day. On a partial collection failure, the job still publishes the valid updated snapshot and its failure report, then marks the workflow failed to make the problem visible. The last valid values from failed sources are retained with their old timestamps.

If a release disappears while its tag remains, the updater stops instead of silently restarting from the old seed. Recover from a previous Actions artifact. There is one writer job; teammates query their own downloaded copies.

Sources are checked on their own cadence. Daily market/news/provider feeds run daily; business reference pages run weekly. RDS reports are collected by their Friday report date, including missed weekly reports (up to eight dates per source per run). Monthly operations and volume endpoints are checked daily, but new values retain the actual monthly period. Quarterly PQD and financial statements remain quarterly. No daily values are fabricated from them.

## What is included

- Official regulator/central-bank RSS, the shared DTCC notice feed, ESMA news, and Federal Register API metadata.
- FRED market series, including funding rates, Treasury yields, spreads, equity/FX/digital-market context and fund-asset proxies. Historical missing values remain null. Discontinued weekly money-market series remain history only.
- FICC daily activity, GSD/MBSD monthly activity, ECS/ITP monthly operations, ETF reference records, underwriting history, RDS jurisdiction-specific public reports and CDS reference rows.
- The reviewed 23-quarter GSD/MBSD/NSCC PQD panel, extraction evidence, quarterly legal-entity financials and operations.
- Public business-scale snapshots and ICI industry data previously captured; CISA catalog, public provider incidents and FEMA declaration records.
- Ten-business source mappings: FICC, ECS, RDS, WIS, ITP, Asset Services, DAS, DDA, Data Services and Consulting.

## Evidence and data limits

`records` stores the current record. `record_versions` stores changes, including reversions. Collection-only metadata does not create a new version. Revisions can include definition or other metadata changes, not just numeric changes. `record_evidence` links facts to SHA-256 evidence references. The original local database retains compressed raw source bodies; the public shared snapshot strips those bodies and full article text, retaining hashes, source URLs, extraction rows and structured facts. A shared `evidence_blobs` row with `compression='not_bundled'` is an evidence reference, not a downloadable original. `fetches`, `runs`, and `source_health` show update health. Historical imports do not reconstruct unknown point-in-time vintages; original unknown release/retrieval dates stay unknown in their payloads.

The daily job collects feed/API summaries, not every article's full original text. Previously collected raw public files are preserved in the historical collection folders of the complete package. Federal Register HTML access challenges are not bypassed; its official API metadata is used. Exact repeated FEMA declaration rows are merged at disaster/state/declaration-type grain. Notice variants pointing to one PDF remain one document, with both publisher labels preserved. New raw responses fetched by a cloud run are checked before publication; the current database snapshot preserves their hashes rather than complete bodies.

**Manual checks remain:** dynamic DTCC PQD/financial/news directories and ICI pages do not yet have a verified supported structured collector. They are disabled for automated extraction and listed in `manual_review_sources`; an old snapshot is never relabeled as current. A sponsor or analyst should check new quarterly releases and supply reviewed extracted data before incorporating it. DAS, DDA and Consulting internal operating KPIs are not publicly available in the collected data. The database does not fill those gaps with proxy “performance.”

Source-to-business links and keyword matches are candidate monitoring relationships, not confirmed impacts. External vulnerabilities/provider events do not establish DTCC exposure. Do not add EU and UK repository totals, industry fund subtotals, or overlapping legal-entity/segment data without checking their scopes. No machine-learning models are retrained and no calibrated risk scores are produced by this updater.

## Maintainer commands

The collector requires Python 3.12+, `curl`, and the two pinned packages:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 update.py
python3 validate.py
```

`python3 update.py --force --only fred_SOFR` checks one source immediately. Default calls skip sources checked within their configured interval. Failed sources also respect that interval; use a targeted force after fixing the cause. HTTP access denials are logged, not bypassed. `sources.json` controls supported adapters and business links. Never enable an unsupported source merely because it has a URL.

The repository is **public**. It contains public-source data and collection code only. Do not upload internal information, credentials, project presentations or private team documents. Read access requires no invitation; write access and workflow operation are controlled by the repository owner. No AWS or DevX resources are created by this project.

Source and scheduling references: [SQLite network sharing guidance](https://www.sqlite.org/whentouse.html), [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [DTCC public market data](https://www.dtcc.com/market-index-data), [FRED](https://fred.stlouisfed.org/), [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1).

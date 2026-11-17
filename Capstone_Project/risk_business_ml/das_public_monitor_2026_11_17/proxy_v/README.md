# DAS-05 public proxy V / DAS-05公开代理V

Start with [中文结果](RESULTS_CN.md) or [English results](RESULTS_EN.md).

This module implements the user-selected **hours until the next nominal conversion-order submission window**. Source-backed weekly hours are distinct from actual service availability and conversion capacity. The API explicitly mentions holiday rejection, but an applicable dated calendar has not been obtained. Current outputs are conditional weekly baselines, not verified actual waiting times.

## Reproduce / 重现

From the parent `das_public_monitor_2026_11_17` directory:

```bash
python3 src/conversion_window_proxy.py --as-of 2026-11-17T17:24:21Z
python3 -m unittest discover -s tests -v
python3 src/import_conversion_proxy.py
```

One timestamp, without writing saved outputs:

```bash
python3 src/conversion_window_proxy.py --at 2026-11-13T19:00:00-05:00
```

Current-time manual refresh:

```bash
python3 src/conversion_window_proxy.py
python3 src/import_conversion_proxy.py
```

No schedule or paid model invocation is enabled. A fresh clone needs the parent module's public evidence refresh before rebuilding; exported CSVs and the portable body-stripped snapshot can be read immediately. The saved result binds its policy and source hashes. Rebuilding against changed sources requires a source check, not reuse of an old interpretation without verification.

## Data separation / 数据区分

- `results/hourly_proxy.csv`: UTC-spaced hourly samples, preserving DST elapsed time.
- `results/daily_0800_et_proxy.csv`: fixed08:00 ET daily observations, independent of collection time.
- `results/quarterly_descriptive_summary.csv`: partial-quarter sample descriptions, **not** historical quarterly bufferV.
- `results/hypothetical_scenarios.csv`: separately labelled assumed S=3 examples, excluded from observed database records.
- `results/snapshot.json`: current nominal wait and a proposed1–5 bin; calendar-confirmed wait, internalV, accepted proxyV, and official risk score remain null.
- `data/das05_proxy.sqlite3.gz`: portable project-schema snapshot of source references and conditional research metrics, no publisher bodies.

The proposed bins are0→1; (0,8]→2; (8,24]→3; (24,48]→4; >48→5. They are uncalibrated research rules, not a claim of equal economic distances, risk-free open hours, or model validity. Multiplication by an assumed S appears only in hypothetical examples and is an ordinal priority illustration.

The optional `--target-db` of `src/import_conversion_proxy.py` imports only the labelled proxy metrics and existing source references into an existing local project database. Non-proxy record content and the master compressed snapshot are checked for preservation. No production score, final16 series, or accepted event is updated.

## Calendar / 日历

`config/calendar_overrides.json` is unconfirmed and empty. A usable replacement needs a reviewed source specifically covering DTS conversion submission, a complete dated coverage range and publication timestamps, plus provenance for every exception. Generic DTC settlement, NYSE or Federal Reserve holidays are not automatically applied. Caller-provided metadata is not independent verification; calendar outputs remain conditional on the supplied reviewed evidence.

Before the first full post-notice day2026-10-29, `evaluate` returns unavailable rather than inventing operating history. The exact regulatory commencement date is a separate unresolved question.

## Read the portable database / 读取快照

Decompress the snapshot to a local file, then query:

```sql
SELECT measurement_date,
       json_extract(payload,'$.baseline_wait_hours') AS nominal_wait_hours,
       json_extract(payload,'$.candidate_proxy_v_score_1_5') AS proposed_bin,
       json_extract(payload,'$.calendar_status') AS calendar_status
FROM records
WHERE dataset_id='das_monitor_metrics'
  AND json_extract(payload,'$.metric_id')='das05_conversion_access_hourly'
ORDER BY measurement_date;
```

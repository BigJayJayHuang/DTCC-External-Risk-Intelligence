# Missing-data retrieval / 缺失数据获取

Checked2026-11-17. This directory records retrieval work, not completed empirical calibration.

- [中文索取清单](DATA_REQUEST_CN.md) / [English request](DATA_REQUEST_EN.md): minimum existing exports to request through the project contact.
- [Availability table](availability.csv): what was obtained and what remains unavailable.
- [Retrieval status](results/retrieval_status.json): verified local gaps and calibration readiness.
- [Public disclosure](results/public_disclosure.json): one source-checked SG collateral-transaction disclosure. It is not a stress label, service-wide volume, protective buffer or operating-delay observation.
- [Sanitized AWS reading receipt](results/receipt_public.json): one bounded public-document reading; source evidence was checked locally. Original PDF/text and detailed AWS responses remain local.

No external message was sent. No participant data endpoint or new credential was requested. Real internalV and formal risk scores remain unavailable because the required measured inputs were not obtained. The1–5 proxy policy was not re-labelled as empirically calibrated.

To rebuild the separate public-disclosure snapshot from cached evidence, run from the parent monitor directory:

```bash
python3 src/import_monitor_db.py --monitor proxy_v/data_acquisition_2026_11_17/results/public_disclosure.json
```

Its body-stripped `data/das_monitor.sqlite3.gz` contains public references and the single disclosure, not order-level operating records.

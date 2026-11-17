# DAS public-evidence monitor / DAS公开证据监测

The runnable scope is intentionally small: DAS-01 software/infrastructure evidence and DAS-04 regulatory/network changes. The five original card IDs remain traceable. DAS-02/03 internal measurements are deferred; DAS-05 has an offline authorized-order adapter. No simulated prelaunch data, internal V, empirical loss prediction or S×V score is manufactured.

本目录把五条研究链落成两个公开监测模块和一个授权订单接入接口。先阅读 [中文运行结果](RESULTS_CN.md) 或 [English results](RESULTS_EN.md)。[结果表](data/findings.csv)、[链的取舍](data/scope.csv)、[报告日历](data/deadlines.csv)及[完整机器输出](results/monitor.json)可直接供团队复核。

## Reproduce the saved result / 重现本次结果

Run from this directory with the local evidence cache present. Rebuilding and importing do not call AWS:

```bash
python3 src/update_monitor.py --as-of 2026-11-17 --window-start 2026-11-09
python3 -m unittest discover -s tests -v
```

## Refresh manually / 后续手动刷新

```bash
python3 src/update_monitor.py --refresh
```

This fetches each configured public URL once, reads current maintainer advisories, applies the date window, and saves a portable SQLite snapshot. It does not enable a schedule, invoke a paid model, access participant-only APIs, or write the production event register. Repeated imports retain dated metrics and deduplicate source bodies.

A fresh Git checkout first needs this public refresh: original publisher bodies are retained locally rather than republished in Git. The branch includes the dated source manifest, findings, source-checked interpretations, code, and body-stripped database. Later publisher changes may prevent an exact historical replay; current refreshes are not claimed as historical vintages.

若官方文件正文发生变化，旧AWS解读会被隔离并标记为过期，不会静默套用；结构化公告监测继续运行。新版本需另行进行有费用上限的人工API阅读与原文复核。本文档的API结果是研究证据，不是DTCC业务负责人确认。

## Real order data / 真实订单接入

`data/authorized_orders_template.csv` contains headers only. It is not a fabricated dataset. The public guide is [here](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content); authenticated service data is not public. Supply an authorized export locally:

```bash
python3 src/update_monitor.py --orders /absolute/path/authorized_orders.csv
```

Only `Processing`, `Completed` and `Failed` are order statuses. A 202 response, an account activity marked `Confirmed`, or an asynchronous operation completion does not prove order completion. Completion duration requires a separately confirmed completion timestamp; `updated_at` is not substituted. Results are operating outcomes, not protective-buffer V.

## Database / 数据库

`data/das_monitor.sqlite3.gz` is a portable public snapshot with raw bodies removed. The local `.sqlite3` retains source evidence. The optional `--target-db /absolute/path/existing/capstone.sqlite3` imports only `das_monitor_*` datasets into the project database under a writer lock. Unrelated datasets and the existing master compressed snapshot are preserved. The November9 evidence package remains unchanged.

## Interpretation / 结果边界

- A Besu software connection is documented, but the deployed DTS version, consensus configuration, patch status and exploitation remain unknown. Findings are requests to check applicability, not confirmed outages.
- Solana is a future announced network in the saved evidence; current Solana incidents are excluded from current DTS outage exposure.
- Canton public configuration is context, not a measurement of DTS private Besu availability, DTC holdings or service resilience.
- The SEC calendar records a reporting term. Non-public submission status is unknown; the exact relief expiry requires confirmation of formal launch and written notice.
- Source availability is distinct from service health; missing data stays null. The source snapshots do not reconstruct historical point-in-time vintages.
- Test fixtures are synthetic and exist only under `tests/`; no test record enters the data outputs or database.

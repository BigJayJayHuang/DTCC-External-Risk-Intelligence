# 数据库更新 / Database update

2026-10-21. 本轮新增 **12,714 条记录**，数据库由42,722条增至 **55,436条**。
This import added **12,714 records**, increasing the database from42,722 to **55,436**.

| 数据 / Dataset | 新增记录 / Records | 范围及限制 / Scope and limits |
|---|---:|---|
| `ofr_repo_observations` | 8,217 | 四个OFR回购序列；含真实缺失记录；最终版本截至2026-06-30。Four final-vintage repo series, including null observations, through2026-06-30. |
| `treasury_auctions` | 3,594 | 2018年至2026-10-20符合日期和已完成条件的拍卖；发行额为公布供给额。Completed, locally filtered auctions; offering amount is announced supply, not actual awards. |
| `fund_flow_quarterly` | 212 | 两个季度资金流序列，各106期，2000Q1–2026Q2；2026-09-11发布版本。Two106-quarter transaction series, September11 release vintage. |
| `chain_pqd_observations` | 68 | 66条新增PQD字段记录，以及2条仅有财报保证事项数据的2024Q4记录；原值与核对后值分列。66 additional PQD rows plus2 financial-note-only rows; original and reconciled fields remain separate. |
| `chain_pqd_cell_evidence` | 531 | 原始单元格、定义、单位、文件与哈希。Original cells, definitions, units, source files and hashes. |
| `financial_guarantee_reconciliation` | 46 | 23季度、GSD与MBSD的财报保证事项与PQD量纲核对。23-quarter financial-guarantee/PQD reconciliations for GSD and MBSD. |
| `mbsd_activity_reconciliation` | 22 | MBSD活动指标核对；两处量纲修正有剔除后敏感性检验。Activity reconciliation including sensitivity that excludes two repaired observations. |
| `public_source_documents` | 24 | 已下载官方响应的来源元数据；不把规则描述当作实际事故。Metadata for downloaded public responses; a rule is not an observed incident. |

**存储位置 / Storage**

- 实际数据库 / Local database: `../../capstone_database/data/capstone.sqlite3`.
- 共享快照 / Shareable snapshot: `../../capstone_database/data/capstone.sqlite3.gz`.
- 快照校验与记录数 / Checksums and counts: `../../capstone_database/data/snapshot_manifest.json`.
- 导入凭证 / Import receipt: `results/database_import_receipt.json`.
- 重复导入核查 / Repeat-import check: `results/database_repeat_import_check.json`.
- SQL示例 / Example SQL: `../../capstone_database/research_queries.sql`.

共享来源只保存一组记录，再关联适用业务。原始响应按SHA-256去重，保留采集时间、单位、空值和失败请求记录。重复导入12,714条全部识别为未变化，未新增记录、版本或采集日志。原有PQD与历史检验未被覆盖。

Shared sources are stored once and linked to relevant businesses. Raw bodies are deduplicated by SHA-256, with retrieval times, native units, missingness and failed requests preserved. A second import marked all12,714 records unchanged and added no records, versions or fetch logs. Legacy PQD values and historical tests were preserved.

**更新边界 / Refresh scope**

本次是经核对的批次导入。现有每日更新程序继续负责其已启用的数据源；本次新增来源尚未接入每日自动采集，配置中明确禁用自动刷新。这份本地数据库和快照已更新，GitHub上的发布包尚未因本次导入而更新。

This is a reviewed batch import. The existing daily updater continues to refresh its enabled sources; these additional source adapters are not yet enabled for automatic daily collection. The local database and snapshot have been updated. This import has not updated the GitHub release.

本地原始响应存入证据表；共享快照保留结构化数据与证据哈希，不含证据表内完整响应正文。未披露的会员、账户或服务专属结果仍为空缺。相关性结果属于探索性证据，不是因果结论或校准后的风险评分。

Raw responses are retained in the local evidence table. The shared snapshot contains structured data and evidence hashes, without complete response bodies in that table. Unavailable participant/account/service outcomes remain missing. Association tests are exploratory evidence, not causal findings or calibrated risk scores.

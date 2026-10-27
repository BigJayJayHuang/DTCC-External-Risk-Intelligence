# 传导链工作台 / Transmission Chain Board

从这里查看**定义 → 检验 → 数据缺口 → 数据库 → 周度评分**。所有材料仍在 `Capstone_Project/` 总文件夹中；本页集中提供入口，原目录和历史证据保留。

Use this board to navigate **definitions → tests → data gaps → database → weekly scoring**. The original folders and historical evidence remain intact inside the single `Capstone_Project/` folder.

## 先看什么 / Start here

**当前模型输入 / Current model inputs：** [16卡季度V总入口](risk_business_ml/final16_quarterly_vulnerability_2026_10_27/README.md) · [中文说明](risk_business_ml/final16_quarterly_vulnerability_2026_10_27/README_CN.md) · [English](risk_business_ml/final16_quarterly_vulnerability_2026_10_27/README_EN.md) · [模拟季度V](risk_business_ml/final16_quarterly_vulnerability_2026_10_27/data/quarterly_vulnerability_SIMULATED.csv) · [团队卡片ID对照](risk_business_ml/final16_quarterly_vulnerability_2026_10_27/results/card_id_map.csv)。10张缺少真实V的卡片各23季度，2020Q4–2026Q2，共230条模拟V；6张卡沿用真实PQD V及原有缺失值。5条链已纳入，当前16张卡、31条已确认组成链。模拟/真实逐行标记、分文件保存；提供按可用日期读取及S×V接口。历史发布时间及数据修订版本未核实，模拟不是已观测内部缓冲或损失概率。10 cards have explicitly simulated quarterly V;6 retain observed-PQD V. All31 component assignments are confirmed.


**历史56条补缺范围 / Historical56-chain missing-data scope：** [真实数据优先修正版 / Real-data-first revision](risk_business_ml/synthetic_data_scope_revision_2026_10_27/README.md) · [56条逐环节清单 / 56-chain source priority](risk_business_ml/synthetic_data_scope_revision_2026_10_27/SOURCE_PRIORITY_CN.md) · [English](risk_business_ml/synthetic_data_scope_revision_2026_10_27/SOURCE_PRIORITY_EN.md)。9条沿用真实数据、22条仅允许模拟缺失环节、18条为缺专属数据的模拟候选、7条先补事实／定义。该历史批次重跑3个固定真实输入的缺口示范；此前131种广泛假设情景保留为历史程序实验，不再作为当前补缺覆盖口径。Observed data take priority; weak empirical results are not missing data. The real database, empirical statuses and weekly scores remain unchanged.

| 目的 / Purpose | 入口 / Open | 阅读提示 / What it means |
|---|---|---|
| **31条新增链的结果 / New-chain findings** | [中文汇总](risk_business_ml/new_reference_chain_tests_2026_10_21/Concise_Test_Summary_CN.md) · [English summary](risk_business_ml/new_reference_chain_tests_2026_10_21/Concise_Test_Summary_EN.md) | 10条部分数值检验、4条案例/条件核对、17条缺专属数据；完整验证0条。10 partial numerical tests,4 case/condition reviews,17 missing-data cases;0 fully validated chains. |
| **逐链状态与缺口 / Status and missing data** | [中文CSV](risk_business_ml/new_reference_chain_tests_2026_10_21/results/new_chain_status_CN.csv) · [English CSV](risk_business_ml/new_reference_chain_tests_2026_10_21/results/new_chain_status_EN.csv) | 每行对应一条新增链，包括做过的检验、发现和还需获取的数据。One row per new chain, with performed tests, findings and required data. |
| **31条新增链的定义 / New-chain definitions** | [中文](reports/transmission_chain_alignment_2026_10_21/output/New_Reference_Chains_v3_CN.md) · [English](reports/transmission_chain_alignment_2026_10_21/output/New_Reference_Chains_v3_EN.md) | 只看本轮新增的机制与候选指标。Mechanisms and candidate indicators for the31 additions. |
| **完整v3目录 / Complete v3 catalog** | [中文Word](reports/transmission_chain_alignment_2026_10_21/output/Transmission_Chains_v3_CN.docx) · [English Word](reports/transmission_chain_alignment_2026_10_21/output/Transmission_Chains_v3_EN.docx) · [JSON](reports/transmission_chain_alignment_2026_10_21/output/chain_registry_v3.json) | 56条定义，含参考链与团队扩展。定义快照中的“未检验”状态以本页新增检验结果为后续证据。56 definitions; subsequent test results above supersede the definition snapshot's untested labels. |
| **可运行分析 / Reproducible analysis** | [已执行Notebook / Executed notebook](risk_business_ml/new_reference_chain_tests_2026_10_21/New_Reference_Chain_Validation.ipynb) · [使用说明 / README](risk_business_ml/new_reference_chain_tests_2026_10_21/README.md) | 计算、图表、方法和限制；不是新增31条链的已校准风险模型。Calculations, figures and limitations; not a calibrated model for all31 additions. |

## 数据与证据 / Data and evidence

| 内容 / Content | 入口 / Open |
|---|---|
| 数据库说明与查询 / Database usage and queries | [中文](capstone_database/README_CN.md) · [English](capstone_database/README.md) · [查询程序 / Query program](capstone_database/query.py) · [研究SQL / Research SQL](capstone_database/research_queries.sql) |
| 共享数据库快照与最新清单 / Shared snapshot and current manifest | [SQLite快照 / Snapshot](capstone_database/data/capstone.sqlite3.gz) · [校验、记录数与时间 / Manifest](capstone_database/data/snapshot_manifest.json) · [数据集目录 / Dataset inventory](capstone_database/exports/dataset_inventory.json) |
| 线上与本地数据合并记录 / Online/local merge receipt | [GitHub同步凭证 / GitHub sync receipt](capstone_database/logs/latest_github_sync.json) · [研究批次集成凭证 / Reviewed batch sync](capstone_database/logs/latest_reviewed_batch_sync.json) |
| 新增研究数据的口径 / Research-data definitions | [中英文说明 / Bilingual note](risk_business_ml/new_reference_chain_tests_2026_10_21/DATABASE_UPDATE_CN_EN.md) · [导入凭证 / Import receipt](risk_business_ml/new_reference_chain_tests_2026_10_21/results/database_import_receipt.json) · [重复导入核查 / Repeat-import check](risk_business_ml/new_reference_chain_tests_2026_10_21/results/database_repeat_import_check.json) |
| 来源与质量核查 / Sources and checks | [来源索引 / Sources](risk_business_ml/new_reference_chain_tests_2026_10_21/results/source_register.json) · [采集记录 / Fetch manifest](risk_business_ml/new_reference_chain_tests_2026_10_21/fetch_manifest.json) · [单位核对说明 / Unit reconciliation](risk_business_ml/new_reference_chain_tests_2026_10_21/data_quality_amendment.json) · [交付核查 / Checks](risk_business_ml/new_reference_chain_tests_2026_10_21/results/delivery_checks.json) |
| 分析数据与程序 / Analysis inputs and code | [配对数据、单元格和页码证据 / Data and evidence](risk_business_ml/new_reference_chain_tests_2026_10_21/data/) · [公开原始响应 / Public raw responses](risk_business_ml/new_reference_chain_tests_2026_10_21/raw/) · [程序 / Scripts](risk_business_ml/new_reference_chain_tests_2026_10_21/src/) |

记录数、采集截止时间与发布版本以清单和日志为准。新增研究来源通过固定批次集成；现有每日采集器只刷新已启用的数据源。历史分析不会随数据库更新自动重算。

Read counts, source cutoffs and release versions from the manifests and logs. Added research inputs are integrated as a frozen batch; daily collectors refresh only enabled sources. Database updates do not automatically recompute historical studies.

## 历史检验与队友评分 / Historical tests and teammate scoring

| 材料 / Workstream | 入口 / Open | 区别 / Keep separate |
|---|---|---|
| **原22条候选链检验 / Earlier22 candidate-chain tests** | [中文汇总](risk_business_ml/transmission_chain_tests_2026_10_16/精简检验汇总_CN.md) · [English summary](risk_business_ml/transmission_chain_tests_2026_10_16/Concise_Test_Summary_EN.md) · [Notebook](risk_business_ml/transmission_chain_tests_2026_10_16/Transmission_Chain_Validation.ipynb) | 旧定义和历史结果；不直接作为新增31条的通过证明。Legacy definitions and results do not validate the31 additions. |
| **队友10条核心链检验 / Teammate's10 core-chain tests** | [报告 / Report](results/chain_tests/REPORT.md) · [检验规范 / Test spec](results/chain_tests/TEST_SPEC.md) · [可信度 / Confidence](results/chain_tests/chain_confidence.json) | 独立的核心链集合及其签字、版本和可信度。A separate core set with its own sign-offs, versions and confidence. |
| **队友周度评分v1.2 / Teammate's weekly scoring v1.2** | [规则 / Scoring spec](results/scoring/SCORING_SPEC.md) · [最新输出 / Latest output](results/scoring/weekly_scores.json) · [历史输出 / History](results/scoring/weekly_scores_history.csv) · [评分代码 / Code](validation/scoring.py) | 基于该核心链集合的规则评分，不代表新增31条全部接入或验证。Rule-based scores for that core set, not evidence that all31 additions are integrated or validated. |

**引用时使用“目录/批次版本＋链编号”，不要仅按 `chain_id` 跨表连接。** 原10条核心链与扩展v3可能复用编号，机制、结果变量和检验规格未必相同。各目录保留各自模型和结果，新增检验不覆盖队友v1.2评分。现有相关性和规则评分不等于因果证明、损失概率或已校准的风险分数。

**Identify chains by catalog/batch version plus chain ID; never join these workstreams on bare `chain_id`.** The10 core chains and expanded v3 catalog can reuse IDs with different mechanisms, outcomes or test specifications. Each directory preserves its own models and results; the new tests do not override the teammate's v1.2 scores. Associations and rule-based scores are not causal proof, loss probabilities or calibrated risk scores.

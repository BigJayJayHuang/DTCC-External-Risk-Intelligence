# Capstone Project · 统一项目文件夹

**[传导链统一工作台 / Transmission Chain Board](TRANSMISSION_CHAIN_INDEX.md)** — 按定义、检验、数据缺口、数据库和队友周度评分集中导航。

这里集中保存我们已经完成的数据采集、处理、指标检验、报告和共享数据库。先从此页进入，无需逐个寻找散落文件。

## 从哪里开始

| 内容 | 入口 | 说明 |
|---|---|---|
| **10月27日当前成果：真实数据优先、仅模拟缺口** | [修正版入口](risk_business_ml/synthetic_data_scope_revision_2026_10_27/README.md) · [中文结果](risk_business_ml/synthetic_data_scope_revision_2026_10_27/RESULTS_CN.md) · [English results](risk_business_ml/synthetic_data_scope_revision_2026_10_27/RESULTS_EN.md) | 56条逐环节分流；9条沿用真实数据、22条只模拟缺失部分、18条为候选、7条先补事实与定义；3个固定真实输入的可运行缺口示范 |
| **当前数据库与每日更新** | [capstone_database](capstone_database/README_CN.md) · [English](capstone_database/README.md) | 最新共享快照、CSV、查询程序、来源映射与更新日志 |
| **10月21日新增传导链检验** | [中文汇总](risk_business_ml/new_reference_chain_tests_2026_10_21/Concise_Test_Summary_CN.md) · [English](risk_business_ml/new_reference_chain_tests_2026_10_21/Concise_Test_Summary_EN.md) | 31条证据核对、逐链状态、Notebook及新增12,714条研究数据的入库记录 |
| **10 月 14 日的数据更新** | [data_refresh_2026_10_14](data_refresh_2026_10_14/README_CN_EN.md) | 十条业务线的公开数据、新闻、业务信息需求及覆盖缺口 |
| **历史业务原始资料** | [public_performance_data](public_performance_data/) | 公开 PQD、财务披露、来源记录及采集支持文件 |
| **最早的新闻采集原型** | [public_news_prototype](public_news_prototype/README.md) | 五个官方来源、原始 RSS、历史新闻和原型代码 |
| **机器学习与风险关联分析** | [risk_business_ml](risk_business_ml/Analysis_Results_and_Usage_Guide_EN.md) · [中文](risk_business_ml/分析结果与使用说明.md) | 数据、程序、Notebook、图表和探索性分析结果 |
| **全部风险类别扩展** | [risk_category_expansion](risk_business_ml/risk_category_expansion/README.md) | 风险类别扩展、特征和关联结果 |
| **事件与 PQD 两项检验** | [中文结果](risk_business_ml/event_vulnerability_tests_2026_10_06/两个检验与脆弱度框架_中文结果.md) | 事件检验、PQD 关联检验及外部冲击 × 内部脆弱度框架 |
| **后续修订与中英文报告** | [feedback_revision_report](risk_business_ml/feedback_revision_report_2026_10_06/README.md) | 区分业务反应与缓冲充足度的补充检验 |
| **逻辑链、数据索要清单与演讲稿** | [reports](reports/) | FICC 九条中英逻辑链、十业务线中英文清单、第五页演讲稿与预览 |
| **核心逻辑链检验（第一轮已签字）** | [results/chain_tests](results/chain_tests/REPORT.md) | FICC、ECS 共 10 条核心链的两项检验、最终可信度（`chain_confidence.json`）和图表；检验规则先定稿后计算（`TEST_SPEC.md`） |
| **每周打分（当前 v1.2）** | [results/scoring](results/scoring/SCORING_SPEC.md) | 每周冲击分 S × 脆弱度 V 与卡片排名：`weekly_scores.json`（最新一周）、`weekly_scores_history.csv`（2021 年起）、v1.1 与 v1.2 对比；旧版本输出保留为 `*_v1.0.*`、`*_v1.1.*` |
| **检验与打分程序** | [validation](validation/) | 数据下载（`fetch.py`）、逻辑链检验（`run.py`）、可信度导出（`export.py`）、每周打分（`scoring.py`）、事件评分规则 v1.2（`event_scoring.py`）与 LLM 事件分类提示词 |
| **历史假设模拟，已被当前范围修正** | [早期DTC/EPN/TBA原型](risk_business_ml/synthetic_chain_simulations_2026_10_27/README.md) · [后续广泛扩展](risk_business_ml/synthetic_chain_expansion_2026_10_27/README.md) | 保留代码、带标签的模拟数据、独立核查与图表；不作为当前补缺进度或真实有效性证明 |

## 队友如何使用

从 [Release](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/releases/tag/data-latest) 下载 **`Capstone_Project_Complete.zip`**。解压后所有材料都在 `Capstone_Project/` 内。

打开终端，进入解压出来的 `Capstone_Project/capstone_database`，运行：

```bash
python3 query.py
```

这会解压并查询当前随包提供的数据库。以后只更新本机数据库，可以运行：

```bash
python3 download_latest.py
```

也可直接打开 `capstone_database/exports/` 中的 CSV。完整旧数据和旧分析都仍在本总文件夹内；它们不会因为每日采集而被重算或改写。

## 使用时保留的边界

当前数据库计划每日 **22:17 UTC** 更新，即纽约夏令时 18:17、冬令时 17:17。GitHub 可能延迟运行。季度、月度数据仍保留实际披露频率。人工复核来源、缺失值和失败状态见数据库说明及日志。

历史模型和风险指标结果是探索性证据，不是已验证的因果关系、业务暴露、可靠预测或校准风险分数。每日工作流只更新数据，不重跑历史机器学习。

原始分析文件按原目录关系保留，方便核对代码与数据；[HISTORICAL_FILE_INDEX.json](HISTORICAL_FILE_INDEX.json) 记录复制文件的来源相对路径与哈希。完整 ZIP 内的 `PACKAGE_MANIFEST.json` 记录每个文件的校验值。重复的旧 ZIP、虚拟环境、依赖目录和临时构建文件不重复打包。

项目方提供的原始 kickoff、需求、taxonomy 文档及完整演示文稿保留在原工作区；本公开共享包包含我们整理的公开数据、分析报告、清单和演讲材料。

## English

**Current work:** [Real-data-first, gap-only revision](risk_business_ml/synthetic_data_scope_revision_2026_10_27/README.md) preserves observed data and existing empirical tests. Its56-chain ledger separates9real-data specifications,22partial-data routes,18missing-service-data candidates and7facts/definition gaps. Three runnable examples generate only missing quantities while holding real source values fixed. Earlier broad simulations remain historical materials; they do not replace observed data or validate actual transmission.

This folder is the single entry point for the team's previous collection work, historical public disclosures, exploratory models and validation, bilingual reports, speaking materials, and the current shared database. Download **one complete ZIP** from the release page. Unzip it and run `python3 query.py` from `Capstone_Project/capstone_database`; use `python3 download_latest.py` later to refresh only your local database copy.

Chain validation and weekly scoring:
- **Validation:** [results/chain_tests](results/chain_tests/REPORT.md) holds validation round 1 (10 core FICC/ECS chains, signed off 2026-10-16).
- **Weekly scoring:** [results/scoring](results/scoring/SCORING_SPEC.md) holds the weekly shock × vulnerability scores and card ranking (current spec v1.2; earlier outputs kept as `*_v1.0.*` / `*_v1.1.*`).
- **Code:** in [validation](validation/). Each spec was frozen and committed before its scores were computed.
- **To re-run**, from `Capstone_Project/`: `.venv-validation/bin/python -m validation.scoring --run-date YYYY-MM-DD`.
- **SEC downloads:** `python -m validation.fetch --source sec_ftd` needs `SEC_USER_AGENT="Organisation contact@email"` in your environment (SEC fair-access policy). Don't commit it.
- **Limits:** these scores are rule-based screening scores, not calibrated risk probabilities.

The daily workflow updates the current database and republishes the complete ZIP. Historical studies retain their original inputs, dates and limitations; they are not retrained by this job. Source-provided project documents and full presentation decks remain in the original workspace. Redundant old archives, installed dependencies, credentials and temporary caches are excluded.

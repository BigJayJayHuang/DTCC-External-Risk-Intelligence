> **范围已更正（2026-10-27）：** 本文件是此前的广泛假设实验，不再作为“仅补缺失数据”的当前结果。已有真实数据的环节不使用生成值替代。请以[真实数据优先修正版](../synthetic_data_scope_revision_2026_10_27/README.md)及56条逐环节清单为准；原数值留作历史程序实验。

> **Scope corrected (2026-10-27):** This is the earlier broad hypothetical batch, not the current missing-data-only study. Observed fields must not be replaced. Use the [real-data-first revision](../synthetic_data_scope_revision_2026_10_27/README.md) and its56-chain step-level ledger. Original numbers remain historical implementation experiments.

# Expanded Synthetic Chain Models / 扩展传导链情景模拟

**SIMULATED ONLY / 全部为假设模拟。** This batch adds19mechanism prototypes for20catalog chains. Together with the earlier3prototypes, there are22mechanisms and131scenarios. Among56catalog chains,24have partial mechanism simulations,2have generic outage contexts only, and30have no dedicated simulation. These are coverage counts, not empirical validation counts.

本轮新增19个机制原型，涉及20条目录链；加上前轮共22个机制、131种情景。56条目录链中，24条有部分机制模拟、2条仅有通用故障背景、30条尚未建立专属模拟。全部保留原始实证状态，不接入真实数据库或队友评分。

Start with **[中文结果](RESULTS_CN.md)** or **[English results](RESULTS_EN.md)**. Then inspect the **[56条覆盖清单](CHAIN_COVERAGE_CN.md) / [56-chain coverage ledger](CHAIN_COVERAGE_EN.md)**. The[original DTC/EPN/TBA study](../synthetic_chain_simulations_2026_10_27/README.md) remains intact.

| Folder | Content / 内容 |
|---|---|
| `src/` | Three new engines containing19distinct mechanisms; runner, independent replay audits, figures and packaging. 三个引擎文件内包含19种不同机制。 |
| `config/` | Configurations, seed and engine/runner/source hashes frozen before calculations. 计算前冻结设置。 |
| `inputs/` | Exactv3catalog, prior-status snapshots, qualitative source references and original-artifact protection hashes. 目录、原状态、来源及保护校验值。 |
| `data/` | Labelled synthetic CSVs and isolatedSQLite database; compressed snapshot supports portable restoration. 独立模拟数据。 |
| `results/` | Scenarios, comparisons, chain coverage, assumptions, unit-test and independent-audit receipts. 情景、逐链状态及核查。 |
| `figures/` | Exported scientific figures; each panel has its own measure/scale. 有独立单位和刻度的模拟图。 |

## Reproduce / 复现

Python3.12+ with the versions in`requirements.txt`. From this folder:

```bash
python3 -m unittest discover -s tests -v
python3 src/run_expansion.py --seed 20261027 --replications 100
python3 src/build_outputs.py
python3 src/audit_margin.py
python3 src/audit_default.py
python3 src/audit_operations.py
python3 src/verify_outputs.py
python3 src/package_delivery.py
python3 src/query_store.py
```

An engine/config/source change produces a new simulation ID. Identical immutable batches do not create duplicate rows. Generated data carry`source_type=synthetic`,`empirical_validation=False`,catalog/assumption/batch/scenario IDs and exact seeds stored as text. Database writes enforce synthetic-only labels. The maintained[SQL examples](src/query_synthetic.sql) use the separate store; the empirical database is never opened for writing.

The combinedZIP has one top-level folder containing this study plus the originalv1study. It includes compressed snapshots, not the large uncompressedSQLite files.`query_store.py`verifies checksums, restores the appropriate synthetic snapshot if absent, then opens a read-only connection.

## Boundaries / 范围

All numeric parameters, virtual members and dependencies are hypothetical. This is not a DTCC production replica, an official margin/default-allocation formula, real-world probability estimate, historical causal test or machine-learning training result. No actual service/member mapping is inferred from generated fixtures. Different-service notional/cash/queue measures must not be ranked together.

所有数值、会员及依赖映射均为假设。它们用于机制与程序检查，不是对真实风险、因果、官方规则公式或模型预测能力的验证。原始数据缺口仍然存在。

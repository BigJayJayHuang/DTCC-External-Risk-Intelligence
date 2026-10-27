> **范围已更正（2026-10-27）：** 本文件是此前的广泛假设实验，不再作为“仅补缺失数据”的当前结果。已有真实数据的环节不使用生成值替代。请以[真实数据优先修正版](../synthetic_data_scope_revision_2026_10_27/README.md)及56条逐环节清单为准；原数值留作历史程序实验。

> **Scope corrected (2026-10-27):** This is the earlier broad hypothetical batch, not the current missing-data-only study. Observed fields must not be replaced. Use the [real-data-first revision](../synthetic_data_scope_revision_2026_10_27/README.md) and its56-chain step-level ledger. Original numbers remain historical implementation experiments.

# Synthetic Chain Simulations / 传导链情景模拟

**SIMULATED ONLY / 全部为假设模拟**。3个模型的配置、数据、程序、结果和检查集中在本文件夹；没有写入真实业务数据库，没有改变原验证状态，也没有自动推送到GitHub。

Start with **[中文结果](RESULTS_CN.md)** or **[English results](RESULTS_EN.md)**.

| Folder / 目录 | Content / 内容 |
|---|---|
| `src/` | Three engines, runner, output builder, independent audits and SQL queries. 三个引擎、运行与独立核查程序。 |
| `config/` | Plan, defaults, seeds and engine hashes frozen before calculations. 计算前冻结的设置。 |
| `inputs/` | Public reference/evidence and original-artifact protection hashes. 公开参照与真实文件保护校验值。 |
| `data/` | Tagged synthetic CSVs and separate `synthetic_scenarios.sqlite3`. 标注为模拟的CSV与独立数据库。 |
| `results/` | Scenario summary, controls, assumptions, audits and simulation-only status. 汇总、假设与检查。 |
| `figures/` | Exportable static scenario figures, all labelled SIMULATED. 所有图均标明模拟。 |

## Run / 运行

Python3.12+ with `requirements.txt` (execution used Python3.13; versions in the receipt).
From this folder:

```bash
python3 -m unittest discover -s tests -v
python3 src/run_simulations.py --seed 20261027 --replications 100
python3 src/build_outputs.py
python3 src/audit_epn_tba.py
python3 src/verify_outputs.py
python3 src/query_store.py
```

The source-generated plan and simulation ID change if engine code or parameters change.
The same batch inserts no duplicate records. Exact unsigned scenario seeds are text in SQLite;
convert with `int(seed_string)` only when initializing an RNG. Inspect the views with a read-only
SQLite connection; example queries are in `src/query_synthetic.sql`. The ZIP ships the compressed
synthetic snapshot; `python3 src/query_store.py` verifies its checksums, restores it if needed,
and then queries it read-only. It never opens the team's real public-data database.

This is a simplified mechanism study, not a production replica, causal validation, real-world
loss/probability model, or a comparison ranking DTCC business lines. No synthetic row is a new
historical event or quarter. The ordinary project database and weekly scoring pipeline do not
read this dedicated store. A real-data anchor constrains scale, not unidentified portfolio shares.

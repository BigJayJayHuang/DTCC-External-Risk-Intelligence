# FICC and ECS transmission chain tests

2026-10-16 · 22 candidate chains · Framework S × V with an applicability gate

先看 **[精简检验汇总_CN.md](精简检验汇总_CN.md)**。它逐条区分已经完成的统计检验、案例或描述核对、以及尚未完成的检验。

- [22条链完整状态表](results/chain_status_CN.csv)
- [FICC最后汇总表对应内容](results/FICC_检验结果汇总.csv)
- [ECS汇总表对应内容](results/ECS_检验结果汇总.csv)
- [已执行的复跑Notebook](Transmission_Chain_Validation.ipynb)
- [案例证据](results/case_evidence.json)
- [尚缺数据和定义](data/remaining_data_gaps.csv)

8条链完成两项统计检验；NSCC-02A和NSCC-03B按卡片门槛达标。门槛达标不是因果证据、可靠风险评分或损失概率。原始候选文件未修改；副本在inputs。源文件里的矛盾定义、变体和未取得的数据均保留记录。

## Files

- inputs: supplied candidate DOCX files, frozen market/business/Sponsored inputs, 23 original PQD source files.
- raw: successfully downloaded official public data, including 210 SEC FTD half-month archives. Failed fetches remain in the fetch manifests.
- data: date-aligned features, cell evidence, exact analysis pairs, FTD daily outstanding balances and file coverage.
- results: primary tests, secondary variants, case evidence, per-chain coverage and gaps.
- figures: the inspected quarterly confidence-interval figure embedded in the notebook.
- src: collection, extraction, computation, summary and notebook scripts.

The existing daily market snapshot retains its individual source cutoffs (generally Oct9 or Oct13). New-source cutoffs differ; see run_manifest.json and fetch manifests. PQD outcomes end in2026Q2. No historical model retraining or final risk-score calibration was performed.

新增来源目前保存在本测试包；接入共享数据库和每日更新作业仍待实施。No GitHub publication was performed for this run.

## Reproduce offline

Use Python3.12 and the packages in requirements.txt. Exact versions used are recorded in environment_versions.json.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/run_numeric_tests.py
.venv/bin/python src/fit_equity_ftd.py
.venv/bin/python src/build_summary.py
.venv/bin/python src/execute_notebook.py
```

These commands use saved inputs without network requests. `src/analyze_ftd.py` additionally rebuilds daily balances from the210raw archives. `src/extract_fed_rates.py` rebuilds the selected Federal Reserve rate series from the original XML archives. `src/extract_pqd_additions.py` rebuilds22XLSX-source cell-evidence extracts; the2024Q4PDF text is retained separately and was not forced into entity-level fields.

The executed notebook has7code cells with zero error outputs. The full-size embedded chart was visually inspected. Whole-page HTML inspection was blocked by the browser's file-protocol policy, so it is not claimed as visually verified. See delivery_checks.json.

Technical processing repairs are logged separately from analytical choices. The rejected early FTD half-month-boundary result in diagnostics is superseded and must not be used; the final calculation preserves actual settlement dates including the15th. No event windows, directions or significance gates were changed because of the numerical results.

# New Reference Chain Tests / 新增传导链检验

2026-10-21. Start with **Concise_Test_Summary_CN.md** or **Concise_Test_Summary_EN.md**.
All31 chains were reviewed;10 received partial numerical diagnostics,4 case/condition reviews,
and17 remain unrun for lack of specific data. No new chain is fully validated.
原有25条定义、22条旧映射及历史结果不变。新增检验没有校准风险评分或证明因果。

The root contains bilingual summaries, an executed notebook and an updated catalog view.
`results/` contains all31 statuses, statistics and provenance; `data/` exact pairs and cell/page
evidence; `inputs/` frozen source data; `raw/` public downloads; `src/` runnable scripts.
Files are grouped in this one folder. The earlier catalog is a definition snapshot; use the
new `chain_registry_v3_with_test_status.json` for the review status.

New public inputs have also been stored in the existing project database:12,714 additional
records,55,436 total. See **DATABASE_UPDATE_CN_EN.md** for dataset counts, provenance,
SQL examples and the distinction between this batch import and daily collectors.

## Offline reproduction

Use Python3.12+ with `requirements.txt` (actual analysis used Python3.13).

```bash
python3 src/run_tests.py
python3 src/build_delivery.py
python3 src/make_notebook.py
```

The executed notebook also reruns calculations offline. To rebuild the financial source
reconciliation separately, install pypdf and run `python3 src/extract_financial_guarantees.py`.
Optional live collection is in `src/collect_sources.py`; it is not needed for offline reruns.
`prepare_plan.py` was used only to freeze inputs from the original workspace.

Do not overwrite the original October16 tests or infer a pass from matching IDs.
Review `data_quality_amendment.json` before using PQD23.2.1. Historical rule versions,
publication lags, quarterly revision vintages and service-specific outcome gaps remain limits.

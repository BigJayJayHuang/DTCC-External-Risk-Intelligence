# Twelve risk families: FICC / ECS associations

Start with 十二类风险关联分析_中文说明.md or the executed notebook.

The package contains 20 distinct risk indicators across 12 taxonomy families, 26 scoped series, 572 quarterly observations, and 482 same/next-quarter comparisons against 13 business series. ECS is represented separately by NSCC and DTC. These are exploratory associations, not causal effects or calibrated loss scores. All 482 comparisons fail exploratory BH FDR 5%.

Data cutoff: 2026Q2. New public snapshots were collected on 2026-10-05 America/New_York (2026-10-06 UTC); individual timestamps and hashes are in source_manifest.json. Reused PQD timestamps and hashes are separate. Official provider histories are selected products; DTCC supplier use is unverified. Missing history stays missing. DTC lacks two clearing-specific primary proxies.

To reproduce using the included snapshots in a Python 3.12 environment:

1. Install requirements.txt in your own virtual environment.
2. Run `python src/prepare_expansion.py` to rebuild risk observations from included public snapshots and PQD workbooks.
3. Run `python src/analyze_expansion.py` to rebuild the full association results.
4. Open and run Twelve_Risk_Families_FICC_ECS.ipynb from this directory to rebuild the plots and inspect results.

The original business financial PDFs are not duplicated in this package. Processed financial inputs, exact source URLs, hashes, PDF pages, derivation formulas and reporting periods are included for provenance. Re-extracting those original financial PDFs requires retrieving them from their recorded official public URLs or using the original parent project. The old financial risk seed is preserved, not independently re-collected in this expansion.

Optional source refresh: `python src/collect_sources.py`, then `python src/collect_histories.py`. Network access is required. FRED can intermittently fail; the delivered snapshots include successful retries with initial failures preserved in the manifest. Reconcile download success before rebuilding. A refresh uses current-vintage data and may change prior values.

Do not treat revenue associations as service reliability or realized loss. Further work needs direct asset/vendor exposure mapping, incidents, employee data and actual business-impact labels. Only 12 quarters overlap across all available primary proxies and revenue series; an all-risk joint machine-learning model would have too little data for credible validation.

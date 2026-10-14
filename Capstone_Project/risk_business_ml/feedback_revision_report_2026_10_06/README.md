# PQD feedback review and supplemental tests

Completed October 6, 2026. Both languages use the same frozen observations through 2026Q2.

## Deliverables

- `output/PQD_Feedback_Review_and_Supplemental_Tests_CN.docx`: Chinese report, 7 pages.
- `output/PQD_Feedback_Review_and_Supplemental_Tests_EN.docx`: English report, 7 pages.
- `output/PQD_Feedback_Review_CN_EN.html`: portable bilingual report with the complete 882 statistical records, filters and source inspection.

The extension separates business responses from buffer adequacy. It is post-result exploratory work. It does not validate causal transmission, risk weights, a production risk score, or an untouched out-of-sample test.

## Evidence

The original analysis under `../event_vulnerability_tests_2026_10_06/` remains unchanged. This extension reuses 22 official spreadsheets and the 2024Q4 PDF, adds 207 raw field values and retains 69 service-quarter observations. Seven external indicators, seven response formulations, three services and two lags produce 294 comparisons for each of three samples.

- `analysis_plan.json`: definitions fixed before running the supplementary statistics, after earlier results had already been reviewed.
- `data/response_cell_evidence.csv`: raw values, USD conversion, workbook cells or PDF page, URLs and source hashes.
- `data/response_quarterly.csv`: service-quarter panel.
- `data/response_pair_evidence.csv`: exact stress and outcome pairings.
- `results/response_correlations.csv`: every comparison, ordinary p and BH q, block-bootstrap interval and first-difference diagnostic.
- `results/display_cases.csv`: six predefined descriptive examples with both lags.
- `source_manifest.json`: reused source provenance and original collection timestamps.
- `results/verification_stats.json`: independent recalculation of all 882 correlations and three BH families, unit checks and preservation of the original files.
- `results/verification_documents.json`: bilingual narrative, table values and document checks.

## Reproduce

From the Capstone Project directory, use `risk_business_ml/.venv/bin/python` to run `src/analyze_responses.py` and `src/write_report_content.py` in this folder. The Word builder `src/build_word_reports.py` uses the Codex bundled Python runtime with python-docx. Before changing the report, preserve its exploratory status and full comparison family.

The narrative generator updates the authored app snapshot. Copy the new `report_content.json` to `report_app/src/content/report/report-copy.json`, set the app snapshot buildStatus to complete only after verification, and build/export through the installed Data app scripts described in `report_app/AGENTS.md`.

Both Word files were rendered with the documents skill renderer, the bundled headless LibreOffice and its fontconfig file. All 14 final pages were inspected. Intermediate PDFs and images under `.build/` are internal quality checks, not additional requested deliverables.

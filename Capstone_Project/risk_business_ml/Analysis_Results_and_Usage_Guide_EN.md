# Risk Types and Business Metric Association Analysis

Data collection date: **October 5, 2026**. The latest business reporting period is **2026Q2**. This analysis examines how different types of risk conditions and business metrics change together.

The analysis covers 6 risk proxies × 13 business metric series, producing 78 association comparisons. Thirteen Ridge models were also trained and compared with a baseline that uses quarter-of-year patterns and the previous quarter's business change.
Some positive and negative relationships were observed, but none passed the exploratory multiple-comparison test at the 5% level. In 5 of the 13 models, adding risk proxies reduced holdout mean absolute error (MAE). Each holdout contains only 2–4 quarters, so these results do not establish stable explanatory performance.

## Main Observations

| Business scope | Business metric | Risk proxy | Quarters | Spearman ρ | Pearson r |
| --- | --- | --- | --- | --- | --- |
| FICC/GSD | QoQ growth in average daily cleared trade sides | Change in market volatility | 22 | +0.551 | +0.435 |
| NSCC | QoQ revenue growth | Number of Federal Reserve monetary policy announcements | 20 | -0.460 | -0.211 |
| FICC/GSD | QoQ growth in average daily cleared notional value | Funding market pressure proxy | 20 | +0.456 | +0.383 |
| FICC | QoQ revenue growth | Funding market pressure proxy | 26 | +0.455 | +0.500 |
| FICC/GSD | QoQ growth in average daily cleared notional value | Interest-rate repricing | 20 | -0.426 | -0.371 |
| FICC | QoQ change in operating profit margin | Funding market pressure proxy | 26 | +0.381 | +0.339 |

Spearman ρ measures the relationship between rankings; Pearson r measures the linear relationship. A positive value means that higher risk-proxy values generally coincide with higher business changes, while a negative value means they generally coincide with lower business changes. Neither coefficient is a risk probability or a percentage causal impact.

The positive association between GSD clearing volume growth and changes in volatility warrants further investigation. The correlation between FICC revenue growth and the funding basis is sensitive to 2020: excluding that year reduces Pearson r from approximately 0.50 to approximately 0.22. Higher clearing activity or revenue may also accompany greater workloads and risk exposure, so it does not demonstrate safer clearing.

Revenue is also affected by fee policies, participant refunds, and one-time rebates, which were not separately controlled for in the models. For example, NSCC's 2021 report disclosed $75 million in rebates for that year, and FICC's 2020 report disclosed a $26 million one-time rebate in 2019 (physical page 10 of each annual report). Revenue changes therefore cannot be attributed entirely to external risk conditions.

## Data Used

- **65 financial reports** for FICC, NSCC, and DTC, yielding **75 entity-quarter records**. FICC has 27 quarters from 2019Q4–2026Q2; DTC has 25 quarters; NSCC has 23 quarters.
- **23 quarters** of FICC/GSD and FICC/MBSD activity data from 2020Q4–2026Q2. “Sides” counts trade sides rather than transactions. “Daily notional” means average daily cleared notional value, not revenue.
- **6 FRED risk series**, containing **11,809 date-series records**, including missing observations on holidays. VIX, Treasury yields, and funding rates are daily series; credit conditions are weekly.
- **1,206 validated announcement headlines** from the Federal Reserve's official 2019–2026 archives. Combined with the original 75 news documents, the deduplicated collection retains **1,263 news evidence documents**. Historical announcement-count features use only the Federal Reserve source.

The financial data cover FICC and the ECS-related legal entities NSCC and DTC. NSCC also includes activities such as wealth management, and DTC includes activities such as asset services. Neither entity's total financial results represent a standalone ECS segment. The other eight business lines listed in the kickoff lack sufficient historical quantitative data and were not assigned fabricated results.

## Risk Indicator Definitions

| Risk proxy | Calculation | Unit |
| --- | --- | --- |
| Change in market volatility | 100 × (current-quarter average VIX / previous-quarter average VIX − 1) | % |
| Interest-rate repricing | Current-quarter-end 10-year US Treasury yield − previous-quarter-end yield | Percentage points |
| Change in credit conditions | Current-quarter average NFCICREDIT − previous-quarter average | Index points |
| Funding market pressure proxy | SOFR − EFFR on matching dates, expressed in basis points; take the quarterly maximum | Basis points |
| Regulatory announcement activity | Number of official archive announcements categorized as `bcreg` or `enforcement` | Headlines per quarter |
| Monetary policy announcement activity | Number of official archive announcements categorized as `monetary` | Headlines per quarter |

Volatility, interest rates, credit conditions, and funding conditions are proxies for the external financial environment. They may relate to Clearing and Settlement Financial Risks in the project taxonomy, but they do not replace data on participant positions, margin coverage, defaults, or liquidity shortfalls.

Regulatory and monetary policy announcement counts measure communication activity only. The analysis does not assess the announcements' direction, relevance, or severity. News evidence remains unreviewed; keyword-based candidate classifications were not treated as verified risk labels.

## Data Issues Addressed

- Financial statement amounts were originally reported in USD thousands and were converted to USD. Three-month values were stored separately from cumulative six- and nine-month values. Where necessary, Q4 was derived by subtracting nine-month year-to-date totals from full-year totals. Calculation formulas, filenames, page numbers, and source links were retained.
- **164 reconciliations** compared reported quarterly values with values derived from cumulative totals. The largest difference was **$1,000**, consistent with the original thousand-dollar reporting precision. No discrepancy exceeded that precision.
- DTC 2022Q4 and NSCC 2020Q3, 2020Q4, and 2025Q4 lacked recoverable data and remain missing. Complete calendar-quarter indexes were established before calculating QoQ changes or lagged controls, preventing a two-quarter change from being mislabeled as a one-quarter change.
- The 2021Q3 GSD/MBSD XLSX notional amounts were not entered in USD. The corresponding PDF confirmed that the values were in USD millions. They were normalized using the original units, with supporting evidence recorded.
- The 2022Q3 GSD/MBSD notional amounts had unresolved magnitude inconsistencies in both XLSX and PDF formats. Those amount observations were excluded. As a result, notional-value growth is missing for 2022Q3 and 2022Q4; the trade-sides series is unaffected.
- No XLSX was available for 2024Q4. GSD/MBSD data were recovered from PDF page 23, retaining the original rounding of notional values to USD millions.
- NSCC's OTC/Exchange descriptions changed over time. Both categories were preserved separately and excluded from clearing-activity modeling; they were not added together.
- Repeated annual financial figures and rolling 12-month incident counts in the Public Quantitative Disclosures (PQD) were not treated as independent quarterly targets.

## How Machine Learning Was Used to Examine Associations

Each entity/metric series was modeled separately, using quarters as time observations. Multiple entities in the same quarter were not counted as additional independent time observations.
Business targets were QoQ revenue growth, changes in operating profit margin, and changes in net profit margin. GSD/MBSD models also examined QoQ growth in average daily cleared notional value and trade sides.

The model is **Ridge regression**, a regularized linear regression approach appropriate for a small sample with potentially correlated risk indicators.
The **baseline** uses quarter-of-year patterns and the previous quarter's business change. The **risk-augmented model** adds the six risk proxies to that baseline.
Only missing previous-quarter control values were imputed using the training-set median, with a missingness indicator added. Actual business targets and risk observations were not fabricated or filled in.

Training data end at **2025Q2**. Four chronologically ordered validation windows within the training period were used to select the regularization strength from **1, 10, and 100**. **2025Q3–2026Q2** was reserved for the final holdout comparison. Standardization and median imputation were fitted only on the training data for each split.

| Business scope | Business metric | Training/test quarters | Test MAE | Error reduction after adding risks |
| --- | --- | --- | --- | --- |
| DTC | QoQ change in net profit margin | 19/4 | 3.80 | -2.7% |
| DTC | QoQ change in operating profit margin | 19/4 | 4.20 | -3.1% |
| DTC | QoQ revenue growth | 19/4 | 4.15 | -0.7% |
| FICC | QoQ change in net profit margin | 22/4 | 2.26 | -39.9% |
| FICC | QoQ change in operating profit margin | 22/4 | 2.68 | -48.4% |
| FICC | QoQ revenue growth | 22/4 | 5.12 | -57.3% |
| FICC/GSD | QoQ growth in average daily cleared notional value | 16/4 | 3.10 | +1.3% |
| FICC/GSD | QoQ growth in average daily cleared trade sides | 18/4 | 11.26 | +3.4% |
| FICC/MBSD | QoQ growth in average daily cleared notional value | 16/4 | 6.59 | +1.9% |
| FICC/MBSD | QoQ growth in average daily cleared trade sides | 18/4 | 7.80 | +9.2% |
| NSCC | QoQ change in net profit margin | 18/2 | 3.16 | -6.7% |
| NSCC | QoQ change in operating profit margin | 18/2 | 3.90 | +0.3% |
| NSCC | QoQ revenue growth | 18/2 | 5.87 | -23.4% |

**MAE** means mean absolute error. For revenue and clearing-activity growth targets, errors are measured in percentage points of growth. For margin-change targets, errors are measured in percentage points of profit margin. A positive “error reduction after adding risks” indicates improvement; a negative value indicates larger errors. MAE should not be compared directly across targets with different units.

Only **2025Q3 and 2026Q2** provide calculable QoQ changes for NSCC in the holdout period, making those tests particularly limited.

Descriptive associations use all available quarters; the holdout period was not used to select model parameters or hyperparameters. The statistical results also include 95% intervals from four-quarter block resampling, season/trend-adjusted correlations, leave-one-year-out sensitivity checks, and exploratory circular time-shift tests.
Circular-shift tests rely on temporal stability, while the period examined includes institutional and market changes. Their p/q values therefore serve only as exploratory references. Resampling intervals are neither causal-effect intervals nor intervals adjusted for multiple comparisons.

## Conclusions for the Project

The relationships between GSD activity and market volatility, and between FICC revenue and funding conditions, can be recorded as business-association leads requiring review. The current analysis cannot support statements such as “this news item caused a specific business loss,” “this business has a specific risk probability,” or risk scores for all ten business lines.

The data are the latest available historical versions downloaded on the collection date. Historical credit-condition values may be revised, and business comparative columns may have been disclosed later. This is therefore a retrospective same-quarter association experiment, not a verified forecast based only on information available at the time.

The most valuable next inputs are event-level human reviews of business relevance and risk classification, explicit effective dates and severity, and monthly or weekly business outcomes such as clearing failures, margin requirements, liquidity shortfalls, system outages, and regulatory remediation costs. Use actual dates and preserve unknown values; information that was not collected must not be recorded as “no risk.” Historical quarterly financial statements cannot support a weekly risk model.

## Opening the Results and Rerunning the Analysis

- `Risk_Business_Associations.ipynb`: the fully executed analysis notebook, including figures and results.
- `Risk_Business_Associations.html`: an HTML preview of the same notebook that can be opened without installing Python.
- `results/risk_business_associations.csv`: the 78 associations, quarter counts, uncertainty measures, and sensitivity checks.
- `results/model_comparison.csv` and `results/holdout_predictions.csv`: model comparisons and quarterly actual/estimated values.
- `data/business_metric_provenance.csv`: sources and derivations for individual financial values.
- `data/risk_proxy_dictionary.csv`: definitions and interpretation limits for the six risk proxies.
- `raw/`: the original public reports, market data, and announcement archives used in the analysis.

Using **Python 3.12**, run the following commands from this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/prepare_data.py
.venv/bin/python src/analyze.py
.venv/bin/python src/build_delivery.py
.venv/bin/python src/validate_delivery.py
```

These commands recompute the analysis from the collected snapshots in this package. They do not automatically add future data to the historical experiment. Load only trusted `.joblib` model files supplied in this package. All work was performed locally; no DevX cloud resources were created.

## Sources and Attribution

Original financial/PQD materials: [DTCC Financial Statements](https://www.dtcc.com/legal/financial-statements) and [DTCC Policy and Compliance](https://www.dtcc.com/legal/policy-and-compliance). Specific download URLs and file hashes are retained in the original source manifests.

- **CBOE**, CBOE Volatility Index: VIX [VIXCLS], retrieved from [FRED](https://fred.stlouisfed.org/series/VIXCLS).
- **Board of Governors of the Federal Reserve System (US)**, Market Yield on U.S. Treasury Securities at 10-Year [DGS10] and 2-Year [DGS2], retrieved from [FRED DGS10](https://fred.stlouisfed.org/series/DGS10) and [FRED DGS2](https://fred.stlouisfed.org/series/DGS2).
- **Federal Reserve Bank of New York**, Secured Overnight Financing Rate [SOFR] and Effective Federal Funds Rate [EFFR], retrieved from [FRED SOFR](https://fred.stlouisfed.org/series/SOFR) and [FRED EFFR](https://fred.stlouisfed.org/series/EFFR).
- **Federal Reserve Bank of Chicago**, Chicago Fed National Financial Conditions Credit Subindex [NFCICREDIT], retrieved from [FRED](https://fred.stlouisfed.org/series/NFCICREDIT). All listed FRED series are distributed by the **Federal Reserve Bank of St. Louis**. Collection date: **October 5, 2026**.
- **Board of Governors of the Federal Reserve System**, [official historical press release archives](https://www.federalreserve.gov/newsevents/pressreleases.htm). Collection date: **October 5, 2026**. Headlines were used for announcement counts, not interpreted as a complete set of actual events or DTCC-specific risks.
- Methodology: [scikit-learn guidance on data leakage](https://scikit-learn.org/stable/common_pitfalls.html) and [Ridge documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).

This package is a private academic analysis deliverable. Public-source attribution and licensing requirements remain applicable. The package has not been publicly published.

## Delivery Validation

The notebook was executed end to end in a fresh kernel. All **13 code cells** completed successfully, and **6 figures** were saved. Checks of original file hashes, source samples, calendar-gap handling, all 78 correlations, and model holdout results passed. All six saved figures were visually inspected, and overlapping labels were corrected.

The HTML preview was exported, and its tables and embedded images were checked. The current tool prohibits opening local `file` pages in the browser, so the complete HTML page has not been visually inspected in a browser. You can open it directly in a browser on your own computer.

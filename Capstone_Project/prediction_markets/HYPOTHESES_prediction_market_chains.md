# Prediction-market chains: hypotheses v1 (Nov 25, 2026)

Full cards with diagrams and test recipes: `Prediction_Market_Chains_Transmission_Chain_Hypotheses_v1.docx` (same folder). Nothing here has been tested; freeze the recipes before running.

## How Kalshi feeds existing chains (no new chain needed)
- **Fed decision repricing** (`KXFEDDECISION`) → FICC-GSD-01, FICC-MBSD-01, RDS-02, AS-02. Weekly repricing in pp; must pass Test 1 (`test1.py`) before it can set a shock.
- **CPI** (`KXCPI`, ticker to confirm) → FICC-GSD-01, RDS-02.
- **Recession odds** → XE-MEMBER, RDS-03A as card context only.

## FICC-DEBT-01 · Debt-ceiling standoff → Treasury payment risk → FICC settlement and collateral (Tier 1)
- **Event:** debt limit not raised as the Treasury's X-date approaches.
- **Signal:** 1-month minus 3-month T-bill yield (FRED DGS1MO − DGS3MO), daily. Kalshi debt-limit probability feeds the rubric when a market is open.
- **Mechanism:** investors shun X-date Treasuries → discounts and fails rise → FICC handles delayed-payment CUSIPs, haircuts and higher GSD fails.
- **Test variable:** NY Fed primary-dealer fails to deliver in Treasuries, weekly, log ratio to 52-week median.
- **Vulnerability:** FICC GSD payment_to_qlr (PQD 7.3.4 ÷ 7.1).
- **Windows:** 2011-07-25 to 08-05 · 2013-10-07 to 10-17 · 2023-05-15 to 06-02.
- **Test 1:** standard daily (90th percentile of prior 252 days), 2 of 3 windows. **Test 2:** event study, fails higher in all 3 windows and one-sided Mann-Whitney p < 0.05.

## XE-SHUTDOWN-01 · Government shutdown → SEC/CFTC staff furloughed → DTCC rule filings and approvals stall (Tier 2)
- **Signal:** Kalshi shutdown probability (`KXGOVSHUT`, `KXSHUTDOWNBY`) → rubric certainty; shutdown date → timing. `signals.py` scores it with rubric v1.2 and flags it for review.
- **Mechanism:** furloughed staff → NSCC, FICC and DTC rule filings wait; data releases can slip.
- **Supporting outcome:** days from filing to SEC approval for DTCC filings pending during shutdowns (manual pull).
- **Vulnerability:** DTCC filings pending at the SEC when the shutdown starts.
- **Windows:** 2013-10-01 to 10-16 · 2018-12-22 to 2019-01-25 · 2025-10-01 to 11-12.
- **Test 1:** rubric back-test; where Kalshi history exists (2025), probability above 70% at least 3 days before the start. Shock-only card, confidence capped at Low/Medium.

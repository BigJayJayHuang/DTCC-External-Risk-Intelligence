# Chain validation — frozen test spec v1

Status: **FROZEN v1 — 2026-10-16**, approved by the chain owner before any test in this round was run. Decisions D1–D9 below were approved verbatim; any later change goes in the change log (section 12).
Sources: `FICC_Transmission_Chain_Hypotheses_v1_EN.docx` (2026-10-15) and `ECS_Transmission_Chain_Hypotheses_v2.docx` (2026-10-16), both in `Capstone_Project/`.
Scope: core chains only — FICC-GSD-01, FICC-GSD-02, FICC-GSD-03, FICC-GSD-04, FICC-MBSD-01, ECS-NSCC-01, ECS-NSCC-02, ECS-NSCC-03, ECS-SET-01, ECS-NSCC-04.

Text in quotation blocks is copied from the cards. Where the cards were silent, the approved decision is given as **Dn** (resolved 2026-10-16).

### Approved decisions

| # | Decision |
|---|---|
| D1 | GSD-02 test variable = `REPO-GCF_AR_OO-F − REPO-DVP_AR_OO-F` (overnight/open, all collateral), OFR **Final** series only; preliminary data excluded |
| D2 | New field `peak_payment_to_qlr` = PQD 7.3.4 ÷ quantified 7.1 sum. Existing 7.3.1-based `payment_to_qlr` unchanged. Every card citing 7.3.4 uses the new field |
| D3 | MBSD-01 2022 window = 2022-09-21 to 2022-10-14 (FOMC 75bp hike through end of BoE gilt intervention; chosen from external events, not the signal) |
| D4 | Outside-window = exclude each window ±20 business days (weekly tests: weeks overlapping that span). 2-window cards need 2/2; 4-window cards need 3/4; 3-window cards need ≥2/3 |
| D5 | Weekly re-run rule for GSD-02, GSD-04, NSCC-04 = GSD-01 rule: weekly peak > 90th percentile of prior 52 weeks, current week excluded (≥26 prior weeks; weeks end Friday). The card criteria are hit ≥2/3 and outside ≤15%; the 25% median-share criterion is not part of the weekly rule |
| D6 | GSD-01 and MBSD-01: card spec is the primary test; no extra "changes" run |
| D7 | NSCC-03: volume = daily sum of `Total Shares` over all Cboe-listed venues incl. TRFs; fails = weekly MEAN of daily total fail value (Σ quantity × price); shock week = volume weekly peak > 90th pct of prior 52 weeks; controls = month-end-week, quarter-end-week, T+1 regime (≥ 2024-05-28) dummies; Newey–West HAC 4 lags; primary = same week, secondary = next week |
| D8 | GSD-03 Test 2: descriptive table only (mean daily Sponsored `TOTAL_AMOUNT`, 60 business days before vs after each past milestone). Pass/fail decided by the chain owner |
| D9 | Bootstrap seed 20261016 |
| GSD-02 HAC | Card says HAC without lag; Newey–West with maxlags = floor(4·(T/100)^(2/9)) (the proposed C5 rule; D7 fixes NSCC-03 only) |
| Data | SEC FTD via sec.gov with the approved User-Agent; DTCC fail rates from the T+1 After-Action Report (Sept 2024) and Wayback snapshots of Equities by the Numbers (each logged); if fewer than 3 months before and after a milestone are available, SET-01 is a before/after check only. PQD 19.1.3 → 19.1.3.2 for GSD (5 quarters only); MBSD/NSCC "vulnerability: no data" |

## 0. Rules common to all chains

| Item | Rule | Source |
|---|---|---|
| One signal, one test variable per card | Exactly as on the card; no extra comparisons | Cards §1/§2; brief rule 2 |
| Mechanism (Step 2) | Not tested | Cards |
| Vulnerability variable | Scoring only; never used in Test 2 | Cards; brief rule 3 |
| Standard Test 1 (daily) | "alert when the daily value is above the 90th percentile of the prior 252 trading days (excluding the current day, at least 126 prior values). Pass if alerts hit at least 2 of 3 relevant windows, at least 25% of days alert in the median window, and the alert rate outside windows is 15% or less" | ECS card text; brief Phase 2 step 2 |
| Standard Test 2 (quarterly) | "quarterly max of the daily signal vs the same-quarter test variable (lag 0). Pass if Spearman rho ≥ 0.3 and the 4-quarter block-bootstrap 95% interval lower bound > 0, on both levels and quarter-on-quarter changes. Report lag 1 as secondary" | ECS card text; brief rule 4 |
| Shared-trend flag | If levels pass but changes don't: flag "possible shared trend" | Brief rule 4 |
| Multiple testing | Benjamini–Hochberg across all primary Test 2 p-values (quarterly Spearman p and event-study HAC p); report raw and adjusted. Case-evidence chains have no p-value | Brief Phase 2 step 4 |
| Confidence | Both pass → High; Test 1 pass + Test 2 inconclusive → Medium; no market indicator, logic and cases only → Low/Medium; Test 1 fail or Test 2 significant in the wrong direction → revise/drop | Cards |
| Bootstrap | 4-consecutive-quarter moving blocks, 2000 replicates, blocks never span a missing quarter (reuses `block_ci` in `event_vulnerability_tests_2026_10_06/src/run_analysis.py`). Seed **20261016** (D9) | Existing code |
| Data cut-off | Daily: latest available at fetch time. PQD: 2020Q4–2026Q2 (23 quarters). OFR "Final" series end 2026-06-30 | Repo |

**Common rules (resolved):** C1 → D4; C2 → D4; C3 → D5; C4 → D6; C5 → D7 (NSCC-03) and the GSD-02 HAC row above. Original proposals kept for the record:

- **C1. Outside-window exclusion.** The cards don't define "outside windows". Proposal: reuse the 10/6 rule (exclude each window ±20 business days; for weekly tests, ±4 weeks). Alternative: exclude only the windows themselves.
- **C2. "≥ 2 of 3" when a card lists 2 or 4 windows.** Proposal: apply as hit fraction ≥ 2/3 (2 windows → 2/2; 4 windows → 3/4), as the 10/6 code did.
- **C3. Weekly-peak re-runs with no weekly rule written** (GSD-02, GSD-04, NSCC-04 say "re-run once with weekly peaks to confirm"). Proposal: use the GSD-01 weekly rule (weekly peak > 90th percentile of prior 52 weeks, excluding the current week; ≥ 26 prior weeks; weeks end Friday). For a weekly test, "in-window alert share" means the share of window weeks that alert.
- **C4. "Levels and changes" for GSD-01 and MBSD-01**, whose test variables are already quarter-on-quarter changes. Proposal: the primary test is exactly the card spec (signal quarterly max vs QoQ change of the PQD field). The changes check is the QoQ change of the signal quarterly max vs the same QoQ change of the PQD field. Alternative: a second difference of the PQD field, which is not recommended.
- **C5. HAC lag length** for the event studies (GSD-02 daily, NSCC-03 weekly). Proposal: Newey–West with maxlags = floor(4·(T/100)^(2/9)).

## 1. FICC-GSD-01 Treasury market volatility (v1)

- Signal: "Absolute daily change in the 10-year Treasury yield, weekly peak — FRED DGS10, 2018 to now". Repo: `market_daily.csv` DGS10; the transform reuses `ust10_abs_change`, then takes the weekly max.
- Test variable: "Quarter-on-quarter change in GSD margin requirement (PQD 6.1.1), same quarter". Repo: `pqd_quarterly.csv` `initial_margin_required_usd` (GSD).
- Vulnerability (scoring only): "Cover-1 stress loss ÷ quarter-end margin (PQD 4.4.3 ÷ 6.1.1). Higher = more vulnerable" → `stress_loss_to_im`.
- Windows: 2020-03-09–03-23 COVID; 2023-03-08–03-17 SVB; 2025-04-02–04-11 Treasury shock.
- Test 1:
  > Re-run with weekly peaks: alert when the weekly peak exceeds the 90th percentile of the prior 52 weeks (excluding the current week); hit ≥ 2/3 of relevant events; alert rate outside events ≤ 15%
- Test 2:
  > Quarterly max of the daily 10-year change vs same-quarter GSD margin change; Spearman rho ≥ 0.3 and the 4-quarter block-bootstrap 95% interval lower bound > 0
- Prior results seen: yes (same-quarter rho 0.408, per the card).
- Notes: the card's Test 1 has no "median in-window share ≥ 25%" criterion; it is not applied. QoQ change requires 2021Q1 onward (22 quarters). The COVID window predates PQD coverage, so only 2023 and 2025 fall inside Test 2's sample.

## 2. FICC-GSD-02 Repo funding pressure (v1) — pilot

- Signal: "SOFR − EFFR, quarter-end adjusted, weekly peak — FRED, from 2018-04". Repo: reuses `sofr_effr_adjusted` from `run_analysis.py`, on `market_daily.csv`.
- Test variable: "Rate dispersion in FICC-cleared repo (DVP / GCF), daily. Pick one before running: DVP 99th − 1st percentile rate; or GCF − DVP spread. Source: OFR Short-term Funding Monitor".
  - **Data finding:** the OFR API publishes no DVP percentile series, only average rates, volumes, and outstanding amounts (checked 2026-10-16, `dataset=repo`, 164 mnemonics). The percentile option is therefore unavailable from public API data.
  - **Resolved (D1):** GCF − DVP overnight, Final. Original note: Proposal: `REPO-GCF_AR_OO-F − REPO-DVP_AR_OO-F` (overnight/open on both legs, so tenor-matched; Final vintage; daily from 2018-05-07 to 2026-06-30). Alternative: `REPO-GCF_AR_T-F − REPO-DVP_AR_OO-F` (Treasury-only GCF collateral).
- Vulnerability (scoring only): "Largest payment obligation ÷ qualifying liquid resources (PQD 7.3.4 ÷ 7.1)" → **resolved (D2)**, original note: the existing `payment_to_qlr` field uses 7.3.1 (stress payment obligation), not 7.3.4. The card text says 7.3.4. Proposal: compute 7.3.4 ÷ 7.1 as the card says (`actual_peak_payment_t12m_usd / qlr_quantified_sum_usd`), and keep `payment_to_qlr` unchanged.
- Windows: 2019-09-16–09-20 repo spike; 2020-03-09–03-23 COVID; 2025-04-02–04-11 Treasury shock.
- Test 1:
  > Original test already passed; re-run once with weekly peaks to confirm

  Rule per C3.
- Test 2:
  > Event study: shock days = days when adjusted SOFR − EFFR exceeds the 90th percentile of the prior 252 days. Regress the test variable on a shock-day dummy plus month-end and quarter-end dummies; shock-day coefficient > 0 with p < 0.05 (HAC standard errors)
- Prior results seen: signal yes; test variable no.

## 3. FICC-GSD-03 Treasury clearing mandate (v1) — no market indicator

- Signal: none (rubric, designed separately).
- Test variable: "DTCC public Sponsored activity statistics, plus public case evidence around past milestones". Repo: `data_refresh_2026_10_14/data/ficc_daily_operations_history.csv`, metrics `TOTAL_AMOUNT`, `DVP_TOTAL_AMOUNT`, `GC_TOTAL_AMOUNT`, `TOTAL_REPO_AMOUNT`, `TOTAL_REVERSE_REPO_AMOUNT` from source `ficc_sponsoredvolume`. **Confirmed: this is Sponsored volume**, daily, 2021-08-16 to 2026-10-09 (1,285 days per metric).
- Vulnerability (scoring only): "Top-5 members' share of client transactions (PQD 19.1.3)".
  - **Data finding:** the PQD splits 19.1.3 into 19.1.3.1 (peak) and 19.1.3.2 (average). GSD reports N/A from 2020Q4 to 2025Q1; values exist only for **2025Q2–2026Q2 (5 quarters)**. MBSD and NSCC are N/A throughout.
  - **Resolved:** 19.1.3.2 for GSD. Original note: proposal is to use 19.1.3.2 (average), consistent with 18.2.2 `AverageInQuarter`. With only 5 quarters, the own-history percentile is very coarse.
- Milestones: 2023-12 SEC adopts the rule; 2025-02 SEC extension; 2026-12-31 cash compliance (upcoming); 2027-06-30 repo compliance (upcoming).
- Test 1:
  > No statistical test. Confirm each milestone has a public source (SEC release or rule text)
- Test 2:
  > At least 1 past milestone with public evidence that GSD Sponsored volume or the number of onboarded members changed around it
- **Resolved (D8).** Original note: "changed around it" is not quantified. Proposal: report a descriptive before/after table only (mean daily Sponsored `TOTAL_AMOUNT` 60 business days before vs after each past milestone), with no automated pass. The pass is decided by the team with the cited source.

## 4. FICC-GSD-04 Member credit deterioration (v1)

- Signal: "20-day widening in the Baa credit spread, weekly peak — FRED BAA10Y". Repo: reuses `baa_widen20`, then takes the weekly max.
- Test variable: case evidence (candidate: DTCC's account of the 2008 Lehman default management).
- Vulnerability (scoring only): "Top-5 members' share of open positions (PQD 18.2.2)" → `top5_open_share` (GSD).
- Windows: 2020-03-09–03-23 COVID; 2023-03-08–03-17 SVB.
- Test 1:
  > Original test already passed; re-run once with weekly peaks to confirm

  Rule per C3 and C2 (2 windows → both must hit).
- Test 2:
  > At least 1 past event with public evidence that FICC started default management or changed risk measures because of a member credit event. Expected confidence: Medium

## 5. FICC-MBSD-01 MBS spread shock (v1)

- Signal: "30-year mortgage rate − 10-year Treasury yield, absolute weekly change — FRED MORTGAGE30US (weekly), DGS10". MORTGAGE30US is to be fetched (reachable).
  - **Resolved (default accepted):** how DGS10 is aligned to the weekly MORTGAGE30US date. Proposal: DGS10 on the same Thursday (Freddie Mac survey date), or the last available day before it.
- Test variable: "Quarter-on-quarter change in MBSD peak single-day variation margin (PQD 6.7.1), same quarter". Repo: `vm_peak_usd` (MBSD) from the feedback-revision panel (`analyze_responses.py`); it will be re-extracted, not copied.
- Vulnerability (scoring only): "MBSD Cover-1 stress loss ÷ quarter-end margin (PQD 4.4.3 ÷ 6.1.1)" → `stress_loss_to_im` (MBSD).
- Windows: 2020-03-09–03-23 COVID; "2nd half of 2022, rate-hike period (window TBD)"; 2025-04-02–04-11.
  - **Resolved (D3):** 2022-09-21 to 2022-10-14.
- Test 1:
  > Alert when the weekly spread change exceeds the 90th percentile of the prior 52 weeks (excluding the current week); hit ≥ 2/3 of relevant events; alert rate outside events ≤ 15%
- Test 2:
  > Quarterly max absolute weekly spread change vs same-quarter change in MBSD 6.7.1; Spearman rho ≥ 0.3 and the 4-quarter block-bootstrap 95% interval lower bound > 0
- Prior results seen: no.

## 6. ECS-NSCC-01 Equity selloff → NSCC variation margin (v2) — v2 candidate

- Signal: "VIX jump = VIX ÷ its own 20-day average, weekly peak — FRED VIXCLS". **Resolved (default accepted):** the 20-day average includes the current day (trailing 20 observations including today).
- Test variable: "Peak single-day VM ÷ average daily VM (PQD 6.7.1 ÷ 6.6.1; repo field vm_peak_to_avg)" (NSCC).
- Vulnerability (scoring only): "PQD 7.3.4 ÷ 7.1" — see G2-b.
- Windows: 2020-03-09–03-23; 2021-01-25–01-29; 2024-08-05–08-09; 2025-04-02–04-11 (4 windows; see C2).
- Test 1: standard daily Test 1 (section 0).
- Test 2: standard quarterly Test 2 (section 0), lag 0 primary, levels and changes; lag 1 secondary.
- **Label:** "v2 candidate, needs confirmation on data not used before (e.g., 2026Q3 PQD)". It was chosen after seeing the Oct 15 lag-1 run. The Oct 15 run's code and output are **not in this repo**, so they cannot be reproduced here.

## 7. ECS-NSCC-02 Funding squeeze → NSCC variation margin (v2) — v2 candidate

- Signal: "SOFR − EFFR, quarter-end adjusted, weekly peak — FRED".
- Test variable: `vm_peak_to_avg` (NSCC).
- Vulnerability (scoring only): "PQD 7.3.4 ÷ 7.1" — see G2-b.
- Windows: 2019-09-16–09-20; 2020-03-09–03-23; 2025-04-02–04-11.
- Test 1:
  > Already passed on Oct 6 (3 of 3); re-run once under the standard to confirm

  This is the daily standard.
- Test 2: standard quarterly Test 2.
- **Label:** v2 candidate (as in section 6).
- Notes: the test variable and process are shared with NSCC-01. The card's display rule is to use the higher shock score; that is a scoring rule, not a test rule.

## 8. ECS-NSCC-03 Volume surge → NSCC settlement fails (v1)

- Signal: "US consolidated equity volume, weekly peak — Cboe U.S. equities market volume summary". Source: `cdn.cboe.com/.../market_history_YYYY.csv`, per-venue daily rows (exchanges plus FINRA TRFs), 2009 onward. Reachable.
  - **Resolved (D7):** total shares. Original note: proposal was daily consolidated volume = sum of `Total Shares` across all listed market participants. Alternative: `Total Trade Count`, which is closer to the card's mechanism ("trade count surges").
- Test variable: "Fails-to-deliver, aggregated weekly (SEC FTD data)".
  - **Resolved (D7):** weekly mean of daily Σ quantity × price. Original note: the SEC files report the outstanding fail balance (shares) per security per settlement date. Proposal: daily total fail value = Σ quantity × price, with weekly mean of the daily totals. Alternative: weekly sum, or shares instead of value.
- Vulnerability: none (shock-only rule).
- Windows: 2020-03-09–03-23; 2021-01-25–01-29; 2025-04-02–04-11.
- Test 1: standard daily Test 1.
- Test 2:
  > Event study: shock weeks (volume above the 90th percentile of the prior 52 weeks) vs other weeks, controlling for month-end and quarter-end. Pass if fails are higher in shock weeks with p < 0.05 (HAC standard errors)

  Month-end and quarter-end weeks are the weeks containing those dates (C5 for HAC).

## 9. ECS-SET-01 Shorter settlement cycle → NSCC and DTC fails (v2) — no market indicator

- Signal: none (rubric).
- Test variable: "NSCC and DTC monthly fail rates (DTCC Equities by the Numbers)". **Data finding:** the live page shows only the current month (Aug 2026) and a May 2024 baseline; no monthly history is published there.
- Vulnerability: none (shock-only).
- Milestones: 2023-02-15 SEC adopts T+1; 2024-05-28 US T+1 go-live; 24x5 and T+0 milestones still to be compiled.
- Test 1:
  > No statistical test. Confirm each milestone has a public source (SEC release or DTCC notice)
- Test 2:
  > One event study, two outcomes: fail rate in the 3 months after each milestone vs the 3 months before, for NSCC and DTC separately. Until monthly history is pulled, report as a before/after check only

## 10. ECS-NSCC-04 Broker distress → NSCC default management (v1)

- Signal: "Baa credit spread, 20-day widening, weekly peak — FRED BAA10Y". This is the same signal and the same Test 1 as GSD-04, but a different process (NSCC rather than FICC), so it is not double-counted.
- Test variable: case evidence (candidate: SEC staff report on early-2021 market conditions).
- Vulnerability (scoring only): `top5_open_share` (NSCC, PQD 18.2.2).
- Windows: 2021-01-25–01-29; 2023-03-08–03-17.
- Test 1:
  > Already passed on Oct 6; re-run once under the standard to confirm

  Per D5 this re-run uses the weekly rule (it overrides the card's "under the standard" wording), with D4 applied (2 windows → both must hit). Note that the Oct 6 test used different windows (COVID and SVB), so this is not an identical re-run.
- Test 2:
  > Pass if at least 1 past case has public evidence that NSCC changed a member's requirements or started default management because of member stress. Expected confidence: Medium

## 10b. Implementation details (recorded 2026-10-16, before any test was run)

These are mechanical choices the cards and D1–D9 do not fix. They were written down before running, and are not tuned.

- **QoQ change** = growth rate `X(t)/X(t−1) − 1`, matching the existing `im_qoq` field (GSD-01 uses `im_qoq` directly; MBSD-01 uses the same formula on `vm_peak_usd`). For the NSCC changes check, Δsignal = qmax(t) − qmax(t−1) and Δtest variable = `vm_peak_to_avg`(t) − (t−1), consecutive quarters only.
- **Quarterly signal** = max of the daily (or weekly, for MBSD-01) signal within the calendar quarter. Requires ≥ 45 daily or ≥ 10 weekly observations, else missing (the 10/6 rule).
- **Test 1 outside-window rate** uses the full available sample (2025 is now a card window, so there is no holdout). Daily window hit requires ≥ 2 testable days (10/6 rule). Weekly windows = weeks (Sat–Fri, labelled by Friday) overlapping the window; exclusion zone = weeks overlapping [start − 20 BD, end + 20 BD].
- **NSCC-04 Test 1** uses the weekly rule per D5; this overrides the card's "under the standard" wording.
- **GSD-02 event study:** y = (GCF_AR_OO − DVP_AR_OO) × 100 bp on days where both Final values exist. Shock day = daily adjusted SOFR−EFFR > prior-252 90th percentile (the same daily threshold as the 10/6 code). Month-end / quarter-end dummy = the date is the last business day of the calendar month / quarter (amended before running: the GCF overnight Final series is published on only 270 days, so the last observed day in a month is often not month-end). OLS with Newey–West HAC. Pass = coefficient > 0 and two-sided HAC p < 0.05.
- **NSCC-03:** daily fail value = Σ(QUANTITY × PRICE) over all rows of a settlement date; rows with a non-numeric price are dropped and counted. Weekly y = mean of daily values in the week. Month-end / quarter-end week = the week containing the last business day of a month / quarter. Pass = shock coefficient > 0 and two-sided HAC p < 0.05.
- **Quarterly Test 2 classification:** PASS = rho ≥ 0.3 and CI low > 0 (for NSCC-01/02, on both levels and changes). WRONG DIRECTION = rho ≤ −0.3 and CI high < 0. Otherwise INCONCLUSIVE. Event studies: WRONG DIRECTION = coefficient < 0 with p < 0.05.
- **BH family** = primary Test 2 p-values: GSD-01, MBSD-01, NSCC-01 (levels, changes), NSCC-02 (levels, changes), GSD-02, NSCC-03 (8 tests). Spearman p is the ordinary p-value.
- **Vulnerability (informational, not a test):** latest value and its percentile within its own history, with score = ceil(percentile × 5) (1–5), direction per card.

## 11. Outputs

The following go in `results/chain_tests/`:

- `<chain_id>.json`
- `summary.csv` (ID | Test 1 | Test 2 | Confidence | Version | Notes)
- `REPORT.md`
- One figure per chain (signal with shaded windows, plus a Test 2 scatter or event plot)

Code goes in `Capstone_Project/validation/`, run as `python -m validation.run --chain <ID>`. Raw downloads go in `Capstone_Project/data/raw/<source>/` with `SOURCES_LOG.csv`. Post-hoc ideas go only under "Suggested post-hoc changes (v2, untested)".

## 13. Post-hoc v2 runs (written 2026-10-16T07:49Z, AFTER v1 results; approved by chain owner)

The v1 results stay as the baseline. These are labelled **post-hoc v2** everywhere.

### FICC-GSD-02 v2 · Repo funding pressure, Treasury-only GCF
- Reason: data coverage, not results. `REPO-GCF_AR_OO-F` (v1) has values on 270 of 2,034 dates, with none in Sept 2019.
- Test variable: `(REPO-GCF_AR_T-F − REPO-DVP_AR_OO-F) × 100` bp, OFR Final only. This is GCF with Treasury collateral across all tenors, minus DVP overnight/open. The tenor mismatch is recorded as a limitation.
- Everything else is identical to v1, including:
  - signal and Test 1 (unchanged, so not re-run);
  - shock-day definition;
  - calendar business-day month-end and quarter-end dummies;
  - Newey–West lags floor(4·(T/100)^(2/9));
  - pass rule: coefficient > 0 and two-sided HAC p < 0.05.
- Multiple testing: v2 is outside the frozen v1 BH family of 8. The report gives the raw p, plus the q it would have if added as a 9th test.

### ECS-NSCC-04 v2 · Broker distress → NSCC default management, without market indicator
- Reason: the v1 Test 1 failed because Baa is a broad credit index, while January 2021 broker stress was broker-specific. Reclassified as **without market indicator** (rubric + case evidence). No new signal was searched for.
- Signal: none (rubric).
- Test 1: no statistical test. Confirm each event has a public source. Events: January 2021 meme-stock week; March 2023 bank stress (SVB).
- Test 2: unchanged card rule: "Pass if at least 1 past case has public evidence that NSCC changed a member's requirements or started default management because of member stress." Never auto-passed; the owner decides.
- Vulnerability: unchanged (NSCC PQD 18.2.2).
- Confidence class: no market indicator → Low/Medium.
- **Mechanism (rewritten at sign-off, 2026-10-16T07:58Z, part of v2):** concentrated member positions strain the member's capital and liquidity → NSCC raises that member's requirements (special charges / excess capital premium). This replaces the card's credit-distress / default-management wording. Reason: the only verified case (Jan 2021) was an ECP / special charge on concentrated positions relative to member capital, not credit stress or default.

## 14. Pre-registered, NOT RUN: ECS-NSCC-01 v3 and ECS-NSCC-02 v3 (written 2026-10-16T07:49Z)

- **Hypothesis:** the NSCC variation-margin response appears at **lag 1** (signal in quarter t vs test variable in quarter t+1).
- **Signals, test variable, Test 1:** as v2 (VIX ÷ 20-day average; quarter-end-adjusted SOFR−EFFR; `vm_peak_to_avg`).
- **Test 2 (primary):** quarterly max of the daily signal in quarter t vs `vm_peak_to_avg` in t+1. Pass if Spearman rho ≥ 0.3 and the 4-quarter block-bootstrap 95% CI lower bound > 0, on both levels and QoQ changes. Seed 20261016.
- **Confirmation data:** only target quarters **2026Q3 onward**, which were not used in any run so far. Signal quarters t ≥ 2026Q2 pair with PQD t+1 ≥ 2026Q3.
- **Minimum sample:** the test is run only once at least 8 new target quarters exist, because the bootstrap needs consecutive blocks. Until then, new quarters are reported descriptively, with no pass/fail. The minimum was set now, before any 2026Q3 data exists.
- **Why:** lag 1 was identified after seeing the Oct 15 and Oct 16 results (2020Q4–2026Q2), so those data cannot confirm it.

## 12. Change log

| Date | Change | Reason |
|---|---|---|
| 2026-10-16 | Draft created | Phase 1 |
| 2026-10-16 | Frozen v1 with D1–D9 | Chain-owner approval before running |
| 2026-10-16 | Added §10b implementation details | Mechanical choices fixed before any test was run |
| 2026-10-16 ≈07:02Z (logged retroactively ≈07:57Z) | §10 NSCC-04: Test 1 wording aligned to D5 (weekly rule overrides the card's "under the standard") | Was omitted from this log at the time; made before any result |
| 2026-10-16 | GSD-02 month/quarter-end dummies defined on calendar business days (§10b) | Found before running: REPO-GCF_AR_OO-F has values on only 270 of 2,034 dates (none in Sept 2019, 2 in March 2020) |
| 2026-10-16 | Data: DTCC T+1 After-Action Report BLOCKED (Cloudflare 1010); Wayback has no snapshots of the fail-rate page | SET-01 becomes a before/after check from published figures |
| 2026-10-16T07:49Z | Added §13 post-hoc v2 specs (FICC-GSD-02 v2 Treasury-only GCF; ECS-NSCC-04 v2 reclassified without market indicator) | Owner-approved after v1 results; written before running v2 |
| 2026-10-16T07:49Z | Added §14 pre-registration of ECS-NSCC-01/02 v3 (lag 1, 2026Q3+ only; not run) | Lag-1 pattern identified after results; confirmation reserved for unused data |
| 2026-10-16T07:58Z | ECS-NSCC-04 v2 mechanism rewritten (§13): "concentrated member positions strain member capital/liquidity → NSCC raises that member's requirements" | Owner sign-off; matches the verified Jan 2021 case |
| 2026-10-16T07:58Z | Round 1 closed with owner sign-offs (final confidence in REPORT.md and chain_confidence.json) | Owner sign-off |
| 2026-10-16T07:49Z | FICC-GSD-03 Feb-2025 milestone source upgraded to SEC Release No. 34-102487 (90 FR 11134; dated Feb 25, 2025). Date unchanged (2025-02-25) | Primary source supplied by owner |

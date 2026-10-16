# Chain validation report: FICC and ECS core chains

**Spec:** [TEST_SPEC.md](TEST_SPEC.md). v1 was frozen 2026-10-16 before any result. §13 (post-hoc v2) and §14 (v3 pre-registration) were added at 07:49 UTC, after the v1 results.

**Status:** the v1 results (first run 2026-10-16 07:09 UTC) are the accepted baseline and are unchanged. Round 2 (2026-10-16, ~07:45–07:57 UTC) added case evidence, two post-hoc v2 runs, one pre-registration and an audit.

**Re-run:** from `Capstone_Project/`, run `.venv-validation/bin/python -m validation.run [--chain ID]`. Chain IDs include `FICC-GSD-02.v2` and `ECS-NSCC-04.v2`. The bootstrap seed is 20261016.

## ✅ Validation round 1: CLOSED (2026-10-16T07:58Z, owner sign-off)

The final confidence per chain is below. The scoring backend reads [chain_confidence.json](chain_confidence.json), which is regenerated with `python -m validation.export` from `validation/signoffs.py` and the per-chain JSONs. "Active version" is the version the backend uses; superseded rows stay in `summary.csv` for the record.

| ID | Active version | Final confidence | Signal | Test variable | Vulnerability variable | Sign-off / note |
|---|---|---|---|---|---|---|
| FICC-GSD-01 | v1 | **Medium** | \|ΔDGS10\| weekly peak | GSD margin QoQ growth (PQD 6.1.1) | 4.4.3 ÷ 6.1.1 | Test 1 pass; Test 2 inconclusive (rho 0.41, CI lower −0.01) |
| FICC-GSD-02 | **v2 (post-hoc)** | **Medium**, **WATCH** | SOFR−EFFR adjusted, weekly peak | OFR GCF (Treasury) − DVP overnight | 7.3.4 ÷ 7.1 | Accepted. Wrong sign but not significant (−0.67 bp, p 0.095); outside the v1 BH family, q 0.23 if added. **Watch:** re-check the sign as new OFR data arrives. v1 (Medium) superseded |
| FICC-GSD-03 | v1 | **Low** | none (rubric) | Sponsored daily volume | 19.1.3.2 (5 quarters only) | **Not supported**: +21.1% = 80th pct, +5.4% = 33rd pct of normal 60-day changes. Shock score from the rubric |
| FICC-GSD-04 | v1 | **Medium** | Baa 20-day widening, weekly peak | Case evidence | 18.2.2 | **PASS** (owner): DTCC 30 Oct 2008 press release, $190bn GSD and $329bn MBSD close-out. Annual report not needed |
| FICC-MBSD-01 | v1 | **Medium** | \|Δ(MORTGAGE30US − DGS10)\| weekly | MBSD 6.7.1 QoQ growth | 4.4.3 ÷ 6.1.1 | Test 1 pass (2/3); Test 2 inconclusive |
| ECS-NSCC-01 | v2 | **Medium** (v2 candidate) | VIX ÷ 20-day average | `vm_peak_to_avg` (6.7.1 ÷ 6.6.1) | 7.3.4 ÷ 7.1 | Lag-1 v3 pre-registered; confirm on 2026Q3+ |
| ECS-NSCC-02 | v2 | **Medium** (v2 candidate) | SOFR−EFFR adjusted | `vm_peak_to_avg` | 7.3.4 ÷ 7.1 | Possible shared trend; lag-1 v3 pre-registered |
| ECS-NSCC-03 | v1 | **Medium** | Cboe consolidated volume | SEC fails-to-deliver, weekly | none (shock-only) | Test 1 pass; Test 2 inconclusive (p 0.24) |
| ECS-SET-01 | v2 | **Low** (descriptive only) | none (rubric) | NSCC/DTC fail rates | none (shock-only) | Owner: Low. Approximate pre-T+1 baseline = **May 2024 snapshot, NSCC 2.00% / DTC 2.83%**: mostly T+2 days (T+1 began May 28) and **only two points**. After: CNS 1.9% on the first day, July 2024 CNS 2.12% and DTC non-CNS 3.31% (report p.7) |
| ECS-NSCC-04 | **v2 (post-hoc)** | **Low** | none (rubric) | Case evidence | 18.2.2 | **Case rule PASS** (owner), confidence Low: the Jan 2021 trigger was concentrated positions vs member capital (ECP charge), not credit stress or default. **Mechanism rewritten (v2):** "concentrated member positions strain member capital/liquidity → NSCC raises that member's requirements" (TEST_SPEC §13). v1 (Test 1 fail) superseded |

**Tally:**

- High: 0
- Medium: 7 (GSD-01, GSD-02 v2 [watch], GSD-04, MBSD-01, NSCC-01*, NSCC-02*, NSCC-03; *v2 candidates)
- Low: 3 (GSD-03, SET-01, NSCC-04 v2)

**Accepted as is:**

- GSD-02.v2 stays Medium, with a watch note.
- The GSD-02 dummy-timing note (D9).
- The Sponsored-series start date of 2021-10-12 for the audit.
- GSD-02.v2 stays outside the v1 BH family, with q = 0.23 reported alongside.

**Open after round 1:**

- Design the rubric for GSD-03, SET-01 and NSCC-04 v2.
- Test the NSCC-01/02 v3 lag-1 hypothesis once 2026Q3+ PQD quarters accumulate (at least 8).
- Keep watching the GSD-02 v2 sign.

---

## Round 2 table (pre-sign-off; kept for the record)

| ID | Test 1 | Test 2 | Confidence | Version | Evidence source | Needs my sign-off |
|---|---|---|---|---|---|---|
| FICC-GSD-01 | PASS (weekly, 3/3, outside 12.2%) | INCONCLUSIVE: rho 0.41, CI [−0.01, 0.76] | Medium | v1 | FRED DGS10; PQD 6.1.1 | N |
| FICC-GSD-02 | PASS (weekly, 3/3, outside 12.4%) | INCONCLUSIVE: +0.02 bp, p 0.97, n 246 | Medium | v1 | FRED SOFR/EFFR; OFR GCF_AR_OO/DVP_AR_OO Final | N |
| FICC-GSD-02.v2 | PASS (unchanged from v1) | INCONCLUSIVE: −0.67 bp, HAC p 0.095, n 1,728 | Medium | **v2 post-hoc** | OFR GCF_AR_T/DVP_AR_OO Final | N |
| FICC-GSD-03 | Milestones sourced (primary SEC releases) | Descriptive: +21.1% (80th pct of all splits), +5.4% (33rd pct) | Low/Medium | v1 | SEC 2023-247; SEC Rel. 34-102487 (90 FR 11134); FICC Sponsored daily data | **Y**: pass/fail of the descriptive test |
| FICC-GSD-04 | PASS (weekly, 2/2, outside 11.1%) | Case evidence; **proposed PASS** | Medium if confirmed | v1 | DTCC press release, 30 Oct 2008 (owner's copy, PDF p.1–3) | **Y**: case verdict |
| FICC-MBSD-01 | PASS (weekly, 2/3; missed COVID) | INCONCLUSIVE: rho 0.15 | Medium | v1 | FRED MORTGAGE30US, DGS10; PQD 6.7.1 | N |
| ECS-NSCC-01 | PASS (daily, 4/4) | INCONCLUSIVE at lag 0 (lag 1 pre-registered as v3, §14) | Medium (v2 candidate) | v2 | FRED VIXCLS; PQD 6.6.1/6.7.1 | N (await 2026Q3+) |
| ECS-NSCC-02 | PASS (daily, 3/3) | INCONCLUSIVE: levels pass, changes fail → possible shared trend (lag 1 pre-registered as v3) | Medium (v2 candidate) | v2 | FRED SOFR/EFFR; PQD 6.6.1/6.7.1 | N (await 2026Q3+) |
| ECS-NSCC-03 | PASS (daily, 3/3) | INCONCLUSIVE: +$0.50bn, p 0.24 | Medium | v1 | Cboe volume; SEC CNS fails-to-deliver | N |
| ECS-SET-01 | Milestones sourced | Before/after check only (descriptive); T+1 report adds post-T+1 points | Low/Medium | v2 | T+1 After-Action Report p.7; DTCC Aug 2024 article; Equities by the Numbers snapshot; SEC 2023-29 | **Y**: milestones and before/after reading |
| ECS-NSCC-04 | **FAIL** (weekly, 1/2) | Case evidence (kept for the record) | Revise/drop | v1 | FRED BAA10Y; SEC staff report | N (superseded by v2) |
| ECS-NSCC-04.v2 | Events sourced (no market indicator) | Case evidence; **proposed PASS** | Low/Medium if confirmed | **v2 post-hoc** | SEC staff report early 2021, PDF p.16, 32–33 (§3.5) | **Y**: reclassification and case verdict |

Multiple testing: the frozen v1 BH family (8 primary Test 2 p-values) is unchanged; no q < 0.05. GSD-02 v2 is outside that family; if it were added as a 9th test, its q would be 0.23.

## What changed vs the v1 baseline

| Item | v1 baseline | Now |
|---|---|---|
| v1 statistics (all 10 chains) | — | **Unchanged.** Every v1 JSON was compared field by field with a pre-round snapshot. The only difference is the GSD-03 milestone label text, which now names Release 34-102487. |
| FICC-GSD-04 case | Secondary article only; FICC role unconfirmed | DTCC press release passages: GSD closed out $190bn gross, MBSD liquidated a $329bn TBA book. **Proposed PASS.** 2008 annual report MISSING. |
| FICC-GSD-03 Feb 2025 milestone | 2025-02-25, secondary sources | Same date; primary source is Release 34-102487. Before/after table **unchanged**. New audit: whole-sample distribution of 60-day changes. |
| ECS-SET-01 | Release-quoted CNS 2.12%, DTC 3.31% ("period not stated") | Same values now cited to the T+1 report p.7 with the period (July 2024 averages), plus CNS 1.9% on the first T+1 day. The report gives no pre-T+1 numbers. Still before/after only. |
| ECS-NSCC-04 | v1 Test 1 FAIL → revise/drop | v1 kept. New **v2 post-hoc**: reclassified without market indicator; SEC report passages; **proposed PASS**. |
| FICC-GSD-02 | v1 INCONCLUSIVE on 246 days | v1 kept. New **v2 post-hoc** (Treasury-only GCF, 1,728 days): still INCONCLUSIVE, coefficient negative but not significant. |
| ECS-NSCC-01/02 | v2 candidates | Lag-1 hypothesis **pre-registered as v3** (§14); to be tested only on 2026Q3+ PQD. Not run. |
| TEST_SPEC change log | 5 entries | Audited below (§D2), 3 entries added; 1 earlier unlogged wording edit flagged. |

## Round 2 detail

### A1. FICC-GSD-04: Lehman close-out (case evidence)

**Source:** DTCC press release "DTCC closes out Lehman bankruptcy", dated 30 October 2008 (Finextra reprint).

- Automated fetch of https://finextra.com/pressarticle/24287/dtcc-closes-out-lehman-bankruptcy was **BLOCKED** (Cloudflare challenge, HTTP 403; no browser spoofing).
- Passages are quoted from your browser-printed copy `data/raw/DTCC closes out Lehman bankruptcy.pdf`.
- The **DTCC 2008 annual report (sechistorical part 1) was not in `data/raw/`**, so it's logged as MISSING. Its two facts you asked for ($500bn total; close-out announced Oct 30, 2008) are both in the press release.

**Passages:**

- PDF p.1: DTCC "announced today that it successfully closed out over $500 billion in market participants' exposure from the Lehman Brothers, Inc. (Lehman) bankruptcy". Dated 30 October 2008.
- PDF p.1: "DTCC reports it does not expect there to be any impact to its retained earnings or to market participants' clearing fund deposits as a result of closing out these pending trade obligations."
- PDF p.2: Lehman "ranked as a top three user of DTCC's Mortgage Backed Securities Division (MBSD); in the top five largest users of the Government Securities Division (GSD)".
- PDF p.2, "Mortgage-backed and Government Securities": "Lehman's pending U.S. Government securities trades ran to $190 billion (gross positions) at the time of the bankruptcy. FICC's GSD guarantees the settlement of these trades once it accepts them for clearing. In order to make good on its guarantee, FICC had to close out the various positions, which ranged from repos to government bonds. FICC successfully closed out these positions without impact on customers."
- PDF p.2: "FICC's MBSD handled the liquidation of a gross position of $329 billion in par value of Lehman's book of 'to be announced' mortgage-backed securities trades … with no losses assessed against MBSD members' clearing deposits and with no observed market impact."
- PDF p.3: "FICC and NSCC retained a third party adviser to assist in liquidating positions held by the clearing corporations."

**Proposed verdict: PASS.** The card rule is "≥ 1 public case where FICC started default management because of a member credit event". FICC GSD closed out Lehman's $190bn gross pending government securities trades to honour its guarantee, and MBSD liquidated the $329bn TBA book, after a top-5 GSD member's bankruptcy.

Two caveats:
- This is a 2008 case, before the PQD era, and outside the card's Test 1 windows.
- The release says the bankruptcy "occurred the week of Sept. 22". Lehman Brothers Holdings filed Sept 15 and the Lehman Brothers Inc. SIPA proceeding began Sept 19, 2008. The phrasing is imprecise but doesn't affect the case.

**If you confirm:** confidence goes to Medium (Test 1 pass plus a verified case), as the card expects.

### A2. FICC-GSD-03: Feb 2025 milestone

**Primary source:** SEC Release No. 34-102487, 90 FR 11134–11139 (FR Doc 2025-03351).

- "Specifically, the Commission is extending the compliance dates by one year, from December 31, 2025, to December 31, 2026, for eligible cash market transactions, and from June 30, 2026, to June 30, 2027, for eligible repo transactions." (Summary, FR pp. 11134–35)
- "Dated: February 25, 2025" (FR p. 11139).
- The release's effective date is March 4, 2025.

The milestone date used in v1 was already 2025-02-25, so the before/after table was **not re-run** and is unchanged. The upcoming milestones (2026-12-31 cash, 2027-06-30 repo) are confirmed by the same release.

### A3. ECS-SET-01: fail rates from the T+1 After-Action Report

The report has a single fail-rate passage. PDF p.7, "Fail Rates Overview":

> "On the first day following transition to T+1, Continuous Net Settlement (CNS) fail rates decreased to 1.9% and remain low at around 2%. CNS Fail Rate: The average CNS Fail Rate for July 2024 was 2.12%. This rate is consistent with T+2 settlement rates. DTC Non-CNS Fails Rate: The average non-CNS Fail Rate for July 2024 was 3.31%. Again, this rate is consistent with T+2 settlement averages."

The report gives **no numeric pre-T+1 fail rate**. Footnote 12 on p.6 cites "DTCC Metrics: Daily Metrics" as the source.

Updated before/after table (descriptive only):

| Series | Before T+1 (2024-05-28) | After T+1 |
|---|---|---|
| NSCC / CNS | May historic avg 2.01% (DTCC article, Aug 2024); May 2024 2.00% (Equities by the Numbers baseline) | first T+1 day 1.9% (report p.7); post-T+1 2.30% (DTCC article); **July 2024 avg 2.12% (report p.7)**; Aug 2026 2.21% (EbtN) |
| DTC (non-CNS) | May 2024 2.83% (EbtN; label "DTC", scope may differ from "non-CNS") | **July 2024 avg 3.31% (report p.7)**; Aug 2026 3.18% (EbtN) |

Read descriptively: CNS fails are about +0.1 to +0.3 pp after T+1 and DTC about +0.5 pp, against single-month baselines. With fewer than 3 months on each side, this is a before/after check only, with no pass/fail.

### A4. ECS-NSCC-04: SEC staff report, January 2021

**Source:** SEC Staff Report on Equity and Options Market Structure Conditions in Early 2021 (`data/raw/case_evidence/SEC_staff_report_early_2021.pdf`).

**Passages:**

- PDF p.16 (printed p.15), §2: "Pursuant to its existing rules, NSCC can also impose excess capital premium ('ECP') charges for members who present a degree of margin exposure for their cleared positions that exceed those members' excess net capital."
- PDF p.32 (printed p.31), §3.5 Clearing Agency Margin and Capital Issues: "On January 27, 2021, in response to market activity during the trading session, NSCC made intraday margin calls from 36 clearing members totaling $6.9 billion, bringing the total required margin across all members to $25.5 billion. Of the $6.9 billion, $2.1 billion were intraday mark-to-market calls, while the remaining $4.8 billion was a special ECP charge."
- Same page: "NSCC imposed this charge on 18 members, all of whom provided the additional margin. NSCC subjected one additional member to the special charge, but that member ultimately did not have to meet that charge after offsetting its exposure with a transfer from an affiliate."
- Same page: "several NSCC members were subject to an ECP charge based on the ratio of the excess risk in their portfolios relative to their capital … NSCC exercised its rules-based discretion to waive the ECP charge for all members on January 28, 2021. Absent this waiver, one retail broker-dealer would have had an additional ECP charge of more than double its margin requirement of $1.4 billion on January 28, 2021. NSCC removed this waiver on February 2, 2021".
- PDF p.33 (printed p.32): "some broker-dealers restricted activities in a limited number of individual stocks in reaction to margin calls and capital charges imposed by NSCC."

**Proposed verdict: PASS**, on the card's "changed a member's requirements" leg. NSCC imposed a $4.8bn special charge on 18 members and applied capital-based ECP charges, which are defined by a member's exposure relative to its own excess net capital. Members restricted trading in reaction.

Caveats for your decision:
- There was no default and no default management.
- The report says the members' ratios "were not driven by individual clearing member actions, but by extreme volatility in individual cleared equities". So this is member capital strain triggered by security-level volatility, which is narrower than broker credit distress.

This evidence attaches to **ECS-NSCC-04.v2** (no market indicator). The v1 row stays at revise/drop because its Test 1 failed.

### B5. FICC-GSD-02 v2 (post-hoc): Treasury-only GCF

- **Reason:** data coverage. GCF overnight has 270 of 2,034 dates and none in Sept 2019. Written in TEST_SPEC §13 before running.
- **Test variable:** (`REPO-GCF_AR_T-F` − `REPO-DVP_AR_OO-F`) × 100 bp, OFR Final. Fetched 2026-10-16 07:49 UTC and logged. It has values on every OFR date from 2018-05-07 to 2026-06-30.
- **Result:** n = 1,728 days (2019-04-05 to 2026-06-30), 202 shock days, Newey–West lags = 7. The spread averages 4.83 bp on shock days and 5.24 bp on others. The shock coefficient is **−0.67 bp** (SE 0.40, HAC p 0.095, 95% CI [−1.45, 0.12]), so **INCONCLUSIVE**: the sign is wrong but not significant, which is not the "wrong direction" rule. The quarter-end dummy is +4.5 bp.
- **Confidence:** Medium (Test 1 pass, Test 2 inconclusive), same as v1.
- **Limitation:** GCF Treasury (all tenors) vs DVP overnight is a tenor mismatch. The v1 BH family is not changed.

### B6. ECS-NSCC-04 v2 (post-hoc): reclassified without market indicator

- **Reason:** the v1 Test 1 failed because Baa is a broad credit index, while the January 2021 stress was broker-specific. No new signal was searched for.
- **Test 1 (sources):** the January 2021 meme-stock week is documented in the SEC staff report. March 2023 SVB is documented in [FDIC PR-16-2023](https://www.fdic.gov/news/press-releases/2023/pr23016.html), but no public evidence was found of an NSCC member-requirement change in that window.
- **Test 2:** see A4; proposed PASS.
- **Vulnerability:** NSCC 18.2.2 = 36.5%, scoring 2/5. The shock score now comes from the rubric (to be designed).
- **Confidence:** Low/Medium if you confirm the case.

### C7. ECS-NSCC-01 / -02 v3: pre-registered, not run

Written into TEST_SPEC §14 at 07:49 UTC:

- **Test:** lag 1 (signal in quarter t vs `vm_peak_to_avg` in t+1), using the same Test 2 criteria (rho ≥ 0.3, CI lower bound > 0, both levels and changes).
- **Data:** only target quarters from 2026Q3 onward.
- **When:** run only once there are at least 8 new target quarters; until then, new quarters are reported descriptively.
- **Why:** the 2020Q4–2026Q2 data that produced the lag-1 pattern cannot be used to confirm it.

### D8. FICC-GSD-03: are +21.1% and +5.4% unusual?

I computed every 60-business-day before/after change in mean daily Sponsored volume over the whole series. These windows overlap and the series trends upward, so this is descriptive only.

| | Value |
|---|---|
| Splits (2022-01-07 to 2026-07-16) | 1,127 |
| Median | +10.7% |
| 75th percentile | +19.0% |
| 90th percentile | +27.4% |
| Share negative | 22.5% |
| **2023-12-13 change (+21.1%)** | **80th percentile** |
| **2025-02-25 change (+5.4%)** | **33rd percentile** |

**Data-quality finding:** the Sponsored series is 0 on 12 days in Aug 2021 and about $0.05–0.5bn/day until 2021-10-08. It then jumps about 500× to about $250bn on 2021-10-12, which looks like the start of the source's coverage. The audit therefore starts at 2021-10-12. On the uncleaned series the figures are median +11.1%, 75th percentile +19.6%, 90th percentile +30.0%. This does not affect the milestone table, whose windows are in 2023–2025.

Reading: the adoption-date change is in the upper quintile but below the 90th percentile; the extension-date change is below the median. Neither stands out from the general growth trend.

### D9. TEST_SPEC.md change-log audit

Times are UTC on 2026-10-16. They were reconstructed from the download log (`SOURCES_LOG.csv`) and file creation/modification times; the change log itself recorded only dates for the first five entries. First v1 test results were written at **07:09:42** (birth time of the first result JSON and figure). An earlier run at about 07:09 crashed before computing any output.

| # | Change-log entry | Time (UTC) | Before or after first result? |
|---|---|---|---|
| 1 | Draft created | Phase 1, before Phase 2 began (exact time not recorded) | Before |
| 2 | Frozen v1 with D1–D9 | Before 06:50:54 (first download) | Before |
| 3 | Added §10b implementation details | ≈07:02 (spec file rewritten 07:02:18) | Before |
| — | **Not logged:** NSCC-04 section wording aligned to D5 ("weekly rule overrides 'under the standard'") | ≈07:02 | Before. **Flag: was not entered in the change log.** Entered retroactively here. |
| 4 | **GSD-02 month/quarter-end dummies redefined on calendar business days** | 07:06:31 (last spec edit before results) | **Before results, but AFTER inspecting the OFR data.** I had seen the coverage (270 dates; days per event window) and the median of the spread (5 bp), but no shock-vs-other comparison and no regression. The change follows mechanically from the sparse dates. **Flagged as requested.** |
| 5 | Data: T+1 report BLOCKED; no Wayback snapshots | ≈07:02–07:06 | Before |
| 6 | §13 post-hoc v2 specs | 07:49 | **After** (owner-approved post-hoc) |
| 7 | §14 v3 pre-registration (not run) | 07:49 | **After** v1 results; before any 2026Q3 data |
| 8 | GSD-03 milestone source upgraded to Rel. 34-102487 (date unchanged) | 07:49 | After (source only; no result changed) |

Also note: the v1 Sponsored audit cut-off (2021-10-12, D8 above) was chosen in round 2 after seeing the series, and is documented here. It affects the descriptive audit only.

## Data sources: status after round 2

| Source | Status |
|---|---|
| SIFMA/ICI/DTCC T+1 After-Action Report | **OK (manual)**: `data/raw/T1-After-Action-Report-FINAL-SIFMA-ICI-DTCC.pdf`, logged with original URL https://www.sifma.org/wp-content/uploads/2024/09/T1-After-Action-Report-FINAL-SIFMA-ICI-DTCC.pdf |
| SEC Release No. 34-102487 | **OK (manual)**: `data/raw/Federal Register, Volume 90 Issue 41 (Tuesday, March 4, 2025).pdf`, logged with https://www.govinfo.gov/content/pkg/FR-2025-03-04/html/2025-03351.htm |
| DTCC Lehman close-out press release | Automated fetch **BLOCKED** (Cloudflare 403). **OK (manual)**: `data/raw/DTCC closes out Lehman bankruptcy.pdf`; `DTCC_Lehman_closeout_press_2008.html` could not be created |
| DTCC 2008 annual report (sechistorical part 1) | **MISSING**: not found in `data/raw/`; logged as MISSING with https://www.sechistorical.org/collection/papers/2000/2008_0101_DTCCAR_1.pdf |
| OFR `REPO-GCF_AR_T-F` | OK (fetched 07:49 UTC) |
| Equities by the Numbers monthly history | Still none (no Wayback snapshots) |
| 2026Q3 PQD | Not yet published (needed for v3 and the v2 candidates) |

---

# v1 baseline (accepted 2026-10-16; unchanged)

### Results

| ID | Test 1 | Test 2 (primary = same quarter / same period) | Confidence | Version |
|---|---|---|---|---|
| FICC-GSD-01 | PASS (weekly; 3/3 windows; outside rate 12.2%) | INCONCLUSIVE: rho 0.41, 95% CI [−0.01, 0.76], n 22; BH q 0.24 | Medium | v1 |
| FICC-GSD-02 | PASS (weekly; 3/3; 12.4%) | INCONCLUSIVE: shock-day coefficient +0.02 bp, HAC p 0.97, n 246 (46 shock days) | Medium | v1 |
| FICC-GSD-03 | Milestones sourced; owner to verify | Descriptive only (D8): Sponsored volume +21.1% / +5.4% around the two past milestones | Low/Medium, pending | v1 |
| FICC-GSD-04 | PASS (weekly; 2/2; 11.1%) | Candidate case evidence (Lehman 2008); owner to verify | Pending: Medium if case verified | v1 |
| FICC-MBSD-01 | PASS (weekly; 2/3; 12.0%) | INCONCLUSIVE: rho 0.15, CI [−0.16, 0.59], n 22; BH q 0.67 | Medium | v1 |
| ECS-NSCC-01 | PASS (daily; 4/4; median window share 81%; outside 7.7%) | INCONCLUSIVE: levels rho 0.34, CI [−0.16, 0.67]; changes rho −0.33, CI [−0.77, 0.32]; BH q 0.26 / 0.26 | Medium, **v2 candidate** | v2 |
| ECS-NSCC-02 | PASS (daily; 3/3; median 38%; outside 10.9%) | INCONCLUSIVE: levels rho **0.55, CI [0.02, 0.70] passes**, but changes rho 0.01, CI [−0.40, 0.57] fails → **"possible shared trend"**; BH q 0.054 / 0.97 | Medium, **v2 candidate** | v2 |
| ECS-NSCC-03 | PASS (daily; 3/3; median 100%; outside 13.5%) | INCONCLUSIVE: shock-week coefficient +$0.50bn, HAC p 0.24, n 431 (61 shock weeks); BH q 0.39 | Medium | v1 |
| ECS-SET-01 | Milestones sourced; owner to verify | Before/after check only; no monthly history obtainable | Low/Medium, pending | v2 |
| ECS-NSCC-04 | **FAIL** (weekly; 1/2 windows; 2/2 required) | Candidate case evidence (SEC report on Jan 2021); owner to verify | **Revise/drop** (Test 1 failed) | v1 |

How to read the table:

- **Medium** follows the card rule "Test 1 passes, Test 2 inconclusive". No chain reached High.
- **No chain was significant in the wrong direction.**
- **Multiple testing:** Benjamini–Hochberg was applied across the 8 primary Test 2 p-values (GSD-01, GSD-02, MBSD-01, NSCC-01 ×2, NSCC-02 ×2, NSCC-03). None has q < 0.05; the smallest is NSCC-02 levels at q = 0.054.

### Chain notes

#### FICC-GSD-01 · Treasury market volatility
- **Test 1:** the weekly peak of |ΔDGS10| alerted in all three windows (COVID 3/3 weeks, SVB 1/2, 2025 2/2). The outside-window alert rate is 12.2% (≤ 15%), so Test 1 passes.
- **Test 2:** quarterly maximum vs same-quarter GSD margin growth (`im_qoq`, PQD 6.1.1) over 2021Q1–2026Q2 gives rho 0.408, which reproduces the 0.408 quoted on the card. The bootstrap lower bound is −0.01, so the rule "CI lower bound > 0" fails by a hair. Lag 1 (secondary) gives rho 0.46, CI [−0.12, 0.72].
- **Vulnerability (scoring only):** stress loss ÷ margin is 4.0% in 2026Q2, the 4th percentile of its own history, which scores 1/5.

#### FICC-GSD-02 · Repo funding pressure (pilot)
- **Test 1:** passes. The weekly peak of adjusted SOFR−EFFR alerted in the Sept 2019 week, 1 of 3 COVID weeks and 1 of 2 tariff weeks; the outside rate is 12.4%.
- **Test 2:** fails to show an effect. The GCF−DVP overnight spread averages 6.0 bp on shock days and 5.9 bp on other days; the coefficient is +0.02 bp, HAC p 0.97, with Newey–West lags = 4.
- **Main limitation (data, not method):** OFR publishes the GCF overnight **Final** rate on only 270 of 2,034 dates. There are none in the Sept 2019 window and 1 day in the COVID window, so the event study rests mostly on 2023–2026 days. Whether a day is published may itself be related to market conditions.
- **Vulnerability:** 7.3.4 ÷ 7.1 (new field `peak_payment_to_qlr`) is 0.77 in 2026Q2, the 86th percentile, which scores 5/5.

#### FICC-GSD-03 · Treasury clearing mandate (no market indicator)
- **Test 1:** sources exist for the 2023-12-13 adoption ([SEC 2023-247](https://www.sec.gov/news/press-release/2023-247)) and the 2025-02-25 extension. The extension is so far cited only through secondary sources ([Markets Media](https://marketsmedia.com/sec-extends-compliance-dates-for-treasury-clearing), [Arnold & Porter](https://www.arnoldporter.com/en/perspectives/advisories/2025/03/us-treasury-clearing-sec-extends-compliance-dates)); please confirm it against the primary SEC release.
- **Test 2 (descriptive, D8):** mean daily Sponsored `TOTAL_AMOUNT` over 60 business days before vs after each past milestone:

  | Milestone | Before | After | Change |
  |---|---|---|---|
  | 2023-12-13 | $796bn | $963bn | **+21.1%** |
  | 2025-02-25 | $1,733bn | $1,827bn | **+5.4%** |

  Sponsored volume also trends up throughout 2021–2026 (see the figure), so these differences are not adjusted for that trend. **Pass/fail is your decision.** DTCC releases report Sponsored peaks of [$1.7T on Sept 30, 2024](https://www.dtcc.com/news/2024/october/03/ficcs-government-securities-division-surpasses) and [$2.48T on June 30, 2025](https://www.dtcc.com/news/2025/july/02/ficc-successfully-processes).
- **Vulnerability:** PQD 19.1.3.2 for GSD is reported only for **5 quarters (2025Q2–2026Q2)**; the latest is 69.8%, at the 60th percentile, which scores 3/5 but rests on a very coarse history. MBSD and NSCC: vulnerability, no data.

#### FICC-GSD-04 · Member credit deterioration
- **Test 1:** passes. The weekly peak of Baa 20-day widening alerted in both windows (2/2 required); the outside rate is 11.1%.
- **Test 2, candidate evidence:** DTCC "closed out more than $500 billion of market participants' exposure to the Lehman Brothers Inc. bankruptcy". Lehman was "among the five largest users of the government securities division", and DTCC expected "no impact on … market participants' clearing fund deposits" ([American Banker, Oct 31, 2008](https://www.americanbanker.com/news/500b-of-lehman-exposure-closed-out); [Finextra reprint of the DTCC release](https://finextra.com/pressarticle/24287/dtcc-closes-out-lehman-bankruptcy)).
- **Gap:** the secondary article does not name FICC as the entity that closed out the positions. The DTCC 2008 annual report download was BLOCKED (see below).
- **Vulnerability:** 18.2.2 top-5 share of open positions is 26.6%, at the 43rd percentile, which scores 3/5.

#### FICC-MBSD-01 · MBS spread shock
- **Test 1:** passes at the threshold, hitting 2 of 3 windows. It hit the gilt window (D3, 1 of 4 weeks) and the 2025 window (2/2) but **missed COVID**: the weekly mortgage-survey spread did not exceed its 52-week 90th percentile in March 2020. The outside rate is 12.0%.
- **Test 2:** quarterly maximum vs MBSD 6.7.1 growth gives rho 0.15, CI [−0.16, 0.59], which is inconclusive. Lag 1 gives rho 0.00.
- **Vulnerability:** MBSD stress loss ÷ margin is 24.8% in 2026Q2 (matching the card), at the 17th percentile, which scores 1/5.

#### ECS-NSCC-01 · Equity selloff → NSCC variation margin (v2 candidate)
**v2 candidate: needs confirmation on data not used before (e.g., 2026Q3 PQD).**
- **Test 1:** passes. VIX ÷ 20-day average alerted in 4/4 windows; the median in-window share is 81% and the outside rate 7.7%.
- **Test 2 (lag 0):** levels rho 0.34, CI [−0.16, 0.67]; changes rho −0.33, CI [−0.77, 0.32]. Both are inconclusive.
- **Lag 1 (secondary):** levels 0.48, CI [0.12, 0.79]; changes 0.44, CI [0.02, 0.73]. Both would pass, but lag 1 is secondary by spec and was the basis for choosing this chain.
- **Vulnerability:** 7.3.4 ÷ 7.1 for NSCC is 1.18, at the 41st percentile, which scores 3/5.

#### ECS-NSCC-02 · Funding squeeze → NSCC variation margin (v2 candidate)
**v2 candidate: needs confirmation on data not used before (e.g., 2026Q3 PQD).**
- **Test 1:** passes, with 3/3 windows, median share 38% and outside rate 10.9%.
- **Test 2 (lag 0):** levels rho 0.55, CI [0.02, 0.70], which passes on its own. Changes rho 0.01, CI [−0.40, 0.57], which does not. Flag: **possible shared trend.**
- **Why the flag matters:** the scatter shows that both `vm_peak_to_avg` and the funding signal are high in 2024Q4–2026Q2. The level correlation largely reflects that common rise, not quarter-to-quarter co-movement.
- **Lag 1 (secondary):** levels 0.71, changes 0.60; both pass.
- **Vulnerability:** same as NSCC-01 (3/5).

#### ECS-NSCC-03 · Volume surge → NSCC settlement fails
- **Test 1:** passes. Daily Cboe consolidated shares, summed over all venues including TRFs, alerted in 3/3 windows with a median in-window share of 100% and an outside rate of 13.5%.
- **Test 2:** in shock weeks the weekly mean fail value is $3.85bn vs $3.18bn in other weeks. The coefficient after month-end, quarter-end and T+1 controls is +$0.50bn, HAC(4) p 0.24, which is inconclusive.
- **Next week (secondary):** +$3.1bn, p 0.069.
- **Data note:** 1.03% of SEC records have no price and are excluded from the dollar value.
- **Vulnerability:** no data (shock-only rule).

#### ECS-SET-01 · Shorter settlement cycle → NSCC and DTC fails
- **Test 1:** sources found for each milestone:
  - T+1 adopted 2023-02-15 ([SEC 2023-29](https://www.sec.gov/news/press-release/2023-29)).
  - T+1 go-live 2024-05-28.
  - NSCC 24x5 clearing go-live 2026-06-28. This date comes from [DTCC notice A9670](https://www.dtcc.com/-/media/Files/pdf/2025/11/5/A9670.pdf) (planned date) and [trade press](https://www.ftfnews.com/nscc-extends-clearing-hours-to-24x5-availability/); please confirm.
  - No adopted T+0 milestone was found.
- **Test 2 (before/after check only):** monthly history could not be obtained (see BLOCKED below). The published points are:

  | Series | Before | After |
  |---|---|---|
  | NSCC/CNS | May historic average **2.01%**; May 2024 **2.00%** | post-T+1 **2.30%** ([DTCC, Aug 2024](https://www.dtcc.com/dtcc-connection/articles/2024/august/26/what-insights-can-be-applied-to-other-markets)); July 2024 **2.12%** ([release](https://www.dtcc.com/news/2024/september/12/sifma-ici-and-dtcc-release-t1-after-action-report)); Aug 2026 **2.21%** |
  | DTC | May 2024 **2.83%** | non-CNS **3.31%** (period not stated); Aug 2026 **3.18%** |

  Fewer than 3 months on each side are available, so this is reported as a before/after check only (rule approved with the data sources). For 24x5 there is only one "after" point (Aug 2026) and no "before" month.

#### ECS-NSCC-04 · Broker distress → NSCC default management
- **Test 1 FAIL:** the weekly Baa 20-day widening did **not** alert in the meme-stock week (1 testable week, no alert). It did alert in the SVB window (1/2 weeks). With 2 windows, 2/2 is required (D4).
  - This is not an identical re-run of the Oct 6 test, which used the COVID and SVB windows.
  - Economically, the January 2021 broker stress was idiosyncratic and did not move broad Baa spreads.
- **Test 2, candidate evidence (recorded, not scored):** SEC staff report on early 2021, p. 32: "On January 27, 2021 … NSCC made intraday margin calls from 36 clearing members totaling $6.9 billion … $4.8 billion was a special ECP charge". NSCC waived the ECP charge on Jan 28 and reinstated it on Feb 2 ([SEC report](https://www.sec.gov/files/staff-report-equity-options-market-struction-conditions-early-2021.pdf); local copy in `data/raw/case_evidence/`).
- **Vulnerability:** NSCC 18.2.2 is 36.5%, at the 39th percentile, which scores 2/5.

### Differences from the Oct 15 numbers cited on the ECS cards

The Oct 15 code is not in the repo and was not reproduced. The lag-0 run above replaces it as the primary result.

| Chain | Oct 15 (lag 1, from card) | This run, lag 1 (secondary) | This run, lag 0 (primary) |
|---|---|---|---|
| ECS-NSCC-01 | levels 0.48, changes 0.44 | levels 0.48, changes 0.44 (both CIs > 0) | levels **0.34**, changes **−0.33**; inconclusive |
| ECS-NSCC-02 | levels 0.71, changes 0.59 | levels 0.71, changes 0.60 (both CIs > 0) | levels **0.55** (CI > 0), changes **0.01**; shared-trend flag |

The lag-1 values match the cards, so the inputs agree. The difference is the timing: at the primary same-quarter timing, neither chain passes on both levels and changes. GSD-01's lag-0 rho (0.408) also matches its card.

### Open data gaps and BLOCKED sources

*Superseded where noted by "Data sources: status after round 2" above: the T+1 report and Release 34-102487 are now obtained (manual); the 2008 annual report is still missing.*

These need a manual download. Put files in `data/raw/<source>/` and re-run.

| Source | Status | What to download by hand | Affects |
|---|---|---|---|
| DTCC T+1 After-Action Report (Sept 2024) | **BLOCKED**: `files.dtcc.com` returns Cloudflare 1010 to non-browser clients | Open https://files.dtcc.com/download/assets/T1-After-Action-Report/e72829eeceb211f086f70aec4933d5f6 in a browser and save it as `data/raw/dtcc/T1_After_Action_Report_2024-09.pdf` | SET-01 |
| Wayback snapshots of Equities by the Numbers | **No data**: the CDX index returns no captures for the three known page URLs (logged) | Ask DTCC, or check whether the page existed under another URL | SET-01 monthly history |
| DTCC 2008 Annual Report | **BLOCKED**: dtcc.com 404; sechistorical.org Cloudflare 1010 | Download https://www.sechistorical.org/collection/papers/2000/2008_0101_DTCCAR_1.pdf in a browser and save it to `data/raw/case_evidence/` | GSD-04 (confirm FICC's role) |
| Finextra reprint of the DTCC Lehman release | HTTP 403 to automated fetch | Save the page manually | GSD-04 |
| SEC release for the Feb 2025 Treasury-clearing extension | Only secondary sources cited | Locate it on sec.gov | GSD-03 |
| PQD 19.1.3.2 history | Data limit: GSD values only from 2025Q2; MBSD/NSCC are N/A | None available | GSD-03 vulnerability score |
| OFR GCF overnight Final | Data limit: 270 dates, none in Sept 2019 | None (see post-hoc suggestion 1) | GSD-02 |
| 2026Q3 PQD | Not yet published | Re-run NSCC-01/02 (and GSD-01) when released | Confirmation of v2 candidates |

**Other run notes:**

- `market_daily.csv` was used as-is; its data runs to 2026-10-09/13.
- PQD covers 2020Q4–2026Q2. The existing 7.3.1-based `payment_to_qlr` is unchanged, and the 7.3.4 field was added alongside it (D2).
- No existing data file was overwritten. New raw data is in `data/raw/`; derived tables are in `data/derived/`.
- SEC requests used the approved User-Agent, sent to sec.gov only, at no more than 2 requests per second. Other sites got the default Python client User-Agent; FRED stalls custom strings.


## Suggested post-hoc changes (v2, untested), status after round 2

None of these was run. Each would need a written reason, a version bump and data not used here before it counts.

1. **[RUN in round 2 as FICC-GSD-02.v2; see B5]** **GSD-02 test variable.** Replace GCF overnight with `REPO-GCF_AR_T-F` or `REPO-GCF_AR_TOT-F` minus `REPO-DVP_AR_TOT-F`. Both have full daily coverage from 2018-05-07, including 5 days in Sept 2019 and 11 in March 2020; I checked availability only, not results. The tenor mismatch should be documented.
2. **[Partly addressed by v3 pre-registration; see C7]** **NSCC-02.** Given the shared-trend flag, a v3 could pre-specify changes (or a detrended level) as the single primary statistic. It would be confirmed on 2026Q3 onward, not re-tested on 2020Q4–2026Q2.
3. **[Pre-registered in round 2 as v3; see C7]** **NSCC-01.** The lag-1 association is the only one that holds. If the team believes VM responds with a lag, that timing has to be argued and frozen before the 2026Q3 PQD is seen.
4. **[DONE in round 2 as ECS-NSCC-04.v2 (case-only); see B6]** **NSCC-04.** The Baa spread does not capture idiosyncratic broker stress such as January 2021. Consider a signal tied to broker-dealer stress, or treat the chain as case-only (no market indicator), and re-specify the windows.
5. **MBSD-01.** The weekly survey rate missed the March 2020 MBS dislocation. A daily public MBS proxy, if one can be found, would match the card's intent better.
6. **NSCC-03.** Fail values are heavily right-skewed. A log transform, or fails in shares, may be more robust. The next-week effect (p 0.069) could be considered as a primary timing in a future version, with a written reason.
7. **GSD-01.** Re-check with 2026Q3: n = 22 and the CI lower bound of −0.01 leave this one quarter away from either answer.

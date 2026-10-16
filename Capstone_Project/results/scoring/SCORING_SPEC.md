# Weekly scoring spec, v1

Status: **FROZEN v1**. Written 2026-10-16 (~08:40 UTC) and committed **before any score was computed**. Rules are not tuned after seeing scores; ideas go in §10 "Proposed changes" and are not applied.

Inputs come from validation round 1 (closed 2026-10-16T07:58Z): `results/chain_tests/chain_confidence.json`.

## 1. Inputs

- `results/chain_tests/chain_confidence.json`: 10 core chains, active versions, confidence, signal fields, vulnerability fields, latest V scores.
- Market data, read only:
  - `capstone_database/exports/market_daily.csv` (FRED: DGS10, SOFR, EFFR, BAA10Y, VIXCLS);
  - `data/raw/fred/MORTGAGE30US.csv`;
  - `data/derived/cboe_consolidated_daily.csv`, rebuilt from `data/raw/cboe/`.
- Signal transforms: exactly the validation code in `validation/data.py` (`ust10_abs_change`, `sofr_effr_adjusted`, `baa_widen20`, `mbs_spread_abs_weekly_change`, `vix_jump`, `consolidated_volume`).
- Event register: `data/events/event_register.csv` (§4).

## 2. Weeks

- A week runs Monday–Friday and is labelled by its **Monday** (`week`); `week_end` is its Friday. Internally this is pandas `W-FRI`.
- **Latest complete week:** the most recent week whose Friday is strictly before the run date. For a run on Friday 2026-10-16 that is the week of 2026-10-05 (ending 2026-10-09).
- If a chain's signal has no observation in a week, S for that chain and week is null, with reason "no data this week". It is never filled.
- **History:** every week from the week of 2021-01-04 through the latest complete week.
- **Sanity weeks:** a date such as 2020-03-16 refers to the week containing it.

## 3. Shock score S (1–5)

### 3A. Chains with a market indicator

These are GSD-01, GSD-02 (v2 active), GSD-04, MBSD-01, NSCC-01, NSCC-02 and NSCC-03.

- **Weekly peak** = maximum of the card's daily signal within the week.
  - MBSD-01's signal is already weekly (one survey observation per week), so its weekly peak is that value.
  - GSD-02 v2 and NSCC-02 use the same signal, so they get the same S.
- **Percentile** of this week's peak among **all prior weekly peaks**:
  - expanding window from the series start; the current week is excluded;
  - at least **104 prior weeks**, else S is null ("insufficient history");
  - midrank: pct = (#prior < x + 0.5 · #prior = x) / #prior, the 10/6 project convention for ties. Many signals have zero-valued weeks.
- **Map:** pct < 0.20 → 1; 0.20 ≤ pct < 0.40 → 2; 0.40 ≤ pct < 0.60 → 3; 0.60 ≤ pct < 0.80 → 4; pct ≥ 0.80 → 5.

### 3B. Chains without a market indicator: event rubric

These are GSD-03, SET-01 and NSCC-04 (v2 active).

Each event in the register has three levels, each 0–2:

- **Certainty** (from the register):
  - 0 = rumor, speculation or under discussion;
  - 1 = formally proposed or announced, date may change;
  - 2 = final/adopted, or already happened.
- **Reach** (from the register; relative to the DTCC process on the card):
  - 0 = one small participant or a minor slice;
  - 1 = one group of participants or one product;
  - 2 = the whole business line or market-wide, OR one of the top-5 members.
- **Timing** (computed by code from `effect_date` vs the scoring week's Friday). days = effect_date − week_end.
  - 2 if |days| ≤ 28 (within the next or past 4 weeks);
  - 1 if 29 ≤ |days| ≤ 84 (5–12 weeks);
  - 0 if |days| > 84.

**Total** = certainty + reach + timing, from 0 to 6. **Map:** 6 → 5; 5 → 4; 4 → 3; 3 → 2; 0–2 → 1. **Cap:** if certainty = 0, S ≤ 2.

**Active event (definition fixed here):** an event is active in a week when announced_date ≤ week_end and effect_date ≥ week_end − 84 days. That is, it counts from its announcement until 12 weeks after it takes effect. A distant future event that has been announced is active, with timing 0. An event more than 12 weeks in the past is not active. If announced_date is blank, effect_date is used.

- **Several active events on one chain in one week:** take the max S and record all event_ids with their levels.
- **No active event that week:** S = 1, recorded as "no active event".
- **Code computes S.** The register (human or LLM) supplies only certainty, reach, dates and evidence.

## 4. Event register

**File:** `data/events/event_register.csv`.

**Columns:** event_id, chain_id, title, announced_date, effect_date, certainty, reach, evidence_quote, source_url, entered_by (human / llm), needs_review (Y/N), notes.

**Seed:** only the events already sourced in `results/chain_tests/REPORT.md`:

- T+1 adoption 2023-02-15 and go-live 2024-05-28;
- NSCC 24x5 go-live 2026-06-28 (needs_review = Y);
- Treasury clearing adoption 2023-12-13; extension 2025-02-25; compliance dates 2026-12-31 (cash) and 2027-06-30 (repo);
- NSCC special ECP charge 2021-01-27 and waiver 2021-01-28.

**Seeding rules:**

- Quotes are taken from REPORT.md.
- If unsure between two levels, pick the lower and set needs_review = Y.
- If REPORT.md holds no quote for an event, evidence_quote says so and needs_review = Y.
- Later LLM rows are appended with entered_by = llm and needs_review = Y.

## 5. Vulnerability V (1–5)

- V = `vulnerability_variable.latest_score_1to5` from chain_confidence.json: the 2026Q2 PQD, own-history percentile, score = ceil(pct × 5).
- All current vulnerability fields are exposure ÷ buffer ratios, where higher = more vulnerable, so no field is reversed. Any future buffer-type field must be reversed before scoring.
- NSCC-03 and SET-01 have no public vulnerability data, so V = null.
- **vuln_reliability flag:** "low (<8 quarters of history)" when `own_history_quarters` < 8 (currently GSD-03: 5 quarters); otherwise "ok"; "n/a" when V is null.
- **History:** every historical week uses the same latest V (2026Q2), literally as specified. History severity is therefore **not point-in-time**, and the history file labels it so (`v_basis = latest_2026Q2_not_point_in_time`).

## 6. Severity and cards

- **Severity** = S × V, from 1 to 25. If V is null, severity is null and the card shows S only, with the label "vulnerability: no data". No default V is ever filled. If S is null, severity is null.
- **Cards (9):** GSD-01, GSD-02, GSD-03, GSD-04, MBSD-01, **NSCC liquidity**, NSCC-03, SET-01, NSCC-04.
- **NSCC liquidity** combines ECS-NSCC-01 and ECS-NSCC-02:
  - S = max of the two;
  - V = their shared V (NSCC 7.3.4 ÷ 7.1);
  - it lists both shock sources with their S, and names the driver (the higher S; on a tie, both are named).
- **Every card carries:**
  - confidence;
  - flags: `watch`, `v2_candidate_needs_2026Q3_confirmation`, `shock_score_from_rubric`, `post_hoc_version`;
  - `vuln_reliability`.
- **Confidence is shown and never multiplied in.** The NSCC liquidity card carries the confidence shared by both chains (Medium) and the union of their flags.
- **Ranking:**
  - Group 1: cards with a severity, sorted by severity descending, ties broken by S descending, then by card id.
  - Group 2: shock-only cards (V null), sorted by S descending, then card id.
  - Cards with S null go last, with their reason.

## 7. Outputs

- `results/scoring/weekly_scores.json`: the latest complete week, one record per card. Each record has id, week, week_end, S, the S computation (percentile with prior-week count and weekly peak; or rubric levels with event_ids), V, severity, confidence, flags, vuln_reliability, rank and group.
- `results/scoring/weekly_scores_history.csv`: the same fields per card per week, from 2021-01-04 to the latest complete week. Per-chain S rows for NSCC-01 and NSCC-02 are included as well as the combined card.
- `results/scoring/figures/shock_scores_history.png`: S over time per chain. Validation event windows are shaded; rubric chains mark event effect dates.

## 8. Sanity check (descriptive, not validation)

- Print all cards for the weeks containing 2020-03-16, 2021-01-25, 2023-03-13, 2024-05-27, 2025-04-07, and the latest complete week. Weeks before 2021-01 are computed on demand for this print only.
- **Known stress events** = each chain's validation event windows (from the chain cards) plus, for rubric chains, the effect dates of their seeded events.
- List every week overlapping a known stress event where that chain's S ≤ 2.
- Report only. No rule is adjusted.

## 9. Code

- `python -m validation.scoring` uses the existing venv `.venv-validation` and reuses `validation/data.py` and `validation/stats.py`.
- It writes only to `results/scoring/` and `data/events/`, and never overwrites existing project files.
- If `data/events/event_register.csv` already exists, it is read rather than re-seeded.

## 10. Proposed changes (not applied)

*(Empty at freeze. Filled after the run, if any.)*

## Change log

| Time (UTC) | Change | Before or after scores |
|---|---|---|
| 2026-10-16 ~08:40 | v1 written and frozen | Before |

# Weekly scoring spec, v1 (current: v1.2, see §12; v1.1 in §11)

Status: **FROZEN v1**. Written 2026-10-16 and committed (`8d75706`, 08:37 UTC) **before any score was computed**. Rules are not tuned after seeing scores; ideas go in §10 "Proposed changes" and are not applied.

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

## 11. Version 1.1: calibration fixes (owner-approved; written 2026-10-16T08:44:54Z, before re-running)

These rules replace the v1.0 rules where stated and fix structural problems found in v1.0 (§10 items 1–4). They were not chosen to get a particular ranking. The v1.0 outputs are kept as `*_v1.0.*`.

1. **NSCC-03 signal (replaces §3A for this chain).**
   - Ratio = weekly peak consolidated volume ÷ median of the **prior 52 weekly peaks** (current week excluded). The full 52 prior weeks are required, else null.
   - The ratio then goes through the same expanding percentile (≥ 104 prior ratio weeks, midrank) and the same 1–5 map.
   - The ratio first exists in Jan 2019, so the first scorable week is around Jan 2021; the 2020 sanity week is null for NSCC-03.
2. **Floor rule (all market-indicator chains).**
   - If a chain's weekly signal (the weekly peak used for scoring; the ratio for NSCC-03) is ≤ 0, then S = 1, whatever its percentile.
   - It is applied literally to every market-indicator chain. In practice it binds where the signal can be ≤ 0: GSD-04 (Baa widening clipped at 0), GSD-02 / NSCC-02 (adjusted SOFR−EFFR can be negative), and any zero-change week of GSD-01 / MBSD-01.
   - VIX ratio and volume ratio are always > 0.
3. **Rubric timing cap.** For each event, if timing = 0 (effect more than 12 weeks ahead or past), that event's S ≤ 2. The cap is applied per event, before taking the max. Announcements stay separate register events dated on their announcement day.
4. **As-of V for history (replaces the history rule in §5).**
   - For each week, take the latest PQD quarter publicly available by week_end. Available date = the DTCC catalogue `listed_date` in the PQD panel where known (all 23 quarters have one); otherwise quarter end + 90 days.
   - V = ceil(pct × 5), with pct = share of the chain's own history up to and including that quarter that is ≤ its value. This is the same formula as round 1.
   - Weeks before any PQD is available have V = null and severity = null ("no PQD public yet").
   - vuln_reliability = "low (<8 quarters of history)" when fewer than 8 quarters are available as of that week.
   - The latest week must reproduce the chain_confidence.json V; the code asserts this.
   - History rows carry `v_basis = as_of_<quarter>`.
5. **Output fields.**
   - `driver` per card in weekly_scores.json: "shock" if S > V, "vulnerability" if V > S, "both" if equal; "n/a" if S or V is null.
   - The v1.0 field that named the NSCC liquidity driving chain is renamed `shock_driver_chain`.
5b. **Clarification (2026-10-16T08:46:38Z, before re-running):** the floor rule (item 2) applies only where §3A would otherwise give a percentile S. A week with insufficient history (fewer than 104 prior weeks) stays null even if its signal is ≤ 0.
6. **Event register v1.1** (owner instructions; evidence fetched before re-running):
   - EV0001 and EV0004: quotes added; certainty 2, reach 2; needs_review N.
   - EV0003: certainty 2, reach 1 if the 2026-06-28 go-live is confirmed by a DTCC notice or press; otherwise needs_review stays Y.
   - EV0006 and EV0007: certainty 2 unless a 2026 SEC proposal or statement about a further extension is found (then 1, with a quote).
   - EV0008: reach 2, needs_review N.
   - The v1.0 register is kept as `data/events/event_register_v1.0.csv`.

## 12. Version 1.2: liquidity V, SLD override, event rubric v1.2 (owner-approved; written 2026-10-23T03:15Z, before re-running)

These rules replace the v1.1 rules where stated. Approved by the owner on 2026-10-23 after the comparison in `results/scoring/proposals/` (former §10 items 6–8; their evidence is kept below). The v1.1 outputs are kept as `*_v1.1.*`.

1. **Liquidity V (replaces the vulnerability field of FICC-GSD-02 and NSCC liquidity).**
   - V uses `payment_to_qlr` = same-quarter PQD 7.3.1 ÷ quantified 7.1, instead of `peak_payment_to_qlr` (7.3.4 ÷ 7.1).
   - Reason: from 2021Q3, 7.3.4 equals the 4-quarter maximum of 7.3.1, and before that it measured actual payments. Either way, it does not match the quarter-end 7.1 snapshot (evidence a below).
   - The formula is unchanged (§11.4: as-of quarter, own-history percentile, ceil(pct × 5)), as is the `vuln_reliability` rule. No quarters are excluded (evidence c).
   - `chain_confidence.json` records the new field for FICC-GSD-02, ECS-NSCC-01 and ECS-NSCC-02. It is regenerated by `python -m validation.export` from the v1.2 entry in `validation/signoffs.py`.
2. **SLD override (NSCC liquidity only).**
   - If NSCC PQD 7.3.2 > 0 in the latest quarter published by week_end (same as-of rule as V), then V = max(V, 4), with the label "SLD needed this quarter".
   - This is a simulated default shortfall that NSCC covered with SLD, not an uncovered loss (evidence b).
   - The card keeps `V_base` (before the override) and `V_override_reason`. The latest-week check against `chain_confidence.json` uses `V_base`.
   - 7.3.2 is read even when 7.1 is blank in that quarter. V_base then carries forward from the last quarter with a ratio, as in §11.4.
3. **Event rubric v1.2 (replaces §3B and §11.3).**
   - Code: `validation/event_scoring.py` (`RUBRIC_VERSION = "event-rubric-v1.2"`). Classifier prompt: `validation/llm_event_classifier_prompt.md`. Both are kept exactly as supplied by the owner; the method is in the owner's "Event Ranking Method (Rubric v1.2)", 2026-10-22.
   - **Active window:** announced_date ≤ week_end and week_start ≤ effect_date + 84 days.
   - **Timing** is in weeks from the nearer edge of the Monday–Friday week, rounded up:
     - 0 if the effect date falls inside the week;
     - 2 if ≤ 4 weeks;
     - 1 if 5–12 weeks;
     - 0 if more than 12 weeks.
     - (v1.1 counted days from the Friday.)
   - **Map and caps:** total = certainty + reach + timing; 6 → 5, 5 → 4, 4 → 3, 3 → 2, 0–2 → 1. Certainty 0 → S ≤ 2. Timing 0 → S ≤ 2.
   - **Stage floors:** these apply only to events mapped to the member card, and only when certainty = 2 and timing ≥ 1. Stage 3 → S ≥ 4; stage 4 → S = 5. A stage on any other card is removed and flagged.
   - **Code checks on LLM rows** (`entered_by = llm`; `validate()`):
     - unknown card ids are dropped;
     - quotes must appear verbatim in the stored article text;
     - certainty 2 needs a primary source (regulator, DTCC, issuer filing, official) or ≥ 2 independent outlets, else it is lowered to 1;
     - reach 2 on a single firm needs a firm on the major-participant list, else it is lowered to 1;
     - LLM confidence < 0.7 → review.
     - All checks lower or flag; none raises a level.
     - Human rows (`entered_by = human`) are not re-checked; their `needs_review` comes from the register.
   - **Human review:** every event with S ≥ 4, and every flagged event, gets `needs_review`. A card whose driving event needs review carries the flag `event_needs_human_check`. Display only; it does not change S or rank.
   - **Several events:** the card takes the highest S among its active events, with ties ordered by certainty, reach, then the most recent update. The card records the driving event. No active event → S = 1.
   - **Versioning:** each event row records the rubric version. LLM rows also record the prompt version (first 12 hex digits of the prompt file's SHA-256) and the model name.
   - **Register v1.2 columns** (added; existing columns unchanged): card_ids (pipe-separated; blank = chain_id), stage, source_tier, outlet, llm_confidence, named_participants, reach_basis, updated_date, prompt_version, model. The v1.1 register is kept as `data/events/event_register_v1.1.csv`. Values for the 9 existing human rows: card_ids = chain_id; source_tier from the source domain (sec.gov / federalregister.gov → regulator; dtcc.com → dtcc); outlet = the publisher; other new fields blank.
   - **Card catalog:** v1.2 scores the existing 9 cards only. The 16-card catalog in the prompt is a screening draft and is not adopted here. Catalog ids map onto scoring cards as follows:
     - the id itself, where it is a scoring card;
     - `ECS-NSCC-LIQ` → NSCC liquidity;
     - `XE-MEMBER` → FICC-GSD-04 and ECS-NSCC-04 (the two chains the draft merges into "Member stress / default").
     - Events on other catalog cards are kept in the register and listed as "unscored card".
   - **Major-participant list:** `data/events/major_participants.csv`. It starts empty, so a reach-2 claim on a single firm is lowered to 1 until the list is filled and reviewed.
4. **Cards with both a market indicator and events.**
   - S = max(market S, event S) when at least one active event maps to the card; otherwise the market S alone. If the market S is null and events are active, S = event S.
   - Each card records `S_source`: `market`, `events`, `market=events` (tie), or `events (market null)`.
   - Rubric-only cards record `events`.
5. **Outputs.**
   - Same files as §7, written by the v1.2 run.
   - v1.1 files are renamed `*_v1.1.*`: weekly_scores, weekly_scores_history, sanity_check, figures/shock_scores_history, peak_payment_to_qlr_summary, figures/peak_payment_to_qlr_history, plus `results/chain_tests/chain_confidence_v1.1.json`.
   - `payment_to_qlr_summary.json` and `figures/payment_to_qlr_history.png` replace the 7.3.4 versions.
   - `compare_v1.1_v1.2.csv` compares, per scored week since 2026-10-05, the v1.1 rules re-run on the same refreshed inputs against v1.2. The v1.1 re-run outputs are kept in `results/scoring/v1.1_rerun/`.
6. **Weeks.** The run of 2026-10-23 scores through the week of 2026-10-12. The week of 2026-10-19 is scored only after its Friday (2026-10-23) market data is published (FRED daily series post about one business day later).

**Evidence (former §10 items 6–8, written 2026-10-23T03:02Z after the v1.1 scores):**

a. **Proposal A (main): V for FICC-GSD-02 and NSCC liquidity from same-quarter 7.3.1 ÷ 7.1 (`payment_to_qlr`, already in the panel) instead of 7.3.4 ÷ 7.1 (`peak_payment_to_qlr`).**
   - **Why:** the numerator and denominator are not on the same basis.
     - 7.3.4 is the "Peak day amount in previous twelve months". From 2021Q3 it equals the trailing four-quarter maximum of 7.3.1 in every quarter for both GSD and NSCC (within $1MM; 2024Q4 is a PDF rounded to $MM). So it is a 12-month peak of a **stress estimate**, not an observed payment.
     - 7.1 is a quarter-end snapshot. DTCC's note on 7.1.9: "Resources reported in Section 7.1 are as of 6/30/26 and do not correspond to the dates of the actual largest obligations."
     - Confirmation: NSCC 7.3.4 ÷ 7.1 > 1 in 18 of 22 quarters, yet 7.3.2 (business days on which the obligation exceeded QLR available at that point) is 0 in 14 of those 18 (2023Q4, 2024Q1 and 2025Q4 are > 1.25 with 7.3.2 = 0). In 2021Q1, 7.3.2 = 1 with the ratio at 0.31.
   - **Effect:** V changes in 11 of 22 quarters for each entity (`v_7_3_1_quarters.csv`). For the week of 2026-10-05: GSD-02 V 5 → 4 (severity 15 → 12, rank 1 → 2; ties GSD-03 at 12 and loses on S, 3 vs 4); NSCC liquidity unchanged at V 3 (in 2026Q2, 7.3.1 = 7.3.4 = $65.96bn).
   - **Remaining limit:** 7.1 still excludes SLD at quarter end ("As of [quarter end] there were no SLD deposits on hand" in nearly every quarter). NSCC 7.3.1 ÷ 7.1 is still > 1 in 15 of 22 quarters, so the level stays above 1; only the percentile (V) is used. DTCC also states the measure is conservative: "resources are likely to increase during periods of stress over a 4-day default period, but no such increases are considered as potential risk mitigation" (PQD 2026Q2 Supplemental Explanatory Note, p.7).
b. **Proposal B (override, not a percentile): if 7.3.2 > 0 in the latest published quarter, V ≥ 4 for that card.**
   - 7.3.2 and 7.3.3 are reported for every quarter in `v_7_3_1_quarters.csv`. GSD: 0 in all quarters. NSCC: > 0 in 2021Q1 (1 day, $0.59bn), 2021Q2 (2, $5.13bn), 2021Q3 (2, $0.59bn), 2022Q1 (1, $0.13bn), 2023Q1 (1, $0.81bn), 2024Q3 (1, $3.98bn), 2024Q4 (2, $7.06bn).
   - B binds (raises V above A) only in NSCC 2021Q1, 2021Q3 and 2022Q1 (7.1 blank in 2022Q1, so V_A carries forward from 2021Q4 as in §11.4). It does not bind this week (2026Q2: 7.3.2 = 0 for both).
   - **Caveat on meaning:** a 7.3.2 day is a simulated default shortfall that NSCC covered with SLD, not an uncovered loss. PQD 2021Q3 note: "The SLD collections fully mitigated NSCC liquidity exposure … any start-of-day SLD collections are reported as QLR shortfalls for that business day". PQD 2024Q4 note: the two December shortfalls ($146.61MM and $7.06BN) "were addressed by the payment of a Supplemental Liquidity Deposit ("SLD") along with OCC's commitment to provide liquidity resources". So B flags quarters where NSCC needed SLD, i.e., resources were strained enough to call on them.
c. **Exclusion check for 2020Q4–2021Q2 (Proposal A): no exclusion needed.**
   - The break is in 7.3.4 only. In 2020Q4–2021Q2, 7.3.4 does not equal the trailing maximum of 7.3.1 for either entity, and NSCC 7.3.4 ($10.9–16.9bn) is below the same quarter's 7.3.1 ($36.0–40.7bn), which is impossible if both measured the same thing. The 7.3.4 row note then read "GSD/MBSD/NSCC did not utilize any of its liquidity resources to cover any member payment obligations", which suggests an actual-usage basis before 2021Q3. No revision-log entry explains the change.
   - 7.3.1 shows no break: the explanatory note describes the same estimated-obligation basis throughout ("estimated liquidity obligations that are based on multi-day obligations throughout the (T+2) settlement cycle plus the Long Allocation and CALM offsets" in 2020Q4; "throughout the settlement cycle plus the Long Allocation and … ("CALM") offsets" in 2026Q2). Levels are inside the later range (NSCC 2020Q4–2021Q2: 37.4, 40.7, 36.0 vs 29.8–66.0 from 2021Q3; GSD: 98.7, 63.5, 71.4 vs 53.1–98.0).
   - Logged, not excluded: two business changes that 7.3.1 reflects as real events, not reporting breaks: the enhanced SLD rule (implemented 2021-06-23) and the T+1 settlement cycle (2024-05-28).
   - If 7.3.4 were kept instead, 2020Q4–2021Q2 should be excluded from its history.
   - Evidence: `results/scoring/proposals/v_7_3_1_evidence.json`.
   - **Source:** the Supplemental Note is the "Supplemental Explanatory Note" on pp.6–7 of each PQD PDF. It was re-downloaded on 2026-10-23T02:59Z from files.dtcc.com with a plain client (HTTP 200, SHA-256 identical to the local copy). The legacy `www.dtcc.com/-/media/…` link returned 404, which is not a refusal.
   - **Unverified caveat (2026Q2):** quarter-end cash in 7.1.2 jumped to $45.0bn (from $27.4bn in 2026Q1). The quarter end coincided with NSCC's 2026-06-29 final-settlement rollover into 6/30 (PQD 17.3 note), which may have inflated quarter-end resources. This is not checked and changes no number here.

## 10. Proposed changes (not applied)

Written after the first run (2026-10-16 08:39 UTC). **None of these is applied**; each needs owner approval and a v2 of this spec.

1. **Trending signals under an expanding percentile (NSCC-03, also GSD-02 / NSCC-02).**
   - NSCC-03 consolidated volume has risen since 2018, so recent weeks rank high almost automatically: S = 5 in 158 of 301 weeks since 2021, and S = 1 in none.
   - Adjusted SOFR−EFFR scores S = 5 in 44% of 2024 weeks and 58% of 2025 weeks.
   - **Option:** score these on a trailing window (e.g., the prior 104 weeks only), or on a detrended signal (weekly peak ÷ trailing 52-week median).
2. **Zero-inflated signal (GSD-04, Baa 20-day widening clipped at 0).** Most weeks are 0, and midrank puts a zero week near the 20th–40th percentile. So S never falls below 2 (136 of 301 weeks at S = 2). **Option:** assign S = 1 when the weekly peak equals the series minimum (0).
3. **Rubric "active" window for announced future events.** An event counts from announcement with timing 0, so SET-01 holds S = 3 for about 15 months between the T+1 adoption and the go-live, and GSD-03 holds S = 2 while compliance dates are more than 12 weeks away. **Option:** make an event active only when timing ≥ 1, or when there is new news about it that week.
4. **History V is not point-in-time (§5).** For backtests, use the PQD quarter whose `listed_date` ≤ week_end, with the percentile computed on history available then.
5. **Insufficient history before late 2020 for the SOFR−EFFR chains** (104-week minimum; the adjusted series starts 2018-10). The 2019 repo and 2020 COVID weeks therefore have no S. This affects only the sanity print, not current scoring.

Items 6–8 (added 2026-10-23T03:02Z) were approved and became v1.2 rules 1–2 in §12; their evidence moved there.

9. **Smoothing V over two quarters (proposed 2026-10-23, not applied; to be evaluated separately).** With the 7.3.1-based ratio (§12.1), V moves more from quarter to quarter: it differs from the 7.3.4-based V in 11 of 22 quarters per entity, and NSCC V goes 5 → 1 from 2025Q1 to 2025Q2. **Option:** V from the mean (or max) of the latest two quarters' percentiles. Evaluate it on history before any decision; it needs owner approval and its own spec version.

## Change log

| Time (UTC) | Change | Before or after scores |
|---|---|---|
| 2026-10-16 08:37:13 | v1 written and frozen; committed as `8d75706` on branch `weekly-scoring` | Before |
| 2026-10-16 08:39 | §10 proposed changes added (not applied) | After |
| 2026-10-16T08:44:54Z | v1.1 calibration fixes (§11) written and committed before re-running | Before v1.1 scores (after v1.0 scores) |
| 2026-10-16T08:46:38Z | §11 item 5b clarification (floor rule vs insufficient history) | Before v1.1 scores |
| 2026-10-16T08:48:35Z | v1.1 run: event register v1.1 applied (EV0001/04 quotes; EV0003 confirmed go-live 2026-06-28; EV0006/07 certainty 2, no 2026 extension found; EV0008 reach 2); v1.0 outputs kept as *_v1.0.* | After v1.1 rules committed (2d0f9db) |
| 2026-10-23T03:02Z | §10 items 6–8 added (7.3.1-based V, 7.3.2 override, 2020Q4–2021Q2 check); comparison written to `results/scoring/proposals/`; active rules and outputs unchanged | After v1.1 scores |
| 2026-10-23T03:15Z | v1.2 (§12) written before re-running: liquidity V from 7.3.1 ÷ 7.1, NSCC SLD override, event rubric v1.2, market + events S = max; former §10 items 6–8 moved to §12; §10 item 9 (two-quarter V smoothing) proposed, not applied | Before v1.2 scores |

# Weekly scoring spec v1.3-indicator (16 final cards)

Status: **APPROVED** (Wenqi Cai, 2026-11-05T04:45Z)

Written 2026-11-05 on branch `feat/v1.3-indicator-dashboard`, before any v1.3 score was computed. Base: `main` at `b34bc3e`. v1.2 (`results/scoring/SCORING_SPEC.md` §1–§12) stays frozen; its code and outputs are not changed (§8).

## 1. Purpose and scope

v1.3 scores the 16 PROPOSED final cards (`risk_business_ml/final16_quarterly_vulnerability_2026_10_27/config/card_registry.json`) for the Risk Horizon dashboard, before the LLM news classifier exists. Shocks come from market indicators and from the hand-entered event register only. News is not scanned, and every record says so (`news_coverage = "manual_register_only"`).

## 2. What changes from v1.2

| Topic | v1.2 | v1.3-indicator |
|---|---|---|
| Cards | 9 legacy cards | 16 final cards; legacy ids are mapped (§5) |
| Market S | §3A, §11.1 and §11.2 | **Unchanged.** Same functions, imported from `validation/scoring.py` |
| Event S | rubric v1.2 (§12.3), S = max(market, event) (§12.4) | **Unchanged** rule; register card ids mapped to final16 ids (D4) |
| V | PQD only, from chain_confidence fields (§11.4, §12.1, §12.2) | final16 V via `final16_vulnerability.get_v`: PQD or public proxy, as-of (D5) |
| Card with no market signal and no active event | S = 1 ("no active event") | **S = null, status `news_not_scanned`** (D1) |
| Incomplete data week | not checked | **status `data_incomplete`, S = null**, or scored from an active register event (D1, §4) |
| Human check | S ≥ 4 on an event (rubric) | **any** card-week with S ≥ 4 (D4) |
| Cross-entity cards | n/a | one record per business line (D2) |
| Dashboard flag | n/a | `show_on_main = severity ≥ 6` (D5) |

## 3. Weeks

- A week is Monday–Friday, labelled by its Monday (`week`). `week_end` is the Friday.
- Market S is the §3A value for the Friday label.
- Weeks in scope: **2026-10-19**, for comparison with v1.2, and **2026-10-26**, the week the dashboard will show. Neither is scored until this spec is approved.

## 4. Status (D1)

Each card-week gets exactly one status:

| Status | When | S | V |
|---|---|---|---|
| `data_incomplete` | The card has a market signal, a series it needs does not reach the required date (below), and no register event is active. | null; the partial-week peak is not reported | shown |
| `data_incomplete` | The card has a market signal, every chain S is null (e.g. fewer than 104 prior weeks), and no register event is active. | null | shown |
| `scored` with `status_reason = "market_data_incomplete"` | The card has a market signal, a series it needs does not reach the required date, and a register event is active. | `S_event`; `S_source = "event_manual"`; `S_market` and `signal` null | shown |
| `news_not_scanned` | The card has no market signal and no active register event. | null | shown |
| `scored` | Otherwise. | 1–5 | shown |

**Data guard.** Each raw series must have an observation on or after its required date. There is no forward-fill across the week end.

| Signal field (v1.2) | Raw series | Required date |
|---|---|---|
| `ust10_abs_change` | DGS10 | Friday |
| `sofr_effr_adjusted` | SOFR, EFFR | Friday |
| `baa_widen20` | BAA10Y | Friday |
| `vix_jump` | VIXCLS | Friday |
| `mbs_spread_abs_wchg` | MORTGAGE30US (weekly); DGS10 | the actual release date in that week; Friday |
| `consolidated_shares` | Cboe consolidated daily shares | Friday |

- **Daily series.** If Friday is a holiday, the week passes once the next business day's observation exists.
- **Weekly series (MORTGAGE30US).** The week passes when the series has a release dated inside the week (Monday–Friday). The required date is that actual release date, normally Thursday. A holiday release counts: in Thanksgiving week, Wednesday 2026-11-25 is the required date. While no release for the week exists, the required date is the usual Thursday and the check fails.

**Decisions on the open points (2026-11-05).**
- Former open point 2: incomplete market data with an active register event is scored from the event, as in the table above.
- Former open point 3: insufficient history (no chain S, no active event) stays under `data_incomplete`.
- Former open point 4: the weekly-series holiday rule above.

## 5. Cards, lines and the legacy map (D2)

- **Business lines.** `results/scoring/v1.3_indicator/config/card_lines.csv` assigns each card one or more rows: `business_line`, `sub_line`, `id_suffix`, `risk_family`. Jay can edit this table. A card with several rows needs distinct `id_suffix` values. `business_line` must be one of the 10 dashboard lines.
- **Cross-entity cards.** XE-MEMBER, XE-DISRUPT, XE-SETTLEBANK and XE-CYBER each have one FICC row and one ECS row. They become two records, `<card>-ficc` and `<card>-ecs`, with identical scores and `cross_entity = true`.
- **Entities.** `entities` lists the entities a card touches, taken from its component chain ids: GSD, MBSD, NSCC, DTC. ECS-SET-01 counts as NSCC and DTC. A card is cross-entity when its entities fall under both FICC and ECS.
- **Legacy map.** Each registry `component_ids` entry maps to its card, plus `NSCC liquidity → ECS-NSCC-LIQ`. In particular FICC-GSD-04 and ECS-NSCC-04 → XE-MEMBER.

**Market chains per card.** These are the component chains that have a signal field in `chain_confidence.json`:

| Card | Chains |
|---|---|
| FICC-GSD-01 | FICC-GSD-01 |
| FICC-GSD-02 | FICC-GSD-02 |
| FICC-MBSD-01 | FICC-MBSD-01 |
| ECS-NSCC-LIQ | ECS-NSCC-01, ECS-NSCC-02 |
| ECS-NSCC-03 | ECS-NSCC-03 |
| XE-MEMBER | FICC-GSD-04 |

The other 10 cards have no market signal.

## 6. Shock S (D4)

1. **Market S per chain.** `percentile_scores(scoring_signal(chain, field))` exactly as in v1.2:
   - weekly peak, expanding midrank percentile against prior weekly peaks;
   - at least 104 prior weeks;
   - one point per 20 percentile points;
   - NSCC-03 uses the 52-week-median ratio;
   - floor: a signal ≤ 0 gives S = 1.
2. **Card market S.** The maximum over the card's chains. The chain that sets it fills `signal`; the first in table order wins a tie.
3. **Event S.** v1.2 `active_events()` (rubric v1.2, `event_scoring.py`) and `apply_signoff()`, on `data/events/event_register.csv`. Each event's `card_ids` are mapped as in §5. Per card, the top event in v1.2 rank order (S, certainty, reach, recency) sets `S_event`.
4. **Combined S.** v1.2 `combine_s()`: S = max(market S, event S) when an event is active.

   | `S_source` | Meaning |
   |---|---|
   | `market` | No active event, or market S > event S |
   | `event_manual` | Event S > market S, the card has no market signal, or the market data is incomplete (§4) |
   | `market+event_manual` | Market S = event S |

   The labels name the input that set the final S, as in v1.2 `combine_s`. When the market S is higher, the source is `market` even if an event is active. This was former open point 6; decided 2026-11-05 to keep it unchanged.

5. **Human check.** `needs_human_signoff = true` whenever S ≥ 4, whatever its source. An event sign-off in `event_signoffs.csv` still clears only that event's own review flag, as in v1.2 §12.3. **Superseded by Amendment A.**

## 7. Vulnerability V, severity, confidence (D5)

- **V.** `get_v(card_id, as_of = week_end)`: the latest quarter whose `available_date` is on or before the week's Friday, which is the same as-of rule as v1.2 §11.4. Simulated V and prelaunch counterfactuals are never used; these are `get_v` defaults.
- **V fields.**
  - `V`, `V_base`, `V_tier` (pqd or public_proxy), `V_quarter` and `V_available_date`.
  - `V_driver`: from `results/v_driver_checks.json`.
  - `V_flags`: `corr_gt_0.7_with_S`, `V5_share_gt_0.5`, `history_lt_8_quarters`, `weak_proxy`, `detrended`, `V_override`.
  - `V_caveats`: from `get_v`.
- **Severity.** severity = S × V, from 1 to 25. It is null when S or V is null.
- **show_on_main.** `severity ≥ 6`; false when severity is null.
- **chain_confidence.** Read-only from `results/chain_tests/chain_confidence.json`. Shown separately and never multiplied into severity. This was former open point 1, decided 2026-11-05. `level` is the level of the chain that set S:

  | Case | Chain used | `rule` |
  |---|---|---|
  | `S_source` is `market` or `market+event_manual` | the signal chain (`signal.chain_id`) | `signal_chain` |
  | `S_source` is `event_manual` | the first of the driving event's register `card_ids` that is a tested chain of this card (e.g. ECS-NSCC-04 for XE-MEMBER) | `driving_event_chain` |
  | `event_manual`, but no such chain | the card's lowest tested chain | `lowest_tested_chain (driving event not on a tested chain)` |
  | S is null | the card's lowest tested chain | `lowest_tested_chain (S null)` |
  | The card has no chain test (8 cards) | none; `level = "Low"` | `untested` |

  The record also lists every tested component chain and its level (`chains`).

## 8. Protected files and approval gate

These must not change in v1.3. `results/scoring/v1.3_indicator/protected_files.json` holds their sha256 at `b34bc3e`, and `validation/test_scoring_v1_3.py` checks them:
- `validation/scoring.py`
- `results/scoring/SCORING_SPEC.md`
- all v1.0–v1.2 `results/scoring/**/weekly_scores*` files
- `results/chain_tests/chain_confidence.json`
- `validation/final16_vulnerability.py`
- `validation/event_scoring.py`

`validation/export.py`, which writes chain_confidence.json, is never called.

v1.3 outputs go only under `results/scoring/v1.3_indicator/`.

## 9. Output record (one per card-week per line row)

| Field | Type | Notes |
|---|---|---|
| `record_id` | string | lowercase card id, plus `-<id_suffix>` for multi-line cards |
| `card_id`, `legacy_v12_cards` | string, string[] | final16 id; mapped v1.2 cards |
| `week`, `week_end` | date | Monday; Friday |
| `spec_version`, `official` | string, bool | `v1.3-indicator`; false until approved |
| `title`, `card_status` | string | registry `name_en`; `PROPOSED` |
| `business_line`, `sub_line`, `region`, `risk_family` | string | from `card_lines.csv`; region `US` |
| `cross_entity`, `entities` | bool, string[] | D2 |
| `status`, `status_reason` | string | `scored` / `news_not_scanned` / `data_incomplete`; the reason when not scored, or `market_data_incomplete` for an event-scored market card (§4) |
| `S`, `S_source` | int 1–5 or null; string or null | §6 |
| `S_market`, `S_event` | int or null | the inputs to the max rule |
| `signal` | object or null | `{name, description, chain_id, value, percentile, prior_weeks, method}`; `value` is the weekly peak (the ratio for NSCC-03) |
| `market_chains` | object[] | per chain: field, description, S, weekly_peak, percentile, prior_weeks, method, reason |
| `data_coverage` | object | per raw series: `{last_date, required_date, ok}` |
| `event_manual` | object | `{active_events, driving_event_ids, needs_review, events[{event_id, title, S, certainty, reach, timing, effect_date, needs_review, review_reasons, signed_off_by}]}` |
| `V`, `V_base`, `V_tier`, `V_driver`, `V_metric`, `V_quarter`, `V_available_date`, `V_flags`, `V_override_reason`, `V_caveats`, `V_null_reason` | | §7 |
| `severity`, `show_on_main` | int 1–25 or null; bool | §7 |
| `needs_human_signoff` | bool | S ≥ 4 |
| `chain_confidence` | object | `{level, rule, chain_id, chains{chain_id: level}}` (§7) |
| `news_coverage` | string | always `manual_register_only` |

Dashboard-only text (transmission steps, sources, display labels) belongs to the export step and is not part of the scoring record.

## 10. Commands

From `Capstone_Project/`:

- `python -m validation.scoring_v1_3 coverage --week <Monday> [...]` — D1 guard per series; no scores.
- `python -m validation.scoring_v1_3 register --week <Monday> [...]` — register rows with their final16 ids and active flags; no scores.
- `python -m validation.scoring_v1_3 score --week <Monday> [...]` — refused while DRAFT. Once approved it writes `results/scoring/v1.3_indicator/weekly_scores_v1.3_<week>.json`: header (spec status, versions, week, run time) plus `records`, with `official = true`.
- `python -m pytest -v validation/test_scoring_v1_3.py` — fixture tests, no live data.

## 11. Open points

1. **`risk_family` and `sub_line` values** in `card_lines.csv`: proposed, to be confirmed by Jay. They are display fields only and do not change S, V or severity.

Former points 1, 2, 3, 4 and 6 were decided on 2026-11-05 and are recorded in §4, §6 and §7.

## Amendment A — sign-off scope, daily values, shared signals

Approved: Wenqi Cai, 2026-11-05T04:55Z. Written before the re-run of the weeks of 2026-10-19 and 2026-10-26; the earlier outputs for those weeks are replaced by the re-run. Amendment A replaces §6.5 and adds fields to §9. Nothing else changes: S, V, severity, status and show_on_main are computed as before.

**A1. Human sign-off (replaces §6.5).**
- `needs_human_signoff = true` only when a register event sets S, S ≥ 4, and the driving event has no sign-off covering that S.
- A register event sets S when `S_source` is `event_manual` or `market+event_manual`. A tie counts as event-set.
- A sign-off covers S when the driving event row carries `signed_off_by`. That is v1.2 `apply_signoff`: a row in `data/events/event_signoffs.csv` with the same certainty and reach and `max_S ≥ S`, on an event whose only review reason is the S ≥ 4 check.
- A sign-off clears the flag. A market-driven S (`S_source = market`) never needs a sign-off.

**A2. Daily values behind a market S ≥ 4.**
- Every record with `S_market ≥ 4` carries `signal.daily_values`: the observations of that week (Monday–Friday) of the transformed signal series whose weekly maximum is the weekly peak, as `[{date, value}]`. For MORTGAGE30US this is the single weekly survey value.
- It also carries `signal.daily_inputs`: the raw series behind those values for the same days, `{series: [{date, value}]}`. For the Cboe ratio it carries `signal.ratio_denominator`, the median of the prior 52 weekly peaks.
- `signal.peak_check` is true when the maximum of `daily_values` (divided by `ratio_denominator` for the ratio) reproduces `signal.value`. A false check stops the run.
- Records with `S_market < 4` or no market S have no `daily_values`.

**A3. Shared signals** (matching rule superseded by Amendment B).
- A record "takes S from" the raw series of every chain whose chain S equals `S_market` (§4 data-guard table), when `S_source` is `market` or `market+event_manual`.
- When two records of different cards in the same week take S from at least one common raw series, each lists the other's `card_id` in `shared_signal` (sorted). `shared_signal_series` gives the common series per card.
- The two records of one cross-entity card do not list each other. Records that do not take S from a market series have `shared_signal = []`.
- These fields are for display only. Severity is not adjusted.

**A4. Event provenance.** Each entry in `event_manual.events` also carries `outlet`, `source_tier` and `source_urls` from the register. This is display only.

## Amendment B — shared signals by transformed signal field (display only)

Approved: Wenqi Cai, 2026-11-05T05:15Z. Written before the re-run of the weeks of 2026-10-19 and 2026-10-26. It replaces the matching rule of A3 and changes no score: S, V, severity, status, show_on_main and needs_human_signoff are computed as before.

- **B1.** A record takes S from the transformed signal field (e.g. `sofr_effr_adjusted`) of every chain whose chain S equals `S_market`, when `S_source` is `market` or `market+event_manual`.
- **B2.** `shared_signal` lists the other cards in the same week that take S from at least one of the same signal fields. A shared raw input no longer counts. For example, DGS10 feeds both `ust10_abs_change` and `mbs_spread_abs_wchg`, so FICC-GSD-01 and FICC-MBSD-01 do not share a signal.
- **B3.** `shared_signal_series` is replaced by `shared_signal_fields`: `{card_id: [signal field]}` for each card in `shared_signal`.
- **B4.** The two records of one cross-entity card still do not list each other. Records that do not take S from a market signal have `shared_signal = []`.

## Amendment C — unreviewed AI-classified events

Approved: Wenqi Cai, 2026-11-08T01:10Z. Proposed 2026-11-08. When approved it changed no existing output: no register row had `entered_by = llm-auto`. `validation/promote_reviewed.py` inserts such rows only while this `Approved:` line is present.

- **C1.** A register event with `entered_by = "llm-auto"` or `review_status = "unreviewed"` (inserted by `promote_reviewed.py` without a human decision) is an *unreviewed AI event*. Each entry in `event_manual.events` carries `entered_by` and `review_status`.
- **C2.** When an unreviewed AI event alone sets S (`S_source = event_manual`), the record has `show_on_main = false`, whatever its severity. If the market S is equal or higher, the market alone justifies S, and `show_on_main` follows §7.
- **C3.** Records whose S comes wholly or partly from an unreviewed AI event carry `event_review_label = "AI-classified, not reviewed"`.
- **C4.** S, V, severity and `needs_human_signoff` are unchanged. S ≥ 4 from any event still needs the matching sign-off, as in A1.
- **C5.** The dashboard must honour `show_on_main` and show `event_review_label`. This needs a `docs/` change that is not part of this amendment.

## Amendment D — market-move news is context on indicator cards

Approved: Wenqi Cai, 2026-11-08T01:10Z. Written before any code change for it. It changes no existing v1.3 score: S, V, severity, status, show_on_main and needs_human_signoff are computed as before, and no register row exists yet that it would reclassify.

- **D1. Event type.** The classifier records `event_type` for every relevant item. Values:
  - `market_move`: price, yield, spread, volatility or volume moves of a market or asset class;
  - `regulatory`: rules, deadlines, regulator or DTCC actions;
  - `firm_specific`: something happening to one or more identified firms (losses, margin calls, downgrades, deleveraging, default);
  - `operational`: outages and system or settlement problems that are not cyber;
  - `cyber`;
  - `other`.
- **D2. Indicator cards.** FICC-GSD-01, FICC-GSD-02, FICC-MBSD-01, ECS-NSCC-LIQ, ECS-NSCC-03 and XE-MEMBER. For each card of an event: if the card is an indicator card and `event_type = market_move`, the event is *context* for that card. It does not set `S_event`, does not count toward `review_tier`, and appears only as related news. On every other card, the event is scored as before.
- **D3. Context file.** Context items go to `data/events/context_news.csv` (week, card_id, title, outlet, url, event_type, proposed_event_id). They never go to `event_register.csv`. `promote_reviewed.py` never inserts a context-tier row, and for an event that is context on some cards it inserts only the scored cards.
- **D4. Related news.** `scoring_v1_3` adds a `related_news` list to each record from that file, matching card_id and week. It is display only.
- **D5. Review tier**, computed after the context rule:
  - `required` if any scored (non-context) card has a would-be S ≥ 4 or severity ≥ 6;
  - `context` if every card of the event is context;
  - otherwise `auto`.

## Amendment E — review-sheet checks after validate()

Approved: Wenqi Cai, 2026-11-09T21:12Z. E1–E4 describe checks already in `validation/review_sheet.py` (prompt v1.6, commit 7ed9f5d); this amendment is written before the code for E5. It changes no existing v1.3 score: S, V, severity, status, show_on_main and needs_human_signoff are computed as before. It decides only which proposed events can reach the register and which items appear as related news.

- **E1. Fields (prompt v1.6).** For every relevant item the classifier records:
  - `geography`: `us`; `non_us_with_us_link` (only when the text itself states a link to US markets, US firms or DTCC participants); or `non_us`.
  - `new_information`: set only when `same_as_event_id` is set. It is `true` if the text adds a new date, action, figure or stage compared with the recorded event, otherwise `false`. It is null when `same_as_event_id` is null.

  Both are null for irrelevant items. Candidate files from older prompts lack these fields; E2 and E3 then do not apply.
- **E2. Non-US filter.** An item with `geography = non_us` is dropped before grouping and logged to `filtered_non_us.csv` in the run folder. It never reaches the review sheet, the register or the related news.
- **E3. Duplicate tier.** A proposed event whose items all have `same_as_event_id` set and `new_information = false` gets `review_tier = duplicate`.
  - `promote_reviewed.py` never inserts it.
  - Its items go to `context_news.csv` as related news on each of its cards (D3, D4).
  - An event with new information keeps its tier and, as before, is listed for a manual merge.
- **E4. Date flags (`date_flags` column).**
  - `date_unverified`: one independent source, every item headline-only, and `event_type` operational or cyber. It is a flag for the reviewer only; the tier is unchanged.
  - `date_mismatch`: an item's `announced_date` is more than 14 days from its feed published date. The event gets `review_tier = date_review` and is kept out of the week's tiering. Like `required`, it needs a decision before `promote_reviewed.py` runs.
- **E5. FICC-GSD-11 gate.** After the non-US filter and before grouping, FICC-GSD-11 stays on an item only if its headline, summary or text contains one of these terms: Treasury, Treasuries, repo, basis trade, SOFR, sponsored, agent clearing.
  - Matching ignores case and uses whole words. The plurals "repos" and "basis trades" and the hyphenated "basis-trade" and "agent-clearing" also count.
  - Otherwise the card is removed from that item, and an item left with no card is dropped.
  - Each removal is logged to `card_gate.csv` in the run folder and added to the item's flags.
  - Grouping, the D2 context rule and the D5 tier are computed after the gate.
- **E6. Order and precedence.** validate() per item → E2 → E5 → grouping → validate() on the combined sources → D2 context rule → D5 tier. Then `duplicate` (E3) replaces any tier, and otherwise `date_review` (E4) replaces any tier.

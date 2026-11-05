# Weekly scoring spec v1.3-indicator (16 final cards)

Status: **DRAFT** — not approved. No v1.3 scores are produced until the owner changes this line to `Status: **APPROVED** (<who>, <UTC time>)` and commits it. `python -m validation.scoring_v1_3 score` refuses to run while this line says DRAFT.

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

5. **Human check.** `needs_human_signoff = true` whenever S ≥ 4, whatever its source. An event sign-off in `event_signoffs.csv` still clears only that event's own review flag, as in v1.2 §12.3.

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

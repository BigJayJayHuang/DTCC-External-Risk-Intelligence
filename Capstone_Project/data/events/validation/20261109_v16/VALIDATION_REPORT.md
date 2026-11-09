# Validation of prompt v1.6 (card catalog v2), 2026-11-09

Settings: model `us.anthropic.claude-sonnet-4-6` (us-east-2), prompt `classifier-prompt-v1.6:0ed6cdbf0b01`, flat schema (strict off, checked in code),
prompt caching on, max_tokens 2000. v1.2 remains the classifier default. Hard cap for this validation: USD 2.50.

## a) Golden set (16 items)

Full table: `golden/GOLDEN_REPORT.md`.

- Expected relevant found with an acceptable card: **6 of 6**.
- Non-borderline negatives marked relevant: **2 of 9**: Invesco QQQ record volume (market_move; under Amendment D it would be context on
  ECS-NSCC-03 / ECS-NSCC-LIQ) and the National CERT warning (PhoneWorld, Pakistan; the model set geography "us" because the headline names no country).
- The Korea T+1 item and the French bank item are now marked irrelevant (non-US, no stated US link).
- Tokens: 23,926 input, 10,230 output, 4,373 cache write, 65,595 cache read. Cost USD 0.2874 (USD 0.4786 without caching).

## b) Week of 2026-11-02, re-run from saved inputs

Inputs: `data/events/weekly/2026-11-02/run_20261109T190208Z/inputs/feeds/classifier_input.csv` (no new fetching); 93 items in the window.
Run: `data/events/weekly/2026-11-02/run_20261109T203937Z/`. Review sheet (new file): `data/events/review/review_2026-11-02_run_20261109T203937Z.csv`.
Context rows were written to `week/context_news_preview.csv`, not to `data/events/context_news.csv`.

Classifier: 25 relevant, 68 irrelevant, 0 errors. Tokens: 141,461 input, 52,306 output, 406,689 cache read, 0 cache write
(the cache was still warm from the golden run). Cost USD 1.4641 (USD 2.6719 without caching).

| Tier | v1.5 run (19:02Z) | v1.6 re-run |
|---|---|---|
| required | 5 | 3 |
| auto | 5 | 2 |
| context | 4 | 3 |
| duplicate | – | 1 |
| date_review | – | 0 |
| filtered non-US (code check) | – | 2 |
| proposed events | 14 | 9 |

### The 10 reviewed events (`validation/fixtures/review_truth_2026-11-02.csv`)

| Proposed event (v1.5) | Your decision | v1.6 outcome | Matches |
|---|---|---|---|
| 1e8cd493 US regulator advances 24-hour trading | required, reject | still **required** (ECS-SET-01, geography us, S 4). Headline-only and the headline says "stock trading"; the CFTC/futures fact is not in the text the model sees | no (still needs your reject) |
| c7d07f39 Hedge Funds Dump Positions | required, reject (context on ECS-NSCC-LIQ) | WSJ item: new proposal **9a4a3088, required** (firm_specific, ECS-NSCC-LIQ + FICC-GSD-11, S 3). The second item (non-US outlet) went to context group 62a72582 | no |
| 1f565142 DTCC Treasury clearing final steps | required, reject (no new info, EV0006) | **duplicate**: same_as **EV0005**, new_information false; never promoted | yes (outcome); recorded event is EV0005, not EV0006 |
| c25bff32 French banking group supply-chain cyberattack | required, reject (non-US) | model: irrelevant (non-US, no stated US link) | yes |
| b970bc72 Thinkorswim outage | required, reject (old article) | still **required**, now flagged `date_unverified`; feed date 2026-11-06, so `date_mismatch` cannot fire | no (flagged; still needs your reject) |
| 59b09a07 Korea T+1 (아시아경제) | auto, reject | relevant, geography non_us, **filtered** to filtered_non_us.csv | yes |
| 1609bdc0 Korea T+1 (뉴스웍스) | auto, reject | relevant, geography non_us, **filtered** | yes |
| c6d01837 BofA analyst downgrade | auto, reject | still **auto** (XE-MEMBER stage 1, S 3); the model treated an analyst downgrade as a stress signal despite "downgraded by a rating agency" | no |
| c771bfa5 French bank €100M | auto, reject | both items: model irrelevant (non-US) | yes |
| 5a1aeeb0 Arini | auto, keep | **auto** (XE-MEMBER, S 2) | yes |

6 of 10 match. The 4 misses are all headline-only items from a single source.

### New required events

No new story reached the required tier. One required row has a new proposal ID, because its card set changed
(v1.5 c7d07f39 → v1.6 9a4a3088). It is the WSJ hedge-fund item you already rejected. Full row:

| column | value |
|---|---|
| proposed_event_id | PE-2026-11-02-9a4a3088 |
| title | Hedge funds dump positions, cut staff as selloff deepens |
| event_type | firm_specific |
| card_ids | ECS-NSCC-LIQ\|FICC-GSD-11 |
| scored_card_ids | ECS-NSCC-LIQ\|FICC-GSD-11 |
| context_card_ids |  |
| certainty | 1 |
| certainty_before_grouping | 1 |
| reach | 1 |
| reach_basis | group |
| announced_date | 2026-11-06 |
| effect_date | 2026-11-06 |
| would_be_S | 3 |
| would_be_severity | {"ECS-NSCC-LIQ": {"V": 3, "severity": 9}, "FICC-GSD-11": {"V": 3, "severity": 9}} |
| review_tier | required |
| geography | us |
| new_information |  |
| date_flags |  |
| same_as_event_id |  |
| stage |  |
| named_participants |  |
| independent_outlets | 1 |
| syndication_collapsed | 0 |
| member_event_types | {"firm_specific": 1} |
| sources | [{"outlet": "WSJ", "url": "https://news.google.com/rss/articles/CBMiqgFBVV95cUxPOFBSNTF3bXFWS1hzT2hRbDZZZFlJTUJlZ2U0OHdTdTBfcEEwdlRUSkk3bFlDM3Ixa1JaR3BUM1dyUFNRU0dWZG5FWE9pZHZwYjBRbGJtZGMzRk9ZZTdaNTAtbUJEWldKT1E0VTI1Q1hfcFEyNmg0WkVwaUdLcGIxZkJCRVZCcWxmX24wRGFEbnhqaFR0ZXNwSW8tNVlTVU5wNk92dVZyLWdiUQ?oc=5", "content_scope": "headline_only", "source_tier": "major_media", "headline": "Exclusive \| Hedge Funds Dump Positions and Cut Staff as Selloff Deepens", "evidence_quotes": ["Hedge Funds Dump Positions and Cut Staff as Selloff Deepens"], "item_flags": ["certainty capped at 1: no primary source and fewer than 2 independent outlets", "LLM confidence 0.50 below 0.7"]}] |
| evidence_quotes | ["Hedge Funds Dump Positions and Cut Staff as Selloff Deepens"] |
| confidence | 0.5 |
| validate_flags | ["certainty capped at 1: no primary source and fewer than 2 independent outlets", "LLM confidence 0.50 below 0.7"] |
| candidate_ids | CAND-2026-11-09-738b76f7f5686273672f6d3b |
| prompt_version | classifier-prompt-v1.6:0ed6cdbf0b01 |
| model | us.anthropic.claude-sonnet-4-6 |
| decision |  |
| reviewer |  |
| corrected_card_ids |  |
| corrected_certainty |  |
| corrected_reach |  |
| reviewer_notes |  |

## Code checks after validate()

- non_us → dropped and logged: 2 (both Korea T+1 items).
- same_as with new_information false → duplicate: 1 (DTCC Treasury clearing).
- date_unverified: 1 (Thinkorswim). date_mismatch: 0.

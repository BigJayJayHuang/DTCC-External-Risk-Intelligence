# Week of 2026-11-02 — all sources except Alpha Vantage, prompt v1.6 (2026-11-10)

Run `data/events/weekly/2026-11-02/run_20261110T033111Z` (from the input of dry run `run_20261110T032717Z`; Google results
reparsed offline from `run_20261110T031359Z`). Review sheet: `data/events/review/review_2026-11-02_run_20261110T033111Z.csv`.
Context rows went to `context_news_preview.csv` in this folder, not to `data/events/context_news.csv`.
Alpha Vantage: not used (NEWS_SENTIMENT is premium; 1 request refused on 2026-11-10).

## Cost
Model `us.anthropic.claude-sonnet-4-6`, flat schema, caching. 165 items processed.
Tokens: 309,070 input, 88,522 output, 717,172 cache read, 4,373 cache write.
Cost USD 2.735 (USD 4.862 without caching); estimate USD 2.772; cap USD 4. No unresolved reservation.

## Tiers
| | count |
|---|---|
| required | 10 |
| auto | 2 |
| context | 3 |
| duplicate | 1 |
| date_review | 0 |
| filtered non-US (after the model) | 2 |
| FICC-GSD-11 gate removals | 2 |
| lost to a schema error (same_as without new_information) | 1 |

## Pre-model exclusions
| step | excluded |
|---|---|
| Google headline filter | 395 |
| Google 25-per-card cap | 31 |
| official items, no card keyword | 19 |
| official non-US items without a US term (FCA 8, ECB 1) | 9 |
| publisher-feed keyword pre-filter | 11 |
| outside the Monday–Sunday window | 1,536 |
| collector duplicates merged | 1 |

## Truth fixture (`validation/fixtures/review_truth_2026-11-02.csv`)
| event | decision | now | right? |
|---|---|---|---|
| 1e8cd493 24-hour trading | required, reject | required | no |
| c7d07f39 hedge funds (WSJ) | required, reject (context) | 9a4a3088 required (ECS-NSCC-LIQ only); second copy context | no |
| 1f565142 DTCC Treasury clearing | required, reject | duplicate (same_as EV0005) | yes |
| c25bff32 French banking group | required, reject | filtered non-US | yes |
| b970bc72 Thinkorswim | required, reject | required, date_unverified | no |
| 59b09a07 Korea T+1 (아시아경제) | auto, reject | filtered non-US | yes |
| 1609bdc0 Korea T+1 (뉴스웍스) | auto, reject | not in this week's Google results | yes |
| c6d01837 BofA analyst downgrade | auto, reject | auto | no |
| c771bfa5 French bank €100M | auto, reject | model: irrelevant | yes |
| 5a1aeeb0 Arini | auto, keep (later rejected on 2026-11-09) | auto | yes vs the fixture; no vs the later reject |

All three hard cases are still headline-only Google items (no summary source this week).

## New required events (titles only; see the review sheet)
- PE-2026-11-02-6ed3e28b Citigroup Global Markets joins FICC GSD as Agent Clearing Member (7 DTCC notices)
- PE-2026-11-02-4cbc12b7 SEC grants exemptive relief from eligible secondary market transaction definition (Federal Register)
- PE-2026-11-02-5b99e177 LTSE amends rule on Level 3 circuit breaker trading resumption (Federal Register)
- PE-2026-11-02-e960a9f3 NSCC rule change on ACATS for insurance and retirement products (Federal Register)
- PE-2026-11-02-1d6ffbfe Mizuho Securities USA additional account activation at DTCC (DTCC notice)
- PE-2026-11-02-51ecda4f Marshall Wace and Millennium hit in October AI rout (Financial Times)
- PE-2026-11-02-99e81ba3 State Street Bank Lending Pass-Through account retirement at DTCC (DTCC notice)

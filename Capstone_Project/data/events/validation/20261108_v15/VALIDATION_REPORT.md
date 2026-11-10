# Validation 2026-11-08: prompt v1.5, flat schema, caching, Amendment D

Total model cost: USD 0.7870 (golden USD 0.2791, 26 items USD 0.5079); cap USD 1.00. These outputs are previews: the canonical `data/events/review/` sheet and `data/events/context_news.csv` were not written.

## Golden set (16 items, `golden/`)

| Measure | Result |
|---|---|
| Expected relevant found with an acceptable card | **6 of 6** (v1.4: 5 of 6) |
| False positives | **3 of 9** |
| Borderline French-bank item | marked irrelevant |

Event types of the relevant answers: market_move (Tech stocks, Magnificent 7, Hedge Funds, Traders flock, QQQ), firm_specific (Arini), regulatory (DTCC Treasury clearing, Korea T+1), cyber (CERT warning). Under Amendment D the QQQ false positive is context, because both of its cards are indicator cards; the Korea T+1 and CERT items would still be scored. See `golden/GOLDEN_REPORT.md`.

## The 26 items marked relevant on 2026-11-08 (`rel26/`)

All 26 were again relevant. Event types: 18 market_move, 3 regulatory, 3 cyber, 2 firm_specific.

**Grouping, after a correction.** The first regroup chained the multi-card market-move items, for example "…traders flee to Treasuries" on ECS-NSCC-LIQ and FICC-GSD-01, into one 18-item event spanning four cards. That scored the whole selloff on FICC-GSD-11. Market moves are now grouped per card, as the rule says ("on the same card").

| | Proposed events | Required | Auto | Context |
|---|---|---|---|---|
| Before (v1.4, no context rule) | 17 | 13 | 4 | — |
| After (v1.5, Amendment D, per-card market moves) | 12 | 5 | 4 | 3 |

**Context rows:** 21 (ECS-NSCC-LIQ 16, FICC-GSD-01 4, ECS-NSCC-03 1).

**Syndication:** no copies were collapsed in this set; no two headlines from different outlets reached Jaccard 0.8.

See `rel26/review_preview_2026-11-02.csv` and `rel26/context_news_preview.csv`.

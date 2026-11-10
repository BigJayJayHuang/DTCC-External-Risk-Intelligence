# Bedrock classifier run — November 5, 2026

The completed batch classified the daily pipeline release's available news in **October 9–November 5, 2026**, inclusive. The newest source publication date is November 4. The input has 481 articles: 206 headline-only and 275 feed summaries. These are not full article bodies.

| Result | Value |
|---|---:|
| Articles processed | 481 |
| Model marked relevant | 0 |
| Model marked irrelevant | 481 |
| Candidates | 0; CSV contains its header only |
| Candidates per card | 0 for each of the 16 catalog cards |
| Parse/schema/check failures in completed batch | 0 |
| Forced tool responses | 481 |
| Text responses / fence fallback | 0 / 0 |
| Throttling retries | 0 |
| Input tokens | 2,004,897 |
| Output tokens | 55,891 |
| Total tokens | 2,060,788 |
| Cached input tokens | 0 |
| Estimated USD cost | 7.5383616 |
| Budget | USD 10; not exhausted |
| Pre-batch agreement | AVAILABLE |

The corrected-schema dry-run estimate was **USD 11.2210758**, using 528 output tokens per article as an explicit assumption. The returned irrelevant records were much shorter. Actual estimates use returned usage at USD 3.30/million input and USD 16.50/million output tokens; taxes and account-specific discounts are excluded.

**Zero relevant records is the model's assessment of the supplied feed text, not a verified claim that no external risks occurred.** No events were promoted or signed off. Full level/date/evidence checks apply only to relevant records, so the completed batch did not produce an Event requiring those checks. The adapter to the existing `event_scoring.validate` was exercised by offline tests, including level caps and fabricated-quote rejection. Irrelevant decisions and their explanations remain available for review.

An initial setup request was rejected with HTTP 400 because the endpoint rejected a nullable enum for `stage`. It returned no model output or token usage. That failed run and its exact error are preserved under `classifier_runs/phase2_20261105/`. The schema was corrected to explicit integer-or-null alternatives, checked offline, and dry-run again before the successful batch. There was no automatic retry of that rejected request.

## Inspectable evidence

- [Candidate CSV](candidates_2026-11-05.csv) and [all 16 card counts](candidates_per_card_2026-11-05.csv).
- [Completed summary](classifier_runs/phase2_20261105_v2/summary.json).
- [All irrelevant records and explanations](classifier_runs/phase2_20261105_v2/irrelevant.jsonl).
- [Raw outputs](classifier_runs/phase2_20261105_v2/raw/) and [supplied source texts](classifier_runs/phase2_20261105_v2/articles/).
- [Output audit](classifier_runs/phase2_20261105_v2/output_audit.json): all 481 request hashes reconstructed, source texts matched, token/cost totals reconciled, and protected prompt/register hashes unchanged.
- [Corrected dry-run summary](classifier_runs/phase2_20261105_v2_dry_run/summary.json) and request-file hash manifest. Full prepared requests remain local to avoid publishing duplicate prompt copies; `--dry-run` rebuilds them from the frozen input and register.
- [Frozen pipeline input](classifier_inputs/2026-11-05/news.csv) and [source manifest](classifier_inputs/2026-11-05/source_manifest.json).
- [Classifier usage and limits](../../validation/LLM_CLASSIFIER.md).

The original prompt, event register and main branch were not changed by this implementation. No AWS credentials, keys or session tokens are included. Twelve offline classifier tests and the existing event-scoring examples passed. The PR's CI runs these tests without AWS access.

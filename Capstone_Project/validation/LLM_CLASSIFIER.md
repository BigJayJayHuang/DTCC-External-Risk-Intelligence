# Bedrock event-classifier candidates

The classifier reads the daily pipeline's `news.csv`, calls Claude Sonnet 4.6, and writes **review candidates only**. Every candidate has `needs_review=Y`, including records whose automatic checks pass. It never writes `data/events/event_register.csv` and never signs off an event.

The [daily-pipeline activation handoff](BEDROCK_DAILY_ROLLOUT.md) covers the prepared incremental job, DTCC's OIDC role, daily budget, durable state and recovery. Automated AWS execution remains disabled until that setup is complete.

## Run locally

From `Capstone_Project/`:

```bash
python3 -m venv .venv-llm
.venv-llm/bin/python -m pip install -r validation/requirements-llm.txt
aws sso login --profile devx-bedrock
export BEDROCK_PROFILE=devx-bedrock

.venv-llm/bin/python -m validation.llm_classifier \
  --start 2026-10-09 --end 2026-11-05 \
  --news data/events/classifier_inputs/2026-11-05/news.csv \
  --dry-run

.venv-llm/bin/python -m validation.llm_classifier \
  --start 2026-10-09 --end 2026-11-05 \
  --news data/events/classifier_inputs/2026-11-05/news.csv \
  --max-articles 481 --budget 10
```

`BEDROCK_PROFILE` defaults to `devx-bedrock`. Each teammate configures their own authorized SSO login; no access keys or session tokens belong in this repository. Model IDs, region, account check, and public token rates come from `llm_classifier_config.json`. Configure no automatic SDK retries: the application retries a throttled request at most twice, waiting 10 and 20 seconds. Access/subscription failures stop the batch immediately. Other invocation failures also stop; no alternate model is selected.

`--start` and `--end` are inclusive publication dates. Use the publisher's `publication_date` when present, otherwise the UTC calendar date in `published_at_utc`; never use `last_seen`. `--max-articles` limits the chronological, deduplicated input. The default news path is `capstone_database/exports/news.csv`; this committed export can be older than the daily release, so inspect coverage in the dry-run summary. A custom `--news` may point to an extracted, verified public daily-pipeline CSV.

The dated input in `data/events/classifier_inputs/2026-11-05/` was extracted from the pipeline release asset updated at `2026-11-05T05:25:44Z`. It has 1,604 rows and 481 articles in October 9–November 5; its newest publication date is November 4. The ZIP entry's CRC and the extracted CSV's SHA-256 were checked. The full 729 MB ZIP was not downloaded or independently hashed; the manifest labels its archive digest as advertised, not verified.

## Prompt and structured output

The original `llm_event_classifier_prompt.md` wording is unchanged. Code extracts its system body and 16-card table and substitutes only the three placeholders. The event-register snapshot supplies event IDs, titles, card IDs, and dates. Entries announced after the article's publication date are excluded; current register data is not a reconstructed historical register vintage. Unreviewed batch candidates are never added to that register context.

Converse uses temperature 0 and maxTokens 1200. `toolChoice` forces `submit_event_classification`, with `strict=true` and a JSON Schema. The tool's `classification` transport field contains either the prompt's full relevant record or its exact two-field irrelevant record. This envelope avoids exceeding Bedrock's optional-property limit. It does not add fields to the classification record or change the system prompt.

If a response contains text instead, the parser removes at most one outer Markdown JSON fence and parses the whole remaining text. It never searches for an arbitrary inner object, repeats a classification to repair formatting, or calls a tool on a user's computer. Every returned model content block is saved before parsing; text fallback and fence-fallback counts are reported separately. Truncated responses fail checks.

## Validation and review files

The classifier validates the schema, known card IDs, up to three distinct cards, ISO dates, confidence range, stage applicability, register match, source URL and source tier. Evidence quotes must occur verbatim in the supplied article text. It then constructs an `event_scoring.Event` and calls the existing `event_scoring.validate`. Any conservative level caps and review reasons are retained alongside original levels. Missing dates are flagged rather than invented to satisfy `Event`.

`major_participants.csv` currently has no names. A model claim of `major_participant` therefore cannot pass the maintained-list check: the existing validator caps reach and flags the record. No firms are silently added to that list.

Outputs under `data/events/`:

- `candidates_<run_date>.csv`: relevant, schema-parseable candidates, all requiring human review. Semantic check failures remain visibly flagged. Existing candidate CSVs are never overwritten.
- `classifier_runs/<run_id>/raw/`: original model content, stop reason, token usage, and retry count for each article; error responses are retained per attempted request.
- `classifier_runs/<run_id>/articles/`: the actual text supplied for evidence checks.
- `classifier_runs/<run_id>/irrelevant.jsonl`: irrelevant article IDs, URLs, reasons, usage and cost.
- `classifier_runs/<run_id>/failed.jsonl`: parse, validation and invocation failures, with article IDs and raw-output references.
- `classifier_runs/<run_id>/availability_before.json`: the single pre-batch availability check. `agreementAvailability=NOT_AVAILABLE` is recorded and does not prevent invocation.
- `classifier_runs/<run_id>/summary.json`: counts, per-card candidates, validation reasons, fallback counts, tokens, estimated cost, input/config/prompt hashes, protected-file checks and completion status.
- Dry runs write `prepared_requests.jsonl` and a summary; they do not create candidates, contact AWS, or invoke a model.

Article bodies are **publisher feed summaries or headlines**, not downloaded full articles. `content_scope` records that limitation on every candidate. A correct quote match proves support in the supplied feed text, not full-source verification or a confirmed business impact.

## Budget and billing estimate

The default cap is USD 10. The dry-run estimate uses UTF-8 request bytes/3 + 512 input tokens and 528 output tokens per article (the single Phase 1 output count), so it is an assumption rather than a tokenizer measurement. Irrelevant tool results can be much shorter.

Before each call, the run reserves a deliberately conservative allowance based on request bytes + 2,048 input tokens and the full 1,200 output-token limit. It stops before that allowance would exceed the remaining cap. Successful responses replace the reservation with their reported token cost. Missing usage or an ambiguous network failure stops the run and records an unreported-cost reserve. A budget stop is a partial batch, not a completed window.

Estimates use Standard US geographic list rates: USD 3.30 per million input tokens and USD 16.50 per million output tokens, with separate cache rates in config. No explicit caching is requested. Taxes and account-specific pricing are excluded; this is not an AWS billing statement. Rates were checked on November 5, 2026 against [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) and its [Bedrock rate table](https://www-cdn.anthropic.com/files/4zrzovbb/website/5678bc2f5978e5bcd4f1fe7c14b2c72284dcf9f8.pdf).

## Offline checks

```bash
.venv-llm/bin/python -m unittest validation.test_llm_classifier -v
.venv-llm/bin/python -m validation.test_event_scoring
```

These use labeled fixtures and fake clients. They test forced tool output, both relevance shapes, one-fence parsing, immutable prompt wording, future-event filtering, existing validator caps, budget blocking, missing-usage stopping, throttle-only retries, one availability check, and register preservation. They make no AWS requests.

AWS references: [toolChoice](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolConfiguration.html), [strict tool schemas](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html).

## Executed four-week run

The November 5 run completed all 481 articles for USD 7.5383616 estimated cost. It marked all 481 irrelevant and produced no candidate rows; all 16 per-card counts are zero. No text/fence fallback, check failure, or throttling retry occurred in the completed batch. See the [execution report](../data/events/CLASSIFIER_RUN_2026-11-05.md) for input limitations, raw outputs, the initial rejected-schema attempt and reconciliation evidence. The prompt and event register are unchanged.

For a repeat run on the same run date, select a fresh `--output-dir` so existing review CSVs cannot be overwritten. A new run creates new model charges under its own budget.

## Weekly Google News source and official-feed pre-filter

`validation/google_news.py` builds one classifier input per Monday–Sunday week (default: the last full week):

```bash
.venv-llm/bin/python -m validation.google_news --week-start 2026-11-02 --official <daily news.csv>
.venv-llm/bin/python -m validation.llm_classifier --start 2026-11-02 --end 2026-11-08 \
  --news data/events/classifier_inputs/week_2026-11-02/classifier_input.csv --dry-run --run-id week_2026-11-02
```

- **Queries.** `validation/news_queries.csv` has `card_id,query` rows: 47 queries for the 16 cards. `validation/google_news_config.json` holds the User-Agent, rate limit, per-card cap, title-similarity threshold and source-tier lists.
- **Fetching.** One Google News RSS search per query, `q=<query> after:<Sunday before> before:<Monday after>`. Plain `urllib` with an honest User-Agent (project URL, no email, no browser string), at most one request every 2 seconds. Collection stops on HTTP 429. Raw RSS is saved in `google_news_raw/` and listed in `fetch_manifest.json`.
- **Item fields.** Title, snippet, outlet, outlet homepage, published time (UTC) and Google link. The publisher URL is resolved only when the Google article ID can be decoded offline. Current IDs cannot be decoded, and the link redirects only through a JavaScript page (checked 2026-11-07). Such items keep the Google link as `url` and are marked `url_resolution = not_resolvable_without_browser`. Google's RSS description repeats the headline and outlet, so the snippet is usually empty. `content_scope = headline_snippet`.
- **Headline filter** (`headline_filter: true`, added 2026-11-07). Google matches loosely, often on article text not in the feed. After dedup, an item is kept only if:
  - its headline contains all terms of a query that returned it (`keep_rule = all_terms_headline_match`), or
  - its outlet is on the major-media list, whatever the headline overlap (`keep_rule = major_media_outlet`).
  
  `headline_term_match` records `full` / `partial` / `none`. Dropped items are listed in `google_news_filtered_out.csv`. The per-card cap is applied after this filter.
- **Dedup and cap.** Items are deduplicated by URL and by near-identical normalized title (similarity ≥ 0.9). Each item records every card query that matched it (`matched_card_ids`, `matched_queries`). At most 25 items are kept per card: most matched queries first, then newest.
- **Source tier.** From the config: listed major outlets are `major_media`, regulator and DTCC hosts get their tier, and everything else is `other`. The classifier compares the model's tier with this input tier.
- **Official-feed pre-filter.** The official feeds (Federal Register, DTCC notices, SEC/CFTC/Fed, FCA/ECB/ESMA/BIS) are kept only when a card query matches title + summary. All terms must appear, case-insensitive, outside longer words, with a plural or inflection suffix allowed. Filtered items are listed in `official_prefilter_filtered_out.csv`.
- **Hints.** The classifier receives `query_hint_card_ids` and a one-line note inside the article JSON. They are hints only; the prompt and rubric are unchanged and the model still decides relevance and cards.

### Week of 2026-11-02: collection and dry run (2026-11-07)

The week was incomplete when collected (Saturday 11-07); official rows reach 11-06.

| Step | Count |
|---|---|
| Google News requests | 47, all HTTP 200 |
| Hits dated in the week | 569 |
| After dedup | 534 |
| After the 25-per-card cap | 308 (11 `major_media`, 297 `other`; 0 publisher URLs resolvable; 0 non-empty snippets) |
| Official items | 107; kept 0, filtered 107 (no query matched) |
| Classifier dry run | 308 requests; estimate USD 7.21 by the classifier's method, about USD 4.84 calibrated with the Nov-5 actual/estimate ratio (0.672) |

The run stopped at the dry run: the estimate exceeds the USD 3 cap set for this week. No AWS call was made.

Google's matching is loose. Only 37 of the 308 headlines contain all terms of a query that returned them, at an estimated USD 0.58 calibrated.

### Week of 2026-11-02: filtered run (2026-11-07)

With the headline filter, 81 Google items and 0 official items went to the model (dry run USD 1.90). The real run, capped at USD 3, completed all 81: 0 relevant, 81 irrelevant, 0 failures. It used 353,055 input and 10,380 output tokens, about USD 1.34. See [the run report](../data/events/CLASSIFIER_RUN_2026-11-07.md), which includes ten random irrelevant items and a list of likely misses caused by headline-only input.

## Prompt v1.3 and prompt caching (2026-11-07)

`llm_event_classifier_prompt_v1.3.md` adds a clarified rule 1 and a section on headline-only and summary-only items. The v1.2 file is unchanged, and v1.2 remains the default, so earlier runs reproduce.

- **Selecting it:** `--prompt-version v1.3`. Every summary, raw output, irrelevant/failed line and candidate row records `prompt_version` (v1.3: `classifier-prompt-v1.3:<sha12>`).
- **Request layout:** the static rules and card catalog form the system text, followed by a Converse `cachePoint` (`--prompt-cache on`, the default for v1.3). The per-item `recent_events` and article go in the user message.
- **Cost figures:** cache read and write tokens are recorded. `estimated_cost_without_cache_usd` prices the same tokens as ordinary input. Cache rates are in `llm_classifier_config.json`; verify them on the AWS Bedrock pricing page.
- **Code checks (v1.3 only, headline-only scopes):** a relevant record with confidence > 0.6, or without "headline_only" in its notes, is flagged. Every candidate keeps `needs_review = Y`, and `review_basis` names headline-only input. `event_scoring.validate` is unchanged.

**Golden set** (`validation/fixtures/golden_set_20261107.csv`): 6 expected-relevant headlines, 9 expected-irrelevant and 1 borderline, from the week of 2026-11-02. Scored by `python -m validation.golden_eval`; see `data/events/golden_runs/20261107/classifier_runs/golden_v13/GOLDEN_REPORT.md`.

| Run | Prompt | Expected relevant found | False positives | Cache write / read tokens | Cost |
|---|---|---|---|---|---|
| `golden_v13` | v1.3, cache on | 0 of 6 | 0 of 9 | 3,080 / 46,200 | USD 0.138 (USD 0.273 without caching) |

The model applied the headline-only section but still judged each expected-relevant headline too vague.

## Publisher feeds, broad pre-filter and full text (2026-11-08)

`python -m validation.publisher_feeds` reads the feeds in `validation/publisher_feeds_config.json` (CNBC, MarketWatch, Yahoo Finance, Nasdaq, Federal Reserve, SEC).

- **Client:** the project's honest User-Agent, at most one request every 2 seconds. Each host's robots.txt is fetched with the same client and checked before any feed or article request. Per RFC 9309, a 4xx robots.txt means no restrictions, and a 5xx or no answer means do not crawl.
- **Pre-filter (no AI):** an item is kept when its headline or summary contains any single keyword from any card's query list (case-insensitive, word boundary). Matched keywords and card hints are recorded. Existing Google News items are added and stay headline-only.
- **Full text:** fetched only when robots.txt allows it, and never past a paywall. A page marked `isAccessibleForFree: false`, or HTTP 401/402/403, falls back to the RSS summary. Text is truncated to about 1,000 words, and `content_scope` is `full_text`, `summary` or `headline_only`.
- **What stays local:** full texts are written only to `data/events/fulltext_cache/`, and classifier article copies use a `.fulltext.txt` suffix; both are git-ignored. The repo keeps headline, URL, RSS summary, scope and `text_sha256`. The classifier verifies the hash before use.

**First collection (2026-11-08 00:26 UTC):**

| Source | Result |
|---|---|
| CNBC (4 feeds) | disallowed by `search.cnbc.com` robots.txt |
| Nasdaq | robots.txt unanswered, so not crawled |
| Yahoo Finance | configured feed 404; per-ticker feed host disallowed by robots.txt |
| MarketWatch | 50 items, 9 kept; article pages disallowed by robots.txt |
| Federal Reserve | 20 items, 7 kept, 7 full text |
| SEC | 25 items, 25 kept; article pages HTTP 403, so RSS summaries |

With the 81 Google items, 122 items were prepared (7 full text, 26 summary, 89 headline-only), published 2024-07-29 to 2026-11-07. None of the six golden positives appear in the publisher feeds. The dry-run estimate, with v1.3 as a stand-in, is USD 1.82 with caching (USD 3.00 at the full input rate). The v1.4 run awaits the v1.4 prompt text.

## Prompt v1.4 (2026-11-08)

`llm_event_classifier_prompt_v1.4.md` is v1.3 with two sections inserted after the Rules list, inside the cached system text: "Relevance vs. evidence strength" and "Worked examples (headline-only input)". Nothing else changed; its file header still says v1.3, and the code labels it `classifier-prompt-v1.4:<sha12>`. Select it with `--prompt-version v1.4`; v1.2 stays the default.

`load_news` now reports items outside `--start`/`--end` per source (`coverage.outside_date_window_by_source`).

**Run of 2026-11-08** (window 2026-11-01 to 2026-11-08, 83 items, cache on): 0 relevant, USD 0.68 (USD 1.58 without caching). See the [run report](../data/events/CLASSIFIER_RUN_2026-11-08.md). It also explains why every strict-schema run so far returned 0 relevant, and suggests a two-call check.

## Strict mode forced "irrelevant"; flat response schema (2026-11-08)

**Diagnostic** (`validation/llm_strict_diagnostic.py`, outputs in `data/events/diagnostics/strict_mode_20261108/`): the same v1.4 request was sent with the strict `anyOf` tool schema and with strict off.

| Input | Strict on | Strict off |
|---|---|---|
| v1.4 worked example 1 | irrelevant | relevant (ECS-NSCC-LIQ) |
| Golden "Tech stocks log worst day since 2020" | irrelevant | relevant (ECS-NSCC-LIQ) |

In one strict call the model's notes said "Setting is_relevant true" while the returned field was false. Constrained decoding never let the relevant branch through, which explains 0 relevant in every earlier strict run.

**Flat schema** (`--response-schema flat`, the CLI default):
- One object; every field is always present and null where it does not apply. No `anyOf`, `oneOf`, `if`/`then` or `const`.
- The tool is still forced, but strict mode is off.
- `validate_flat()` checks types, enums, catalog card_ids, ISO dates, confidence 0–1, and that relevant records fill every relevant field. Failures go to `failed.jsonl` and are never retried.
- `response_mode` is recorded.
- `--response-schema strict-anyof` reproduces earlier runs. `llm_daily.py` still calls the strict builders and should be switched before activation.

**Golden set with v1.4 + flat schema** (`data/events/golden_runs/20261108/GOLDEN_REPORT.md`; the first run hit its USD 0.30 sub-cap after 14 items, so the last 2 were run separately):

| Measure | Result |
|---|---|
| Expected relevant found with an acceptable card | 5 of 6 |
| Non-borderline negatives wrongly marked relevant | 3 of 9 |
| Cost | USD 0.270 |

The bar for re-running the 83-item window (≥ 5/6 and ≤ 1 false positive) was not met.

## Weekly run with the flat schema, review sheet and promotion (2026-11-08)

**Run** `data/events/weekly/2026-11-02/` (`v14_flat`, 83 items, 2026-11-01 to 2026-11-08, cache on): 26 relevant, 54 irrelevant, 3 hard failures sent to `failed.jsonl`. Cost USD 1.243 (USD 2.138 without caching). See `RUN_REPORT.md` there.

**Review sheet** (`python -m validation.review_sheet`) groups relevant candidates into proposed events:
- **Grouping:** candidates join one event when their card_ids overlap, their announced dates are at most 2 days apart, and their title+summary word Jaccard is ≥ 0.25 (connected components).
- **Certainty:** `event_scoring.validate()` runs on the combined sources, so independent outlets can lift the single-source certainty cap.
- **Scores and tier:** would-be S (rubric v1.2) and severity (S × final16 V for the week) set `review_tier` (`required` if S ≥ 4 or severity ≥ 6).
- **Output:** `data/events/review/review_2026-11-02.csv` with 17 proposed events (13 required, 4 auto).

**Promotion** (`python -m validation.promote_reviewed --sheet …`; written and tested, not run on real data):
- **Required rows:** enter only with approve/edit and a named reviewer.
- **Auto rows:** enter as `llm-auto` / `unreviewed` unless rejected, and only after Amendment C of the v1.3 spec is approved.
- **Updates to existing events:** rows with `same_as_event_id` are listed for manual merge.
- **Reruns:** the script is idempotent via `proposal_id`.
- **Sign-off:** S ≥ 4 still needs a matching sign-off, as today.

**Scoring and dashboard:** `scoring_v1_3` keeps an S set only by an unreviewed AI event off the main page and labels it "AI-classified, not reviewed" (Amendment C, proposed). The dashboard (`docs/`) does not yet read these fields.

# Bedrock event-classifier candidates

The classifier reads the daily pipeline's `news.csv`, calls Claude Sonnet 4.6, and writes **review candidates only**. Every candidate has `needs_review=Y`, including records whose automatic checks pass. It never writes `data/events/event_register.csv` and never signs off an event.

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

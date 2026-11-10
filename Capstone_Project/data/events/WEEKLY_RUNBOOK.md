# Weekly news runbook

This turns one week of news into a short list for review, then into scored events. The model only proposes. A person approves anything that would matter.

## 1. Run the week (once the week is over)

From `Capstone_Project/`, log in to AWS first:

```bash
aws sso login --profile devx-bedrock
.venv-llm/bin/python -m validation.weekly_news_run --week-start 2026-11-09 --cap 3
```

Alpha Vantage news summaries are **off by default**: NEWS_SENTIMENT is a premium endpoint, and a free key gets "This is a premium endpoint". With a premium key in `ALPHAVANTAGE_API_KEY`, add `--alphavantage`.

Two modes never call the model: `--collect-only` stops after collection (step 2), and `--dry-run` stops after the cost estimate (step 3). `--from-inputs <classifier_input.csv>` reuses a saved collection instead of fetching again.

`--week-start` is the Monday of a finished Monday–Sunday week. `--cap` is the most you allow the model calls to cost, in USD. The command then:

1. **Collects news for that week.**
   - Google News headlines for each card's search terms.
   - The publisher feeds in `validation/publisher_feeds_config.json`, which respect each site's robots.txt and never get past a paywall.
2. **Pre-filters without AI.**
   - Google items are kept only when the headline contains all the words of a search, or when they come from a major outlet.
   - Feed items are kept when they contain any search keyword.
3. **Estimates the cost (dry run).** If the estimate with caching is above `--cap`, it stops here and has spent nothing.
4. **Classifies each item** with prompt v1.6, the flat answer format and caching. It never spends more than `--cap`.
5. **Applies the Amendment E checks, then groups items about the same occurrence into proposed events.**
   - Items with geography `non_us` are dropped and logged to `filtered_non_us.csv`.
   - FICC-GSD-11 stays on an item only when its source text names Treasury, repo, basis trade, SOFR, sponsored or agent clearing. Removals are logged to `card_gate.csv`.
   - The groups follow Amendment D of the scoring spec.
   - Price, yield, spread, volatility or volume moves on cards that already have a market indicator become *context*: they are shown as related news and never scored.
6. **Writes two files:**
   - `data/events/review/review_<Monday>.csv`, the review sheet. An existing sheet is never overwritten.
   - New rows in `data/events/context_news.csv`.

Everything the run produced is in `data/events/weekly/<Monday>/<run id>/`, including `weekly_summary.json`. Full article texts stay on your computer, in `data/events/fulltext_cache/`, and are never committed.

**If the run stops with `stopped_unresolved_prior_cost_reserve`:** an earlier paid call of that week was interrupted, and its bill is unknown. The receipt (`classifier_runs/<id>/summary.json`) is never edited. To record the whole reserved amount as spent (an upper bound):

```bash
python -m validation.weekly_cost_reconcile --summary <that summary.json> --reconciled-by "<your name>" --reason "<why the exact bill cannot be confirmed>"
```

This appends a row to `data/events/weekly/cost_reconciliations.csv`, and paid runs for that week are unblocked.

## 2. Review (only the "required" rows)

Open the review sheet. Each row is one proposed event, sorted by the model's confidence. The `review_tier` column decides what you must look at.

| Tier | Meaning | What you do |
|---|---|---|
| `required` | Would score S ≥ 4 or severity ≥ 6 on a card | Fill `decision` (`approve`, `edit` or `reject`) and `reviewer`. For `edit`, also fill `corrected_card_ids`, `corrected_certainty` or `corrected_reach`. |
| `auto` | Lower scores | Nothing needed. It enters as "AI-classified, not reviewed" and stays off the main page. Write `reject` to keep it out. |
| `context` | Market move on an indicator card | Nothing. It is related news only and never enters the event register. |
| `duplicate` | Same as a recorded event, with no new information | Nothing. Its items become related news on its cards; it never enters the register. |
| `date_review` | The announced date is more than 14 days from the feed date | Same as `required`: check the date, then decide. |

Read each row's `sources` and `evidence_quotes` before you decide. Every quote is copied word for word from the source text. `validate_flags` lists the automatic checks that fired, for example a certainty cap when only one outlet reported it.

A row with `same_as_event_id` updates an event that is already in the register. Merge it by hand.

`date_flags` = `date_unverified` means a single headline-only source on an outage or cyber item: check the article's real date before approving.

## 3. Promote

```bash
python -m validation.promote_reviewed --sheet data/events/review/review_<Monday>.csv --dry-run   # check first
python -m validation.promote_reviewed --sheet data/events/review/review_<Monday>.csv
```

- **Refusals.** It refuses to run if any `required` row has no decision, and then writes nothing.
- **Approved and edited rows** enter `data/events/event_register.csv` with you as `entered_by`.
- **Auto rows** enter as `llm-auto` / `unreviewed`.
- **Context rows and rejected rows** never enter.
- **Reruns** are safe: rows already promoted are skipped.

## 4. Sign off anything with S ≥ 4

The script lists the new event ids that score S ≥ 4. For each one you accept, add a row to `data/events/event_signoffs.csv` with: the event_id, its certainty and reach, a `max_S`, your name, the UTC time, and a note on the source you checked.

Until that row exists, scoring keeps the event flagged for a human check. A sign-off covers only S up to its `max_S`. If the event later reaches a higher S, it needs a new sign-off.

## 5. Score the week (v1.3)

```bash
python -m validation.scoring_v1_3 score --week <Monday>
```

- **Scoring** uses market indicators plus register events.
- **Unreviewed AI events** (`llm-auto`) never put a card on the main page by themselves.
- **Context news** appears in each card's `related_news`.

## 6. Draft and review the So what / So now what text

```bash
python -m validation.narratives --week <Monday> --cap 0.50 --dry-run   # inputs and worst-case cost, no model call
python -m validation.narratives --week <Monday> --cap 0.50
```

- **What it writes.** One model call per scored card, with prompt `validation/narrative_prompt_v1.md`. The two rows of a cross-entity card share one call. Cards with any other status get fixed, non-AI template text.
- **Checks.** Every number must come from the card's input; word limits; no banned phrases ("must", "should raise", "recommend that DTCC", …); a public-proxy V, Low chain confidence and a shared signal must be mentioned. The result is in `check_flags`.
- **Review.** Open `data/narratives/review_narratives_<Monday>.csv`. For each AI row, fill `decision` (`approve`, `edit` or `reject`) and `reviewer`. For `edit`, fill `corrected_so_what` and/or `corrected_so_now_what`. A row with `check_flags` needs an edit before it can be published.
- **Display only.** This step never changes S, V, severity, status or ranking.
- **Prompt v3 (trial).** `--prompt v3 --compare-with …` writes `comparison_narratives_v3_<Monday>.csv` with the reviewed text, v2 and v3 side by side, plus word counts. v3 shortens v2: V written as "V k of 5 (low/medium/high vs own history)", so_what names only what sets S, no added interpretive words, no PQD on public-proxy cards.
- **Prompt v2 (trial).** `--prompt v2 --compare-with data/narratives/review_narratives_<Monday>.csv` drafts with prompt v2 and writes `comparison_narratives_v2_<Monday>.csv`: the reviewed text next to each v2 draft. It never writes the review sheet. v2 adds every field that sets S, plain signal names, the latest PQD quarter and the meaning of V. Its style checks flag series codes, a latest quarter called "next", firm-specific wording for market-wide signals, and a missing V meaning.

## 7. Export the dashboard

```bash
python3 ../docs/data/export_risk_output.py --week <Monday> ...
```

The export publishes approved narratives only, after re-running the checks: approve, or edit using the corrected text. They are labelled "AI-written, reviewed by analyst". Rows without a decision, rejected rows, and rows that fail the checks show "Analysis pending review". Template rows show their fixed text, without an AI label.

Check the export with `python3 ../docs/data/validate_output.py ../docs/data/risk_output.json` before publishing.

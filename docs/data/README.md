# Risk Horizon data hookup

The dashboard (`docs/index.html`) only displays data. It reads **one file**, which the risk model writes:

```
docs/data/risk_output.json
```

- The file is built from the scoring v1.3-indicator weekly outputs (`Capstone_Project/results/scoring/v1.3_indicator/`) by `python3 docs/data/export_risk_output.py`.
- To test any other file, use `?data=data/your_file.json`. Demo layout data lives outside `docs/`, in `frontend_demo/`, because everything under `docs/` is published.

To publish a new week:

1. Score it with `python -m validation.scoring_v1_3 score --week <Monday>` (from `Capstone_Project/`), then run `python3 docs/data/export_risk_output.py --week ...`.
2. Run `python3 docs/data/validate_output.py docs/data/risk_output.json`. It also checks the front layer: front text only when reviewed, word limits, fixed template text, and `front_so_now_what` / `front_chain_short` equal to the reviewed `card_playbook.csv` (`--playbook <file>` checks against another playbook, for local tests).
3. Commit and push to `main`. GitHub Pages updates in about a minute.

## File format

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-10-26T08:00:00-04:00",   // when the model ran (ISO 8601)
  "model_version": "v1.0",                        // optional, shown in the footer
  "sample": false,                                // true shows a "Sample data" badge

  "snapshots": [                                  // one per weekly run; any order
    {"id": "2026-10-26", "date": "2026-10-26", "label": "Week of Oct 26, 2026",
     "news_coverage": "manual_register_only"}     // or "headline_level_ai_screen" once the weekly news run covered the week
  ],

  "lines": {                                      // optional, per business line
    "ECS": {
      "summary": {"2026-10-26": "One-paragraph brief for the week"},  // or a plain string
      "summary_ai": false,                                             // true adds an AI-WRITTEN tag to the summary
      "coming":  [{"date": "2026-12-18", "title": "Triple witching"}],  // latest week: days from the viewer's today; older weeks: from that Friday ("as of"); past dates hidden
      "review":  [{"title": "...", "risk_family": "Strategic", "reason": "why not scored", "snapshot": "2026-10-26"}]
    }
  },

  "items": [ /* one record per risk card per snapshot (see below) */ ]
}
```

### One item = one card

Each item belongs to one snapshot. To show week-over-week change, write the same `id` again in the next snapshot. The page then compares the two scores and adds chips like "↑ from 9 (Medium)" or "New this week".

| Field | Required | Type | Notes |
|---|---|---|---|
| `id` | yes | string | Stable across weeks for the same risk, e.g. `ecs-volatility` |
| `snapshot` | yes | string | Must match a `snapshots[].id` |
| `business_line` | yes | string | One of: `FICC`, `ECS`, `RDS`, `WIS`, `ITP`, `Asset Services`, `DAS`, `DDA`, `Data Services`, `Consulting` |
| `title` | yes | string | Card headline |
| `shock` | yes | int 1–5, or `null` when `status` is `news_not_scanned`, `no_relevant_news` or `data_incomplete` | External score S |
| `vulnerability` | no | int 1–5 or `null` | Internal score V from PQD or a public proxy (`V_tier`). `null` shows "V pending" with no score. Never use 0. |
| `status` | no | string | `scored` (default); `no_relevant_news` (grey "No relevant news found (headline-level scan)" box, sorted last; only in weeks whose snapshot has `news_coverage` `headline_level_ai_screen`); `news_not_scanned` (grey "News not scanned" box, sorted last; only in weeks before the weekly news screen); or `data_incomplete` (grey "Data incomplete" box) |
| `V_tier` | no | string | `pqd` or `public_proxy`, shown next to V |
| `needs_human_signoff` | no | bool | `true` shows a "Pending review" badge |
| `analysis_status` | no | string | `pending_llm`: no narrative step for the week. `pending_review`: an AI draft exists but is not approved, so the text is null and the page shows "Analysis pending review". `template`: fixed non-AI text for cards without a scored shock. `ai_reviewed`: AI-drafted text approved or edited by an analyst |
| `shared_signal` | no | string[] | card_ids of other cards whose S comes from the same signal field (e.g. `sofr_effr_adjusted`); shows "Signal shared with …" |
| `card_id` | no | string | final16 card id; the validator checks each card/business-line pair against `card_lines.csv` |
| `risk_family` | yes | string | Credit, Liquidity, Market, Operational, Cyber, Regulatory, Strategic |
| `sub_line` | no | string | e.g. `NSCC`, `GSD`, `NSCC · DTC` |
| `region` | no | string | Default `US` |
| `confidence` | no | string | High / Medium / Low-Medium / Low |
| `updated_at` | no | ISO datetime | Used for "Newest first" sorting and the "updated" stamp |
| `summary_line` | no | string | One line under the card title |
| `what_happened` | no | string | |
| `transmission` | no | object | `{event, mechanism, dtcc_process}` |
| `so_what`, `so_now_what` | no | string, or `null` only when `analysis_status` is `pending_llm` (weeks before the narrative step: grey "Narrative analysis starts from the week of <first week with narratives>." box) or `pending_review` (grey "Analysis pending review" box) | From `Capstone_Project/data/narratives/review_narratives_<week>.csv`. Only approved or edited AI rows that pass `validation/narrative_checks.py` are published: so_what at most 2 sentences / 45 words, so_now_what at most 2 sentences / 40 words, numbers only from the card's input, no banned phrases. Template rows: "No scored shock this week." / "See the transmission chain for what would trigger a score." |
| `front_status` | no | string | Card front layer (what the GM reads first). `ai_reviewed`: reviewed AI front text below; `template`: unscored card, front shows the card name and one fixed line; `pending_review`: a front draft exists but is not approved (front shows the card name and "Summary pending analyst review"); `none`: no front step for the week |
| `front_headline` | no | string or `null` | At most 10 words: what happened plus its consequence for the DTCC process. Shown as the card title; the card name (`title`) then appears only in the detail view. `template`: the card name. `null` unless `ai_reviewed` or `template` |
| `front_what_happened` | no | string or `null` | One sentence, at most 20 words, numbers only from the card's input. `template`: "No market signal or relevant news this week." |
| `front_so_what`, `front_so_now_what` | no | string or `null` | So what: one plain-English sentence, at most 20 words, no percentiles, "V k of 5", series codes or jargon. So now what: one action copied from the card's reviewed playbook (`front_action_id`). Only for `ai_reviewed` |
| `front_chain_short` | no | string[3] or `null` | Three labels of at most 6 words (world event, mechanism, DTCC process) from a reviewed row of `Capstone_Project/data/narratives/card_playbook.csv`. Shown in the detail view only, above the analyst view, with the full chain text below |
| `front_sources_line` | no | string | Short source names built from the record, e.g. "FRED (VIX, SOFR, EFFR) · DTCC quarterly disclosures · MarketWatch" (non-AI). A card with related news labelled `membership/onboarding` also names "DTCC member notices" |
| `front_ai_fields`, `front_review_label` | no | string[], string | On `ai_reviewed` fronts: the AI-drafted front fields and "AI-drafted · analyst-reviewed" (shown as a small footer). `front_reviewer`, `front_decision`, `front_prompt_version`, `front_model` and `playbook_reviewer` record the provenance |
| `time_phased` | no | object | `{now, next, later}` |
| `shock_method` | no | string | `Market indicator` or `Event rubric` |
| `shock_basis`, `vulnerability_basis` | no | string | How each score was built |
| `why_this_line` | no | string | |
| `key_unknowns` | no | string[] | |
| `where_we_stand` | no | string | |
| `shareable_line` | no | string | Has a "Copy line" button |
| `sources` | no | `[{name, url}]` | A `url` of `""` shows plain text |
| `ai_generated_fields` | no | string[] | Field names that get an AI tag, e.g. `summary_line`, `so_what`, `so_now_what`, `shareable_line`. The tag reads `narrative_review_label` when set, otherwise "AI-WRITTEN" |
| `narrative_review_label` | no | string | "AI-written, reviewed by analyst" on `ai_reviewed` items. `narrative_reviewer`, `narrative_decision` (`approve` / `edit`), `narrative_prompt_version` and `narrative_model` record the provenance |
| `review_status` | no | string | e.g. `AI-drafted, analyst-checked` |
| `related_news` | no | `[{title, outlet, url, event_type, proposed_event_id, label?}]` | Headline-level news for this card and week (Amendments D, E and G: market moves on indicator cards, duplicates of recorded events, and new-member notices with `label` "membership/onboarding"). Shown as "Related news · headline-level news, not scored", with the label as a chip; never part of the score |
| `related_news_display` | no | `[{index, top, published, keyword, priority_outlet, excluded, label, reason}]` | Display order of `related_news` in the detail view (display only; `related_news` itself is unchanged). The first entries with `top: true` (at most 5) are shown; every item is listed under "Show all N". Ranking, without a model: titles with one of the card's search keywords (`Capstone_Project/validation/news_queries.csv`) first, then priority outlets, then newest (publication time from the week's committed collection files). Political and crypto headlines never enter the top; gold, oil, sterling or currency headlines only with a card keyword. Lists: `Capstone_Project/validation/related_news_display.json`; code: `Capstone_Project/validation/related_news_rank.py`. Labelled items (e.g. `membership/onboarding`) are summarised in one line at the top instead |
| `ai_unreviewed_events` | no | string[] | Active register events on this card entered by the news classifier without a human decision (`llm-auto`/`unreviewed`) |
| `ai_review_label` | no | string or `null` | `AI-classified, not reviewed` when such an event affects the card, or when S comes from one (`event_review_label`); shown as a chip on the card and in the detail view |

The page calculates these itself, so the model should not send them:

- severity = `shock × vulnerability`
- level: High 15–25, Medium 8–14, Low 1–7
- change versus the previous week

## Card front and detail view

- **Card front** (the list), in order: score box with level and change arrow (▲/▼ from the previous score, or NEW); `front_headline` as the title (the card name when there is no reviewed front); chips for risk family, business line and confidence (plus "Pending review" and "AI-classified, not reviewed" when they apply); a "What happened" line; two boxes, "So what" and "So now what"; a sources line; the small footer "AI-drafted · analyst-reviewed" when the front text is reviewed AI text. Unscored cards show the card name and only the line "No market signal or relevant news this week."
- **Unscored cards on the list** (`no_relevant_news`, `news_not_scanned`) are grouped after the scored cards in one collapsed block, "N other cards: no market signal or relevant news this week" (or "news not scanned" in earlier weeks). Expanded, each is one row: card name, business-line chip, confidence chip, V and its tier, and a Details link. With the "No relevant news" or "Not scanned" filter they are shown as full cards. The summary counts are unchanged.
- **Detail view**: the same title, chips and "What happened" line; then the card name and the three `front_chain_short` boxes (the last one highlighted), followed by the full transmission-chain text; then the front "So what" / "So now what" and sources line; then the **Analyst view**: Shock × Vulnerability with the V tier, the signal with its percentile and daily values, the shared-signal note, the detailed narrative (`so_what` / `so_now_what`) with its AI label, how the score was built, confidence, related news, the full sources list and the structured record.
- The export publishes front text only from reviewed rows of `review_front_<week>.csv` (decision `approve` or `edit` with a reviewer), only with an action from a reviewed `card_playbook.csv` row of that card, and only when `validation/card_front_checks.py` passes again against the stored input. Otherwise the front falls back to the card name and the detailed narrative stays in the analyst view.

## What the page controls do

- **Snapshot:** which weekly run to view.
- **Time:**
  - "Selected week" shows only that run.
  - "Last 30 days", "Last 90 days" and "All time" show the latest version of each item within that window, counting back from the selected week. Older items get a "Week of …" chip.
- **Sort:** score high→low (default), score low→high, newest first, oldest first. "Newest" uses `updated_at`. Items with V pending sort last when sorting by score. Unscored cards ("News not scanned", "Data incomplete") always sort last.
- **Filters:** severity, risk family and region.
- **Tabs:** all 10 business lines are always shown, each with its item count.
- **Related news:** in the detail view's analyst view: one summary line per label (e.g. "7 new FICC members this week"), the top 5 items by `related_news_display`, and every item under "Show all N". It is not shown on the card front.

## Running locally

Browsers block `fetch()` when the page is opened from disk (`file://`). Serve the folder instead:

```
cd docs && python3 -m http.server 8000
# open http://localhost:8000/
```

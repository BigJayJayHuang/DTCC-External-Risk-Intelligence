# Risk Horizon data hookup

The dashboard (`docs/index.html`) only displays data. It reads **one file**, which the risk model writes:

```
docs/data/risk_output.json
```

- This file is empty for now, so the page shows "No model output yet".
- To preview the layout with fake data, open the page with `?sample=1`. That loads `sample_risk_output.json`.
- To test any other file, use `?data=data/your_file.json`.

When the model is ready:

1. Write `risk_output.json` in the format below.
2. Run `python3 docs/data/validate_output.py docs/data/risk_output.json`.
3. Commit and push. GitHub Pages updates in about a minute.

## File format

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-10-26T08:00:00-04:00",   // when the model ran (ISO 8601)
  "model_version": "v1.0",                        // optional, shown in the footer
  "sample": false,                                // true shows a "Sample data" badge

  "snapshots": [                                  // one per weekly run; any order
    {"id": "2026-10-26", "date": "2026-10-26", "label": "Week of Oct 26, 2026"}
  ],

  "lines": {                                      // optional, per business line
    "ECS": {
      "summary": {"2026-10-26": "One-paragraph brief for the week"},  // or a plain string
      "coming":  [{"date": "2026-12-18", "title": "Triple witching"}],
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
| `shock` | yes | int 1–5 | External score S |
| `vulnerability` | no | int 1–5 or `null` | Internal score V from PQD. `null` shows "V pending" with no score. Never use 0. |
| `risk_family` | yes | string | Credit, Liquidity, Market, Operational, Cyber, Regulatory, Strategic |
| `sub_line` | no | string | e.g. `NSCC`, `GSD`, `NSCC · DTC` |
| `region` | no | string | Default `US` |
| `confidence` | no | string | High / Medium / Low-Medium / Low |
| `updated_at` | no | ISO datetime | Used for "Newest first" sorting and the "updated" stamp |
| `summary_line` | no | string | One line under the card title |
| `what_happened` | no | string | |
| `transmission` | no | object | `{event, mechanism, dtcc_process}` |
| `so_what`, `so_now_what` | no | string | |
| `time_phased` | no | object | `{now, next, later}` |
| `shock_method` | no | string | `Market indicator` or `Event rubric` |
| `shock_basis`, `vulnerability_basis` | no | string | How each score was built |
| `why_this_line` | no | string | |
| `key_unknowns` | no | string[] | |
| `where_we_stand` | no | string | |
| `shareable_line` | no | string | Has a "Copy line" button |
| `sources` | no | `[{name, url}]` | A `url` of `""` shows plain text |
| `ai_generated_fields` | no | string[] | Field names that get an "AI-WRITTEN" tag, e.g. `summary_line`, `so_what`, `so_now_what`, `shareable_line` |
| `review_status` | no | string | e.g. `AI-drafted, analyst-checked` |

The page calculates these itself, so the model should not send them:

- severity = `shock × vulnerability`
- level: High 15–25, Medium 8–14, Low 1–7
- change versus the previous week

## What the page controls do

- **Snapshot:** which weekly run to view.
- **Time:**
  - "Selected week" shows only that run.
  - "Last 30 days", "Last 90 days" and "All time" show the latest version of each item within that window, counting back from the selected week. Older items get a "Week of …" chip.
- **Sort:** score high→low (default), score low→high, newest first, oldest first. "Newest" uses `updated_at`. Items with V pending sort last when sorting by score.
- **Filters:** severity, risk family and region.
- **Tabs:** all 10 business lines are always shown, each with its item count.

## Running locally

Browsers block `fetch()` when the page is opened from disk (`file://`). Serve the folder instead:

```
cd docs && python3 -m http.server 8000
# open http://localhost:8000/?sample=1
```

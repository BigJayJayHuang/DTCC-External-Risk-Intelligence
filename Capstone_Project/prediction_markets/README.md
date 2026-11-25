# Prediction markets (Kalshi) → Risk Horizon

Read-only connection to Kalshi's public market data. It turns prediction-market prices into weekly inputs for chains the model already has, plus two proposed new chains. Standard library only, no API key, no AI call. Nothing outside this folder is changed.

Status: v0.1, built Nov 25, 2026. Tested offline (16 tests). The live API has not been called yet from our machines: both the cloud sandbox and the Cowork VM block kalshi.com, so the first live run has to be from a normal terminal.

## What it adds

| Use | Series (config) | Feeds | What the model gets |
|---|---|---|---|
| Market signal | Fed decision (`KXFEDDECISION`), CPI (`KXCPI`, to confirm) | FICC-GSD-01, FICC-MBSD-01, RDS-02, AS-02 | Weekly **repricing** in percentage points: how far the odds for the next Fed decision moved. Must pass Test 1 before it can set a shock. |
| Event rubric | Government shutdown (`KXGOVSHUT`, `KXSHUTDOWNBY`), debt ceiling (ticker to find) | XE-SHUTDOWN-01, FICC-DEBT-01 (new) | Probability → rubric **certainty** (≥70% = 2, 30–70% = 1, <30% = 0); resolution date → **timing**. Scored with `validation/event_scoring.py` (rubric v1.2). Always flagged for human review. |
| Context only | Recession (ticker to find) | XE-MEMBER, RDS-03A | A line on the card, not scored. |

Thin markets (open interest under 1,000 and 24-hour volume under 100 contracts) are skipped. Thresholds are in `config/series.json`.

## Files

| File | What it does |
|---|---|
| `kalshi_client.py` | Read-only client: markets, events, series, daily candles (falls back to the historical endpoint for old settled markets), retries on 429 |
| `collect.py` | `discover` series tickers, `snapshot` current prices, `history` daily prices to CSV |
| `signals.py` | Weekly signals → `output/pm_signals_<week>.json` with a `by_chain` index and a one-line `card_line` for the dashboard |
| `test1.py` | Standard Test 1 on daily repricing against `config/windows.json` |
| `config/series.json` | Which series feed which chains, thresholds, ticker status |
| `config/windows.json` | Pre-set Test 1 windows (set before testing) |
| `fixtures/` | **Simulated** API responses for offline tests and demos (not real prices) |
| `market_view.py`, `attach_market_views.py`, `config/topics.json` | The market box: match a tagged article to a market, agreement and factor |
| `HYPOTHESES_prediction_market_chains.md` | Hypothesis cards for FICC-DEBT-01 and XE-SHUTDOWN-01 |

## Run it

```bash
cd Capstone_Project/prediction_markets
python3 -m unittest test_prediction_markets -v          # offline tests
python3 signals.py --week 2026-11-23 --offline           # demo with simulated fixtures

# live (normal terminal, not the Cowork VM)
python3 collect.py discover --search debt ceiling        # find tickers, then edit config/series.json
python3 signals.py --week 2026-11-23                     # this week's signals
python3 collect.py history --series KXFEDDECISION --days 900
python3 test1.py --series KXFEDDECISION                  # Test 1
```

## Hooking into the weekly run (next step, not done here)

`output/pm_signals_<week>.json` is the only interface. To use it, the export step would:
1. For market-signal series, add the repricing value to the card's `market_chains` list (same percentile method as other signals) once Test 1 passes.
2. For event-rubric series, add the returned `rubric` block as an event for the card (it is already scored with rubric v1.2 and marked `needs_review`).
3. Show `card_line` in the card's analyst view, e.g. "Kalshi: 68% chance · Government shutdown on December 12, 2026 (33% 7 days ago)".

Left to the team so this folder doesn't clash with `validation/` or `docs/data/export_risk_output.py`.

## Market box on the card (v0.3, point in time)

When a news article is about a future event, the card shows **What the market expects**, next to So what / So now what: up to 3 markets, each with YES % on the left, NO % on the right and a bar in the middle, **as of the end of the card's week** (Sunday close, US Eastern). Past weeks never use today's prices.

1. **Tag (AI, prompt v1.7):** `forward_topic` (fed_cut, government_shutdown, debt_limit_breach, recession, **other**, none), `forward_lean` (yes / no / neutral), `forward_quote` (checked verbatim) and `forward_subject` (for `other`: a short search phrase such as "Jensen Huang return as Nvidia CEO"; at least half its words must be in the article).
2. **Snapshot (code):** `kalshi_candidates.py` builds that week's point-in-time list, `data/kalshi/<Monday>/kalshi_candidates.csv`, with the articles' subjects added to the search.
3. **Match (code, never the AI):** vetted topics use the series in `config/topics.json` and the event resolving closest to the article's date; `other` searches the week's markets by the subject words and keeps up to 3 events (e.g. back by end of month, by end of year). Writes `data/market_views/market_views_<Monday>.json`.
4. **Factor:** vetted topics with a yes/no lean propose factor = 0.75 + 0.5 × (market probability of the article's side); subject matches are **box only** (factor 1.0). Combined with hype, the total stays within 0.75–1.25. The export applies it only with `--apply-market-factor`, after review, and only to event-scored cards.

The weekly news run (`python -m validation.weekly_news_run`) does steps 1–3 automatically (step 7 of the runbook). `run_once.py` back-fills past weeks from their saved news.

## Run it once (one command, for a teammate)

From the repo root, in a normal terminal (Kalshi is blocked on some school/VPN/sandbox networks), after `aws sso login --profile devx-bedrock`:

```bash
python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-02 --offline   # 10-second dry run, simulated data, no network
python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-09              # back-fill a past week: v1.7 on its saved news -> point-in-time Kalshi -> export
```

It checks Kalshi, runs the classifier with prompt v1.7 into `data/market_views/classifier_runs/` (the team's `data/events` files are not touched), writes `data/market_views/market_views_<week>.json`, and exports to `docs/data/risk_output_kalshi.json` (the live `risk_output.json` is not touched). Open `docs/index.html?data=data/risk_output_kalshi.json` to see the boxes next to So what / So now what. Use `--candidates <csv>` to skip the classifier, `--max-articles` / `--budget` to cap Bedrock cost, and `--apply-market-factor` only after an analyst has reviewed the boxes. The `--week` must be a snapshot week the export knows.

## Weekly candidate list (kalshi_candidates.py, point in time)

A scan of the Kalshi markets that were live at the end of each dashboard week, for the team to map to risk families and cards. One row per binary market, one file per week.

```bash
python3 Capstone_Project/prediction_markets/kalshi_candidates.py --week 2026-11-02 --week 2026-11-09 --week 2026-11-16 --offline
python3 Capstone_Project/prediction_markets/kalshi_candidates.py --week 2026-11-02 --week 2026-11-09 --week 2026-11-16
```

Writes `Capstone_Project/data/kalshi/<Monday>/kalshi_candidates.csv`, `raw/` and `run_log.json`.

- **Snapshot:** the end of that week's Sunday, US Eastern (week of Nov 2 → as of Nov 8). A market is included only if it was live then (`open_time <= as_of < close_time`); markets that have since closed or settled are fetched from the closed/settled and historical endpoints.
- **Prices:** `prob_as_of` = daily candle close at the snapshot, `prob_7d_before` = close 7 days earlier, `change_7d_pts` from the two; volume and open interest from the candles. For the current, unfinished week, live quotes are used (`prob_source` says which). Bid/ask columns are blank for past weeks (today's quotes would be look-ahead).
- **Outcome columns** `result` (yes / no / open / pending), `settled_at`, `outcome_note`: for the "expected vs happened" slide only, never shown on the main page.
- **Which markets** (`config/candidates.json`): Economics, Financials, Companies, Politics (government keywords only), Science and Technology, Climate and Weather, Crypto (regulation only, never price levels); combo/parlay markets dropped; whole-word keywords incl. Nvidia, Nasdaq, S&P 500, tech, semiconductor, AI stocks, market cap, volatility, VIX. `--subjects-from <candidates.csv>` adds the week's news subjects (any category except Sports/Entertainment/Culture/Mentions/Social). Check `categories_seen` in the run log after the first live run and fix spellings in the config.
- **Mapping columns** are left blank and kept on re-run. **All or nothing:** a failed call leaves the previous file and logs to `data/kalshi/_errors/`.

Tests: `python3 -m unittest test_kalshi_candidates test_market_view -v`.

## Before relying on it

- Confirm `KXCPI` and find the debt-ceiling and recession tickers with `discover` (or search the candidate list).
- Check Kalshi's terms before any commercial use of the data; for the capstone it is read-only research use.
- The certainty thresholds and the 20 pp "jump" flag are proposals: freeze them with the team before testing.
- Kalshi's KX-prefixed series may not cover the 2024 windows; if not, Test 1 reports INCONCLUSIVE.

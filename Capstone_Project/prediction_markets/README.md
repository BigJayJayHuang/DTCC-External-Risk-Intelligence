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

## Market box on the card (v0.2)

When a news article is about a future event a market prices, the card shows **What the market expects**: YES % on the left, NO % on the right, a bar in the middle, the change over a week, and whether the market agrees with the article.

1. **Tag (AI):** news classifier prompt **v1.7** (`validation/llm_event_classifier_prompt_v1.7.md`, v1.6 unchanged) adds `forward_topic` (fed_cut, government_shutdown, debt_limit_breach, recession, none), `forward_lean` (yes / no / neutral) and `forward_quote` (checked verbatim; a missing quote turns the lean neutral). Run with `--prompt-version v1.7`.
2. **Match (code):** `attach_market_views.py --week <Monday> --candidates <run>/candidates.csv` finds the Kalshi market from `config/topics.json` (the AI never picks tickers), checks the resolution date is close to the article's date, skips thin markets, and writes `../data/market_views/market_views_<week>.json`.
3. **Factor:** article leans yes/no → factor = 0.75 + 0.5 × (market probability of the article's side), so 50% = 1.0, 80% agreement = 1.15, 20% = 0.85. Neutral articles get the box with factor 1.0. Combined with the social-media hype factor, the total stays within 0.75–1.25.
4. **Show (export + page):** `docs/data/export_risk_output.py` adds `market_view` to the card. The factor only changes the score with `--apply-market-factor` (after analyst review), and only for event-scored cards; it adds `shock_adjusted` and never overwrites `shock`. Without a market-views file the export output is byte-for-byte the same as before.

Tests: `python3 -m unittest test_market_view` (here) and `python3 -m unittest validation.test_llm_classifier_v17 validation.test_market_view_export` (from Capstone_Project). Before switching the weekly run to v1.7, re-run the golden eval to confirm the new fields don't change the other labels.

## Run it once (one command, for a teammate)

From the repo root, in a normal terminal (Kalshi is blocked on some school/VPN/sandbox networks), after `aws sso login --profile devx-bedrock`:

```bash
python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-02 --offline   # 10-second dry run, simulated data, no network
python3 Capstone_Project/prediction_markets/run_once.py --week 2026-11-23              # real run: classifier v1.7 -> Kalshi -> export
```

It checks Kalshi, runs the classifier with prompt v1.7 into `data/market_views/classifier_runs/` (the team's `data/events` files are not touched), writes `data/market_views/market_views_<week>.json`, and exports to `docs/data/risk_output_kalshi.json` (the live `risk_output.json` is not touched). Open `docs/index.html?data=data/risk_output_kalshi.json` to see the boxes next to So what / So now what. Use `--candidates <csv>` to skip the classifier, `--max-articles` / `--budget` to cap Bedrock cost, and `--apply-market-factor` only after an analyst has reviewed the boxes. The `--week` must be a snapshot week the export knows.

## Weekly candidate list (kalshi_candidates.py)

A broad scan of open Kalshi markets for the team to map to risk families and cards. One row per binary market.

```bash
python3 Capstone_Project/prediction_markets/kalshi_candidates.py --snapshot-date 2026-11-30 --offline   # simulated dry run
python3 Capstone_Project/prediction_markets/kalshi_candidates.py --snapshot-date 2026-11-30             # real run (normal terminal)
```

Writes `Capstone_Project/data/kalshi/<snapshot_date>/kalshi_candidates.csv`, `raw/` (events and candlesticks JSON) and `run_log.json` (API calls, categories seen, filter counts, price source).

- **Which markets** (`config/candidates.json`): open, closing within 18 months; Economics, Financials, Politics (government-operation keywords only), Science and Technology, Climate and Weather, and Crypto only for stablecoin / market-structure / SEC / CFTC markets (never price levels). Combo/parlay markets (`KXMVE…`) dropped. Keywords match whole words, so "rate" doesn't match "corporate" and "SEC" doesn't match "second". After the first live run, check `categories_seen` in the run log and fix any category spelling in the config.
- **Prices** are 0–1. `prob_now` = mid of the yes bid/ask (else last price) when run on or before the snapshot date. When run later, it is the daily candle close on the snapshot date instead; `prob_source` says which. `prob_7d_ago` = daily close 7 days earlier (blank if the market is newer). `volume_7d` = sum of the last 7 daily candles (Kalshi has no 7-day field). `liquidity_ok` = Y if open interest ≥ 1,000 or 7-day volume ≥ 1,000 (set in the config).
- **Mapping columns** are left blank. Re-running the same week keeps anything already typed into them (matched by `market_ticker`).
- **All or nothing:** the files are written to a temp folder and swapped in only if every call succeeded. If any call fails, the previous snapshot stays and the error is saved in `data/kalshi/_errors/`.
- `kalshi_url` points to the series page (`kalshi.com/markets/<series>`); Kalshi's event page slugs are not in the API.

Tests: `python3 -m unittest test_kalshi_candidates -v`.

## Before relying on it

- Confirm `KXCPI` and find the debt-ceiling and recession tickers with `discover` (or search the candidate list).
- Check Kalshi's terms before any commercial use of the data; for the capstone it is read-only research use.
- The certainty thresholds and the 20 pp "jump" flag are proposals: freeze them with the team before testing.
- Kalshi's KX-prefixed series may not cover the 2024 windows; if not, Test 1 reports INCONCLUSIVE.

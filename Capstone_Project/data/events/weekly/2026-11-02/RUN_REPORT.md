# Weekly classifier run, week of 2026-11-02 (prompt v1.4, flat schema, cache on)

Run `v14_flat`, `classifier-prompt-v1.4:83ad6672fcbc`, response schema `flat` (tool strict = False), cap USD 1.50. The 83 items published 2026-11-01 to 2026-11-08 are those of `classifier_inputs/feeds_2026-11-08`: 81 Google headline-only items, 1 SEC summary and 1 MarketWatch summary. The event register and sign-offs are unchanged.

## Result

| Measure | Value |
|---|---|
| Relevant | 26 |
| Irrelevant | 54 |
| Hard failures | 3, sent to `failed.jsonl` without retry: twice the model omitted `same_as_event_id`; once the answer stopped at the 1,200-token output limit |
| Tokens | 126,377 input, 43,121 output |
| Cache | 3,685 write, 302,170 read |
| Cost | USD 1.2435 (USD 2.1379 without caching) |

## Relevant items and proposed events per card

| Card | Relevant items | Proposed events |
|---|---|---|
| ECS-NSCC-03 | 1 | 1 |
| ECS-NSCC-LIQ | 17 | 8 |
| ECS-SET-01 | 2 | 2 |
| FICC-GSD-01 | 2 | 2 |
| FICC-GSD-03 | 1 | 1 |
| FICC-GSD-11 | 2 | 2 |
| XE-CYBER | 3 | 3 |
| XE-MEMBER | 2 | 2 |

17 proposed events (`data/events/review/review_2026-11-02.csv`): 13 required, 4 auto. The grouping rule is described in `validation/review_sheet.py`.

## Ten random irrelevant items (seed 20261109)

| Headline (outlet) | Card hints | Model reason |
|---|---|---|
| Bank of France Flags 2026 Growth Downgrade (Briefs Finance) | XE-MEMBER | Headline describes a French central bank macroeconomic growth forecast downgrade for France/Europe. No US market event, no DTCC participant stress, no link to US clearing or settlement processes. Does not match any catalog card's Step 1. |
| Taiwan Stock Market Selloff: Woman Buys 390 Lots of 00631L in Two Hours, Only Realizes "Too Impulsive" When Facing NT$14.26 Million Settlement (BigGo Finance) | ECS-NSCC-LIQ | Non-US market (Taiwan Stock Exchange); the event involves a retail investor's personal trading decision in a Taiwanese ETF with no stated link to US markets or DTCC participants. No catalog card applies. |
| How a third-party cyberattack exposed the vulnerabilities of French banking (BLiTZ - Fears None But God) | XE-CYBER | Headline describes a cyberattack on French banking with no stated link to US markets, DTCC participants, or US financial infrastructure. Non-US market event with no connection to DTCC processes. |
| Here’s why Deutsche Bank downgraded Clariant stock By Investing.com (Investing.com India) | XE-MEMBER | Clariant is a Swiss specialty chemicals company, not a financial institution or DTCC member. A Deutsche Bank analyst downgrade of a non-financial firm's stock does not match any card's Step 1 event type. |
| Health intel-sharing group warns industry in wake of cyberattack on French blood bank (NPR) | XE-CYBER | Cyberattack on a French blood bank (healthcare/non-financial sector, non-US). No link to US financial markets, DTCC participants, or any catalog card's Step 1 event. |
| Federal Bank Ltd Downgraded to Hold by MarketsMOJO Amid Mixed Technical and Valuation Signals (MarketsMojo) | XE-MEMBER | Federal Bank Ltd is an Indian commercial bank, not a US DTCC member or major participant. A downgrade by a domestic Indian analytics firm (MarketsMOJO) based on technical/valuation signals has no stated link to US markets or DTCC processes. Does not match any catalog card. |
| Gopax Trading Halt: What Is Behind This Sudden Korean Exchange Move? (Coin Gabbar) | XE-DISRUPT | Gopax is a South Korean cryptocurrency exchange. A trading halt there has no stated link to US markets or DTCC participants; non-US crypto venue is outside the catalog scope. |
| French Bank Loses 100 Million Euros in Cyberattack (BankInfoSecurity) | XE-CYBER | Non-US bank (French) with no stated link to US markets or DTCC participants; XE-CYBER requires a large participant or vendor connected to DTCC processes, which is not established by this headline alone. |
| Medicare prescription drug costs will jump 50% in 2027. Doing nothing could cost you. (MarketWatch) | FICC-MBSD-01 | Article is about Medicare prescription drug costs and open enrollment — a healthcare/consumer topic with no connection to financial markets, DTCC processes, or any catalog card. |
| South Korea Seeks to Shorten Stock Settlement Cycle to T+1 by 2028 (bloomingbit) | ECS-SET-01 | Non-US market event (South Korea) with no stated link to US markets or DTCC participants; ECS-SET-01 covers US settlement cycle changes only. |

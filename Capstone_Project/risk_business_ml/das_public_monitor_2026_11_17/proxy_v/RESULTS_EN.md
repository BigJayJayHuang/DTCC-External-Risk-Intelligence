# DAS-05 conversion-window proxy V: research results

As of: 2026-11-17T12:24:21-05:00

Implemented hours until the next nominal conversion-order submission window. This public-rule-derived structural proxy is not observed latency, capacity, or an internal protective buffer.

Current baseline wait: **0.0000 hours**; candidate bin: **1/5**. Zero means only that the nominal window is open, not that the service is healthy or risk-free.

Reconstructed 470 hourly samples and 20 fixed-08:00 ET daily samples from 2026-10-29. Maximum sampled wait: 57 hours, reflecting the extra elapsed hour across the autumn2026 DST change.

## Calculation and proposed bins

Find the next nominal opening in America/New_York, then subtract UTC instants. The implementation includes02:00 and excludes18:00; exclusion of the closing endpoint is a conservative research assumption.

| Waiting hours | Candidate bin |
|---|---|
| 0 | 1 |
| (0, 8] | 2 |
| (8, 24] | 3 |
| (24, 48] | 4 |
| >48 | 5 |

Fixed bins are proposed and uncalibrated, not historical percentiles or loss probabilities.

## Hypothetical scenarios, not observed events

Each example assumes S=3 and an event that requires conversion between traditional and tokenized form. No example claims an actual DTCC incident or enters accepted-event or observed-data records.

| Scenario | Time ET | Baseline wait (h) | Candidate V | Illustrative S×V index |
|---|---|---:|---:|---:|
| EXAMPLE-OPEN | 2026-11-13T17:00:00-05:00 | 0 | 1 | 3 |
| EXAMPLE-FRIDAY-CLOSED | 2026-11-13T19:00:00-05:00 | 55 | 5 | 15 |
| EXAMPLE-SUNDAY | 2026-11-15T08:00:00-05:00 | 18 | 3 | 9 |

## Interpretation limits

- The API mentions holiday rejection, but no applicable dated conversion calendar was obtained. All results use the nominal weekly baseline; calendar-confirmed wait stays null. No NYSE, Fed, or DTC settlement holiday substitution is made.
- Already-tokenized transfers operate separately24/7. This proxy only applies to pathways requiring conversion; news applicability is not automatically inferred.
- Service health, participant/security eligibility, queueing, and completion times are unknown. Zero submission wait promises no immediate processing, trade, settlement, or completion.
- Reconstructed using current evidence, not verified historical vintages. No values before2026-10-29 or invented2020Q4–2026Q2 operating history.
- Quarterly output is a partial-quarter sample description, not prior-quarter internalV. InternalV, accepted proxyV, and official risk scores stay null; final16 and production scoring are unchanged.
- Assumed S and S×V examples are illustrative ordinal priority indices, excluded from observed database records. They are not probabilities, losses, causal effects, or empirical validation.

Validation requires authorized order/event outcomes and the actual service calendar, testing whether longer access waits correspond to longer delays or queues while accounting for outages, load, and event type.

## Sources

- [DTCC DAS-001 notice](https://files.dtcc.com/download/assets/DAS-001/8a31d732d2d311f1a30ef632b7f70f6d)
- [Official API reference](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content)

Source hashes and policy provenance: `results/source_evidence.json`.
Data: `results/hourly_proxy.csv`, `results/daily_0800_et_proxy.csv`, `results/quarterly_descriptive_summary.csv`.
Hypothetical examples are separate: `results/hypothetical_scenarios.csv`.

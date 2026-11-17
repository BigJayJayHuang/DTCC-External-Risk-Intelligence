# DAS: minimum real data required for calibration

Checked2026-11-17. Priority: DAS-05; other cards require separate protective-buffer evidence.

Purpose: test whether conversion-submission access waits relate to actual delays, rejections or queues, and obtain measured internal buffers. Reconstructed schedule samples are not operating records.

## Existing exports to request through the DTCC project contact

Request anonymized records since launch through the latest available date. Keep earlier pilots and controlled-production tests separately identified by environment. A participant export supports analysis of that participant; it does not establish service-wide performance.

| Priority | Existing record/export | Minimum fields | Purpose |
|---|---|---|---|
| P0 | Official calendar applicable to DTS conversion submission | Effective range, dates, opening/closing times, timezone, holidays/exceptions, publication time and version | Calculate applicable access waits without using later information |
| P0 | Request/gateway history, including rejected attempts | Pseudonymous request and intent/retry-group IDs, first intended/attempted submission time, attempt times, acceptance time, response/error codes, linked order ID, direction and network | Capture out-of-window demand that never creates an order |
| P0 | Complete order lifecycle export | Pseudonymous order ID, receipt/creation, processing-start and explicitly confirmed completion/failure times, status history, direction, network, quantity, outcome/reason | Separate access, queue and execution delay; retain incomplete orders |
| P0 | Concurrent load and service interruptions | Timestamp, pending count, oldest-order age, arrivals/completions with interval, incident/maintenance start/recovery, affected function | Distinguish calendar effects, workload and service failures |
| P0 | Capacity-test summary and comparable peak demand | Test date/environment, tested primary/backup orders per hour, constraints, peak arrivals on the same time scale | Capacity buffer = tested processing capacity/comparable peak demand; completions are not maximum capacity |
| P1 | Business-reviewed event/outcome register | Event ID, occurrence/knowledge times, applicable workflow, independently supported shock and scoring version, whether conversion was necessary, outcome and observation window | Test S×V against actual business outcomes; hypothetical S=3 is not a label |

Prefer an existing CSV, operating summary, test extract or shareable regulatory-report extract. No customer names, wallet addresses, account numbers, access credentials or request bodies are required. If order-level records cannot be shared, hourly aggregates by network/direction can support a limited first pass; document lost timing and linkage detail.

## Additional buffers for the remaining cards

| Card | Actual measurements needed |
|---|---|
| DAS-01 | Tested recovery/data loss, backup throughput, comparable peak demand and drill date |
| DAS-02 | Reconciliation backlog/age, ledger differences at a common as-of time, and verified resolution capacity |
| DAS-03 | Verified control-protected asset value, total asset value, control definition and attestation date |
| DAS-04 | Contingency de-tokenization capacity within a defined response horizon, affected positions in matching units and formal regulatory commencement notice |

## Verified access routes and limits

- [Conversion Orders documentation](https://dtcclearning.com/helpfiles/dda/tokenization_service/Content/Topics/tokenization_srvc/conversion_orders.htm): participant account CSV export; latest status-update time is not necessarily completion time.
- [Account Screen documentation](https://dtcclearning.com/helpfiles/dda/tokenization_service/Content/Topics/tokenization_srvc/accounts_oct_rev.htm): Balance, Activity and Wallets exports; not service-wide capacity or verified security coverage.
- [Public API reference](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content): operating endpoints require participant authorization. DevX AWS access does not grant DTS data access.
- [SEC source](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf): describes staff reporting on activity, holdings, wallets and unavailability. It establishes neither public release nor complete capacity/lifecycle reporting.

This retrieval work does not contact third parties, request keys or call restricted business APIs. DTCC should determine what is shareable through the existing project process. Received records still need quality checks; reliable calibration cannot be promised before inspecting them.

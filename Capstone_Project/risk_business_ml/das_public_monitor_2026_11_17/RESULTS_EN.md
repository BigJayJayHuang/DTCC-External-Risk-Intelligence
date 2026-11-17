# DAS public-evidence monitor: observed results

As of / 核验日：2026-11-17 · 2026-11-09–2026-11-17

Five research chains are narrowed to two executable public monitors and an authorized-order data adapter. Outputs are applicability reviews, future changes, evidence and a reporting calendar. Internal V and S×V scores remain unavailable.

## Findings

- [GHSA-hhgq-3gvc-4jhp](https://github.com/besu-eth/besu/security/advisories/GHSA-hhgq-3gvc-4jhp): Published 2026-11-10; maintainer severity medium; affected <= 26.10.1; patched 26.10.2. Confirm DTS version and configuration. No DAS incident has been established by this evidence.
- [GHSA-6pcq-hcgg-5q76](https://github.com/besu-eth/besu/security/advisories/GHSA-6pcq-hcgg-5q76): Published 2026-11-10; maintainer severity medium; affected <= 26.10.1; patched 26.10.2. Confirm DTS version and configuration. No DAS incident has been established by this evidence.
- [Solana](https://www.dtcc.com/press-releases/2026/dtcc-tokenization-service-to-connect-with-solana): Integration is planned for H2 2027. This belongs in a future-change watchlist, not current production outage exposure.

## Scope decisions

| ID | Subject | Treatment | Minimum missing input |
|---|---|---|---|
| DAS-01 | Software and infrastructure | ACTIVE_PUBLIC_MONITOR | Actual version, consensus configuration, patch and failover evidence |
| DAS-02 | Records and reconciliation | DEFER_INTERNAL_MEASUREMENT | Reconciliation breaks, backlog, resolution capacity and timestamps |
| DAS-03 | Wallet and security controls | DEFER_INTERNAL_MEASUREMENT | Registered-wallet inventory, key-control attestations and screening logs |
| DAS-04 | Regulation, eligibility and scope | ACTIVE_PUBLIC_MONITOR | Formal launch notice, contingency capacity and affected positions |
| DAS-05 | Conversion and corporate actions | AUTHORIZED_DATA_ADAPTER_READY | Actual order and completion logs; capacity benchmarks and corporate-action outcomes |

## Computable calendar

- 2026Q4 report to SEC staff: **2027-01-15**, 59 calendar days from the as-of date. Submission is not publicly observed; this does not imply non-submission.
- [SEC source / 监管文件](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf) — The exact relief expiry remains null until the formal Preliminary Base Version launch notice is established.

## Removed from this implementation

- No prelaunch quarterly DAS simulation and no fabricated internal V.
- No crypto prices, Canton Coin volume, generic CVE counts or HTTP reachability substituted for DAS internal vulnerability.
- No screening of unknown Registered Wallets or inference of controls from collaborator names.
- No machine-learning regression without operating outcomes and no unsupported risk score.

## Authorized data interface

[Public API documentation](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content). The public API guide was collected; actual service endpoints require participant authorization and were not called. A header-only template is supplied. Authorized exports can yield unique orders, order status outcomes and explicitly confirmed completion durations. These are operating outcomes, not internal buffer V.

Current order input: `awaiting_authorized_data`

## Execution and evidence

Sources retrieved: 12/12. Raw files, dates and SHA-256 hashes are in inputs/source_manifest.json. Findings remain review-only. No production event register or existing final16 scoring was modified.

The existing AWS API interpreted the public documents; 10 interpreted facts have local source checks. Quote and interpretation corrections are retained separately. This is not business signoff or empirical validation.

Stale API fact IDs (excluded until source review): []

Rebuild: `python3 src/build_monitor.py --as-of 2026-11-17 --window-start 2026-11-09`
Refresh public sources: `python3 src/collect_public.py` (network; no paid model call).
Read new documents through the existing AWS API: `python3 src/read_public_with_aws.py --invoke` (explicit manual call; cached attempt prevents accidental repeat).
Import: `python3 src/import_monitor_db.py` (portable SQLite; optional targeted existing-database import).

# DAS business line: public evidence and transmission chains

Collection date: 2026-11-09. The existing AWS Bedrock API read and interpreted the public documents and proposed the chains. Local code retrieved sources, checked provenance, and prepared the database.

Scope: DTC Digital Asset Solutions, focusing on tokenization/de-tokenization of DTC-held securities and the connection to traditional systems. DDA technology products remain a separate project business line.

These are research inputs requiring review. Continuous DAS internal buffers and operating outcomes were not obtained; event-to-business outcome correlations and risk scores have not been calculated.

## Public facts

- DTS launched October 28, 2026 as a voluntary service enabling eligible DTC Participants to tokenize DTC-custodied securities. ([launch](https://www.dtcc.com/press-releases/2026/dtcc-tokenization-service-goes-live))
- Twenty DTC Participants signed agreements to access DTS at launch; future users to be onboarded on a rolling basis. Signed agreements are not confirmed active users. ([launch](https://www.dtcc.com/press-releases/2026/dtcc-tokenization-service-goes-live))
- SEC Division of Trading and Markets staff issued a no-action position on December 11, 2025, covering Reg SCI, Exchange Act Section 19(b)/Rule 19b-4, and Rules 17Ad-22(e) and 17Ad-25(i)/(j) for the Preliminary Base Version. This is a staff no-action position, not blanket Commission approval. ([sec_staff_web_excerpt](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf))
- Eligible securities include Russell1000 constituents at pilot launch and later additions (including subsequent index removals), U.S. Treasury bills/bonds/notes, and ETFs tracking major indices. ([sec_staff_web_excerpt](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf))
- DTC will not ascribe collateral value or settlement value to any Tokenized Entitlements for purposes of DTC risk management, including Net Debit Cap or Collateral Monitor calculations. ([sec_staff_web_excerpt](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf))
- LedgerScan and Factory are designated Tier 2 systems with a four-hour recovery time objective, two-minute maximum data loss, and annual out-of-region DR testing. They are physically and logically separate from DTC's SCI clearing/settlement systems. ([sec_staff_web_excerpt](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf))
- Tokens are only transferable to Registered Wallets of DTC Participants. DTC retains technological capability to transfer tokens to address Conditions Requiring Reversal (erroneous entries, lost tokens, malfeasance). ([sec_staff_web_excerpt](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf))
- Conversion orders (tokenization/de-tokenization) may be submitted Monday–Friday 2:00 a.m.–6:00 p.m. ET; token transfers between Registered Wallets may occur 24/7. ([notice_das001](https://files.dtcc.com/download/assets/DAS-001/8a31d732d2d311f1a30ef632b7f70f6d))

## Candidate transmission chains

The following new DAS research IDs do not modify the original final16 cards or production news classifier.

### DAS-01 Network/System Resilience – DTS Infrastructure Outage

Network or DTS system unavailability may delay conversion orders or token transfers; participants relying on timely conversion or collateral movement could experience operational delays. System separation is a control intended to limit propagation; core-DTC disruption or participant losses are not automatic and have not been observed here.

- Internal-buffer metric: Tested failover capacity / peak required conversion throughput (ratio): proportion of peak conversion-order volume that can be processed from the secondary location within the RTO window
- Required real data: Actual tested secondary-site throughput records; peak conversion-order submission rates; LedgerScan/Factory DR test results
- Simulation limit: Assumption-based sensitivity testing only; no empirical DTS throughput or outage history available; private Besu uptime cannot be proxied by public network data

### DAS-02 Records/Reconciliation – LedgerScan Divergence Risk

A mismatch between LedgerScan records and on-chain state could require reconciliation or controlled correction; unresolved backlog could delay entitlement processing and affect DTC quarterly reporting to SEC staff. This is a conditional hypothesis; DTC bears the reporting commitment and published outcomes were not obtained.

- Internal-buffer metric: Reconciliation-resolution capacity / peak unresolved backlog (ratio): maximum number of divergence cases resolvable per day divided by peak observed or stress-assumed unresolved cases
- Required real data: LedgerScan reconciliation throughput benchmarks; historical count of Conditions Requiring Reversal invocations; root-wallet resolution turnaround times
- Simulation limit: No empirical reconciliation backlog data available; simulation is assumption-based only; root-wallet usage frequency not found in supplied documents

### DAS-03 Wallet/Security – Registered Wallet Compromise or OFAC Screening Failure

Compromised wallet allows unauthorized token transfers between Registered Wallets → DTC's LedgerScan detects movement but reversal requires root-wallet intervention → delay in reversal creates window of disputed ownership → if OFAC screening failed, DTC and participant face sanctions exposure; Registered Wallet restriction limits transfers to allowlisted addresses, reducing but not eliminating risk of unauthorized movement.

- Internal-buffer metric: Tokenized assets under verified multi-party control / total DTS tokenized assets (ratio): share of tokenized positions held in wallets with confirmed multi-party or institutional-grade key management
- Required real data: Wallet custodian key-management attestations; proportion of Registered Wallets using multi-party computation or HSM controls; OFAC re-screening frequency
- Simulation limit: Named collaborators are not confirmed approved custodians per supplied documents; no empirical wallet-compromise incident data available; simulation is assumption-based only

### DAS-04 Eligibility/Regulation – SEC No-Action Withdrawal or Eligibility Boundary Breach

A change in applicable regulatory conditions could require service restrictions, rule filings or contingency conversion, depending on official instructions. Capacity relative to affected positions determines the hypothetical adjustment burden. Neither forced conversion nor an enforcement action is assumed to occur automatically.

- Internal-buffer metric: Contingency de-tokenization capacity / affected tokenized positions (ratio): maximum number of positions DTC can de-tokenize per day under contingency procedures divided by total tokenized positions outstanding
- Required real data: DTC contingency de-tokenization throughput benchmarks; current total tokenized positions outstanding; eligibility monitoring process documentation
- Simulation limit: No empirical de-tokenization volume data available; regulatory revocation probability is not quantifiable from supplied documents; simulation is assumption-based sensitivity testing only

### DAS-05 Conversion/Corporate-Action Capacity – Window Congestion and Corporate Action Processing

Peak conversion demand above processing capacity could produce queues and delay participant workflows. Corporate-action payment errors could require correction. The letter permits two limited interfaces to core DTC: securities movements to/from the Digital Omnibus Account and corporate-action cash payments; cash payment is not the sole permitted interface. No processing failure has been established by this research.

- Internal-buffer metric: Conversion capacity / peak conversion demand (ratio): maximum Factory throughput (conversion orders per hour) divided by peak observed or stress-assumed submission rate
- Required real data: Factory system throughput benchmarks (orders per hour); historical or stress-scenario peak conversion-order submission rates; corporate action processing error rates for tokenized positions
- Simulation limit: No empirical DTS conversion volume data available; Factory throughput limits not disclosed in supplied documents; simulation is assumption-based functional testing only

## Validation and model interface

Retain S × V without E. Use business mechanisms to establish relevance, screen external signals against events, and run separate same-quarter transmission and next-quarter predictive tests once real internal outcomes are available.

Continuous real V is unavailable: the quarterly availability table preserves nulls. Any later 2020Q4–2026Q2 simulated series must be labeled counterfactual/prelaunch and stored separately from observations; it cannot be described as measured history or empirical validation.

The existing16 cards distinguish six PQD V cards from ten actual public-proxy V cards. Public proxies are not simulated values. No accepted proxy-V series is yet available for the new DAS cards. See [team pipeline alignment](TEAM_PIPELINE_ALIGNMENT_CN_EN.md).

When a suitable series exists, reuse the V rule: p = fraction of historical values <= current value; V = max(1, ceil(5p)). Orient values toward higher risk, use only available history, and flag short histories.

## Data and execution records

- Downloaded 5 DTCC official documents plus a web-reader excerpt of approximately the first11 pages of the SEC letter. Direct download of the39-page SEC PDF returned HTTP403; the full-document gap remains.
- Three AWS reading calls: first output-length limit, second candidate failed source review, third source-backed revision. All raw responses and costs were retained.
- Estimated cost using saved configured rates and returned token usage: $0.4458861.
- API candidates were checked against source excerpts with a separate correction record; exact quotation does not empirically validate a whole transmission chain.
- Added separate das_* datasets to the live local project SQLite and supplied a dedicated shareable snapshot. The existing compressed master snapshot was not rewritten; original full-source evidence remains local.
- [Chain registry](data/chain_candidates.json) · [Data request list](data/data_request_list.csv) · [Quarterly availability](data/quarterly_v_availability.csv)
- [Source manifest](inputs/source_manifest.json) · [Reviewed AWS interpretation](results/reviewed_understanding.json) · [Verification](results/verification.json)
- [Portable database](data/das_research.sqlite3.gz) · [Queries](queries.sql)

## Next steps

- Request actual Factory/LedgerScan capacity, DR-test results, conversion demand and reconciliation records; these populate the five protective-buffer ratios.
- Confirm Registered Wallet control attestations and approved infrastructure directly with DTC; named collaborators do not establish deployment or approval.
- Confirm the formal Preliminary Base Version commencement date and relief expiry with DTC rather than deriving expiry from a production milestone.
- Assess actual public-proxy series separately from internal measurements. Do not substitute market stress or generic crypto prices automatically for DAS V.
- Use assumption-based functional/sensitivity tests only with explicit labels; these do not calibrate or empirically validate real DAS risk.
- Extend a dedicated reviewed DAS news/card schema before any production classification; preserve the original final16 catalog.

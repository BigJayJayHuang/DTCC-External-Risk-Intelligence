# Test Summary: 31 New Transmission Chains

October21,2026 · Definition v3 · Exploratory analysis

**All31 received an evidence/data review; not all31 support numerical testing.** Ten received partial event/association/internal diagnostics, four only case/condition reviews, and17 still lack specific data. No new chain is fully validated. This is not a blanket finding that all31 mechanisms are invalid.

Event screening covers seven chains using five shared signals. Five chain views meet the old event threshold, representing only three distinct signals: funding, Treasury-yield changes and VIX. Eight association/diagnostic specifications cover seven chains, including one supplementary proxy and one internal diagnostic. Repeated signals and replacement outcomes are not independent validations.

## Findings

- **Auction supply to GSD total settlement:** same-month changes have rho0.578, 95% interval[0.451,0.688], n104 months. Month-effect OLS-HAC p0.204 weakens robustness. This is aggregate throughput, not auction-specific settlement disruption.
- **MBSD activity to unsettled positions:** levels rho0.879, interval[0.638,0.936], n22 quarters; consecutive-quarter changes rho0.414 and later-period levels rho0.257. Excluding the two activity-unit repairs gives levels rho0.865 and changes rho0.268. The association merits further work, but an independent external shock and actual forward-TBA pipeline detail remain missing.
- **Rate shock to GSD aggregate margin:** rho0.408, interval[-0.014,0.764], n22; below the old association gate. Futures and linked-account margin data are missing.
- **Funding to GCF price:** HAC coefficient0.021bp, p0.976, n246 days. The proxy specification is unsupported; this does not disprove collateral/funds-settlement mechanisms.
- **NSCC liquidity:** VIX to peak VM rho0.326, with an interval crossing zero. VM is not SLD. Next-quarter rho0.408 is a separate secondary result, not a replacement for the primary specification.
- Non-Fed triparty contraction hit none of four predefined stress windows; the CP spread hit only one of two. The original windows and failures were retained.

## Methods and limitations

Legacy rules are retained: past-only90th-percentile thresholds over252 valid daily observations or52 weekly peaks; at least two observable events, event-hit fraction>=2/3 and non-event alert proxy<=15%; daily tests additionally require median in-window alarm share>=25%. Non-event alert share is not a true false-positive rate because the event list is incomplete.

Same-quarter associations are primary; next-quarter associations are secondary. Confidence intervals use2,000 paired moving-block resamples: four consecutive quarters or12months, seed20261016. The old quarterly component gate is n>=12, rho>=0.3 and95% lower bound>0; new monthly specifications require n>=36. BH correction covers six primary specifications. Ordinary p/BH do not themselves remove serial dependence; block intervals/HAC address dependence uncertainty. Internal and supplementary diagnostics stay separate.

The plan was fixed before new correlations were calculated, after previous results and historical events were known. It is not preregistered and has no blind holdout. Auxiliary series are current revised/final vintages. Lead-lag pairs are descriptive, not real-time predictive performance, particularly given quarterly Financial Accounts publication delays. Current rules establish possible mechanisms, not the applicable rule version in every historical event.

The framework remains S times V with no separate E multiplier. Association tests are not vulnerability scores. No new service V, weights, loss probabilities or ML risk scores were invented.

## Data reconciliation and coverage

GSD/MBSD PQD23.2.1 values for2020Q4–2021Q3 were1,000times smaller than contemporaneous guarantee-note disclosures. All23 financial statements were checked; inconsistent early outcomes use the financial-note billion-USD conversion while retaining raw PQD values. The missing2024Q4 spreadsheet outcome is explicitly supplied by its financial note; cleared-notional data remain missing, so primary pairs n22. See data_quality_amendment.json and data/financial_guarantee_reconciliation.csv.

MBSD23.1.2 activity for2021Q3/2022Q3 appears million-USD encoded. Multiplying by1,000,000 matches independent monthly clearing-par totals divided by64 Treasury-observation business dates to within0.501million USD rounding tolerance in each quarter. This cross-source unit interpretation is accompanied by a sensitivity excluding both repaired periods; units were not inferred from correlations. See data/mbsd_cleared_notional_reconciliation.csv.

New OFR final data endJune30,2026; auctions are filtered throughOctober20, with complete-month analysis throughSeptember2026; Financial Accounts flows end2026Q2 in the September11 release. Frozen market series endOctober9 or13 and are not relabelled as October21 observations. PQD outcomes end2026Q2. Exact spans are in results/series_coverage.csv.

Enhanced ACS launched in March2025 and SFT in2022; earlier crises are not outcomes of those configurations. Historical Lehman/Carter notices were available only as official search-index excerpts, with404body URLs; these remain limited leads/condition checks, not complete historical-case validation.

## Chain-by-chain status

| Chain | Work completed | Interpretation and required evidence |
|---|---|---|
| ECS-NSCC-04 | Partial numerical tests | Tested top-five position concentration against top-five margin share. This is an internal structure diagnostic, not a named member concentration add-on. Anonymized member-day positions, concentration add-ons, risk parameters and requirement notices; the two top-five groups need not contain the same members. |
| FICC-MBSD-02 | Not run: specific data missing | Reviewed pool-settlement/fails-charge rules. Treasury or agency-debt fails were not substituted for MBSD pool-delivery failures. Historical SIFMA notification/settlement calendars, total and failed MBSD Pool Deliver Obligations, and dated allocation/reference-data errors. |
| FICC-MBSD-03 | Not run: specific data missing | Rules support Watch List monitoring and margin requirements. A broad Baa spread does not identify an MBSD member downgrade or Watch List entry. Historical MBSD membership/entity mapping, member credit events, and dated Watch List/additional-margin actions and amounts. |
| FICC-GSD-05 | Partial numerical tests | Ran funding-event screening and a GCF-minus-DVP rate-spread HAC regression. Price transmission is not evidence of late collateral allocation or funds-settlement failure. GCF allocation obligations, deadlines, late fees and funds-settlement exceptions; the final-rate matched sample covers only a short period. |
| FICC-GSD-07 | Partial numerical tests | Extracted MMF repo asset transactions and tested their association with GCF activity; added a separate non-Fed triparty-contraction sensitivity. CCIT lender identities, daily withdrawals/rollovers, and CCIT/GCF obligations; aggregate MMF repo transactions include Federal Reserve counterparties. |
| FICC-MBSD-04 | Case/condition review only | Used the January 9, 2025 market closure as a condition check: the indexed DTCC notice says available cash/securities settlement continued. Closure alone does not establish MBSD delay. The historical body URL is now unavailable. An actual MBSD market-disruption invocation, affected obligations, original/revised cutoffs, backlog and recovery records. |
| FICC-MBSD-05 | Not run: specific data missing | Reviewed participant-system-disruption rules. The ICBC Treasury-market incident is not direct evidence of an MBSD participant outage. Affected MBSD member/system, incident start/end, FICC connectivity/trade/settlement effects and comparable controls. |
| FICC-GSD-09 | Partial numerical tests | Tested Treasury-yield shocks against aggregate GSD margin changes and extracted PQD20.7.2. Futures-side and linked-account data are missing. Same-day Treasury-futures changes, cross-margin portfolios/Required Fund Deposits and definition versions; raw20.7.2 percent encodings are not directly spliced across periods. |
| FICC-GSD-10 | Partial numerical tests | Collected completed-auction records, aggregated offered amount by issue/settlement month, and tested changes against GSD total settlement activity; evidence weakens after calendar-month controls. Auction-only GSD netting/settlement, auction settlement exceptions and contemporaneous when-issued yields; no auction tail was fabricated. |
| FICC-MBSD-06 | Partial numerical tests | Tested cleared notional against MBSD unsettled positions after reconciling early PQD23.2.1 scale discrepancies to guarantee notes. Levels correlate strongly; changes and later-period evidence are weaker. TBA initiation and scheduled-settlement months, forward buildup/cancellations and funding pressure; cleared activity remains a pipeline proxy. |
| FICC-MBSD-07 | Not run: specific data missing | Confirmed option-trade/expiry/exercise provisions in MBSD rules. Ordinary rate movements were not substituted for near-expiry MBS option exposures. MBS option expiries, strikes/open interest, moneyness transitions, and actual exercise/settlement volume. |
| FICC-MBSD-08 | Not run: specific data missing | Reviewed EPN notification timing and disruption provisions; paired late/error messages and downstream settlements were unavailable. Timestamped EPN messages, validation errors, SIFMA cutoffs, pool confirmations and settlement results. |
| FICC-MBSD-09 | Not run: specific data missing | Confirmed EPN user cybersecurity requirements and related disruption provisions; a CISA catalog addition does not establish an EPN attack or user exposure. Named EPN-user incidents, affected technology/connectivity, rejected/delayed messages and recovery; share event IDs with MBSD05/08. |
| ECS-NSCC-05 | Partial numerical tests | Ran VIX event screening and association with maximum NSCC daily variation-margin payments. VM is a liquidity-demand proxy, not an SLD collection. Daily/intraday SLD requirements and collections, largest-member liquidity exposure, expiry/roll events. |
| ECS-NSCC-07 | Not run: specific data missing | Reviewed settling-bank provisions. A Fedwire or generic bank outage does not by itself establish an uncompleted member NSCC net settlement. Historical NSCC settling-bank mapping, named failures/refusals, net-net obligations and scheduled/actual completion times. |
| ECS-NSCC-08 | Case/condition review only | Official indexed notices describe Lehman ACATS request restrictions and later process changes, supporting a broker-failure touchpoint, not an inevitable volume surge. Historical PDF bodies are unavailable. Broker-specific ACATS requests, rejects, completions/reversals and timing; obtain original historical notices and comparable windows. |
| ECS-NSCC-09 | Partial numerical tests | Screened the funding proxy only on post-2022 SFT-era SVB/2025 events; no SFT-specific clearing, repricing or collateral outcome was available. SFT service volumes, positions, repricing, initial/independent amounts and settlement obligations; RDS SFTR reporting totals are not NSCC SFT clearing volumes. |
| ECS-DTC-01 | Partial numerical tests | Ran CP-minus-bill event screening and reviewed the MMI Funding Acknowledgment process; IPA/acronym funding outcomes were unavailable. Issuer/IPA/acronym mapping, presentments, acknowledgement times/amounts, PIF/optimization status and failed/delayed settlements. |
| ECS-DTC-03 | Case/condition review only | The indexed January9 2025 notice indicates DTCC settlement could remain open during market closure; ordinary closure is not a DTC force-majeure invocation. Actual DTC Rule38 invocation, affected obligations, revised cutoffs, backlog and recovery; distinguish market closure from service interruption. |
| AssetSvc-DTC-01 | Case/condition review only | SEC historical material confirms IPWG service restrictions and procedural review. Rules support chill/lock mechanisms, but no matched sample establishes that every SEC suspension triggers a DTC lock. Security/CUSIP-level SEC/FINRA actions, DTC chill/lock start/end and reason codes, and non-locked controls. |
| AssetSvc-DTC-02 | Not run: specific data missing | Reviewed deposit/registration/custody procedures; a trading suspension or generic issuer credit story is not a transfer-agent registration failure. Transfer-agent/issuer events, registration rejects/confirmations, DTC deposit-processing results and affected securities. |
| FICC-GSD-11 | Not run: specific data missing | Confirmed the enhanced ACS launch in March2025. Older crises cannot validate the new-service configuration; earlier agency arrangements must be distinguished. ACS version/effective dates, executing-client to Agent Clearing Member mapping, client stress and agent obligations/margin. |
| ECS-NSCC-10 | Not run: specific data missing | Reviewed ESS rules. Group Sandy expenses or Lehman envelope-service removal do not directly test a site outage causing ESS backlog. ESS site incidents, daily envelope/claim counts, queues/delays and money-settlement timing. |
| WIS-NSCC-01 | Not run: specific data missing | Rules establish I&RS service scope. Insurer stress does not automatically establish I&RS data/payment disruption. I&RS membership-to-insurer mapping, credit events, service messages/payments, rejects/delays and recovery. |
| ECS-DTC-04 | Not run: specific data missing | CDS risk-model and DTC rules establish the cross-border link. Canadian market indices or credit-default-swap data are not CDS infrastructure outages. CDS link incidents, DTC-CDS interface state, cross-border obligations, fails/delays and versions; share raw events with NSCC12. |
| AssetSvc-DTC-03 | Not run: specific data missing | DTC Rule36 establishes swap-margin segregated accounts. MF Global futures-customer-fund events are not evidence of instruction disruption in those accounts. DCO/FCM-to-DTC account roles, pledgee/pledgor instruction/access failures and segregated swap-margin balances. |
| AssetSvc-DTC-04 | Not run: specific data missing | CFTC material confirms MF Global customer-fund events, but there is no matched DTC Rule37 account balance/transfer evidence to validate the DTC route. FCM-failure to DTC customer-property segregated-account mapping, balances, transfer/protection instructions and timing under the applicable rule version. |
| WIS-NSCC-02 | Not run: specific data missing | Extracted Federal Reserve quarterly mutual-fund net issuance/redemptions. Continuous Fund/SERV outcomes are missing; net outflow is not gross processing volume and cannot satisfy daily event screening. Daily/monthly Fund/SERV purchases, redemptions/gross orders, payments, rejects/delays; industry net flows remain an external candidate. |
| WIS-NSCC-03 | Not run: specific data missing | Rules establish the AIP service mechanism. Mutual-fund outflows or generic private-credit stories were not substituted for AIP data/payment incidents. AIP fund/administrator mapping, valuation/liquidity events, AIP message/payment volumes and failure/delay times. |
| ECS-DTC-06 | Partial numerical tests | Ran daily VIX event screening and reviewed NDC/Collateral Monitor delivery controls; participant intraday cap usage and blocked deliveries were unavailable. Participant intraday debit, Net Debit Cap, Collateral Monitor, blocked DVP amounts/durations and funding-release records; daily VIX is only a proxy. |
| ECS-NSCC-12 | Not run: specific data missing | Rules and CDS risk-model material establish international-link scope; foreign stress was not matched to NSCC link transaction failures. Foreign institution/NSCC member/link roles, service versions, cross-border trade/payment exceptions; do not transfer DTC04 outcomes directly. |

## Executed numerical results

| Specification | Sample and result | Scope |
|---|---|---|
| GCF funding spread | n=246; β=0.021 bp; HAC p=0.976; 95% CI [-1.327, 1.369] | Component gate unmet; mechanism not disproved |
| MMF repo flows to GCF activity | n=31; ρ=0.115; 95% CI [-0.178, 0.497] | Component gate unmet; mechanism not disproved |
| Non-Fed triparty to GCF (supplementary) | n=97; ρ=0.099; 95% CI [-0.069, 0.224] | Component gate unmet; mechanism not disproved |
| Rate shock to GSD aggregate margin (proxy) | n=22; ρ=0.408; 95% CI [-0.014, 0.764] | Component gate unmet; mechanism not disproved |
| Auction supply to GSD total settlement (proxy) | n=104; ρ=0.578; 95% CI [0.451, 0.688] | Component gate met; full chain unvalidated |
| MBSD cleared notional to unsettled positions (proxy) | n=22; ρ=0.879; 95% CI [0.638, 0.936] | Component gate met; full chain unvalidated |
| NSCC concentration to margin share (internal diagnostic) | n=22; ρ=-0.353; 95% CI [-0.725, 0.258] | Internal diagnostic, not external-shock validation |
| VIX to NSCC VM payments (not SLD) | n=23; ρ=0.326; 95% CI [-0.083, 0.771] | Component gate unmet; mechanism not disproved |

![Quarterly confidence intervals](figures/quarterly_components.png)

![MBSD levels and changes](figures/mbsd_levels_changes.png)

## Files and reproduction

- [Chain status CSV](results/new_chain_status_EN.csv)
- [Executed notebook](New_Reference_Chain_Validation.ipynb)
- [All association results](results/association_results.csv) / [event results](results/event_test_summary.csv)
- [Source register](results/source_register.json) / [fetch attempts](fetch_manifest.json)
- [Updated catalog view](chain_registry_v3_with_test_status.json)

## Public-source references

- [OFR](https://data.financialresearch.gov/): New final-vintage repo data with separately downloaded metadata. Final series end2026-06-30; rate matched sample is much shorter than volume history.
- [TREASURY](https://www.treasurydirect.gov/legal-information/developers/web-api-security/): Server ignored request date filter; 11158 records received; local completed-auction and date filters retained3594 records. Offering amount is not actual awarded amount or auction tail.
- [FED_Z1](https://www.federalreserve.gov/releases/z1/20260911/z1_csv_files.zip): September11 2026 release. FU632051000.Q MMF repo asset transactions and FU653164205.Q mutual-fund net share issuance, USD million, not seasonally adjusted.
- [PQD](https://www.dtcc.com/legal/policy-and-compliance): Frozen2020Q4–2026Q2 sources;22 XLSX plus one2024Q4 PDF. Additional cell extraction covers22 quarters, not an invented23rd spreadsheet.
- [FINANCIALS](https://www.dtcc.com/legal/financial-statements): 23 FICC financial statement guarantee-note tables, with page evidence;23.2.1 early scale discrepancies and missing2024Q4 spreadsheet outcome reconciled explicitly.
- [LEGACY_MARKET](https://fred.stlouisfed.org/): Frozen prior market observations; individual dates differ. Not a fresh daily market update. DCPF3M/DTB3 frozen separately.
- [RULES_INDEX](https://www.dtcc.com/legal/rules-and-procedures): Official current links resolve to files.dtcc.com. Current rules support mechanisms, not historical incidents or historical rule versions.
- [NSCC_RULES](https://files.dtcc.com/download/assets/nscc_rules.pdf/85bda02a369211f0a3ae820bd5ac0897): Rule4A SLD, Rule9 ESS, ACATS, I&RS, AIP, SFT and international-link provisions; September21 2026 version.
- [GSD_RULES](https://files.dtcc.com/download/assets/FICC-GSD%2BRulebook%2B%E2%80%93%2B2026-0826%2BFinal.pdf/b6c07124ceb411f09c9062cd3fe05a01): GCF, CCIT, auction purchases, cross-margining and ACS definitions.
- [MBSD_RULES](https://files.dtcc.com/download/assets/ficc_mbsd_rules.pdf/d410be52369111f0b606526112f6cc5f): Watch List, pool settlement/fails, options, market/system disruption rules.
- [EPN_RULES](https://files.dtcc.com/download/assets/ficc_mbsd_epnrules.pdf/4c561ca4369211f09a845e09fb65ecc7): EPN message and cybersecurity obligations; no message-error or attack history inferred.
- [DTC_RULES](https://files.dtcc.com/download/assets/dtc_rules.pdf/6064c95e369511f09a845e09fb65ecc7): MMI, settling banks, Canadian-Link, chills/locks, segregation and disruption provisions; April28 2026 version.
- [DTC_SETTLEMENT](https://files.dtcc.com/download/assets/Settlement.pdf/c83a99be369a11f093d0c204a2f8334f): Funding acknowledgments, NDC and Collateral Monitor controls. No participant exception logs collected.
- [SEC_CHILL](https://public-inspection.federalregister.gov/2014-06459.pdf): Historical SEC procedural discussion of DTC restrictions and International Power; does not establish a matched suspension-to-lock event series.
- [SEC_IPWG](https://www.sec.gov/news/digest/2012/dig031512.htm): Web text reviewed, lines101–103; confirms DTC suspension/procedural remand for IPWG; direct local request403. No inference that every SEC halt causes a lock.
- [ACATS_LEHMAN](https://www.dtcc.com/-/media/Files/pdf/2008/9/22/a6705.pdf): Official search-index excerpt only; body404. Describes no new Lehman ACATS initiation requests after September22 2008. Not a complete volume/duration test.
- [ACATS_PROJECT](https://www.dtcc.com/-/media/Files/pdf/2012/12/21/a7556.pdf): Official search-index excerpt only; body404. Describes Lehman-related ACATS process initiatives, not quantitative volumes.
- [CARTER_CLOSURE](https://www.dtcc.com/-/media/Files/pdf/2024/12/30/0275.pdf): Official search-index excerpt only; body404. Announcement that DTCC subsidiaries remain open for available settlement on January9 2025; condition check, not a post-event outage log.
- [ACS_LAUNCH](https://www.dtcc.com/press-releases/2025/dtccs-ficc-now-live-with-new-treasury-clearing-capabilities): Enhanced ACS launch March2025. Do not assign pre-launch crisis outcomes to this configuration.
- [SFT_ACCESS](https://www.dtcc.com/press-releases/2026/dtcc-receives-regulatory-approval-to-launch-new-client-access-model-for-nsccs-sft-clearing-service): May13 2026 access-model extension; not an adverse outcome or time series. SFT launched2022 per DTCC2022 annual-report indexed text.
- [CDS](https://www.cds.ca/resource/en/56): CDS link risk model; infrastructure CDS is not a credit-default swap. No link-outage history collected.
- [CFTC_MFG](https://www.cftc.gov/PressRoom/PressReleases/6626-13): MF Global customer-fund enforcement history. Does not establish involvement of DTC Rule36/37 accounts.

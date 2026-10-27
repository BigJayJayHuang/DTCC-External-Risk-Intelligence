> **Scope corrected (2026-10-27):** This is the earlier broad hypothetical batch, not the current missing-data-only study. Observed fields must not be replaced. Use the [real-data-first revision](../synthetic_data_scope_revision_2026_10_27/README.md) and its56-chain step-level ledger. Original numbers remain historical implementation experiments.

# Expanded transmission-chain scenario simulations

**Synthetic mechanism experiments, not actual incidents, official risk models or machine-learning validation.** This batch adds **19 mechanism prototypes, partial mechanism coverage for 20 catalog chains and 102 predeclared scenarios**, each with 100 paired paths: 10,200 scenario runs and 298,200 generated records. Seed 20261027; batch `SIM2_a980a9e441f61837`.

Together with the [earlier DTC/EPN/TBA prototypes](../synthetic_chain_simulations_2026_10_27/README.md), there are **22 mechanism prototypes and 131 scenarios**. Among 56 expanded-v3 catalog chains, **24 have partial mechanism simulations, another 2 have generic outage contexts only, and 30 have no dedicated simulation**. Coverage counts are not validation counts. No chain in this branch is marked fully validated.

## Added scope

- Margin/liquidity: separate GSD, MBSD and NSCC books; VM cash flows, margin stocks, concentration add-ons and SLD remain distinct. Cross-margin illustrates assumed offsets.
- Default/funding: GSD own resources and illustrative residual allocation, NSCC long/short close-out, GCF joint deadline gates, auction issue-date funding concentration, and distinct DTC/NSCC settling-bank gates.
- Service operations: MMI funding acknowledgement, ACATS transfer waves, Fund/SERV gross purchase/redemption processing, registration confirmation, explicit security-level chill/lock, DTC Canadian link and NSCC international link.

## Results under declared assumptions

Each row uses its own measures and inputs; the values cannot rank business risk. Mitigation can add cash, resources, capacity or change exposures and is not costless.

| Chain IDs | Mechanism simulated | Baseline mean | Stress mean | Mitigation mean | Units |
|---|---|---|---|---|---|
| FICC-GSD-01 | Assumed Treasury price moves/volatility alter required margin. | 0.00 | 99.78 | 0.00 | USD million |
| FICC-MBSD-01 | An assumed MBS factor move changes VM cash and required margin. | 3.85 | 96.36 | 33.73 | USD million |
| ECS-NSCC-01 | Assumed equity moves become member VM payments and receipts. | 3.78 | 60.49 | 21.17 | USD million |
| TEAM-ECS-01 | Assumed volatility changes Clearing Fund requirements and incremental cash needs, separate from VM. | 0.00 | 136.09 | 0.00 | USD million |
| ECS-NSCC-04 | Single-member security concentration alters a hypothetical margin add-on. | 0.00 | 31.76 | 0.00 | USD million |
| ECS-NSCC-05 | Largest affiliated-family liquidity exposure produces illustrative deposit calls and uncovered gaps. | 0.00 | 168.61 | 168.61 | USD million |
| FICC-GSD-09 | Signed Treasury/futures exposures alter combined risk and requirement under assumed correlation. | 37.54 | 300.55 | 75.08 | USD million |
| FICC-GSD-06 | Conditional own-resource use and toy residual allocation after activated default | 0.00 | 30.22 | 12.06 | USD million |
| ECS-NSCC-06 | Adverse repricing of hypothetical long/short positions during delayed close-out | 0.00 | 7.81 | 3.96 | USD million |
| FICC-GSD-05 | Joint cash/collateral deadlines on hypothetical allocation units | 0.00 | 76.92 | 0.00 | USD million |
| FICC-GSD-10 | Concentration of assumed netted issue-date cash obligations | 0.00 | 92.48 | 0.00 | USD million |
| ECS-DTC-02 | DTC-only hypothetical bank mapping and end-day acknowledgement gate | 0.00 | 23.69 | 0.00 | USD million |
| ECS-NSCC-07 | NSCC-only hypothetical bank mapping and end-day acknowledgement gate | 0.00 | 13.43 | 0.00 | USD million |
| ECS-DTC-01 | Hypothetical IPA funding acknowledgement by acronym, with separate maturity and issuance instructions. | 0.00% | 24.07% | 0.00% | fraction_of_instructions |
| ECS-NSCC-08 | Hypothetical broker-exit transfer arrivals and processing queue. | 0.00% | 37.89% | 0.00% | fraction_of_instructions |
| WIS-NSCC-02 | Separate purchase/redemption gross orders, processing capacity and independently prefunded redemption cash. | 0.00% | 42.49% | 0.00% | fraction_of_instructions |
| AssetSvc-DTC-02 | Deposit instructions require an explicit hypothetical registration confirmation. | 0.00% | 25.80% | 0.00% | fraction_of_instructions |
| AssetSvc-DTC-01 | Explicit security-level deposit chill gates deposits; global lock gates modeled deposits and transfers. | 0.00% | 13.13% | 0.00% | fraction_of_instructions |
| ECS-DTC-04 | Independently generated DTC Canadian-Link dependencies and interrupted cross-border instructions. | 0.00% | 29.60% | 0.40% | fraction_of_instructions |
| ECS-NSCC-12 | Separately generated foreign-institution link dependencies and interrupted NSCC cross-border instructions. | 0.00% | 28.33% | 0.00% | fraction_of_instructions |

`USD million` means millions of US dollars. Fraction measures are displayed as percentages; proportions in assumed paths are not real failure probabilities. Means reflect only the specified synthetic distributions. See [all scenario summaries](results/scenario_summary.csv). Figure intervals are 5th–95th path percentiles, not confidence intervals for real-world parameters.

Figures: [Margin/liquidity](figures/margin_liquidity.png) · [Default/funding](figures/default_funding.png) · [Service operations](figures/service_operations.png). Panel measures/scales are independent and do not rank business risk.

SLD calls and collection must be read separately. More available member cash improves collection and the remaining gap without changing the required call.

| SLD measure, USD million | Baseline | Stress | More member cash |
|---|---|---|---|
| SLD called | 0.00 | 168.61 | 168.61 |
| SLD collected in the model | 0.00 | 63.46 | 168.61 |
| Remaining modeled liquidity gap | 0.00 | 105.15 | 0.00 |

NSCC VM and TEAM-ECS-01 margin calls appear as separate rows above. For cross-margin, the mitigation column is only an alternative scenario restoring assumed correlation; correlation is not a directly controllable business action. Zero outcomes in many mitigation cases reflect sufficient chosen resources/thresholds, not guarantees of real-world safety.

## Interpretation

Workflow: **route an event to the catalog mechanism → generate virtual positions/orders/funding → impose a predeclared shock → apply explicit resource/time/authorization constraints → record outcomes → compare paired baseline, stress, mitigation and unrelated controls**. There is no additional E multiplier; applicability is an assumed routing condition, not a relationship established by generated data.

VM is a marked-to-market cash flow, margin is a resource requirement stock, and SLD is a separate liquidity payment requirement. Late-completed and unfinished outcomes are distinct. Passing a funding/authorization gate in a model is not proof that full real-world settlement would complete. The GSD residual-capacity allocation is not the official loss waterfall. The NSCC adverse long/short close-out scenario is not one common market-price path.

## Evidence still missing

- Actual incident-to-member/service exposure, incident frequency, real parameters and official model formulas.
- A causal relationship between external shocks and lagged-PQD vulnerability, a validated full shock×vulnerability score, or predictive model performance. No model was fitted or retrained on synthetic outcomes.
- See [all 56 catalog-chain coverage entries](CHAIN_COVERAGE_EN.md) and the [chain CSV](results/chain_coverage_EN.csv). Actual memberships, discretionary control decisions, legal triggers/consent, service versions and observed outcomes cannot be manufactured as evidence.
- The empirical database, 31-chain empirical results and teammate weekly scores remain unchanged. Every generated record is isolated in a separate SQLite database with `source_type=synthetic` and `empirical_validation=False`.

## Reproduce and inspect

[README](README.md) · [Frozen plan](config/resolved_plan.json) · [Assumptions](results/model_assumptions.json) · [Checks](results/verification.json) · [Sources and uses](inputs/source_register.json). Quant-tech baseline/sensitivity guidance informed experiment design; that does not establish real-world generalization.

Qualitative references: [MMI acknowledgement](https://dtcclearning.com/products-and-services/settlement/mmi.html), [ACATS](https://dtcclearning.com/products-and-services/equities-clearing/acats.html), [Fund/SERV](https://dtcclearning.com/products-and-services/mutual-fund-services/fund-serv.html), [cross-margining](https://dtcclearning.com/products-and-services/fixed-income-clearing/cross-margining.html). None supplies the hypothetical numeric parameters used here. Saved rule evidence retains its original version.

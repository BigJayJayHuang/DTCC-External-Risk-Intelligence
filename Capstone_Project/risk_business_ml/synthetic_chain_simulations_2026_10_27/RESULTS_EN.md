> **Scope corrected (2026-10-27):** This is the earlier broad hypothetical batch, not the current missing-data-only study. Observed fields must not be replaced. Use the [real-data-first revision](../synthetic_data_scope_revision_2026_10_27/README.md) and its56-chain step-level ledger. Original numbers remain historical implementation experiments.

# Three synthetic transmission-chain prototypes

**SIMULATION ONLY.** These are executed mechanism/implementation experiments, not observations of DTCC members, incidents, production processing or calibrated business risk.

Three models,29 declared scenarios,100 paired replications per scenario: **2,900 scenario runs** and **334,757 generated input/trace/summary records**. Seed20261027. Identity: `SIM_ec170e3eef71a590`. The29 cases use different assumptions and measures; they are not29 historical events.

| Prototype | Conditional result under the stated assumptions |
|---|---|
| DTC two-constraint queue | Mean pending transactions at the480-minute horizon: **USD33.96million** under combined funding delay/shortfall and haircut shock, versus0 in baseline. A larger assumed cap/collateral buffer allows processing but leaves mean outstanding debit **USD57.10million**. Extra-cash mitigation adds **USD103.48million** of assumed cash on average; its benefit is not free. Cap capacity alone does not remove the collateral constraint in these cases. |
| EPN notification-to-pool pipeline | A hypothetical160-minute relevant outage leaves **21.44%** of orders overdue at the assumed delivery deadline, versus0 in baseline. A higher ALL-DAY processing capacity yields0 overdue orders in the paired cases. Beyond-horizon outage leaves **25.29** orders unfinished on average; zero late-completed orders in that case is not evidence of safety. |
| TBA stock-flow ladder | Peak overdue notional averages **25.98%** of hypothetical opening TBA stock under prolonged deferral; earlier recovery reduces this measure to **17.04%**. These are gross-notional stock ratios, not losses, cash payment obligations or real failure probabilities. |

## What was checked

Hand-computed fixtures, resource/admission limits, cash and transaction conservation, stock-flow conservation, exact unrelated-event controls, deadlines, horizon censoring, common random inputs and repeat-store idempotency. Runtime controls are in `results/execution_receipt.json`; independent audits and unit-test evidence are in `results/`. Passing a code check does not validate an empirical transmission chain.

## Assumptions that change interpretation

- DTC: a generic single-participant FIFO queue; it is not DTC's production optimization engine. Simulated cash repays debit before prefunding; it is not also credited to collateral. Received securities do not automatically replenish the separate eligible collateral portfolio. Baseline scheduled cash equals generated gross payments by construction. Stress combines50% scheduled amounts,180-minute delay and a haircut increase; some funding arrives outside the horizon, so received cash is not simply50% of baseline.
- EPN: relative cutoff240, delivery deadline300 and horizon480 are arbitrary simulation minutes, not official SIFMA cutoffs. All generated original/corrected valid notices arrive before cutoff; the outage delays processing and delivery. A separate hand-computed fixture covers a late notice that is still delivered on time. Capacity mitigation applies to the ENTIRE day. Nominal queue start/pre-service wait excludes pauses during service. Delayed completions and unfinished orders remain separate.
- TBA: the public2026Q2 broad MBSD unsettled-guarantee amount, USD562billion, is an illustrative scale only. A50% TBA share and25%/75% sensitivity shares are assumptions, not estimates. New flows, maturities, cancellations and deferrals are synthetic. Equal normalized results across share cases follow from linear scaling, not evidence of real business sensitivity. On an unimpaired model day all due positions settle; there is no independently calibrated throughput limit.
- Percentile bars describe variation among hypothetical paths. They are not confidence intervals for DTCC or empirical probabilities. No p-values or synthetic correlations are used to declare a chain validated.

## Data separation

Every generated row is labelled `source_type=synthetic`, with scenario/replication/seed, assumption version, catalog version and simulation ID. Exact unsigned RNG seeds are stored as text. The public anchor is in a separate reference table. The dedicated `data/synthetic_scenarios.sqlite3` is physically separate from the team's real public-data database. Historical missing-data statuses and existing weekly scores remain unchanged; no model was fitted or retrained on synthetic outcomes.

Use `results/chain_simulation_status.csv` for the additional scenario-exploration label. It does not replace the empirical31-chain status table. MBSD05/09 are generic conditional-outage contexts, not identified cyber incidents or affected participants.

## Open and rerun

Start with [README](README.md). See [all scenario results](results/scenario_summary.csv), [frozen plan](config/resolved_plan.json), [assumptions](results/model_assumptions.json), [source register](inputs/source_register.json) and [SQL examples](src/query_synthetic.sql). The full numerical setup is reproducible; the real-world behavior remains to be tested with suitable data.

Mechanism context: [DTCC financial risk controls](https://www.dtcc.com/about/protecting-the-markets/managing-risk/financial-risk-management). Synthetic-data scope: [ONS policy](https://www.ons.gov.uk/aboutus/transparencyandgovernance/datastrategy/datapolicies/syntheticdatapolicy). These sources do not supply our hypothetical numerical parameters. Quant-tech sensitivity/generalization guidance informed the control design.

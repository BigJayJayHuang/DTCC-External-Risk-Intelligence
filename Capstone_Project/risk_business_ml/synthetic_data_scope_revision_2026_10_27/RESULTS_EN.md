# Corrected scope: preserve real data; simulate missing steps only

**The earlier expansion was too broad and has been corrected.** Source precedence must determine the inputs, not merely appear as a synthetic-data label afterward. Existing real-data tests remain authoritative, including weak or insignificant results. A failed threshold or short sample is not missing data.

## Source routes across 56 chains

- **9 use existing real-data specifications.** Some calendar/design work remains; do not generate replacement business observations.
- **22 preserve observed components and permit simulation only for missing steps.**
- **18 lack dedicated service data and are conditional-simulation candidates.** This is not a claim that18new tests are complete.
- **7 require facts/definitions first.** Actual legal decisions, Watch List actions, dependencies and triggers cannot be manufactured as evidence.

The [56-chain ledger](SOURCE_PRIORITY_EN.md) and [CSV](results/source_priority_EN.csv) identify observed components, forbidden replacements and permitted assumptions.

## Three corrected runnable examples

| Chain/example | Real data held fixed | Missing quantities assumed | Checks |
|---|---|---|---|
| GSD auction funding | Actual September 2026 issue dates and 37 records totalling USD 2.658 trillion **offered supply** | Unknown award/clearing participation/netting conversion and cash availability/delay | Cash and unpaid-obligation conservation; dates and offered amounts unchanged |
| MBSD TBA ladder | Actual 2026Q2 broad unsettled-guarantee notional, **USD 562 billion** | Undisclosed TBA share, maturity ladder and deferral | Stock conservation; broad total is not actual TBA-only stock |
| NSCC member concentration | Actual 2026Q2 top-five position-share quarterly average **36.49%**, with peak **40.25%** separate | Compatible virtual member allocation and hypothetical add-on rule | Aggregate, rank and normalization constraints; no real identities inferred |

There are 15 scenarios with 100 paired paths each: **1,500 runs and 62,500 scenario/trace records**; 17 unit checks passed. The source policy rejects generation requests for observed fields and verifies unchanged frozen files.

Under the current stress assumptions, means are **USD 25,362.03 million** peak unpaid auction obligations, **6.86%** peak overdue / assumed initial TBA stock, and **2.1767 normalized exposure units** for the hypothetical concentration add-on (total 100, **not dollars**). These are not observed GSD shortfalls, actual TBA failure rates or actual NSCC calls. See [all scenarios](results/scenario_summary.csv).

## What this tests

**Preserve real observations → assume only missing quantities/ranges → enforce resource/stock/rank constraints → compare baseline, stress, mitigation and unrelated controls → report sensitivity to assumptions.**

This answers what would happen under explicit missing-link assumptions and checks implementation coherence. It cannot establish that a real historical event reached a business. A virtual member distribution is not an observed book; quarterly-average concentration is not a daily or quarter-end portfolio. Offered supply is not awarded supply or a GSD obligation. Original empirical tests, the real database and teammate scores are unchanged.

Conditional simulation is appropriate when facts are supported but an internal process is missing. Unconfirmed incidents, dependencies or legal triggers remain unconfirmed, rather than being filled with random event labels. Missing from collected data is not proof that public data are permanently unavailable.

[Frozen sources](inputs/observed_source_manifest.json) · [Field-level provenance](results/field_provenance.json) · [Assumptions](results/model_assumptions.json) · [Execution receipt](results/execution_receipt.json). Earlier 131 broad hypothetical scenarios remain historical implementation experiments, not the current gap-only coverage count.

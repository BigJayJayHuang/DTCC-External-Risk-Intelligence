"""Validation round 1: owner sign-offs (2026-10-16) and the active version of each chain.

The scoring backend reads results/chain_tests/chain_confidence.json, built from this file
and the per-chain JSONs by `python -m validation.export`.
"""

ROUND = 'validation round 1'
CLOSED_UTC = '2026-10-16T07:58Z'

# chain id -> active version file, final confidence, superseded versions, evidence note
FINAL = {
    'FICC-GSD-01': dict(active='FICC-GSD-01', confidence='Medium', superseded=[],
        evidence='Test 1 PASS (weekly, 3/3). Test 2 inconclusive: same-quarter rho 0.41, 95% CI [-0.01, 0.76], n 22; BH q 0.24.'),
    'FICC-GSD-02': dict(active='FICC-GSD-02.v2', confidence='Medium', superseded=['FICC-GSD-02 (v1, Medium)'], watch=True,
        evidence='Test 1 PASS (weekly, 3/3). v2 (post-hoc, Treasury-only GCF for data coverage): shock-day coefficient -0.67 bp, '
                 'HAC p 0.095, n 1,728; wrong sign but not significant -> WATCH. Outside v1 BH family; q 0.23 if added. '
                 'v1 (GCF overnight, n 246): +0.02 bp, p 0.97.'),
    'FICC-GSD-03': dict(active='FICC-GSD-03', confidence='Low', superseded=[], shock_from_rubric=True,
        evidence='No market indicator. Milestones sourced (SEC 2023-247; Rel. 34-102487). Test 2 not supported: Sponsored volume '
                 '+21.1% (80th pct) and +5.4% (33rd pct) of all 60-day before/after changes. Owner sign-off: not supported.'),
    'FICC-GSD-04': dict(active='FICC-GSD-04', confidence='Medium', superseded=[],
        evidence='Test 1 PASS (weekly, 2/2). Test 2 PASS by owner sign-off: DTCC press release 30 Oct 2008, PDF p.2 - FICC GSD '
                 'closed out $190bn gross Lehman positions to honour its guarantee; MBSD liquidated $329bn TBA book with no losses '
                 'to members\' clearing deposits.'),
    'FICC-MBSD-01': dict(active='FICC-MBSD-01', confidence='Medium', superseded=[],
        evidence='Test 1 PASS (weekly, 2/3; missed COVID). Test 2 inconclusive: rho 0.15, CI [-0.16, 0.59]; BH q 0.67.'),
    'ECS-NSCC-01': dict(active='ECS-NSCC-01', confidence='Medium', superseded=[], candidate=True,
        evidence='v2 candidate. Test 1 PASS (daily, 4/4). Test 2 inconclusive at lag 0 (levels 0.34, changes -0.33). Lag-1 '
                 'hypothesis pre-registered as v3 (TEST_SPEC §14), to be tested only on 2026Q3+ PQD.'),
    'ECS-NSCC-02': dict(active='ECS-NSCC-02', confidence='Medium', superseded=[], candidate=True,
        evidence='v2 candidate. Test 1 PASS (daily, 3/3). Test 2 inconclusive: levels rho 0.55 CI [0.02, 0.70] pass, changes 0.01 '
                 'fail -> possible shared trend. Lag-1 hypothesis pre-registered as v3 (2026Q3+ only).'),
    'ECS-NSCC-03': dict(active='ECS-NSCC-03', confidence='Medium', superseded=[],
        evidence='Test 1 PASS (daily, 3/3). Test 2 inconclusive: shock-week coefficient +$0.50bn fail value, HAC p 0.24 '
                 '(next week p 0.069). Vulnerability: no public data (shock-only).'),
    'ECS-SET-01': dict(active='ECS-SET-01', confidence='Low', superseded=[], shock_from_rubric=True,
        evidence='No market indicator; descriptive only. Approximate pre-T+1 baseline = May 2024 snapshot (NSCC 2.00%, DTC 2.83%; '
                 'mostly T+2 days, only two points). After: CNS 1.9% first T+1 day, July 2024 CNS 2.12% and DTC non-CNS 3.31% '
                 '(T+1 After-Action Report p.7); Aug 2026 NSCC 2.21%, DTC 3.18%.'),
    'ECS-NSCC-04': dict(active='ECS-NSCC-04.v2', confidence='Low', superseded=['ECS-NSCC-04 (v1, Test 1 FAIL, revise/drop)'],
        shock_from_rubric=True,
        mechanism='Concentrated member positions strain member capital/liquidity -> NSCC raises that member\'s requirements '
                  '(special charges / excess capital premium).',
        evidence='v2 (post-hoc): no market indicator. Case rule PASS by owner sign-off: SEC staff report (early 2021), printed '
                 'pp.31-32 - $4.8bn special charge on 18 members (Jan 27, 2021); capital-based ECP charges waived Jan 28. '
                 'Confidence Low: trigger was concentrated positions vs member capital, not credit stress or default.'),
}

# Scoring v1.2 (results/scoring/SCORING_SPEC.md §12.1; owner-approved 2026-10-23): liquidity V from same-quarter
# PQD 7.3.1 ÷ 7.1 instead of 7.3.4 ÷ 7.1. Validation results are unchanged; only the scoring field is replaced.
SCORING_VULN = {cid: dict(field='payment_to_qlr', scoring_version='v1.2',
                          label='Estimated largest payment obligation ÷ qualifying liquid resources (7.3.1 ÷ 7.1)',
                          replaces='peak_payment_to_qlr (7.3.4 ÷ 7.1)')
                for cid in ('FICC-GSD-02', 'ECS-NSCC-01', 'ECS-NSCC-02')}

"""Chain cards in scope (TEST_SPEC.md v1). One signal, one test variable per card."""

W = lambda label, start, end: {'label': label, 'start': start, 'end': end}
COVID = W('COVID shock', '2020-03-09', '2020-03-23')
SVB = W('Bank stress (SVB)', '2023-03-08', '2023-03-17')
UST25 = W('2025 Treasury/tariff shock', '2025-04-02', '2025-04-11')
REPO19 = W('Repo spike', '2019-09-16', '2019-09-20')
MEME = W('Meme-stock week', '2021-01-25', '2021-01-29')
VOL24 = W('Volatility spike', '2024-08-05', '2024-08-09')
GILT22 = W('Rate hikes / gilt stress (D3)', '2022-09-21', '2022-10-14')

CHAINS = {
    'FICC-GSD-01': dict(
        name='Treasury market volatility', version='v1', entity='GSD', kind='quarterly',
        signal='ust10_abs_change', signal_label='|ΔDGS10| daily, bp (FRED)', test1='weekly', test1_median_share=False,
        windows=[COVID, SVB, UST25], test_var='im_qoq', test_var_label='GSD margin QoQ growth (PQD 6.1.1)',
        changes_check=False, vuln='stress_loss_to_im', vuln_label='Cover-1 stress loss ÷ margin (4.4.3 ÷ 6.1.1)',
        prior_seen='Yes (card cites same-quarter rho 0.408)'),
    'FICC-GSD-02': dict(
        name='Repo funding pressure', version='v1', entity='GSD', kind='event_daily',
        signal='sofr_effr_adjusted', signal_label='SOFR−EFFR quarter-end adjusted, bp', test1='weekly', test1_median_share=False,
        windows=[REPO19, COVID, UST25], test_var='gcf_minus_dvp_oo_bp', test_var_label='OFR GCF−DVP overnight rate, bp (Final)',
        vuln='peak_payment_to_qlr', vuln_label='Peak payment obligation ÷ qualifying liquid resources (7.3.4 ÷ 7.1)',
        prior_seen='Signal yes; test variable no'),
    'FICC-GSD-03': dict(
        name='Treasury clearing mandate', version='v1', entity='GSD', kind='case_sponsored',
        signal=None, test_var='sponsored_total_usd', test_var_label='FICC Sponsored daily TOTAL_AMOUNT (USD)',
        vuln='top5_client_share', vuln_label='Top-5 share of client transactions (PQD 19.1.3.2, avg)', prior_seen='No'),
    'FICC-GSD-04': dict(
        name='Member credit deterioration', version='v1', entity='GSD', kind='case',
        signal='baa_widen20', signal_label='Baa−10Y 20-day widening, bp', test1='weekly', test1_median_share=False,
        windows=[COVID, SVB], vuln='top5_open_share', vuln_label='Top-5 share of open positions (PQD 18.2.2)',
        prior_seen='Yes for the signal'),
    'FICC-MBSD-01': dict(
        name='MBS spread shock', version='v1', entity='MBSD', kind='quarterly',
        signal='mbs_spread_abs_wchg', signal_label='|Δ(MORTGAGE30US − DGS10)| weekly, bp', test1='weekly_native',
        test1_median_share=False, windows=[COVID, GILT22, UST25], test_var='vm_peak_qoq',
        test_var_label='MBSD peak daily VM QoQ growth (PQD 6.7.1)', changes_check=False,
        vuln='stress_loss_to_im', vuln_label='Cover-1 stress loss ÷ margin (4.4.3 ÷ 6.1.1)', prior_seen='No'),
    'ECS-NSCC-01': dict(
        name='Equity selloff → NSCC variation margin', version='v2', entity='NSCC', kind='quarterly',
        signal='vix_jump', signal_label='VIX ÷ 20-day average', test1='daily', test1_median_share=True,
        windows=[COVID, MEME, VOL24, UST25], test_var='vm_peak_to_avg', test_var_label='Peak ÷ average daily VM (6.7.1 ÷ 6.6.1)',
        changes_check=True, vuln='peak_payment_to_qlr', vuln_label='Peak payment obligation ÷ qualifying liquid resources (7.3.4 ÷ 7.1)',
        prior_seen='Yes (Oct 15 lag-1: rho 0.48 levels, 0.44 changes)', candidate=True,
        oct15={'levels': 0.48, 'changes': 0.44, 'lag': 1}),
    'ECS-NSCC-02': dict(
        name='Funding squeeze → NSCC variation margin', version='v2', entity='NSCC', kind='quarterly',
        signal='sofr_effr_adjusted', signal_label='SOFR−EFFR quarter-end adjusted, bp', test1='daily', test1_median_share=True,
        windows=[REPO19, COVID, UST25], test_var='vm_peak_to_avg', test_var_label='Peak ÷ average daily VM (6.7.1 ÷ 6.6.1)',
        changes_check=True, vuln='peak_payment_to_qlr', vuln_label='Peak payment obligation ÷ qualifying liquid resources (7.3.4 ÷ 7.1)',
        prior_seen='Yes (Oct 15 lag-1: rho 0.71 levels, 0.59 changes)', candidate=True,
        oct15={'levels': 0.71, 'changes': 0.59, 'lag': 1}),
    'ECS-NSCC-03': dict(
        name='Volume surge → NSCC settlement fails', version='v1', entity='NSCC', kind='event_weekly',
        signal='consolidated_shares', signal_label='US consolidated equity volume, shares (Cboe, all venues incl. TRFs)',
        test1='daily', test1_median_share=True, windows=[COVID, MEME, UST25],
        test_var='fail_value_usd', test_var_label='SEC CNS fails-to-deliver, weekly mean of daily Σ qty×price (USD)',
        vuln=None, vuln_label='vulnerability: no data (shock-only)', prior_seen='No'),
    'ECS-SET-01': dict(
        name='Shorter settlement cycle → NSCC and DTC fails', version='v2', entity='NSCC/DTC', kind='case_settlement',
        signal=None, vuln=None, vuln_label='vulnerability: no data (shock-only)', prior_seen='No'),
    'ECS-NSCC-04': dict(
        name='Broker distress → NSCC default management', version='v1', entity='NSCC', kind='case',
        signal='baa_widen20', signal_label='Baa−10Y 20-day widening, bp', test1='weekly', test1_median_share=False,
        windows=[MEME, SVB], vuln='top5_open_share', vuln_label='Top-5 share of open positions (PQD 18.2.2)',
        prior_seen='Yes for the signal'),
}

# Case evidence compiled 2026-10-16 from public sources; the chain owner verifies (never auto-passed).
CASES = {
    'FICC-GSD-03': {
        'milestones': [
            {'date': '2023-12-13', 'event': 'SEC adopts Treasury clearing rules (Rel. 2023-247)', 'past': True,
             'sources': ['https://www.sec.gov/news/press-release/2023-247']},
            {'date': '2025-02-25', 'event': 'SEC extends compliance dates by one year', 'past': True,
             'sources': ['https://marketsmedia.com/sec-extends-compliance-dates-for-treasury-clearing',
                         'https://www.arnoldporter.com/en/perspectives/advisories/2025/03/us-treasury-clearing-sec-extends-compliance-dates'],
             'note': 'secondary sources; primary SEC release to be confirmed by owner'},
            {'date': '2026-12-31', 'event': 'Cash compliance date (upcoming)', 'past': False, 'sources': ['as above']},
            {'date': '2027-06-30', 'event': 'Repo compliance date (upcoming)', 'past': False, 'sources': ['as above']},
        ],
        'supporting': [
            {'claim': 'Sponsored Service peak USD 1.7T (Sept 30, 2024) and USD 2.48T (June 30, 2025)',
             'sources': ['https://www.dtcc.com/news/2024/october/03/ficcs-government-securities-division-surpasses',
                         'https://www.dtcc.com/news/2025/july/02/ficc-successfully-processes']}],
    },
    'FICC-GSD-04': {'candidates': [{
        'event': 'Lehman Brothers Inc. bankruptcy, Sept 2008',
        'evidence': 'DTCC "closed out more than $500 billion of market participants\' exposure to the Lehman Brothers Inc. '
                    'bankruptcy"; Lehman was "among the five largest users of the government securities division"; DTCC '
                    '"expects no impact on its retained earnings or on market participants\' clearing fund deposits".',
        'sources': ['https://www.americanbanker.com/news/500b-of-lehman-exposure-closed-out (Oct 31, 2008)',
                    'https://finextra.com/pressarticle/24287/dtcc-closes-out-lehman-bankruptcy (DTCC press release reprint; HTTP 403 to automated fetch)'],
        'gaps': 'Secondary article does not name FICC/GSD as the closing-out entity; DTCC 2008 annual report download was '
                'BLOCKED (dtcc.com 404; sechistorical.org Cloudflare 1010). Owner to confirm FICC role from the annual report.'}]},
    'ECS-NSCC-04': {'candidates': [{
        'event': 'Meme-stock week, Jan 27–28, 2021',
        'evidence': 'SEC staff report p.32: "On January 27, 2021 ... NSCC made intraday margin calls from 36 clearing members '
                    'totaling $6.9 billion ... Of the $6.9 billion, $2.1 billion were intraday mark-to-market calls, while the '
                    'remaining $4.8 billion was a special ECP charge." NSCC "exercised its rules-based discretion to waive the '
                    'ECP charge for all members on January 28, 2021" and "removed this waiver on February 2, 2021".',
        'sources': ['https://www.sec.gov/files/staff-report-equity-options-market-struction-conditions-early-2021.pdf (p.32; local copy data/raw/case_evidence/SEC_staff_report_early_2021.pdf)'],
        'gaps': 'The report attributes the calls to unusual volatility in specific securities and to members\' excess risk vs '
                'capital; whether this is "member stress" (card wording) is the owner\'s call. Not a Baa-spread event.'}]},
    'ECS-SET-01': {
        'milestones': [
            {'date': '2023-02-15', 'event': 'SEC adopts T+1', 'sources': ['https://www.sec.gov/news/press-release/2023-29']},
            {'date': '2024-05-28', 'event': 'US T+1 go-live',
             'sources': ['https://www.dtcc.com/news/2024/september/12/sifma-ici-and-dtcc-release-t1-after-action-report']},
            {'date': '2026-06-28', 'event': 'NSCC 24x5 clearing go-live',
             'sources': ['https://www.dtcc.com/-/media/Files/pdf/2025/11/5/A9670.pdf (DTCC notice, planned date)',
                         'https://www.ftfnews.com/nscc-extends-clearing-hours-to-24x5-availability/'],
             'note': 'go-live date from trade press; DTCC confirmation to be checked'},
            {'date': None, 'event': 'T+0', 'sources': [], 'note': 'no adopted milestone found'},
        ],
        'fail_rate_points': [
            {'series': 'NSCC/CNS', 'period': 'May (historic avg, T+2)', 'value_pct': 2.01, 'side': 'before', 'milestone': '2024-05-28',
             'source': 'https://www.dtcc.com/dtcc-connection/articles/2024/august/26/what-insights-can-be-applied-to-other-markets'},
            {'series': 'NSCC/CNS', 'period': 'post T+1 (to Aug 2024)', 'value_pct': 2.30, 'side': 'after', 'milestone': '2024-05-28',
             'source': 'https://www.dtcc.com/dtcc-connection/articles/2024/august/26/what-insights-can-be-applied-to-other-markets'},
            {'series': 'NSCC/CNS', 'period': 'July 2024', 'value_pct': 2.12, 'side': 'after', 'milestone': '2024-05-28',
             'source': 'https://www.dtcc.com/news/2024/september/12/sifma-ici-and-dtcc-release-t1-after-action-report'},
            {'series': 'DTC non-CNS', 'period': 'post-T+1, period not stated in release', 'value_pct': 3.31, 'side': 'after', 'milestone': '2024-05-28',
             'source': 'https://www.dtcc.com/news/2024/september/12/sifma-ici-and-dtcc-release-t1-after-action-report'},
            {'series': 'NSCC', 'period': 'May 2024 (pre-T+1 baseline)', 'value_pct': 2.00, 'side': 'before', 'milestone': '2024-05-28',
             'source': 'DTCC Equities by the Numbers snapshot (repo: data_refresh_2026_10_14/data/ecs_itp_monthly_operations_snapshot.csv)'},
            {'series': 'DTC', 'period': 'May 2024 (pre-T+1 baseline)', 'value_pct': 2.83, 'side': 'before', 'milestone': '2024-05-28',
             'source': 'same snapshot'},
            {'series': 'NSCC', 'period': 'Aug 2026', 'value_pct': 2.21, 'side': 'after', 'milestone': '2026-06-28', 'source': 'same snapshot'},
            {'series': 'DTC', 'period': 'Aug 2026', 'value_pct': 3.18, 'side': 'after', 'milestone': '2026-06-28', 'source': 'same snapshot'},
        ],
    },
}

# ------------------------------------------------------------------ post-hoc v2 (TEST_SPEC.md §13; written after v1 results)
CHAINS['FICC-GSD-02.v2'] = dict(
    CHAINS['FICC-GSD-02'], version='v2 (post-hoc)', post_hoc=True, base='FICC-GSD-02', gcf='REPO-GCF_AR_T-F',
    test_var_label='OFR GCF (Treasury collateral, all tenors) − DVP overnight, bp (Final)',
    post_hoc_reason='Data coverage: GCF_AR_OO-F has 270 of 2,034 dates (none in Sept 2019); not chosen from results',
    prior_seen='Yes: v1 result (INCONCLUSIVE) seen before this change')
CHAINS['ECS-NSCC-04.v2'] = dict(
    CHAINS['ECS-NSCC-04'], version='v2 (post-hoc)', post_hoc=True, base='ECS-NSCC-04', kind='case_nomarket', signal=None,
    post_hoc_reason='v1 Test 1 failed: Baa is a broad credit index and Jan 2021 broker stress was broker-specific; '
                    'reclassified as without market indicator (rubric + case evidence); no new signal searched',
    prior_seen='Yes: v1 Test 1 FAIL seen before this change')

# ------------------------------------------------------------------ case evidence added 2026-10-16 (owner-supplied manual downloads)
CASES['FICC-GSD-03']['milestones'][1].update(
    event='SEC extends Treasury clearing compliance dates by one year (Release No. 34-102487)',
    sources=['https://www.govinfo.gov/content/pkg/FR-2025-03-04/html/2025-03351.htm (90 FR 11134-11139; local copy '
             'data/raw/Federal Register, Volume 90 Issue 41 (Tuesday, March 4, 2025).pdf)'],
    quote='"Specifically, the Commission is extending the compliance dates by one year, from December 31, 2025, to December 31, '
          '2026, for eligible cash market transactions, and from June 30, 2026, to June 30, 2027, for eligible repo transactions." '
          '(Summary, 90 FR 11134-11135; "Dated: February 25, 2025", 90 FR 11139). Effective date of the release: March 4, 2025.',
    note='primary source (owner-supplied)')

CASES['FICC-GSD-04'] = {'candidates': [{
    'event': 'Lehman Brothers Inc. bankruptcy, Sept 2008 (member credit event)',
    'source': 'DTCC press release "DTCC closes out Lehman bankruptcy", 30 Oct 2008 (Finextra reprint). Original URL '
              'https://finextra.com/pressarticle/24287/dtcc-closes-out-lehman-bankruptcy; automated fetch BLOCKED (Cloudflare 403); '
              'owner-supplied browser print data/raw/DTCC closes out Lehman bankruptcy.pdf',
    'passages': [
        {'page': 'PDF p.1', 'text': 'DTCC "announced today that it successfully closed out over $500 billion in market participants\' '
                                    'exposure from the Lehman Brothers, Inc. (Lehman) bankruptcy which occurred the week of Sept. 22." '
                                    'Dated 30 October 2008.'},
        {'page': 'PDF p.1', 'text': '"DTCC reports it does not expect there to be any impact to its retained earnings or to market '
                                    'participants\' clearing fund deposits as a result of closing out these pending trade obligations."'},
        {'page': 'PDF p.2', 'text': 'Lehman "ranked as a top three user of DTCC\'s Mortgage Backed Securities Division (MBSD); in the '
                                    'top five largest users of the Government Securities Division (GSD)".'},
        {'page': 'PDF p.2, "Mortgage-backed and Government Securities"',
         'text': '"Lehman\'s pending U.S. Government securities trades ran to $190 billion (gross positions) at the time of the '
                 'bankruptcy. FICC\'s GSD guarantees the settlement of these trades once it accepts them for clearing. In order to '
                 'make good on its guarantee, FICC had to close out the various positions, which ranged from repos to government '
                 'bonds. FICC successfully closed out these positions without impact on customers."'},
        {'page': 'PDF p.2, "Mortgage-backed and Government Securities"',
         'text': '"FICC\'s MBSD handled the liquidation of a gross position of $329 billion in par value of Lehman\'s book of '
                 '\'to be announced\' mortgage-backed securities trades ... FICC gradually sold the remaining net obligations into '
                 'the market with no losses assessed against MBSD members\' clearing deposits and with no observed market impact."'},
        {'page': 'PDF p.3', 'text': '"FICC and NSCC retained a third party adviser to assist in liquidating positions held by the '
                                    'clearing corporations."'},
    ],
    'gaps': 'DTCC 2008 annual report (sechistorical part 1) was not found in data/raw (MISSING); the press release alone covers '
            'the ~$500bn total and the Oct 30, 2008 announcement. The release says the bankruptcy "occurred the week of Sept. 22"; '
            'Lehman Brothers Holdings filed Sept 15 and the SIPA proceeding for Lehman Brothers Inc. began Sept 19, 2008, so the '
            'week reference is imprecise but not material to the case.',
    'proposed_verdict': 'PASS (proposed): FICC GSD closed out ~$190bn of Lehman\'s gross pending government securities trades to '
                        'honour its settlement guarantee, and MBSD liquidated a $329bn TBA book, after a member\'s bankruptcy. '
                        'This is default management triggered by a member credit event, which is the card rule. Owner to confirm.'}]}

CASES['ECS-NSCC-04'] = {'candidates': [{
    'event': 'Meme-stock week, Jan 27–28, 2021',
    'source': 'SEC Staff Report on Equity and Options Market Structure Conditions in Early 2021 (Oct 14, 2021), '
              'https://www.sec.gov/files/staff-report-equity-options-market-struction-conditions-early-2021.pdf; '
              'local copy data/raw/case_evidence/SEC_staff_report_early_2021.pdf',
    'passages': [
        {'page': 'PDF p.16 (printed p.15), §2', 'text': '"Pursuant to its existing rules, NSCC can also impose excess capital premium '
            '(\'ECP\') charges for members who present a degree of margin exposure for their cleared positions that exceed those '
            'members\' excess net capital."'},
        {'page': 'PDF p.32 (printed p.31), §3.5 Clearing Agency Margin and Capital Issues',
         'text': '"On January 27, 2021, in response to market activity during the trading session, NSCC made intraday margin calls '
                 'from 36 clearing members totaling $6.9 billion, bringing the total required margin across all members to $25.5 '
                 'billion. Of the $6.9 billion, $2.1 billion were intraday mark-to-market calls, while the remaining $4.8 billion '
                 'was a special ECP charge."'},
        {'page': 'PDF p.32 (printed p.31), §3.5', 'text': '"NSCC imposed this charge on 18 members, all of whom provided the '
            'additional margin. NSCC subjected one additional member to the special charge, but that member ultimately did not '
            'have to meet that charge after offsetting its exposure with a transfer from an affiliate."'},
        {'page': 'PDF p.32 (printed p.31), §3.5', 'text': '"In addition, several NSCC members were subject to an ECP charge based on '
            'the ratio of the excess risk in their portfolios relative to their capital. Because these members\' ratios of excess '
            'risk versus capital were not driven by individual clearing member actions, but by extreme volatility in individual '
            'cleared equities, NSCC exercised its rules-based discretion to waive the ECP charge for all members on January 28, '
            '2021. Absent this waiver, one retail broker-dealer would have had an additional ECP charge of more than double its '
            'margin requirement of $1.4 billion on January 28, 2021. NSCC removed this waiver on February 2, 2021"'},
        {'page': 'PDF p.33 (printed p.32), §3.5', 'text': '"some broker-dealers restricted activities in a limited number of '
            'individual stocks in reaction to margin calls and capital charges imposed by NSCC."'},
    ],
    'gaps': 'No member default and no default management: the case is about changed member requirements. The report attributes '
            'the trigger to "extreme volatility in individual cleared equities", not to a member\'s own actions.',
    'proposed_verdict': 'PASS (proposed) on the "changed a member\'s requirements" leg: NSCC raised requirements on specific members '
                        '($4.8bn special charge on 18 members, and capital-based ECP charges whose basis is members\' excess risk '
                        'relative to their capital), and members restricted trading in reaction. Caveat for the owner: the trigger was '
                        'security-level volatility interacting with member capital, which is narrower than "member stress" in the '
                        'usual credit sense. Owner to confirm.'}]}

CASES['ECS-NSCC-04.v2'] = {
    'milestones': [
        {'date': '2021-01-25', 'event': 'Meme-stock week (Jan 25–29, 2021)',
         'sources': ['https://www.sec.gov/files/staff-report-equity-options-market-struction-conditions-early-2021.pdf']},
        {'date': '2023-03-08', 'event': 'Bank stress (SVB failure, Mar 10, 2023)',
         'sources': ['https://www.fdic.gov/news/press-releases/2023/pr23016.html'],
         'note': 'source confirms the event; no public evidence found of an NSCC member-requirement change in this window'},
    ],
    'candidates': CASES['ECS-NSCC-04']['candidates']}

CASES['ECS-SET-01']['fail_rate_points'] = [
    p for p in CASES['ECS-SET-01']['fail_rate_points'] if 'After-Action' not in p['source'] and 'after-action' not in p['source']
] + [
    {'series': 'NSCC/CNS', 'period': 'first day after T+1 (May 29, 2024)', 'value_pct': 1.9, 'side': 'after', 'milestone': '2024-05-28',
     'source': 'T+1 After-Action Report (Sept 2024), PDF p.7 "Fail Rates Overview"'},
    {'series': 'NSCC/CNS', 'period': 'July 2024 average', 'value_pct': 2.12, 'side': 'after', 'milestone': '2024-05-28',
     'source': 'T+1 After-Action Report (Sept 2024), PDF p.7 "Fail Rates Overview"'},
    {'series': 'DTC non-CNS', 'period': 'July 2024 average', 'value_pct': 3.31, 'side': 'after', 'milestone': '2024-05-28',
     'source': 'T+1 After-Action Report (Sept 2024), PDF p.7 "Fail Rates Overview"'},
]
CASES['ECS-SET-01']['report_quotes'] = [
    {'page': 'PDF p.7, "Fail Rates Overview"', 'text': '"On the first day following transition to T+1, Continuous Net Settlement '
        '(CNS) fail rates decreased to 1.9% and remain low at around 2%. CNS Fail Rate: The average CNS Fail Rate for July 2024 was '
        '2.12%. This rate is consistent with T+2 settlement rates. DTC Non-CNS Fails Rate: The average non-CNS Fail Rate for July '
        '2024 was 3.31%. Again, this rate is consistent with T+2 settlement averages."'},
    {'page': 'PDF p.6, footnote 12', 'text': 'Source of the transition metrics: "DTCC Metrics: Daily Metrics". The report gives no '
        'numeric pre-T+1 fail rate; "before" points come from other DTCC publications.'},
]

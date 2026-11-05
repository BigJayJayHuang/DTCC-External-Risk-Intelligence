"""Unit tests for scoring v1.3-indicator. Fixtures only: no market data, register or PQD panel is read.

    python -m pytest -v validation/test_scoring_v1_3.py      (from Capstone_Project/)
"""
import hashlib, json, unittest
from pathlib import Path

import pandas as pd

from . import scoring as V12
from . import final16_vulnerability as F16
from . import scoring_v1_3 as S13
from .paths import PROJECT

WEEK, FRI, THU = '2026-10-26', pd.Timestamp('2026-10-30'), pd.Timestamp('2026-10-29')
CONF = V12.load_chain_conf()                       # static config (chain_confidence.json), read-only
CARDS = {c['card_id']: c for c in S13.load_cards(CONF)}
FULL = {s: FRI for s in ['SOFR', 'EFFR', 'DGS10', 'BAA10Y', 'VIXCLS', 'CBOE_CONSOLIDATED']} | {'MORTGAGE30US': THU}
NO_EVENT = {'S': 1, 'method': 'rubric v1.2', 'reason': 'no active event', 'events': [], 'active_events': 0}


def mkt(S, peak=1.0, pct=0.5):
    return {'S': S, 'method': 'percentile', 'weekly_peak': peak, 'percentile': pct, 'prior_weeks': 300}


def event(S, eid='EV9001', needs_review=False, card_ids=('FICC-GSD-03',), signed_off_by=None):
    e = {'event_id': eid, 'title': 'fixture event', 'S': S, 'certainty': 2, 'reach': 2, 'timing': 1, 'effect_date': '2026-12-31',
         'needs_review': needs_review, 'review_reasons': [], 'card_ids': list(card_ids), 'outlet': 'SEC', 'source_tier': 'regulator',
         'source_urls': ['https://example.invalid/rule']}
    if signed_off_by:
        e['signed_off_by'] = signed_off_by
    return {'S': S, 'method': 'rubric v1.2', 'events': [e], 'driving_event_ids': [eid], 'needs_review': needs_review,
            'rubric_version': 'event-rubric-v1.2', 'active_events': 1}


def vrec(V, tier='pqd', quarter='2026Q2'):
    return {'V': V, 'V_base': V, 'v_source_tier': tier, 'quarter': quarter, 'available_date': '2026-09-01',
            'vulnerability_metric': 'fixture_metric', 'history_quality': 'ok', 'caveats': []}


def days(peak, n=5):
    """Fixture week of daily values whose maximum is the weekly peak."""
    return {'daily_values': [{'date': str((pd.Timestamp(WEEK) + pd.Timedelta(days=i)).date()), 'value': peak * (0.5 + 0.1 * i)}
                             for i in range(n - 1)] + [{'date': str(FRI.date()), 'value': peak}], 'daily_inputs': {}}


def run(card_id, market=None, ev=NO_EVENT, V=3, last=FULL, check=None, releases=None, daily=None):
    card = CARDS[card_id]
    cov = S13.coverage([m['field'] for m in card['market_chains']], last, FRI, releases)
    if daily is None:   # consistent fixture daily values for every market chain
        daily = {c: days(r['weekly_peak']) for c, r in (market or {}).items() if r.get('weekly_peak') is not None}
    return S13.card_week(card, WEEK, market_recs=market or {}, cov=cov, ev=ev, v=vrec(V), check=check or {}, daily=daily)


class ReuseV12(unittest.TestCase):
    def test_imports_are_the_v12_and_final16_functions(self):
        self.assertIs(S13.percentile_scores, V12.percentile_scores)
        self.assertIs(S13.scoring_signal, V12.scoring_signal)
        self.assertIs(S13.weekly_peaks, V12.weekly_peaks)
        self.assertIs(S13.get_v, F16.get_v)


class Status(unittest.TestCase):
    def test_market_only_card(self):
        r = run('FICC-GSD-01', market={'FICC-GSD-01': mkt(3, peak=7.0, pct=0.55)}, V=1)
        self.assertEqual((r['status'], r['S'], r['S_source'], r['S_market'], r['S_event']), ('scored', 3, 'market', 3, None))
        self.assertEqual(r['signal'], {'name': 'ust10_abs_change', 'description': CONF['FICC-GSD-01']['signal']['description'],
                                       'chain_id': 'FICC-GSD-01', 'value': 7.0, 'percentile': 0.55, 'prior_weeks': 300,
                                       'method': 'percentile'})
        self.assertEqual((r['severity'], r['show_on_main'], r['needs_human_signoff']), (3, False, False))

    def test_event_only_card_without_active_event_is_news_not_scanned(self):
        r = run('FICC-GSD-03', V=3)
        self.assertEqual((r['status'], r['S'], r['S_source'], r['signal']), ('news_not_scanned', None, None, None))
        self.assertEqual((r['V'], r['severity'], r['show_on_main'], r['needs_human_signoff']), (3, None, False, False))

    def test_event_only_card_with_active_register_event(self):
        r = run('FICC-GSD-03', ev=event(4), V=3)
        self.assertEqual((r['status'], r['S'], r['S_source'], r['S_event']), ('scored', 4, 'event_manual', 4))
        self.assertEqual(r['event_manual']['driving_event_ids'], ['EV9001'])
        self.assertEqual((r['severity'], r['show_on_main'], r['needs_human_signoff']), (12, True, True))

    def test_new_card_without_chain_test(self):
        r = run('XE-CYBER', V=5)
        self.assertEqual(r['status'], 'news_not_scanned')
        self.assertEqual(r['chain_confidence'], {'level': 'Low', 'rule': 'untested', 'chain_id': None, 'chains': {}})

    def test_every_record_has_news_coverage(self):
        for cid in CARDS:
            self.assertEqual(run(cid)['news_coverage'], 'manual_register_only')


class MaxRule(unittest.TestCase):
    def test_event_above_market(self):
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(2)}, ev=event(4), V=4)
        self.assertEqual((r['S'], r['S_source'], r['S_market'], r['S_event']), (4, 'event_manual', 2, 4))

    def test_tie(self):
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4)}, ev=event(4), V=4)
        self.assertEqual((r['S'], r['S_source']), (4, 'market+event_manual'))

    def test_market_above_event(self):
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(5)}, ev=event(3), V=4)
        self.assertEqual((r['S'], r['S_source']), (5, 'market'))

    def test_multi_chain_card_takes_max_chain(self):
        r = run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(2), 'ECS-NSCC-02': mkt(5, peak=9.0)}, V=3)
        self.assertEqual((r['S'], r['signal']['chain_id'], r['signal']['name']), (5, 'ECS-NSCC-02', 'sofr_effr_adjusted'))

    def test_insufficient_history_without_event_is_incomplete(self):
        r = run('FICC-GSD-01', market={'FICC-GSD-01': {'S': None, 'reason': 'insufficient history (50 < 104 prior weeks)'}})
        self.assertEqual((r['status'], r['S']), ('data_incomplete', None))


class DataGuard(unittest.TestCase):
    def test_daily_series_must_reach_friday(self):
        last = FULL | {'VIXCLS': THU}
        r = run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(5), 'ECS-NSCC-02': mkt(2)}, last=last)
        self.assertEqual((r['status'], r['S'], r['S_market'], r['signal'], r['severity']), ('data_incomplete', None, None, None, None))
        self.assertIn('VIXCLS last 2026-10-29 < required 2026-10-30', r['status_reason'])
        self.assertTrue(all(c['S'] is None and c['weekly_peak'] is None for c in r['market_chains']))
        self.assertFalse(r['data_coverage']['VIXCLS']['ok'])
        self.assertEqual(r['chain_confidence']['rule'], 'lowest_tested_chain (S null)')

    def test_incomplete_market_data_with_active_event_scores_from_event(self):
        last = FULL | {'VIXCLS': THU}
        r = run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(5), 'ECS-NSCC-02': mkt(2)}, last=last,
                ev=event(4, card_ids=['ECS-NSCC-02']), V=3)
        self.assertEqual((r['status'], r['status_reason'], r['S'], r['S_source'], r['S_market'], r['S_event'], r['signal']),
                         ('scored', 'market_data_incomplete', 4, 'event_manual', None, 4, None))
        self.assertEqual((r['severity'], r['show_on_main'], r['needs_human_signoff']), (12, True, True))
        self.assertFalse(r['data_coverage']['VIXCLS']['ok'])
        self.assertEqual((r['chain_confidence']['chain_id'], r['chain_confidence']['rule']), ('ECS-NSCC-02', 'driving_event_chain'))

    def test_weekly_series_holiday_release_counts(self):
        tg_fri = pd.Timestamp('2026-11-27')                       # Thanksgiving week: Thu 2026-11-26 holiday
        daily = {s: tg_fri for s in ['DGS10']}
        moved = S13.coverage(['mbs_spread_abs_wchg'], daily, tg_fri, {'MORTGAGE30US': ['2026-11-19', '2026-11-25']})
        self.assertEqual(moved['MORTGAGE30US'], {'last_date': '2026-11-25', 'required_date': '2026-11-25', 'ok': True})
        pending = S13.coverage(['mbs_spread_abs_wchg'], daily, tg_fri, {'MORTGAGE30US': ['2026-11-12', '2026-11-19']})
        self.assertEqual(pending['MORTGAGE30US'], {'last_date': '2026-11-19', 'required_date': '2026-11-26', 'ok': False})
        r = run('FICC-MBSD-01', market={'FICC-MBSD-01': mkt(3)}, releases={'MORTGAGE30US': ['2026-10-22', '2026-10-28']})
        self.assertEqual((r['status'], r['data_coverage']['MORTGAGE30US']['required_date']), ('scored', '2026-10-28'))

    def test_mortgage_needs_its_thursday_survey(self):
        ok = S13.coverage(['mbs_spread_abs_wchg'], FULL, FRI)
        self.assertEqual(ok['MORTGAGE30US']['required_date'], '2026-10-29')
        self.assertTrue(all(c['ok'] for c in ok.values()))
        late = S13.coverage(['mbs_spread_abs_wchg'], FULL | {'MORTGAGE30US': pd.Timestamp('2026-10-22')}, FRI)
        self.assertFalse(late['MORTGAGE30US']['ok'])
        no_dgs10 = S13.coverage(['mbs_spread_abs_wchg'], FULL | {'DGS10': THU}, FRI)   # no forward fill of the yield
        self.assertFalse(no_dgs10['DGS10']['ok'])

    def test_missing_series_counts_as_incomplete(self):
        cov = S13.coverage(['consolidated_shares'], {}, FRI)
        self.assertEqual(cov['CBOE_CONSOLIDATED'], {'last_date': None, 'required_date': '2026-10-30', 'ok': False})

    def test_event_only_card_has_no_guard(self):
        self.assertEqual(run('ECS-SET-01', last={})['status'], 'news_not_scanned')

    def test_week_must_be_a_monday(self):
        with self.assertRaises(ValueError):
            S13.week_dates('2026-10-30')


class CrossEntity(unittest.TestCase):
    def test_xe_cards_split_into_ficc_and_ecs(self):
        for cid in ['XE-MEMBER', 'XE-DISRUPT', 'XE-SETTLEBANK', 'XE-CYBER']:
            card = CARDS[cid]
            recs = S13.split_lines(run(cid, market={'FICC-GSD-04': mkt(3)} if cid == 'XE-MEMBER' else None, V=2), card)
            self.assertEqual([r['record_id'] for r in recs], [cid.lower() + '-ficc', cid.lower() + '-ecs'])
            self.assertEqual([r['business_line'] for r in recs], ['FICC', 'ECS'])
            strip = lambda r: {k: v for k, v in r.items() if k not in ('record_id', 'business_line', 'sub_line')}
            self.assertEqual(strip(recs[0]), strip(recs[1]))
            self.assertTrue(all(r['cross_entity'] for r in recs))

    def test_entities_from_components(self):
        self.assertEqual(CARDS['XE-MEMBER']['entities'], ['GSD', 'NSCC', 'MBSD'])
        self.assertEqual(CARDS['XE-DISRUPT']['entities'], ['MBSD', 'DTC'])
        self.assertEqual(CARDS['XE-SETTLEBANK']['entities'], ['NSCC', 'GSD', 'DTC'])

    def test_single_line_card(self):
        recs = S13.split_lines(run('FICC-GSD-01', market={'FICC-GSD-01': mkt(3)}), CARDS['FICC-GSD-01'])
        self.assertEqual([(r['record_id'], r['business_line'], r['cross_entity']) for r in recs], [('ficc-gsd-01', 'FICC', False)])
        self.assertEqual(sum(len(c['lines']) for c in CARDS.values()), 20)
        self.assertEqual(sum(c['cross_entity'] for c in CARDS.values()), 4)

    def test_line_table_is_checked(self):
        table = S13.load_line_table()
        ids = list(CARDS)
        self.assertEqual(S13.check_line_table(table, ids), [])
        bad = {**table, 'XE-CYBER': [dict(table['XE-CYBER'][0], id_suffix=''), table['XE-CYBER'][1]],
               'ECS-DTC-01': [dict(table['ECS-DTC-01'][0], business_line='DTC')]}
        errs = S13.check_line_table(bad, ids)
        self.assertTrue(any('XE-CYBER' in e for e in errs) and any('ECS-DTC-01' in e for e in errs))


class SeverityAndSignoff(unittest.TestCase):
    def test_show_on_main_threshold(self):
        self.assertEqual([(r['severity'], r['show_on_main']) for r in
                          (run('FICC-GSD-01', market={'FICC-GSD-01': mkt(2)}, V=3), run('FICC-GSD-01', market={'FICC-GSD-01': mkt(5)}, V=1))],
                         [(6, True), (5, False)])

    def test_null_V_gives_null_severity(self):
        r = run('FICC-GSD-01', market={'FICC-GSD-01': mkt(4)}, V=None)
        self.assertEqual((r['status'], r['S'], r['severity'], r['show_on_main']), ('scored', 4, None, False))

    def test_signoff_only_for_unsigned_event_S_ge_4(self):           # Amendment A1
        self.assertFalse(run('FICC-GSD-01', market={'FICC-GSD-01': mkt(5)}, V=5)['needs_human_signoff'])     # market S 5
        self.assertTrue(run('FICC-GSD-03', ev=event(4))['needs_human_signoff'])                                # event S 4, unsigned
        self.assertFalse(run('FICC-GSD-03', ev=event(3))['needs_human_signoff'])                               # event S 3
        signed = run('FICC-GSD-03', ev=event(4, signed_off_by='Wenqi Cai 2026-11-05T04:45Z'))
        self.assertEqual((signed['S'], signed['needs_human_signoff']), (4, False))                              # sign-off clears it
        self.assertEqual(signed['event_manual']['events'][0]['signed_off_by'], 'Wenqi Cai 2026-11-05T04:45Z')
        self.assertFalse(run('FICC-GSD-02', market={'FICC-GSD-02': mkt(5)}, ev=event(4), V=4)['needs_human_signoff'])  # market wins
        self.assertTrue(run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4)}, ev=event(4), V=4)['needs_human_signoff'])   # tie
        self.assertTrue(run('FICC-GSD-02', market={'FICC-GSD-02': mkt(2)}, ev=event(4), V=4)['needs_human_signoff'])   # event wins

    def test_event_provenance_on_record(self):                        # Amendment A4
        e = run('FICC-GSD-03', ev=event(4))['event_manual']['events'][0]
        self.assertEqual((e['outlet'], e['source_tier'], e['source_urls']), ('SEC', 'regulator', ['https://example.invalid/rule']))


class DailyValues(unittest.TestCase):                                   # Amendment A2
    def test_market_S_ge_4_carries_daily_values(self):
        info = days(9.0) | {'daily_inputs': {'SOFR': [{'date': '2026-10-30', 'value': 4.0}]}}
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4, peak=9.0)}, daily={'FICC-GSD-02': info})
        self.assertEqual(r['signal']['daily_values'], info['daily_values'])
        self.assertEqual(r['signal']['daily_inputs'], info['daily_inputs'])
        self.assertTrue(r['signal']['peak_check'])

    def test_market_S_below_4_has_no_daily_values(self):
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(3, peak=9.0)})
        self.assertNotIn('daily_values', r['signal'])

    def test_market_S_ge_4_kept_when_event_wins(self):
        r = run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4, peak=9.0)}, ev=event(5), V=4)
        self.assertEqual((r['S_source'], r['signal']['peak_check']), ('event_manual', True))

    def test_inconsistent_daily_values_stop_the_run(self):
        with self.assertRaises(ValueError):
            run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4, peak=9.0)}, daily={'FICC-GSD-02': days(8.0)})
        with self.assertRaises(ValueError):
            run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4, peak=9.0)}, daily={})

    def test_ratio_denominator(self):
        info = days(2_000.0) | {'ratio_denominator': 1_000.0}
        self.assertTrue(S13.peak_check(2.0, info))
        self.assertFalse(S13.peak_check(2000.0, info))


class SharedSignal(unittest.TestCase):                                  # Amendment A3 / B
    def week(self):
        return [run('FICC-GSD-02', market={'FICC-GSD-02': mkt(5)}, V=4),
                run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(3), 'ECS-NSCC-02': mkt(5)}),
                run('FICC-GSD-01', market={'FICC-GSD-01': mkt(3)}),
                run('FICC-MBSD-01', market={'FICC-MBSD-01': mkt(4)}),
                run('XE-MEMBER', market={'FICC-GSD-04': mkt(4)}),
                run('FICC-GSD-03', ev=event(4)),
                run('XE-CYBER')]

    def test_shared_signal_field(self):
        recs = {r['card_id']: r for r in S13.assign_shared(self.week())}
        self.assertEqual(recs['FICC-GSD-02']['shared_signal'], ['ECS-NSCC-LIQ'])
        self.assertEqual(recs['ECS-NSCC-LIQ']['shared_signal'], ['FICC-GSD-02'])
        self.assertEqual(recs['ECS-NSCC-LIQ']['shared_signal_fields'], {'FICC-GSD-02': ['sofr_effr_adjusted']})
        self.assertNotIn('shared_signal_series', recs['ECS-NSCC-LIQ'])
        for cid in ['XE-MEMBER', 'FICC-GSD-03', 'XE-CYBER']:
            self.assertEqual(recs[cid]['shared_signal'], [], cid)

    def test_shared_raw_input_does_not_count(self):                    # Amendment B2: DGS10 feeds two different fields
        recs = {r['card_id']: r for r in S13.assign_shared(self.week())}
        self.assertEqual((recs['FICC-GSD-01']['shared_signal'], recs['FICC-MBSD-01']['shared_signal']), ([], []))
        self.assertEqual((recs['FICC-GSD-01']['shared_signal_fields'], recs['FICC-MBSD-01']['shared_signal_fields']), ({}, {}))

    def test_tied_chains_both_count(self):                              # both NSCC chains at S_market
        recs = {r['card_id']: r for r in S13.assign_shared(
            [run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4)}, V=4),
             run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(4), 'ECS-NSCC-02': mkt(4)})])}
        self.assertEqual(recs['FICC-GSD-02']['shared_signal_fields'], {'ECS-NSCC-LIQ': ['sofr_effr_adjusted']})

    def test_only_chains_that_set_S(self):
        recs = {r['card_id']: r for r in S13.assign_shared(
            [run('FICC-GSD-02', market={'FICC-GSD-02': mkt(4)}, V=4),
             run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(5), 'ECS-NSCC-02': mkt(4)})])}   # NSCC S from VIX, not SOFR
        self.assertEqual((recs['FICC-GSD-02']['shared_signal'], recs['ECS-NSCC-LIQ']['shared_signal']), ([], []))

    def test_event_set_S_does_not_share(self):
        recs = S13.assign_shared([run('FICC-GSD-02', market={'FICC-GSD-02': mkt(2)}, ev=event(4), V=4),
                                  run('ECS-NSCC-LIQ', market={'ECS-NSCC-01': mkt(2), 'ECS-NSCC-02': mkt(2)})])
        self.assertEqual([r['shared_signal'] for r in recs], [[], []])   # GSD-02's S comes from the event, not SOFR/EFFR

    def test_cross_entity_records_do_not_list_each_other(self):
        base = S13.assign_shared([run('XE-MEMBER', market={'FICC-GSD-04': mkt(4)})])[0]
        recs = S13.split_lines(base, CARDS['XE-MEMBER'])
        self.assertEqual([r['shared_signal'] for r in recs], [[], []])

    def test_chain_confidence_from_signal_chain(self):
        r = run('XE-MEMBER', market={'FICC-GSD-04': mkt(5)}, V=1)
        cc = r['chain_confidence']
        self.assertEqual(cc['chains'], {'FICC-GSD-04': 'Medium', 'ECS-NSCC-04': 'Low'})
        self.assertEqual((cc['level'], cc['rule'], cc['chain_id'], r['severity']), ('Medium', 'signal_chain', 'FICC-GSD-04', 5))
        tie = run('XE-MEMBER', market={'FICC-GSD-04': mkt(4)}, ev=event(4, card_ids=['ECS-NSCC-04']), V=1)
        self.assertEqual((tie['S_source'], tie['chain_confidence']['chain_id']), ('market+event_manual', 'FICC-GSD-04'))

    def test_chain_confidence_from_driving_event_chain(self):
        r = run('XE-MEMBER', market={'FICC-GSD-04': mkt(2)}, ev=event(4, card_ids=['ECS-NSCC-04']), V=1)
        cc = r['chain_confidence']
        self.assertEqual((r['S_source'], cc['level'], cc['rule'], cc['chain_id']), ('event_manual', 'Low', 'driving_event_chain', 'ECS-NSCC-04'))
        g3 = run('FICC-GSD-03', ev=event(4))['chain_confidence']
        self.assertEqual((g3['level'], g3['chain_id']), ('Low', 'FICC-GSD-03'))
        unmapped = run('XE-MEMBER', market={'FICC-GSD-04': mkt(2)}, ev=event(4, card_ids=['XE-MEMBER']), V=1)['chain_confidence']
        self.assertEqual((unmapped['level'], unmapped['chain_id'], unmapped['rule']),
                         ('Low', 'ECS-NSCC-04', 'lowest_tested_chain (driving event not on a tested chain)'))

    def test_chain_confidence_when_S_is_null(self):
        r = run('FICC-GSD-03', V=3)       # news_not_scanned, tested chain FICC-GSD-03 (Low)
        self.assertEqual((r['chain_confidence']['level'], r['chain_confidence']['rule']), ('Low', 'lowest_tested_chain (S null)'))
        x = run('XE-MEMBER', last=FULL | {'BAA10Y': THU}, V=1)
        self.assertEqual((x['status'], x['chain_confidence']['level'], x['chain_confidence']['chain_id']), ('data_incomplete', 'Low', 'ECS-NSCC-04'))
        m = run('FICC-MBSD-01', last=FULL | {'DGS10': THU})
        self.assertEqual(m['chain_confidence']['level'], 'Medium')

    def test_v_fields(self):
        f = S13.v_fields({**vrec(5, 'public_proxy'), 'history_quality': 'low (<8 quarters)', 'V_override_reason': None},
                         {'driver': 'NVD published CVEs', 'flag_corr_gt_0_7': True, 'flag_v5_share_gt_0_5': True,
                          'proxy_quality': 'weak proxy', 'detrended': True})
        self.assertEqual((f['V'], f['V_tier'], f['V_driver'], f['V_quarter']), (5, 'public_proxy', 'NVD published CVEs', '2026Q2'))
        self.assertEqual(f['V_flags'], ['corr_gt_0.7_with_S', 'V5_share_gt_0.5', 'history_lt_8_quarters', 'weak_proxy', 'detrended'])


class EventMapping(unittest.TestCase):
    def test_old_ids_map_to_final16(self):
        m = S13.old_to_new(json.loads(S13.REGISTRY.read_text()))
        self.assertEqual({k: m[k] for k in ['FICC-GSD-04', 'ECS-NSCC-04', 'NSCC liquidity', 'ECS-NSCC-01', 'FICC-GSD-09', 'ECS-SET-01']},
                         {'FICC-GSD-04': 'XE-MEMBER', 'ECS-NSCC-04': 'XE-MEMBER', 'NSCC liquidity': 'ECS-NSCC-LIQ',
                          'ECS-NSCC-01': 'ECS-NSCC-LIQ', 'FICC-GSD-09': 'FICC-GSD-01', 'ECS-SET-01': 'ECS-SET-01'})
        self.assertEqual(CARDS['XE-MEMBER']['legacy_v12_cards'], ['FICC-GSD-04', 'ECS-NSCC-04'])

    def test_card_events_uses_v12_ranking_order(self):
        m = S13.old_to_new(json.loads(S13.REGISTRY.read_text()))
        ranked = [{'event_id': 'A', 'S': 4, 'card_ids': ['ECS-NSCC-04'], 'needs_review': True},
                  {'event_id': 'B', 'S': 2, 'card_ids': ['FICC-GSD-04'], 'needs_review': False},
                  {'event_id': 'C', 'S': 5, 'card_ids': ['ECS-SET-01'], 'needs_review': False}]
        ev = S13.card_events(ranked, 'XE-MEMBER', m)
        self.assertEqual((ev['S'], ev['driving_event_ids'], ev['active_events'], ev['needs_review']), (4, ['A'], 2, True))
        self.assertEqual(S13.card_events(ranked, 'FICC-GSD-03', m)['active_events'], 0)


class Gate(unittest.TestCase):
    def test_score_refused_while_spec_is_draft(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft, approved = tmp / 'draft.md', tmp / 'approved.md'
            draft.write_text('# spec\n\nStatus: **DRAFT** — not approved. Change to `Status: **APPROVED** (...)`.\n')
            approved.write_text('# spec\n\nStatus: **APPROVED** (Someone, 2026-11-05T00:00Z)\n')
            self.assertFalse(S13.spec_approved(draft))
            self.assertTrue(S13.spec_approved(approved))
            with mock.patch.object(S13, 'SPEC', draft), mock.patch.object(S13, 'OUT', tmp / 'out'):
                with self.assertRaises(SystemExit):
                    S13.main(['score', '--week', WEEK])
            self.assertFalse((tmp / 'out').exists())


class ProtectedFiles(unittest.TestCase):
    def test_protected_files_unchanged(self):
        manifest = json.loads((S13.OUT / 'protected_files.json').read_text())['files']
        for f, h in manifest.items():
            self.assertEqual(hashlib.sha256((PROJECT / f).read_bytes()).hexdigest(), h, f)
        weekly = {str(p.relative_to(PROJECT)) for p in (PROJECT / 'results' / 'scoring').rglob('weekly_scores*')
                  if 'v1.3_indicator' not in p.parts}
        self.assertEqual(weekly, {f for f in manifest if 'weekly_scores' in f})


if __name__ == '__main__':
    unittest.main()

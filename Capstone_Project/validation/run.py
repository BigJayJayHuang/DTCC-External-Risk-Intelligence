"""Run the frozen chain tests (TEST_SPEC.md v1).

    python -m validation.run                    # all core chains + summary.csv + REPORT.md
    python -m validation.run --chain FICC-GSD-01

All chains are always computed so the Benjamini–Hochberg family is the same whichever
chain is requested; --chain only limits which per-chain files are written.
"""
import argparse, datetime as dt, json, math

import numpy as np
import pandas as pd

from . import data as D, stats as S, checks
from .chains import CHAINS, CASES
from .paths import RESULTS, FIGURES

SIGNALS = {
    'ust10_abs_change': D.ust10_abs_change, 'sofr_effr_adjusted': D.sofr_effr_adjusted, 'baa_widen20': D.baa_widen20,
    'vix_jump': D.vix_jump, 'mbs_spread_abs_wchg': D.mbs_spread_abs_weekly_change, 'consolidated_shares': D.consolidated_volume,
}
T1_DATE = pd.Timestamp('2024-05-28')
SPONSORED_CLEAN_START = '2021-10-12'


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o.date() if isinstance(o, pd.Timestamp) else o)
    return o


def pqd_series(entity, col):
    p = D.pqd_panel()
    return p[p.entity == entity].set_index('quarter')[col]


# ------------------------------------------------------------------ Test 1
def run_test1(c):
    s = SIGNALS[c['signal']]()
    mode = c['test1']
    if mode == 'daily':
        alerts = S.daily_alerts(s)
    else:
        alerts = S.weekly_alerts(s, already_weekly=(mode == 'weekly_native'))
    res = S.test1(alerts, c['windows'], weekly=(mode != 'daily'), use_median_share=c['test1_median_share'])
    return res, alerts


# ------------------------------------------------------------------ Test 2 variants
def test2_quarterly(c):
    s = SIGNALS[c['signal']]()
    weekly = c['signal'] == 'mbs_spread_abs_wchg'
    x = S.quarterly_max(s, 10 if weekly else 45)
    y = pqd_series(c['entity'], c['test_var'])
    out = {'method': 'Spearman, quarterly max signal vs same-quarter test variable; 4-quarter block bootstrap (seed %d)' % S.SEED}
    out['primary_levels'] = S.spearman_block(x, y, 'lag 0, levels')
    out['secondary_lag1_levels'] = S.spearman_block(x, S.shift_quarter(y, 1), 'lag 1 (signal t vs test variable t+1), levels')
    prim = [out['primary_levels']]
    if c.get('changes_check'):
        dx, dy = S.consecutive_diff(x), S.consecutive_diff(y)
        out['primary_changes'] = S.spearman_block(dx, dy, 'lag 0, QoQ changes')
        out['secondary_lag1_changes'] = S.spearman_block(dx, S.shift_quarter(dy, 1), 'lag 1, QoQ changes')
        prim.append(out['primary_changes'])
        if out['primary_levels']['status'] == 'PASS' and out['primary_changes']['status'] != 'PASS':
            out['flag'] = 'possible shared trend'
    statuses = [p['status'] for p in prim]
    out['result'] = ('WRONG_DIRECTION' if 'WRONG_DIRECTION' in statuses else 'PASS' if all(s_ == 'PASS' for s_ in statuses)
                     else 'INCONCLUSIVE')
    out['primary_p'] = [(p['label'], p['p']) for p in prim]
    return out, {'x': x, 'y': y}


def test2_event_daily(c):
    shock_src = S.daily_alerts(D.sofr_effr_adjusted())
    y = D.ofr_spread(c.get('gcf', 'REPO-GCF_AR_OO-F'))
    shock = shock_src.alert.reindex(y.index)
    idx = y.index
    me = pd.Series((idx == (idx + pd.offsets.BMonthEnd(0))).astype(float), index=idx, name='month_end')
    qe = pd.Series((idx == (idx + pd.offsets.BQuarterEnd(0))).astype(float), index=idx, name='quarter_end')
    T = int(pd.concat([y, shock], axis=1).dropna().shape[0])
    res = S.event_study(y, shock, [me, qe], S.nw_lags(T), 'shock day vs other days, same day')
    out = {'method': 'OLS y ~ shock_day + month_end + quarter_end, Newey–West HAC', 'primary': res,
           'result': res['status'], 'primary_p': [(res['label'], res['p'])]}
    return out, {'y': y, 'shock': shock}


def test2_event_weekly(c):
    vol_alerts = S.weekly_alerts(D.consolidated_volume())
    shock = vol_alerts.alert
    ftd = D.sec_ftd_daily().fail_value_usd
    y = ftd.resample('W-FRI').mean()
    y = y[ftd.resample('W-FRI').count() > 0]
    weeks = y.index.union(shock.dropna().index)
    bme = pd.date_range('2017-12-01', '2027-01-31', freq='BME')
    bqe = pd.date_range('2017-12-01', '2027-01-31', freq='BQE')
    wk = lambda d: d + pd.to_timedelta((4 - d.dayofweek) % 7, unit='D')
    me = pd.Series(weeks.isin(wk(bme)).astype(float), index=weeks, name='month_end_week')
    qe = pd.Series(weeks.isin(wk(bqe)).astype(float), index=weeks, name='quarter_end_week')
    t1 = pd.Series((weeks >= T1_DATE).astype(float), index=weeks, name='t1_regime')
    prim = S.event_study(y, shock, [me, qe, t1], 4, 'shock week, same week')
    sec = S.event_study(y.shift(-1), shock, [me, qe, t1], 4, 'shock week vs next week fails (secondary)')
    out = {'method': 'OLS weekly mean fail value ~ shock_week + month_end_week + quarter_end_week + T+1 regime, Newey–West HAC 4 lags',
           'primary': prim, 'secondary_next_week': sec, 'result': prim['status'], 'primary_p': [(prim['label'], prim['p'])]}
    return out, {'y': y, 'shock': shock}


def test2_sponsored(c):
    sp = D.sponsored_total()
    rows = []
    for m in CASES['FICC-GSD-03']['milestones']:
        if not m['past']:
            continue
        t = pd.Timestamp(m['date'])
        before, after = sp[sp.index < t].tail(60), sp[sp.index >= t].head(60)
        rows.append({'milestone': m['date'], 'event': m['event'], 'before_window': f'{before.index.min().date()}–{before.index.max().date()}',
                     'after_window': f'{after.index.min().date()}–{after.index.max().date()}', 'n_before': len(before), 'n_after': len(after),
                     'mean_before_usd_bn': before.mean() / 1e9, 'mean_after_usd_bn': after.mean() / 1e9,
                     'change_pct': after.mean() / before.mean() - 1})
    # Audit: every 60-obs before/after split over the whole sample (overlapping windows; descriptive only)
    def splits(x):
        v = x.values
        return pd.Series([v[i:i + 60].mean() / v[i - 60:i].mean() - 1 for i in range(60, len(v) - 59)], index=x.index[60:len(v) - 59])
    raw = splits(sp)
    # Before 2021-10-12 the series is ~$0–0.5bn/day, then jumps ~500x overnight: source coverage start, not activity.
    ch = splits(sp[sp.index >= SPONSORED_CLEAN_START])
    dist = {'n_splits': int(len(ch)), 'first_split': str(ch.index.min().date()), 'last_split': str(ch.index.max().date()),
            'median': float(ch.median()), 'p75': float(ch.quantile(.75)), 'p90': float(ch.quantile(.90)),
            'share_negative': float((ch < 0).mean()), 'series_start_used': SPONSORED_CLEAN_START,
            'uncleaned_full_series': {'n_splits': int(len(raw)), 'median': float(raw.median()), 'p75': float(raw.quantile(.75)),
                                      'p90': float(raw.quantile(.90))},
            'note': 'overlapping windows on an upward-trending series; descriptive only, no pass/fail. Days before 2021-10-12 '
                    '(12 zero days in Aug 2021, then ~$0.05-0.5bn/day) excluded as a source-coverage artefact.'}
    for row in rows:
        row['percentile_in_sample'] = float((ch <= row['change_pct']).mean())
    return {'method': 'Descriptive (D8): mean daily Sponsored TOTAL_AMOUNT, 60 business days before vs after each past milestone',
            'table': rows, 'all_splits_distribution': dist, 'result': 'DESCRIPTIVE — owner decides', 'primary_p': []}, {'sp': sp, 'ch': ch}


# ------------------------------------------------------------------ scoring info + confidence
def vulnerability(c):
    if not c.get('vuln'):
        return {'variable': c['vuln_label'], 'status': 'no data (shock-only rule)'}
    s = pqd_series(c['entity'], c['vuln']).dropna()
    latest_q, latest = s.index[-1], s.iloc[-1]
    pct = float((s <= latest).mean())
    out = {'variable': c['vuln_label'], 'field': c['vuln'], 'direction': 'higher = more vulnerable', 'latest_quarter': latest_q,
           'latest_value': latest, 'own_history_quarters': len(s), 'own_history_percentile': pct,
           'score_1to5': max(1, math.ceil(pct * 5)), 'use': 'scoring only; not used in Test 2'}
    if len(s) < 8:
        out['warning'] = f'only {len(s)} quarters of history; percentile is very coarse'
    return out


def confidence(c, t1, t2):
    k = c['kind']
    if k in ('case_sponsored', 'case_settlement', 'case_nomarket'):
        return 'Low/Medium (no market indicator; logic + cases, pending owner verification)'
    if t1 == 'FAIL':
        return 'Revise/drop (Test 1 failed)'
    if k == 'case':
        return 'Pending: Medium if owner verifies case evidence (Test 1 passed)'
    if t2 == 'WRONG_DIRECTION':
        return 'Revise/drop (Test 2 significant in wrong direction)'
    if t2 == 'PASS':
        return 'High'
    return 'Medium (Test 1 pass, Test 2 inconclusive)'


# ------------------------------------------------------------------ plots
def plot(cid, c, alerts, t2, t2data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={'width_ratios': [1.6, 1]})
    a = ax[0]
    if alerts is not None:
        a.plot(alerts.index, alerts.value, lw=.7, color='#3b6ea5', label=c['signal_label'])
        a.plot(alerts.index, alerts.threshold, lw=.8, color='#c0504d', ls='--', label='90th pct threshold')
        al = alerts[alerts.alert == 1]
        a.scatter(al.index, al.value, s=6, color='#c0504d', zorder=3, label='alert')
        for w in c['windows']:
            a.axvspan(pd.Timestamp(w['start']), pd.Timestamp(w['end']) + pd.Timedelta(days=1), color='#f2c14e', alpha=.45)
        a.set_title(f'{cid} Test 1 ({t2data.get("t1freq", "")}): signal, threshold, event windows')
        a.legend(fontsize=7, loc='upper left')
    elif 'sp' in t2data:
        sp = t2data['sp'] / 1e12
        a.plot(sp.index, sp, lw=.6, color='#3b6ea5')
        for m in CASES['FICC-GSD-03']['milestones']:
            if m['past']:
                a.axvline(pd.Timestamp(m['date']), color='#c0504d', ls='--')
        a.set_title(f'{cid}: FICC Sponsored daily volume (USD tn), past milestones'); a.set_ylabel('USD tn')
    elif cid == 'ECS-SET-01':
        pts = pd.DataFrame(CASES['ECS-SET-01']['fail_rate_points'])
        a.barh(pts.series + ' · ' + pts.period, pts.value_pct, color=np.where(pts.side == 'before', '#9bbbd9', '#3b6ea5'))
        a.set_xlabel('fail rate, %'); a.set_title(f'{cid}: published fail-rate points (light = before milestone)')
        a.tick_params(axis='y', labelsize=7)
    else:
        a.axis('off')
        lines = [f"{m['date']}  {m['event']}" for m in CASES[cid]['milestones']]
        a.text(0, .9, f'{cid} (no market indicator): events with public sources', fontsize=10, weight='bold')
        a.text(0, .75, '\n'.join(lines), fontsize=9, va='top')
    b = ax[1]
    if 'x' in t2data:
        j = pd.concat([t2data['x'].rename('x'), t2data['y'].rename('y')], axis=1).dropna()
        b.scatter(j.x, j.y, s=18, color='#3b6ea5')
        for q, r in j.iterrows():
            b.annotate(q, (r.x, r.y), fontsize=5.5, alpha=.7)
        pl = t2['primary_levels']
        b.set_title(f"Test 2 lag 0: rho={pl['rho']:.2f}, CI [{pl['ci95'][0]:.2f}, {pl['ci95'][1]:.2f}]", fontsize=9)
        b.set_xlabel('quarterly max signal'); b.set_ylabel(c['test_var_label'], fontsize=8)
    elif 'shock' in t2data:
        j = pd.concat([t2data['y'].rename('y'), t2data['shock'].rename('shock')], axis=1).dropna()
        groups = [j.y[j.shock == 0], j.y[j.shock == 1]]
        b.boxplot(groups, tick_labels=['other', 'shock'], showfliers=True)
        p = t2['primary']
        b.set_title(f"Test 2: coef={p['coef_shock']:.3g}, HAC p={p['p']:.3f}, n={p['n']} (shock {p['shock_obs']})", fontsize=9)
        b.set_ylabel(c['test_var_label'], fontsize=8)
    elif 'sp' in t2data:
        tb = pd.DataFrame(t2['table'])
        b.hist(t2data['ch'] * 100, bins=40, color='#9bbbd9')
        for _, row in tb.iterrows():
            b.axvline(row.change_pct * 100, color='#c0504d', ls='--')
            b.annotate(f"{row.milestone}: {row.change_pct:+.1%} (pct {row.percentile_in_sample:.0%})",
                       (row.change_pct * 100, b.get_ylim()[1] * (.9 - .12 * _)), xytext=(4, 0), textcoords='offset points', fontsize=7)
        dist = t2['all_splits_distribution']
        b.set_title(f"All 60-BD before/after changes: median {dist['median']:+.1%}, p75 {dist['p75']:+.1%}, p90 {dist['p90']:+.1%}", fontsize=8)
        b.set_xlabel('% change in mean daily Sponsored volume')
    else:
        b.axis('off')
        b.text(0, .5, 'Test 2 = case evidence\n(owner verifies; see REPORT.md)', fontsize=10)
    fig.tight_layout()
    fig.savefig(FIGURES / f'{cid}.png', dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ orchestration
def run_chain(cid):
    c = CHAINS[cid]
    rec = {'chain_id': cid, 'name': c['name'], 'version': c['version'], 'entity': c['entity'], 'spec': 'results/chain_tests/TEST_SPEC.md v1 (frozen 2026-10-16)',
           'prior_results_seen': c['prior_seen'], 'run_utc': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'bootstrap_seed': S.SEED}
    if c.get('candidate'):
        rec['label'] = 'v2 candidate, needs confirmation on data not used before (e.g., 2026Q3 PQD)'
    alerts, t2data = None, {}
    if c.get('post_hoc'):
        rec['post_hoc'] = {'label': 'post-hoc v2', 'base_chain': c['base'], 'reason': c['post_hoc_reason'],
                           'spec': 'TEST_SPEC.md §13 (written after v1 results)'}
    if c['signal']:
        rec['signal'] = c['signal_label']
        rec['test1'], alerts = run_test1(c)
        t2data['t1freq'] = rec['test1']['frequency']
    else:
        ms = CASES[cid]['milestones']
        rec['test1'] = {'method': 'No statistical test; confirm each milestone has a public source', 'milestones': ms,
                        'result': 'SOURCED — owner to verify' if all(m['sources'] for m in ms if m['date']) else 'INCOMPLETE'}
    k = c['kind']
    if k == 'quarterly':
        rec['test2'], d = test2_quarterly(c)
    elif k == 'event_daily':
        rec['test2'], d = test2_event_daily(c)
    elif k == 'event_weekly':
        rec['test2'], d = test2_event_weekly(c)
    elif k == 'case_sponsored':
        rec['test2'], d = test2_sponsored(c)
    elif k in ('case', 'case_nomarket'):
        cands = CASES[cid]['candidates']
        rec['test2'], d = {'method': 'Case evidence (card rule); never auto-passed', 'candidates': cands,
                           'proposed_verdict': cands[0].get('proposed_verdict'),
                           'result': 'CANDIDATE EVIDENCE — owner to verify', 'primary_p': []}, {}
    else:  # case_settlement
        rec['test2'], d = {'method': 'Before/after check only: no monthly fail-rate history (After-Action Report has post-T+1 points only; no Wayback snapshots)',
                           'points': CASES[cid]['fail_rate_points'], 'report_quotes': CASES[cid].get('report_quotes', []),
                           'result': 'BEFORE/AFTER CHECK ONLY — owner to verify', 'primary_p': []}, {}
    t2data.update(d)
    if c.get('test_var_label'):
        rec['test_variable'] = c['test_var_label']
    rec['vulnerability'] = vulnerability(c)
    return rec, alerts, t2data


def run(selected):
    RESULTS.mkdir(parents=True, exist_ok=True)
    checks.run()
    recs, aux = {}, {}
    for cid in CHAINS:
        recs[cid], alerts, t2data = run_chain(cid)
        aux[cid] = (alerts, t2data)
    # Benjamini–Hochberg across all primary Test 2 p-values
    v1 = [cid for cid in recs if not CHAINS[cid].get('post_hoc')]
    fam = [(cid, lab, p) for cid in v1 for lab, p in recs[cid]['test2']['primary_p'] if p is not None]
    q = D.bh([p for _, _, p in fam])
    for (cid, lab, p), qq in zip(fam, q):
        recs[cid]['test2'].setdefault('bh', []).append({'test': lab, 'p_raw': p, 'q_bh': qq, 'family_size': len(fam)})
    for cid in recs:
        if CHAINS[cid].get('post_hoc'):
            for lab, p in recs[cid]['test2']['primary_p']:
                qq = D.bh([x for _, _, x in fam] + [p])[-1]
                recs[cid]['test2'].setdefault('bh', []).append(
                    {'test': lab, 'p_raw': p, 'q_bh_if_added_to_v1_family': qq, 'family_size': len(fam) + 1,
                     'note': 'post-hoc; not part of the frozen v1 BH family'})
    for cid, r in recs.items():
        r['test2'].pop('primary_p', None)
        t1 = r['test1']['result']
        r['confidence'] = confidence(CHAINS[cid], t1, r['test2']['result'])
    for cid in selected:
        (RESULTS / f'{cid}.json').write_text(json.dumps(_clean(recs[cid]), indent=2, ensure_ascii=False))
        plot(cid, CHAINS[cid], aux[cid][0], recs[cid]['test2'], aux[cid][1])
    if len(selected) == len(CHAINS):
        summary(recs)
    return recs


def _t2_short(r):
    t = r['test2']
    if 'primary_levels' in t:
        s = f"{t['result']} (lag0 levels rho {t['primary_levels']['rho']:.2f}, CI [{t['primary_levels']['ci95'][0]:.2f}, {t['primary_levels']['ci95'][1]:.2f}]"
        if 'primary_changes' in t:
            s += f"; changes rho {t['primary_changes']['rho']:.2f}, CI [{t['primary_changes']['ci95'][0]:.2f}, {t['primary_changes']['ci95'][1]:.2f}]"
        return s + ')' + (f" [{t['flag']}]" if t.get('flag') else '')
    if 'primary' in t:
        p = t['primary']
        return f"{t['result']} (coef {p['coef_shock']:.3g}, HAC p {p['p']:.3f}, n {p['n']}, shock obs {p['shock_obs']})"
    return t['result']


def summary(recs):
    rows = []
    for cid, r in recs.items():
        t1 = r['test1']
        t1s = t1['result']
        if 'criteria' in t1:
            cr = t1['criteria']
            t1s += ' (' + ', '.join(f"{k} {v['value']:.2f}" for k, v in cr.items() if v['value'] is not None) + f", {t1['frequency']})"
        notes = [r.get('label', '')]
        if r['test2'].get('bh'):
            notes.append('BH q: ' + '; '.join(f"{b['test']} {b.get('q_bh', b.get('q_bh_if_added_to_v1_family')):.3f}"
                                              + ('' if 'q_bh' in b else ' (if added to v1 family)') for b in r['test2']['bh']))
        if r.get('post_hoc'):
            notes.append('POST-HOC v2: ' + r['post_hoc']['reason'])
        if r['test2'].get('proposed_verdict'):
            notes.append('Proposed: ' + r['test2']['proposed_verdict'].split(':')[0])
        rows.append({'ID': cid, 'Test 1': t1s, 'Test 2': _t2_short(r), 'Confidence': r['confidence'], 'Version': r['version'],
                     'Notes': ' | '.join(n for n in notes if n)})
    pd.DataFrame(rows).to_csv(RESULTS / 'summary.csv', index=False)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--chain', default='all', choices=['all', *CHAINS])
    a = ap.parse_args()
    sel = list(CHAINS) if a.chain == 'all' else [a.chain]
    recs = run(sel)
    for cid in sel:
        r = recs[cid]
        print(f"{cid}: Test1={r['test1']['result']} | Test2={_t2_short(r)} | {r['confidence']}")

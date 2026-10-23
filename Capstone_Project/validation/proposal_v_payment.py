"""SCORING_SPEC.md §10 items 6–7 (proposed, NOT active): V from 7.3.1 ÷ 7.1 (A) and a 7.3.2 > 0 override (B).

    python -m validation.proposal_v_payment [--week-end 2026-10-09]

Read only: does not touch active scoring, chain_confidence.json or any committed output.
Writes results/scoring/proposals/ (quarters table, ranking comparison, evidence).
"""
import argparse, copy, json, math, re

import numpy as np
import openpyxl
import pandas as pd

from . import data as D
from . import scoring as S
from .chains import CHAINS
from .paths import PROJECT, OLD_TESTS, PQD_MANIFEST

OUT = PROJECT / 'results' / 'scoring' / 'proposals'
ENT = {'FICC/GSD': 'GSD', 'NSCC': 'NSCC'}
CARDS = {'FICC-GSD-02': 'GSD', 'NSCC liquidity': 'NSCC'}
A_FIELD = 'payment_to_qlr'          # 7.3.1 ÷ quantified 7.1 (existing panel column)
CUR_FIELD = 'peak_payment_to_qlr'   # 7.3.4 ÷ quantified 7.1 (v1.1 active)
B_FLOOR = 4
PDF_2024Q4 = OLD_TESTS / 'data' / '2024Q4_page_15.txt'   # 2024Q4 was published as PDF only


def _num(x):
    try:
        return float(str(x).replace(',', ''))
    except (TypeError, ValueError):
        return np.nan


def raw_7_3():
    """PQD 7.3.1–7.3.4 for GSD and NSCC from the published files (7.3.3 is not in the panel)."""
    rows = []
    for m in json.loads(PQD_MANIFEST.read_text()):
        path = OLD_TESTS / m['local_file']
        if 'pqd' not in m['local_file'] or not path.exists():
            continue
        q = f"{m['reporting_year']}Q{m['reporting_quarter']}"
        if path.suffix == '.pdf':
            t = PDF_2024Q4.read_text()
            # PDF p.15 columns are GSD, MBSD, NSCC; USD $MM
            assert 'Bus. Days 0 0 2' in t and 'USD $MM 0 0 7,065' in t and '77,969 34,707 57,403' in t, 'PDF 2024Q4 text changed'
            rows += [{'quarter': q, 'entity': 'GSD', '7.3.1': 77969e6, '7.3.2': 0, '7.3.3': 0, '7.3.4': 83399e6, 'src': 'PDF p.15'},
                     {'quarter': q, 'entity': 'NSCC', '7.3.1': 57403e6, '7.3.2': 2, '7.3.3': 7065e6, '7.3.4': 57403e6, 'src': 'PDF p.15'}]
            continue
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rec = {}
        for r in wb['DTCC_ConsolidatedDataFile'].values:
            ref = str(r[1]) if len(r) > 1 else ''
            if ref not in ('7.3.1', '7.3.2', '7.3.3', '7.3.4'):
                continue
            for i, c in enumerate(r):
                if c in ENT and i + 4 < len(r):
                    rec.setdefault(ENT[c], {})[ref] = _num(r[i + 4])
        wb.close()
        rows += [{'quarter': q, 'entity': e, **v, 'src': path.name} for e, v in rec.items()]
    return pd.DataFrame(rows).drop_duplicates(['quarter', 'entity']).sort_values(['entity', 'quarter'])


def own_history_v(s):
    """v1.1 V formula on each quarter's own history up to and including it: ceil(share ≤ value × 5)."""
    s = s.dropna()
    return pd.Series({q: max(1, math.ceil(float((s.loc[:q] <= s.loc[q]).mean()) * 5)) for q in s.index}, dtype='Int64')


def method_break_check(t):
    """Item 3: does 7.3.1 show the same break as 7.3.4 in 2020Q4–2021Q2?"""
    out = {}
    for e, g in t.groupby('entity'):
        g = g.set_index('quarter').sort_index()
        trail_max = g['7.3.1'].rolling(4, min_periods=1).max()
        out[e] = {
            # tolerance $1MM: 2024Q4 is a PDF rounded to $MM
            '7.3.4_equals_trailing4q_max_of_7.3.1': {q: bool(abs(g.loc[q, '7.3.4'] - trail_max.loc[q]) < 1e6) for q in g.index},
            '7.3.4_below_same_quarter_7.3.1': [q for q in g.index if g.loc[q, '7.3.4'] < g.loc[q, '7.3.1'] * (1 - 1e-9)],
            '7.3.1_bn_early_vs_later': {'2020Q4-2021Q2': [round(x / 1e9, 1) for x in g.loc['2020Q4':'2021Q2', '7.3.1']],
                                        '2021Q3+ min/median/max': [round(x / 1e9, 1) for x in
                                                                   (g.loc['2021Q3':, '7.3.1'].min(), g.loc['2021Q3':, '7.3.1'].median(), g.loc['2021Q3':, '7.3.1'].max())]},
        }
    return out


def quarters_table():
    p = D.pqd_panel()
    t = raw_7_3()
    m = t.merge(p[['quarter', 'entity', 'qlr_quantified_sum_usd', 'liquidity_breach_days', CUR_FIELD, A_FIELD]], on=['quarter', 'entity'], how='left')
    chk = m.dropna(subset=['liquidity_breach_days'])
    assert (chk['7.3.2'] == chk.liquidity_breach_days).all(), 'panel 7.3.2 differs from published files'
    out = []
    for e, g in m.groupby('entity'):
        g = g.set_index('quarter').sort_index()
        g['V_current_7.3.4'] = own_history_v(g[CUR_FIELD])
        g['V_A_7.3.1'] = own_history_v(g[A_FIELD])
        # B reads 7.3.2 of the latest published quarter even when 7.1 is blank there; V_A then carries forward, as in S.vuln
        va = g['V_A_7.3.1'].ffill()
        g['V_A+B'] = [None if pd.isna(v) else (max(int(v), B_FLOOR) if d > 0 else int(v)) for v, d in zip(va, g['7.3.2'])]
        out.append(g.reset_index())
    q = pd.concat(out)
    q = q.rename(columns={'qlr_quantified_sum_usd': '7.1_quantified'})
    for c in ['7.3.1', '7.3.4', '7.1_quantified', '7.3.3']:
        q[c + '_bn'] = (q[c] / 1e9).round(2)
    return t, q[['entity', 'quarter', '7.3.1_bn', '7.3.4_bn', '7.1_quantified_bn', '7.3.2', '7.3.3_bn',
                 CUR_FIELD, A_FIELD, 'V_current_7.3.4', 'V_A_7.3.1', 'V_A+B', 'src']]


def ranking(week_end, mode):
    """This week's cards with V from v1.1 ('current'), Proposal A ('A') or A+B ('A+B'). Active code is not modified."""
    conf = copy.deepcopy(S.load_chain_conf())
    reg = S.load_register()
    if mode != 'current':
        for cid in ('FICC-GSD-02', 'ECS-NSCC-01', 'ECS-NSCC-02'):
            conf[cid]['vulnerability_variable']['field'] = A_FIELD
            conf[cid]['vulnerability_variable']['description'] = 'Estimated largest payment obligation ÷ qualifying liquid resources (7.3.1 ÷ 7.1) [PROPOSED]'
    base_vuln = S.vuln

    def vuln(cid, c, we):
        V, rel, basis = base_vuln(cid, c, we)
        if mode == 'A+B' and c['vulnerability_variable']['field'] == A_FIELD and V is not None:
            ent = CHAINS[S.ACTIVE.get(cid, cid)]['entity']
            p = S.PQD_AVAIL[(S.PQD_AVAIL.entity == ent) & (S.PQD_AVAIL.available_date <= we)].sort_values('quarter')
            if p.liquidity_breach_days.iloc[-1] > 0:
                V = max(V, B_FLOOR)
        return V, rel, basis

    S.vuln = vuln
    try:
        rows = S.chain_rows(conf, reg, [week_end])
        cards = S.build_cards(conf, rows, week_end)
    finally:
        S.vuln = base_vuln
    return pd.DataFrame([{'card': c['id'], 'group': c['group'], 'rank': c['rank_in_group'], 'S': c['S'], 'V': c['V'],
                          'severity': c['severity'], 'driver': c['driver'], 'v_basis': c['v_basis']} for c in cards])


def main(week_end):
    week_end = pd.Timestamp(week_end)
    OUT.mkdir(parents=True, exist_ok=True)
    raw, q = quarters_table()
    q.to_csv(OUT / 'v_7_3_1_quarters.csv', index=False)

    r = {m: ranking(week_end, m).set_index('card') for m in ('current', 'A', 'A+B')}
    cur = S.load_chain_conf()
    for cid, card in [('FICC-GSD-02', 'FICC-GSD-02'), ('ECS-NSCC-01', 'NSCC liquidity')]:   # baseline must reproduce v1.1
        assert r['current'].loc[card, 'V'] == cur[cid]['vulnerability_variable']['latest_score_1to5'], card
    cmp_ = pd.concat({m: d[['group', 'rank', 'S', 'V', 'severity']] for m, d in r.items()}, axis=1)
    cmp_.columns = [f'{a}_{b}' for a, b in cmp_.columns]
    cmp_.reset_index().to_csv(OUT / f'ranking_{(week_end - pd.Timedelta(days=4)).date()}_v1.1_vs_proposal.csv', index=False)

    evidence = {'spec': 'SCORING_SPEC.md §10 items 6–7 (proposed, not active)', 'week_end': str(week_end.date()),
                'method_break_check': method_break_check(raw)}
    (OUT / 'v_7_3_1_evidence.json').write_text(json.dumps(S._clean(evidence), indent=2))

    pd.set_option('display.width', 250)
    pd.set_option('display.max_columns', 30)
    for e in ('GSD', 'NSCC'):
        print(f'== {e}')
        print(q[q.entity == e].drop(columns=['entity', 'src']).to_string(index=False))
    print('== ranking, week ending', week_end.date())
    print(cmp_.to_string())
    print(json.dumps(evidence['method_break_check'], indent=1)[:4000])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--week-end', default='2026-10-09')
    main(ap.parse_args().week_end)

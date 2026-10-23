"""Export final chain confidence for the scoring backend.

    python -m validation.export
Reads results/chain_tests/<active>.json and validation/signoffs.py; writes
results/chain_tests/chain_confidence.json and adds a final-confidence column to summary.csv.
Scoring v1.2: chains in signoffs.SCORING_VULN get that vulnerability field, scored on the PQD panel.
"""
import json, math

import pandas as pd

from . import data as D
from .chains import CHAINS
from .paths import RESULTS
from .signoffs import FINAL, ROUND, CLOSED_UTC, SCORING_VULN


def scoring_vuln(entity, field):
    """Latest quarter, own-history percentile and ceil(pct × 5), as in round 1 (SCORING_SPEC §12.1)."""
    p = D.pqd_panel()
    s = p[p.entity == entity].set_index('quarter').sort_index()[field].dropna()
    pct = float((s <= s.iloc[-1]).mean())
    return {'latest_quarter': s.index[-1], 'own_history_percentile': pct, 'score_1to5': max(1, math.ceil(pct * 5))}


def build():
    records = []
    for cid, f in FINAL.items():
        c = CHAINS[f['active']]
        r = json.loads((RESULTS / f"{f['active']}.json").read_text())
        v = r['vulnerability']
        sv = SCORING_VULN.get(cid)
        if sv:
            v = {**v, **scoring_vuln(c['entity'], sv['field'])}
        has_signal = bool(c.get('signal'))
        records.append({
            'id': cid,
            'version': c['version'],
            'result_file': f"results/chain_tests/{f['active']}.json",
            'confidence': f['confidence'],
            'chain_type': 'with market indicator' if has_signal else 'without market indicator',
            'signal': {'field': c['signal'], 'description': c['signal_label']} if has_signal
                      else {'field': None, 'description': 'none; shock score from rubric (to be designed)'},
            'test_variable': c.get('test_var_label') or 'case evidence',
            'vulnerability_variable': {'field': sv['field'] if sv else c.get('vuln'),
                                       'description': sv['label'] if sv else c['vuln_label'],
                                       'direction': 'higher = more vulnerable' if c.get('vuln') else None,
                                       'latest_quarter': v.get('latest_quarter'), 'latest_percentile': v.get('own_history_percentile'),
                                       'latest_score_1to5': v.get('score_1to5'), 'warning': v.get('warning'),
                                       **({'scoring_version': sv['scoring_version'], 'replaces': sv['replaces']} if sv else {})},
            'mechanism_override': f.get('mechanism'),
            'flags': [x for x, on in [('watch', f.get('watch')), ('v2_candidate_needs_2026Q3_confirmation', f.get('candidate')),
                                      ('shock_score_from_rubric', f.get('shock_from_rubric')),
                                      ('post_hoc_version', c.get('post_hoc'))] if on],
            'superseded_versions': f['superseded'],
            'evidence_note': f['evidence'],
        })
    out = {'round': ROUND, 'closed_utc': CLOSED_UTC, 'spec': 'results/chain_tests/TEST_SPEC.md',
           'confidence_levels': ['High', 'Medium', 'Low'], 'chains': records}
    (RESULTS / 'chain_confidence.json').write_text(json.dumps(out, indent=2, ensure_ascii=False))

    s = pd.read_csv(RESULTS / 'summary.csv')
    final = {f['active']: f['confidence'] for f in FINAL.values()}
    s['Final confidence (round 1 sign-off)'] = s.ID.map(lambda i: final.get(i, 'superseded'))
    s.to_csv(RESULTS / 'summary.csv', index=False)
    return out


if __name__ == '__main__':
    for rec in build()['chains']:
        print(rec['id'], rec['version'], rec['confidence'], rec['flags'])

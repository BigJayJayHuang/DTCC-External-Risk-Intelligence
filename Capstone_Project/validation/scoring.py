"""Weekly scoring step (results/scoring/SCORING_SPEC.md v1.2: v1 frozen at 8d75706, v1.1 rules §11 at 2d0f9db,
v1.2 rules §12 at f7c0d24).

    python -m validation.scoring [--run-date YYYY-MM-DD]
"""
import argparse, datetime as dt, hashlib, json, math, re
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D
from . import event_scoring as E
from .chains import CHAINS
from .paths import PROJECT, RESULTS
from .run import SIGNALS

OUT = PROJECT / 'results' / 'scoring'
REGISTER = PROJECT / 'data' / 'events' / 'event_register.csv'
MAJOR_PARTICIPANTS = PROJECT / 'data' / 'events' / 'major_participants.csv'
PROMPT = Path(__file__).with_name('llm_event_classifier_prompt.md')
PROMPT_VERSION = hashlib.sha256(PROMPT.read_bytes()).hexdigest()[:12]
HISTORY_START = pd.Timestamp('2021-01-08')          # Friday of the week of 2021-01-04
MIN_PRIOR_WEEKS = 104
SPEC_VERSION = 'v1.2'
SLD_FLOOR = 4                                        # §12.2
# §12.3: prompt catalog ids -> scoring cards; v1.2 scores the existing 9 cards only
CATALOG_TO_CARDS = {'ECS-NSCC-LIQ': ['NSCC liquidity'], 'XE-MEMBER': ['FICC-GSD-04', 'ECS-NSCC-04']}
MEMBER_CARDS = {'XE-MEMBER', 'FICC-GSD-04', 'ECS-NSCC-04'}
ACTIVE = {'FICC-GSD-02': 'FICC-GSD-02.v2', 'ECS-NSCC-04': 'ECS-NSCC-04.v2'}
SANITY_DATES = ['2020-03-16', '2021-01-25', '2023-03-13', '2024-05-27', '2025-04-07']
CARD_ORDER = ['FICC-GSD-01', 'FICC-GSD-02', 'FICC-GSD-03', 'FICC-GSD-04', 'FICC-MBSD-01', 'NSCC liquidity',
              'ECS-NSCC-03', 'ECS-SET-01', 'ECS-NSCC-04']


def friday(d):
    d = pd.Timestamp(d)
    return d + pd.Timedelta(days=(4 - d.dayofweek) % 7)


def pct_to_s(p):
    return 1 if p < .2 else 2 if p < .4 else 3 if p < .6 else 4 if p < .8 else 5


def total_to_s(t):
    return {6: 5, 5: 4, 4: 3, 3: 2}.get(t, 1)


# ------------------------------------------------------------------ 3A percentile S
def weekly_peaks(series):
    s = series.dropna()
    labels = s.index + pd.to_timedelta((4 - s.index.dayofweek) % 7, unit='D')
    return s.groupby(labels).max().sort_index()


def percentile_scores(peaks):
    """Expanding midrank percentile of each week's peak vs all prior weekly peaks (current excluded)."""
    vals = peaks.values
    out = {}
    for i, (wk, x) in enumerate(peaks.items()):
        prior = vals[:i]
        if len(prior) < MIN_PRIOR_WEEKS:
            out[wk] = {'S': None, 'reason': f'insufficient history ({len(prior)} < {MIN_PRIOR_WEEKS} prior weeks)',
                       'weekly_peak': float(x), 'prior_weeks': len(prior)}
            continue
        p = (np.sum(prior < x) + .5 * np.sum(prior == x)) / len(prior)
        if x <= 0:   # v1.1 §11.2 floor rule: no widening / no stress
            out[wk] = {'S': 1, 'method': 'floor (signal <= 0)', 'weekly_peak': float(x), 'percentile': float(p), 'prior_weeks': len(prior)}
        else:
            out[wk] = {'S': pct_to_s(p), 'method': 'percentile', 'weekly_peak': float(x), 'percentile': float(p), 'prior_weeks': len(prior)}
    return out


# ------------------------------------------------------------------ 3B rubric S (v1.2 §12.3: event_scoring.py)
def load_register():
    r = pd.read_csv(REGISTER, dtype=str).fillna('')
    for c in ['certainty', 'reach']:
        r[c] = r[c].astype(int)
    r['effect'] = pd.to_datetime(r.effect_date)
    r['announced'] = pd.to_datetime(r.announced_date.where(r.announced_date != '', r.effect_date))
    r['card_ids'] = r.card_ids.where(r.card_ids != '', r.chain_id)
    return r


def scoring_cards(card_ids):
    return sorted({s for c in card_ids for s in CATALOG_TO_CARDS.get(c, [c]) if s in CARD_ORDER})


def load_events(reg):
    """Register rows -> event_scoring.Event. LLM rows go through validate(); human rows keep their register review flag."""
    catalog = set(CARD_ORDER) | set(re.findall(r'^\| ((?:FICC|ECS|XE)-[A-Z0-9-]+) \|', PROMPT.read_text(), re.M))
    major = set(pd.read_csv(MAJOR_PARTICIPANTS, dtype=str).name.dropna())
    events = []
    for _, r in reg.iterrows():
        ev = E.Event(event_id=r.event_id, card_ids=r.card_ids.split('|'), title=r.title,
                     announced_date=r.announced.date(), effect_date=r.effect.date(),
                     certainty=int(r.certainty), reach=int(r.reach),
                     evidence_quotes=[q.strip() for q in r.evidence_quote.split('||') if q.strip()],
                     sources=[{'url': u.strip(), 'outlet': r.outlet, 'tier': r.source_tier} for u in r.source_url.split(';') if u.strip()],
                     llm_confidence=float(r.llm_confidence) if r.llm_confidence else 1.0,
                     stage=int(r.stage) if r.stage else None,
                     named_participants=[x for x in r.named_participants.split('|') if x], reach_basis=r.reach_basis,
                     updated_date=pd.Timestamp(r.updated_date).date() if r.updated_date else None)
        if r.entered_by == 'llm':
            path = PROJECT / r.article_file if r.article_file else None
            texts = [path.read_text()] if path and path.is_file() else []
            ev = E.validate(ev, texts, catalog, major)
            if not texts:
                ev.review_reasons.append('article text not stored (article_file)')
        elif r.needs_review == 'Y':
            ev.review_reasons = ['register needs_review = Y']
        if ev.stage is not None and not set(ev.card_ids) <= MEMBER_CARDS:
            ev.stage = None
            ev.review_reasons.append('stage removed: not a member-card event')
        events.append(ev)
    return events


EVENTS = None


def register_events(reg):
    global EVENTS
    if EVENTS is None:
        EVENTS = load_events(reg)
    return EVENTS


def active_events(reg, week_end):
    """Ranked active events of the week (event_scoring.rank_events), each with the scoring cards it maps to."""
    by_id = {e.event_id: e for e in register_events(reg)}
    out = []
    for r in E.rank_events(list(by_id.values()), (week_end - pd.Timedelta(days=4)).date()):
        out.append({**r, 'effect_date': str(by_id[r['event_id']].effect_date), 'scoring_cards': scoring_cards(r['card_ids'])})
    return out


def card_event_score(reg, card_id, week_end):
    """Highest S among active events mapped to the card (ties: certainty, reach, recency) and the driving event."""
    mine = [r for r in active_events(reg, week_end) if card_id in r['scoring_cards']]
    if not mine:
        return {'S': 1, 'method': 'rubric v1.2', 'reason': 'no active event', 'events': [], 'active_events': 0}
    d = mine[0]
    return {'S': d['S'], 'method': 'rubric v1.2', 'events': mine, 'driving_event_ids': [d['event_id']],
            'needs_review': d['needs_review'], 'rubric_version': E.RUBRIC_VERSION, 'active_events': len(mine)}


# ------------------------------------------------------------------ cards
def load_chain_conf():
    d = json.loads((RESULTS / 'chain_confidence.json').read_text())
    return {c['id']: c for c in d['chains']}


def scoring_signal(cid, field):
    peaks = weekly_peaks(SIGNALS[field]())
    if cid == 'ECS-NSCC-03':   # v1.1 §11.1: weekly peak / median of prior 52 weekly peaks
        return (peaks / peaks.shift(1).rolling(52, min_periods=52).median()).dropna()
    return peaks


def chain_rows(conf, reg, week_ends):
    """Per-chain S for each requested week_end."""
    pct = {}
    for cid, c in conf.items():
        f = c['signal']['field']
        if f:
            pct[cid] = percentile_scores(scoring_signal(cid, f))
    rows = {}
    for cid, c in conf.items():
        for we in week_ends:
            if c['signal']['field']:
                rec = pct[cid].get(we) or {'S': None, 'reason': 'no data this week'}
            else:
                rec = card_event_score(reg, cid, we)
            rows[(cid, we)] = rec
    return rows


def pqd_available():
    p = D.pqd_panel().copy()
    qend = pd.Series(pd.PeriodIndex(p.quarter, freq='Q').end_time.normalize(), index=p.index)
    listed = pd.to_datetime(p.listed_date, format='%b %d, %Y', errors='coerce')
    p['available_date'] = listed.fillna(qend + pd.Timedelta(days=90))
    p['available_basis'] = np.where(listed.notna(), 'listed_date', 'quarter_end+90d')
    return p


PQD_AVAIL = None


def vuln(cid, c, we):
    """v1.1 §11.4: as-of V from the latest PQD quarter public by week_end."""
    global PQD_AVAIL
    v = c['vulnerability_variable']
    if not v['field']:
        return None, 'n/a', ''
    if PQD_AVAIL is None:
        PQD_AVAIL = pqd_available()
    ent = CHAINS[ACTIVE.get(cid, cid)]['entity']
    p = PQD_AVAIL[(PQD_AVAIL.entity == ent) & (PQD_AVAIL.available_date <= we)].sort_values('quarter')
    s = p.set_index('quarter')[v['field']].dropna()
    if s.empty:
        return None, 'no PQD public yet', ''
    pct = float((s <= s.iloc[-1]).mean())
    return max(1, math.ceil(pct * 5)), ('low (<8 quarters of history)' if len(s) < 8 else 'ok'), f'as_of_{s.index[-1]}'


def sld_override(we):
    """v1.2 §12.2: NSCC 7.3.2 > 0 in the latest PQD quarter public by week_end -> V >= 4 for NSCC liquidity."""
    p = PQD_AVAIL[(PQD_AVAIL.entity == 'NSCC') & (PQD_AVAIL.available_date <= we)].sort_values('quarter')
    if p.empty or not p.liquidity_breach_days.iloc[-1] > 0:
        return None
    q = p.iloc[-1]
    return f'SLD needed this quarter (NSCC 7.3.2 = {int(q.liquidity_breach_days)} days in {q.quarter})'


def combine_s(S_market, ev):
    """v1.2 §12.4: S = max(market S, event S) when an event is active on the card; records the source."""
    if not ev['active_events']:
        return S_market, 'market'
    if S_market is None:
        return ev['S'], 'events (market null)'
    S = max(S_market, ev['S'])
    return S, 'market=events' if S_market == ev['S'] else 'market' if S_market > ev['S'] else 'events'


def build_cards(conf, rows, we, reg=None):
    reg = load_register() if reg is None else reg
    cards = []
    def card(card_id, members):
        c0 = conf[members[0]]
        V, rel, basis = vuln(members[0], c0, we)
        V_base, override = V, None
        if card_id == 'NSCC liquidity' and V is not None:
            override = sld_override(we)
            if override:
                V = max(V, SLD_FLOOR)
        recs = {m: rows[(m, we)] for m in members}
        Ss = {m: r['S'] for m, r in recs.items()}
        valid = {m: s for m, s in Ss.items() if s is not None}
        S = max(valid.values()) if valid else None
        if c0['signal']['field']:
            ev = card_event_score(reg, card_id, we)
            S, S_source = combine_s(S, ev)
        else:
            ev, S_source = recs[members[0]], 'events'
        flags = {f for m in members for f in conf[m]['flags']}
        if S_source != 'market' and ev.get('needs_review'):
            flags.add('event_needs_human_check')
        out = {'id': card_id, 'week': str((we - pd.Timedelta(days=4)).date()), 'week_end': str(we.date()),
               'chains': [{'chain_id': m, 'version': conf[m]['version'], 'signal': conf[m]['signal']['description'],
                           'S': recs[m]['S'], 'S_computation': recs[m]} for m in members],
               'S': S, 'S_source': S_source, 'V': V, 'V_base': V_base, 'V_override_reason': override,
               'vulnerability_variable': c0['vulnerability_variable']['description'],
               'severity': S * V if (S is not None and V is not None) else None,
               'confidence': c0['confidence'], 'flags': sorted(flags), 'vuln_reliability': rel, 'v_basis': basis}
        if c0['signal']['field'] and ev['active_events']:
            out['S_events'] = ev
        out['driver'] = ('n/a' if S is None or V is None else 'shock' if S > V else 'vulnerability' if V > S else 'both')
        if not c0['vulnerability_variable']['field']:
            out['label'] = 'vulnerability: no data'
        elif V is None:
            out['label'] = 'vulnerability: no PQD public yet'
        if S is None:
            out['S_null_reason'] = '; '.join(f"{m}: {recs[m].get('reason')}" for m in members)
        if len(members) > 1 and valid:
            out['shock_driver_chain'] = [m for m, s in valid.items() if s == S]
        cards.append(out)
    for cid in CARD_ORDER:
        if cid == 'NSCC liquidity':
            assert conf['ECS-NSCC-01']['confidence'] == conf['ECS-NSCC-02']['confidence']
            card(cid, ['ECS-NSCC-01', 'ECS-NSCC-02'])
        else:
            card(cid, [cid])
    # ranking
    g1 = sorted([c for c in cards if c['severity'] is not None], key=lambda c: (-c['severity'], -c['S'], c['id']))
    g2 = sorted([c for c in cards if c['severity'] is None and c['S'] is not None], key=lambda c: (-c['S'], c['id']))
    g3 = sorted([c for c in cards if c['S'] is None], key=lambda c: c['id'])
    for grp, lst in [('severity', g1), ('shock-only', g2), ('no score', g3)]:
        for i, c in enumerate(lst, 1):
            c['group'], c['rank_in_group'] = grp, i
    return g1 + g2 + g3


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(o) else float(o)
    return o


def flat(cards):
    out = []
    for c in cards:
        base = {'week': c['week'], 'week_end': c['week_end'], 'card_id': c['id'], 'S': c['S'], 'S_source': c['S_source'],
                'V': c['V'], 'V_base': c['V_base'], 'V_override_reason': c['V_override_reason'] or '', 'severity': c['severity'],
                'confidence': c['confidence'], 'flags': '|'.join(c['flags']), 'vuln_reliability': c['vuln_reliability'],
                'group': c['group'], 'rank_in_group': c['rank_in_group'], 'v_basis': c['v_basis'], 'driver': c['driver'],
                'shock_driver_chain': '|'.join(c.get('shock_driver_chain', []))}
        for ch in c['chains']:
            comp = ch['S_computation']
            out.append({**base, 'chain_id': ch['chain_id'], 'chain_S': ch['S'], 'S_method': comp.get('method', ''),
                        'weekly_peak': comp.get('weekly_peak'), 'percentile': comp.get('percentile'), 'prior_weeks': comp.get('prior_weeks'),
                        'rubric_events': ';'.join(f"{e['event_id']}(c{e['certainty']}r{e['reach']}t{e['timing']}=S{e['S']})"
                                                  for e in comp.get('events', [])),
                        'S_note': comp.get('reason', '')})
    return out


# ------------------------------------------------------------------ figure
def figure(hist, reg):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    chains = [c for c in ['FICC-GSD-01', 'FICC-GSD-02', 'FICC-GSD-03', 'FICC-GSD-04', 'FICC-MBSD-01', 'ECS-NSCC-01', 'ECS-NSCC-02',
                          'ECS-NSCC-03', 'ECS-SET-01', 'ECS-NSCC-04']]
    active = {'FICC-GSD-02': 'FICC-GSD-02.v2', 'ECS-NSCC-04': 'ECS-NSCC-04.v2'}
    fig, axes = plt.subplots(len(chains), 1, figsize=(12, 1.35 * len(chains)), sharex=True)
    for ax, cid in zip(axes, chains):
        h = hist[hist.chain_id == cid].drop_duplicates('week_end')
        x = pd.to_datetime(h.week_end)
        ax.step(x, h.chain_S, where='post', lw=.8, color='#3b6ea5')
        for w in CHAINS[active.get(cid, cid)].get('windows', []):
            ax.axvspan(pd.Timestamp(w['start']), pd.Timestamp(w['end']) + pd.Timedelta(days=1), color='#f2c14e', alpha=.6)
        for _, e in reg[reg.chain_id == cid].iterrows():
            ax.axvline(e.effect, color='#c0504d', lw=.8, ls='--')
        ax.set_ylim(.5, 5.5); ax.set_yticks([1, 3, 5]); ax.tick_params(labelsize=7)
        ax.set_ylabel(cid.replace('FICC-', '').replace('ECS-', ''), fontsize=7, rotation=0, ha='right', va='center')
    axes[0].set_title('Weekly shock score S by chain (shaded: validation event windows; dashed: register event effect dates)', fontsize=9)
    fig.tight_layout()
    (OUT / 'figures').mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / 'figures' / 'shock_scores_history.png', dpi=130)
    plt.close(fig)


# ------------------------------------------------------------------ main
def main(run_date):
    run_date = pd.Timestamp(run_date)
    d = run_date - pd.Timedelta(days=1)                       # latest Friday strictly before the run date (spec §2)
    latest = d - pd.Timedelta(days=(d.dayofweek - 4) % 7)
    conf, reg = load_chain_conf(), load_register()
    weeks = list(pd.date_range(HISTORY_START, latest, freq='W-FRI'))
    sanity_weeks = [friday(d) for d in SANITY_DATES] + [latest]
    rows = chain_rows(conf, reg, sorted(set(weeks) | set(sanity_weeks)))
    OUT.mkdir(parents=True, exist_ok=True)

    cards_latest = build_cards(conf, rows, latest, reg)
    unscored = [{k: e[k] for k in ('event_id', 'title', 'card_ids', 'S')} for e in active_events(reg, latest) if not e['scoring_cards']]
    (OUT / 'weekly_scores.json').write_text(json.dumps(_clean({
        'spec': 'results/scoring/SCORING_SPEC.md v1.2 (v1 commit 8d75706; v1.1 rules commit 2d0f9db; v1.2 rules commit f7c0d24)',
        'spec_version': SPEC_VERSION, 'rubric_version': E.RUBRIC_VERSION, 'prompt_version': PROMPT_VERSION,
        'run_date': str(run_date.date()),
        'week': str((latest - pd.Timedelta(days=4)).date()), 'week_end': str(latest.date()),
        'v_basis': 'as-of V (latest PQD public by week_end)', 'cards': cards_latest,
        'unscored_events': unscored}), indent=2, ensure_ascii=False))
    for c in cards_latest:   # §11.4 / §12.2: the latest week's V before the SLD override must reproduce chain_confidence.json
        cid = c['chains'][0]['chain_id']
        assert c['V_base'] == conf[cid]['vulnerability_variable']['latest_score_1to5'], (cid, c['V_base'])

    hist = pd.DataFrame([r for we in weeks for r in flat(build_cards(conf, rows, we, reg))])
    hist.to_csv(OUT / 'weekly_scores_history.csv', index=False)
    figure(hist, reg)

    sanity = {str(we.date()): build_cards(conf, rows, we, reg) for we in sanity_weeks}
    # known stress events: validation windows + rubric event effect dates
    misses = []
    active = {'FICC-GSD-02': 'FICC-GSD-02.v2', 'ECS-NSCC-04': 'ECS-NSCC-04.v2'}
    all_pct = {cid: percentile_scores(scoring_signal(cid, c['signal']['field'])) for cid, c in conf.items() if c['signal']['field']}
    for cid, c in conf.items():
        events = [(w['label'], pd.Timestamp(w['start']), pd.Timestamp(w['end'])) for w in CHAINS[active.get(cid, cid)].get('windows', [])]
        if not c['signal']['field']:
            events = [(f"{e.event_id} {e.title}", e.effect, e.effect) for _, e in reg[reg.chain_id == cid].iterrows()]
        for label, a, b in events:
            for we in pd.date_range(friday(a), friday(b), freq='W-FRI'):
                rec = all_pct[cid].get(we, {'S': None, 'reason': 'no data this week'}) if cid in all_pct else card_event_score(reg, cid, we)
                if rec['S'] is None or rec['S'] <= 2:
                    misses.append({'chain_id': cid, 'event': label, 'week_end': str(we.date()), 'S': rec['S'],
                                   'detail': rec.get('reason') or (f"pct {rec.get('percentile'):.2f}" if rec.get('percentile') is not None else '')})
    (OUT / 'sanity_check.json').write_text(json.dumps(_clean({'weeks': sanity, 'stress_weeks_with_S_le_2_or_null': misses}), indent=2))
    return cards_latest, sanity, misses, reg


def show(cards):
    for c in cards:
        sev = c['severity'] if c['severity'] is not None else '—'
        extra = f" driver={c['driver']}" + (f" shock_from={','.join(c['shock_driver_chain'])}" if c.get('shock_driver_chain') else '')
        print(f"  [{c['group']} #{c['rank_in_group']}] {c['id']:<15} S={c['S']} V={c['V']} severity={sev} "
              f"conf={c['confidence']} flags={','.join(c['flags']) or '-'} vuln={c['vuln_reliability']}{extra}"
              + (f" | {c.get('S_null_reason')}" if c['S'] is None else ''))


# ------------------------------------------------------------------ v1.1 / v1.2 extras
def plot_payment_to_qlr():
    """Full history of PQD 7.3.1 / 7.1 (payment_to_qlr) behind the V of GSD-02 and NSCC liquidity (v1.2 §12.1)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    p = pqd_available()
    fig, ax = plt.subplots(figsize=(11, 4))
    rows = []
    for ent, col in [('GSD', '#3b6ea5'), ('NSCC', '#c0504d'), ('MBSD', '#9bbbd9')]:
        s = p[p.entity == ent].set_index('quarter').payment_to_qlr
        x = pd.PeriodIndex(s.index, freq='Q').end_time
        ax.plot(x, s.values, marker='o', ms=3, lw=1.2 if ent != 'MBSD' else .8, color=col, label=f'{ent}' + (' (context)' if ent == 'MBSD' else ''))
        sd = s.dropna()
        pct = float((sd <= sd.iloc[-1]).mean())
        rows.append({'entity': ent, 'latest_quarter': sd.index[-1], 'latest_value': float(sd.iloc[-1]), 'own_history_quarters': len(sd),
                     'percentile': pct, 'V': max(1, math.ceil(pct * 5)), 'min': float(sd.min()), 'max': float(sd.max()),
                     'missing_quarters': s[s.isna()].index.tolist()})
        ax.annotate(f'{ent} {sd.index[-1]}: {sd.iloc[-1]:.2f} (pct {pct:.0%}, V={max(1, math.ceil(pct * 5))})',
                    (x[-1], sd.iloc[-1]), xytext=(6, 0), textcoords='offset points', fontsize=7, color=col)
    ax.axhline(1, color='grey', lw=.6, ls=':')
    ax.set_title('PQD 7.3.1 ÷ 7.1 (estimated largest payment obligation ÷ quantified qualifying liquid resources), 2020Q4–2026Q2; '
                 '2022Q1 missing (7.1 blanks)', fontsize=9)
    ax.set_ylabel('ratio'); ax.legend(fontsize=8)
    fig.tight_layout()
    (OUT / 'figures').mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / 'figures' / 'payment_to_qlr_history.png', dpi=130)
    plt.close(fig)
    return rows


COMPARE_FROM = '2026-10-05'


def compare_versions():
    """v1.1 (re-run on the same inputs, results/scoring/v1.1_rerun/) vs v1.2, card level, weeks from COMPARE_FROM (§12.5)."""
    keep = ['week', 'card_id', 'S', 'V', 'severity', 'group', 'rank_in_group']
    v11 = pd.read_csv(OUT / 'v1.1_rerun' / 'weekly_scores_history.csv').drop_duplicates(['week', 'card_id'])[keep]
    v12 = pd.read_csv(OUT / 'weekly_scores_history.csv').drop_duplicates(['week', 'card_id'])[keep + ['S_source', 'V_base', 'V_override_reason']]
    df = v11.merge(v12, on=['week', 'card_id'], how='outer', suffixes=('_v1.1', '_v1.2'))
    df = df[df.week >= COMPARE_FROM].sort_values(['week', 'group_v1.2', 'rank_in_group_v1.2'])
    df.to_csv(OUT / 'compare_v1.1_v1.2.csv', index=False)
    return df


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-date', default=str(dt.date.today()))
    a = ap.parse_args()
    latest, sanity, misses, reg = main(a.run_date)
    ppq = plot_payment_to_qlr()
    (OUT / 'payment_to_qlr_summary.json').write_text(json.dumps(_clean(ppq), indent=2))
    cmp = compare_versions()
    for wk, cards in sanity.items():
        print(f'== week ending {wk}')
        show(cards)
    print('== stress-event weeks with S <= 2 (or null)')
    for m in misses:
        print('  ', m)
    print('== 7.3.1 / 7.1 history summary')
    for r_ in ppq:
        print('  ', r_)
    print('== v1.1 vs v1.2')
    print(cmp.to_string(index=False))
    print('== needs_review = Y')
    for _, e in reg[reg.needs_review == 'Y'].iterrows():
        print(f'   {e.event_id} {e.chain_id} {e.title} ({e.effect_date}): {e.notes}')

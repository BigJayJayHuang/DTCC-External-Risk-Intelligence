"""Scoring v1.3-indicator for the 16 final cards (results/scoring/v1.3_indicator/SCORING_SPEC_v1.3.md).

    python -m validation.scoring_v1_3 coverage --week 2026-10-19 --week 2026-10-26   # D1 data guard, no scores
    python -m validation.scoring_v1_3 register --week 2026-10-19 --week 2026-10-26   # manual register, active flags
    python -m validation.scoring_v1_3 score --week 2026-10-26                        # refused while the spec is DRAFT

The v1.2 rules are reused, not copied: market S comes from scoring.percentile_scores / scoring_signal /
weekly_peaks, event S from scoring.active_events + apply_signoff + combine_s, and V from
final16_vulnerability.get_v. None of those files is changed, and validation/export.py is never called.
"""
import argparse, csv, json, re, sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import data as D
from . import event_scoring as E
from . import scoring as V12
from .final16_vulnerability import ROOT as FINAL16, get_v
from .paths import PROJECT, RESULTS
from .scoring import percentile_scores, scoring_signal, weekly_peaks  # noqa: F401  (weekly_peaks runs inside scoring_signal)

SPEC_VERSION = 'v1.3-indicator'
OUT = PROJECT / 'results' / 'scoring' / 'v1.3_indicator'
SPEC = OUT / 'SCORING_SPEC_v1.3.md'
LINES_CONFIG = OUT / 'config' / 'card_lines.csv'
REGISTRY = FINAL16 / 'config' / 'card_registry.json'
V_CHECKS = FINAL16 / 'results' / 'v_driver_checks.json'
NEWS_COVERAGE = 'manual_register_only'                 # default for a week not listed in NEWS_COVERAGE_FILE (Amendment F1)
NEWS_SCREENED = 'headline_level_ai_screen'
NEWS_COVERAGE_FILE = OUT / 'config' / 'news_coverage.csv'
CONTEXT_NEWS = PROJECT / 'data' / 'events' / 'context_news.csv'   # Amendment D: market-move news on indicator cards
SHOW_ON_MAIN_MIN = 6
SIGNOFF_MIN_S = 4
DASHBOARD_LINES = {'FICC', 'ECS', 'RDS', 'WIS', 'ITP', 'Asset Services', 'DAS', 'DDA', 'Data Services', 'Consulting'}
CONFIDENCE_ORDER = ['High', 'Medium', 'Low']

# D1: raw series behind each v1.2 signal field. MORTGAGE30US is weekly (Thursday survey); the rest are daily.
SIGNAL_SERIES = {
    'ust10_abs_change': ['DGS10'],
    'sofr_effr_adjusted': ['SOFR', 'EFFR'],
    'baa_widen20': ['BAA10Y'],
    'vix_jump': ['VIXCLS'],
    'mbs_spread_abs_wchg': ['MORTGAGE30US', 'DGS10'],
    'consolidated_shares': ['CBOE_CONSOLIDATED'],
}
WEEKLY_SERIES = {'MORTGAGE30US': 3}          # usual release weekday (Thursday); the actual release date counts
ENTITY_PREFIX = {'FICC-GSD': ['GSD'], 'FICC-MBSD': ['MBSD'], 'ECS-NSCC': ['NSCC'], 'ECS-DTC': ['DTC'], 'ECS-SET': ['NSCC', 'DTC']}
ENTITY_LINE = {'GSD': 'FICC', 'MBSD': 'FICC', 'NSCC': 'ECS', 'DTC': 'ECS'}
SOURCE_LABEL = {'market': 'market', 'events': 'event_manual', 'events (market null)': 'event_manual',
                'market=events': 'market+event_manual'}


# ------------------------------------------------------------------ weeks
def week_dates(week):
    """Monday label -> (Monday, Friday) as Timestamps."""
    monday = pd.Timestamp(week)
    if monday.dayofweek != 0:
        raise ValueError(f'week must be a Monday: {week}')
    return monday, monday + pd.Timedelta(days=4)


# ------------------------------------------------------------------ cards (registry + D2 line table)
def entities(component_ids):
    out = []
    for c in component_ids:
        prefix = '-'.join(c.split('-')[:2])
        for e in ENTITY_PREFIX.get(prefix, []):
            if e not in out:
                out.append(e)
    return out


def load_line_table(path=LINES_CONFIG):
    with Path(path).open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    table = {}
    for r in rows:
        table.setdefault(r['card_id'], []).append(r)
    return table


def check_line_table(table, card_ids):
    """Errors in the D2 line table (empty list = OK)."""
    errors = []
    for cid in card_ids:
        rows = table.get(cid, [])
        if not rows:
            errors.append(f'{cid}: no business-line row')
        if len({r['risk_family'] for r in rows}) > 1:
            errors.append(f'{cid}: risk_family differs between its rows')
        if len(rows) > 1 and (any(not r['id_suffix'] for r in rows) or len({r['id_suffix'] for r in rows}) < len(rows)):
            errors.append(f'{cid}: several rows need distinct non-empty id_suffix values')
        for r in rows:
            if r['business_line'] not in DASHBOARD_LINES:
                errors.append(f"{cid}: business_line {r['business_line']!r} is not a dashboard line")
    errors += [f'{cid}: row for a card not in the final16 registry' for cid in table if cid not in card_ids]
    return errors


def old_to_new(registry):
    """v1.2 / component / catalog card id -> final16 card id."""
    m = {'NSCC liquidity': 'ECS-NSCC-LIQ'}
    for r in registry:
        m[r['card_id']] = r['card_id']
        for c in r['component_ids']:
            m.setdefault(c, r['card_id'])
    return m


def load_cards(conf, registry=None, table=None):
    registry = registry or json.loads(REGISTRY.read_text())
    table = table or load_line_table()
    errors = check_line_table(table, [r['card_id'] for r in registry])
    if errors:
        raise ValueError('card_lines.csv: ' + '; '.join(errors))
    mapping = old_to_new(registry)
    cards = []
    for r in registry:
        comps = r['component_ids']
        tested = {c: conf[c]['confidence'] for c in comps if c in conf}
        ents = entities(comps)
        cards.append({
            'card_id': r['card_id'], 'title': r['name_en'], 'status_registry': r['status'], 'components': comps,
            'market_chains': [{'chain_id': c, 'field': conf[c]['signal']['field'], 'description': conf[c]['signal']['description']}
                              for c in comps if c in conf and conf[c]['signal']['field']],
            'entities': ents, 'cross_entity': len({ENTITY_LINE[e] for e in ents}) > 1,
            'legacy_v12_cards': [c for c in V12.CARD_ORDER if mapping.get(c) == r['card_id']],
            'lines': table[r['card_id']], 'risk_family': table[r['card_id']][0]['risk_family'], 'tested_chains': tested})
    return cards


def chain_confidence(tested, S, S_source, signal_chain, driving_event):
    """Resolved §11.1: the level of the chain that set S; lowest tested chain if S is null; Low if untested."""
    if not tested:
        return {'level': 'Low', 'rule': 'untested', 'chain_id': None, 'chains': {}}
    lowest = max(tested, key=lambda c: CONFIDENCE_ORDER.index(tested[c]))
    if S is None:
        chain, rule = lowest, 'lowest_tested_chain (S null)'
    elif S_source in ('market', 'market+event_manual'):
        chain, rule = signal_chain, 'signal_chain'
    else:
        chain = next((c for c in (driving_event or {}).get('card_ids', []) if c in tested), None)
        chain, rule = (chain, 'driving_event_chain') if chain else (lowest, 'lowest_tested_chain (driving event not on a tested chain)')
    return {'level': tested[chain], 'rule': rule, 'chain_id': chain, 'chains': tested}


# ------------------------------------------------------------------ D1 data guard
def coverage(fields, last_dates, week_end, release_dates=None):
    """Per raw series: last observation, the date it must reach for this week, ok.

    Daily series must reach the Friday. A weekly series must have its release inside the week (Mon-Fri); the required
    date is that actual release date (resolved §11.4: e.g. Wed 2026-11-25 in Thanksgiving week), or the usual
    weekday while no release for the week exists yet."""
    out, release_dates = {}, release_dates or {}
    monday = week_end - pd.Timedelta(days=4)
    for f in fields:
        for s in SIGNAL_SERIES[f]:
            last = last_dates.get(s)
            if s in WEEKLY_SERIES:
                dates = [pd.Timestamp(d) for d in release_dates.get(s, [last] if last is not None else [])]
                in_week = [d for d in dates if monday <= d <= week_end]
                need = max(in_week) if in_week else monday + pd.Timedelta(days=WEEKLY_SERIES[s])
                ok = bool(in_week)
                last = max(dates) if dates else last
            else:
                need = week_end
                ok = last is not None and pd.Timestamp(last) >= need
            out[s] = {'last_date': None if last is None else str(pd.Timestamp(last).date()),
                      'required_date': str(need.date()), 'ok': ok}
    return out


def series_last_dates():
    out = {s: D.fred(s).index.max() for s in ['SOFR', 'EFFR', 'DGS10', 'BAA10Y', 'VIXCLS', 'MORTGAGE30US']}
    out['CBOE_CONSOLIDATED'] = D.consolidated_volume().index.max()
    return out


def series_release_dates():
    return {s: list(D.fred(s).index) for s in WEEKLY_SERIES}


# ------------------------------------------------------------------ D4 manual-register event S (v1.2 logic)
def card_events(ranked, card_id, mapping):
    """v1.2 card_event_score() for a final16 card: ranked = active_events() rows after apply_signoff()."""
    mine = [r for r in ranked if card_id in {mapping.get(c) for c in r['card_ids']}]
    if not mine:
        return {'S': 1, 'method': 'rubric v1.2', 'reason': 'no active event', 'events': [], 'active_events': 0}
    d = mine[0]
    return {'S': d['S'], 'method': 'rubric v1.2', 'events': mine, 'driving_event_ids': [d['event_id']],
            'needs_review': d['needs_review'], 'rubric_version': E.RUBRIC_VERSION, 'active_events': len(mine)}


def ranked_events(reg, week_end):
    """v1.2 active_events() + apply_signoff(), plus register provenance (Amendment A4, display only)."""
    signoffs = {s.event_id: s for s in pd.read_csv(V12.SIGNOFFS, dtype=str).itertuples()} if V12.SIGNOFFS.exists() else {}
    events = {e.event_id: e for e in V12.register_events(reg)}
    entry = {r['event_id']: (r.get('entered_by', ''), r.get('review_status', '')) for r in reg.to_dict('records')}
    out = []
    for r in V12.active_events(reg, week_end):
        e = events[r['event_id']]
        entered_by, review_status = entry.get(r['event_id'], ('', ''))
        out.append({**V12.apply_signoff(r, signoffs), 'outlet': e.sources[0].get('outlet') if e.sources else None,
                    'source_tier': e.sources[0].get('tier') if e.sources else None, 'source_urls': [s['url'] for s in e.sources],
                    'entered_by': entered_by, 'review_status': review_status})
    return out


AI_UNREVIEWED_LABEL = 'AI-classified, not reviewed'


def ai_unreviewed(event: dict | None) -> bool:
    """Register rows promoted by promote_reviewed.py without a human decision (Amendment C, proposed)."""
    return bool(event) and (event.get('entered_by') == 'llm-auto' or event.get('review_status') == 'unreviewed')


# ------------------------------------------------------------------ Amendment A2: daily values behind a market S >= 4
def _week_of(index, friday):
    """Same week labelling as v1.2 weekly_peaks(): each observation belongs to the next Friday on or after it."""
    return (index + pd.to_timedelta((4 - index.dayofweek) % 7, unit='D')) == friday


def _obs(series, friday):
    s = series.dropna()
    return [{'date': str(d.date()), 'value': float(v)} for d, v in s[_week_of(s.index, friday)].items()]


def daily_info(field, friday):
    """Observations of the week behind the weekly peak, the raw inputs for those days, and the Cboe ratio denominator."""
    s = V12.SIGNALS[field]()
    info = {'daily_values': _obs(s, friday), 'daily_inputs': {}}
    if field == 'consolidated_shares':      # the signal is the raw series; S uses peak / median of prior 52 weekly peaks
        den = weekly_peaks(s).shift(1).rolling(52, min_periods=52).median().get(friday)
        info['ratio_denominator'] = None if den is None or pd.isna(den) else float(den)
    else:
        info['daily_inputs'] = {r: _obs(D.fred(r), friday) for r in SIGNAL_SERIES[field]}
    return info


def peak_check(value, info):
    vals = [d['value'] for d in info.get('daily_values', [])]
    if not vals or value is None:
        return False
    top = max(vals) / info['ratio_denominator'] if info.get('ratio_denominator') else max(vals)
    return abs(top - value) <= 1e-9 * max(1.0, abs(value))


# ------------------------------------------------------------------ Amendment A3 / B: shared signals
def s_fields(rec):
    """Signal fields a record takes S from (Amendment B1): every chain whose S equals S_market, when the market sets S."""
    if rec['S_source'] not in ('market', 'market+event_manual') or rec['S_market'] is None:
        return set()
    return {c['field'] for c in rec['market_chains'] if c['S'] == rec['S_market']}


def assign_shared(recs):
    """recs: one base record per card for one week. Adds shared_signal / shared_signal_fields in place (Amendment B2-B4)."""
    fields = {r['card_id']: s_fields(r) for r in recs}
    for r in recs:
        mine = fields[r['card_id']]
        common = {o: sorted(mine & f) for o, f in fields.items() if o != r['card_id'] and mine & f}
        r['shared_signal'] = sorted(common)
        r['shared_signal_fields'] = dict(sorted(common.items()))
    return recs


# ------------------------------------------------------------------ D5 V
def v_fields(v, check):
    flags = []
    if check.get('flag_corr_gt_0_7'):
        flags.append('corr_gt_0.7_with_S')
    if check.get('flag_v5_share_gt_0_5'):
        flags.append('V5_share_gt_0.5')
    if str(v.get('history_quality', '')).startswith('low'):
        flags.append('history_lt_8_quarters')
    if check.get('proxy_quality') == 'weak proxy':
        flags.append('weak_proxy')
    if check.get('detrended'):
        flags.append('detrended')
    if v.get('V_override_reason'):
        flags.append('V_override')
    return {'V': v.get('V'), 'V_base': v.get('V_base'), 'V_tier': v.get('v_source_tier'),
            'V_driver': check.get('driver') or v.get('vulnerability_metric'), 'V_metric': v.get('vulnerability_metric'),
            'V_quarter': v.get('quarter'), 'V_available_date': v.get('available_date'), 'V_flags': flags,
            'V_override_reason': v.get('V_override_reason'), 'V_caveats': v.get('caveats', []),
            'V_null_reason': v.get('reason') if v.get('V') is None else None}


# ------------------------------------------------------------------ one card-week
def load_context_news(path=CONTEXT_NEWS):
    """(week, card_id) -> related news rows (display only, Amendment D4)."""
    out = {}
    if Path(path).exists():
        with Path(path).open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                out.setdefault((r['week'], r['card_id']), []).append(
                    {k: r[k] for k in ('title', 'outlet', 'url', 'event_type', 'proposed_event_id')})
    return out


def load_news_coverage(path=NEWS_COVERAGE_FILE):
    """Amendment F1: week (Monday) -> news_coverage. Weeks not listed are manual_register_only."""
    out = {}
    if Path(path).exists():
        with Path(path).open(encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                if r['news_coverage'] not in (NEWS_COVERAGE, NEWS_SCREENED):
                    raise ValueError(f"{path}: unknown news_coverage {r['news_coverage']!r} for {r['week']}")
                out[r['week']] = r['news_coverage']
    return out


def card_week(card, week, *, market_recs, cov, ev, v, check, daily=None, related=None, news_coverage=NEWS_COVERAGE):
    """Base record for one card-week (before the D2 line split). All inputs are plain data."""
    monday, friday = week_dates(week)
    rec = {'card_id': card['card_id'], 'week': str(monday.date()), 'week_end': str(friday.date()),
           'spec_version': SPEC_VERSION, 'official': False, 'title': card['title'], 'card_status': card['status_registry'],
           'region': 'US', 'risk_family': card['risk_family'], 'cross_entity': card['cross_entity'],
           'entities': card['entities'], 'legacy_v12_cards': card['legacy_v12_cards'], 'news_coverage': news_coverage}
    missing = [f"{s} last {c['last_date']} < required {c['required_date']}" for s, c in cov.items() if not c['ok']]
    chains = []
    for mc in card['market_chains']:
        # D1: a partial week is never scored, so its partial weekly peak is not reported either
        r = {'S': None, 'reason': 'data_incomplete'} if missing else (market_recs.get(mc['chain_id']) or {'S': None, 'reason': 'no data this week'})
        chains.append({**mc, 'S': r.get('S'), 'weekly_peak': r.get('weekly_peak'), 'percentile': r.get('percentile'),
                       'prior_weeks': r.get('prior_weeks'), 'method': r.get('method'), 'reason': r.get('reason')})
    valid = [c for c in chains if c['S'] is not None]
    S_market = max(c['S'] for c in valid) if valid else None
    drv = next((c for c in valid if c['S'] == S_market), None)
    S_event = ev['S'] if ev['active_events'] else None

    if card['market_chains'] and missing and ev['active_events']:
        # resolved §11.2: incomplete market data but an active register event -> score from the event
        status, S, src, reason = 'scored', ev['S'], 'event_manual', 'market_data_incomplete'
    elif card['market_chains'] and missing:
        status, S, src, reason = 'data_incomplete', None, None, '; '.join(missing)
    elif card['market_chains'] and S_market is None and not ev['active_events']:
        status, S, src = 'data_incomplete', None, None
        reason = '; '.join(f"{c['chain_id']}: {c['reason']}" for c in chains)
    elif card['market_chains']:
        S, label = V12.combine_s(S_market, ev)
        status, src, reason = 'scored', SOURCE_LABEL[label], None
    elif ev['active_events']:
        status, S, src, reason = 'scored', ev['S'], 'event_manual', None
    elif news_coverage == NEWS_SCREENED:                # Amendment F2
        status, S, src = 'no_relevant_news', None, None
        reason = 'no market signal for this card and no active register event; the weekly headline-level news screen found no relevant news'
    else:
        status, S, src = 'news_not_scanned', None, None
        reason = 'no market signal for this card and no active manual-register event; news classifier not yet running'

    signal = None if drv is None else {'name': drv['field'], 'description': drv['description'], 'chain_id': drv['chain_id'],
                                       'value': drv['weekly_peak'], 'percentile': drv['percentile'],
                                       'prior_weeks': drv['prior_weeks'], 'method': drv['method']}
    if signal and S_market >= SIGNOFF_MIN_S:           # Amendment A2
        info = (daily or {}).get(drv['chain_id']) or {}
        signal.update(info)
        signal['peak_check'] = peak_check(drv['weekly_peak'], info)
        if not signal['peak_check']:
            raise ValueError(f"{card['card_id']} {week}: daily values do not reproduce the weekly peak of {drv['chain_id']}")
    driving = ev['events'][0] if ev['events'] else None
    event_set = src in ('event_manual', 'market+event_manual')     # Amendment A1
    vf = v_fields(v, check)
    sev = S * vf['V'] if (S is not None and vf['V'] is not None) else None
    rec.update({
        'status': status, 'status_reason': reason, 'S': S, 'S_source': src, 'S_market': S_market, 'S_event': S_event,
        'signal': signal, 'market_chains': chains, 'data_coverage': cov,
        'event_manual': {'active_events': ev['active_events'], 'driving_event_ids': ev.get('driving_event_ids', []),
                         'needs_review': ev.get('needs_review', False),
                         'events': [{k: e.get(k) for k in ('event_id', 'title', 'S', 'certainty', 'reach', 'timing', 'effect_date',
                                                           'needs_review', 'review_reasons', 'signed_off_by', 'outlet', 'source_tier',
                                                           'source_urls', 'entered_by', 'review_status')} for e in ev['events']]},
        **vf,
        'severity': sev,
        # Amendment C (proposed): an unreviewed AI-classified event that alone sets S keeps the card off the main page
        'show_on_main': sev is not None and sev >= SHOW_ON_MAIN_MIN and not (src == 'event_manual' and ai_unreviewed(driving)),
        'event_review_label': AI_UNREVIEWED_LABEL if src in ('event_manual', 'market+event_manual') and ai_unreviewed(driving) else None,
        'needs_human_signoff': bool(event_set and S is not None and S >= SIGNOFF_MIN_S and not (driving and driving.get('signed_off_by'))),
        'chain_confidence': chain_confidence(card['tested_chains'], S, src, drv['chain_id'] if drv else None, driving),
        'shared_signal': [], 'shared_signal_fields': {},
        'related_news': list(related or [])})
    return rec


def split_lines(rec, card):
    """D2: one record per business-line row; identical scores, id suffixed when the card has several rows."""
    out = []
    for row in card['lines']:
        rid = card['card_id'].lower() + (f"-{row['id_suffix']}" if row['id_suffix'] else '')
        out.append({'record_id': rid, 'business_line': row['business_line'], 'sub_line': row['sub_line'], **rec})
    return out


# ------------------------------------------------------------------ live assembly (used only by `score`)
def build_week(week, cards=None):
    monday, friday = week_dates(week)
    conf, reg = V12.load_chain_conf(), V12.load_register()
    cards = cards or load_cards(conf)
    registry = json.loads(REGISTRY.read_text())
    mapping, checks = old_to_new(registry), {c['card_id']: c for c in json.loads(V_CHECKS.read_text())['cards']}
    last, releases, ranked = series_last_dates(), series_release_dates(), ranked_events(reg, friday)
    pct = {mc['chain_id']: percentile_scores(scoring_signal(mc['chain_id'], mc['field'])) for c in cards for mc in c['market_chains']}
    daily = {mc['chain_id']: daily_info(mc['field'], friday) for c in cards for mc in c['market_chains']}
    related = load_context_news()
    news_coverage = load_news_coverage().get(str(monday.date()), NEWS_COVERAGE)
    base = [card_week(card, week, market_recs={k: pct[k].get(friday) for k in (mc['chain_id'] for mc in card['market_chains'])},
                      cov=coverage([mc['field'] for mc in card['market_chains']], last, friday, releases),
                      ev=card_events(ranked, card['card_id'], mapping),
                      v=get_v(card['card_id'], str(friday.date())), check=checks.get(card['card_id'], {}), daily=daily,
                      related=related.get((str(monday.date()), card['card_id']), []), news_coverage=news_coverage)
            for card in cards]
    assign_shared(base)
    return [r for rec, card in zip(base, cards) for r in split_lines(rec, card)]


def spec_approved(path=SPEC):
    return bool(re.search(r'^Status: \*\*APPROVED', Path(path).read_text(), re.M)) if Path(path).exists() else False


# ------------------------------------------------------------------ CLI
def _coverage_report(weeks):
    last, releases = series_last_dates(), series_release_dates()
    print(json.dumps({'last_dates': {s: str(d.date()) for s, d in last.items()},
                      'weeks': {w: coverage(list(SIGNAL_SERIES), last, week_dates(w)[1], releases) for w in weeks}}, indent=2))


def _register_report(weeks, registry=None):
    mapping = old_to_new(registry or json.loads(REGISTRY.read_text()))
    rows = []
    for ev in V12.load_events(V12.load_register()):
        rows.append({'event_id': ev.event_id, 'title': ev.title, 'card_ids': ev.card_ids,
                     'final16': sorted({mapping.get(c, '?') for c in ev.card_ids}),
                     'announced': str(ev.announced_date), 'effect': str(ev.effect_date), 'certainty': ev.certainty,
                     'reach': ev.reach, 'sources': ev.sources,
                     'active': {w: E.is_active(ev, week_dates(w)[0].date()) for w in weeks}})
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('command', choices=['coverage', 'register', 'score'])
    p.add_argument('--week', action='append', required=True, help='Monday, YYYY-MM-DD (repeatable)')
    a = p.parse_args(argv)
    for w in a.week:
        week_dates(w)
    if a.command == 'coverage':
        return _coverage_report(a.week)
    if a.command == 'register':
        return _register_report(a.week)
    if not spec_approved(SPEC):
        raise SystemExit(f'{SPEC} is not APPROVED; v1.3 scores are not produced while the spec is DRAFT.')
    text = SPEC.read_text()
    status = re.search(r'^Status: (.*)$', text, re.M).group(1)
    amendments = [{'amendment': a, 'approved': who} for a, who in re.findall(r'^## Amendment (\w+)[^\n]*\n\nApproved: ([^.\n]+)', text, re.M)]
    OUT.mkdir(parents=True, exist_ok=True)
    for w in a.week:
        recs = [{**r, 'official': True} for r in build_week(w)]
        doc = {'spec': 'results/scoring/v1.3_indicator/SCORING_SPEC_v1.3.md', 'spec_status': status, 'spec_amendments': amendments,
               'spec_version': SPEC_VERSION,
               'rubric_version': E.RUBRIC_VERSION, 'week': w, 'week_end': str(week_dates(w)[1].date()),
               'run_utc': pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%dT%H:%MZ'),
               'news_coverage': load_news_coverage().get(w, NEWS_COVERAGE), 'records': recs}
        path = OUT / f'weekly_scores_v1.3_{w}.json'
        path.write_text(json.dumps(V12._clean(doc), indent=2, ensure_ascii=False) + '\n')
        print(path.relative_to(PROJECT), len(recs), 'records')


if __name__ == '__main__':
    sys.exit(main())

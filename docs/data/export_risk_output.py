#!/usr/bin/env python3
"""Build docs/data/risk_output.json from the scoring v1.3-indicator weekly files.

Usage (from the repo root):  python3 docs/data/export_risk_output.py [--week 2026-10-19 --week 2026-10-26 --week 2026-11-02]
Then check it:               python3 docs/data/validate_output.py docs/data/risk_output.json

Standard library only. Every text field is a fixed template filled with numbers, ids, dates and URLs from the
scoring records, the chain registry and the source manifests; no prose is generated. All v1.3 record fields are
kept on each item as extra fields. so_what and so_now_what are reserved for future AI text: they are null, with
analysis_status = "pending_llm"; no placeholder text is written into the data. Output is deterministic for the same inputs.
related_news (Amendment D4/E3) is passed through from the scoring records; ai_unreviewed_events lists the active register events
on the card that are AI-classified and not reviewed (Amendment C1), whether or not they set S.
"""
import argparse, csv, hashlib, json, runpy
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CP = REPO / 'Capstone_Project'
V13 = CP / 'results' / 'scoring' / 'v1.3_indicator'
CARD_REGISTRY = CP / 'risk_business_ml' / 'final16_quarterly_vulnerability_2026_10_27' / 'config' / 'card_registry.json'
FINAL16_CONFIG = CP / 'risk_business_ml' / 'final16_quarterly_vulnerability_2026_10_27' / 'src' / 'config.py'
CHAIN_REGISTRY = CP / 'risk_business_ml' / 'new_reference_chain_tests_2026_10_21' / 'chain_registry_v3_with_test_status.json'
PQD_MANIFEST = CP / 'risk_business_ml' / 'event_vulnerability_tests_2026_10_06' / 'source_manifest.json'
OUT = REPO / 'docs' / 'data' / 'risk_output.json'
WEEKS = ['2026-10-19', '2026-10-26', '2026-11-02']
AI_UNREVIEWED_LABEL = 'AI-classified, not reviewed'

# Real calendar dates only (lines.*.coming).
COMING = {
    'FICC': [{'date': '2026-12-31', 'title': 'Treasury clearing compliance: eligible cash transactions'},
             {'date': '2027-06-30', 'title': 'Treasury clearing compliance: eligible repo transactions'}],
    'ECS': [{'date': '2026-12-18', 'title': 'Triple witching'}],
    'ITP': [{'date': '2027-10-11', 'title': 'EU move to T+1 settlement'}],
}

# Fixed templates per v1.2 signal field: (label, unit, number format)
SIGNAL_TEXT = {
    'ust10_abs_change': ('Weekly peak absolute daily change in the 10-year Treasury yield', ' bp', '{:.0f}'),
    'sofr_effr_adjusted': ('Weekly peak SOFR–EFFR spread (quarter-end adjusted)', ' bp', '{:.0f}'),
    'baa_widen20': ('Weekly peak 20-day widening of the Baa–10-year Treasury spread', ' bp', '{:.0f}'),
    'vix_jump': ('Weekly peak VIX relative to its 20-day average', '×', '{:.2f}'),
    'mbs_spread_abs_wchg': ('Weekly change in the 30-year mortgage rate minus 10-year Treasury spread', ' bp', '{:.0f}'),
    'consolidated_shares': ('Weekly peak US consolidated equity volume relative to the median of the prior 52 weekly peaks', '×', '{:.2f}'),
}
SERIES_SOURCE = {
    'CBOE_CONSOLIDATED': ('Cboe U.S. equities market volume history', 'https://www.cboe.com/us/equities/market_statistics/historical_market_volume/'),
}
SIGNAL_SERIES = {'ust10_abs_change': ['DGS10'], 'sofr_effr_adjusted': ['SOFR', 'EFFR'], 'baa_widen20': ['BAA10Y'],
                 'vix_jump': ['VIXCLS'], 'mbs_spread_abs_wchg': ['MORTGAGE30US', 'DGS10'], 'consolidated_shares': ['CBOE_CONSOLIDATED']}
SHOCK_METHOD = {'market': 'Market indicator', 'event_manual': 'Event rubric (hand-entered register)',
                'market+event_manual': 'Market indicator and event rubric (equal)'}
TIER_TEXT = {'pqd': 'DTCC public quantitative disclosure (PQD)', 'public_proxy': 'public proxy series, not DTCC data'}
NOT_SCORED = {
    'news_not_scanned': 'Not scored: no market indicator for this card and no active hand-entered event; news is not yet scanned.',
    'data_incomplete': 'Not scored: market data for this week is incomplete ({reason}).',
    'no_relevant_news': ('Not scored: no market indicator for this card and no active register event; '
                         'the weekly headline-level news screen found no relevant news.'),        # Amendment F
}


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def market_text(sig):
    label, unit, fmt = SIGNAL_TEXT[sig['name']]
    if str(sig.get('method') or '').startswith('floor'):
        return f"{label} {fmt.format(sig['value'])}{unit}: at or below zero, so S = 1 (floor rule)"
    return f"{label} {fmt.format(sig['value'])}{unit}, {ordinal(round(sig['percentile'] * 100))} percentile of {sig['prior_weeks']} prior weeks"


def event_text(e):
    url = (e.get('source_urls') or [''])[0]
    return f"Hand-entered event {e['event_id']}: {e['title']}, effective {e['effect_date']}, source {e.get('outlet') or 'register'}: {url}"


def rubric_text(e):
    return (f"Event {e['event_id']}: certainty {e['certainty']} + reach {e['reach']} + timing {e['timing']} "
            f"= {e['certainty'] + e['reach'] + e['timing']} → S {e['S']} (rubric v1.2)")


def driving_event(r):
    ids = r['event_manual']['driving_event_ids']
    return next((e for e in r['event_manual']['events'] if ids and e['event_id'] == ids[0]), None)


def texts(r):
    """(what_happened, shock_basis) from fixed templates."""
    if r['status'] != 'scored':
        t = NOT_SCORED[r['status']].format(reason=r.get('status_reason') or '')
        return t, t
    e, sig = driving_event(r), r['signal']
    if r['S_source'] == 'market':
        return market_text(sig), market_text(sig)
    if r['S_source'] == 'market+event_manual':
        return f"{market_text(sig)}; {event_text(e)}", f"{market_text(sig)}; {rubric_text(e)}"
    suffix = ' (market data incomplete this week)' if r.get('status_reason') == 'market_data_incomplete' else ''
    return event_text(e) + suffix, rubric_text(e) + suffix


def transmission(r, cards, chains):
    """Chain steps: the chain that set S, else the card's first component chain on this business line."""
    cc = r['chain_confidence']
    cid = cc['chain_id'] if cc.get('rule') in ('signal_chain', 'driving_event_chain') else None
    if not cid:
        comps = cards[r['card_id']]['component_ids']
        cid = next((c for c in comps if c.split('-')[0] == r['business_line']), comps[0])
    c = chains[cid]
    return cid, {'event': c['world_event']['EN'], 'mechanism': c['mechanism']['EN'], 'dtcc_process': c['dtcc_process']['EN']}


def sources(r, proxy, pqd_urls):
    out = []
    for mc in r['market_chains']:
        for s in SIGNAL_SERIES[mc['field']]:
            name, url = SERIES_SOURCE.get(s, (f'FRED: {s}', f'https://fred.stlouisfed.org/series/{s}'))
            out.append({'name': name, 'url': url})
    by_url = {}
    for e in r['event_manual']['events']:
        for u in e.get('source_urls') or []:
            by_url.setdefault(u, [e.get('outlet') or 'Source', []])[1].append(e['event_id'])
    out += [{'name': f"{outlet} ({', '.join(ids)})", 'url': u} for u, (outlet, ids) in by_url.items()]
    if r['V_tier'] == 'pqd':
        period = r['V_quarter'][:4] + ' Q' + r['V_quarter'][-1]
        out.append({'name': f'DTCC CPMI-IOSCO public quantitative disclosure, {period}', 'url': pqd_urls.get(period, '')})
    elif r['V_tier'] == 'public_proxy' and r['card_id'] in proxy:
        out.append({'name': proxy[r['card_id']]['source'], 'url': proxy[r['card_id']]['source_url']})
    seen, uniq = set(), []
    for s in out:                                  # one entry per URL (first name wins)
        if s['url'] not in seen:
            seen.add(s['url']); uniq.append(s)
    return uniq


def review_status(r):
    e = driving_event(r)
    if r['needs_human_signoff']:
        return 'Pending human sign-off'
    if e and e.get('signed_off_by') and r['S_source'] in ('event_manual', 'market+event_manual'):
        return f"Event {e['event_id']} signed off by {e['signed_off_by']}"
    return None


def ai_unreviewed_events(r):
    """Amendment C1: active register events on this card entered by llm-auto or still unreviewed."""
    return [e['event_id'] for e in r['event_manual']['events']
            if e.get('entered_by') == 'llm-auto' or e.get('review_status') == 'unreviewed']


def item(r, run_utc, cards, chains, proxy, pqd_urls):
    what, basis = texts(r)
    tchain, tr = transmission(r, cards, chains)
    it = dict(r)                                   # every v1.3 field is kept
    it.update({
        'id': r['record_id'], 'snapshot': r['week'], 'business_line': r['business_line'], 'sub_line': r['sub_line'],
        'region': r['region'], 'risk_family': r['risk_family'], 'title': r['title'],
        'shock': r['S'], 'vulnerability': r['V'], 'confidence': r['chain_confidence']['level'], 'updated_at': run_utc,
        'what_happened': what, 'shock_basis': basis,
        'vulnerability_basis': (f"{r['V_driver']}; {r['V_quarter']}; {TIER_TEXT.get(r['V_tier'], r['V_tier'])}"
                                if r['V'] is not None else (r.get('V_null_reason') or '')),
        'transmission': tr, 'transmission_chain_id': tchain,
        'sources': sources(r, proxy, pqd_urls), 'ai_generated_fields': [],
        'so_what': None, 'so_now_what': None, 'analysis_status': 'pending_llm',   # slots reserved for the LLM step
        'related_news': r.get('related_news') or [], 'ai_unreviewed_events': ai_unreviewed_events(r)})
    # display label: also when an unreviewed AI event is active on the card without setting S (event_review_label is kept as scored)
    it['ai_review_label'] = AI_UNREVIEWED_LABEL if (it['ai_unreviewed_events'] or r.get('event_review_label')) else None
    if r['S_source']:
        it['shock_method'] = SHOCK_METHOD[r['S_source']]
    rs = review_status(r)
    if rs:
        it['review_status'] = rs
    return it


def summary(items):
    scored = [i for i in items if i['status'] == 'scored']
    main = sum(1 for i in scored if i['show_on_main'])
    ns = sum(1 for i in items if i['status'] == 'news_not_scanned')
    nr = sum(1 for i in items if i['status'] == 'no_relevant_news')
    di = sum(1 for i in items if i['status'] == 'data_incomplete')
    s = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    text = f"{main} of {s(len(scored), 'scored card')} at severity ≥ 6"
    if ns or not nr:                               # weeks before the news run keep their original wording
        text += f"; {s(ns, 'card')} not yet scanned for news"
    if nr:
        text += f"; {s(nr, 'card')} with no relevant news found (headline-level scan)"
    return text + (f"; {s(di, 'card')} with incomplete market data." if di else '.')


def iso(run_utc):
    return run_utc[:-1] + ':00Z' if len(run_utc) == 17 and run_utc.endswith('Z') else run_utc


def build(weeks):
    docs = [json.loads((V13 / f'weekly_scores_v1.3_{w}.json').read_text()) for w in weeks]
    cards = {c['card_id']: c for c in json.loads(CARD_REGISTRY.read_text())}
    chains = {c['chain_id']: c for c in json.loads(CHAIN_REGISTRY.read_text())['chains']}
    proxy = runpy.run_path(str(FINAL16_CONFIG))['PUBLIC_PROXY']
    pqd_urls = {m['reporting_period']: (m.get('source_urls') or [''])[0]
                for m in json.loads(PQD_MANIFEST.read_text()) if m.get('document_kind') == 'public_quantitative_disclosure'}
    items = [item(r, iso(d['run_utc']), cards, chains, proxy, pqd_urls) for d in docs for r in d['records']]
    lines = {}
    for line in sorted({i['business_line'] for i in items} | set(COMING)):
        entry = {'review': []}
        mine = [i for i in items if i['business_line'] == line]
        if mine:
            entry['summary'] = {w: summary([i for i in mine if i['snapshot'] == w]) for w in weeks}
        if line in COMING:
            entry['coming'] = COMING[line]
        lines[line] = entry
    label = lambda w: 'Week of ' + date.fromisoformat(w).strftime('%b %-d, %Y')
    latest = max(docs, key=lambda d: d['week'])                       # spec metadata of the latest scored week
    by_week = {d['week']: d for d in docs}
    return {
        'schema_version': '1.0', 'generated_at': max(iso(d['run_utc']) for d in docs), 'model_version': 'v1.3-indicator',
        'sample': False, 'news_coverage': latest.get('news_coverage', 'manual_register_only'),   # latest week (Amendment F1)
        'spec': latest['spec'], 'spec_status': latest['spec_status'].replace('**', ''), 'spec_amendments': latest.get('spec_amendments', []),
        'source_files': [{'file': str((V13 / f'weekly_scores_v1.3_{w}.json').relative_to(REPO)),
                          'sha256': hashlib.sha256((V13 / f'weekly_scores_v1.3_{w}.json').read_bytes()).hexdigest()} for w in weeks],
        'snapshots': [{'id': w, 'date': w, 'label': label(w), 'news_coverage': by_week[w].get('news_coverage', 'manual_register_only')}
                      for w in sorted(weeks, reverse=True)],
        'lines': lines, 'items': items}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--week', action='append', help='Monday, YYYY-MM-DD (repeatable); default: ' + ', '.join(WEEKS))
    p.add_argument('--out', type=Path, default=OUT)
    a = p.parse_args()
    data = build(a.week or WEEKS)
    a.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{a.out}: {len(data['items'])} items, {len(data['snapshots'])} snapshots")


if __name__ == '__main__':
    main()

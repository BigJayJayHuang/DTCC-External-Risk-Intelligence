"""Worked examples from "Event Ranking Method (Rubric v1.2)", 2026-10-22 (scoring week Oct 19–23, 2026).

    python -m validation.test_event_scoring
"""
from datetime import date

from .event_scoring import Event, validate, event_score

WEEK = date(2026, 10, 19)
CATALOG = {'FICC-GSD-03', 'ECS-SET-01', 'XE-MEMBER'}
MAJOR = {'JPMorgan Chase'}


def ev(**kw):
    base = dict(event_id='T', card_ids=['FICC-GSD-03'], title='t', announced_date=date(2025, 2, 25), effect_date=WEEK,
                certainty=2, reach=2, evidence_quotes=['quote'], sources=[{'outlet': 'SEC', 'tier': 'regulator'}])
    return Event(**{**base, **kw})


def check(e, text, S, certainty, reach, timing):
    r = event_score(validate(e, [text], CATALOG, MAJOR), WEEK)
    assert (r['S'], r['certainty'], r['reach'], r['timing']) == (S, certainty, reach, timing), r
    return r


def test_examples():
    # 1. Cash Treasury clearing deadline, SEC final rule: 2 + 2 + 1 = 5 -> S 4, human check
    r = check(ev(effect_date=date(2026, 12, 31)), 'quote', 4, 2, 2, 1)
    assert r['needs_review']
    # 2. Blog post on T+0 discussion: 0 + 2 + 2 = 4 -> 3, certainty-0 cap -> 2
    r = check(ev(card_ids=['ECS-SET-01'], certainty=0, announced_date=WEEK, sources=[{'outlet': 'blog', 'tier': 'other'}]),
              'quote', 2, 0, 2, 2)
    assert 'certainty=0 cap' in r['caps']
    # 3. Special charge on a small broker, one Reuters story, LLM called it major: certainty and reach capped at 1 -> 4 -> S 3
    check(ev(card_ids=['XE-MEMBER'], announced_date=WEEK, sources=[{'outlet': 'Reuters', 'tier': 'major_media'}],
             reach_basis='major_participant', named_participants=['Small Broker LLC']), 'quote', 3, 1, 1, 2)
    # 4. DTCC notice: ceased to act for a member on Oct 1 (stage 3): 2 + 1 + 2 = 5 -> 4, stage-3 floor 4
    check(ev(card_ids=['XE-MEMBER'], announced_date=date(2026, 10, 1), effect_date=date(2026, 10, 1), reach=1, stage=3,
             sources=[{'outlet': 'DTCC', 'tier': 'dtcc'}]), 'quote', 4, 2, 1, 2)
    # quote not in the article -> flagged, levels unchanged
    r = check(ev(effect_date=date(2026, 12, 31)), 'other text', 4, 2, 2, 1)
    assert any('verbatim' in x for x in r['review_reasons'])


if __name__ == '__main__':
    test_examples()
    print('event_scoring worked examples: OK')

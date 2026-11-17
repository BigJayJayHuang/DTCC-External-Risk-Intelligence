"""DAS-05 public schedule-access proxy, separate from internal and accepted V.

This is a deterministic reconstruction of a documented weekly rule. It is not
operating telemetry, capacity, completion latency, or a historical data vintage.
No network access, paid API, accepted-event, or production-score writes occur.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / 'proxy_v'
NY = ZoneInfo('America/New_York')
UTC = timezone.utc
FIRST_DAY = date(2026, 10, 29)
POLICY_ID = 'DAS05-CONVERSION-ACCESS-PROXY-v0.1'


def parse_instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timestamp must include a UTC offset or timezone')
    return value.astimezone(UTC)


def candidate_score(wait_hours):
    if isinstance(wait_hours, bool) or not isinstance(wait_hours, (int, float)):
        raise ValueError('Wait must be a finite nonnegative number')
    if not math.isfinite(wait_hours) or wait_hours < 0:
        raise ValueError('Wait must be a finite nonnegative number')
    if wait_hours == 0:
        return 1
    for bound, score in ((8, 2), (24, 3), (48, 4)):
        if wait_hours <= bound:
            return score
    return 5


def _day_windows(day, override=None):
    windows = override if override is not None else ([['02:00', '18:00']] if day.weekday() < 5 else [])
    result = []
    last_end = None
    if not isinstance(windows, list):
        raise ValueError('Calendar windows must be a list')
    for pair in windows:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('Each window needs opening and closing HH:MM')
        opening, closing = [time.fromisoformat(t) for t in pair]
        if any(t.tzinfo is not None or t.second or t.microsecond for t in (opening, closing)):
            raise ValueError('Use timezone-free HH:MM boundaries')
        if opening >= closing or (last_end is not None and opening < last_end):
            raise ValueError('Windows must be ordered, nonoverlapping, and within one day')
        start = datetime.combine(day, opening, NY).astimezone(UTC)
        end = datetime.combine(day, closing, NY).astimezone(UTC)
        # A future override must not silently use a nonexistent or ambiguous DST boundary.
        for local_time, stamp in ((opening, start), (closing, end)):
            local = datetime.combine(day, local_time, NY)
            if stamp.astimezone(NY).replace(tzinfo=None) != local.replace(tzinfo=None):
                raise ValueError('Nonexistent local calendar boundary')
            if local.utcoffset() != local.replace(fold=1).utcoffset():
                raise ValueError('Ambiguous local calendar boundary')
        result.append((start, end))
        last_end = closing
    return result


def baseline_access(at):
    instant = parse_instant(at)
    day = instant.astimezone(NY).date()
    for step in range(8):
        for opening, closing in _day_windows(day + timedelta(days=step)):
            if instant < closing:
                next_open = max(instant, opening)
                return dict(baseline_wait_hours=(next_open - instant).total_seconds() / 3600,
                            baseline_next_open_local=next_open.astimezone(NY).isoformat(),
                            baseline_submission_window_open=opening <= instant < closing)
    raise RuntimeError('Weekly baseline has no next opening')


def _official_url(url):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    return parsed.scheme == 'https' and (host == 'dtcc.com' or host.endswith('.dtcc.com')
        or host == 'dtcclearning.com' or host.endswith('.dtcclearning.com') or host == 'dtcc-da.com')


def confirmed_calendar_access(at, calendar):
    """Only a separately reviewed, completely covered DTS calendar may refine baseline.

    A list of isolated closures does not establish that all unlisted dates are open.
    Nothing in the supplied configuration currently meets this gate.
    """
    absent = dict(calendar_confirmed_wait_hours=None, calendar_confirmed_next_open_local=None,
                  calendar_status='UNCONFIRMED_HOLIDAYS_AND_SPECIAL_HOURS')
    if not calendar or calendar.get('review_status') != 'REVIEWED_OFFICIAL_DTS_CONVERSION_CALENDAR':
        return absent
    if calendar.get('scope') != 'DTS_CONVERSION_ORDER_SUBMISSION':
        return dict(absent, calendar_status='CALENDAR_SCOPE_NOT_APPLICABLE')
    if not _official_url(calendar.get('coverage_source_url')):
        return dict(absent, calendar_status='CALENDAR_SOURCE_NOT_SUPPORTED')
    try:
        first = date.fromisoformat(calendar['coverage_start'])
        last = date.fromisoformat(calendar['coverage_end'])
        known_at = parse_instant(calendar['coverage_published_at'])
    except (KeyError, TypeError, ValueError):
        return dict(absent, calendar_status='CALENDAR_COVERAGE_INCOMPLETE')
    instant = parse_instant(at)
    day = instant.astimezone(NY).date()
    if known_at > instant:
        return dict(absent, calendar_status='CALENDAR_NOT_KNOWN_AT_QUERY_TIME')
    if first > day or last < day or first > last:
        return dict(absent, calendar_status='QUERY_OUTSIDE_CALENDAR_COVERAGE')
    entries = calendar.get('days', {})
    if not isinstance(entries, dict):
        raise ValueError('Calendar days must be an object')
    for step in range(min((last - day).days + 1, 367)):
        candidate_day = day + timedelta(days=step)
        override = entries.get(candidate_day.isoformat())
        if override is not None:
            if not isinstance(override, dict) or not _official_url(override.get('source_url')):
                return dict(absent, calendar_status='DAY_OVERRIDE_SOURCE_NOT_SUPPORTED')
            try:
                published = parse_instant(override['published_at'])
            except (KeyError, TypeError, ValueError):
                return dict(absent, calendar_status='DAY_OVERRIDE_PUBLICATION_MISSING')
            if published > instant:
                return dict(absent, calendar_status='DAY_OVERRIDE_NOT_KNOWN_AT_QUERY_TIME')
            if 'windows' not in override:
                raise ValueError('A dated override requires windows, including [] for closure')
        for opening, closing in _day_windows(candidate_day, override['windows'] if override is not None else None):
            if instant < closing:
                next_open = max(instant, opening)
                return dict(calendar_confirmed_wait_hours=(next_open - instant).total_seconds() / 3600,
                            calendar_confirmed_next_open_local=next_open.astimezone(NY).isoformat(),
                            calendar_status='RESEARCH_REVIEWED_CALENDAR_CONDITIONAL_ON_INPUT')
    return dict(absent, calendar_status='NEXT_OPENING_OUTSIDE_CALENDAR_COVERAGE')


def evaluate(at, *, calendar=None, policy=None):
    instant = parse_instant(at)
    local = instant.astimezone(NY)
    first = max(FIRST_DAY, date.fromisoformat(policy['first_supported_local_date'])) if policy else FIRST_DAY
    result = dict(card_id='DAS-05', business_line='DAS', policy_id=POLICY_ID,
                  observation_at_utc=instant.isoformat(), observation_at_et=local.isoformat(),
                  observation_date=instant.isoformat(),
                  measurement_type='PUBLIC_RULE_DERIVED_WEEKLY_BASELINE',
                  score_status='PROPOSED_FIXED_BINS_NOT_EMPIRICALLY_CALIBRATED',
                  calendar_status='UNCONFIRMED_HOLIDAYS_AND_SPECIAL_HOURS',
                  internal_V=None, accepted_proxy_V=None, risk_score=None,
                  service_health=None, event_applicability='NOT_ASSESSED',
                  actual_submission_or_completion_delay_hours=None,
                  historical_point_in_time_verified=False, operating_telemetry=False,
                  is_simulated_operating_data=False, quarterly_internal_v_replacement=False,
                  baseline_wait_hours=None, baseline_next_open_local=None,
                  baseline_submission_window_open=None, candidate_proxy_v_score_1_5=None,
                  calendar_confirmed_wait_hours=None, calendar_confirmed_next_open_local=None)
    if local.date() < first:
        return dict(result, state='BEFORE_SUPPORTED_BASELINE')
    result.update(baseline_access(instant))
    result.update(confirmed_calendar_access(instant, calendar))
    result['candidate_proxy_v_score_1_5'] = candidate_score(result['baseline_wait_hours'])
    result['state'] = 'RESEARCH_BASELINE_ONLY'
    return result


def load_inputs(root=ROOT):
    from build_monitor import read_source, norm
    root = Path(root)
    policy_path = root / 'proxy_v/config/policy.json'
    policy = json.loads(policy_path.read_text())
    if (policy['policy_id'] != POLICY_ID or policy['opening_local_time'] != '02:00'
            or policy['closing_local_time'] != '18:00' or policy['timezone'] != NY.key
            or policy['closing_inclusive'] or not policy['opening_inclusive']
            or policy['official_scoring_enabled']
            or policy['first_supported_local_date'] != FIRST_DAY.isoformat()
            or policy['score_bins'] != [
                {'score': 1, 'wait_hours': '0'}, {'score': 2, 'wait_hours': '(0, 8]'},
                {'score': 3, 'wait_hours': '(8, 24]'}, {'score': 4, 'wait_hours': '(24, 48]'},
                {'score': 5, 'wait_hours': '(48, infinity)'}]):
        raise ValueError('Policy and engine disagree; create and review a new version')
    manifest = json.loads((root / 'inputs/source_manifest.json').read_text())
    sources = {s['source_id']: s for s in manifest}
    evidence = []
    for sid, quote in ((policy['source_id'], policy['hours_quote']),
                       (policy['holiday_source_id'], policy['holiday_quote'])):
        source = sources[sid]
        text = read_source(root, source)
        if text is None or norm(quote) not in norm(text):
            raise ValueError('Policy evidence missing or changed: ' + sid)
        evidence.append(dict(source_id=sid, url=source['url'], quote=quote,
                             text_sha256=source['text_sha256'],
                             collected_at_utc=source['collected_at_utc'],
                             publication_date=source.get('publication_date')))
    calendar = json.loads((root / 'proxy_v/config/calendar_overrides.json').read_text())
    return policy, calendar, evidence, [sources[s['source_id']] for s in evidence]


def _hourly_series(first, as_of, calendar, policy):
    point = datetime.combine(first, time.min, NY).astimezone(UTC)
    result = []
    while point <= as_of:
        result.append(dict(evaluate(point, calendar=calendar, policy=policy), sampling='HOURLY_UTC_GRID'))
        point += timedelta(hours=1)
    return result


def _daily_series(first, as_of, calendar, policy):
    result = []
    day = first
    while day <= as_of.astimezone(NY).date():
        point = datetime.combine(day, time(8), NY).astimezone(UTC)
        if point <= as_of:
            result.append(dict(evaluate(point, calendar=calendar, policy=policy), sampling='DAILY_FIXED_0800_ET'))
        day += timedelta(days=1)
    return result


def _scenarios(calendar, policy):
    # Explicit hypothetical examples, never accepted events or database observations.
    specs = [('EXAMPLE-OPEN', '2026-11-13T17:00:00-05:00'),
             ('EXAMPLE-FRIDAY-CLOSED', '2026-11-13T19:00:00-05:00'),
             ('EXAMPLE-SUNDAY', '2026-11-15T08:00:00-05:00')]
    result = []
    for sid, stamp in specs:
        row = evaluate(stamp, calendar=calendar, policy=policy)
        result.append(dict(row, scenario_id=sid, record_type='HYPOTHETICAL_SCENARIO_NOT_AN_EVENT',
                           assumed_requires_conversion=True, assumed_shock_score=3,
                           illustrative_priority_index=3 * row['candidate_proxy_v_score_1_5'],
                           priority_index_status='ORDINAL_RESEARCH_ILLUSTRATION_NOT_LOSS_OR_PROBABILITY'))
    return result


def write_csv(path, rows):
    if not rows:
        path.write_text('observation_at_utc,baseline_wait_hours\n', encoding='utf-8-sig')
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def _write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def build_proxy(*, as_of, start=FIRST_DAY, root=ROOT):
    root = Path(root)
    as_of = parse_instant(as_of)
    policy, calendar, evidence, sources = load_inputs(root)
    first = max(start, date.fromisoformat(policy['first_supported_local_date']))
    if first > as_of.astimezone(NY).date():
        raise ValueError('No supported dates in requested series')
    for source in sources:
        if parse_instant(source['collected_at_utc']) > as_of:
            raise ValueError('As-of predates current evidence collection; no historical vintage claim allowed')
    hourly = _hourly_series(first, as_of, calendar, policy)
    daily = _daily_series(first, as_of, calendar, policy)
    snapshot = evaluate(as_of, calendar=calendar, policy=policy)
    scenarios = _scenarios(calendar, policy)
    # These are partial-quarter sample descriptions, never a quarterly buffer V.
    quarters = {}
    for row in hourly:
        d = datetime.fromisoformat(row['observation_at_et'])
        quarters.setdefault(f'{d.year}Q{(d.month-1)//3+1}', []).append(row)
    quarterly = [dict(quarter=q, sample_count=len(rows),
                       first_sample_at_et=rows[0]['observation_at_et'],
                       last_sample_at_et=rows[-1]['observation_at_et'],
                       mean_sampled_baseline_wait_hours=sum(r['baseline_wait_hours'] for r in rows) / len(rows),
                       maximum_sampled_baseline_wait_hours=max(r['baseline_wait_hours'] for r in rows),
                       baseline_closed_sample_share=sum(not r['baseline_submission_window_open'] for r in rows) / len(rows),
                       coverage='PARTIAL_QUARTER_POST_NOTICE_BASELINE_ONLY',
                       internal_V=None, accepted_proxy_V=None, risk_score=None,
                       historical_point_in_time_verified=False)
                 for q, rows in quarters.items()]
    output = root / 'proxy_v/results'
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / 'snapshot.json', snapshot)
    _write_json(output / 'source_evidence.json', dict(evidence=evidence,
        policy_sha256=hashlib.sha256((root / 'proxy_v/config/policy.json').read_bytes()).hexdigest(),
        calendar_sha256=hashlib.sha256((root / 'proxy_v/config/calendar_overrides.json').read_bytes()).hexdigest()))
    write_csv(output / 'hourly_proxy.csv', hourly)
    write_csv(output / 'daily_0800_et_proxy.csv', daily)
    write_csv(output / 'quarterly_descriptive_summary.csv', quarterly)
    write_csv(output / 'hypothetical_scenarios.csv', scenarios)
    metrics = []
    for rows, metric_id in ((hourly, 'das05_conversion_access_hourly'),
                            (daily, 'das05_conversion_access_daily_0800_et'),
                            ([snapshot], 'das05_conversion_access_snapshot')):
        for row in rows:
            metrics.append(dict(row, metric_id=metric_id, value=row['baseline_wait_hours'],
                                unit='hours_until_nominal_order_submission_window',
                                source_ids=[s['source_id'] for s in sources]))
    _write_json(output / 'database_payload.json', dict(sources=sources, metrics=metrics))
    summary = dict(as_of_timestamp_utc=as_of.isoformat(), as_of_timestamp_et=as_of.astimezone(NY).isoformat(),
                   policy_id=POLICY_ID, status='RESEARCH_PUBLIC_PROXY_NOT_ACCEPTED_INTERNAL_V',
                   start_local_date=first.isoformat(), hourly_rows=len(hourly), daily_rows=len(daily),
                   hypothetical_scenarios=len(scenarios), quarter_summaries=quarterly,
                   current_baseline_wait_hours=snapshot['baseline_wait_hours'],
                   current_candidate_proxy_v_score_1_5=snapshot['candidate_proxy_v_score_1_5'],
                   maximum_sampled_baseline_wait_hours=max(r['baseline_wait_hours'] for r in hourly),
                   calendar_status=snapshot['calendar_status'],
                   calendar_confirmed_wait_hours=snapshot['calendar_confirmed_wait_hours'],
                   internal_V=None, accepted_proxy_V=None,
                   risk_score=None, empirical_validation=False, paid_api_calls=0,
                   official_event_register_modified=False, production_scoring_modified=False,
                   historical_point_in_time_verified=False)
    _write_json(output / 'build_receipt.json', summary)
    for zh, lang in ((True, 'CN'), (False, 'EN')):
        (root / f'proxy_v/RESULTS_{lang}.md').write_text(render_report(summary, scenarios, zh), encoding='utf-8')
    return summary


def render_report(s, scenarios, zh):
    title = 'DAS-05 转换窗口代理 V：研究结果' if zh else 'DAS-05 conversion-window proxy V: research results'
    lines = ['# ' + title, '', f"As of: {s['as_of_timestamp_et']}", '']
    confirmed_wait = s.get('calendar_confirmed_wait_hours')
    calendar_cn = ('API明确提及节假日拒单，但尚未取得适用于转换订单的日期表。因此以上均是名义周历结果，日历确认后的等待值保持为空；没有套用NYSE、联储或DTC结算假期。'
                   if confirmed_wait is None else
                   f'输入的复核日历给出当前等待 {confirmed_wait:g} 小时；以上基线和候选分档仍单独按名义周历展示。日历结果依赖输入证据，不构成正式内部V。')
    calendar_en = ('The API mentions holiday rejection, but no applicable dated conversion calendar was obtained. All results use the nominal weekly baseline; calendar-confirmed wait stays null. No NYSE, Fed, or DTC settlement holiday substitution is made.'
                   if confirmed_wait is None else
                   f'The supplied reviewed calendar gives a current wait of {confirmed_wait:g} hours. Baseline outputs and candidate bins still describe the separate nominal weekly rule. Calendar results remain conditional on the input evidence, not official internalV.')
    if zh:
        lines += ['已实现“距离下一次名义转换订单提交窗口的等待小时数”。这是公开规则推导的结构性代理，不是实际订单延迟、转换容量或内部缓冲。', '',
                  f"当前名义等待：**{s['current_baseline_wait_hours']:.4f} 小时**；候选代理分档：**{s['current_candidate_proxy_v_score_1_5']}/5**。0小时仅表示名义窗口开放，不表示服务正常或无风险。", '',
                  f"从 {s['start_local_date']} 起重建 {s['hourly_rows']} 个小时样本、{s['daily_rows']} 个固定08:00 ET日样本。最长样本等待为 {s['maximum_sampled_baseline_wait_hours']:g} 小时；跨2026年秋季夏令时切换的周末比普通周末多1小时。", '',
                  '## 计算与分档', '',
                  '先按 America/New_York 找到下一次名义开窗时刻，再以UTC时刻相减。窗口暂按02:00含、18:00不含处理；关闭端点是保守实现假设。', '',
                  '| 等待小时 | 候选分档 |', '|---|---|', '| 0 | 1 |', '| (0, 8] | 2 |', '| (8, 24] | 3 |', '| (24, 48] | 4 |', '| >48 | 5 |', '',
                  '分档是透明的研究规则，尚未校准；不使用自身历史百分位，也不把序数分档当作损失概率。', '',
                  '## 情景演示，非真实事件', '',
                  '以下统一假设冲击S=3，且事件确实需要传统证券与代币形式之间的转换。示例不表示DTCC发生了事故，也不进入事件登记表或真实数据记录。', '']
    else:
        lines += ['Implemented hours until the next nominal conversion-order submission window. This public-rule-derived structural proxy is not observed latency, capacity, or an internal protective buffer.', '',
                  f"Current baseline wait: **{s['current_baseline_wait_hours']:.4f} hours**; candidate bin: **{s['current_candidate_proxy_v_score_1_5']}/5**. Zero means only that the nominal window is open, not that the service is healthy or risk-free.", '',
                  f"Reconstructed {s['hourly_rows']} hourly samples and {s['daily_rows']} fixed-08:00 ET daily samples from {s['start_local_date']}. Maximum sampled wait: {s['maximum_sampled_baseline_wait_hours']:g} hours, reflecting the extra elapsed hour across the autumn2026 DST change.", '',
                  '## Calculation and proposed bins', '',
                  'Find the next nominal opening in America/New_York, then subtract UTC instants. The implementation includes02:00 and excludes18:00; exclusion of the closing endpoint is a conservative research assumption.', '',
                  '| Waiting hours | Candidate bin |', '|---|---|', '| 0 | 1 |', '| (0, 8] | 2 |', '| (8, 24] | 3 |', '| (24, 48] | 4 |', '| >48 | 5 |', '',
                  'Fixed bins are proposed and uncalibrated, not historical percentiles or loss probabilities.', '',
                  '## Hypothetical scenarios, not observed events', '',
                  'Each example assumes S=3 and an event that requires conversion between traditional and tokenized form. No example claims an actual DTCC incident or enters accepted-event or observed-data records.', '']
    lines += ['| Scenario | Time ET | Baseline wait (h) | Candidate V | Illustrative S×V index |',
              '|---|---|---:|---:|---:|']
    for row in scenarios:
        lines.append(f"| {row['scenario_id']} | {row['observation_at_et']} | {row['baseline_wait_hours']:g} | {row['candidate_proxy_v_score_1_5']} | {row['illustrative_priority_index']} |")
    if zh:
        lines += ['', '## 结果边界', '',
                  '- ' + calendar_cn,
                  '- 已代币化资产的24/7转移与转换订单不同。只有需要转换的机制才可能使用此代理；本模块不自动判断新闻适用性。',
                  '- 实际系统状态、参与机构与证券资格、排队及完成时间未知。当前窗口内0小时不表示即时成交、结算或转换完成。',
                  '- 本轮使用当前文件重建规则，不声称历史信息时点已核实。2026-10-29以前不回填，不生成2020Q4–2026Q2的DAS运行历史。',
                  '- 季度表只是本季度部分样本描述，不能当作上一季度内部V。真实内部V、已接受代理V和正式风险分数均为空；没有改动final16或生产评分。',
                  '- 情景中的S和S×V是演示假设；不入真实观察数据库，不表示概率、损失、因果效应或经验验证。', '',
                  '后续检验需要授权订单/事件结果与正式服务日历，观察更长窗口等待是否对应更大的转换延迟或积压，同时控制实际故障、业务量及事件类型。', '']
    else:
        lines += ['', '## Interpretation limits', '',
                  '- ' + calendar_en,
                  '- Already-tokenized transfers operate separately24/7. This proxy only applies to pathways requiring conversion; news applicability is not automatically inferred.',
                  '- Service health, participant/security eligibility, queueing, and completion times are unknown. Zero submission wait promises no immediate processing, trade, settlement, or completion.',
                  '- Reconstructed using current evidence, not verified historical vintages. No values before2026-10-29 or invented2020Q4–2026Q2 operating history.',
                  '- Quarterly output is a partial-quarter sample description, not prior-quarter internalV. InternalV, accepted proxyV, and official risk scores stay null; final16 and production scoring are unchanged.',
                  '- Assumed S and S×V examples are illustrative ordinal priority indices, excluded from observed database records. They are not probabilities, losses, causal effects, or empirical validation.', '',
                  'Validation requires authorized order/event outcomes and the actual service calendar, testing whether longer access waits correspond to longer delays or queues while accounting for outages, load, and event type.', '']
    lines += ['## Sources', '',
              '- [DTCC DAS-001 notice](https://files.dtcc.com/download/assets/DAS-001/8a31d732d2d311f1a30ef632b7f70f6d)',
              '- [Official API reference](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content)', '',
              'Source hashes and policy provenance: `results/source_evidence.json`.',
              'Data: `results/hourly_proxy.csv`, `results/daily_0800_et_proxy.csv`, `results/quarterly_descriptive_summary.csv`.',
              'Hypothetical examples are separate: `results/hypothetical_scenarios.csv`.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=parse_instant, default=datetime.now(UTC))
    parser.add_argument('--start', type=date.fromisoformat, default=FIRST_DAY)
    parser.add_argument('--at', type=parse_instant, help='Evaluate one timestamp without writing outputs')
    args = parser.parse_args()
    if args.at is not None:
        policy, calendar, _, _ = load_inputs()
        output = evaluate(args.at, policy=policy, calendar=calendar)
    else:
        output = build_proxy(as_of=args.as_of, start=args.start)
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

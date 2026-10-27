"""Hypothetical notification/processing/pool-delivery queue, not an EPN replica.

All times are relative simulation minutes. A late valid notice is a separate
condition from delivery after the assumed deadline or noncompletion at horizon.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_CONFIG = {
    'orders_per_replication': 48,
    'notice_cutoff_min': 240.0,
    'delivery_deadline_min': 300.0,
    'horizon_min': 480.0,
    'arrival_start_min': 0.0,
    'arrival_end_min': 180.0,
    'pool_ready_start_min': 130.0,
    'pool_ready_end_min': 220.0,
    'baseline_error_fraction': 0.15,
    'repair_error_fraction': 0.40,
    'correction_latency_low_min': 10.0,
    'correction_latency_high_min': 30.0,
    'processing_capacity_orders_per_min': 0.5,
    'rescue_capacity_orders_per_min': 2.0,
    'delivery_lag_min': 20.0,
    'outage_start_min': 90.0,
    'short_outage_duration_min': 60.0,
    'prolonged_outage_duration_min': 160.0,
    'severe_outage_duration_min': 290.0,
    'beyond_horizon_outage_duration_min': 420.0,
    'order_notional_median_usd_million': 5.0,
    'order_notional_log_sigma': 0.5,
}


def processing_finish(start: float, work_minutes: float,
                      outage: tuple[float, float] | None = None) -> float:
    """Finish a task with preemptive outage suspension and subsequent resumption."""
    if not math.isfinite(start) or not math.isfinite(work_minutes) or start < 0 or work_minutes <= 0:
        raise ValueError('Nonnegative start and positive processing time required')
    if outage is None:
        return start + work_minutes
    a, b = map(float, outage)
    if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b <= a:
        raise ValueError('Outage must have a nonnegative start and later end')
    if start >= b or start + work_minutes <= a:
        return start + work_minutes
    if start < a:
        return b + work_minutes - (a-start)
    return b + work_minutes


def _peak_backlog(arrivals: list[float], completions: list[float], horizon: float) -> int:
    events = [(t, 1) for t in arrivals if t <= horizon]
    events += [(t, -1) for t in completions if t <= horizon]
    level = peak = 0
    for _, delta in sorted(events, key=lambda x: (x[0], x[1])):
        level += delta
        peak = max(peak, level)
    return peak


def simulate_orders(orders: list[dict[str, Any]], *,
                    notice_cutoff_min: float = 240.0,
                    delivery_deadline_min: float = 300.0,
                    horizon_min: float = 480.0,
                    processing_capacity_orders_per_min: float = 0.5,
                    delivery_lag_min: float = 20.0,
                    outage: tuple[float, float] | None = None,
                    outage_applies: bool = True) -> tuple[pd.DataFrame, dict[str, Any]]:
    """FIFO valid-notice queue followed by a pool-availability/delivery gate.

    Invalid first attempts are rejected instantly in an assumed precheck. The
    corrected valid attempt arrives after the supplied correction latency. There
    is one processing server, no message loss, no partial delivery and no modeled
    cash leg. Actual production acceptance and settlement rules are not inferred.
    """
    if not all(math.isfinite(v) for v in [notice_cutoff_min, delivery_deadline_min, horizon_min]) or not 0 <= notice_cutoff_min <= delivery_deadline_min <= horizon_min:
        raise ValueError('Require 0 <= notice cutoff <= delivery deadline <= horizon')
    if not math.isfinite(processing_capacity_orders_per_min) or not math.isfinite(delivery_lag_min) or processing_capacity_orders_per_min <= 0 or delivery_lag_min < 0:
        raise ValueError('Positive capacity and nonnegative delivery lag required')
    if not orders:
        raise ValueError('At least one order is required')
    ids = [o['order_id'] for o in orders]
    if len(ids) != len(set(ids)):
        raise ValueError('Order IDs must be unique')
    prepared = []
    for original in orders:
        o = dict(original)
        arrival = float(o['submission_min'])
        amount = float(o['notional_usd_million'])
        latency = float(o.get('correction_latency_min', 0.0))
        pool_time = o.get('pool_available_min')
        if (not math.isfinite(arrival) or not math.isfinite(amount)
                or not math.isfinite(latency) or arrival < 0 or amount < 0 or latency < 0):
            raise ValueError('Order time, amount and latency must be finite/nonnegative')
        if pool_time is not None and (not math.isfinite(float(pool_time)) or float(pool_time) < 0):
            raise ValueError('Pool availability must be nonnegative/finite or None')
        initial_valid = bool(o.get('initial_valid', True))
        o.update(submission_min=arrival, notional_usd_million=amount,
                 initial_valid=initial_valid,
                 valid_notification_min=arrival + (0.0 if initial_valid else latency),
                 correction_latency_min=latency,
                 pool_available_min=float(pool_time) if pool_time is not None else None)
        prepared.append(o)
    previous_finish = 0.0
    traces = []
    for o in sorted(prepared, key=lambda x: (x['valid_notification_min'], str(x['order_id']))):
        valid_at = o['valid_notification_min']
        start = max(valid_at, previous_finish)
        service_minutes = float(o.get('work_units', 1.0))/processing_capacity_orders_per_min
        finish = processing_finish(start, service_minutes, outage if outage_applies else None)
        previous_finish = finish
        pool_at = o['pool_available_min']
        completion = max(finish, pool_at) + delivery_lag_min if pool_at is not None else math.inf
        completed = completion <= horizon_min
        late = completed and completion > delivery_deadline_min
        overdue = completion > delivery_deadline_min
        trace = {
            **o,
            'queue_start_min': start if start <= horizon_min else None,
            'processing_complete_min': finish if finish <= horizon_min else None,
            'planned_processing_finish_min': finish,
            'valid_notification_late': valid_at > notice_cutoff_min,
            'processing_after_notice_cutoff': finish > notice_cutoff_min,
            'initial_validation_rejected': not o['initial_valid'],
            'completed_within_horizon': completed,
            'delivery_complete_min': completion if completed else None,
            'delivery_late': late,
            'unfinished_at_horizon': not completed,
            'overdue_at_deadline': overdue,
            'observed_delivery_delay_min': max(0.0, completion-delivery_deadline_min) if completed else None,
            'delay_lower_bound_min': max(0.0, min(completion, horizon_min)-delivery_deadline_min),
            'processing_wait_min': max(0.0, min(start, horizon_min)-valid_at) if valid_at <= horizon_min else 0.0,
        }
        traces.append(trace)
    events = pd.DataFrame(traces).sort_values('order_id').reset_index(drop=True)
    amount = events.notional_usd_million
    completed_mask = events.completed_within_horizon
    unfinished_mask = events.unfinished_at_horizon
    late_mask = events.delivery_late
    overdue_mask = events.overdue_at_deadline
    total = float(amount.sum())
    completed_amount = float(amount[completed_mask].sum())
    unfinished_amount = float(amount[unfinished_mask].sum())
    summary = {
        'order_count': len(events),
        'total_notional_usd_million': total,
        'late_message_count': int(events.valid_notification_late.sum()),
        'initial_rejection_count': int(events.initial_validation_rejected.sum()),
        'processing_after_cutoff_count': int(events.processing_after_notice_cutoff.sum()),
        'completed_delivery_count': int(completed_mask.sum()),
        'completed_delivery_notional_usd_million': completed_amount,
        'delayed_completed_delivery_count': int(late_mask.sum()),
        'delayed_completed_notional_usd_million': float(amount[late_mask].sum()),
        'unfinished_delivery_count': int(unfinished_mask.sum()),
        'unfinished_notional_usd_million': unfinished_amount,
        'overdue_delivery_count': int(overdue_mask.sum()),
        'overdue_notional_usd_million': float(amount[overdue_mask].sum()),
        'overdue_order_fraction': float(overdue_mask.mean()),
        'mean_delay_lower_bound_min': float(events.delay_lower_bound_min.mean()),
        'max_delay_lower_bound_min': float(events.delay_lower_bound_min.max()),
        'mean_processing_wait_min': float(events.processing_wait_min.mean()),
        'peak_system_backlog_orders': _peak_backlog(
            list(events.valid_notification_min), list(events.planned_processing_finish_min), horizon_min),
        'processing_backlog_at_horizon': int(((events.valid_notification_min <= horizon_min) & (events.planned_processing_finish_min > horizon_min)).sum()),
        'notional_conservation_error_usd_million': total-completed_amount-unfinished_amount,
        'horizon_min': float(horizon_min),
        'notice_cutoff_min': float(notice_cutoff_min),
        'delivery_deadline_min': float(delivery_deadline_min),
    }
    return events, summary


def run_experiment(seed: int, replications: int = 200,
                   config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    if replications < 1 or int(cfg['orders_per_replication']) < 1:
        raise ValueError('Positive replications and orders required')
    scenarios = [
        ('epn_baseline', 'Baseline', '基准', 0.0, True, False, False),
        ('epn_early_repair', 'Early message repair', '错误及时修复', 0.0, True, False, True),
        ('epn_short_outage', 'Short relevant outage', '短时相关中断', cfg['short_outage_duration_min'], True, False, False),
        ('epn_prolonged_outage', 'Prolonged relevant outage', '较长相关中断', cfg['prolonged_outage_duration_min'], True, False, False),
        ('epn_severe_outage', 'Severe relevant outage', '严重相关中断', cfg['severe_outage_duration_min'], True, False, False),
        ('epn_beyond_horizon', 'Outage beyond horizon', '超过观察期的中断', cfg['beyond_horizon_outage_duration_min'], True, False, False),
        ('epn_unrelated_outage', 'Unrelated outage', '无关中断对照', cfg['prolonged_outage_duration_min'], False, False, False),
        ('epn_capacity_rescue', 'Higher all-day processing capacity', '较高全天处理能力', cfg['prolonged_outage_duration_min'], True, True, False),
    ]
    input_rows = []; event_frames = []; run_rows = []
    base_capacity = float(cfg['processing_capacity_orders_per_min'])
    for rep in range(replications):
        rep_seed = int(np.random.SeedSequence([int(seed), 827, rep]).generate_state(1)[0])
        rng = np.random.default_rng(rep_seed)
        n = int(cfg['orders_per_replication'])
        # All scenarios reuse these latent draws: no independent seed-driven
        # composition changes can masquerade as an outage or rescue effect.
        arrival = rng.uniform(cfg['arrival_start_min'], cfg['arrival_end_min'], n)
        pool = rng.uniform(cfg['pool_ready_start_min'], cfg['pool_ready_end_min'], n)
        error_draw = rng.uniform(0, 1, n)
        correction = rng.uniform(cfg['correction_latency_low_min'], cfg['correction_latency_high_min'], n)
        notionals = np.round(rng.lognormal(np.log(cfg['order_notional_median_usd_million']), cfg['order_notional_log_sigma'], n), 6)
        for sid, en, cn, duration, applies, rescue, repair in scenarios:
            metadata = {'scenario_id': sid, 'replicate_id': rep, 'scenario_seed': rep_seed}
            errors = cfg['repair_error_fraction'] if repair else cfg['baseline_error_fraction']
            orders = [dict(order_id=f'order_{i:03d}', submission_min=float(arrival[i]),
                           notional_usd_million=float(notionals[i]), initial_valid=bool(error_draw[i] >= errors),
                           correction_latency_min=float(correction[i]), pool_available_min=float(pool[i]))
                      for i in range(n)]
            capacity = float(cfg['rescue_capacity_orders_per_min']) if rescue else base_capacity
            outage = ((float(cfg['outage_start_min']), float(cfg['outage_start_min']+duration)) if duration > 0 else None)
            for o in orders:
                input_rows.append({**metadata, **o, 'processing_capacity_orders_per_min': capacity,
                                   'outage_start_min': outage[0] if outage else None,
                                   'outage_end_min': outage[1] if outage else None,
                                   'outage_applies': applies, 'notice_cutoff_min': cfg['notice_cutoff_min'],
                                   'delivery_deadline_min': cfg['delivery_deadline_min'],
                                   'horizon_min': cfg['horizon_min']})
            events, metrics = simulate_orders(orders,
                notice_cutoff_min=float(cfg['notice_cutoff_min']),
                delivery_deadline_min=float(cfg['delivery_deadline_min']),
                horizon_min=float(cfg['horizon_min']),
                processing_capacity_orders_per_min=capacity,
                delivery_lag_min=float(cfg['delivery_lag_min']), outage=outage, outage_applies=applies)
            for key, value in metadata.items(): events[key] = value
            event_frames.append(events)
            run_rows.append({**metadata, 'model_id': 'EPN_POOL',
                             'chain_ids': 'FICC-MBSD-08|FICC-MBSD-02|FICC-MBSD-05|FICC-MBSD-09',
                             'scenario_label_en': en, 'scenario_label_cn': cn,
                             'shock_level': float(duration), 'shock_unit': 'hypothetical outage minutes',
                             'processing_capacity_orders_per_min': capacity,
                             'outage_applies': applies, **metrics})
    runs = pd.DataFrame(run_rows)
    inputs = pd.DataFrame(input_rows)
    events = pd.concat(event_frames, ignore_index=True)
    paired = runs.set_index(['scenario_id', 'replicate_id'])
    baseline = paired.loc['epn_baseline']
    unrelated = paired.loc['epn_unrelated_outage']
    relevant = paired.loc['epn_prolonged_outage']
    rescue = paired.loc['epn_capacity_rescue']
    conserved = bool((runs.notional_conservation_error_usd_million.abs() < 1e-8).all())
    unrelated_equal = bool(np.allclose(baseline[['overdue_delivery_count','unfinished_delivery_count','mean_delay_lower_bound_min']], unrelated[['overdue_delivery_count','unfinished_delivery_count','mean_delay_lower_bound_min']]))
    timing = bool((events.loc[events.completed_within_horizon, 'delivery_complete_min'] >= events.loc[events.completed_within_horizon, 'processing_complete_min']).all())
    capacity_check = bool((rescue.overdue_delivery_count.to_numpy() <= relevant.overdue_delivery_count.to_numpy()).all())
    return {
        'tables': {'epn_inputs': inputs, 'epn_events': events, 'epn_runs': runs},
        'checks': [
            {'name':'epn_notional_conservation', 'passed':conserved, 'detail':'Each synthetic notional is completed or unfinished once; no cash leg is inferred.'},
            {'name':'epn_unrelated_outage_equals_baseline', 'passed':unrelated_equal, 'detail':'Same latent orders; an unlinked outage has no process effect.'},
            {'name':'epn_delivery_after_processing', 'passed':timing, 'detail':'Observed delivery cannot precede valid-message processing.'},
            {'name':'epn_capacity_rescue_not_worse', 'passed':capacity_check, 'detail':'Higher all-day processing capacity does not increase overdue deliveries in paired paths.'},
        ],
        'assumptions': {
            'model_id':'EPN_POOL', 'config':cfg,
            'mechanism':'Instant initial syntax precheck, FIFO valid-notice processor with pausing outage, pool availability gate, fixed delivery lag.',
            'time_basis':'Hypothetical relative minutes; not official SIFMA/EPN operating cutoffs.',
            'units':'Order notional in USD million; work/capacity are hypothetical orders per simulation minute.',
            'coupling':'Common latent arrivals, pool-ready times, correction times, error draws and notionals across scenarios within a replicate.',
            'late_notice_scope':'Late valid notification is reported separately; it is not automatically a failed delivery.',
            'horizon_scope':'Delayed completed deliveries and not completed by horizon are separate; delay for unfinished orders is a lower bound.',
            'capacity_scope':'Each scenario uses its specified fixed capacity for the entire simulated day, including before and after an outage. The higher-capacity case is not a capacity change activated only at recovery.',
            'waiting_scope':'queue_start_min is the nominal eligible/service-start time before any outage suspension. processing_wait_min measures waiting before that nominal start and excludes pauses during processing. Delivery deadline and horizon delay metrics capture the end-to-end effect of outages.',
            'identification_limit':'Assumed conditional queue mechanism only, not real EPN outage exposure, failure probabilities or empirical chain validation.',
        },
    }

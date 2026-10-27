"""Hypothetical TBA maturity ladder; not an estimate of actual MBSD activity.

The broad MBSD reference supplies an illustrative dollar scale only. The TBA
share, arrivals, maturities, cancellations and deferrals are assumptions. Gross
notional is never labelled a cash obligation, loss, margin call or liquidity gap.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence
import numpy as np
import pandas as pd


DEFAULTS = {
    'horizon_days': 60,
    'broad_mbsd_reference_usd': 562_000_000_000.0,
    'hypothetical_tba_share': 0.5,
    'daily_new_fraction_of_initial': 0.025,
    'daily_flow_log_sigma': 0.25,
    'flow_ar1': 0.5,
    'daily_cancellation_fraction_of_initial': 0.0005,
    'initial_due_days': [5, 10, 20, 30, 40, 50],
    'initial_due_weights': [0.10, 0.15, 0.20, 0.20, 0.20, 0.15],
    'new_trade_tenors_days': [10, 20, 30, 40],
    'new_trade_tenor_probabilities': [0.10, 0.20, 0.40, 0.30],
}
# Public name used by the parent runner when freezing the declared experiment.
DEFAULT_CONFIG = DEFAULTS


def _vector(values: Sequence[float], length: int, name: str) -> np.ndarray:
    a = np.asarray(values, dtype=float)
    if a.shape != (length,) or not np.isfinite(a).all():
        raise ValueError(f'{name} must contain {length} finite numbers')
    return a


def simulate_ladder(
    initial_cohorts: Mapping[int, float],
    new_trades: Sequence[float],
    new_tenors: Sequence[int],
    cancellation_requests: Sequence[float],
    completion_fractions: Sequence[float],
    early_settlement_requests: Sequence[float] | None = None,
) -> pd.DataFrame:
    """Execute a fully auditable assumed daily stock-flow model.

    Cancellations occur pro rata before settlement. Due-but-unsettled amounts
    retain their original maturity date and remain eligible on later days.
    Optional early settlements are an explicitly assumed, negotiated operation;
    experiments below use zero early settlement and instead vary recovery time.
    """
    n = len(new_trades)
    if not n:
        raise ValueError('At least one simulation day is required')
    new = _vector(new_trades, n, 'new_trades')
    tenors = _vector(new_tenors, n, 'new_tenors')
    cancellations = _vector(cancellation_requests, n, 'cancellation_requests')
    completion = _vector(completion_fractions, n, 'completion_fractions')
    early = _vector(early_settlement_requests if early_settlement_requests is not None else np.zeros(n), n, 'early_settlement_requests')
    if (new < 0).any() or (cancellations < 0).any() or (early < 0).any():
        raise ValueError('Notionals cannot be negative')
    if (tenors < 1).any() or not np.equal(tenors, np.floor(tenors)).all():
        raise ValueError('New trade tenors must be positive integer days')
    if ((completion < 0) | (completion > 1)).any():
        raise ValueError('Completion fractions must lie in [0, 1]')
    buckets: dict[int, float] = defaultdict(float)
    for due, amount in initial_cohorts.items():
        if int(due) != due or due < 0 or not np.isfinite(amount) or amount < 0:
            raise ValueError('Opening cohorts require nonnegative integer maturities and finite nonnegative amounts')
        buckets[int(due)] += float(amount)
    rows = []
    for day in range(n):
        opening = float(sum(buckets.values()))
        maturity = day + int(tenors[day])
        buckets[maturity] += float(new[day])
        before_cancel = opening + float(new[day])
        actual_cancel = min(float(cancellations[day]), before_cancel)
        cancel_fraction = actual_cancel / before_cancel if before_cancel else 0.0
        for due in list(buckets):
            buckets[due] *= 1.0 - cancel_fraction
        due_notional = float(sum(amount for due, amount in buckets.items() if due <= day))
        settled_due = due_notional * float(completion[day])
        for due in list(buckets):
            if due <= day:
                buckets[due] *= 1.0 - float(completion[day])
        early_left = float(early[day])
        settled_early = 0.0
        for due in sorted(k for k in buckets if k > day):
            take = min(buckets[due], early_left)
            buckets[due] -= take
            early_left -= take
            settled_early += take
            if early_left <= 0:
                break
        settled = settled_due + settled_early
        closing = float(sum(buckets.values()))
        overdue = float(sum(amount for due, amount in buckets.items() if due <= day))
        residual = closing - (opening + float(new[day]) - actual_cancel - settled)
        rows.append({
            'sim_day': day, 'opening_unsettled_usd': opening,
            'new_trade_usd': float(new[day]), 'new_trade_tenor_days': int(tenors[day]),
            'new_trade_due_day': maturity,
            'cancellation_requested_usd': float(cancellations[day]),
            'cancelled_usd': actual_cancel, 'due_before_settlement_usd': due_notional,
            'completion_fraction_assumed': float(completion[day]),
            'settled_due_usd': settled_due, 'settled_early_usd': settled_early,
            'settled_usd': settled, 'closing_unsettled_usd': closing,
            'overdue_unsettled_usd': overdue, 'stock_flow_residual_usd': residual,
        })
    return pd.DataFrame(rows)


def scenario_definitions(base_share: float = 0.5) -> list[dict]:
    """Declare cases before computation, including unexposed and severity cases."""
    cases = [
        dict(scenario_id='tba_baseline', scenario_label_en='Baseline, no deferral', scenario_label_cn='基准：无延期', shock_level=0.0, start=20, end=19, share=base_share),
        dict(scenario_id='tba_transient_delay', scenario_label_en='Transient settlement deferral', scenario_label_cn='短期交收延期', shock_level=0.4, start=20, end=29, share=base_share),
        dict(scenario_id='tba_prolonged_delay', scenario_label_en='Prolonged settlement deferral', scenario_label_cn='持续交收延期', shock_level=0.8, start=15, end=44, share=base_share),
        dict(scenario_id='tba_earlier_recovery', scenario_label_en='Same initial shock, earlier recovery', scenario_label_cn='相同初始冲击、提前恢复', shock_level=0.8, start=15, end=29, share=base_share),
        dict(scenario_id='tba_unrelated_event', scenario_label_en='Unrelated event, no exposure', scenario_label_cn='无关事件、没有暴露', shock_level=0.0, start=20, end=19, share=base_share),
    ]
    for severity in [0.2, 0.4, 0.6, 0.8]:
        cases.append(dict(scenario_id=f'tba_severity_{int(100*severity):02}', scenario_label_en=f'Assumed deferral fraction {severity:.0%}', scenario_label_cn=f'假设延期比例{severity:.0%}', shock_level=severity, start=20, end=34, share=base_share))
    for share in [0.25, 0.75]:
        cases.append(dict(scenario_id=f'tba_share_{int(100*share):02}_baseline', scenario_label_en=f'Assumed TBA share {share:.0%}, baseline', scenario_label_cn=f'假设TBA份额{share:.0%}、基准', shock_level=0.0, start=20, end=19, share=share))
        cases.append(dict(scenario_id=f'tba_share_{int(100*share):02}_delay', scenario_label_en=f'Assumed TBA share {share:.0%}, prolonged deferral', scenario_label_cn=f'假设TBA份额{share:.0%}、持续延期', shock_level=0.8, start=15, end=44, share=share))
    return cases


def _validate_config(config: dict) -> None:
    if int(config['horizon_days']) != config['horizon_days'] or config['horizon_days'] < 1:
        raise ValueError('horizon_days must be a positive integer')
    for name in ['broad_mbsd_reference_usd','daily_new_fraction_of_initial','daily_flow_log_sigma','daily_cancellation_fraction_of_initial']:
        if not np.isfinite(config[name]) or config[name] < 0:
            raise ValueError(name+' must be finite and nonnegative')
    if config['broad_mbsd_reference_usd'] <= 0:
        raise ValueError('A positive illustrative scale is required')
    if not (0 < config['hypothetical_tba_share'] <= 1):
        raise ValueError('hypothetical_tba_share must lie in (0, 1]')
    if not (abs(config['flow_ar1']) < 1):
        raise ValueError('flow_ar1 must have absolute value below 1')
    for days, probabilities in [('initial_due_days','initial_due_weights'),('new_trade_tenors_days','new_trade_tenor_probabilities')]:
        d=np.asarray(config[days],dtype=float);p=np.asarray(config[probabilities],dtype=float)
        if len(d)!=len(p) or not len(d) or not np.isfinite(d).all() or (d<1).any() or not (d==d.astype(int)).all() or not np.isfinite(p).all() or (p<=0).any() or not np.isclose(p.sum(),1):
            raise ValueError('Invalid maturity days/probabilities: '+days)


def run_experiment(seed: int, replications: int = 200, config: dict | None = None) -> dict:
    """Return seeded common-random-number scenario tables without writing files."""
    if replications < 1 or int(replications) != replications:
        raise ValueError('replications must be a positive integer')
    cfg={**DEFAULTS, **(config or {})};_validate_config(cfg)
    n=int(cfg['horizon_days']);cases=scenario_definitions(float(cfg['hypothetical_tba_share']))
    input_rows=[];daily_frames=[];run_rows=[]
    max_residual=0.0;min_stock=float('inf');max_cancel_excess=0.0
    for rep in range(replications):
        scenario_seed=int(np.random.SeedSequence([int(seed),681,rep]).generate_state(1)[0])
        rng=np.random.default_rng(scenario_seed)
        weights=rng.dirichlet(np.asarray(cfg['initial_due_weights'])*100.0)
        z=np.empty(n);z[0]=rng.normal();rho=float(cfg['flow_ar1'])
        for day in range(1,n):z[day]=rho*z[day-1]+np.sqrt(1-rho*rho)*rng.normal()
        sigma=float(cfg['daily_flow_log_sigma'])
        flow_multipliers=np.exp(sigma*z-0.5*sigma*sigma)
        tenors=rng.choice(cfg['new_trade_tenors_days'],size=n,p=cfg['new_trade_tenor_probabilities'])
        cancellation_multipliers=rng.beta(2,8,size=n)*5.0
        frames={}
        for case in cases:
            initial=float(cfg['broad_mbsd_reference_usd'])*case['share']
            initial_cohorts={}
            for due,weight in zip(cfg['initial_due_days'],weights):
                initial_cohorts[int(due)]=initial_cohorts.get(int(due),0.0)+initial*float(weight)
            new=initial*float(cfg['daily_new_fraction_of_initial'])*flow_multipliers
            cancel=initial*float(cfg['daily_cancellation_fraction_of_initial'])*cancellation_multipliers
            completion=np.ones(n)
            start=max(0,case['start']);end=min(n-1,case['end'])
            if end>=start:completion[start:end+1]=1.0-case['shock_level']
            path=simulate_ladder(initial_cohorts,new,tenors,cancel,completion)
            meta={'scenario_id':case['scenario_id'],'replicate_id':rep,'scenario_seed':scenario_seed}
            frames[case['scenario_id']]=path
            path=path.assign(**meta,hypothetical_tba_share=case['share'])
            daily_frames.append(path)
            for due,amount in initial_cohorts.items():
                input_rows.append({**meta,'input_type':'opening_cohort','sim_day':0,'scheduled_maturity_day':due,'notional_usd':amount,'cancellation_request_usd':None,'completion_fraction_assumed':None,'hypothetical_tba_share':case['share']})
            for day in range(n):
                input_rows.append({**meta,'input_type':'new_trade_and_day_control','sim_day':day,'scheduled_maturity_day':day+int(tenors[day]),'notional_usd':float(new[day]),'cancellation_request_usd':float(cancel[day]),'completion_fraction_assumed':float(completion[day]),'hypothetical_tba_share':case['share']})
            # A same-share no-deferral path defines excess stock. A larger scale
            # must not be compared with a smaller-share baseline.
            baseline_id='tba_baseline' if case['share']==float(cfg['hypothetical_tba_share']) else f"tba_share_{int(100*case['share']):02}_baseline"
            baseline=frames[baseline_id]
            excess=path.closing_unsettled_usd.to_numpy()-baseline.closing_unsettled_usd.to_numpy()
            residue=float(path.stock_flow_residual_usd.abs().max());max_residual=max(max_residual,residue)
            min_stock=min(min_stock,float(path.closing_unsettled_usd.min()),float(path.overdue_unsettled_usd.min()))
            max_cancel_excess=max(max_cancel_excess,float((path.cancelled_usd-path.opening_unsettled_usd-path.new_trade_usd).max()))
            run_rows.append({**meta,'model_id':'TBA_PIPELINE','chain_ids':'FICC-MBSD-06',
                'scenario_label_en':case['scenario_label_en'],'scenario_label_cn':case['scenario_label_cn'],
                'shock_level':case['shock_level'],'hypothetical_tba_share':case['share'],
                'broad_mbsd_reference_usd':float(cfg['broad_mbsd_reference_usd']),
                'initial_unsettled_usd':initial,'horizon_days':n,
                'deferral_start_day':case['start'],'deferral_end_day':case['end'],
                'new_notional_usd':float(path.new_trade_usd.sum()),
                'settled_notional_usd':float(path.settled_usd.sum()),
                'cancelled_notional_usd':float(path.cancelled_usd.sum()),
                'ending_unsettled_usd':float(path.closing_unsettled_usd.iloc[-1]),
                'peak_unsettled_usd':max(initial,float(path.closing_unsettled_usd.max())),
                'peak_overdue_usd':float(path.overdue_unsettled_usd.max()),
                'overdue_notional_days_usd_days':float(path.overdue_unsettled_usd.sum()),
                'maximum_excess_unsettled_usd':float(max(0.0,excess.max())),
                'excess_unsettled_notional_days_usd_days':float(excess.sum()),
                'peak_unsettled_to_initial':max(1.0,float(path.closing_unsettled_usd.max())/initial),
                'peak_overdue_to_initial':float(path.overdue_unsettled_usd.max())/initial,
                'max_stock_flow_residual_usd':residue,
                'terminal_conservation_residual_usd':float(path.closing_unsettled_usd.iloc[-1]-(initial+path.new_trade_usd.sum()-path.cancelled_usd.sum()-path.settled_usd.sum())),
            })
        # Unrelated event must not change an exposed service's inputs or paths.
        if not frames['tba_baseline'].equals(frames['tba_unrelated_event']):
            raise AssertionError('Unrelated event changed the maturity ladder')
    runs=pd.DataFrame(run_rows);daily=pd.concat(daily_frames,ignore_index=True)
    tolerance=float(cfg['broad_mbsd_reference_usd'])*1e-10
    checks=[
        {'check_id':'tba_daily_stock_flow_conservation','passed':max_residual<=tolerance,'detail':f'max absolute residual USD {max_residual:.12g}; floating tolerance USD {tolerance:.12g}'},
        {'check_id':'tba_nonnegative_stock','passed':min_stock>=-tolerance,'detail':f'min closing/overdue USD {min_stock:.12g}'},
        {'check_id':'tba_cancellation_capped_at_available_stock','passed':max_cancel_excess<=tolerance,'detail':f'max cancellation excess USD {max_cancel_excess:.12g}'},
        {'check_id':'tba_terminal_conservation','passed':bool(runs.terminal_conservation_residual_usd.abs().le(tolerance).all()),'detail':'opening + cumulative new - settled - cancelled = terminal stock'},
        {'check_id':'tba_unrelated_event_equals_baseline','passed':True,'detail':'Every replicate compared all daily input/output fields exactly'},
        {'check_id':'tba_baseline_has_no_overdue','passed':bool(runs.loc[runs.scenario_id.str.endswith('baseline'),'peak_overdue_usd'].eq(0).all()),'detail':'All due trades settle in no-deferral cases'},
    ]
    assumptions={
        'model_id':'TBA_PIPELINE','units':'USD gross unsettled notional; USD-days for integrated stocks; simulated days, not calendar dates',
        'interpretation':'Conditional stock-flow scenario only, not empirical DTCC transmission validation, loss, cash obligation, margin call or calibrated failure probability.',
        'reference':{'broad_mbsd_reference_usd':float(cfg['broad_mbsd_reference_usd']),'reference_quarter':'2026Q2','scope':'Broad MBSD unsettled-guarantee notional, NOT identified TBA positions','source_file':'FICC_Q2_2026.pdf','page':17,'sha256':'db6ad9f8356dca918c1bc8b347bf7b82a1f40de7718644cb25ca6bca52645f49'},
        'hypothetical_tba_share':'0.5 default, 0.25/0.75 sensitivities; never estimated from PQD',
        'new_flow_and_maturities':'Entirely assumed; broad daily MBSD clearing notional is not used as TBA origination',
        'cancellations':'Seeded requests proportional to initial stock, capped at available stock and allocated pro rata before settlement',
        'deferrals':'Assumed completion fraction applies only to due/overdue buckets; deferred positions retain original maturity and remain outstanding',
        'recovery':'Earlier recovery removes the assumed impairment sooner; no early settlement of future trades is used in experiment cases',
        'capacity_limit':'There is no separate settlement-throughput cap. In an unimpaired day all due/overdue notionals settle, so recovery speed is a model assumption, not an observed MBSD capability.',
        'randomness':'Same latent opening weights, AR(1) lognormal daily-flow multiplier, tenor choices and cancellation requests across paired cases; share cases scale the same draws',
        'config':cfg,'scenario_definitions':cases,
    }
    return {'tables':{'tba_runs':runs,'tba_inputs':pd.DataFrame(input_rows),'tba_daily':daily},'checks':checks,'assumptions':assumptions}

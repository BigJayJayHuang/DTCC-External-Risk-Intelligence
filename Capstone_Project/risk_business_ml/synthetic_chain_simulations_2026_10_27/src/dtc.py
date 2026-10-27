"""Synthetic, single-participant settlement queue; NOT the DTC production engine.

All money is USD million and time is minutes after a hypothetical opening.
External cash repays simulated net debit first; only the remainder is prefunding.
It is never also credited to eligible collateral. A cap increase is capacity, not
cash. Purchased assets do not automatically replenish the separate collateral
portfolio. These are declared scenario assumptions, not calibrated DTCC rules.
"""
from __future__ import annotations
from collections import deque
import math
from typing import Mapping, Sequence
import numpy as np
import pandas as pd

DEFAULT_CONFIG = {
    'units': 'USD million', 'time_units': 'minutes after hypothetical opening',
    'horizon_minutes': 480.0, 'transaction_count': 30,
    'transaction_gamma_shape': 2.0, 'transaction_gamma_scale_usd_million': 1.7,
    'last_transaction_minute': 425.0,
    'opening_cash_usd_million': 5.0, 'opening_debit_usd_million': 0.0,
    'net_debit_cap_usd_million': 35.0,
    'collateral_market_value_usd_million': 40.0, 'baseline_haircut': 0.10,
    'funding_times_minutes': [60.0,140.0,220.0,300.0,390.0],
    'funding_weight_dirichlet_alpha': 4.0,
    'shock_funding_fraction': 0.50, 'shock_funding_delay_minutes': 180.0,
    'shock_haircut': 0.35, 'shock_start_minute': 100.0,
    'high_buffer_cap_multiple_of_total': 1.8,
    'high_buffer_collateral_multiple_of_total': 1.8,
    'rescue_minute': 320.0, 'cash_rescue_multiple_of_total': 1.0,
    'cap_rescue_multiple_of_total': 1.8,
    'sensitivity_low_haircut': 0.20, 'sensitivity_high_haircut': 0.55,
}

def _nonnegative(value, name):
    value=float(value)
    if not math.isfinite(value) or value < 0: raise ValueError(name+' must be finite and nonnegative')
    return value

def _haircut(value):
    value=_nonnegative(value,'haircut')
    if value > 1: raise ValueError('haircut must be between zero and one')
    return value

def simulate_day(transactions: Sequence[Mapping], resource_events: Sequence[Mapping], *,
                 opening_cash_usd_million=0.0, opening_debit_usd_million=0.0,
                 net_debit_cap_usd_million=0.0, collateral_market_value_usd_million=0.0,
                 haircut=0.0, horizon_minutes=480.0):
    """Pure deterministic event engine returning ``summary`` and ``events``.

    Transaction fields: transaction_id, time_minutes, amount_usd_million.
    Resources: event_type in cash_funding/cap_increase/collateral_update/
    unrelated_event; time_minutes; amount_usd_million for the first two;
    haircut and/or collateral_market_value_usd_million for collateral_update.
    Resources arriving after the horizon are not available during this day.
    Same-time resource changes precede obligations. FIFO prevents bypassing a
    blocked head; this is an explicit simplifying policy, not DTC optimization.
    """
    horizon=_nonnegative(horizon_minutes,'horizon')
    opening_cash=_nonnegative(opening_cash_usd_million,'opening cash')
    opening_debit=_nonnegative(opening_debit_usd_million,'opening debit')
    initial_cap=_nonnegative(net_debit_cap_usd_million,'cap')
    initial_collateral=_nonnegative(collateral_market_value_usd_million,'collateral')
    initial_haircut=_haircut(haircut)
    cap=initial_cap; market=initial_collateral; cut=initial_haircut
    # Apply the same repay-first cash convention to opening resources.
    offset=min(opening_cash,opening_debit)
    cash=opening_cash-offset;debit=opening_debit-offset
    queue=deque();settled={};arrivals={};events=[];blocked=set();schedule=[]
    requested=0.0;paid=0.0;funding=0.0;borrowed=0.0;repaid=offset
    peak_queue=0.0;queue_area=0.0;last_time=0.0;initial_breach=debit>min(cap,market*(1-cut))+1e-9
    if initial_breach:raise ValueError('opening net debit exceeds an opening resource constraint')
    for index,raw in enumerate(transactions):
        tid=str(raw['transaction_id']);time=_nonnegative(raw['time_minutes'],'transaction time')
        amount=_nonnegative(raw['amount_usd_million'],'transaction amount')
        if amount <= 0 or time > horizon:raise ValueError('transactions need positive amounts and in-horizon times')
        if tid in arrivals:raise ValueError('duplicate transaction_id')
        arrivals[tid]=(time,amount);schedule.append((time,1,index,'transaction',{'transaction_id':tid,'amount_usd_million':amount}))
    accepted_types={'cash_funding','cap_increase','collateral_update','unrelated_event'}
    for index,raw in enumerate(resource_events):
        kind=raw['event_type'];time=_nonnegative(raw['time_minutes'],'resource time')
        if kind not in accepted_types:raise ValueError('unsupported resource event '+str(kind))
        event=dict(raw)
        if kind in {'cash_funding','cap_increase'}:event['amount_usd_million']=_nonnegative(raw['amount_usd_million'],'resource amount')
        if kind=='collateral_update':
            if 'haircut' in raw:event['haircut']=_haircut(raw['haircut'])
            if 'collateral_market_value_usd_million' in raw:event['collateral_market_value_usd_million']=_nonnegative(raw['collateral_market_value_usd_million'],'collateral')
        if time <= horizon:schedule.append((time,0,index,kind,event))
    schedule.sort(key=lambda x:(x[0],x[1],x[2]))

    def trace(time,kind,tid=None,amount=0.0,reason='',cash_used=0.0,new_debit=0.0,cash_repaid=0.0):
        pending=sum(arrivals[i][1] for i in queue)
        residual=opening_cash+funding+debit-opening_debit-paid-cash
        events.append({
            'event_index':len(events),'time_minutes':time,'event_type':kind,
            'transaction_id':tid,'event_amount_usd_million':amount,'reason':reason,
            'cash_used_usd_million':cash_used,'new_debit_usd_million':new_debit,
            'cash_repaid_usd_million':cash_repaid,
            'cash_balance_usd_million':cash,'net_debit_usd_million':debit,
            'net_debit_cap_usd_million':cap,'collateral_market_value_usd_million':market,
            'haircut':cut,'eligible_collateral_usd_million':market*(1-cut),
            'cumulative_cash_funding_usd_million':funding,
            'cumulative_new_debit_usd_million':borrowed,
            'cumulative_debit_repaid_usd_million':repaid,
            'arrived_amount_usd_million':requested,'settled_amount_usd_million':paid,
            'pending_amount_usd_million':pending,'pending_count':len(queue),
            'ledger_residual_usd_million':residual,
            'queue_conservation_residual_usd_million':requested-paid-pending,
            'resource_breach_after_revaluation':debit>min(cap,market*(1-cut))+1e-9,
            'initial_cash_usd_million':opening_cash,'initial_debit_usd_million':opening_debit,
            'initial_cap_usd_million':initial_cap,
            'initial_collateral_market_value_usd_million':initial_collateral,
            'initial_haircut':initial_haircut,
        })

    def recycle(time):
        nonlocal cash,debit,paid,borrowed
        while queue:
            tid=queue[0];arrival,amount=arrivals[tid]
            cash_used=min(cash,amount);credit=amount-cash_used
            projected=debit+credit
            reasons=[]
            if projected>cap+1e-9:reasons.append('cap')
            if projected>market*(1-cut)+1e-9:reasons.append('eligible_collateral')
            if reasons:
                blocked.add(tid);trace(time,'blocked',tid,amount,'+'.join(reasons));break
            queue.popleft();cash-=cash_used;debit=projected;paid+=amount;borrowed+=credit
            settled[tid]={'time_minutes':time,'wait_minutes':time-arrival,'amount_usd_million':amount}
            trace(time,'settlement',tid,amount,'admitted_by_both_constraints',cash_used,credit)

    trace(0.0,'opening')
    for time,_,_,kind,raw in schedule:
        queue_area+=(time-last_time)*sum(arrivals[i][1] for i in queue);last_time=time
        if kind=='transaction':
            tid=raw['transaction_id'];queue.append(tid);requested+=raw['amount_usd_million']
            trace(time,'transaction_arrival',tid,raw['amount_usd_million'])
        elif kind=='cash_funding':
            amount=raw['amount_usd_million'];funding+=amount;repay=min(debit,amount)
            debit-=repay;cash+=amount-repay;repaid+=repay
            trace(time,kind,amount=amount,cash_repaid=repay,reason='repay_debit_first_then_prefund;no_collateral_credit')
        elif kind=='cap_increase':
            cap+=raw['amount_usd_million'];trace(time,kind,amount=raw['amount_usd_million'],reason='capacity_only;no_cash_or_collateral_created')
        elif kind=='collateral_update':
            cut=raw.get('haircut',cut);market=raw.get('collateral_market_value_usd_million',market)
            trace(time,kind,reason='external_revaluation;existing_settlements_not_reversed')
        else:trace(time,'unrelated_event',reason='no_mapped_resource_or_obligation_changed')
        recycle(time)
        peak_queue=max(peak_queue,sum(arrivals[i][1] for i in queue))
    queue_area+=(horizon-last_time)*sum(arrivals[i][1] for i in queue)
    trace(horizon,'day_end')
    waits=[r['wait_minutes'] for r in settled.values()]
    pending=sum(arrivals[i][1] for i in queue)
    summary={
        'submitted_amount_usd_million':requested,'submitted_count':len(arrivals),
        'settled_amount_usd_million':paid,'settled_count':len(settled),
        'eod_pending_amount_usd_million':pending,'eod_pending_count':len(queue),
        'ever_head_blocked_count':len(blocked),
        'ever_queued_count':sum(w>1e-9 for w in waits)+len(queue),
        'peak_queued_amount_usd_million':peak_queue,
        'queue_area_usd_million_minutes':queue_area,
        'mean_settled_wait_minutes':float(np.mean(waits)) if waits else None,
        'max_settled_wait_minutes':max(waits) if waits else None,
        'max_eod_pending_age_minutes':max((horizon-arrivals[i][0] for i in queue),default=0.0),
        'cash_funding_received_usd_million':funding,'eod_cash_usd_million':cash,
        'eod_net_debit_usd_million':debit,'eod_cap_usd_million':cap,
        'eod_eligible_collateral_usd_million':market*(1-cut),
        'horizon_minutes':horizon,'amount_units':'USD million','time_units':'minutes',
        'pending_waits_are_right_censored':True,
        'max_abs_ledger_residual_usd_million':max(abs(e['ledger_residual_usd_million']) for e in events),
        'max_abs_queue_residual_usd_million':max(abs(e['queue_conservation_residual_usd_million']) for e in events),
        'all_settlements_within_resources':all(e['net_debit_usd_million']<=min(e['net_debit_cap_usd_million'],e['eligible_collateral_usd_million'])+1e-8 for e in events if e['event_type']=='settlement'),
    }
    return {'summary':summary,'events':events}

def run_experiment(seed:int, replications:int=200, config:dict|None=None):
    """Paired hypothetical scenarios sharing each replicate's generated workload."""
    cfg={**DEFAULT_CONFIG,**(config or {})}
    if cfg['units']!='USD million':raise ValueError('only USD million is supported')
    if not isinstance(replications,int) or replications<1:raise ValueError('replications must be a positive integer')
    if not isinstance(cfg['transaction_count'],int) or cfg['transaction_count']<1:raise ValueError('transaction_count must be positive')
    if cfg['last_transaction_minute']>cfg['horizon_minutes']:raise ValueError('transactions must arrive by horizon')
    if not 0<=cfg['shock_funding_fraction']<=1:raise ValueError('shock funding fraction must be in [0,1]')
    scenarios=[
        ('dtc_baseline','Baseline resources and funding','基准资源与资金到达','baseline','standard',None),
        ('dtc_funding_shock','Funding delay/shortfall and collateral haircut','资金延迟/减少与抵押品折扣冲击','shock','standard',None),
        ('dtc_high_buffer','Same shock with larger cap/collateral buffer','同一冲击、较大额度与抵押品缓冲','shock','high_buffer',None),
        ('dtc_cash_rescue','Same shock plus explicitly supplied cash','同一冲击、额外现金注入','shock','standard','cash'),
        ('dtc_cap_only_rescue','Same shock plus cap capacity only','同一冲击、仅增加额度容量','shock','standard','cap'),
        ('dtc_unrelated_event','Unrelated event; baseline resources unchanged','无关联事件、基准资源不变','unrelated','standard',None),
        ('dtc_sensitivity_haircut_low','Funding shock; lower assumed haircut','资金冲击、较低假设抵押品折扣','sensitivity_low','standard',None),
        ('dtc_sensitivity_haircut_high','Funding shock; higher assumed haircut','资金冲击、较高假设抵押品折扣','sensitivity_high','standard',None),
    ]
    runs=[];inputs=[];traces=[]
    for replicate in range(replications):
        scenario_seed=int(np.random.SeedSequence([int(seed),replicate,606]).generate_state(1,dtype=np.uint64)[0])
        rng=np.random.default_rng(scenario_seed)
        n=cfg['transaction_count']
        times=np.sort(rng.uniform(5.0,cfg['last_transaction_minute'],n))
        amounts=rng.gamma(cfg['transaction_gamma_shape'],cfg['transaction_gamma_scale_usd_million'],n)
        tx=[{'transaction_id':f'T{i:03d}','time_minutes':float(t),'amount_usd_million':float(a)} for i,(t,a) in enumerate(zip(times,amounts))]
        total=float(sum(amounts));fund_times=cfg['funding_times_minutes']
        weights=rng.dirichlet(np.full(len(fund_times),cfg['funding_weight_dirichlet_alpha']))
        # Baseline full-day funding equals gross requested payments by assumption.
        base_funding=[{'event_type':'cash_funding','time_minutes':float(t),'amount_usd_million':float(total*w)} for t,w in zip(fund_times,weights)]
        for scenario_id,label_en,label_cn,mode,vulnerability,rescue in scenarios:
            tags={'scenario_id':scenario_id,'replicate_id':replicate,'scenario_seed':scenario_seed}
            stressed=mode not in {'baseline','unrelated'}
            haircut=cfg['sensitivity_low_haircut'] if mode=='sensitivity_low' else cfg['sensitivity_high_haircut'] if mode=='sensitivity_high' else cfg['shock_haircut']
            funding=[{**e,'time_minutes':e['time_minutes']+(cfg['shock_funding_delay_minutes'] if stressed else 0),'amount_usd_million':e['amount_usd_million']*(cfg['shock_funding_fraction'] if stressed else 1)} for e in base_funding]
            resources=funding[:]
            if stressed:resources.append({'event_type':'collateral_update','time_minutes':cfg['shock_start_minute'],'haircut':haircut})
            if mode=='unrelated':resources.append({'event_type':'unrelated_event','time_minutes':cfg['shock_start_minute']})
            cap=cfg['net_debit_cap_usd_million'];collateral=cfg['collateral_market_value_usd_million']
            if vulnerability=='high_buffer':
                cap=max(cap,cfg['high_buffer_cap_multiple_of_total']*total)
                collateral=max(collateral,cfg['high_buffer_collateral_multiple_of_total']*total)
            if rescue=='cash':resources.append({'event_type':'cash_funding','time_minutes':cfg['rescue_minute'],'amount_usd_million':cfg['cash_rescue_multiple_of_total']*total,'resource_role':'hypothetical_extra_cash'})
            if rescue=='cap':resources.append({'event_type':'cap_increase','time_minutes':cfg['rescue_minute'],'amount_usd_million':cfg['cap_rescue_multiple_of_total']*total})
            opening={'opening_cash_usd_million':cfg['opening_cash_usd_million'],'opening_debit_usd_million':cfg['opening_debit_usd_million'],'net_debit_cap_usd_million':cap,'collateral_market_value_usd_million':collateral,'haircut':cfg['baseline_haircut'],'horizon_minutes':cfg['horizon_minutes']}
            result=simulate_day(tx,resources,**opening)
            runs.append({**tags,'model_id':'DTC_CONTROL','chain_ids':'ECS-DTC-06','scenario_label_en':label_en,'scenario_label_cn':label_cn,'shock_level':1-cfg['shock_funding_fraction'] if stressed or mode=='unrelated' else 0.0,'shock_exposure':'unrelated_event' if mode=='unrelated' else 'mapped_funding_and_collateral' if stressed else 'none','vulnerability_label':vulnerability,'parameter_sensitivity':'haircut' if mode.startswith('sensitivity') else 'none','assumed_stress_haircut':haircut if stressed else cfg['baseline_haircut'],**result['summary']})
            inputs.append({**tags,'input_type':'opening_resources','event_type':'opening','time_minutes':0.0,**opening,'in_horizon':True,'amount_units':'USD million'})
            inputs.extend({**tags,'input_type':'transaction','event_type':'transaction',**t,'in_horizon':True,'amount_units':'USD million'} for t in tx)
            inputs.extend({**tags,'input_type':'resource_event',**r,'in_horizon':r['time_minutes']<=cfg['horizon_minutes'],'amount_units':'USD million'} for r in resources)
            traces.extend({**tags,**e} for e in result['events'])
    run_frame=pd.DataFrame(runs);trace_frame=pd.DataFrame(traces)
    wide=run_frame.pivot(index='replicate_id',columns='scenario_id',values='eod_pending_amount_usd_million')
    residual=float(trace_frame.ledger_residual_usd_million.abs().max())
    queue_residual=float(trace_frame.queue_conservation_residual_usd_million.abs().max())
    checks=[
        {'check_id':'dtc_cash_credit_ledger_conservation','passed':residual<1e-7,'max_abs_residual_usd_million':residual},
        {'check_id':'dtc_transaction_queue_conservation','passed':queue_residual<1e-7,'max_abs_residual_usd_million':queue_residual},
        {'check_id':'dtc_admission_constraints','passed':bool(run_frame.all_settlements_within_resources.all())},
        {'check_id':'dtc_no_exposure_control','passed':bool(np.allclose(wide.dtc_baseline,wide.dtc_unrelated_event,atol=1e-9))},
        {'check_id':'dtc_haircut_sensitivity_direction','passed':bool((wide.dtc_sensitivity_haircut_high+1e-8>=wide.dtc_sensitivity_haircut_low).all())},
        {'check_id':'dtc_timestamps_within_horizon','passed':bool(trace_frame.time_minutes.between(0,cfg['horizon_minutes']).all())},
    ]
    assumptions={
        'model_id':'DTC_CONTROL','chain_ids':['ECS-DTC-06'],'config':cfg,
        'interpretation':'Synthetic conditional scenario exploration and implementation checks only; no empirical chain validation, calibrated default probability or reconstruction of DTC controls.',
        'queue_policy':'One participant, positive indivisible outgoing obligations, strict FIFO; blocked head prevents bypass. Resource events at a timestamp precede transaction arrivals.',
        'cash_accounting':'Cash first repays simulated outstanding debit; excess is prefunding. Outgoing payments spend prefunding before adding debit. Cash is never also credited to the eligible collateral portfolio.',
        'cap_accounting':'An increased debit cap is capacity only, not money and not collateral. Actual funding requires a separate cash event.',
        'collateral_accounting':'Separate exogenously valued eligible portfolio = market value*(1-haircut); incoming purchased securities are not automatically added. Revaluation can create an existing exposure breach without reversing completed settlements.',
        'baseline_funding':'Total scheduled baseline cash funding equals gross generated payment amount; timing weights are arbitrary seeded Dirichlet draws, not inferred participant behavior.',
        'pairing':'Each replicate uses the same transactions and base funding draws across all scenarios. Funding/haircut/resource changes are declared interventions, not estimated causal effects.',
        'censoring':'EOD pending waits are right-censored; settled-wait statistics exclude pending obligations and are not overall completion-time estimates.',
        'cash_rescue':'Default rescue deliberately supplies cash equal to gross payments as a sufficient-liquidity control, not an operational recommendation.',
        'parameters':'All hypothetical constants and distributions are scenario assumptions, not DTCC limits or estimated risk parameters.',
    }
    return {'tables':{'dtc_runs':run_frame,'dtc_inputs':pd.DataFrame(inputs),'dtc_events':trace_frame},'checks':checks,'assumptions':assumptions}

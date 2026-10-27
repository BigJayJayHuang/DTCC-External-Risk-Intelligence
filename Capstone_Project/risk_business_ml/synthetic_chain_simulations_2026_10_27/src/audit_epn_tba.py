"""Independently replay saved EPN/TBA inputs; never call either model engine.

TBA uses a separately implemented bucket/cancellation ledger with math.fsum.
EPN removes the outage interval from an active-service clock, then inverts that
clock. This differs from the generator's case-by-case outage-finish function.
The audit checks synthetic implementation consistency, not empirical validity.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
KEYS=['scenario_id','replicate_id']

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def audit(root=ROOT):
    if not __debug__:raise RuntimeError('Run without -O: audit assertions must remain enabled')
    root=Path(root)
    receipt=json.loads((root/'results/execution_receipt.json').read_text())
    plan=json.loads((root/'config/resolved_plan.json').read_text())
    assumptions=json.loads((root/'results/model_assumptions.json').read_text())
    names=['tba_inputs','tba_daily','tba_runs','epn_inputs','epn_events','epn_runs']
    frames={};hashes={}
    for name in names:
        path=root/'data'/f'{name}.csv';hashes[str(path.relative_to(root))]=digest(path)
        assert hashes[str(path.relative_to(root))]==receipt['csv_sha256'][name],name+' CSV checksum mismatch'
        frame=pd.read_csv(path,float_precision='round_trip',dtype={'scenario_seed':str})
        assert len(frame)==receipt['tables'][name]
        assert set(frame.simulation_id)=={receipt['simulation_id']}
        assert set(frame.source_type)=={'synthetic'}
        assert set(frame.catalog_version)=={plan['catalog_version']}
        assert not frame.empirical_validation.any()
        frames[name]=frame
    for name in ['epn','tba']:
        path=root/'src'/f'{name}.py';hashes[str(path.relative_to(root))]=digest(path)
        assert hashes[str(path.relative_to(root))]==plan['engine_hashes'][name],name+' engine changed after plan freeze'
    for rel in ['config/resolved_plan.json','results/model_assumptions.json','results/execution_receipt.json']:
        hashes[rel]=digest(root/rel)
    hashes['src/audit_epn_tba.py']=digest(Path(__file__))
    eps=np.finfo(float).eps
    scale=float(plan['models']['tba']['broad_mbsd_reference_usd'])
    tba_tol=max(1e-8,eps*max(1.0,scale)*4096)
    tba=tba_audit(frames['tba_inputs'],frames['tba_daily'],frames['tba_runs'],tba_tol,plan)
    time_scale=max(1.0,float(plan['models']['epn']['horizon_min']))
    epn_time_tol=max(1e-9,eps*time_scale*4096)
    epn_amount_tol=max(1e-9,eps*float(frames['epn_runs'].total_notional_usd_million.max())*4096)
    epn=epn_audit(frames['epn_inputs'],frames['epn_events'],frames['epn_runs'],epn_time_tol,epn_amount_tol,plan)
    # Cross-check the scale against the supplied public evidence rather than
    # treating a guessed TBA share as a measured input.
    anchor=pd.read_csv(root/'inputs/financial_guarantee_reconciliation.csv',float_precision='round_trip')
    matched=anchor[anchor.entity.eq('MBSD')&anchor.quarter.eq('2026Q2')]
    assert len(matched)==1
    source=matched.iloc[0];assert float(source.chosen_usd)==scale
    pdf=root/'inputs'/source.source_file
    assert digest(pdf)==source.sha256
    assert assumptions['tba']['reference']['sha256']==source.sha256
    assert assumptions['tba']['reference']['scope']=='Broad MBSD unsettled-guarantee notional, NOT identified TBA positions'
    hashes['inputs/financial_guarantee_reconciliation.csv']=digest(root/'inputs/financial_guarantee_reconciliation.csv')
    hashes['inputs/'+source.source_file]=digest(pdf)
    return {
        'audited_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'simulation_id':receipt['simulation_id'],'passed':True,
        'scope':'Independent saved-input/output replay for EPN and TBA only; DTC not audited by this script.',
        'source_and_csv_sha256':hashes,
        'tolerances':{'tba_usd':tba_tol,'epn_minutes':epn_time_tol,'epn_usd_million':epn_amount_tol,'basis':'Double-precision machine epsilon times monetary/time scale and a4096-operation rounding allowance; floors1e-8USD/1e-9minute. Not risk thresholds.'},
        'tba':tba,'epn':epn,
        'public_anchor':{'source_file':source.source_file,'page':int(source.page),'sha256':source.sha256,'broad_mbsd_notional_usd':scale,'scope':'Broad MBSD unsettled guarantee notional; hypothetical TBA shares are assumptions, not measured exposure.'},
        'interpretation_limits':[
            'Successful replay verifies arithmetic and the declared hypothetical mechanism; it is not evidence of real DTCC exposure, causal transmission, calibrated risk or actual production behavior.',
            'EPN cutoffs/deadlines and queue capacity are hypothetical; late valid notices, late completed deliveries and unfinished deliveries are distinct.',
            'For unfinished EPN deliveries, reported delay is only a horizon-censored lower bound; zero late-completed deliveries does not mean no disruption.',
            'EPN queue_start is nominal service eligibility before outage suspension; processing_wait excludes the outage suspension inside service.',
            'EPN capacity-rescue scenario assumes higher capacity all day, not an isolated post-outage recovery intervention.',
            'TBA values are gross notional, not cash funding, margin calls or losses. Broad MBSD scale does not identify a TBA-only portfolio.',
            'No additional settlement-throughput cap is present in the TBA ladder; full clearing on an unimpaired day is an assumption.'
        ],
    }

def tba_audit(inputs,daily,runs,tolerance,plan):
    assert not daily.duplicated(KEYS+['sim_day']).any()
    assert not runs.duplicated(KEYS).any()
    paths={k:g.set_index('sim_day') for k,g in daily.groupby(KEYS)}
    summaries=runs.set_index(KEYS)
    assert len(paths)==len(summaries)==runs.scenario_id.nunique()*plan['replications_per_scenario']
    max_diff=0.0;max_money_diff=0.0;max_integrated_diff=0.0;terminal_residual=0.0;groups=0
    compared=['opening_unsettled_usd','new_trade_usd','cancelled_usd','due_before_settlement_usd','settled_usd','closing_unsettled_usd','overdue_unsettled_usd']
    for key,g in inputs.groupby(KEYS):
        cohorts=g[g.input_type.eq('opening_cohort')]
        bucket={}
        for r in cohorts.itertuples():
            due=int(r.scheduled_maturity_day);bucket[due]=bucket.get(due,0.0)+float(r.notional_usd)
        initial=math.fsum(bucket.values());nn=ss=cc=0.0;peak=initial;overdue_peak=0.0;overdue_days=0.0
        controls=g[g.input_type.eq('new_trade_and_day_control')].sort_values('sim_day')
        assert controls.sim_day.tolist()==list(range(int(plan['models']['tba']['horizon_days'])))
        assert set(paths[key].index)==set(controls.sim_day)
        for r in controls.itertuples():
            day=int(r.sim_day);opening=math.fsum(bucket.values());new=float(r.notional_usd)
            due=int(r.scheduled_maturity_day);assert due>day
            bucket[due]=bucket.get(due,0.0)+new;pre=math.fsum(bucket.values())
            cancel=min(float(r.cancellation_request_usd),pre)
            assert 0<=cancel<=pre+tolerance
            for d in bucket:bucket[d]-=bucket[d]*cancel/pre if pre else 0.0
            due_sum=math.fsum(v for d,v in bucket.items() if d<=day)
            fraction=float(r.completion_fraction_assumed);assert 0<=fraction<=1
            settled=0.0
            for d in bucket:
                if d<=day:
                    amount=bucket[d]*fraction;settled+=amount;bucket[d]-=amount
            closing=math.fsum(bucket.values());overdue=math.fsum(v for d,v in bucket.items() if d<=day)
            assert min(bucket.values(),default=0.0)>=-tolerance
            expected=[opening,new,cancel,due_sum,settled,closing,overdue]
            for col,value in zip(compared,expected):
                err=abs(float(paths[key].loc[day,col])-value);max_diff=max(max_diff,err);max_money_diff=max(max_money_diff,err)
                assert err<=tolerance,(key,day,col,err)
            assert abs(float(paths[key].loc[day,'settled_early_usd']))<=tolerance,'Experiment unexpectedly uses early settlement'
            nn+=new;ss+=settled;cc+=cancel;peak=max(peak,closing);overdue_peak=max(overdue_peak,overdue);overdue_days+=overdue
        residual=abs(initial+nn-ss-cc-closing);terminal_residual=max(terminal_residual,residual)
        assert residual<=tolerance
        expected_summary={'initial_unsettled_usd':initial,'new_notional_usd':nn,'settled_notional_usd':ss,'cancelled_notional_usd':cc,'ending_unsettled_usd':closing,'peak_unsettled_usd':peak,'peak_overdue_usd':overdue_peak,'overdue_notional_days_usd_days':overdue_days}
        for col,value in expected_summary.items():
            err=abs(float(summaries.loc[key,col])-value);max_diff=max(max_diff,err)
            if col.endswith('_usd_days'):max_integrated_diff=max(max_integrated_diff,err)
            else:max_money_diff=max(max_money_diff,err)
            # Integrated notional-days accumulates one rounded stock per day.
            allowed=tolerance*max(1,len(controls)) if col.endswith('_usd_days') else tolerance
            assert err<=allowed,(key,col,err)
        assert abs(initial/float(plan['models']['tba']['broad_mbsd_reference_usd'])-float(g.hypothetical_tba_share.iloc[0]))<1e-12
        groups+=1
    assert groups==len(paths)
    return {'paths_replayed':groups,'daily_rows_replayed':len(daily),'numeric_fields_replayed':compared,'max_absolute_saved_value_difference_usd_or_usd_days':max_diff,'max_saved_amount_difference_usd':max_money_diff,'max_saved_integrated_difference_usd_days':max_integrated_diff,'max_terminal_arithmetic_residual_usd':terminal_residual,'algorithm':'Separate original-maturity buckets, explicit pro-rata cancellation amounts, math.fsum; no generator or engine imports.'}

def epn_audit(inputs,events,runs,time_tolerance,amount_tolerance,plan):
    assert not events.duplicated(KEYS+['order_id']).any()
    assert not inputs.duplicated(KEYS+['order_id']).any()
    assert not runs.duplicated(KEYS).any()
    ev={k:g.set_index('order_id') for k,g in events.groupby(KEYS)};summaries=runs.set_index(KEYS)
    assert len(ev)==len(summaries)==runs.scenario_id.nunique()*plan['replications_per_scenario']
    max_time=0.0;max_amount=0.0;orders_replayed=0;nominal_in_outage=0;late_notices=0;groups=0
    lag=float(plan['models']['epn']['delivery_lag_min'])
    for key,g in inputs.groupby(KEYS):
        row=g.iloc[0];h=float(row.horizon_min);cut=float(row.notice_cutoff_min);deadline=float(row.delivery_deadline_min);capacity=float(row.processing_capacity_orders_per_min)
        assert 0<=cut<=deadline<=h and capacity>0
        assert len(g)==len(ev[key]) and set(g.order_id)==set(ev[key].index)
        outage=bool(row.outage_applies) and pd.notna(row.outage_start_min)
        a=float(row.outage_start_min) if outage else math.inf;b=float(row.outage_end_min) if outage else math.inf
        # Active-clock inverse is intentionally independent of processing_finish.
        def active(t):return min(t,a) if t<b else t-(b-a)
        def physical(t):return t if t<=a else t+(b-a)
        previous_active=0.0;previous_physical=0.0;pred=[];valid_times=[];finish_times=[]
        orders=sorted(g.to_dict('records'),key=lambda o:(o['submission_min']+(0 if o['initial_valid'] else o['correction_latency_min']),str(o['order_id'])))
        for o in orders:
            valid=float(o['submission_min']+(0 if o['initial_valid'] else o['correction_latency_min']))
            assert valid>=0
            start_nominal=max(valid,previous_physical)
            work=float(o.get('work_units',1.0))/capacity
            finish_active=max(active(valid),previous_active)+work
            finish=physical(finish_active);previous_active=finish_active;previous_physical=finish
            pool=float(o['pool_available_min']) if pd.notna(o['pool_available_min']) else math.inf
            completion=max(finish,pool)+lag;e=ev[key].loc[o['order_id']]
            complete=completion<=h;late=complete and completion>deadline;unfinished=not complete;overdue=completion>deadline
            for col,expected in {'valid_notification_min':valid,'planned_processing_finish_min':finish,'delay_lower_bound_min':max(0.0,min(completion,h)-deadline),'processing_wait_min':max(0.0,min(start_nominal,h)-valid) if valid<=h else 0.0}.items():
                err=abs(float(e[col])-expected);max_time=max(max_time,err);assert err<=time_tolerance,(key,o['order_id'],col,err)
            for col,expected in {'completed_within_horizon':complete,'delivery_late':late,'unfinished_at_horizon':unfinished,'overdue_at_deadline':overdue,'valid_notification_late':valid>cut,'processing_after_notice_cutoff':finish>cut,'initial_validation_rejected':not bool(o['initial_valid'])}.items():assert bool(e[col])==expected,(key,o['order_id'],col)
            for col,predicted,observed in [('queue_start_min',start_nominal,start_nominal<=h),('processing_complete_min',finish,finish<=h),('delivery_complete_min',completion,complete)]:
                assert pd.isna(e[col])==(not observed),(key,o['order_id'],col,'censoring')
                if observed:
                    err=abs(float(e[col])-predicted);max_time=max(max_time,err);assert err<=time_tolerance
            assert pd.isna(e.observed_delivery_delay_min)==unfinished
            if complete:assert abs(float(e.observed_delivery_delay_min)-max(0.0,completion-deadline))<=time_tolerance
            if outage and start_nominal<=h and a<=start_nominal<b:nominal_in_outage+=1
            lower_bound=max(0.0,min(completion,h)-deadline)
            wait=max(0.0,min(start_nominal,h)-valid) if valid<=h else 0.0
            pred.append((complete,late,unfinished,overdue,float(o['notional_usd_million']),valid>cut,not bool(o['initial_valid']),finish>cut,lower_bound,wait))
            valid_times.append(valid);finish_times.append(finish);orders_replayed+=1
        p=np.asarray(pred);rr=summaries.loc[key]
        for index,col in [(0,'completed_delivery_count'),(1,'delayed_completed_delivery_count'),(2,'unfinished_delivery_count'),(3,'overdue_delivery_count'),(5,'late_message_count'),(6,'initial_rejection_count'),(7,'processing_after_cutoff_count')]:assert int(rr[col])==int(p[:,index].sum()),(key,col)
        for index,col in [(0,'completed_delivery_notional_usd_million'),(1,'delayed_completed_notional_usd_million'),(2,'unfinished_notional_usd_million'),(3,'overdue_notional_usd_million')]:
            value=math.fsum(p[p[:,index].astype(bool),4]);err=abs(float(rr[col])-value);max_amount=max(max_amount,err);assert err<=amount_tolerance
        assert int(rr.overdue_delivery_count)==int(rr.delayed_completed_delivery_count+rr.unfinished_delivery_count)
        assert int(rr.order_count)==len(pred)
        for col,value in {'mean_delay_lower_bound_min':float(p[:,8].mean()),'max_delay_lower_bound_min':float(p[:,8].max()),'mean_processing_wait_min':float(p[:,9].mean())}.items():
            err=abs(float(rr[col])-value);max_time=max(max_time,err);assert err<=time_tolerance,(key,col)
        assert abs(float(rr.overdue_order_fraction)-float(p[:,3].mean()))<=np.finfo(float).eps*4096
        err=abs(float(rr.completed_delivery_notional_usd_million+rr.unfinished_notional_usd_million-rr.total_notional_usd_million));max_amount=max(max_amount,err);assert err<=amount_tolerance
        peak=max((sum(v<=t<f for v,f in zip(valid_times,finish_times)) for t in set(valid_times) if t<=h),default=0)
        assert peak==int(rr.peak_system_backlog_orders)
        assert sum(v<=h<f for v,f in zip(valid_times,finish_times))==int(rr.processing_backlog_at_horizon)
        late_notices+=int(rr.late_message_count);groups+=1
    assert groups==len(ev) and orders_replayed==len(events)
    return {'paths_replayed':groups,'orders_replayed':orders_replayed,'max_time_difference_minutes':max_time,'max_notional_difference_usd_million':max_amount,'counts_censoring_and_backlog':'passed','observed_late_valid_notice_count':late_notices,'nominal_queue_starts_within_outage':nominal_in_outage,'algorithm':'Remove downtime from active-service clock, schedule FIFO work there, invert to physical time; independently classify deadlines, censoring and backlog.'}

if __name__=='__main__':
    result=audit()
    target=ROOT/'results/independent_epn_tba_audit.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ['simulation_id','passed','tolerances','tba','epn']},ensure_ascii=False,indent=2))

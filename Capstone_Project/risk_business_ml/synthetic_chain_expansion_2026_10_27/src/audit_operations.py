"""Independent replay of saved service-operation inputs, gates and queue ledgers.

Does not import or call service_operations.py. A separate active-service clock
rebuilds suspended processing, deadlines, incomplete instructions and cash use.
This checks arithmetic under frozen assumptions, never empirical transmission.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()


def optional(value):
    return None if value is None or pd.isna(value) else value


def checked_equal(actual, expected, label, residuals):
    actual, expected = optional(actual), optional(expected)
    if actual is None or expected is None:
        if actual is not None or expected is not None:
            raise AssertionError(f'{label}: {actual!r} != {expected!r}')
        return
    if isinstance(expected,(bool,np.bool_)):
        if isinstance(actual,str):
            if actual not in ['True','False','true','false','0','1']:
                raise AssertionError(f'{label}: unrecognized saved boolean')
            actual=actual in ['True','true','1']
        if bool(actual) != bool(expected):
            raise AssertionError(f'{label}: boolean mismatch')
        return
    if isinstance(expected,(int,float,np.number)):
        difference=abs(float(actual)-float(expected))
        residuals[label]=max(residuals.get(label,0.0),difference)
        if not math.isclose(float(actual),float(expected),rel_tol=1e-11,abs_tol=1e-9):
            raise AssertionError(f'{label}: {actual!r} != {expected!r}')
    elif str(actual) != str(expected):
        raise AssertionError(f'{label}: {actual!r} != {expected!r}')


def finish_on_active_clock(start, work, outage):
    """Convert wall time to available-service time, add work, then invert.

    The inverse chooses the first wall time for service-clock ties. Therefore a
    job ending exactly at outage start completes there rather than at recovery.
    """
    if outage is None:
        return start+work
    a,b=outage
    active_start=start-max(0.0,min(start,b)-a)
    active_target=active_start+work
    return active_target if active_target<=a else active_target+(b-a)


def verify_declared_configuration(group, model, role, cfg, residuals):
    """Re-derive service-specific gates/dependencies from frozen assumptions."""
    stressed=role in ['stress','mitigation','sensitivity']
    expected_count=cfg['base_orders']
    if model in ['acats_wave','fundserv_gross'] and stressed:
        expected_count*=cfg['severe_volume_multiplier'] if role=='sensitivity' else cfg['stress_volume_multiplier']
    if len(group)!=expected_count:
        raise AssertionError('Workload count differs from declared scenario')
    capacity=cfg['mitigation_capacity_per_min'] if role=='mitigation' and model in ['acats_wave','fundserv_gross'] else cfg['processing_capacity_per_min']
    outage=None
    if model in ['dtc_canadian_link','nscc_international_link'] and stressed:
        prefix='dtc' if model=='dtc_canadian_link' else 'nscc'
        end=cfg['link_severe_outage_end_min'] if role=='sensitivity' else cfg[prefix+'_link_repaired_outage_end_min'] if role=='mitigation' else cfg[prefix+'_link_stress_outage_end_min']
        outage=(cfg[prefix+'_link_outage_start_min'],end)
    cash=None
    if model=='fundserv_gross':
        redemption_total=float(group.loc[group.operation.eq('redemption'),'notional_usd_million'].sum())
        cash=redemption_total*(cfg['fundserv_stress_redemption_cash_multiple'] if role in ['stress','sensitivity'] else cfg['fundserv_baseline_redemption_cash_multiple'])
    for r in group.to_dict('records'):
        order_index=int(str(r['order_id'])[1:])
        security=int(r['security_group'])
        gate, lane, exposed=0.0,'service',False
        if model=='mmi_ack':
            operation='maturity' if order_index%2==0 else 'issuance'
            affected=stressed and security<(2 if role=='sensitivity' else 1)
            gate=(cfg['mmi_repaired_ack_min'] if role=='mitigation' else None) if affected else cfg['mmi_baseline_ack_min']
            checked_equal(r['funding_acknowledgement_required'],True,'funding_acknowledgement_required',residuals)
            checked_equal(r['funding_acknowledgement_received'],not affected or role=='mitigation','funding_acknowledgement_received',residuals)
            checked_equal(r['acronym_id'],'MMI_'+str(security),'acronym_id',residuals)
        elif model=='registration':
            operation='deposit'
            affected=stressed and security<(2 if role=='sensitivity' else 1)
            gate=(cfg['registration_repaired_min'] if role=='mitigation' else None) if affected else cfg['registration_baseline_min']
            checked_equal(r['registration_required'],True,'registration_required',residuals)
        elif model=='security_restriction':
            operation='deposit' if order_index%2==0 else 'book_entry_transfer'
            restriction=('global_lock' if role=='sensitivity' else 'deposit_chill') if stressed and security==0 else 'none'
            affected=restriction=='global_lock' or (restriction=='deposit_chill' and operation=='deposit')
            gate=(cfg['restriction_release_min'] if role=='mitigation' else None) if affected else 0.0
            checked_equal(r['explicit_dtc_restriction'],restriction,'explicit_dtc_restriction',residuals)
            checked_equal(r['trading_halt_observed'],role=='unrelated' and security==0,'trading_halt_observed',residuals)
        elif model=='fundserv_gross':
            operation='purchase' if order_index%2==0 else 'redemption'
            checked_equal(r['purchase_cash_independently_prefunded'],True,'purchase_cash_independently_prefunded',residuals)
        elif model=='acats_wave':
            operation='account_transfer'
            checked_equal(r['transfer_source_broker'],'synthetic_exiting_broker' if stressed else 'synthetic_ordinary_broker','transfer_source_broker',residuals)
        elif model in ['dtc_canadian_link','nscc_international_link']:
            prefix='dtc' if model=='dtc_canadian_link' else 'nscc'
            dependency=r['route_uniform']<cfg[prefix+'_link_exposed_share']
            operation='cross_border_instruction' if dependency else 'domestic_instruction'
            lane='link_exposed' if dependency else 'domestic'
            exposed=dependency and stressed
            checked_equal(r['link_id'],'DTC_CDS_synthetic_link' if prefix=='dtc' else 'NSCC_foreign_FI_synthetic_link','link_id',residuals)
            checked_equal(r['actual_dependency_verified'],False,'actual_dependency_verified',residuals)
        else:
            raise AssertionError('Unexpected operation model '+str(model))
        for name,value in [('operation',operation),('gate_time_min',gate),('lane_id',lane),('outage_exposed',exposed),
                           ('config_capacity_per_min',capacity),('config_deadline_min',cfg['deadline_min']),
                           ('config_horizon_min',cfg['horizon_min']),('config_settlement_lag_min',cfg['settlement_lag_min']),
                           ('outage_start_min',outage[0] if outage else None),('outage_end_min',outage[1] if outage else None),
                           ('config_redemption_cash_usd_million',cash)]:
            checked_equal(r[name],value,'input:'+name,residuals)
    return capacity,outage,cash


def replay(group, *, capacity, outage, cash, deadline, horizon, lag):
    inputs=[]
    for row in group.to_dict('records'):
        gate=optional(row['gate_time_min'])
        inputs.append({**row,'ready':max(row['arrival_min'],gate) if gate is not None else math.inf})
    inputs.sort(key=lambda r:(r['ready'],str(r['order_id'])))
    last_finish=defaultdict(float)
    observed=[]
    for row in inputs:
        ready=row['ready']
        start=max(ready,last_finish[row['lane_id']])
        if math.isinf(start):
            finish=planned=math.inf
        else:
            finish=finish_on_active_clock(start,row['work_units']/capacity,outage if row['outage_exposed'] else None)
            last_finish[row['lane_id']]=finish
            planned=finish+lag
        before=cash
        blocked=False
        if cash is not None and row['operation']=='redemption' and planned<=horizon:
            if row['notional_usd_million']>cash+1e-12:
                blocked=True
                planned=math.inf
            else:
                cash-=row['notional_usd_million']
        complete=planned<=horizon
        late=bool(complete and planned>deadline)
        observed.append({
            'order_id':row['order_id'],'operation':row['operation'],
            'notional_usd_million':row['notional_usd_million'],
            'eligible_min':ready if math.isfinite(ready) else None,
            'gate_unfulfilled':optional(row['gate_time_min']) is None,
            'processing_start_min':start if start<=horizon else None,
            'processing_finish_min':finish if finish<=horizon else None,
            'planned_finish_min':planned if math.isfinite(planned) else None,
            'settlement_complete_min':planned if complete else None,
            'completed_within_horizon':complete,'completed_late':late,
            'unfinished_at_horizon':not complete,'overdue_at_deadline':planned>deadline,
            'delay_lower_bound_min':max(0.0,min(planned,horizon)-deadline),
            'cash_blocked':blocked,'redemption_cash_before_usd_million':before,
            'redemption_cash_after_usd_million':cash,
        })
    amounts=np.array([r['notional_usd_million'] for r in observed])
    complete=np.array([r['completed_within_horizon'] for r in observed])
    late=np.array([r['completed_late'] for r in observed])
    overdue=np.array([r['overdue_at_deadline'] for r in observed])
    purchase=np.array([r['operation']=='purchase' for r in observed])
    redemption=np.array([r['operation']=='redemption' for r in observed])
    summary={
        'order_count':len(observed),'completed_count':int(complete.sum()),
        'completed_late_count':int(late.sum()),'unfinished_count':int((~complete).sum()),
        'overdue_count':int(overdue.sum()),'overdue_fraction':float(overdue.mean()),
        'unfinished_fraction':float((~complete).mean()),
        'gross_instruction_notional_usd_million':float(amounts.sum()),
        'completed_notional_usd_million':float(amounts[complete].sum()),
        'unfinished_notional_usd_million':float(amounts[~complete].sum()),
        'overdue_notional_usd_million':float(amounts[overdue].sum()),
        'mean_delay_lower_bound_min':float(np.mean([r['delay_lower_bound_min'] for r in observed])),
        'purchases_usd_million':float(amounts[purchase].sum()),
        'redemptions_usd_million':float(amounts[redemption].sum()),
        'net_fund_flow_usd_million':float(amounts[purchase].sum()-amounts[redemption].sum()),
        'completed_redemptions_usd_million':float(amounts[redemption & complete].sum()),
        'cash_blocked_count':sum(r['cash_blocked'] for r in observed),
        'redemption_cash_end_usd_million':cash,
    }
    return observed,summary


def run():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    plan=json.loads((ROOT/'config/resolved_plan.json').read_text())
    definitions={r['scenario_id']:r for r in json.loads((ROOT/'results/scenario_definitions.json').read_text())}
    names=['ops_inputs','ops_events','ops_runs']
    for name in names:
        if sha(ROOT/'data'/f'{name}.csv')!=receipt['csv_sha256'][name]:
            raise AssertionError('Saved CSV differs from execution receipt: '+name)
    if sha(ROOT/'src/service_operations.py')!=plan['engine_sha256']['service_operations']:
        raise AssertionError('Operation engine differs from frozen source')
    tables={name:pd.read_csv(ROOT/'data'/f'{name}.csv',float_precision='round_trip',dtype={'scenario_seed':str},low_memory=False) for name in names}
    for table in tables.values():
        assert table.source_type.eq('synthetic').all() and not table.empirical_validation.any()
    events=tables['ops_events'].set_index(['scenario_id','replicate_id','order_id'])
    runs=tables['ops_runs'].set_index(['scenario_id','replicate_id'])
    residuals={}
    paths=orders=0
    for (scenario,rep),group in tables['ops_inputs'].groupby(['scenario_id','replicate_id'],sort=True):
        spec=definitions[scenario]
        capacity,outage,initial_cash=verify_declared_configuration(group,spec['model_id'],spec['role'],plan['models']['service_operations'],residuals)
        cfg=plan['models']['service_operations']
        replayed,total=replay(group,capacity=capacity,outage=outage,cash=initial_cash,
                              deadline=cfg['deadline_min'],horizon=cfg['horizon_min'],lag=cfg['settlement_lag_min'])
        for result in replayed:
            saved=events.loc[(scenario,rep,result['order_id'])]
            for key,value in result.items():
                if key!='order_id':
                    checked_equal(saved[key],value,'event:'+key,residuals)
        saved=runs.loc[(scenario,rep)]
        total['redemption_cash_initial_usd_million']=initial_cash
        total['primary_value']=total['overdue_fraction']
        for key,value in total.items():
            checked_equal(saved[key],value,'run:'+key,residuals)
        checked_equal(saved['primary_metric'],'overdue_fraction','primary_metric',residuals)
        checked_equal(saved['primary_units'],'fraction_of_instructions','primary_units',residuals)
        assert group.scenario_seed.nunique()==1
        paths+=1
        orders+=len(group)
    report={
        'simulation_id':receipt['simulation_id'],'passed':True,
        'independent_method':'Read-only CSV replay; gates/dependencies re-derived from frozen configuration, processing rebuilt using a separate active-service clock, then deadline/censoring and cash ledgers recomputed; no engine import/calls.',
        'models_replayed':int(tables['ops_runs'].model_id.nunique()),
        'scenario_paths_replayed':paths,'order_paths_replayed':orders,
        'max_absolute_difference':max(residuals.values(),default=0.0),
        'max_residuals_by_field':residuals,
        'input_csv_sha256':{name:sha(ROOT/'data'/f'{name}.csv') for name in names},
        'frozen_engine_sha256':plan['engine_sha256']['service_operations'],
        'scope_limit':'Implementation and assumed mechanism arithmetic only; not service-specific historical validation or calibrated risk.',
    }
    (ROOT/'results/independent_operations_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','models_replayed','scenario_paths_replayed','order_paths_replayed','max_absolute_difference']},indent=2))
    return report


if __name__=='__main__':
    run()

"""Independent CSV replay of the six default/funding toy mechanisms.

This verifier does not import or call the model engine. It reconstructs each
result from saved source inputs and frozen assumptions, then checks saved
traces and aggregate outputs. Passing is implementation QA, not validation of
actual DTCC behavior or calibrated risks.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def truth(value):
    if isinstance(value,(bool,np.bool_)):return bool(value)
    if str(value).lower() in ('true','1','1.0'):return True
    if str(value).lower() in ('false','0','0.0'):return False
    raise AssertionError('Not an explicit boolean: '+repr(value))


def audit():
    plan=json.loads((ROOT/'config/resolved_plan.json').read_text())
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    cfg=plan['models']['default_funding']
    assert sha(ROOT/'src/default_funding.py')==plan['engine_sha256']['default_funding']
    frames={}
    hashes={}
    for key in ('df_runs','df_inputs','df_traces'):
        path=ROOT/'data'/f'{key}.csv'
        hashes[key]=sha(path)
        assert hashes[key]==receipt['csv_sha256'][key]
        frames[key]=pd.read_csv(path,float_precision='round_trip',dtype={'scenario_seed':'string'},low_memory=False)
        assert frames[key].source_type.eq('synthetic').all()
        assert not frames[key].empirical_validation.map(truth).any()
    runs,inputs,traces=(frames[k] for k in ('df_runs','df_inputs','df_traces'))
    input_groups={k:f for k,f in inputs.groupby(['scenario_id','replicate_id'],sort=False)}
    trace_groups={k:f for k,f in traces.groupby(['scenario_id','replicate_id'],sort=False)}
    residuals=defaultdict(float)
    traced=0
    def number(actual,expected,field):
        if expected is None:
            assert pd.isna(actual),(field,actual,expected)
            return
        actual=float(actual);expected=float(expected)
        assert math.isfinite(actual) and math.isfinite(expected),(field,actual,expected)
        gap=abs(actual-expected)
        residuals[field]=max(residuals[field],gap)
        assert gap<=1e-8+abs(expected)*2e-12,(field,actual,expected,gap)
    def state(actual,expected,field):assert truth(actual)==bool(expected),(field,actual,expected)
    for run in runs.to_dict('records'):
        model=run['model_id'];role=run['scenario_id'].removeprefix('df_'+model+'_')
        active=role not in ('baseline','unrelated')
        key=(run['scenario_id'],run['replicate_id'])
        fi=input_groups[key];ft=trace_groups[key]
        assert fi.scenario_seed.eq(run['scenario_seed']).all() and ft.scenario_seed.eq(run['scenario_seed']).all()
        if model=='gsd_default':
            d=fi[fi.input_type.eq('default_loss_and_resources')].iloc[0]
            survivors=fi[fi.input_type.eq('survivor_capacity')]
            capacities=dict(zip(survivors.input_id,survivors.capacity_usd_million.astype(float)))
            multiple=2.5 if role=='sensitivity_low' else 6.0 if role=='sensitivity_high' else cfg['default_shock_loss_multiple']
            loss=float(d.base_closeout_loss_usd_million)*multiple if active else 0.0
            own=float(d.own_resources_usd_million)*(cfg['default_buffer_multiple'] if role=='mitigation' else 1)
            own_used=min(loss,own);residual=max(0.0,loss-own)
            total_cap=math.fsum(capacities.values());shared=min(residual,total_cap);uncovered=max(0.0,residual-total_cap)
            for field,expected in {
                'loss_usd_million':loss,'own_resources_usd_million':own,
                'own_resources_used_usd_million':own_used,'residual_after_own_usd_million':residual,
                'hypothetical_shared_capacity_usd_million':total_cap,
                'hypothetical_shared_used_usd_million':shared,'unallocated_loss_usd_million':uncovered,
                'primary_value':residual,
            }.items():number(run[field],expected,'default:'+field)
            allocated=0.0
            for row in ft.to_dict('records'):
                expected=shared*capacities[row['member_id']]/total_cap if total_cap else 0
                number(row['hypothetical_allocation_usd_million'],expected,'default:member_allocation')
                assert expected<=capacities[row['member_id']]+1e-10
                allocated+=float(row['hypothetical_allocation_usd_million'])
            number(allocated+own_used+uncovered,loss,'default:loss_conservation')
            state(run['default_activated'],active,'default:activation')
        elif model=='cns_closeout':
            day=1 if role in ('mitigation','sensitivity_low') else 9 if role=='sensitivity_high' else cfg['cns_shock_delay_days']
            adverse=cfg['cns_daily_adverse_move']*math.sqrt(day) if active else 0
            positions=fi.set_index('position_id')
            gross=fees=loss=0.0
            for row in ft.to_dict('records'):
                p=positions.loc[row['position_id']]
                quantity=float(p.quantity);price=float(p.opening_price)
                notional=abs(quantity)*price/1e6
                expected_close=price*(1-(1 if quantity>=0 else -1)*adverse)
                expected_loss=notional*adverse
                expected_fee=notional*cfg['cns_cost_fraction'] if active else 0
                number(row['closing_price'],expected_close,'cns:closing_price')
                number(row['signed_pnl_usd_million'],-expected_loss,'cns:signed_pnl')
                number(row['transaction_cost_usd_million'],expected_fee,'cns:fee')
                number(row['gross_notional_usd_million'],notional,'cns:notional')
                gross+=notional;fees+=expected_fee;loss+=expected_loss
            for field,expected in {'primary_value':loss+fees,'closeout_loss_usd_million':loss+fees,
                                   'net_pnl_usd_million':-loss,'gross_notional_usd_million':gross,
                                   'transaction_cost_usd_million':fees,'assumed_adverse_price_fraction':adverse}.items():
                number(run[field],expected,'cns:'+field)
            state(run['default_activated'],active,'cns:activation')
        elif model=='gcf_deadline':
            haircut=(.15 if role=='sensitivity_low' else .40 if role=='sensitivity_high' else cfg['gcf_shock_haircut']) if active else 0
            cash_fraction=cfg['gcf_shock_cash_fraction'] if active else 1
            delay=cfg['gcf_shock_delay_min'] if active and role!='mitigation' else 0
            extra=.6 if role=='mitigation' else 0
            by_id=fi.set_index('obligation_id');failed_amount=0.0;failed_count=late=unfinished=0
            cash_gap=coll_gap=0.0
            for row in ft.to_dict('records'):
                original=by_id.loc[row['obligation_id']]
                cash=float(original.cash_available_usd_million)*cash_fraction+float(original.cash_required_usd_million)*extra
                coll=float(original.collateral_market_usd_million)*(1-haircut)+float(original.collateral_required_usd_million)*extra
                ct=float(original.cash_ready_min)+delay;st=float(original.collateral_ready_min)+delay
                eligible=cash+1e-10>=float(original.cash_required_usd_million) and coll+1e-10>=float(original.collateral_required_usd_million)
                finish=max(ct,st) if eligible else math.inf
                complete=finish<=cfg['horizon_min'];ontime=finish<=cfg['gcf_deadline_min']
                cg=max(0.0,float(original.cash_required_usd_million)-cash)
                sg=max(0.0,float(original.collateral_required_usd_million)-coll)
                for field,expected in {'cash_available_usd_million':cash,'eligible_collateral_usd_million':coll,
                    'cash_ready_min':ct,'collateral_ready_min':st,'completion_min':finish if complete else None,
                    'cash_shortfall_usd_million':cg,'collateral_shortfall_usd_million':sg}.items():
                    number(row[field],expected,'gcf:'+field)
                for field,expected in {'completed_by_horizon':complete,'late_completed':complete and not ontime,
                    'unfinished_at_horizon':not complete,'failed_at_deadline':not ontime}.items():state(row[field],expected,'gcf:'+field)
                if not ontime:failed_amount+=float(original.notional_usd_million);failed_count+=1
                late+=int(complete and not ontime);unfinished+=int(not complete);cash_gap+=cg;coll_gap+=sg
            for field,expected in {'primary_value':failed_amount,'failed_deadline_notional_usd_million':failed_amount,
                'failed_deadline_count':failed_count,'late_completed_count':late,'unfinished_count':unfinished,
                'cash_shortfall_usd_million':cash_gap,'collateral_shortfall_usd_million':coll_gap}.items():number(run[field],expected,'gcf:'+field)
        elif model=='auction_funding':
            scheduled=defaultdict(float)
            total=math.fsum(fi.net_cash_due_usd_million.astype(float))
            for i,original in enumerate(fi.to_dict('records')):
                day=i%2 if active and role=='sensitivity_low' else 0 if active else int(original['issue_day'])
                scheduled[day]+=float(original['net_cash_due_usd_million'])*(1.5 if role=='sensitivity_high' else 1)
            opening=total*(cfg['auction_opening_cash_fraction']+(.75 if role=='mitigation' else 0))
            cash=opening;unpaid=0.0;cum_due=cum_paid=0.0;peak=0.0
            for row in ft.sort_values('day').to_dict('records'):
                day=int(row['day']);funding=total*cfg['auction_daily_cash_fraction']
                cash+=funding;new=scheduled[day];cum_due+=new
                pay=min(cash,unpaid+new);cash-=pay;unpaid+=new-pay;cum_paid+=pay;peak=max(peak,unpaid)
                for field,expected in {'new_cash_due_usd_million':new,'cash_funding_usd_million':funding,
                    'cash_paid_usd_million':pay,'unpaid_due_usd_million':unpaid,'closing_cash_usd_million':cash,
                    'cumulative_due_usd_million':cum_due,'cumulative_paid_usd_million':cum_paid}.items():number(row[field],expected,'auction:'+field)
                number(opening+(day+1)*funding-cum_paid,cash,'auction:cash_conservation')
                number(cum_due-cum_paid,unpaid,'auction:obligation_conservation')
            for field,expected in {'primary_value':peak,'peak_unpaid_due_usd_million':peak,
                'terminal_unpaid_usd_million':unpaid,'terminal_cash_usd_million':cash,'total_paid_usd_million':cum_paid}.items():number(run[field],expected,'auction:'+field)
        elif model in ('dtc_bank','nscc_bank'):
            service='DTC' if model=='dtc_bank' else 'NSCC'
            assert set(fi.service)=={service} and set(ft.service)=={service}
            blocked=2 if role=='sensitivity_high' else 1 if active else 0
            blocked_gross_debit=blocked_gross_credit=netdebit=0.0;banks_blocked=0
            by_bank={k:f for k,f in fi.groupby('bank_id',sort=True)}
            sorted_banks=sorted(by_bank)
            for row in ft.to_dict('records'):
                bank=row['bank_id'];balances=by_bank[bank].signed_balance_usd_million.astype(float)
                ack=cfg['bank_deadline_min'] if role=='mitigation' else cfg['bank_deadline_min']+15 if role=='sensitivity_low' and sorted_banks.index(bank)<blocked else cfg['bank_shock_ack_min'] if sorted_banks.index(bank)<blocked else 300
                accepted=ack<=cfg['bank_deadline_min']
                debit=math.fsum(x for x in balances if x>0);credit=math.fsum(-x for x in balances if x<0);net=debit-credit
                for field,expected in {'gross_debit_usd_million':debit,'gross_credit_usd_million':credit,
                    'aggregate_net_net_usd_million':net,'acknowledgement_min':ack,
                    'blocked_gross_debit_usd_million':0 if accepted else debit,
                    'blocked_gross_credit_usd_million':0 if accepted else credit,
                    'unsettled_net_debit_usd_million':0 if accepted else max(0.0,net)}.items():number(row[field],expected,'banks:'+field)
                state(row['accepted_by_deadline'],accepted,'banks:accepted_by_deadline')
                if not accepted:blocked_gross_debit+=debit;blocked_gross_credit+=credit;netdebit+=max(0.0,net);banks_blocked+=1
            for field,expected in {'primary_value':blocked_gross_debit,'blocked_participant_debit_usd_million':blocked_gross_debit,
                'blocked_participant_credit_usd_million':blocked_gross_credit,'unsettled_bank_net_debit_usd_million':netdebit,
                'banks_blocked':banks_blocked}.items():number(run[field],expected,'banks:'+field)
        else:raise AssertionError('Unknown model '+model)
        traced+=len(ft)
    result={
        'passed':True,'simulation_id':receipt['simulation_id'],
        'method':'Independent replay from saved CSV inputs and frozen assumptions; engine functions never imported or called.',
        'models_checked':sorted(runs.model_id.unique().tolist()),'runs_checked':len(runs),'traces_checked':traced,
        'max_absolute_residuals':dict(sorted(residuals.items())),
        'csv_sha256':hashes,'model_source_sha256':plan['engine_sha256']['default_funding'],
        'claim_limit':'Implementation/accounting QA only; not empirical validation, default probability or official risk-formula replication.',
    }
    output=ROOT/'results/independent_default_audit.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','runs_checked','traces_checked')}))
    return result


if __name__=='__main__':audit()

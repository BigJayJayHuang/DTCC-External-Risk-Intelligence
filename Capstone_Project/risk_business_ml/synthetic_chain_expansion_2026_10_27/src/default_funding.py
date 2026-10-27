"""Synthetic default/funding mechanism experiments, not DTCC production models.

Money is USD million; deadlines are relative hypothetical simulation minutes.
No frequencies, fees, official waterfall sequence or actual member mappings are
inferred. A simulated default activation is an input, never a probability.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

DEFAULT_CONFIG = {
    'units': 'USD million',
    'default_loss_median': 12.0,
    'default_loss_sigma': 0.40,
    'own_resources_median': 22.0,
    'shared_capacity_median': 24.0,
    'surviving_members': 8,
    'default_shock_loss_multiple': 4.0,
    'default_buffer_multiple': 2.0,
    'cns_positions': 12,
    'cns_price': 100.0,
    'cns_notional_median': 8.0,
    'cns_daily_adverse_move': 0.035,
    'cns_cost_fraction': 0.001,
    'cns_shock_delay_days': 4.0,
    'gcf_obligations': 12,
    'gcf_deadline_min': 300.0,
    'horizon_min': 480.0,
    'gcf_shock_cash_fraction': 0.85,
    'gcf_shock_haircut': 0.25,
    'gcf_shock_delay_min': 150.0,
    'auction_issues': 12,
    'auction_days': 4,
    'auction_daily_cash_fraction': 0.30,
    'auction_opening_cash_fraction': 0.10,
    'bank_participants': 12,
    'bank_count': 3,
    'bank_deadline_min': 420.0,
    'bank_shock_ack_min': 510.0,
}

MODELS = {
    'gsd_default': ('FICC-GSD-06', '违约资源与假设剩余损失分配', 'Default resources and hypothetical residual allocation'),
    'cns_closeout': ('ECS-NSCC-06', 'CNS多空头寸平仓', 'CNS long/short close-out'),
    'gcf_deadline': ('FICC-GSD-05', 'GCF抵押品及现金到期门槛', 'GCF collateral/cash deadline gates'),
    'auction_funding': ('FICC-GSD-10', '拍卖发行日资金集中', 'Auction issue-date funding concentration'),
    'dtc_bank': ('ECS-DTC-02', 'DTC结算银行汇总净额门槛', 'DTC settling-bank aggregate gate'),
    'nscc_bank': ('ECS-NSCC-07', 'NSCC结算银行汇总净额门槛', 'NSCC settling-bank aggregate gate'),
}


def _finite(value, name, nonnegative=True):
    value = float(value)
    if not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError(name+' must be finite'+(' and nonnegative' if nonnegative else ''))
    return value


def allocate_default_loss(loss, own_resources, surviving_capacities, *, activated=True):
    """Declared toy two-layer allocation; NOT the official GSD loss waterfall.

    Apply own resources, then prorate the residual across hypothetical survivor
    capacities, capped at their sum. Unallocated loss remains explicit.
    """
    loss = _finite(loss, 'loss')
    own_resources = _finite(own_resources, 'own_resources')
    capacities = np.asarray(surviving_capacities, dtype=float)
    if capacities.ndim != 1 or len(capacities) == 0 or not np.all(np.isfinite(capacities)) or np.any(capacities < 0):
        raise ValueError('At least one finite nonnegative survivor capacity required')
    loss = loss if activated else 0.0
    own_used = min(loss, own_resources)
    residual = max(0.0, loss-own_used)
    available = float(capacities.sum())
    collective_used = min(residual, available)
    allocations = capacities/available*collective_used if available > 0 else capacities*0.0
    uncovered = max(0.0, residual-collective_used)
    return {'loss_usd_million': loss, 'own_resources_usd_million': own_resources,
            'own_resources_used_usd_million': own_used,
            'residual_after_own_usd_million': residual,
            'hypothetical_shared_capacity_usd_million': available,
            'hypothetical_shared_used_usd_million': collective_used,
            'unallocated_loss_usd_million': uncovered,
            'allocations': allocations.tolist(),
            'loss_conservation_residual': loss-own_used-float(allocations.sum())-uncovered}


def closeout_positions(positions, *, adverse_fraction, delay_days, cost_fraction=0.0, activated=True):
    """Close long holdings lower and buy short holdings higher, by assumption.

    Quantity is signed; notional is abs(quantity)*opening_price/1e6. The adverse
    fraction grows with sqrt(delay), a declared stress mapping, not a forecast.
    """
    adverse_fraction = _finite(adverse_fraction, 'adverse_fraction')
    delay_days = _finite(delay_days, 'delay_days')
    cost_fraction = _finite(cost_fraction, 'cost_fraction')
    move = adverse_fraction*math.sqrt(delay_days) if activated else 0.0
    if move >= 1: raise ValueError('Stress move must stay below 100 percent')
    rows = []
    for i, p in enumerate(positions):
        q = _finite(p['quantity'], 'quantity', False)
        price = _finite(p['opening_price'], 'opening_price')
        if price <= 0: raise ValueError('Opening price must be positive')
        sign = 1 if q >= 0 else -1
        closing = price*(1-sign*move)
        pnl = q*(closing-price)/1e6 if activated else 0.0
        fee = abs(q)*price/1e6*cost_fraction if activated else 0.0
        rows.append({'position_id': str(p.get('position_id',i)), 'quantity':q,
                     'opening_price':price, 'closing_price':closing,
                     'signed_pnl_usd_million':pnl, 'transaction_cost_usd_million':fee,
                     'gross_notional_usd_million':abs(q)*price/1e6,
                     'delay_days':delay_days if activated else 0.0})
    if not rows: raise ValueError('At least one position required')
    pnl=sum(r['signed_pnl_usd_million'] for r in rows)
    fee=sum(r['transaction_cost_usd_million'] for r in rows)
    return rows, {'closeout_loss_usd_million':max(0.0,-pnl)+fee,
                  'net_pnl_usd_million':pnl,'transaction_cost_usd_million':fee,
                  'gross_notional_usd_million':sum(r['gross_notional_usd_million'] for r in rows),
                  'assumed_adverse_price_fraction':move}


def gcf_deadline(obligations, *, deadline_min, horizon_min, haircut=0.0,
                 cash_fraction=1.0, cash_delay_min=0.0, collateral_delay_min=0.0,
                 extra_cash_fraction=0.0, extra_collateral_fraction=0.0):
    """Toy allocation units require both legs; no calibrated fees are imposed."""
    deadline=_finite(deadline_min,'deadline');horizon=_finite(horizon_min,'horizon')
    cut=_finite(haircut,'haircut');cash_fraction=_finite(cash_fraction,'cash_fraction')
    cash_delay_min=_finite(cash_delay_min,'cash delay');collateral_delay_min=_finite(collateral_delay_min,'collateral delay')
    extra_cash_fraction=_finite(extra_cash_fraction,'extra cash fraction');extra_collateral_fraction=_finite(extra_collateral_fraction,'extra collateral fraction')
    if deadline>horizon or cut>=1:raise ValueError('Require deadline <= horizon and haircut < 1')
    rows=[]
    for i,o in enumerate(obligations):
        due=_finite(o['notional_usd_million'],'notional')
        cash_need=_finite(o['cash_required_usd_million'],'cash need')
        collateral_need=_finite(o['collateral_required_usd_million'],'collateral need')
        cash=_finite(o['cash_available_usd_million'],'cash')*cash_fraction+cash_need*extra_cash_fraction
        collateral=_finite(o['collateral_market_usd_million'],'collateral market')*(1-cut)+collateral_need*extra_collateral_fraction
        cash_ready=_finite(o['cash_ready_min'],'cash ready')+cash_delay_min
        collateral_ready=_finite(o['collateral_ready_min'],'collateral ready')+collateral_delay_min
        eligible=cash+1e-10>=cash_need and collateral+1e-10>=collateral_need
        completion=max(cash_ready,collateral_ready) if eligible else None
        complete=eligible and completion<=horizon
        ontime=eligible and completion<=deadline
        rows.append({'obligation_id':str(o.get('obligation_id',i)),
                     'notional_usd_million':due,'cash_required_usd_million':cash_need,
                     'collateral_required_usd_million':collateral_need,
                     'cash_available_usd_million':cash,'eligible_collateral_usd_million':collateral,
                     'cash_ready_min':cash_ready,'collateral_ready_min':collateral_ready,
                     'completion_min':completion if complete else None,'completed_by_horizon':bool(complete),
                     'late_completed':bool(complete and not ontime),'unfinished_at_horizon':bool(not complete),
                     'failed_at_deadline':bool(not ontime),
                     'cash_shortfall_usd_million':max(0.0,cash_need-cash),
                     'collateral_shortfall_usd_million':max(0.0,collateral_need-collateral)})
    if not rows:raise ValueError('At least one obligation required')
    total=sum(r['notional_usd_million'] for r in rows)
    failed=sum(r['notional_usd_million'] for r in rows if r['failed_at_deadline'])
    return rows,{'total_notional_usd_million':total,'failed_deadline_notional_usd_million':failed,
                 'failed_deadline_count':sum(r['failed_at_deadline'] for r in rows),
                 'late_completed_count':sum(r['late_completed'] for r in rows),
                 'unfinished_count':sum(r['unfinished_at_horizon'] for r in rows),
                 'cash_shortfall_usd_million':sum(r['cash_shortfall_usd_million'] for r in rows),
                 'collateral_shortfall_usd_million':sum(r['collateral_shortfall_usd_million'] for r in rows)}


def auction_cash_ledger(issue_obligations, *, daily_funding, opening_cash=0.0):
    """Pay due and overdue issue-date obligations; unpaid amounts carry forward.

    No credit is created by this ledger. New cash is an explicit exogenous input.
    All obligations are assumed already netted and netting-eligible.
    """
    opening_cash=_finite(opening_cash,'opening cash')
    funding=[_finite(x,'daily funding') for x in daily_funding]
    if not funding:raise ValueError('At least one funding day required')
    scheduled=np.zeros(len(funding))
    for issue in issue_obligations:
        day=int(issue['issue_day']);amount=_finite(issue['net_cash_due_usd_million'],'issue obligation')
        if day<0 or day>=len(funding) or day!=issue['issue_day']:raise ValueError('Issue day outside horizon')
        scheduled[day]+=amount
    cash=opening_cash;backlog=0.0;cum_requested=0.0;cum_paid=0.0;cum_funding=0.0;rows=[]
    for day,f in enumerate(funding):
        cash+=f;cum_funding+=f;new=float(scheduled[day]);cum_requested+=new
        requested=backlog+new;paid=min(cash,requested);cash-=paid;backlog=requested-paid;cum_paid+=paid
        rows.append({'day':day,'new_cash_due_usd_million':new,'cash_funding_usd_million':f,
                     'cash_paid_usd_million':paid,'unpaid_due_usd_million':backlog,'closing_cash_usd_million':cash,
                     'cumulative_due_usd_million':cum_requested,'cumulative_paid_usd_million':cum_paid,
                     'cash_conservation_residual':opening_cash+cum_funding-cum_paid-cash,
                     'obligation_conservation_residual':cum_requested-cum_paid-backlog})
    return rows,{'peak_unpaid_due_usd_million':max(r['unpaid_due_usd_million'] for r in rows),
                 'terminal_unpaid_usd_million':backlog,'opening_cash_usd_million':opening_cash,
                 'total_cash_funding_usd_million':sum(funding),'total_due_usd_million':float(scheduled.sum()),
                 'terminal_cash_usd_million':cash,'total_paid_usd_million':cum_paid}


def settling_bank_gate(participants, *, service, bank_acceptance_min, deadline_min):
    """Aggregate signed balances separately within one named service.

    Positive balance is participant debit, negative is credit. A refusal or
    late acknowledgement blocks the represented balances in this toy model.
    No cross-service netting, reassignment or recovery guarantee is assumed.
    """
    if service not in {'DTC','NSCC'}:raise ValueError('Service must be DTC or NSCC')
    deadline=_finite(deadline_min,'deadline');banks={};seen=set()
    for p in participants:
        if p.get('service',service)!=service:raise ValueError('Cross-service participants cannot be netted')
        pid=str(p['participant_id']);bank=str(p['bank_id']);balance=_finite(p['signed_balance_usd_million'],'signed balance',False)
        if pid in seen:raise ValueError('Duplicate participant');
        seen.add(pid);banks.setdefault(bank,[]).append((pid,balance))
    if not banks:raise ValueError('At least one participant required')
    rows=[]
    for bank,items in sorted(banks.items()):
        ack=bank_acceptance_min.get(bank)
        ack=_finite(ack,'acceptance time') if ack is not None else None
        accepted=ack is not None and ack<=deadline
        debit=sum(max(0,b) for _,b in items);credit=sum(max(0,-b) for _,b in items);net=debit-credit
        rows.append({'service':service,'bank_id':bank,'participant_count':len(items),
                     'gross_debit_usd_million':debit,'gross_credit_usd_million':credit,
                     'aggregate_net_net_usd_million':net,'acknowledgement_min':ack,
                     'accepted_by_deadline':accepted,
                     'blocked_gross_debit_usd_million':0.0 if accepted else debit,
                     'blocked_gross_credit_usd_million':0.0 if accepted else credit,
                     'unsettled_net_debit_usd_million':0.0 if accepted else max(0.0,net),
                     'netting_identity_residual':sum(b for _,b in items)-net})
    return rows,{'blocked_participant_debit_usd_million':sum(r['blocked_gross_debit_usd_million'] for r in rows),
                 'blocked_participant_credit_usd_million':sum(r['blocked_gross_credit_usd_million'] for r in rows),
                 'unsettled_bank_net_debit_usd_million':sum(r['unsettled_net_debit_usd_million'] for r in rows),
                 'banks_blocked':sum(not r['accepted_by_deadline'] for r in rows),
                 'service':service}


def _scenario_specs():
    specs=[]
    role_names=[('baseline','基准','Baseline'),('shock','冲击','Shock'),('mitigation','同一冲击与缓解','Same shock with mitigation'),
                ('unrelated','无关事件对照','Unrelated-event control'),('sensitivity_low','较低冲击假设','Lower stress assumption'),
                ('sensitivity_high','较高冲击假设','Higher stress assumption')]
    for model,(_,cn,en) in MODELS.items():
        for role,rcn,ren in role_names:
            specs.append({'scenario_id':'df_'+model+'_'+role,'model_id':model,'label_cn':cn+'：'+rcn,
                          'label_en':en+': '+ren,'role':role})
    return specs


def run_experiment(seed:int, replications:int, config:dict|None=None):
    cfg={**DEFAULT_CONFIG,**(config or {})}
    if cfg['units']!='USD million':raise ValueError('Only USD million supported')
    if not isinstance(replications,int) or replications<1:raise ValueError('Positive replication count required')
    for key in ['surviving_members','cns_positions','gcf_obligations','auction_issues','auction_days','bank_participants','bank_count']:
        if not isinstance(cfg[key],int) or cfg[key]<1:raise ValueError(key+' must be positive integer')
    if cfg['bank_count']>cfg['bank_participants']:raise ValueError('More banks than participants')
    specs=_scenario_specs();runs=[];inputs=[];traces=[]
    for model_index,(model,_) in enumerate(MODELS.items()):
        for rep in range(replications):
            uint=int(np.random.SeedSequence([int(seed),model_index,rep,481]).generate_state(1,dtype=np.uint64)[0])
            rng=np.random.default_rng(uint)
            if model=='gsd_default':
                base_loss=float(rng.lognormal(math.log(cfg['default_loss_median']),cfg['default_loss_sigma']))
                own=float(rng.lognormal(math.log(cfg['own_resources_median']),0.2))
                capacities=rng.dirichlet(np.ones(cfg['surviving_members'])*2)*float(rng.lognormal(math.log(cfg['shared_capacity_median']),0.25))
                base_input=[{'input_id':'D0','input_type':'default_loss_and_resources','base_closeout_loss_usd_million':base_loss,'own_resources_usd_million':own}]
                base_input += [{'input_id':f'S{i}','input_type':'survivor_capacity','capacity_usd_million':float(x)} for i,x in enumerate(capacities)]
            elif model=='cns_closeout':
                notionals=rng.lognormal(math.log(cfg['cns_notional_median']),0.5,cfg['cns_positions'])
                signs=np.where(np.arange(cfg['cns_positions'])%2==0,1,-1)
                positions=[{'position_id':f'P{i}','quantity':float(s*n*1e6/cfg['cns_price']),'opening_price':cfg['cns_price']} for i,(n,s) in enumerate(zip(notionals,signs))]
                base_input=[{'input_id':p['position_id'],'input_type':'position',**p} for p in positions]
            elif model=='gcf_deadline':
                n=cfg['gcf_obligations'];notionals=rng.lognormal(math.log(6),0.4,n)
                obligations=[{'obligation_id':f'O{i}','notional_usd_million':float(a),'cash_required_usd_million':float(a),'collateral_required_usd_million':float(a),
                              'cash_available_usd_million':float(a*rng.uniform(1.05,1.35)), 'collateral_market_usd_million':float(a*rng.uniform(1.08,1.35)),
                              'cash_ready_min':float(rng.uniform(90,210)),'collateral_ready_min':float(rng.uniform(90,210))} for i,a in enumerate(notionals)]
                base_input=[{'input_id':p['obligation_id'],'input_type':'allocation_unit',**p} for p in obligations]
            elif model=='auction_funding':
                amounts=rng.lognormal(math.log(12),0.4,cfg['auction_issues']);total=float(amounts.sum())
                issues=[{'issue_id':f'A{i}','issue_day':i%cfg['auction_days'],'net_cash_due_usd_million':float(a)} for i,a in enumerate(amounts)]
                funding=[total*cfg['auction_daily_cash_fraction']]*cfg['auction_days']
                base_input=[{'input_id':p['issue_id'],'input_type':'issue_obligation',**p} for p in issues]
            else:
                service='DTC' if model=='dtc_bank' else 'NSCC'
                balances=rng.lognormal(math.log(7 if service=='DTC' else 4),0.45,cfg['bank_participants'])
                # Each bank contains debit and credit members; seed and scale differ by service.
                participants=[{'participant_id':f'{service}_P{i}','bank_id':f'{service}_B{i%cfg["bank_count"]}',
                               'signed_balance_usd_million':float(b*(1 if i<cfg['bank_participants']*0.75 else -0.6)),'service':service} for i,b in enumerate(balances)]
                base_input=[{'input_id':p['participant_id'],'input_type':'bank_member',**p} for p in participants]
                bank_ids=sorted({p['bank_id'] for p in participants})
            for spec in [s for s in specs if s['model_id']==model]:
                role=spec['role'];active=role not in {'baseline','unrelated'}
                tags={'scenario_id':spec['scenario_id'],'replicate_id':rep,'scenario_seed':str(uint),'model_id':model}
                inputs.extend([{**tags,**x} for x in base_input])
                if model=='gsd_default':
                    multiple=2.5 if role=='sensitivity_low' else 6.0 if role=='sensitivity_high' else cfg['default_shock_loss_multiple']
                    result=allocate_default_loss(base_loss*multiple,own*(cfg['default_buffer_multiple'] if role=='mitigation' else 1.0),capacities,activated=active)
                    details=[{'record_type':'allocation','member_id':f'S{i}','hypothetical_allocation_usd_million':a,'capacity_usd_million':float(capacities[i])} for i,a in enumerate(result.pop('allocations'))]
                    metric='residual_loss_after_own_resources';value=result['residual_after_own_usd_million']
                    result.update(default_activated=active,assumed_loss_multiple=multiple)
                elif model=='cns_closeout':
                    days=1.0 if role in {'mitigation','sensitivity_low'} else 9.0 if role=='sensitivity_high' else cfg['cns_shock_delay_days']
                    details,result=closeout_positions(positions,adverse_fraction=cfg['cns_daily_adverse_move'],delay_days=days,cost_fraction=cfg['cns_cost_fraction'],activated=active)
                    metric='conditional_closeout_loss';value=result['closeout_loss_usd_million']
                    result['default_activated']=active
                elif model=='gcf_deadline':
                    cashfraction=cfg['gcf_shock_cash_fraction'] if active else 1.0
                    cut=(0.15 if role=='sensitivity_low' else 0.40 if role=='sensitivity_high' else cfg['gcf_shock_haircut']) if active else 0.0
                    delay=cfg['gcf_shock_delay_min'] if active else 0.0
                    extra=0.6 if role=='mitigation' else 0.0
                    # Mitigation explicitly supplies additional resources earlier, unlike merely extending a cutoff.
                    details,result=gcf_deadline(obligations,deadline_min=cfg['gcf_deadline_min'],horizon_min=cfg['horizon_min'],haircut=cut,cash_fraction=cashfraction,
                                                cash_delay_min=0 if role=='mitigation' else delay,collateral_delay_min=0 if role=='mitigation' else delay,
                                                extra_cash_fraction=extra,extra_collateral_fraction=extra)
                    metric='notional_failing_assumed_deadline';value=result['failed_deadline_notional_usd_million']
                    result.update(assumed_haircut=cut,assumed_cash_fraction=cashfraction,additional_resource_fraction=extra,
                                  additional_cash_usd_million=sum(o['cash_required_usd_million']*extra for o in obligations),
                                  additional_eligible_collateral_usd_million=sum(o['collateral_required_usd_million']*extra for o in obligations))
                elif model=='auction_funding':
                    modified=[dict(x) for x in issues]
                    if active:
                        for i,x in enumerate(modified):
                            x['issue_day']=i%2 if role=='sensitivity_low' else 0
                            if role=='sensitivity_high':x['net_cash_due_usd_million']*=1.5
                    opening=total*(cfg['auction_opening_cash_fraction']+(0.75 if role=='mitigation' else 0))
                    details,result=auction_cash_ledger(modified,daily_funding=funding,opening_cash=opening)
                    metric='peak_unpaid_issue_date_obligation';value=result['peak_unpaid_due_usd_million']
                    result['additional_opening_cash_usd_million']=total*0.75 if role=='mitigation' else 0.0
                else:
                    acknowledgements={bank:300.0 for bank in bank_ids}
                    blockedbanks=0 if not active else 2 if role=='sensitivity_high' else 1
                    for bank in bank_ids[:blockedbanks]:
                        acknowledgements[bank]=cfg['bank_shock_ack_min'] if role!='sensitivity_low' else cfg['bank_deadline_min']+15.0
                    if role=='mitigation':
                        acknowledgements={bank:cfg['bank_deadline_min'] for bank in bank_ids}
                    details,result=settling_bank_gate(participants,service=service,bank_acceptance_min=acknowledgements,deadline_min=cfg['bank_deadline_min'])
                    metric='blocked_participant_gross_debit';value=result['blocked_participant_debit_usd_million']
                traces.extend([{**tags,'trace_index':i,**d} for i,d in enumerate(details)])
                runs.append({**tags,'primary_metric':metric,'primary_value':float(value),'primary_units':'USD million',**result})
    runframe=pd.DataFrame(runs);inputframe=pd.DataFrame(inputs);traceframe=pd.DataFrame(traces)
    checks=[]
    def check(name,passed,detail):checks.append({'name':name,'passed':bool(passed),'detail':detail})
    check('scenario_run_count',len(runs)==len(specs)*replications,'Six submodels, six paired scenarios per submodel')
    check('finite_primary_outputs',np.isfinite(runframe.primary_value).all() and (runframe.primary_value>=0).all(),'Conditional amounts finite and nonnegative')
    for model in MODELS:
        f=runframe[runframe.model_id==model].set_index(['scenario_id','replicate_id'])
        a=f.loc['df_'+model+'_baseline'].primary_value.to_numpy();b=f.loc['df_'+model+'_unrelated'].primary_value.to_numpy()
        check(model+':unrelated_control',np.array_equal(a,b),'Unrelated event changes no modeled dependency')
    d=runframe[runframe.model_id=='gsd_default']
    check('default_loss_conservation',d.loss_conservation_residual.abs().max()<1e-8,'Loss = own resources used + hypothetical collective allocation + unallocated loss')
    a=traceframe[traceframe.model_id=='auction_funding']
    check('auction_cash_conservation',a.cash_conservation_residual.abs().max()<1e-8,'Opening cash + explicit funding = cash paid + closing cash')
    check('auction_obligation_conservation',a.obligation_conservation_residual.abs().max()<1e-8,'Cumulative obligations = paid + unpaid')
    b=traceframe[traceframe.model_id.isin(['dtc_bank','nscc_bank'])]
    check('bank_netting_identity',b.netting_identity_residual.abs().max()<1e-8,'Debit minus credit = aggregate net-net within each service only')
    check('service_isolation',set(b[b.model_id=='dtc_bank'].service)=={'DTC'} and set(b[b.model_id=='nscc_bank'].service)=={'NSCC'},'No balances netted across DTC and NSCC')
    g=traceframe[traceframe.model_id=='gcf_deadline']
    check('gcf_censoring_partition',all(int(r['late_completed'])+int(r['unfinished_at_horizon'])<=1 for r in g.to_dict('records')),'Late completed and unfinished are distinct states')
    check('seed_text',all(isinstance(s,str) for s in inputframe.scenario_seed),'Unsigned seeds retain exact text')
    scopes={
        'gsd_default':('违约后自有资源与剩余损失的假设分配','Conditional own-resource use and toy residual allocation after activated default','未复制官方损失瀑布、评估周期、法定分摊上限或违约发生率','Does not reproduce official waterfall, assessment periods, legal caps or default incidence'),
        'cns_closeout':('假设多空头寸在延迟平仓中的不利价格变化','Adverse repricing of hypothetical long/short positions during delayed close-out','未建模实际CNS头寸、买入成交深度、真实市场路径或违约发生率','No actual CNS positions, buy-in depth, historical paths or default incidence'),
        'gcf_deadline':('虚拟分配单位的现金与抵押品共同到期门槛','Joint cash/collateral deadlines on hypothetical allocation units','未计算官方费用；未复制GCF净头寸方向与实际日内优化','No official fees; no production GCF position-side netting or intraday optimization'),
        'auction_funding':('已假设净额后的发行日现金义务集中','Concentration of assumed netted issue-date cash obligations','未估计拍卖尾差因果作用、实际获配、证券交付或净额率','No auction-tail causal estimate, actual awards, security-delivery leg or netting ratio'),
        'dtc_bank':('DTC专属虚拟银行映射与日终确认门槛','DTC-only hypothetical bank mapping and end-day acknowledgement gate','未复制Fedwire交易、真实结算银行应急安排或银行违约概率','No actual Fedwire transfers, bank contingency arrangements or default probability'),
        'nscc_bank':('NSCC专属虚拟银行映射与日终确认门槛','NSCC-only hypothetical bank mapping and end-day acknowledgement gate','未复制Fedwire交易；未将DTC结果直接用于NSCC','No actual Fedwire transfers; DTC outcomes are not transferred to NSCC'),
    }
    chain_map=[]
    for model,(chain,_,_) in MODELS.items():
        cn,en,ncn,nen=scopes[model]
        chain_map.append({'chain_id':chain,'model_id':model,'scope_cn':cn,'scope_en':en,'not_modeled_cn':ncn,'not_modeled_en':nen})
    assumptions={
        'status':'synthetic_only; implementation/scenario exploration, not empirical chain validation',
        'units':'USD million; relative hypothetical minutes or days; all parameters hypothetical',
        'parameters':cfg,
        'default':'Actual default activation is a chosen scenario input, not a calibrated event probability; the two-layer pro-rata allocation is an illustrative accounting mechanism, not official GSD loss allocation.',
        'cns':'Adverse price = opening price times 1 minus signed position direction times daily_move*sqrt(delay). Every long falls and every short rises in this deliberately adverse scenario. No historical return or probability model is estimated.',
        'gcf':'Each toy allocation unit requires both cash and collateral; this is a transaction-level joint gate rather than a claim every real GCF member owes both legs. Baseline collateral haircut zero. Mitigation injects explicit cash and collateral and restores earlier availability. No fee estimates.',
        'auction':'All generated issue obligations assumed already eligible and netted. Shock moves obligations to one date; higher sensitivity also increases volume by 50%. Unpaid obligations carry forward; funds are not unlimited. Added mitigation cash is explicit.',
        'banks':'Signed participant balances aggregated within service-specific bank IDs. Late acknowledgement/refusal blocks both represented debit and credit balances; net debit is separately reported. Partial payments, reassignment, multilaterally combined DTC/NSCC settlement and production contingency rules are absent. Mitigation assumes timely restored acknowledgement.',
        'paired_design':'Each model/replicate has identical underlying workload across its six scenarios. Scenarios perturb declared activation, resources, scheduling, delay or acknowledgement; bank workloads differ between services.',
        'reference':'Exact chain semantics from supplied chain_registry_v3.json expanded_v3 catalog; numeric formulas are declared assumptions, not copied DTCC rules.',
        'limits':'No synthetic row is a historical event or quarter. No real loss probability, calibrated risk score, causal relationship or business-line risk ranking is established.',
    }
    return {'tables':{'df_runs':runframe,'df_inputs':inputframe,'df_traces':traceframe},'assumptions':assumptions,'checks':checks,'chain_map':chain_map,'scenarios':specs}

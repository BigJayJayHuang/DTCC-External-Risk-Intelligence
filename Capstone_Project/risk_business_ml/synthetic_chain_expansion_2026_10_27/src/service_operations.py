"""Seven conditional, synthetic service-operation mechanisms.

These are deliberately simplified queue/gate experiments. No timing, capacity,
failure frequency or payment formula is an official DTCC operating parameter.
The supplied v3 chain catalogue supplies the mechanism labels, not calibration.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_CONFIG = {
    'base_orders': 15,
    'horizon_min': 480.0,
    'deadline_min': 300.0,
    'arrival_end_min': 150.0,
    'processing_capacity_per_min': 0.10,
    'mitigation_capacity_per_min': 0.30,
    'settlement_lag_min': 10.0,
    'notional_median_usd_million': 1.0,
    'notional_log_sigma': 0.5,
    'stress_volume_multiplier': 3,
    'severe_volume_multiplier': 4,
    'mmi_baseline_ack_min': 45.0,
    'mmi_repaired_ack_min': 200.0,
    'registration_baseline_min': 35.0,
    'registration_repaired_min': 210.0,
    'restriction_release_min': 180.0,
    'fundserv_baseline_redemption_cash_multiple': 1.2,
    'fundserv_stress_redemption_cash_multiple': 0.55,
    'dtc_link_exposed_share': 0.60,
    'nscc_link_exposed_share': 0.45,
    'dtc_link_outage_start_min': 90.0,
    'dtc_link_stress_outage_end_min': 350.0,
    'dtc_link_repaired_outage_end_min': 220.0,
    'nscc_link_outage_start_min': 65.0,
    'nscc_link_stress_outage_end_min': 370.0,
    'nscc_link_repaired_outage_end_min': 210.0,
    'link_severe_outage_end_min': 650.0,
}

MODEL_LABELS = {
    'mmi_ack': ('MMI融资确认门控', 'MMI funding-acknowledgement gate'),
    'acats_wave': ('ACATS账户转移集中到达', 'ACATS transfer-arrival wave'),
    'fundserv_gross': ('Fund/SERV总订单与赎回资金', 'Fund/SERV gross orders and redemption funding'),
    'registration': ('证券存入登记确认', 'Deposit registration-confirmation gate'),
    'security_restriction': ('证券级存入冻结与全面锁定', 'Security-specific deposit chill / global lock'),
    'dtc_canadian_link': ('DTC加拿大链接依赖', 'DTC Canadian-Link dependency'),
    'nscc_international_link': ('NSCC国际链接依赖', 'NSCC International-Link dependency'),
}


def service_finish(start: float, duration: float,
                   outage: tuple[float, float] | None = None) -> float:
    """Preemptive service suspension; the interval is [start,end)."""
    if not all(math.isfinite(x) for x in (start, duration)) or start < 0 or duration <= 0:
        raise ValueError('Finite nonnegative start and positive duration required')
    if outage is None:
        return start + duration
    a, b = outage
    if not all(math.isfinite(x) for x in (a, b)) or a < 0 or b <= a:
        raise ValueError('Invalid outage interval')
    if start >= b or start + duration <= a:
        return start + duration
    if start < a:
        return b + duration - (a - start)
    return b + duration


def simulate_orders(orders: list[dict[str, Any]], *, capacity_per_min: float,
                    deadline_min: float, horizon_min: float,
                    settlement_lag_min: float = 10.0,
                    outage: tuple[float, float] | None = None,
                    redemption_cash_usd_million: float | None = None
                    ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """FIFO by eligibility within explicitly separate illustrative service lanes.

    Gate=None means an unfulfilled prerequisite, not a lost record. Such an
    instruction consumes no processing capacity. Link-exposed and domestic
    transactions use separate hypothetical lanes, so no unmodelled spillover is
    asserted. Fund/SERV redemption cash is separately prefunded; purchase cash
    is not automatically reused to finance redemptions.
    """
    if not orders or len({o['order_id'] for o in orders}) != len(orders):
        raise ValueError('Require nonempty orders with unique IDs')
    if not all(math.isfinite(v) for v in (capacity_per_min, deadline_min, horizon_min, settlement_lag_min)):
        raise ValueError('Nonfinite configuration')
    if capacity_per_min <= 0 or not 0 <= deadline_min <= horizon_min or settlement_lag_min < 0:
        raise ValueError('Invalid capacity, deadline or horizon')
    if redemption_cash_usd_million is not None and (not math.isfinite(redemption_cash_usd_million) or redemption_cash_usd_million < 0):
        raise ValueError('Redemption cash must be nonnegative and finite')
    prepared = []
    for original in orders:
        o = dict(original)
        arrival = float(o['arrival_min'])
        amount = float(o['notional_usd_million'])
        gate = o.get('gate_time_min', 0.0)
        gate = None if gate is None else float(gate)
        work = float(o.get('work_units', 1.0))
        if (not all(math.isfinite(v) for v in (arrival, amount, work)) or arrival < 0
                or amount < 0 or work <= 0 or (gate is not None and (not math.isfinite(gate) or gate < 0))):
            raise ValueError('Invalid order values')
        eligible = max(arrival, gate) if gate is not None else math.inf
        prepared.append({**o, 'arrival_min': arrival, 'notional_usd_million': amount,
                         'gate_time_min': gate, 'work_units': work,
                         'eligible_min': eligible})
    lane_finish = defaultdict(float)
    events = []
    cash = redemption_cash_usd_million
    for o in sorted(prepared, key=lambda x: (x['eligible_min'], str(x['order_id']))):
        lane = o.get('lane_id', 'service')
        start = max(o['eligible_min'], lane_finish[lane])
        if math.isfinite(start):
            finish = service_finish(start, o['work_units']/capacity_per_min,
                                    outage if o.get('outage_exposed', False) else None)
            lane_finish[lane] = finish
            planned = finish + settlement_lag_min
        else:
            finish = planned = math.inf
        cash_before = cash
        cash_blocked = bool(cash is not None and o.get('operation') == 'redemption'
                            and planned <= horizon_min and o['notional_usd_million'] > cash + 1e-12)
        if cash_blocked:
            planned = math.inf
        complete = planned <= horizon_min
        if complete and cash is not None and o.get('operation') == 'redemption':
            cash -= o['notional_usd_million']
        completed_late = bool(complete and planned > deadline_min)
        # An incomplete instruction is kept distinct from completed-late output.
        # Since horizon>=deadline, every incomplete item is overdue by deadline.
        events.append({
            **o,
            'eligible_min': o['eligible_min'] if math.isfinite(o['eligible_min']) else None,
            'gate_unfulfilled': o['gate_time_min'] is None,
            'processing_start_min': start if start <= horizon_min else None,
            'processing_finish_min': finish if finish <= horizon_min else None,
            'planned_finish_min': planned if math.isfinite(planned) else None,
            'settlement_complete_min': planned if complete else None,
            'completed_within_horizon': complete,
            'completed_late': completed_late,
            'unfinished_at_horizon': not complete,
            'overdue_at_deadline': bool(planned > deadline_min),
            'delay_lower_bound_min': max(0.0, min(planned, horizon_min) - deadline_min),
            'cash_blocked': cash_blocked,
            'redemption_cash_before_usd_million': cash_before,
            'redemption_cash_after_usd_million': cash,
        })
    frame = pd.DataFrame(events).sort_values('order_id').reset_index(drop=True)
    completed = frame.completed_within_horizon
    amounts = frame.notional_usd_million
    purchase = frame.operation.eq('purchase')
    redeem = frame.operation.eq('redemption')
    total = float(amounts.sum())
    summary = {
        'order_count': len(frame),
        'completed_count': int(completed.sum()),
        'completed_late_count': int(frame.completed_late.sum()),
        'unfinished_count': int(frame.unfinished_at_horizon.sum()),
        'overdue_count': int(frame.overdue_at_deadline.sum()),
        'overdue_fraction': float(frame.overdue_at_deadline.mean()),
        'unfinished_fraction': float(frame.unfinished_at_horizon.mean()),
        'gross_instruction_notional_usd_million': total,
        'completed_notional_usd_million': float(amounts[completed].sum()),
        'unfinished_notional_usd_million': float(amounts[~completed].sum()),
        'overdue_notional_usd_million': float(amounts[frame.overdue_at_deadline].sum()),
        'mean_delay_lower_bound_min': float(frame.delay_lower_bound_min.mean()),
        'purchases_usd_million': float(amounts[purchase].sum()),
        'redemptions_usd_million': float(amounts[redeem].sum()),
        'net_fund_flow_usd_million': float(amounts[purchase].sum() - amounts[redeem].sum()),
        'completed_redemptions_usd_million': float(amounts[redeem & completed].sum()),
        'cash_blocked_count': int(frame.cash_blocked.sum()),
        'redemption_cash_initial_usd_million': redemption_cash_usd_million,
        'redemption_cash_end_usd_million': cash,
    }
    return frame, summary


def _chain_map() -> list[dict[str, str]]:
    entries = [
        ('ECS-DTC-01', 'mmi_ack', '假设IPA对发行人简称的融资确认门控，区分到期与发行指令。',
         'Hypothetical IPA funding acknowledgement by acronym, with separate maturity and issuance instructions.',
         '未复制MMI优化、PIF、真实IPA融资确认或付款失败频率；融资确认不是实际结算成功的充分条件。', 'No MMI optimization, PIF, real IPA acknowledgements or calibrated failure frequency; acknowledgement is not sufficient for actual settlement success.'),
        ('ECS-NSCC-08', 'acats_wave', '券商退出引起的假设账户转移集中到达与处理队列。',
         'Hypothetical broker-exit transfer arrivals and processing queue.',
         '未复制ACATS真实时限、全部状态、参与者违约后的撤销、账户资产可转移性及券商映射。', 'No actual ACATS deadlines, full state machine, participant-default reversals, asset transferability or broker mapping.'),
        ('WIS-NSCC-02', 'fundserv_gross', '分别生成申购赎回总订单，模拟处理能力与独立赎回预付资金约束。',
         'Separate purchase/redemption gross orders, processing capacity and independently prefunded redemption cash.',
         '未复制真实基金净值、净额结算、订单规则及基金或分销商映射。', 'No actual NAVs, payment netting, order rules or fund/distributor mappings.'),
        ('AssetSvc-DTC-02', 'registration', '证券存入必须通过假设的登记确认门控。',
         'Deposit instructions require an explicit hypothetical registration confirmation.',
         '未建模真实发行人、过户代理及证券权属裁定。', 'No real issuer, transfer agent or ownership determination.'),
        ('AssetSvc-DTC-01', 'security_restriction', '显式证券级存入冻结仅阻止存入，全面锁定阻止所模拟的存入与划转。',
         'Explicit security-level deposit chill gates deposits; global lock gates modeled deposits and transfers.',
         '不从停牌自动推断DTC锁定，未识别真实锁定决定或原因。', 'No automatic lock inference from a trading halt; no actual restriction decision or reason identified.'),
        ('ECS-DTC-04', 'dtc_canadian_link', '单独生成DTC加拿大链接依赖及跨境指令中断。',
         'Independently generated DTC Canadian-Link dependencies and interrupted cross-border instructions.',
         '未建模真实CDS接口、资金外汇腿或NSCC结果；不会继承NSCC路径。', 'No actual CDS interface, cash/FX legs or inherited NSCC outcomes.'),
        ('ECS-NSCC-12', 'nscc_international_link', '另行生成境外机构链接依赖及NSCC跨境指令中断。',
         'Separately generated foreign-institution link dependencies and interrupted NSCC cross-border instructions.',
         '未复制真实国际链接协议或用DTC结果替代NSCC结果。', 'No actual international-link agreement or substitution of DTC outcomes for NSCC outcomes.'),
    ]
    return [dict(zip(('chain_id','model_id','scope_cn','scope_en','not_modeled_cn','not_modeled_en'), row)) for row in entries]


def _scenarios() -> list[dict[str, Any]]:
    output = []
    roles = [
        ('baseline','基准','Baseline'),
        ('stress','相关冲击','Relevant stress'),
        ('mitigation','修复或额外资源','Repair or additional resources'),
        ('unrelated','不满足传导条件的事件','Event without modeled transmission conditions'),
        ('sensitivity','更强冲击／更广限制','More severe shock / wider restriction'),
    ]
    for model, (cn,en) in MODEL_LABELS.items():
        for role,cnrole,enrole in roles:
            output.append({'scenario_id':f'ops_{model}_{role}', 'model_id':model,
                           'label_cn':f'{cn}：{cnrole}', 'label_en':f'{en}: {enrole}', 'role':role})
    return output


def _fixture(rng: np.random.Generator, count: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    # Fixed identity/order prefixes support common random input pairing even
    # where a volume shock adds orders. These are workload draws, not incidents.
    return [{
        'order_id':f'O{i:04d}',
        'arrival_min':float(rng.uniform(0, config['arrival_end_min'])),
        'notional_usd_million':float(rng.lognormal(math.log(config['notional_median_usd_million']), config['notional_log_sigma'])),
        'security_group':int(rng.integers(0,4)),
        'route_uniform':float(rng.uniform()),
        'operation':'instruction',
        'work_units':1.0,
        'lane_id':'service',
        'outage_exposed':False,
        'gate_time_min':0.0,
    } for i in range(count)]


def _configure(model: str, role: str, raw: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stress = role in ('stress','mitigation','sensitivity')
    base = int(config['base_orders'])
    count = base
    if model in ('acats_wave','fundserv_gross') and stress:
        count *= int(config['severe_volume_multiplier'] if role == 'sensitivity' else config['stress_volume_multiplier'])
    orders = [dict(o) for o in raw[:count]]
    options = {
        'capacity_per_min':float(config['processing_capacity_per_min']),
        'deadline_min':float(config['deadline_min']),
        'horizon_min':float(config['horizon_min']),
        'settlement_lag_min':float(config['settlement_lag_min']),
        'outage':None,
        'redemption_cash_usd_million':None,
    }
    if role == 'mitigation' and model in ('acats_wave','fundserv_gross'):
        options['capacity_per_min'] = float(config['mitigation_capacity_per_min'])
    for i,o in enumerate(orders):
        group = o['security_group']
        if model == 'mmi_ack':
            o['operation'] = 'maturity' if i%2 == 0 else 'issuance'
            o['acronym_id'] = f'MMI_{group}'
            affected = stress and group < (2 if role == 'sensitivity' else 1)
            o['funding_acknowledgement_required'] = True
            o['funding_acknowledgement_received'] = not affected or role == 'mitigation'
            o['gate_time_min'] = (config['mmi_repaired_ack_min'] if role == 'mitigation' else None) if affected else config['mmi_baseline_ack_min']
        elif model == 'acats_wave':
            o['operation'] = 'account_transfer'
            o['transfer_source_broker'] = 'synthetic_exiting_broker' if stress else 'synthetic_ordinary_broker'
        elif model == 'fundserv_gross':
            o['operation'] = 'purchase' if i%2 == 0 else 'redemption'
            o['purchase_cash_independently_prefunded'] = True
        elif model == 'registration':
            o['operation'] = 'deposit'
            affected = stress and group < (2 if role == 'sensitivity' else 1)
            o['registration_required'] = True
            o['gate_time_min'] = (config['registration_repaired_min'] if role == 'mitigation' else None) if affected else config['registration_baseline_min']
        elif model == 'security_restriction':
            o['operation'] = 'deposit' if i%2 == 0 else 'book_entry_transfer'
            # The unrelated control observes a trading halt but has no DTC
            # restriction. A halt by itself cannot switch the authorization.
            o['trading_halt_observed'] = role == 'unrelated' and group == 0
            restriction = ('global_lock' if role == 'sensitivity' else 'deposit_chill') if stress and group == 0 else 'none'
            o['explicit_dtc_restriction'] = restriction
            affected = restriction == 'global_lock' or (restriction == 'deposit_chill' and o['operation'] == 'deposit')
            o['gate_time_min'] = (config['restriction_release_min'] if role == 'mitigation' else None) if affected else 0.0
        elif model in ('dtc_canadian_link','nscc_international_link'):
            prefix = 'dtc' if model == 'dtc_canadian_link' else 'nscc'
            share = config[prefix+'_link_exposed_share']
            exposed = o['route_uniform'] < share
            o['operation'] = 'cross_border_instruction' if exposed else 'domestic_instruction'
            o['link_id'] = 'DTC_CDS_synthetic_link' if prefix == 'dtc' else 'NSCC_foreign_FI_synthetic_link'
            o['actual_dependency_verified'] = False
            o['lane_id'] = 'link_exposed' if exposed else 'domestic'
            o['outage_exposed'] = exposed and stress
    if model == 'fundserv_gross':
        redemption_total = sum(o['notional_usd_million'] for o in orders if o['operation'] == 'redemption')
        multiplier = config['fundserv_stress_redemption_cash_multiple'] if role in ('stress','sensitivity') else config['fundserv_baseline_redemption_cash_multiple']
        options['redemption_cash_usd_million'] = redemption_total * multiplier
    if model in ('dtc_canadian_link','nscc_international_link') and stress:
        prefix = 'dtc' if model == 'dtc_canadian_link' else 'nscc'
        end = config['link_severe_outage_end_min'] if role == 'sensitivity' else config[prefix+'_link_repaired_outage_end_min'] if role == 'mitigation' else config[prefix+'_link_stress_outage_end_min']
        options['outage'] = (float(config[prefix+'_link_outage_start_min']),float(end))
    return orders, options


def run_experiment(seed: int = 20261027, replications: int = 100,
                   config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        unknown = set(config)-set(cfg)
        if unknown:
            raise ValueError('Unknown configuration fields: '+str(unknown))
        cfg.update(config)
    if not isinstance(replications,int) or replications < 1 or not isinstance(cfg['base_orders'],int) or cfg['base_orders'] < 1:
        raise ValueError('Positive integer replications/base_orders required')
    if not (0 <= cfg['dtc_link_exposed_share'] <= 1 and 0 <= cfg['nscc_link_exposed_share'] <= 1):
        raise ValueError('Exposure shares must lie in [0,1]')
    scenarios = _scenarios()
    all_inputs, all_events, runs = [], [], []
    paired = {}
    for model_index,model in enumerate(MODEL_LABELS):
        for replicate in range(replications):
            seed_int = int(np.random.SeedSequence([seed,model_index,replicate]).generate_state(1,dtype=np.uint64)[0])
            raw = _fixture(np.random.default_rng(seed_int), cfg['base_orders']*int(cfg['severe_volume_multiplier']), cfg)
            for spec in [s for s in scenarios if s['model_id'] == model]:
                orders, options = _configure(model,spec['role'],raw,cfg)
                events, summary = simulate_orders(orders,**options)
                identity = {'scenario_id':spec['scenario_id'],'model_id':model,'replicate_id':replicate,'scenario_seed':str(seed_int)}
                inputs = pd.DataFrame(orders).assign(**identity)
                events = events.assign(**identity)
                for key,value in options.items():
                    if key == 'outage':
                        inputs['outage_start_min'] = value[0] if value else None
                        inputs['outage_end_min'] = value[1] if value else None
                    else:
                        inputs['config_'+key] = value
                all_inputs.extend(inputs.to_dict('records'))
                all_events.extend(events.to_dict('records'))
                runs.append({**identity, **summary,
                             'primary_metric':'overdue_fraction',
                             'primary_value':summary['overdue_fraction'],
                             'primary_units':'fraction_of_instructions',
                             'scenario_role':spec['role']})
                paired[(model,replicate,spec['role'])] = summary
    run_frame = pd.DataFrame(runs)
    inputs_frame = pd.DataFrame(all_inputs)
    event_frame = pd.DataFrame(all_events)
    checks = []
    for model in MODEL_LABELS:
        subset = run_frame[run_frame.model_id.eq(model)]
        count_ok = (subset.completed_count + subset.unfinished_count).eq(subset.order_count).all()
        amount_ok = np.allclose(subset.completed_notional_usd_million+subset.unfinished_notional_usd_million,subset.gross_instruction_notional_usd_million,atol=1e-10,rtol=1e-12)
        checks.append({'name':model+':instruction_conservation','passed':bool(count_ok and amount_ok),'detail':'Completed plus unfinished counts/notionals equal generated instructions; no missing instructions.'})
        null_ok = all(paired[(model,r,'baseline')] == paired[(model,r,'unrelated')] for r in range(replications))
        checks.append({'name':model+':unrelated_event_control','passed':bool(null_ok),'detail':'No outcome change when explicit service dependency/restriction/transmission condition is absent.'})
    fund = run_frame[run_frame.model_id.eq('fundserv_gross')]
    cash_residual = fund.redemption_cash_initial_usd_million - fund.completed_redemptions_usd_million - fund.redemption_cash_end_usd_million
    checks.append({'name':'fundserv:cash_conservation','passed':bool(np.allclose(cash_residual,0,atol=1e-10) and (fund.redemption_cash_end_usd_million >= -1e-10).all()),'detail':'Only completed redemptions consume independently prefunded cash; no reuse of purchase flows.'})
    checks.append({'name':'fundserv:gross_vs_net','passed':bool(np.allclose(fund.purchases_usd_million+fund.redemptions_usd_million,fund.gross_instruction_notional_usd_million) and (fund.gross_instruction_notional_usd_million+1e-10 >= fund.net_fund_flow_usd_million.abs()).all()),'detail':'Purchase plus redemption gross notionals determine workload; purchase minus redemption is reported separately.'})
    limits = {
        'simulation_only':True,
        'source_basis':'Supplied expanded_v3 chain registry; mechanism labels only, not calibrated operating rules.',
        'all_numeric_parameters':'Hypothetical; relative simulation minutes are not actual service cutoffs or required completion periods.',
        'workload_randomness':'Paired generated workload draws, not frequencies of broker failures, outages or restrictions.',
        'cash_scope':'Only Fund/SERV redemption cash is explicitly conserved. Other instruction notionals are not cash obligations or losses.',
        'queue_scope':'FIFO by explicit gate eligibility; one synthetic worker per lane, no production optimization, real netting or network spillovers.',
        'censoring':'Completed-late and unfinished-at-horizon are separate. Delay for unfinished items is a lower bound.',
        'exposure_scope':'Dependency/acronym/security mappings are generated fixtures, not identified real participants or services.',
        'no_causality_claim':'No historical validation, calibrated probability, real risk score, p-value or evidence that any actual event reached a service.',
        'mitigation_scope':'MMI acknowledgement/registration repairs restore missing prerequisites; extra processing capacity and redemption cash are hypothetical additional resources, not free real improvements.',
        'configuration':cfg,
    }
    return {'tables':{'ops_runs':run_frame,'ops_inputs':inputs_frame,'ops_events':event_frame},
            'assumptions':limits, 'checks':checks, 'chain_map':_chain_map(), 'scenarios':scenarios}

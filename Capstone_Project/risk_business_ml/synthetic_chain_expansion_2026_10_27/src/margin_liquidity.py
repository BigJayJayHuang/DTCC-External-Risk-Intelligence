"""Hypothetical margin, VM, concentration, liquidity and cross-margin mechanisms.

This is synthetic scenario arithmetic, not a reconstruction of DTCC models or
official margin/SLD formulas. VM is a cash transfer; a required margin stock,
its incremental cash call, and an SLD call are separate quantities throughout.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Sequence

import numpy as np
import pandas as pd


DEFAULT_CONFIG = {
    'members': 12,
    'risk_multiplier': 3.0,
    'market_position_log_sigma': 0.35,
    'market_hedged_residual_fraction': 0.35,
    'market_stress_volatility_multiplier': 2.5,
    'market_sensitivity_volatility_multiplier': 4.0,
    'market_cash_fraction_of_opening_requirement': 0.35,
    'market_services': {
        'gsd': {'delta_median': 0.22, 'delta_units': 'USD million per bp',
                'baseline_move': 1.0, 'stress_move': 35.0, 'move_units': 'bp',
                'unit_sigma': 8.0, 'primary': 'margin_call_usd_million'},
        'mbsd': {'delta_median': 0.30, 'delta_units': 'USD million per bp',
                 'baseline_move': 2.0, 'stress_move': 50.0, 'move_units': 'bp',
                 'unit_sigma': 12.0, 'primary': 'vm_paid_usd_million'},
        'nscc': {'delta_median': 120.0, 'delta_units': 'USD million per unit return',
                 'baseline_move': -0.005, 'stress_move': -0.08,
                 'move_units': 'fractional return', 'unit_sigma': 0.02,
                 'primary': 'vm_paid_usd_million'},
    },
    'concentration_gross_usd_million': 600.0,
    'concentration_dirichlet_shape': 3.0,
    'concentration_base_margin_fraction': 0.04,
    'concentration_top_share_threshold': 0.30,
    'concentration_addon_rate': 0.15,
    'concentration_stress_top_share': 0.65,
    'concentration_mitigated_top_share': 0.30,
    'concentration_sensitivity_threshold': 0.15,
    'concentration_member_capital_usd_million': 100.0,
    'liquidity_families': 6,
    'liquidity_exposure_median_usd_million': 70.0,
    'liquidity_exposure_log_sigma': 0.30,
    'liquidity_resources_fraction_of_largest_family': 1.10,
    'liquidity_member_cash_fraction_of_exposure': 0.18,
    'liquidity_stress_exposure_multiplier': 2.0,
    'liquidity_top_families': 2,
    'liquidity_cash_rescue_multiplier': 5.0,
    'liquidity_resource_sensitivity_multiplier': 0.70,
    'cross_exposure_median_usd_million': 150.0,
    'cross_hedge_ratio': 0.85,
    'cross_sigma_fraction': 0.02,
    'cross_baseline_correlation': 0.95,
    'cross_stress_correlation': 0.0,
    'cross_stress_volatility_multiplier': 2.0,
    'cross_gross_floor_fraction': 0.005,
}


def _finite_nonnegative(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(name + ' must be finite and nonnegative')
    return value


def _member_ids(rows: Sequence[dict]) -> None:
    if not rows or len({r['member_id'] for r in rows}) != len(rows):
        raise ValueError('Nonempty unique member identifiers required')


def market_response(members: Sequence[dict], *, move: float, unit_sigma: float,
                    volatility_multiplier: float = 1.0, residual_fraction: float = 1.0,
                    risk_multiplier: float = 3.0) -> tuple[pd.DataFrame, dict]:
    """One-factor MTM and an assumed absolute-delta margin rule.

    Opening required margin is computed on original positions. A hypothetical
    hedge reduces net delta; it does not retroactively change that opening stock.
    VM receipts can finance the same member's margin cash call. No inter-member
    borrowing, timing network or immediate return of released margin is modeled.
    """
    _member_ids(members)
    if not math.isfinite(float(move)):
        raise ValueError('Market move must be finite')
    sigma = _finite_nonnegative(unit_sigma, 'unit_sigma')
    vol = _finite_nonnegative(volatility_multiplier, 'volatility_multiplier')
    z = _finite_nonnegative(risk_multiplier, 'risk_multiplier')
    residual = _finite_nonnegative(residual_fraction, 'residual_fraction')
    if residual > 1:
        raise ValueError('Residual fraction cannot exceed one')
    traces = []
    for original in members:
        delta = float(original['signed_delta'])
        if not math.isfinite(delta):
            raise ValueError('Signed delta must be finite')
        cash = _finite_nonnegative(original['starting_cash_usd_million'], 'starting_cash')
        new_delta = delta * residual
        pnl = new_delta * float(move)
        paid, received = max(-pnl, 0.0), max(pnl, 0.0)
        opening = abs(delta) * sigma * z
        required = abs(new_delta) * sigma * z * vol
        call, release = max(required-opening, 0.0), max(opening-required, 0.0)
        available, outgo = cash + received, paid + call
        gap, end_cash = max(outgo-available, 0.0), max(available-outgo, 0.0)
        traces.append({**original, 'effective_delta': new_delta,
                       'pnl_usd_million': pnl, 'vm_paid_usd_million': paid,
                       'vm_received_usd_million': received,
                       'opening_required_margin_usd_million': opening,
                       'required_margin_usd_million': required,
                       'margin_call_usd_million': call,
                       'potential_margin_release_usd_million': release,
                       'cash_needed_usd_million': outgo,
                       'funding_gap_usd_million': gap,
                       'ending_cash_usd_million': end_cash,
                       'cash_balance_residual_usd_million': available+gap-outgo-end_cash})
    frame = pd.DataFrame(traces)
    totals = {c: float(frame[c].sum()) for c in [
        'pnl_usd_million', 'vm_paid_usd_million', 'vm_received_usd_million',
        'opening_required_margin_usd_million', 'required_margin_usd_million',
        'margin_call_usd_million', 'potential_margin_release_usd_million',
        'cash_needed_usd_million', 'funding_gap_usd_million', 'ending_cash_usd_million']}
    totals['vm_net_transfer_usd_million'] = totals['vm_paid_usd_million']-totals['vm_received_usd_million']
    totals['margin_stock_residual_usd_million'] = (
        totals['required_margin_usd_million']-totals['opening_required_margin_usd_million']
        -totals['margin_call_usd_million']+totals['potential_margin_release_usd_million'])
    return frame, totals


def concentration_requirement(security_weights: Sequence[float], *,
                              gross_usd_million: float,
                              base_margin_fraction: float = 0.04,
                              threshold: float = 0.30, addon_rate: float = 0.15,
                              member_capital_usd_million: float = 100.0) -> tuple[pd.DataFrame, dict]:
    """Hypothetical top-security-share add-on for one virtual member.

    The threshold/rate are research assumptions, not an NSCC concentration rule.
    A capital ratio is a mechanical diagnostic, not a regulatory capital test.
    """
    w = np.asarray(security_weights, dtype=float)
    if w.ndim != 1 or not len(w) or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        raise ValueError('Finite nonnegative security weights with positive sum required')
    if not math.isfinite(float(threshold)) or not 0 <= threshold <= 1:
        raise ValueError('Threshold must be in [0,1]')
    gross = _finite_nonnegative(gross_usd_million, 'gross')
    base_rate = _finite_nonnegative(base_margin_fraction, 'base_margin_fraction')
    rate = _finite_nonnegative(addon_rate, 'addon_rate')
    capital = _finite_nonnegative(member_capital_usd_million, 'capital')
    if capital == 0:
        raise ValueError('Positive illustrative capital required')
    w = w / w.sum()
    top_share = float(w.max())
    base = gross*base_rate
    addon = max(top_share-threshold, 0.0)*gross*rate
    positions = pd.DataFrame({'security_id': [f'S{i:02}' for i in range(len(w))],
                              'weight': w, 'position_usd_million': w*gross})
    return positions, {'gross_position_usd_million': gross, 'largest_security_share': top_share,
                       'security_hhi': float(np.square(w).sum()),
                       'base_margin_usd_million': base,
                       'concentration_addon_usd_million': addon,
                       'required_margin_usd_million': base+addon,
                       'requirement_to_assumed_capital': (base+addon)/capital,
                       'position_conservation_residual_usd_million': float(positions.position_usd_million.sum()-gross)}


def liquidity_deposits(members: Sequence[dict], *, base_resources_usd_million: float,
                        exposure_multiplier: float = 1.0,
                        top_families: int = 2) -> tuple[pd.DataFrame, dict]:
    """Allocate a hypothetical largest-family coverage gap to top families.

    This is not the actual NSCC Rule 4(A) SLD calculation. Family-level need is
    the maximum aggregated family exposure, not the sum of all market VM. The
    allocation rule is pro rata within the selected families, then members.
    Called deposits and collected cash are explicitly separated.
    """
    _member_ids(members)
    base = _finite_nonnegative(base_resources_usd_million, 'base_resources')
    mult = _finite_nonnegative(exposure_multiplier, 'exposure_multiplier')
    if isinstance(top_families, bool) or int(top_families) != top_families or top_families < 1:
        raise ValueError('Positive integer number of selected families required')
    frame = pd.DataFrame(members).copy()
    for col in ['exposure_usd_million', 'available_cash_usd_million']:
        frame[col] = [_finite_nonnegative(v, col) for v in frame[col]]
    frame['stressed_exposure_usd_million'] = frame.exposure_usd_million*mult
    grouped = frame.groupby('family_id').stressed_exposure_usd_million.sum()
    largest = float(grouped.max())
    called = max(largest-base, 0.0)
    selected = sorted(grouped.index, key=lambda f: (-grouped.loc[f], str(f)))[:int(top_families)]
    total_selected = float(grouped.loc[selected].sum())
    frame['selected_family'] = frame.family_id.isin(selected)
    frame['sld_call_usd_million'] = np.where(
        frame.selected_family & (total_selected > 0),
        called*frame.stressed_exposure_usd_million/max(total_selected, 1e-300), 0.0)
    frame['sld_collected_usd_million'] = np.minimum(frame.sld_call_usd_million, frame.available_cash_usd_million)
    collected = float(frame.sld_collected_usd_million.sum())
    remaining = max(largest-base-collected, 0.0)
    unused = max(base+collected-largest, 0.0)
    return frame, {'largest_family_exposure_usd_million': largest,
                   'base_resources_usd_million': base,
                   'sld_called_usd_million': called,
                   'sld_collected_usd_million': collected,
                   'sld_unfunded_call_usd_million': called-collected,
                   'remaining_liquidity_gap_usd_million': remaining,
                   'unused_resources_usd_million': unused,
                   'call_allocation_residual_usd_million': float(frame.sld_call_usd_million.sum()-called),
                   'resource_balance_residual_usd_million': base+collected+remaining-largest-unused}


def combined_margin(treasury_exposure: float, futures_exposure: float, *,
                    sigma_fraction: float = 0.02, correlation: float = 0.95,
                    volatility_multiplier: float = 1.0,
                    risk_multiplier: float = 3.0,
                    gross_floor_fraction: float = 0.005) -> dict:
    """Two-factor covariance toy model, never an official cross-margin formula.

    Exposures are signed USD million price sensitivities. Positive correlation
    offsets opposite-signed exposures but reinforces same-signed exposures.
    No actual GSD/CME allocation, eligibility or liquidation model is inferred.
    """
    a, b, rho = float(treasury_exposure), float(futures_exposure), float(correlation)
    if not all(math.isfinite(x) for x in [a, b, rho]) or not -1 <= rho <= 1:
        raise ValueError('Finite exposures and correlation in [-1,1] required')
    sigma = _finite_nonnegative(sigma_fraction, 'sigma_fraction')
    vol = _finite_nonnegative(volatility_multiplier, 'volatility_multiplier')
    z = _finite_nonnegative(risk_multiplier, 'risk_multiplier')
    floor_rate = _finite_nonnegative(gross_floor_fraction, 'gross_floor_fraction')
    variance = max(a*a+b*b+2*rho*a*b, 0.0)
    risk = z*sigma*vol*math.sqrt(variance)
    gross = abs(a)+abs(b)
    floor = gross*floor_rate
    standalone = z*sigma*vol*gross
    return {'treasury_exposure_usd_million': a,
            'futures_exposure_usd_million': b,
            'correlation': rho, 'volatility_multiplier': vol,
            'risk_component_usd_million': risk,
            'gross_floor_usd_million': floor,
            'combined_requirement_usd_million': max(risk, floor),
            'sum_standalone_risk_usd_million': standalone,
            'risk_offset_usd_million': standalone-risk}


def scenario_definitions() -> list[dict]:
    out = []
    service_cn = {'gsd': 'GSD国债', 'mbsd': 'MBSD房贷证券', 'nscc': 'NSCC股票'}
    for service in ['gsd', 'mbsd', 'nscc']:
        model = 'ml_market_'+service
        rows = [('baseline', '基准变动', 'Baseline move', 'baseline'),
                ('stress', '价格与波动率冲击', 'Price and volatility shock', 'stress'),
                ('hedged', '假设对冲降低净敞口', 'Assumed hedge reduces net exposure', 'mitigation'),
                ('unrelated', '无关事件对照', 'Unrelated-event control', 'unrelated'),
                ('vol_sensitivity', '更高波动率假设', 'Higher assumed volatility', 'sensitivity')]
        for suffix, cn, en, role in rows:
            out.append({'scenario_id': model+'_'+suffix, 'model_id': model,
                        'label_cn': service_cn[service]+'：'+cn,
                        'label_en': service.upper()+': '+en, 'role': role})
    rows = {
        'ml_concentration': [('baseline','分散头寸','Diversified positions','baseline'),
                             ('stress','单一证券集中','Single-security concentration','stress'),
                             ('diversified','降低集中度','Reduce concentration','mitigation'),
                             ('unrelated','无关事件对照','Unrelated-event control','unrelated'),
                             ('threshold_sensitivity','更低加收门槛','Lower assumed add-on threshold','sensitivity')],
        'ml_sld': [('baseline','基准家族敞口','Baseline family exposures','baseline'),
                   ('stress','最大家族敞口放大','Larger family liquidity exposures','stress'),
                   ('cash_rescue','假设会员增加可用现金','Assumed extra member cash','mitigation'),
                   ('unrelated','无关事件对照','Unrelated-event control','unrelated'),
                   ('resource_sensitivity','更低基础流动性资源','Lower assumed base resources','sensitivity')],
        'ml_cross_margin': [('baseline','对冲账簿基准','Offsetting-book baseline','baseline'),
                            ('stress','相关性破裂与波动放大','Basis dislocation and volatility shock','stress'),
                            ('correlation_rescue','恢复假设对冲相关性','Restore assumed hedge correlation','mitigation'),
                            ('unrelated','无关事件对照','Unrelated-event control','unrelated'),
                            ('wrong_way','同方向敞口敏感性','Same-direction exposure sensitivity','sensitivity'),
                            ('no_offset','无相关性收益敏感性','No-correlation-benefit sensitivity','sensitivity')],
    }
    for model, cases in rows.items():
        for suffix, cn, en, role in cases:
            out.append({'scenario_id': model+'_'+suffix, 'model_id': model,
                        'label_cn': cn, 'label_en': en, 'role': role})
    return out


def chain_mappings() -> list[dict]:
    rows = [
        ('FICC-GSD-01','ml_market_gsd','国债价格变动及波动率假设改变所需保证金。',
         'Assumed Treasury price moves/volatility alter required margin.',
         '未复制VaR、组合净额、真实GSD头寸或保证金通知。',
         'No production VaR/netting, actual GSD portfolio or requirement notices.'),
        ('FICC-MBSD-01','ml_market_mbsd','假设MBS因子变动改变VM现金及所需保证金。',
         'An assumed MBS factor move changes VM cash and required margin.',
         '未分离利率、利差、凸性及真实TBA交易。',
         'No separate rate/spread/convexity model or real TBA trades.'),
        ('ECS-NSCC-01','ml_market_nscc','假设股价变动转为会员VM支付与收款。',
         'Assumed equity moves become member VM payments and receipts.',
         '未模拟实际NSCC结算时序或会员资金网络。',
         'No actual NSCC settlement timing or member funding network.'),
        ('TEAM-ECS-01','ml_market_nscc','假设波动率改变Clearing Fund要求及增量现金需求；与VM分列。',
         'Assumed volatility changes Clearing Fund requirements and incremental cash needs, separate from VM.',
         '未复制NSCC保证金公式或证明真实追加通知。',
         'No production NSCC margin formula or evidence of actual calls.'),
        ('ECS-NSCC-04','ml_concentration','同一会员证券集中度改变假设保证金加收。',
         'Single-member security concentration alters a hypothetical margin add-on.',
         '未验证资本承压、官方阈值、真实会员或实际风控决定。',
         'No observed capital strain, official thresholds, real member or risk decision.'),
        ('ECS-NSCC-05','ml_sld','最大关联家族流动性敞口转为假设补充存款追缴及未覆盖缺口。',
         'Largest affiliated-family liquidity exposure produces illustrative deposit calls and uncovered gaps.',
         '未复制Rule 4(A)公式、动态需求、实际SLD通知及真实资源。',
         'No Rule 4(A) formula, dynamic needs, actual SLD calls or real resources.'),
        ('FICC-GSD-09','ml_cross_margin','国债和期货带符号敞口在假设相关性下改变组合风险及所需金额。',
         'Signed Treasury/futures exposures alter combined risk and requirement under assumed correlation.',
         '未模拟真实项目资格、机构间分配、清盘或GSD官方RFD。',
         'No actual program eligibility, inter-CCP allocation, liquidation or official GSD RFD.'),
    ]
    return [dict(zip(['chain_id','model_id','scope_cn','scope_en','not_modeled_cn','not_modeled_en'], row)) for row in rows]


def _force_top_share(weights: np.ndarray, target: float) -> np.ndarray:
    # Reassign the same total gross position across securities, not new leverage.
    ix = int(np.argmax(weights))
    out = weights.copy()
    other = out.sum()-out[ix]
    out *= (1-target)/other
    out[ix] = target
    return out


def run_experiment(seed: int = 20261027, replications: int = 100,
                   config: dict | None = None) -> dict:
    if isinstance(replications, bool) or int(replications) != replications or replications < 1:
        raise ValueError('Positive integer replications required')
    cfg = deepcopy(DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            cfg[key] = deepcopy(value)
    n = int(cfg['members'])
    if n < 4 or n % 2 or int(cfg['liquidity_families']) < 1 or n % int(cfg['liquidity_families']):
        raise ValueError('An even member count >=4, divisible into liquidity families, is required')
    definitions = scenario_definitions()
    tables = {k: [] for k in ['ml_runs','ml_market_inputs','ml_market_members',
                              'ml_concentration_inputs','ml_concentration_positions',
                              'ml_liquidity_inputs','ml_liquidity_allocations',
                              'ml_cross_inputs','ml_cross_members']}
    meta = {r['scenario_id']: r for r in definitions}

    def identify(sid, rep, paired_seed):
        return {'scenario_id': sid, 'model_id': meta[sid]['model_id'],
                'replicate_id': rep, 'scenario_seed': str(paired_seed)}

    def save(dataset, records, identity):
        tables[dataset].extend([{**identity, **r} for r in records])

    def save_run(identity, outcome, metric):
        tables['ml_runs'].append({**identity, 'primary_metric': metric,
                                 'primary_value': float(outcome[metric]),
                                 'primary_units': 'USD million', **outcome})

    for rep in range(int(replications)):
        for service_index, service in enumerate(['gsd', 'mbsd', 'nscc']):
            paired_seed = int(np.random.SeedSequence([int(seed), 101+service_index, rep]).generate_state(1, dtype=np.uint64)[0])
            rng = np.random.default_rng(paired_seed)
            settings = cfg['market_services'][service]
            magnitudes = rng.lognormal(math.log(settings['delta_median']), cfg['market_position_log_sigma'], n//2)
            # Equal and opposite aggregate exposures make VM cash transfers balance.
            delta = np.concatenate([magnitudes, -magnitudes])
            rng.shuffle(delta)
            members = [{'member_id': f'M{i:02}', 'signed_delta': float(d),
                        'delta_units': settings['delta_units'],
                        'starting_cash_usd_million': abs(float(d))*settings['unit_sigma']*cfg['risk_multiplier']*cfg['market_cash_fraction_of_opening_requirement']}
                       for i, d in enumerate(delta)]
            model = 'ml_market_'+service
            for case in ['baseline','stress','hedged','unrelated','vol_sensitivity']:
                sid = model+'_'+case
                identity = identify(sid, rep, paired_seed)
                stressed = case in ['stress','hedged','vol_sensitivity']
                move = settings['stress_move'] if stressed else settings['baseline_move']
                vol = cfg['market_stress_volatility_multiplier'] if stressed else 1.0
                if case == 'vol_sensitivity':
                    vol = cfg['market_sensitivity_volatility_multiplier']
                residual = cfg['market_hedged_residual_fraction'] if case == 'hedged' else 1.0
                inputs = [{**m, 'move': move, 'move_units': settings['move_units'],
                           'unit_sigma': settings['unit_sigma'], 'volatility_multiplier': vol,
                           'residual_fraction': residual, 'risk_multiplier': cfg['risk_multiplier']} for m in members]
                frame, outcome = market_response(members, move=move, unit_sigma=settings['unit_sigma'],
                                                 volatility_multiplier=vol, residual_fraction=residual,
                                                 risk_multiplier=cfg['risk_multiplier'])
                save('ml_market_inputs', inputs, identity)
                save('ml_market_members', frame.to_dict('records'), identity)
                save_run(identity, outcome, settings['primary'])

        paired_seed = int(np.random.SeedSequence([int(seed), 201, rep]).generate_state(1, dtype=np.uint64)[0])
        rng = np.random.default_rng(paired_seed)
        weights = rng.dirichlet(np.full(n, cfg['concentration_dirichlet_shape']))
        gross = cfg['concentration_gross_usd_million']*float(rng.uniform(0.85, 1.15))
        for case in ['baseline','stress','diversified','unrelated','threshold_sensitivity']:
            sid = 'ml_concentration_'+case
            identity = identify(sid, rep, paired_seed)
            target = cfg['concentration_mitigated_top_share'] if case == 'diversified' else cfg['concentration_stress_top_share']
            use_weights = _force_top_share(weights, target) if case in ['stress','diversified','threshold_sensitivity'] else weights
            threshold = cfg['concentration_sensitivity_threshold'] if case == 'threshold_sensitivity' else cfg['concentration_top_share_threshold']
            inputs = [{'security_id': f'S{i:02}', 'original_weight': float(weights[i]),
                       'weight': float(w), 'gross_usd_million': gross,
                       'base_margin_fraction': cfg['concentration_base_margin_fraction'],
                       'threshold': threshold, 'addon_rate': cfg['concentration_addon_rate'],
                       'member_capital_usd_million': cfg['concentration_member_capital_usd_million']}
                      for i, w in enumerate(use_weights)]
            frame, outcome = concentration_requirement(use_weights, gross_usd_million=gross,
                base_margin_fraction=cfg['concentration_base_margin_fraction'], threshold=threshold,
                addon_rate=cfg['concentration_addon_rate'], member_capital_usd_million=cfg['concentration_member_capital_usd_million'])
            save('ml_concentration_inputs', inputs, identity)
            save('ml_concentration_positions', frame.to_dict('records'), identity)
            save_run(identity, outcome, 'concentration_addon_usd_million')

        paired_seed = int(np.random.SeedSequence([int(seed), 301, rep]).generate_state(1, dtype=np.uint64)[0])
        rng = np.random.default_rng(paired_seed)
        exposure = rng.lognormal(math.log(cfg['liquidity_exposure_median_usd_million']), cfg['liquidity_exposure_log_sigma'], n)
        members = [{'member_id': f'M{i:02}', 'family_id': f'F{i % int(cfg["liquidity_families"]):02}',
                    'exposure_usd_million': float(v),
                    'available_cash_usd_million': float(v)*cfg['liquidity_member_cash_fraction_of_exposure']}
                   for i, v in enumerate(exposure)]
        family_totals = pd.DataFrame(members).groupby('family_id').exposure_usd_million.sum()
        baseline_resources = float(family_totals.max())*cfg['liquidity_resources_fraction_of_largest_family']
        for case in ['baseline','stress','cash_rescue','unrelated','resource_sensitivity']:
            sid = 'ml_sld_'+case
            identity = identify(sid, rep, paired_seed)
            multiplier = cfg['liquidity_stress_exposure_multiplier'] if case in ['stress','cash_rescue','resource_sensitivity'] else 1.0
            resources = baseline_resources*(cfg['liquidity_resource_sensitivity_multiplier'] if case == 'resource_sensitivity' else 1.0)
            use_members = [{**m, 'available_cash_usd_million': m['available_cash_usd_million']*(cfg['liquidity_cash_rescue_multiplier'] if case == 'cash_rescue' else 1.0)} for m in members]
            inputs = [{**m, 'base_resources_usd_million': resources, 'exposure_multiplier': multiplier,
                       'top_families': cfg['liquidity_top_families']} for m in use_members]
            frame, outcome = liquidity_deposits(use_members, base_resources_usd_million=resources,
                exposure_multiplier=multiplier, top_families=cfg['liquidity_top_families'])
            save('ml_liquidity_inputs', inputs, identity)
            save('ml_liquidity_allocations', frame.to_dict('records'), identity)
            save_run(identity, outcome, 'sld_called_usd_million')

        paired_seed = int(np.random.SeedSequence([int(seed), 401, rep]).generate_state(1, dtype=np.uint64)[0])
        rng = np.random.default_rng(paired_seed)
        treasury = rng.lognormal(math.log(cfg['cross_exposure_median_usd_million']), cfg['market_position_log_sigma'], n)
        treasury *= rng.choice([-1.0, 1.0], size=n)
        futures = -treasury*cfg['cross_hedge_ratio']
        for case in ['baseline','stress','correlation_rescue','unrelated','wrong_way','no_offset']:
            sid = 'ml_cross_margin_'+case
            identity = identify(sid, rep, paired_seed)
            rho = cfg['cross_stress_correlation'] if case in ['stress','no_offset'] else cfg['cross_baseline_correlation']
            vol = cfg['cross_stress_volatility_multiplier'] if case in ['stress','correlation_rescue','wrong_way'] else 1.0
            effective_futures = -futures if case == 'wrong_way' else futures
            inputs = [{'member_id': f'M{i:02}', 'treasury_exposure_usd_million': float(a),
                       'futures_exposure_usd_million': float(b),
                       'baseline_futures_exposure_usd_million': float(futures[i]),
                       'sigma_fraction': cfg['cross_sigma_fraction'], 'correlation': rho,
                       'volatility_multiplier': vol, 'risk_multiplier': cfg['risk_multiplier'],
                       'gross_floor_fraction': cfg['cross_gross_floor_fraction']} for i, (a,b) in enumerate(zip(treasury,effective_futures))]
            traces = [{'member_id': item['member_id'], **combined_margin(
                item['treasury_exposure_usd_million'], item['futures_exposure_usd_million'],
                sigma_fraction=item['sigma_fraction'], correlation=rho, volatility_multiplier=vol,
                risk_multiplier=cfg['risk_multiplier'], gross_floor_fraction=cfg['cross_gross_floor_fraction'])} for item in inputs]
            outcome = {k: float(sum(r[k] for r in traces)) for k in [
                'risk_component_usd_million','gross_floor_usd_million',
                'combined_requirement_usd_million','sum_standalone_risk_usd_million','risk_offset_usd_million']}
            save('ml_cross_inputs', inputs, identity)
            save('ml_cross_members', traces, identity)
            save_run(identity, outcome, 'combined_requirement_usd_million')

    frames = {k: pd.DataFrame(v) for k, v in tables.items()}
    runs = frames['ml_runs']
    market = frames['ml_market_members']
    liquidity = frames['ml_liquidity_allocations']
    checks = [
        {'name':'market_vm_cash_conserved', 'passed':bool((runs.loc[runs.model_id.str.startswith('ml_market_'),'vm_net_transfer_usd_million'].abs()<1e-8).all()),
         'detail':'Generated equal/opposite aggregate factor exposures; VM paid equals VM received.'},
        {'name':'market_required_stock_bookkeeping', 'passed':bool((runs.margin_stock_residual_usd_million.dropna().abs()<1e-8).all()),
         'detail':'Required ending stock minus opening stock equals incremental call minus potential release; stock is not VM.'},
        {'name':'market_member_cash_conserved', 'passed':bool((market.cash_balance_residual_usd_million.abs()<1e-8).all()),
         'detail':'Starting cash + VM receipts + shortfall = VM outflow + margin cash requirement + residual cash.'},
        {'name':'concentration_gross_notional_conserved', 'passed':bool((runs.position_conservation_residual_usd_million.dropna().abs()<1e-8).all()),
         'detail':'Changing security shares preserves the same member gross position.'},
        {'name':'sld_calls_allocated_and_resource_balance', 'passed':bool((runs.call_allocation_residual_usd_million.dropna().abs()<1e-8).all() and (runs.resource_balance_residual_usd_million.dropna().abs()<1e-8).all()),
         'detail':'Illustrative called amount is allocated once; collected deposits enter resources once.'},
        {'name':'sld_collected_not_greater_than_call_or_cash', 'passed':bool((liquidity.sld_collected_usd_million<=liquidity.sld_call_usd_million+1e-10).all() and (liquidity.sld_collected_usd_million<=liquidity.available_cash_usd_million+1e-10).all()),
         'detail':'An unfunded call does not become usable liquidity.'},
    ]
    null_ok = True
    for model in runs.model_id.unique():
        base = runs.loc[runs.scenario_id.eq(model+'_baseline')].sort_values('replicate_id').primary_value.to_numpy()
        null = runs.loc[runs.scenario_id.eq(model+'_unrelated')].sort_values('replicate_id').primary_value.to_numpy()
        null_ok = null_ok and np.array_equal(base, null)
    checks.append({'name':'paired_unrelated_controls_identical', 'passed':bool(null_ok),
                   'detail':'An event that does not alter the modeled inputs leaves the primary metric unchanged.'})
    checks.append({'name':'all_scenario_values_finite', 'passed':bool(np.isfinite(runs.primary_value).all()),
                   'detail':'All exported primary values are finite.'})
    assumptions = {
        'evidence_type':'synthetic scenario mechanism exploration only',
        'official_formula_reproduction':False,
        'empirical_validation':False,
        'numeric_parameters':'All member positions, capital, exposures, cash, volatility, rates, thresholds and correlations are hypothetical. No observed loss/default/incident frequencies are generated.',
        'market_formula':'PnL=effective signed delta*factor move; VM pay=max(-PnL,0), receive=max(PnL,0). Opening requirement=abs(original delta)*unit sigma*risk multiplier. Ending required margin=abs(effective delta)*unit sigma*risk multiplier*volatility multiplier. The positive stock increase is an assumed cash call, separate from VM.',
        'market_units':'GSD/MBSD factor delta is USD million per bp; NSCC delta is USD million per fractional return. The MBSD factor combines unspecified rate/spread effects without modeling convexity.',
        'market_cash_timing':'Receipts are available to the same member for a margin call. Potential releases are reported but not immediately recycled. No network timing, settlement failures, inter-member borrowing or production margin model.',
        'concentration_formula':'Base margin=gross*base fraction; assumed add-on=max(largest security share-threshold,0)*gross*add-on rate. Security HHI is descriptive only. Capital denominator is hypothetical and not a regulatory ratio.',
        'sld_formula':'Assumed need=max(aggregated affiliated-family exposures). Called deposit=max(need-base resources,0). Allocate call pro rata to exposures in the top N families and their members. Collected cash=min(call,available member cash); uncollected deposits do not cover need.',
        'sld_boundary':'Toy family allocation, not NSCC Rule 4(A). SLD calls are neither VM cash nor Clearing Fund margin stocks. No actual family membership or calls.',
        'cross_margin_formula':'max(gross exposure floor, z*sigma*vol*sqrt(a^2+b^2+2*rho*a*b)). This is an illustrative covariance model, not actual GSD/CME eligibility, split or Required Fund Deposit.',
        'pairing':'Same seed and original member/security inputs across scenarios within each mechanism and replicate. Different business services use separate synthetic portfolios; results do not rank actual business-line risk.',
        'interpretation':'Stress, mitigation and sensitivity differences follow the declared arithmetic. Monte Carlo spread is assumption-driven path variation, not real-world confidence or causal evidence.',
        'config':cfg,
        'catalog_reference':'new_reference_chain_tests_2026_10_21/inputs/chain_registry_v3.json; exact existing mechanism definitions, not a new finding about current rules.',
    }
    return {'tables':frames, 'assumptions':assumptions, 'checks':checks,
            'chain_map':chain_mappings(), 'scenarios':definitions}

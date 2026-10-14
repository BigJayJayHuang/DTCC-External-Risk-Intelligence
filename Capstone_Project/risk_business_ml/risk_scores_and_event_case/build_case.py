"""Retrospective monitoring overlay; this is not a calibrated risk model."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FEATURES = ['vix_change_pct', 'rate_change_pp', 'credit_change_index', 'funding_basis_max_bps']
LABELS = dict(zip(FEATURES, ['市场波动上升', '利率重新定价', '信用条件收紧', '资金市场利差压力']))
METRICS = ['revenue_growth_pct', 'operating_margin_change_pp', 'net_margin_change_pp']
ENTITIES = ['FICC', 'NSCC', 'DTC']
LATEST, CASE = '2026Q2', '2020Q1'
captured = datetime.now(timezone.utc).isoformat()
risk = pd.read_csv(ROOT / 'data/risk_quarterly.csv').set_index('quarter')
assoc = pd.read_csv(ROOT / 'results/risk_business_associations.csv')
pressure = risk[FEATURES].copy()
for f in FEATURES:
    pressure[f] = pressure[f].abs() if f == 'rate_change_pp' else pressure[f].clip(lower=0)
reference = pressure.loc['2020Q1':'2025Q2']
assert len(reference) == 22 and reference.notna().all().all()
history = pressure.loc['2020Q1':LATEST]
percentile = pd.DataFrame(index=history.index, columns=FEATURES, dtype=float)
for f in FEATURES:
    # Non-positive pressure receives no contribution. Ties count as <=.
    percentile[f] = history[f].map(lambda x: 0.0 if x <= 0 else 100 * np.mean(reference[f] <= x + 1e-12))

weight_rows, weight_map = [], {}
for entity in ENTITIES:
    selected = assoc[(assoc.entity == entity) & assoc.metric.isin(METRICS) & assoc.risk_feature.isin(FEATURES)]
    best = selected.loc[selected.groupby('risk_feature').spearman_rho.apply(lambda x: x.abs().idxmax())].set_index('risk_feature').loc[FEATURES]
    strength = best.spearman_rho.abs()
    weights = strength / strength.sum()
    weight_map[entity] = weights
    for f in FEATURES:
        weight_rows.append({'entity': entity, 'risk_feature': f, 'risk_label_zh': LABELS[f],
                            'selected_business_metric': best.loc[f, 'metric'],
                            'signed_spearman_rho': best.loc[f, 'spearman_rho'],
                            'absolute_spearman_rho': strength[f], 'weight': weights[f],
                            'n_quarters': int(best.loc[f, 'n_quarters']),
                            'association_first_quarter': best.loc[f, 'first_quarter'],
                            'association_last_quarter': best.loc[f, 'last_quarter'],
                            'passes_exploratory_fdr_5pct': bool(best.loc[f, 'passes_exploratory_fdr_5pct'])})
weights_df = pd.DataFrame(weight_rows)
weights_df.to_csv(HERE / 'monitoring_weights.csv', index=False)

detail = []
for q in history.index:
    for f in FEATURES:
        row = {'quarter': q, 'risk_feature': f, 'risk_label_zh': LABELS[f],
               'raw_value': risk.loc[q, f], 'transformed_pressure': pressure.loc[q, f],
               'external_pressure_percentile_0_100': percentile.loc[q, f]}
        for e in ENTITIES:
            row[f'{e}_weight'] = weight_map[e][f]
            row[f'{e}_contribution_points'] = percentile.loc[q, f] * weight_map[e][f]
        detail.append(row)
detail_df = pd.DataFrame(detail)
detail_df.to_csv(HERE / 'risk_driver_scores_history.csv', index=False)
detail_df[detail_df.quarter == LATEST].to_csv(HERE / 'risk_driver_scores_2026Q2.csv', index=False)
detail_df[detail_df.quarter == CASE].to_csv(HERE / 'risk_driver_scores_2020Q1.csv', index=False)
totals = pd.DataFrame(index=history.index)
for e in ENTITIES:
    totals[f'{e}_financial_monitoring_index'] = percentile.mul(weight_map[e]).sum(axis=1)
totals['ECS_related_proxy_index'] = totals[['NSCC_financial_monitoring_index', 'DTC_financial_monitoring_index']].max(axis=1)
totals['ECS_proxy_selected_entity'] = np.where(totals.NSCC_financial_monitoring_index >= totals.DTC_financial_monitoring_index, 'NSCC', 'DTC')
totals['equal_weight_index'] = percentile.mean(axis=1)
totals.to_csv(HERE / 'financial_monitoring_indices_history.csv', index_label='quarter')

families = [
    ('Business Continuity', '业务连续性', 'N/A', '缺少停机、灾备切换、人员可用性等数据'),
    ('Cybersecurity and Information Protection', '网络安全与信息保护', 'N/A', '缺少已核实攻击事件、漏洞暴露和影响标签'),
    ('Information Technology', '信息技术', 'N/A', '缺少系统故障、容量、时延等数据'),
    ('Data Management', '数据管理', 'N/A', '缺少业务数据差错、完整性与时效性指标'),
    ('Processing and Operations', '处理与运营', 'N/A', '缺少可比的差错率、结算失败率和运营事件标签'),
    ('Clearing and Settlement Financial Risks', '清算与结算金融风险', '部分覆盖', '四项外部代理组成金融压力监测指数；无法评分真实敞口或损失'),
    ('Corporate Financial', '公司财务', 'N/A', '财务表现是被解释的业务指标，不能直接当作公司财务风险标签'),
    ('Model', '模型', 'N/A', '模型有效性检查不等于业务模型风险的量化标签'),
    ('Legal and Regulatory Compliance', '法律与监管合规', '仅有活动代理', '监管公告篇数没有相关性、严重度、实施期限或成本标签'),
    ('Third Party Risk', '第三方', 'N/A', '缺少供应商事件及业务依赖数据'),
    ('Human Capital and People', '人员与人力资本', 'N/A', '缺少人员流失、关键岗位与操作失误数据'),
    ('Strategic', '战略', '仅有活动代理', '货币政策公告篇数没有政策方向或业务影响标签'),
]
pd.DataFrame(families, columns=['taxonomy_family', 'label_zh', 'coverage', 'reason']).to_csv(HERE / 'taxonomy_score_coverage.csv', index=False)
policy = []
for f in ['fed_regulatory_announcements', 'fed_monetary_announcements']:
    row = {'risk_feature': f, '2020Q1_count': int(risk.loc[CASE, f]), '2026Q2_count': int(risk.loc[LATEST, f]), 'risk_score': None}
    for e in ENTITIES:
        row[f'{e}_max_absolute_spearman'] = float(assoc[(assoc.entity == e) & (assoc.risk_feature == f) & assoc.metric.isin(METRICS)].spearman_rho.abs().max())
    policy.append(row)
pd.DataFrame(policy).to_csv(HERE / 'policy_activity_context.csv', index=False)

urls = {
    'ficc_event': 'https://www.dtcc.com/insights/2022/making-the-us-treasury-market-safer-for-all-participants',
    'fed_event': 'https://www.federalreserve.gov/publications/2020-november-financial-stability-report-borrowing.htm',
    'nscc_annual': 'https://www.dtcc.com/-/media/Files/Downloads/legal/financials/2020/NSCC-Annual-Financial-Statements-2020-and-2019.pdf',
}
event = {
    'event_id': 'covid-market-stress-2020-03', 'event_name_zh': '2020年3月疫情引发的市场流动性与波动冲击',
    'event_start': '2020-03-01', 'event_end': '2020-03-31', 'scoring_quarter': CASE,
    'event_window_note': '月份表示案例观察范围，不是单一新闻的精确发生日；季度指数包含2020年1至3月。',
    'scoring_is_retrospective': True, 'not_a_2020_point_in_time_prediction': True,
    'financial_monitoring_indices': totals.loc[CASE].to_dict(),
    'trigger_evidence': {'vix_mean_change_pct': float(risk.loc[CASE, 'vix_change_pct']),
                         'ten_year_yield_change_pp': float(risk.loc[CASE, 'rate_change_pp']),
                         'credit_conditions_change_index': float(risk.loc[CASE, 'credit_change_index']),
                         'max_sofr_minus_effr_bps': float(risk.loc[CASE, 'funding_basis_max_bps'])},
    'observed_ficc_activity': {'treasury_daily_clearing_volume_usd_lower_bound': 6e12,
                              'approx_increase_over_usual_daily_average_pct': 43,
                              'source': urls['ficc_event'], 'source_publication_date': '2022-02-22'},
    'observed_outcomes': [
        {'entity': 'FICC', 'scope': 'March 2020 episode described by DTCC',
         'finding': 'Orderly processing and settlement; ceasing to act for a member did not result in adverse market impact or loss allocation to members.', 'source': urls['ficc_event']},
        {'entity': 'NSCC', 'scope': 'Full year 2020 and 2019; guaranteed obligations in Note 15',
         'finding': 'No participant defaults to those guaranteed obligations. This is not a statement that all trades settled without delay.', 'source': urls['nscc_annual'], 'pdf_page': 24},
    ],
    'transmission_chains': {
        'FICC_GSD': ['疫情与现金需求上升', '国债卖出、重新定价及流动性压力', '现金国债与回购清算活动、头寸风险进入GSD', '清算量与担保义务带来容量、保证金与流动性管理压力', '实际维持有序清算结算；不能推断已发生损失'],
        'FICC_MBSD': ['疫情与现金需求上升', '机构MBS价差与波动压力', '会员MBS头寸及保证金管理压力可能进入MBSD', '具体保证金增幅及损失没有本案可核实的月度量化证据'],
        'ECS_NSCC_DTC': ['市场波动及交易变化', '券商未结算股票与ETF头寸变化', 'NSCC担保敞口与风险保证金管理', '会员现金及证券交付需求影响DTC结算环节', '延迟或违约属于条件性风险；本案没有DTC损失或失败率的直接证据'],
    },
    'sources': urls,
}
(HERE / 'event_case_2020_03.json').write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding='utf-8')

pdf = ROOT / 'raw/business_documents/financial_statements/NSCC_Annual_2020_2019.pdf'
reader = PdfReader(pdf)
evidence = {}
for page in [24, 26]:
    evidence[str(page)] = reader.pages[page - 1].extract_text()
(HERE / 'nscc_annual_page_evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
sources = [{'url': url, 'accessed_at_utc': captured, 'access_method': 'official_page_read_with_web_tool'} for url in urls.values()]
sources.append({'path': str(pdf.relative_to(ROOT)), 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'pdf_pages_used': [24, 26], 'access_method': 'existing_download_read_with_pypdf'})
sources.extend([{'url': 'https://www.dtcc.com/-/media/Files/Downloads/legal/policy-and-compliance/' + n,
                 'download_status': 'HTTP 404; excluded from numerical event evidence'}
                for n in ['CPMI-IOSCO-Quantitative-Disclosure-Results-2019-Q4-1.pdf', 'CPMI-IOSCO-Quantitative-Disclosure-Results-2020-Q1-2.pdf']])
(HERE / 'case_sources_manifest.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding='utf-8')

# Verify scoring independently with sorted reference values and searchsorted.
independent = pd.DataFrame(index=history.index)
for f in FEATURES:
    ordered = np.sort(reference[f].to_numpy())
    independent[f] = [0.0 if x <= 0 else 100 * np.searchsorted(ordered, x + 1e-12, side='right') / len(ordered) for x in history[f]]
assert np.allclose(independent[FEATURES], percentile[FEATURES])
assert all(np.isclose(w.sum(), 1.0) for w in weight_map.values())
assert percentile.ge(0).all().all() and percentile.le(100).all().all()
assert totals.filter(like='index').ge(0).all().all() and totals.filter(like='index').le(100 + 1e-10).all().all()
assert np.allclose(totals.ECS_related_proxy_index, np.maximum(totals.NSCC_financial_monitoring_index, totals.DTC_financial_monitoring_index))
assert totals.FICC_financial_monitoring_index.idxmax() == CASE
assert totals.ECS_related_proxy_index.idxmax() == CASE
assert totals.equal_weight_index.idxmax() == CASE
assert not weights_df.passes_exploratory_fdr_5pct.any()

summary = {
    'generated_at_utc': captured, 'business_data_latest_quarter': LATEST,
    'reference_window': ['2020Q1', '2025Q2'], 'reference_quarters': len(reference),
    'monitoring_history_window': ['2020Q1', LATEST], 'history_quarters': len(history),
    'score_name': 'Exploratory financial-pressure monitoring index',
    'score_formula': 'sum_i(100 * empirical_CDF_reference(nonnegative_pressure_i) * normalized_max_abs_Spearman_i), with zero score for nonpositive pressure',
    'weight_selection': 'Maximum absolute Spearman across 3 financial business metrics, normalized over 4 financial proxies separately for each legal entity',
    'weights_use_existing_full_sample_associations': True,
    'not_point_in_time_or_forecast': True, 'calibrated_loss_or_default_probability': False,
    'ECS_proxy_formula': 'max(NSCC legal entity monitoring index, DTC legal entity monitoring index)',
    'ECS_standalone_score_available': False,
    'policy_announcement_counts_excluded_from_financial_score': True,
    'latest_indices': totals.loc[LATEST].to_dict(), 'event_indices': totals.loc[CASE].to_dict(),
    'event_rank_by_FICC_and_ECS_proxy': 1,
    'validation': {'independent_percentile_calculation': 'passed', 'weights_sum_to_one': 'passed',
                   'scores_in_0_100_range': 'passed', 'ECS_max_aggregation': 'passed',
                   'same_highest_period_under_equal_weights': 'passed',
                   'all_weight_associations_fail_exploratory_FDR_5pct': 'confirmed'},
}
(HERE / 'scoring_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'latest': summary['latest_indices'], 'case': summary['event_indices'], 'validation': summary['validation']}, ensure_ascii=False, indent=2))

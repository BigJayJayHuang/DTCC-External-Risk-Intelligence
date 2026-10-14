from pathlib import Path
import json
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
summary = json.loads((HERE / 'scoring_summary.json').read_text())
weights = pd.read_csv(HERE / 'monitoring_weights.csv')
drivers = pd.read_csv(HERE / 'risk_driver_scores_history.csv')
totals = pd.read_csv(HERE / 'financial_monitoring_indices_history.csv').set_index('quarter')
policy = pd.read_csv(HERE / 'policy_activity_context.csv')
coverage = pd.read_csv(HERE / 'taxonomy_score_coverage.csv', keep_default_na=False)
event = json.loads((HERE / 'event_case_2020_03.json').read_text())
urls = event['sources']

def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])

def driver_table(q):
    return table(['外部风险维度', '原始信号', '外部压力分位（0–100）', 'FICC 贡献分', 'NSCC 贡献分', 'DTC 贡献分'],
        [[r.risk_label_zh,
          f'{r.raw_value:+.2f}%' if r.risk_feature == 'vix_change_pct' else
          f'{r.raw_value:+.2f} 个百分点' if r.risk_feature == 'rate_change_pp' else
          f'{r.raw_value:+.6f} 指数点' if r.risk_feature == 'credit_change_index' else f'{r.raw_value:.0f} 基点',
          f'{r.external_pressure_percentile_0_100:.1f}', f'{r.FICC_contribution_points:.1f}',
          f'{r.NSCC_contribution_points:.1f}', f'{r.DTC_contribution_points:.1f}']
         for r in drivers[drivers.quarter == q].itertuples()])

overview = table(['评分口径', '2026Q2', '2020Q1 事件窗口', '解释范围'], [
    ['FICC', f'{totals.loc["2026Q2", "FICC_financial_monitoring_index"]:.1f}', f'{totals.loc["2020Q1", "FICC_financial_monitoring_index"]:.1f}', 'FICC 法律实体的四项外部金融压力监测'],
    ['ECS 相关代理', f'{totals.loc["2026Q2", "ECS_related_proxy_index"]:.1f}', f'{totals.loc["2020Q1", "ECS_related_proxy_index"]:.1f}', '取 NSCC、DTC 两个法律实体监测指数较大者'],
    ['NSCC', f'{totals.loc["2026Q2", "NSCC_financial_monitoring_index"]:.1f}', f'{totals.loc["2020Q1", "NSCC_financial_monitoring_index"]:.1f}', '含 ECS 以外业务，不能视为独立 ECS 财务'],
    ['DTC', f'{totals.loc["2026Q2", "DTC_financial_monitoring_index"]:.1f}', f'{totals.loc["2020Q1", "DTC_financial_monitoring_index"]:.1f}', '含资产服务等 ECS 以外业务'],
])
weight_table = table(['风险维度', 'FICC 权重', 'NSCC 权重', 'DTC 权重'],
    [[label] + [f'{weights[(weights.entity == e) & (weights.risk_feature == f)].weight.iloc[0] * 100:.1f}%' for e in ['FICC','NSCC','DTC']]
     for f, label in drivers[['risk_feature','risk_label_zh']].drop_duplicates().itertuples(index=False, name=None)])
coverage_rows = []
for r in coverage.itertuples():
    ficc = '50.4（部分代理）' if r.taxonomy_family == 'Clearing and Settlement Financial Risks' else 'N/A'
    ecs = '43.4（相关代理）' if r.taxonomy_family == 'Clearing and Settlement Financial Risks' else 'N/A'
    coverage_rows.append([r.label_zh, ficc, ecs, r.reason])
policy_rows = []
for _, r in policy.iterrows():
    policy_rows.append(['监管公告' if r.risk_feature == 'fed_regulatory_announcements' else '货币政策公告',
                        int(r['2026Q2_count']), int(r['2020Q1_count']),
                        f'{r.FICC_max_absolute_spearman:.3f}', f'{r.NSCC_max_absolute_spearman:.3f}',
                        f'{r.DTC_max_absolute_spearman:.3f}', 'N/A：篇数不是风险严重度'])
policy_table = table(['外部活动代理', '2026Q2 篇数', '2020Q1 篇数', 'FICC 最大关联强度', 'NSCC 最大关联强度', 'DTC 最大关联强度', '风险分数'], policy_rows)

chain_rows = [
    ['1. 外部事件', '疫情冲击与现金需求增加，投资者调整或出售资产。', '疫情与市场动荡为已观察事实；具体机构动机不能一概而论。', urls['fed_event']],
    ['2. 市场风险信号', '国债与机构 MBS 市场流动性恶化、重新定价；本地季度 VIX 均值上升 123.26%。', '美联储回顾支持市场失序；季度数值来自已有公开序列。季度变化不等于每一天的方向。', urls['fed_event']],
    ['3A. 进入 FICC/GSD', '会员的现金国债及回购活动进入 GSD 清算；清算规模、头寸风险和管理工作增加。', 'DTCC 确认 2020 年 3 月 FICC 国债日清算量超过 6 万亿美元，约比通常日均高 43%。该数不能解读为净敞口、亏损或整个季度日均。', urls['ficc_event']],
    ['4A. FICC 风险机制', '交易与价格变动影响担保敞口和保证金管理；会员需要准备资金和合格抵押品。若会员无法履约，CCP 需要处理其头寸。', '这是传导机制，不能由 VIX 或资金利差推算某会员具体保证金、违约概率或 FICC 缺口。国债期货保证金不能当作 FICC 现金国债保证金。', urls['ficc_event']],
    ['5A. FICC 实际结果', '高压力进入了清算工作量与风险管理环节，但处理、结算仍保持有序。', 'DTCC 表示，当时停止为一名会员服务，没有造成不利市场影响，也没有向其他会员分摊损失。不能据此宣称所有风险都不存在。', urls['ficc_event']],
    ['3B. 进入 ECS/NSCC', '股票、ETF 等价格与未结算头寸变化，进入 NSCC 的净额清算及交易担保。', '这是 NSCC 业务机制；本案未取得 2020 年 3 月独立 ECS 日度敞口或保证金增量。', urls['nscc_annual']],
    ['4B. ECS 风险机制', 'NSCC 根据未结算组合风险调整保证金；会员的现金、证券交付需求继续进入 DTC 结算环节。', 'NSCC 2020 年报确认日内计算与必要的追加保证金机制。DTC 延迟、失败或损失仅是条件性后果，本案没有直接量化证据。', urls['nscc_annual']],
    ['5B. ECS 可确认结果', '风险管理与抵押品准备是应重点监测的环节，不能写成已经发生会员违约。', 'NSCC 年报说明：2020、2019 年度，对附注 15 所述担保义务没有参与者违约。全年口径不能替代 3 月的结算失败率，也不能扩展成 DTC 零事故。', urls['nscc_annual']],
]
pd.DataFrame(chain_rows, columns=['stage_zh','transmission_zh','evidence_limit_zh','source_url']).to_csv(HERE / 'event_transmission_chain.csv', index=False)
chain_table = table(['传导阶段', '具体发生或可能发生什么', '证据与边界'], [[a,b,c] for a,b,c,_ in chain_rows])

business = pd.read_csv(ROOT / 'data/business_quarterly_financials.csv')
business_rows = [[r.entity, f'{r.revenue_usd / 1e6:.2f}', f'{r.operating_margin_pct:.2f}%']
                 for r in business[(business.quarter == '2020Q1') & business.entity.isin(['FICC','NSCC','DTC'])].sort_values('entity').itertuples()]

report = f'''# FICC 与 ECS 风险监测表及历史事件传导案例

整理日期：2026-10-05。本次已收集的最新业务季度：2026Q2（截至 2026-06-30）。事件案例：2020 年 3 月疫情冲击，对应季度为 2020Q1。

这份结果用于决定“先核查哪些外部风险和哪些业务环节”。现有模型是探索性的关联分析，本次新增的是透明的监测评分规则，**不是模型原先已经训练出的真实风险分数**。

## 1. 业务金融压力监测总表

{overview}

分数范围为 0–100，仅覆盖四项外部金融代理。分数高表示相对于固定历史基准，应优先核查金融压力，**不表示违约概率、预期损失或整个业务的安全程度**。无法凭两者的分差判断 FICC 比 ECS 更危险。

ECS 指 Equity Clearing & Settlement（权益清算与结算），对应 kickoff 的 NSCC 清算与 DTC 结算。公开财务资料没有独立 ECS 分部，所以采用两者指数较大值作为相关业务监测代理。这是本次人为选定的筛查规则，并非 DTCC 标准。2026Q2 的代理取 NSCC；2020Q1 取 DTC。两个法律实体均包含 ECS 以外业务，不能把代理当作 ECS 实际评分，也不能将两者收入相加作为 ECS 收入。

## 2. 各类外部金融信号如何形成分数

以下是 **2026Q2** 的驱动分解。“贡献分”是该信号给相应法律实体总指数增加的点数，不是该类别单独的风险严重度。四项贡献相加得到对应的总指数；显示值四舍五入后可能相差 0.1。

{driver_table('2026Q2')}

例如，FICC 的资金市场利差项为 38.0 分，表示它贡献了本次 50.4 总指数中的 38.0 分。原始信号只是季度最大 SOFR−EFFR 为 8 基点，不能解释为 FICC 已经资金短缺。VIX 变化项为零只表示本季度 VIX 均值没有上升，不能解释为市场没有风险；VIX 水平、组合集中度等未纳入这项评分。信用条件变化很小却有 45.5 历史分位，说明分位只描述排序，不是经济严重度。

两类政策公告继续保留为上下文，暂不写成风险分：

{policy_table}

“最大关联强度”为三个财务变化指标中最大的 Spearman 绝对值；它不表示影响方向。监管公告需要再识别与业务是否相关、规则要求、期限及成本；货币政策公告需要识别宽松或收紧、设施及适用对象。仅凭篇数不能做到这些。

## 3. 项目全部风险类别的覆盖情况

这里按照用户提供的 Cleansed Risk Taxonomy 保留全部 12 个家族；四项金融代理是其中一个家族的外部维度，不能冒充全部风险类别。

{table(['风险家族', 'FICC 当前口径', 'ECS 相关口径', '目前能判断什么／缺什么'], coverage_rows)}

N/A 表示不能依据现有数据量化，不能填成 0。法律监管、战略家族虽有公告活动代理，仍缺少真实风险标签。

## 4. 评分方法与模型证据

1. 风险信号转换：VIX 均值季度增幅、NFCICREDIT 季度均值增量、季度最大 SOFR−EFFR 只取正向值；十年期国债收益率季度末变化取绝对值。收益率上升和下降都可能重新定价；它们对具体头寸的盈亏方向未知。
2. 固定参考分布：2020Q1–2025Q2，共 22 个季度。正压力的“外部压力分位”=100×参考季度中压力不高于当前值的比例；非正压力记 0，平值包含在比例中。参考分布按本地数据当前版本重建，并非当时发布版本。
3. 每个法律实体，分别从收入增速、营业利润率变化、净利润率变化中选取每项代理最大的 Spearman 绝对值，再对四项归一化为权重。
4. 各项贡献分=外部压力分位×该业务权重；业务指数=四项贡献之和。ECS 相关指数=max(NSCC 指数，DTC 指数)。

{weight_table}

权重来自已有全样本描述性关联结果（截至 2026Q2），不是 Ridge 系数，不是因果效应，也不是验证过的风险权重。因此 2020Q1 案例是**事后回看**，不能声称模型在 2020 年已经预警。相关系数采用绝对值，只衡量潜在监测相关性：收入上升也可能伴随工作量和担保压力增加。

现有 78 项关联比较没有一项通过探索性 FDR 5% 检查；13 组业务指标中，仅 5 组在很小的留出样本上优于控制模型。分数尚不能用于正式限额、资本配置或损失预测。最大相关值的选择本身也会放大探索性结果，未来需要独立事件标签、业务敞口和样本外校准。

## 5. 选出的事件：2020 年 3 月疫情市场动荡

2020Q1 是 2020Q1–2026Q2 共 26 个季度中，FICC 和 ECS 相关金融监测指数最高的季度。FICC 为 98.4，ECS 相关代理为 98.4。换成四项等权重后，这一季度仍排第一，等权指数为 97.7。**这是高金融压力筛查窗口，不是已确认损失窗口。**

{driver_table('2020Q1')}

这些是季度汇总，包含 1 月至 3 月，不能当作某一天的风险分数。具体案例观察范围是 2020 年 3 月；quarter-end 利率下降 1.22 个百分点也不意味着月内收益率一直下降。

### 事件传导表

{chain_table}

市场背景参见[美联储 2020 年金融稳定报告的 3 月市场回顾]({urls['fed_event']})；FICC 的量与结算结果参见[DTCC 对 2020 年 3 月的回顾，发布于 2022-02-22]({urls['ficc_event']})；NSCC 的担保、风险管理及年度结果参见[NSCC 2020／2019 年报]({urls['nscc_annual']})，PDF 第 24、26 页。

FICC 的 MBSD 也有与机构 MBS 市场动荡相连的候选链：MBS 价差与波动→会员头寸与抵押品风险→保证金及流动性管理。美联储报告记录了 MBS 市场压力，但本案没有足够证据量化 MBSD 的 3 月保证金增幅或损失，所以不把这条候选链写成已验证的公司损失。

### 同期财务指标，帮助区分压力与业绩

{table(['法律实体', '2020Q1 收入（百万美元）', '2020Q1 营业利润率'], business_rows)}

以上来自已有 business_quarterly_financials.csv 与对应财务原件，描述当季表现，不是疫情造成的净影响。不能把收入上升全部归因于这一个事件；费用、退款、返利、季节性和其他业务都可能影响结果。本案能确认的 FICC 业务结果主要是清算活动量上升及有序结算；ECS 的损失和 DTC 结算失败率仍缺直接数据。

## 6. 后续可以用于事件数据集的字段

event_id、发生时间与观察窗口、报道时间、原始来源、风险家族、外部风险信号、相关业务、暴露环节、机制描述、证据状态、实际业务指标变化、缓解措施、是否发生违约／损失以及缺失原因应分别保存。本例已保存为 event_case_2020_03.json 和 event_transmission_chain.csv。

案例文本和季度分数不是现成的监督学习损失标签。尤其不能将“98.4 分”作为模型真实损失的训练目标，否则只会学会重复本次评分规则。若以后做自动评分，需要人工复核的事件严重度、实际运营结果或敞口标签，并保留发布时间，确保训练时不使用事后信息。

## 7. 来源、计算与交付记录

- 模型依据：results/risk_business_associations.csv、results/analysis_summary.json。
- 风险信号：data/risk_quarterly.csv；[VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)、[DGS10](https://fred.stlouisfed.org/series/DGS10)、[NFCICREDIT](https://fred.stlouisfed.org/series/NFCICREDIT)、[SOFR](https://fred.stlouisfed.org/series/SOFR)、[EFFR](https://fred.stlouisfed.org/series/EFFR) 及 Federal Reserve 官方公告档案。
- 业务及分类范围：kickoff 第 9、10、12 张幻灯片，以及 Cleansed Risk Taxonomy。
- 新增检查：使用排序后计数独立复核历史分位；检查权重和为 1、分数范围、ECS 聚合和等权敏感性。全部通过。
- NSCC 年报原件已经在项目中保存，并提取案例用到的 PDF 第 24、26 页。case_sources_manifest.json 记录来源、访问方式和原件散列。
- 为补充保证金前后对比，尝试访问 2019Q4 和 2020Q1 的旧 PQD 下载地址，均返回 404。因此没有将搜索摘要中的保证金数值加入案例；本次不声称已经下载这两个报告。
- 现有中文／英文模型说明、模型与数据未修改。本次评分及案例独立保存在 risk_scores_and_event_case 文件夹。

本次生成时间（UTC）：{summary['generated_at_utc']}。
'''
(HERE / 'FICC_ECS_风险监测与事件传导说明_CN.md').write_text(report, encoding='utf-8')

receipt = {'schemaVersion': 1, 'items': [
    {'id': 'financial-monitoring-score', 'title': 'FICC 与 ECS 相关业务金融压力监测', 'queries': [
        {'id': 'computed-scores', 'source': {
            'label': '本地公开数据与探索性关联结果',
            'files': ['risk_quarterly.csv','risk_business_associations.csv','scoring_summary.json'],
            'links': ['https://fred.stlouisfed.org/series/VIXCLS','https://fred.stlouisfed.org/series/DGS10','https://fred.stlouisfed.org/series/NFCICREDIT','https://fred.stlouisfed.org/series/SOFR','https://fred.stlouisfed.org/series/EFFR'],
            'metricDefinitions': [
                {'label': '金融压力监测指数', 'definition': '四项历史压力分位按探索性业务关联权重加权，范围为0至100。'},
                {'label': 'ECS相关代理', 'definition': 'NSCC与DTC法律实体金融监测指数较大值。'},
            ],
            'filters': ['参考分布：2020Q1至2025Q2，共22个季度','业务关联：三个财务变化指标的最大Spearman绝对值，按四项金融代理归一化'],
            'caveats': ['分数是新增的事后监测规则，不是校准的违约概率、真实损失或正式风险等级。', 'NSCC和DTC包含ECS以外业务，ECS没有独立分部数据。', '已有78项关联比较均未通过探索性FDR 5%检查；权重使用截至2026Q2的描述性关联。'],
            'executedAt': summary['generated_at_utc'],
            'evidenceFlow': [{'kind':'validation','title':'计算复核','body':'独立排序计数与原分位计算一致，权重和为1，分数在0至100范围，ECS聚合一致；等权评分也将2020Q1列为最高季度。'}],
        }, 'reportingPeriod': '最新业务季度2026Q2；历史事件季度2020Q1',
         'columns': ['季度','FICC监测指数','ECS相关代理指数','NSCC监测指数','DTC监测指数'],
         'rows': [{'季度':q, 'FICC监测指数':round(totals.loc[q,'FICC_financial_monitoring_index'],1),
                   'ECS相关代理指数':round(totals.loc[q,'ECS_related_proxy_index'],1),
                   'NSCC监测指数':round(totals.loc[q,'NSCC_financial_monitoring_index'],1),
                   'DTC监测指数':round(totals.loc[q,'DTC_financial_monitoring_index'],1)} for q in ['2026Q2','2020Q1']],
         'methods': [{'language':'calculation','code':'压力分位=100×参考季度中压力不高于当前值的比例；非正压力分位为0。业务指数=Σ(压力分位×归一化最大绝对Spearman权重)。ECS相关代理=max(NSCC指数,DTC指数)。'}]},
    ]},
    {'id':'march-2020-ficc-event','title':'2020年3月压力进入FICC清算业务', 'queries': [
        {'id':'fed-market-review','source': {'label':'美联储2020年金融稳定报告','links':[urls['fed_event']],
            'caveats':['市场机制回顾不能量化某个FICC会员的敞口或损失。']},
         'summary':'2020年3月国债与机构MBS市场流动性恶化，卖出压力与交易商中介能力受到约束。','reportingPeriod':'2020年3月'},
        {'id':'dtcc-ficc-review','source': {'label':'DTCC对FICC疫情市场波动的回顾','links':[urls['ficc_event']],
            'caveats':['约43%的增幅比较通常日均，不能视为季度均值或净风险敞口。']},
         'summary':'FICC国债日清算量超过6万亿美元，约高于通常日均43%；保持有序处理与结算，停止为一名会员服务没有导致其他会员损失分摊。',
         'reportingPeriod':'2020年3月事件；回顾发表于2022年2月22日'},
    ]},
    {'id':'ecs-transmission-and-evidence-limit','title':'ECS的风险机制与可核实结果','queries': [
        {'id':'nscc-financial-statement','source': {'label':'NSCC 2020与2019年审计年报','links':[urls['nscc_annual']],
             'files':['NSCC_Annual_2020_2019.pdf'],
             'caveats':['全年没有对所述担保义务的参与者违约，不代表所有交易零延迟，也不能推断DTC零事故。','本案没有3月独立ECS保证金、DTC失败率或损失的量化证据。'],
             'evidenceFlow':[{'kind':'source','title':'年报附注15与16','body':'读取本地原件PDF第24页的担保义务及无参与者违约表述，第26页的日内组合计算和追加保证金机制。'}]},
         'summary':'NSCC的交易担保及风险保证金连接市场波动与会员资金准备；2020和2019年对附注15所述担保义务没有参与者违约。',
         'reportingPeriod':'2020与2019年度；3月案例的月度结果存在数据缺口'},
    ]},
]}
(HERE / 'inline_sources.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print('Chinese report and source receipt prepared.')

"""Build a Chinese report and execute the portable analysis notebook."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import nbformat as nbf
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
RESULTS = ROOT / 'results'
REPORT = '十二类风险关联分析_中文说明.md'
NOTEBOOK = 'Twelve_Risk_Families_FICC_ECS.ipynb'

def fmt(v):
    return 'N/A' if pd.isna(v) else f'{v:+.3f}'

def md_table(frame):
    columns = list(frame.columns)
    rows = ['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    rows.extend('| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |' for row in frame.itertuples(index=False, name=None))
    return '\n'.join(rows)

def tables():
    matrix = pd.read_csv(RESULTS / 'twelve_family_revenue_association_matrix.csv')
    definitions = pd.read_csv(DATA / 'expanded_risk_dictionary.csv')
    coverage = pd.read_csv(DATA / 'collection_coverage.csv')
    display = pd.DataFrame({'风险类别': matrix.family_zh})
    source_rows = []
    for row in matrix.itertuples():
        d = definitions[definitions.feature == row.primary_feature].iloc[0]
        c = coverage[(coverage.feature == row.primary_feature) & coverage.entity_scope.isin(['ALL', 'CLEARING', 'FICC'])].iloc[0]
        source_rows.append({'风险类别': row.family_zh, '主指标': d.label_zh,
                            '来源': d.source, '有效风险季度': f'{c.first_quarter}—{c.last_quarter}；{c.quarters}期'})
    for entity, label in [('FICC', 'FICC'), ('NSCC', 'NSCC：ECS清算端'), ('DTC', 'DTC：ECS结算端')]:
        display[label] = [f'{fmt(rho)}（n={int(n)}）' if pd.notna(rho) else 'N/A：缺少适用指标'
                          for rho, n in zip(matrix[entity + '_same_quarter_rho'], matrix[entity + '_same_quarter_n'])]
    display.to_csv(RESULTS / '十二类风险_收入关联汇总.csv', index=False, encoding='utf-8-sig')
    return matrix, definitions, pd.DataFrame(source_rows), display

def manifests():
    original = json.loads((ROOT.parent / 'raw/business_documents/source_manifest.json').read_text())
    pqd = []
    for d in original['documents']:
        destination = ROOT / 'raw/pqd_sources' / Path(d['file']).name
        if destination.exists():
            actual = hashlib.sha256(destination.read_bytes()).hexdigest()
            assert actual == d['sha256']
            pqd.append({'file': str(destination.relative_to(ROOT)), 'sha256': actual,
                        'source_urls': d.get('source_urls', []),
                        'collection_timestamps_utc': d.get('collection_timestamps_utc', []),
                        'reporting_period': d.get('reporting_period')})
    seeds = []
    for name in ['legacy_risk_quarterly.csv', 'legacy_analysis_panel.csv', 'business_quarterly_financials.csv',
                 'business_quarterly_operations.csv', 'business_metric_provenance.csv']:
        path = DATA / name
        seeds.append({'file': 'data/' + name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'role': 'Preserved input from the previous verified local public-data analysis'})
    (ROOT / 'reused_input_manifest.json').write_text(json.dumps({'pqd_workbooks': pqd, 'preserved_inputs': seeds}, ensure_ascii=False, indent=2))
    # Financial PDFs remain in the original project. The package includes their
    # exact public URLs, hashes and disclosure periods alongside the processed input.
    financial = [d for d in original['documents'] if d.get('document_kind') == 'financial_statements']
    (ROOT / 'business_financial_source_manifest.json').write_text(json.dumps({'documents': financial,
        'raw_pdf_location_note': 'Original PDFs are preserved in the parent project; this package carries processed financial inputs and source provenance, not duplicate PDFs.'}, ensure_ascii=False, indent=2))

def report(matrix, definitions, coverage, display):
    summary = json.loads((RESULTS / 'expanded_analysis_summary.json').read_text())
    common = pd.read_csv(RESULTS / 'common_calendar_revenue_associations.csv')
    common_display = pd.DataFrame({'风险类别': common.family_zh})
    for e in ['FICC', 'NSCC', 'DTC']:
        common_display[e + '：相同12季度ρ'] = common[e + '_rho'].map(fmt)
    associations = pd.read_csv(RESULTS / 'expanded_risk_business_associations.csv')
    selected = associations[(associations.metric == 'revenue_growth_pct') &
        (((associations.entity == 'NSCC') & associations.risk_feature.isin(['cloud_infrastructure_incidents', 'cloud_data_service_incidents'])) |
         ((associations.entity == 'DTC') & (associations.risk_feature == 'workspace_provider_incidents')) |
         ((associations.entity == 'FICC') & (associations.risk_feature == 'treasury_bill_yield_volatility')))]
    rows = []
    for r in selected.itertuples():
        rows.append({'业务/指标': r.entity + '/' + r.risk_label_zh, '配对': '同期' if r.lag_quarters == 0 else '风险→下一季度',
                     'n': r.n_quarters, '原始ρ': fmt(r.spearman_rho), '季节/趋势调整ρ': fmt(r.season_trend_adjusted_spearman),
                     '95%分块重抽样区间': f'[{fmt(r.spearman_block_ci_low)}, {fmt(r.spearman_block_ci_high)}]'})
    own = associations[(associations.risk_feature == 'own_liquidity_buffer_pressure') &
                       (associations.metric == 'revenue_growth_pct')]
    own_rows = pd.DataFrame([{'业务': r.entity, '配对': '同期' if r.lag_quarters == 0 else '风险→下一季度',
                             'ρ': fmt(r.spearman_rho), 'n': r.n_quarters} for r in own.itertuples()])
    manifest = json.loads((ROOT / 'source_manifest.json').read_text())
    times = [datetime.fromisoformat(r['fetched_at_utc']) for r in manifest if r.get('status') == 'downloaded']
    collection_local = min(times).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M') + '—' + max(times).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M')
    content = f'''# FICC 与 ECS：十二类风险的公开数据关联分析

本次已为原始分类中的 **12 类风险**建立可量化指标，主指标和补充指标共 **20 种、26 条适用范围序列、572 条季度风险观测**。FICC 和 NSCC 均覆盖 12 类；DTC 覆盖 10 类。这里的“覆盖”表示有公开风险信号或代理变量可做探索，不表示已经取得该类风险的全部真实业务暴露。

新公开来源采集时间：**{collection_local}，美国东部时间**；UTC 时间逐文件保存在来源清单。分析统一截止 **2026Q2**，最早外部数据从 2019Q1 开始，业务有效季度从 2020 年起。较新的原始记录保留在证据文件中，但未混入截至 2026Q2 的分析。

这次是扩大风险数据后的**关联研究**。全部 482 项同期或滞后比较均未通过探索性多重检验 5% 门槛。因此，下表可以用于提出后续验证问题，不能据此判定风险导致损失、给出损失概率或确定业务风险排名。

## 业务口径和“相关性”到底在比较什么

ECS 指 Equity Clearing & Settlement。公开报告没有可直接使用的独立 ECS 财务序列，本次分别使用 **NSCC 法人收入作为清算端代理、DTC 法人收入作为结算端代理**。二者的口径与 ECS 管理业务边界可能不同，不能机械加总，也没有用最大相关系数拼成 ECS 总分。

主表比较：风险主指标的季度值，与该业务**同季度收入环比增长率**的 Spearman 相关系数。收入环比增长率 =（本季度收入 / 上一日历季度收入 − 1）×100%。缺少前一季度收入时，该季度增长率保留缺失。

ρ 的范围是 −1 到 +1。正值表示风险指标高的季度通常也有较高收入增幅；负值表示风险指标高的季度通常收入增幅较低。它并不说明风险本身是好是坏，也不说明收入变化由该风险造成。交易活跃度、利率、费用政策和报告口径等都可能共同影响结果。n 是实际有双方数据的季度数。

## 十二类主指标及采集覆盖

每类先固定一个有公开历史且定义可追溯的主指标，再计算关联；没有按业务结果挑选绝对值最大的系数。其他指标在完整明细中保留。

{md_table(coverage)}

来源与解释边界：

- 业务连续性使用 [OpenFEMA 灾害宣告数据](https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries)，先去除县级重复，再按宣告日期统计重大灾害。另保留排除生物类宣告的敏感性指标。全国宣告数无法识别某一 DTCC 场所受灾或停机。
- 网络安全使用 [CISA 已被利用漏洞目录](https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json)；dateAdded 是列入目录的日期。分析从 2022Q1 起，避开 2021 年目录启动的批量录入。没有 DTCC 软件资产清单，不能认定漏洞影响 DTCC。
- 信息技术、数据管理、第三方分别使用选定云基础设施、云数据服务、办公服务的官方历史服务事件公告。例如 [Compute Engine 历史](https://status.cloud.google.com/products/L3ggmi3Jy4xJmgodFA9K/history)、[Cloud SQL 历史](https://status.cloud.google.com/products/hV87iK5DcEXKgWU2kDri/history)、[Gmail 历史](https://www.google.com/appsstatus/dashboard/products/prPt2Yra2CbGsbEm9cpC/history)。共下载 11 个产品的多年历史页，不用仅覆盖近期的 JSON 倒推以前“没有故障”。同组按事件 ID 去重，IT 与数据组可能共享同一事件，不能相加。**尚未验证 DTCC 使用这些服务，这些只是外部环境代理。** 服务事件可包括中断、性能下降等，公告数量无法区分严重程度与影响范围；公告政策变化也可能改变序列。
- 处理与运营使用 DTCC PQD 17.3.1 过去 12 个月清算核心系统故障数；核心系统不可用比例 17.2.1 作为补充。共享清算系统不是每项业务独立事故数，也不覆盖全部手工处理错误。DTC 没有适用主指标，所以留空。
- 模型风险使用 DTCC PQD 6.5.3 的保证金回测未覆盖比例 = 100% − 覆盖率。FICC 按 GSD、MBSD 的 6.5.2 回测观察数加权汇总，明确为研究计算；各部门原值和单元格证据均保留。该指标是模型表现信号，不是模型设计错误或实际损失标签。DTC 没有对应清算保证金回测指标。
- 清算金融风险主指标是 [SOFR](https://fred.stlouisfed.org/series/SOFR) 与 [EFFR](https://fred.stlouisfed.org/series/EFFR) 的季度最大利差，另有市场波动、长端利率与信用条件变化。它们均是外部市场信号，不等于会员违约或保证金缺口。
- 公司财务的跨业务主指标是 [美联储三个月国债收益率 DGS3MO](https://fred.stlouisfed.org/series/DGS3MO) 的季度日度标准差，原单位为百分点，作为现金再投资环境信号。另从 PQD 15.1.1/15.1.2 提取自有流动净资产与半年运营费用的比值，提供更接近公司自身的补充分析。
- 法律监管使用 [Federal Register 官方接口](https://www.federalregister.gov/reader-aids/developer-resources/rest-api) 中 SEC、CFTC、Federal Reserve 发布的最终规则；它包含行政类和其他金融业务规则。517 条文档与接口总数一致；规则数量只代表变化活动，不是合规违规严重度。
- 人力资本使用美国劳工统计局经 FRED 发布的 [金融保险行业主动离职率 JTU5200QUR](https://fred.stlouisfed.org/series/JTU5200QUR)。它不是 DTCC 员工流失率，原序列未经季调，另做季度季节性调整。
- 战略使用 Baker、Bloom、Davis 编制并经 FRED 发布的 [美国经济政策不确定性 USEPUINDXM](https://fred.stlouisfed.org/series/USEPUINDXM)，补充美联储货币政策公告数。它是战略环境信号，不能替代具体项目失败或竞争指标。

## 同期收入关联：全类别汇总

{md_table(display)}

N/A 是业务适用指标缺失，不是相关性为零。各行的有效时期不同，不能仅凭绝对值大小做跨类别风险排名。

![十二类收入关联](results/figures/twelve_family_revenue_heatmap.png)

## 哪些线索值得继续验证

NSCC 的技术服务事件代理与收入增幅同期 ρ = −0.495（16 个季度），数据服务事件代理为 −0.432（16 个季度）。两者的分块重抽样区间均跨过零；控制季节和趋势后绝对值下降到约 0.21。这意味着负相关是一个线索，但统计支持还不足。

DTC 与办公服务事件公告同期为 +0.597，下一季度则为 −0.391。不能解释成“服务事件让 DTC 更赚钱”。没有供应商关系证据，且不同时间配对的方向不稳定。

FICC 的短期国债收益率波动同期为 +0.381，下一季度为 −0.099。金融压力可能同时伴随交易需求变化；收入上升也不代表结算安全风险下降。

{md_table(pd.DataFrame(rows))}

![同期与下一季度比较](results/figures/same_vs_next_quarter_associations.png)

## 同一组季度复核

为避免“每一类在不同年份比较”误导，另使用所有可用主指标和三项业务收入共有的 12 个季度：{', '.join(summary['common_calendar_quarters'])}。这些季度并不连续，因此结果仍是一个子样本敏感性检查。

{md_table(common_display)}

NSCC 的技术、数据服务代理在共同季度内仍分别为 −0.415、−0.404；FICC 对应系数则由全可用期的正值变成小负值。公司财务主代理与 NSCC 的系数由 −0.059 变为 −0.497。**样本选择明显影响结果，当前不能把相关系数当作稳定的风险传导参数。**

## 补充的公司自身财务信号

半年运营费用 / 自有流动净资产，比值越高表示流动净资产对这项费用尺度的缓冲相对较小。仅使用注释明确为季度末的 2023Q1—2026Q2 记录，共 13 个季度，早期重复的年度值已剔除。这是内生财务状态指标，费用本身也与盈利机械相关，不能用作独立外生冲击。

{md_table(own_rows)}

## 完整分析包括什么

除了主表中的收入，完整明细还比较了 FICC、NSCC、DTC 的运营利润率变化和净利润率变化；以及 FICC/GSD、FICC/MBSD 的日均交易名义额和交易笔数增幅，共 13 条业务序列。482 条结果包含每项指标的同期和下一季度关系，提供 Pearson、Spearman、配对季度数、时期、区间、调整后系数以及解释边界。

分析先补齐完整日历季度，再移动风险一季度，避免跨越缺失期错配。双方缺失均不插值、不前向填充。每项比较至少要求 8 个季度和 3 个不同值；少于 12 个季度的结果视为样本有限。风险 t 与业务 t+1 的关系是回顾性关联，历史数据使用本次采集版本，尚未建立严格的当时可得数据版本，不能宣称具有可用预测效果。

区间采用 2,000 次配对的 4 季度循环分块重抽样；另做季度季节性与线性趋势调整、逐年剔除、剔除 2020 年、指标差分检查。过去 12 个月滚动指标使用隔年差分检查重叠窗口影响。循环平移作为探索性参考，再对 482 项比较做 BH 多重检验修正；所有结果均未达到 5% 门槛。季度样本很少，循环平移参考分辨率低，未通过也不能证明风险没有影响。

![风险信号历史](results/figures/expanded_risk_signal_history.png)

## 当前完成与仍需补充的部分

已完成：12 类公开数据指标、20 种主/补充指标、可复现的 482 项关联研究、共同季度复核、原始证据与单元格来源保存。新增成功下载 23 份公开来源文件，复用 22 份已有 PQD 工作簿。部分故障历史、PQD 季度和财务季度有缺失，均在覆盖表中明确保留。

尚不能完成的结论：每类风险造成多少实际损失、DTCC 使用了事件涉及的哪些服务、哪些软件漏洞确实暴露、真实员工流失的业务影响，以及因果风险分数。这些分别需要供应商/软件资产对应表、事故和影响记录、人员数据、业务暴露及损失或违约标签。没有这些数据时，公开代理的相关性不能替代直接业务证据。

全部主指标、三项业务收入都齐全的共同样本只有 12 个季度，因此没有把全部风险塞进同一个机器学习模型。那样很容易过拟合。当前结果更适合筛选后续数据需求和验证问题。原来的金融风险监测分数保留，**没有重新标为十二类综合风险评分**。

## 文件索引

- `Twelve_Risk_Families_FICC_ECS.ipynb`：已从新内核运行的中文分析 notebook，带完整表格与三张图；HTML 为其导出版本。
- `results/十二类风险_收入关联汇总.csv`：可直接用 Excel 打开的中文主表。
- `results/expanded_risk_business_associations.csv`：482 条完整结果，包括同期/滞后、全部业务指标及稳健性检查。
- `results/common_calendar_revenue_associations.csv`：统一季度的复核结果。
- `data/expanded_risk_dictionary.csv`、`data/collection_coverage.csv`：20 种风险指标的定义、适用范围、覆盖期和限制。
- `data/expanded_risk_observations.csv`、`data/expanded_analysis_panel.csv`：季度风险值与完整配对表，缺失保留为空。
- `source_manifest.json`、`history_products.json`、`reused_input_manifest.json`：下载来源、时间、文件哈希、产品选择及复用记录。
- `data/pqd_risk_cell_evidence.csv`：PQD 文件、工作表、行和列的来源证据。

所有原有中文/英文说明和原有模型文件均保留，本次内容位于新的 `risk_category_expansion` 文件夹。
'''
    (ROOT / REPORT).write_text(content)

def notebook():
    cells = []
    def md(s): cells.append(nbf.v4.new_markdown_cell(s))
    def code(s): cells.append(nbf.v4.new_code_cell(s))
    md('''# 十二类风险与 FICC / ECS 的公开数据关联分析

已收集 12 类风险信号或公开代理，20 种指标。ECS 用 NSCC 清算端、DTC 结算端分别观察。

本 notebook 重新计算所有关联并显示来源覆盖与稳健性检查。分析截止 2026Q2；这不是因果分析、损失预测或校准风险评分。各类别覆盖期不同，未取得完整的 DTCC 供应商、人员、事故或损失标签。

原始来源下载时间（含时区）见 `source_manifest.json`。这次的美国东部采集日期为 2026-10-05，UTC 为 2026-10-06。''')
    code('''from pathlib import Path
import sys, json, io, contextlib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display
ROOT = Path.cwd()
if not (ROOT / 'data/expanded_risk_observations.csv').exists():
    ROOT = ROOT / 'risk_category_expansion'
assert (ROOT / 'data/expanded_risk_observations.csv').exists(), '请在本文件夹运行 notebook'
sys.path.insert(0, str(ROOT / 'src'))
from analyze_expansion import run
from presentation import primary_heatmap, lag_comparison, risk_history
pd.set_option('display.max_colwidth', 80)
pd.set_option('display.max_rows', 40)
definitions = pd.read_csv(ROOT / 'data/expanded_risk_dictionary.csv')
coverage = pd.read_csv(ROOT / 'data/collection_coverage.csv')
observations = pd.read_csv(ROOT / 'data/expanded_risk_observations.csv')
display(pd.DataFrame({'项目': ['风险类别', '不同指标', '含适用范围序列', '季度风险观测'],
                      '数量': [definitions.family.nunique(), definitions.feature.nunique(), len(definitions), len(observations)]}))''')
    md('''## 1. 覆盖情况：先确认数据，再讨论业务

下表包括所有主指标和补充指标。外部公告、行业数据与 DTCC 自身披露区别写在定义表中；同一指标可能有多个适用实体。CISA 的 dateAdded 是目录新增日期，云产品公告不是 DTCC 事故记录。缺失季度不会被填成“没有风险”。''')
    code('''display(coverage[['family', 'label_zh', 'entity_scope', 'first_quarter', 'last_quarter', 'quarters', 'unique_values']].rename(
    columns={'family':'风险类别编码','label_zh':'指标','entity_scope':'适用范围','first_quarter':'首季度','last_quarter':'末季度','quarters':'观测季度数','unique_values':'不同值数量'}))
display(definitions[['label_zh','source','units','entity_scope','measurement_window','interpretation_limit']])''')
    md('''## 2. 重新计算同期和下一季度关联

先建立完整日历季度，再移动一季度；风险与业务缺失都保留空值。至少 8 个配对季度且风险、业务各有 3 个不同值。使用 Spearman / Pearson、2,000 次四季度分块重抽样、季节和趋势调整、逐年剔除及变化敏感性检查。

全部数据是本次采集版本，下一季度关联也只是回顾性分析，不代表当时可得的预测。循环平移及 BH 是小样本的探索性参考，多重检验结果不能用来证明风险不存在。''')
    code('''with contextlib.redirect_stdout(io.StringIO()):
    associations, matrix, summary = run()
display(pd.DataFrame({'项目':['业务指标序列','估计的同期/滞后比较','通过探索性FDR 5%的比较','FICC覆盖类别','NSCC覆盖类别','DTC覆盖类别'],
    '数量':[summary['business_target_series'],len(associations),summary['passing_exploratory_fdr_5pct'],
            summary['FICC_families_with_primary_revenue_association'],summary['NSCC_families_with_primary_revenue_association'],summary['DTC_families_with_primary_revenue_association']]}))''')
    md('''## 3. 十二类风险与收入环比增长的主表

每类主指标在分析脚本中预先指定，不按结果选择最大的系数。ρ > 0 表示两者在季度排序上同向，ρ < 0 表示反向；它不是风险分数。风险与收入同升，不能理解为“风险有利”或“业务更安全”。

ECS 两端保持独立。DTC 的处理/运营、模型风险没有适用的清算主指标，N/A 不等于零。''')
    code('''view = pd.DataFrame({'风险类别':matrix.family_zh})
for entity in ['FICC','NSCC','DTC']:
    view[entity+' 同期ρ'] = matrix[entity+'_same_quarter_rho'].round(3)
    view[entity+' n'] = matrix[entity+'_same_quarter_n']
display(view)
fig = primary_heatmap(matrix)
display(fig); plt.close(fig)''')
    md('''## 4. 下一季度关系与不确定性

服务事件包括中断、性能下降等，数量不能区分严重程度，公告政策也可能变化。NSCC 的技术、数据服务代理同期负相关约为 −0.495、−0.432，但区间跨零，季节/趋势调整后减弱。DTC 的办公服务事件代理同期 +0.597、下一季度 −0.391，方向不稳定。供应商关系尚未验证，不能据此构建具体业务损失链。

下表显示 NSCC 的全部主指标及 95% 重抽样区间。季度数少于 12 时不计算包含五项控制项的季节/趋势调整。重抽样区间也不改变全部比较未通过多重检验的事实。''')
    code('''primary_map = dict(zip(matrix.family,matrix.primary_feature))
primary_rows = associations[(associations.metric=='revenue_growth_pct') &
    (associations.risk_feature==associations.family.map(primary_map))]
display(primary_rows[primary_rows.entity=='NSCC'][['family','lag_quarters','n_quarters','spearman_rho',
    'spearman_block_ci_low','spearman_block_ci_high','season_trend_adjusted_spearman','fdr_q_exploratory']].round(3))
fig = lag_comparison(matrix)
display(fig); plt.close(fig)''')
    md('''## 5. 使用相同的 12 个季度复核

这是所有适用主指标与三个收入序列共同有值的子样本，不是连续时间段。FICC 的技术与数据代理在共同季度内变成小负值，说明样本时期会影响方向。NSCC 的两项系数仍为负，但不能据此主张因果或稳定预测。''')
    code('''common = pd.read_csv(ROOT / 'results/common_calendar_revenue_associations.csv')
print('共同季度：', ', '.join(summary['common_calendar_quarters']))
display(common[['family_zh','FICC_rho','FICC_n','NSCC_rho','NSCC_n','DTC_rho','DTC_n']].round(3))''')
    md('''## 6. 公司自身财务、模型和系统指标

PQD 提供比外部环境更直接的观察，但仍需限制解释：模型回测未覆盖比例是过去 12 个月指标；核心故障为共享清算系统滚动窗口；自有流动净资产与运营费用比值是内生状态。FICC 回测数值是按 GSD/MBSD 观察数加权的研究汇总，不是 DTCC 独立发布的评级。''')
    code('''own = associations[(associations.metric=='revenue_growth_pct') &
    associations.risk_feature.isin(['own_liquidity_buffer_pressure','margin_backtest_uncovered_pct','clearing_core_failures_12m']) &
    associations.entity.isin(['FICC','NSCC'])]
display(own[['entity','risk_label_zh','lag_quarters','n_quarters','spearman_rho','measurement_window','interpretation_limit']].round(3))
checks = pd.read_csv(ROOT/'data/backtest_coverage_reconciliation.csv')
print('回测报告覆盖率与次数推算最大差异（百分点）：',round(checks.difference_pp.abs().max(),6))
fig = risk_history()
display(fig); plt.close(fig)''')
    md('''## 7. 全部业务指标的结果在哪里

共 13 条业务指标：三个法人的收入增长、运营利润率和净利润率变化，以及 GSD / MBSD 的日均交易名义额和交易笔数增幅。完整 482 行保存在 `results/expanded_risk_business_associations.csv`；下面是按业务和指标的比较数量，另给出 NSCC 运营利润率同期主指标结果。

主表不是“所有风险只影响收入”的假设，收入只是便于一致展示的一个结果变量。''')
    code('''display(associations.groupby(['entity','metric','lag_quarters']).size().rename('比较数量').reset_index())
display(associations[(associations.entity=='NSCC') & (associations.metric=='operating_margin_change_pp') &
    (associations.lag_quarters==0) & (associations.risk_feature==associations.family.map(primary_map))]
    [['family','risk_label_zh','n_quarters','spearman_rho','season_trend_adjusted_spearman','fdr_q_exploratory']].round(3))''')
    md('''## 8. 结论及后续数据需求

12 类均有可用于探索的公开信号，FICC、NSCC 覆盖 12 类，DTC 覆盖 10 类。本次不是把所有类别的真实 DTCC 暴露“补齐”；其中多个类别依赖行业或选定服务提供商代理。482 项比较没有一项通过探索性多重检验 5%，样本量与季度粒度也限制识别能力。

下一步应优先取得资产/供应商映射、事故及业务影响记录、人员数据、损失或违约标签。全部主指标的共同样本只有 12 个季度，当前不训练全风险联合预测模型，避免用参数过多的小样本模型制造高拟合效果。原有金融监测分数及中文/英文材料保留，不改称十二类综合风险评分。

来源：[CISA 官方目录](https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json)、[OpenFEMA](https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries)、[Compute Engine 历史](https://status.cloud.google.com/products/L3ggmi3Jy4xJmgodFA9K/history)、[Cloud SQL 历史](https://status.cloud.google.com/products/hV87iK5DcEXKgWU2kDri/history)、[Gmail 历史](https://www.google.com/appsstatus/dashboard/products/prPt2Yra2CbGsbEm9cpC/history)、[BLS 主动离职率 via FRED](https://fred.stlouisfed.org/series/JTU5200QUR)、[政策不确定性 via FRED](https://fred.stlouisfed.org/series/USEPUINDXM)、[美联储三个月国债收益率 via FRED](https://fred.stlouisfed.org/series/DGS3MO)、[Federal Register API](https://www.federalregister.gov/reader-aids/developer-resources/rest-api)。DTCC 原始 PQD 精确链接在 `reused_input_manifest.json`，财务报告链接在 `business_financial_source_manifest.json`，财务指标页码与公式在 `data/business_metric_provenance.csv`。''')
    nb = nbf.v4.new_notebook(cells=cells, metadata={'kernelspec': {'name':'python3','display_name':'Python 3 (Capstone)','language':'python'},
                                                   'language_info':{'name':'python','version':'3.12'}})
    nbf.validate(nb)
    nbf.write(nb, ROOT/NOTEBOOK)
    for key, folder in [('MPLCONFIGDIR','.cache/matplotlib'),('IPYTHONDIR','.cache/ipython'),('JUPYTER_RUNTIME_DIR','.cache/jupyter')]:
        (ROOT/folder).mkdir(parents=True,exist_ok=True)
        os.environ[key] = str(ROOT/folder)
    with tempfile.TemporaryDirectory(prefix='capstone-risk-kernel-') as temporary:
        spec = Path(temporary)/'capstone';spec.mkdir()
        (spec/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],
                                                   'display_name':'Capstone risk analysis','language':'python'}))
        manager = KernelManager(kernel_name='capstone',ip='127.0.0.1',kernel_spec_manager=KernelSpecManager(kernel_dirs=[temporary]))
        client = NotebookClient(nb,km=manager,timeout=180,startup_timeout=30,resources={'metadata':{'path':str(ROOT)}})
        try: client.execute()
        finally:
            if manager.has_kernel: manager.shutdown_kernel(now=True)
    nbf.validate(nb);nbf.write(nb,ROOT/NOTEBOOK)
    html,_ = HTMLExporter(template_name='lab').from_notebook_node(nb)
    (ROOT/NOTEBOOK.replace('.ipynb','.html')).write_text(html)
    print(json.dumps({'executed_code_cells':sum(c.cell_type=='code' for c in nb.cells),
                      'figure_outputs':sum('image/png' in o.get('data',{}) for c in nb.cells if c.cell_type=='code' for o in c.outputs),
                      'errors':sum(o.output_type=='error' for c in nb.cells if c.cell_type=='code' for o in c.outputs)}))

def receipt(matrix, coverage):
    source_definitions = {'label':'公开风险数据与 DTCC 季度指标',
        'files':[{'label':'expanded_risk_dictionary.csv'},{'label':'collection_coverage.csv'},
                 {'label':'expanded_risk_observations.csv'},{'label':'source_manifest.json'},{'label':'reused_input_manifest.json'}],
        'links':[{'label':'CISA 已利用漏洞目录','href':'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'},
                 {'label':'OpenFEMA 灾害宣告','href':'https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries'},
                 {'label':'Cloud SQL 官方事件历史','href':'https://status.cloud.google.com/products/hV87iK5DcEXKgWU2kDri/history'},
                 {'label':'BLS 金融保险业主动离职率 via FRED','href':'https://fred.stlouisfed.org/series/JTU5200QUR'},
                 {'label':'Federal Register 官方接口','href':'https://www.federalregister.gov/reader-aids/developer-resources/rest-api'}],
        'metricDefinitions':[{'label':'风险指标','definition':'风险指标是公开风险信号或代理变量，并非真实 DTCC 损失、违约或事故标签。'},
                             {'label':'类别覆盖','definition':'类别覆盖表示该类别至少有一种可量化、可追溯的历史公开指标。'}],
        'filters':['风险分析截止：2026Q2','按来源有效覆盖期保留季度观测'],
        'caveats':['12 类覆盖不代表全部 DTCC 真实风险暴露已取得。','尚未验证 DTCC 使用选定的云及办公服务提供商。','服务事件公告可包含中断、性能下降等，数量不区分严重程度，公告政策也可能变化。']}
    a = {'id':'risk-coverage','title':'新增风险数据覆盖全部十二类', 'queries':[{'id':'coverage','source':source_definitions,
        'reportingPeriod':'各来源有效风险季度从 2019Q1 / 2020Q1 / 2020Q4 / 2021Q3 / 2022Q1 起，均分析至 2026Q2 内。',
        'columns':list(coverage.columns),'rows':coverage.to_dict(orient='records')}]}
    rows = []
    for r in matrix.itertuples():
        d = {'风险类别':r.family_zh}
        for e in ['FICC','NSCC','DTC']:
            rho = getattr(r,e+'_same_quarter_rho')
            d[e+' ρ'] = round(rho,3) if pd.notna(rho) else None
            d[e+' n'] = int(getattr(r,e+'_same_quarter_n'))
        rows.append(d)
    b = {'id':'revenue-associations','title':'十二类主指标与业务收入增幅的同期关联','queries':[{'id':'primary-revenue-matrix',
        'source':{'label':'风险与业务季度配对结果',
            'files':[{'label':'twelve_family_revenue_association_matrix.csv'},{'label':'expanded_risk_business_associations.csv'},
                     {'label':'business_quarterly_financials.csv'},{'label':'business_metric_provenance.csv'}],
            'metricDefinitions':[{'label':'收入增幅','definition':'收入增幅为本季度收入相对于上一完整日历季度收入的百分比变化。'},
                                 {'label':'Spearman ρ','definition':'Spearman ρ 是配对季度内风险指标与收入增幅排名的相关系数。'},
                                 {'label':'n','definition':'n 是双方指标都有值的实际季度数。'},
                                 {'label':'ECS 代理','definition':'NSCC 与 DTC 分别作为 ECS 的清算端和结算端法人代理，保持独立。'}],
            'filters':['业务指标：收入环比增长率','风险与业务配对：同一日历季度','每类指标：分析前固定的主指标','缺失值：不填充'],
            'caveats':['不同风险类别有效时期不同，不能按系数绝对值排名业务风险。',
                       'DTC 的处理/运营与模型风险缺少适用主指标，N/A 不等于零。',
                       '全部 482 项扩展比较未通过探索性 BH 多重检验 5%，样本少且循环平移参考分辨率低。',
                       '相关性不是因果效应、损失概率或校准风险分数。'],
            'evidenceFlow':[{'kind':'calculation','title':'计算方法','detail':'按完整日历季度对齐，计算排名相关；同时保留滞后一季度、四季度分块重抽样、季节/趋势调整及共同季度复核。'}]},
        'reportingPeriod':'有效业务配对季度从 2020 年起，截止 2026Q2；n 因指标与业务覆盖而异。',
        'columns':list(rows[0]),'rows':rows}]}
    (ROOT/'inline_sources.json').write_text(json.dumps({'schemaVersion':1,'items':[a,b]},ensure_ascii=False,indent=2,allow_nan=False))

def readme():
    (ROOT/'README.md').write_text('''# Twelve risk families: FICC / ECS associations

Start with 十二类风险关联分析_中文说明.md or the executed notebook.

The package contains 20 distinct risk indicators across 12 taxonomy families, 26 scoped series, 572 quarterly observations, and 482 same/next-quarter comparisons against 13 business series. ECS is represented separately by NSCC and DTC. These are exploratory associations, not causal effects or calibrated loss scores. All 482 comparisons fail exploratory BH FDR 5%.

Data cutoff: 2026Q2. New public snapshots were collected on 2026-10-05 America/New_York (2026-10-06 UTC); individual timestamps and hashes are in source_manifest.json. Reused PQD timestamps and hashes are separate. Official provider histories are selected products; DTCC supplier use is unverified. Missing history stays missing. DTC lacks two clearing-specific primary proxies.

To reproduce using the included snapshots in a Python 3.12 environment:

1. Install requirements.txt in your own virtual environment.
2. Run `python src/prepare_expansion.py` to rebuild risk observations from included public snapshots and PQD workbooks.
3. Run `python src/analyze_expansion.py` to rebuild the full association results.
4. Open and run Twelve_Risk_Families_FICC_ECS.ipynb from this directory to rebuild the plots and inspect results.

The original business financial PDFs are not duplicated in this package. Processed financial inputs, exact source URLs, hashes, PDF pages, derivation formulas and reporting periods are included for provenance. Re-extracting those original financial PDFs requires retrieving them from their recorded official public URLs or using the original parent project. The old financial risk seed is preserved, not independently re-collected in this expansion.

Optional source refresh: `python src/collect_sources.py`, then `python src/collect_histories.py`. Network access is required. FRED can intermittently fail; the delivered snapshots include successful retries with initial failures preserved in the manifest. Reconcile download success before rebuilding. A refresh uses current-vintage data and may change prior values.

Do not treat revenue associations as service reliability or realized loss. Further work needs direct asset/vendor exposure mapping, incidents, employee data and actual business-impact labels. Only 12 quarters overlap across all available primary proxies and revenue series; an all-risk joint machine-learning model would have too little data for credible validation.
''')
    (ROOT/'requirements.txt').write_text('''pandas==2.2.3
numpy==2.3.5
scipy==1.18.1
matplotlib==3.11.2
openpyxl==3.1.5
beautifulsoup4
lxml
nbformat
nbclient
nbconvert
ipykernel
''')

if __name__=='__main__':
    matrix,definitions,coverage,display = tables()
    manifests()
    report(matrix,definitions,coverage,display)
    receipt(matrix,coverage)
    readme()
    notebook()

from pathlib import Path
import nbformat as nb

R=Path(__file__).resolve().parents[1]
cells=[]
def md(s):cells.append(nb.v4.new_markdown_cell(s))
def code(s):cells.append(nb.v4.new_code_cell(s))
md('# 十条业务线公开数据更新：质量与复现检查\n\n本快照覆盖 **2026-10-07 至 2026-10-14**。这是数据采集及质量检查，不是新的风险预测或因果检验。原有模型与报告保留。')
md('## Context & Methods\n\n新闻按已知发布时间换算美国东部时间；只有日期的记录保留来源日期和时区缺口。市场观察日、报告期、发布日期及抓取时间分别保存。缺失值不填零，不前向填充。共用数据只保存一个来源，业务关联单独建表。\n\n### Key Assumptions\n\n所有市场历史均为当前抓取版本，不能用于宣称真实历史时点的预测能力。业务关键词映射是候选关系，仍需人工审核。行业基金资产不是 WIS 收入，公开云事件不是 DTCC 事故。')
md('## Data\n\n### 1. 读取固定快照与业务范围')
code("""from pathlib import Path
import json, hashlib, collections
import pandas as pd
import numpy as np
from IPython.display import display
root = Path.cwd()
if not (root/'source_manifest.json').exists():
    root = root/'data_refresh_2026_10_14'
assert (root/'source_manifest.json').exists(), 'Run from the project or snapshot directory'
data=root/'data'
manifest=json.loads((root/'source_manifest.json').read_text())
registry=json.loads((root/'source_registry.json').read_text())
documents=[json.loads(x) for x in (data/'news_increment_2026_10_07_to_14.jsonl').read_text().splitlines()]
market=pd.read_csv(data/'market_observations_updated.csv')
fresh_market=pd.read_csv(data/'market_increment_2026_10_07_to_14.csv')
mapping=pd.read_csv(data/'shared_source_business_mapping.csv')
plan=pd.read_csv(data/'ten_business_data_requirements.csv')
summary=json.loads((root/'processing_summary.json').read_text())
display(pd.DataFrame({'dataset':['本期文档','本期市场非缺失观察','业务线','公开业务规模指标'], 'rows':[len(documents),fresh_market.value.notna().sum(),len(plan),summary['business_snapshot_metrics']]}))
""")
md('### 2. 原始证据、旧输入和唯一下载地址')
code("""assert len(registry)==len({s['id'] for s in registry})==len({s['url'] for s in registry})
verified=0
for source in manifest:
    if source['status'] in ['downloaded','retrieved_via_web']:
        path=root/source['file']
        assert path.is_file(), source['source_id']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'], source['source_id']
        verified+=1
prior_inputs=json.loads((root/'reused_input_manifest.json').read_text())
for item in prior_inputs:
    original=root.parent/item['file']
    input_path=original if original.is_file() else root/item['portable_copy']
    assert hashlib.sha256(input_path.read_bytes()).hexdigest()==item['sha256']
print(f'当前原始证据哈希核对：{verified}；旧输入未变：{len(prior_inputs)}')
""")
md('## Results\n\n### 3. 主键、日期、缺失值与共享关联')
code("""assert len(documents)==len({d['document_id'] for d in documents})==len({d['url'] for d in documents})
assert all('2026-10-07'<=d['publication_date']<='2026-10-14' for d in documents)
assert not any('publication_after_collection' in d['quality_flags'] for d in documents)
assert not market.duplicated(['series_id','observation_date']).any()
assert market.observation_date.max()<='2026-10-14'
assert fresh_market.observation_date.min()>='2026-10-07'
assert not mapping.duplicated(['source_id','business_line']).any()
assert set(mapping.source_id).issubset({s['id'] for s in registry})
assert set(mapping.business_line)==set(plan.business_line)
assert len(plan)==10
news_links=pd.read_csv(data/'news_business_links.csv')
assert set(news_links.document_id).issubset({d['document_id'] for d in documents})
for document in documents:
    actual=set(news_links.loc[news_links.document_id==document['document_id'],'business_line'])
    assert actual==set(document['business_lines_candidate'])
display(news_links[['document_id','business_line']].drop_duplicates().groupby('business_line').size().rename('候选文档数').to_frame())
print('候选文档可关联多个业务，业务列合计不能当作独立事件数。')
""")
md('### 4. 独立核对资金利差及历史门槛')
code("""wide=market.pivot(index='observation_date',columns='series_id',values='value')
funding=((wide.SOFR-wide.EFFR)*100).dropna()
signals=pd.read_csv(data/'daily_market_signals_increment.csv')
raw_funding=signals[signals.indicator=='sofr_effr']
for row in raw_funding.itertuples():
    assert abs(row.value-funding.loc[row.date])<1e-9
    past=funding.loc[funding.index<row.date].tail(252)
    assert len(past)>=126
    assert abs(row.threshold_past90-np.quantile(past,.90))<1e-9
assert abs(funding.loc['2019-09-17']-295.0)<1e-8
display(raw_funding[['date','value','unit','threshold_past90','alarm']])
print('阈值排除当天，但当前版本历史数据仍不等于历史时点可用版本。')
""")
md('### 5. 业务数据的粒度、报告期和非加总范围')
code("""underwriting=pd.read_csv(data/'asset_services_underwriting_monthly.csv')
assert not underwriting.duplicated(['reporting_month','security_category']).any()
ficc_monthly=pd.read_csv(data/'ficc_gsd_mbsd_monthly_volumes.csv')
assert not ficc_monthly.duplicated(['division','reporting_month','metric_code']).any()
assert set(ficc_monthly.division)=={'GSD','MBSD'}
assert ficc_monthly.source_file.nunique()==1
trailer_checks=pd.read_csv(data/'ficc_daily_file_reconciliation.csv')
assert (trailer_checks.data_rows==trailer_checks.trailer_expected_rows).all()
industry=pd.read_csv(data/'wis_industry_money_market_assets.csv')
assert not industry.duplicated(['fund_category','investor_type','observation_date']).any()
total=industry[(industry.fund_category=='All')&(industry.investor_type=='Total')&(industry.observation_date=='2026-10-07')].iloc[0]
assert total.assets_billion_usd==7963.55
assert abs((7963.55-7891.27)-72.27)<=.02
operations=pd.read_csv(data/'ecs_itp_monthly_operations_snapshot.csv')
assert not operations.duplicated(['business_line','metric_label','reporting_period','region']).any()
display(pd.DataFrame({'数据':['承销月度','GSD/MBSD 月度','ECS/ITP 快照','RDS 周报','WIS 行业资产'], '最新报告期':[underwriting.reporting_month.max(),ficc_monthly.reporting_month.max(),operations.reporting_period.max(),'2026-10-09',industry.observation_date.max()]}))
print('RDS 各地区/表格与基金分类的总计、子项分别保存，不将重叠行简单加总。')
""")
md('### 6. 来源缺口与文档内容可用性')
code("""coverage=pd.read_csv(data/'market_series_coverage.csv')
display(coverage[['series_id','frequency','latest_current_observation','availability_status','window_nonmissing_rows']])
retired=coverage[coverage.series_id.isin(['WRMFSL','WIMFSL'])]
assert (retired.availability_status=='discontinued_history_only').all()
assert (retired.window_nonmissing_rows==0).all()
content_counts=collections.Counter(d['original_content_status'] for d in documents)
display(pd.DataFrame(sorted(content_counts.items()),columns=['原文状态','文档数']))
regulator=json.loads((root/next(s['file'] for s in manifest if s['source_id']=='federal_register')).read_text())
assert regulator['count']==len(regulator['results'])==66
assert not regulator.get('next_page_url')
assert len({x['document_number'] for x in regulator['results']})==66
assert all('2026-10-07'<=x['publication_date']<='2026-10-14' for x in regulator['results'])
print('Federal Register API 元数据完整取得；原文访问提示页面不作为新闻正文。')
""")
md('### 7. 保存核查结果')
code("""validation={'passed':True,'scope':'fixed public snapshot and data integrity; no predictive or causal validation',
    'window_documents':len(documents),'market_nonmissing_increment':int(fresh_market.value.notna().sum()),
    'business_lines':len(plan),'verified_current_raw_files':verified,'verified_unchanged_prior_inputs':len(prior_inputs),
    'news_content_counts':dict(content_counts),'all_regulatory_api_rows':regulator['count'],
    'checks':['unique source IDs and exact URLs','raw and prior input hashes','news and market primary keys',
              'requested publication/observation windows','no future publication timestamps',
              'business relationship referential integrity','funding basis and past-only thresholds',
              'underwriting and FICC monthly grains','shared GSD/MBSD source file','daily trailer counts',
              'industry table rounding and nonadditive hierarchy','discontinued-series flags','Federal Register API pagination/count'],
    'models_retrained':False,'business_risk_scores_generated':False}
(root/'validation_results.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
display(pd.DataFrame({'检查':['数据主键、证据、日期与关联','预测能力或因果影响'], '结果':['通过本 Notebook 的检查','本轮未重新检验']}))
""")
md('## Takeaways\n\n十条业务线已有不同的公开输入和清楚的内部数据缺口。采集文件、当前报告期、候选业务映射和旧输入核对均可检查。部分来源只取得元数据，两个旧货币基金周度序列已经停更。此快照能供后续业务监测和研究使用，尚不能据此给十条业务线生成可靠风险分数。')
n=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}})
nb.write(n,R/'Public_Data_Refresh_Quality_Checks_CN.ipynb')
print('Wrote quality notebook:',len([c for c in cells if c.cell_type=='code']),'code cells')

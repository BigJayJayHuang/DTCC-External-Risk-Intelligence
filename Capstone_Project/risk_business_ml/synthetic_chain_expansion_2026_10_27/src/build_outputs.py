"""Bilingual coverage ledger and scenario figures from saved synthetic outputs."""
from pathlib import Path
import csv,json,math,os,textwrap
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.qa/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def read(name):return pd.read_csv(ROOT/'data'/f'{name}.csv',dtype={'scenario_seed':'string'},float_precision='round_trip')
def dump(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def esc(value):return str(value).replace('|',' / ').replace('\n',' ')
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(esc(v) for v in r)+' |' for r in rows])
def role_class(role):
    role=str(role).lower()
    return 'stress' if role in ['shock','stress'] else role

def format_value(v,u):
    if 'fraction' in u.lower() or u.lower()=='ratio':return f'{v*100:.2f}%'
    return f'{v:,.2f}'

def main():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    scenarios=pd.DataFrame(json.loads((ROOT/'results/scenario_definitions.json').read_text()))
    maps=json.loads((ROOT/'results/chain_model_map.json').read_text())
    rows=[]
    for dataset in receipt['tables']:
        if not dataset.endswith('_runs'):continue
        frame=read(dataset)
        for scenario,g in frame.groupby('scenario_id',sort=False):
            spec=scenarios[scenarios.scenario_id.eq(scenario)].iloc[0]
            assert g.primary_metric.nunique()==g.primary_units.nunique()==1
            x=g.primary_value
            rows.append({'model_id':spec.model_id,'scenario_id':scenario,'label_cn':spec.label_cn,'label_en':spec.label_en,
                         'role':spec.role,'engine':spec.engine,'metric':g.primary_metric.iloc[0],'units':g.primary_units.iloc[0],
                         'replications':len(g),'mean':x.mean(),'p05':x.quantile(.05),'p95':x.quantile(.95),
                         'simulation_id':receipt['simulation_id'],'source_type':'synthetic','empirical_validation':False,
                         'interval_meaning':'5th–95th path percentiles; not empirical confidence intervals or real-world probabilities'})
    summary=pd.DataFrame(rows)
    summary.to_csv(ROOT/'results/scenario_summary.csv',index=False,float_format='%.17g')
    checks=[]
    for model,g in summary.groupby('model_id',sort=False):
        baseline=g[g.role.map(role_class).eq('baseline')].iloc[0]
        stress=g[g.role.map(role_class).eq('stress')].iloc[0]
        mitigation=g[g.role.map(role_class).eq('mitigation')].iloc[0]
        ids=sorted({r['chain_id'] for r in maps if r['model_id']==model})
        checks.append({'model_id':model,'chain_ids':'; '.join(ids),'metric':stress.metric,'units':stress.units,
                       'baseline_scenario':baseline.scenario_id,'baseline_mean':baseline['mean'],
                       'stress_scenario':stress.scenario_id,'stress_mean':stress['mean'],
                       'mitigation_scenario':mitigation.scenario_id,'mitigation_mean':mitigation['mean'],
                       'delta_stress_minus_baseline':stress['mean']-baseline['mean'],
                       'delta_mitigation_minus_stress':mitigation['mean']-stress['mean'],
                       'source_type':'synthetic','interpretation':'Conditional assumptions; values are not cross-business comparable risk scores'})
    comparisons=pd.DataFrame(checks)
    comparisons.to_csv(ROOT/'results/model_comparisons.csv',index=False,float_format='%.17g')
    coverage=build_coverage(maps,receipt)
    draw(summary)
    write_notes(receipt,summary,comparisons,coverage,maps)
    print(f'Built {len(summary)} scenario summaries, {len(comparisons)} model comparisons and {len(coverage)} catalog rows')

def build_coverage(maps,receipt):
    catalog=json.loads((ROOT/'inputs/chain_registry_v3.json').read_text())
    v1=pd.read_csv(ROOT/'inputs/v1_chain_simulation_status.csv').set_index('chain_id')
    prior=pd.read_csv(ROOT/'inputs/original_new_chain_status_EN.csv').set_index('chain_id')
    prior_cn=pd.read_csv(ROOT/'inputs/original_new_chain_status_CN.csv',encoding='utf-8-sig').set_index('chain_id')
    output=[]
    for chain in catalog['chains']:
        cid=chain['chain_id'];new=[r for r in maps if r['chain_id']==cid]
        if new:
            stage='conditional_mechanism_simulated_v2';cn='本轮：部分机制情景已模拟';en='New: conditional mechanism simulated'
            scopes_cn='；'.join(r['scope_cn'] for r in new);scopes_en='; '.join(r['scope_en'] for r in new)
            omissions_cn='；'.join(r['not_modeled_cn'] for r in new);omissions_en='; '.join(r['not_modeled_en'] for r in new)
            batch=receipt['simulation_id'];model='; '.join(sorted({r['model_id'] for r in new}))
        elif cid in v1.index:
            generic=v1.loc[cid,'simulation_status']=='generic_outage_scenario_only'
            stage='generic_context_only_v1' if generic else 'conditional_mechanism_simulated_v1'
            cn='前轮：仅通用故障背景' if generic else '前轮：部分机制情景已模拟'
            en='Earlier: generic outage context only' if generic else 'Earlier: conditional mechanism simulated'
            scopes_cn='通用通知处理及交割队列' if cid!='FICC-MBSD-06' and cid!='ECS-DTC-06' else '头寸滚动守恒' if cid=='FICC-MBSD-06' else '额度、抵押品准入及资金队列'
            scopes_en='Generic notification/delivery queue' if cid not in ['FICC-MBSD-06','ECS-DTC-06'] else 'Stock-flow conservation' if cid=='FICC-MBSD-06' else 'Debit/collateral admission and funding queue'
            omissions_cn='仍缺真实会员、事故、时点及业务结果；不代表完整链或真实攻击得到验证。'
            omissions_en='Actual members, incidents, timing and service outcomes remain missing; not a complete chain or identified cyberattack.'
            batch=v1.loc[cid,'simulation_id'];model=v1.loc[cid,'model_id']
        else:
            stage='not_simulated';cn='尚未建立专属模拟';en='No dedicated simulation yet'
            scopes_cn='无';scopes_en='None';batch='';model=''
            omissions_cn='本轮未定义该链的专属状态、决策及业务结果模型；通用队列或随机标签不能代替。'
            omissions_en='No chain-specific state/decision/outcome model in this batch; a generic queue or random labels are not a substitute.'
        missing=str(prior.loc[cid,'missing_data']) if cid in prior.index else 'See original business workstream; not reclassified or inherited in this batch.'
        original=str(prior.loc[cid,'work_status']) if cid in prior.index else 'Outside the31-added-chain empirical table; unchanged'
        missing_cn=str(prior_cn.loc[cid,'missing_data']) if cid in prior_cn.index else '参见原业务检验材料；本轮未重分类或继承其他目录的结果。'
        original_cn=str(prior_cn.loc[cid,'work_status']) if cid in prior_cn.index else '不属于31条新增链的实证表；原状态未改变。'
        output.append({'catalog_version':'expanded_v3','chain_id':cid,'status_code':stage,'status_cn':cn,'status_en':en,
                       'event_cn':chain['world_event']['CN'],'event_en':chain['world_event']['EN'],
                       'mechanism_cn':chain['mechanism']['CN'],'mechanism_en':chain['mechanism']['EN'],
                       'process_cn':chain['dtcc_process']['CN'],'process_en':chain['dtcc_process']['EN'],
                       'model_id':model,'simulation_id':batch,'modeled_scope_cn':scopes_cn,'modeled_scope_en':scopes_en,
                       'not_modeled_cn':omissions_cn,'not_modeled_en':omissions_en,'original_empirical_status':original,
                       'real_data_still_needed':missing,'original_empirical_status_cn':original_cn,'real_data_still_needed_cn':missing_cn,
                       'full_chain_validated':False,'real_world_probability_calibrated':False})
    frame=pd.DataFrame(output);frame.to_csv(ROOT/'results/chain_coverage_bilingual.csv',index=False)
    for language in ['CN','EN']:
        lang=language.lower()
        original_col='original_empirical_status_cn' if language=='CN' else 'original_empirical_status'
        missing_col='real_data_still_needed_cn' if language=='CN' else 'real_data_still_needed'
        columns=['catalog_version','chain_id','status_'+lang,'process_'+lang,'model_id','simulation_id','modeled_scope_'+lang,'not_modeled_'+lang,original_col,missing_col,'full_chain_validated','real_world_probability_calibrated']
        frame[columns].to_csv(ROOT/'results'/f'chain_coverage_{language}.csv',index=False)
        headers=['链编号','模拟状态','业务流程','模型','尚未包含'] if language=='CN' else ['Chain ID','Simulation status','Business process','Model','Not modeled']
        body=[[r['chain_id'],r['status_'+lang],r['process_'+lang],r['model_id'],r['not_modeled_'+lang]] for r in output]
        prefix='# 56条链的情景模拟覆盖清单\n\n情景覆盖不是实证验证。原始实证状态未改；本表不继承其他目录中复用编号的结果。\n\n' if language=='CN' else '# Scenario coverage across56 catalog chains\n\nScenario coverage is not empirical validation. Original empirical statuses remain unchanged; reused IDs in other catalogs do not inherit results.\n\n'
        (ROOT/f'CHAIN_COVERAGE_{language}.md').write_text(prefix+table(headers,body)+'\n')
    return frame

def draw(summary):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    titles={'ml_market_gsd':'GSD | Incremental margin call','ml_market_mbsd':'MBSD | VM paid','ml_market_nscc':'NSCC | VM paid',
            'ml_concentration':'NSCC | Hypothetical concentration add-on','ml_sld':'NSCC | SLD called',
            'ml_cross_margin':'GSD cross-margin | Illustrative combined requirement',
            'gsd_default':'GSD default | Residual loss after own resources','cns_closeout':'NSCC CNS | Conditional close-out loss',
            'gcf_deadline':'GCF | Notional missing assumed deadline','auction_funding':'Auction issue date | Peak unpaid obligation',
            'dtc_bank':'DTC bank gate | Blocked participant gross debit','nscc_bank':'NSCC bank gate | Blocked participant gross debit',
            'mmi_ack':'MMI acknowledgement | Overdue instructions','acats_wave':'ACATS transfer wave | Overdue instructions',
            'fundserv_gross':'Fund/SERV gross orders | Overdue instructions','registration':'Registration gate | Overdue instructions',
            'security_restriction':'Explicit chill / lock | Overdue instructions','dtc_canadian_link':'DTC Canadian link | Overdue instructions',
            'nscc_international_link':'NSCC international link | Overdue instructions'}
    for engine,group in summary.groupby('engine',sort=False):
        models=list(group.model_id.drop_duplicates());ncols=2;nrows=math.ceil(len(models)/ncols)
        fig,axes=plt.subplots(nrows,ncols,figsize=(15,3.2*nrows+1),layout='constrained',squeeze=False)
        for ax,model in zip(axes.flat,models):
            g=group[group.model_id.eq(model)]
            selected=pd.concat([g[g.role.map(role_class).eq(role)].head(1) for role in ['baseline','stress','mitigation']])
            scale=100 if 'fraction' in str(selected.units.iloc[0]).lower() or str(selected.units.iloc[0]).lower()=='ratio' else 1
            means=selected['mean'].to_numpy()*scale;low=selected.p05.to_numpy()*scale;high=selected.p95.to_numpy()*scale
            colors=['#466f92','#c58149','#768044'];y=np.arange(len(selected))
            ax.hlines(y,low,high,color=colors,linewidth=2);ax.scatter(means,y,c=colors,s=32,zorder=3)
            final_label='Alternative correlation' if model=='ml_cross_margin' else 'Same stress + mitigation'
            ax.set_yticks(y,['Baseline','Stress',final_label]);ax.set_ylim(2.6,-.6)
            ax.set_xlim(0,max(1,float(high.max())*1.34));ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
            unit='%' if scale==100 else selected.units.iloc[0]
            ax.set_xlabel(unit);ax.set_title('\n'.join(textwrap.wrap(titles.get(model,model),58)),loc='left',pad=10)
            for yy,v in zip(y,means):ax.annotate(f'{v:,.2f}',(v,yy),xytext=(5,-13),textcoords='offset points',fontsize=9)
        for ax in list(axes.flat)[len(models):]:ax.set_visible(False)
        fig.suptitle('SIMULATED ONLY | '+engine.replace('_',' ').title(),fontsize=16,fontweight='bold')
        fig.supxlabel('100 paired paths per scenario. Dots: means; lines: 5th–95th path percentiles, NOT confidence intervals. Independent panel scales; no business-risk ranking.',fontsize=9)
        fig.savefig(ROOT/'figures'/f'{engine}.png',dpi=160);plt.close(fig)

def write_notes(receipt,summary,comparisons,coverage,maps):
    v1=json.loads((ROOT/'inputs/v1_execution_receipt.json').read_text())
    old_summary=pd.read_csv(ROOT/'inputs/v1_scenario_summary.csv')
    old_direct=coverage.status_code.eq('conditional_mechanism_simulated_v1').sum()
    generic=coverage.status_code.eq('generic_context_only_v1').sum()
    new=coverage.status_code.eq('conditional_mechanism_simulated_v2').sum()
    unrun=coverage.status_code.eq('not_simulated').sum()
    all_models=receipt['model_count']+old_summary.model_id.nunique()
    count=receipt['database_store']['records_in_batch']
    rows_cn=[];rows_en=[];chain_comparisons=[]
    for _,r in comparisons.iterrows():
        m=[x for x in maps if x['model_id']==r.model_id];scope_cn=m[0]['scope_cn'];scope_en=m[0]['scope_en']
        values=[format_value(r[k],r.units) for k in ['baseline_mean','stress_mean','mitigation_mean']]
        ids='ECS-NSCC-01' if r.model_id=='ml_market_nscc' else r.chain_ids
        rows_cn.append([ids,scope_cn,*values,r.units]);rows_en.append([ids,scope_en,*values,r.units])
        for mapping in m:
            metric='margin_call_usd_million' if mapping['chain_id']=='TEAM-ECS-01' else r.metric
            result=dict(r);result.update(chain_id=mapping['chain_id'],metric=metric)
            if mapping['chain_id']=='TEAM-ECS-01':
                f=read('ml_runs')
                for role in ['baseline','stress','mitigation']:
                    result[role+'_mean']=f.loc[f.scenario_id.eq(r[role+'_scenario']),metric].mean()
                result['delta_stress_minus_baseline']=result['stress_mean']-result['baseline_mean']
                result['delta_mitigation_minus_stress']=result['mitigation_mean']-result['stress_mean']
                extra=[format_value(result[k],r.units) for k in ['baseline_mean','stress_mean','mitigation_mean']]
                rows_cn.append([mapping['chain_id'],mapping['scope_cn'],*extra,r.units])
                rows_en.append([mapping['chain_id'],mapping['scope_en'],*extra,r.units])
            chain_comparisons.append(result)
    pd.DataFrame(chain_comparisons).to_csv(ROOT/'results/chain_outcome_comparisons.csv',index=False,float_format='%.17g')
    ml=read('ml_runs');sld=comparisons[comparisons.model_id.eq('ml_sld')].iloc[0]
    sld_rows=[]
    for field,cn_label,en_label in [('sld_called_usd_million','要求的SLD','SLD called'),('sld_collected_usd_million','实际收取的模拟SLD','SLD collected in the model'),('remaining_liquidity_gap_usd_million','模型中剩余流动性缺口','Remaining modeled liquidity gap')]:
        vals=[float(ml.loc[ml.scenario_id.eq(sld[k+'_scenario']),field].mean()) for k in ['baseline','stress','mitigation']]
        sld_rows.append((cn_label,en_label,vals))
    sld_cn=table(['SLD指标，百万美元','基准','压力','增加会员现金后'],[[cn,*[f'{v:.2f}' for v in vals]] for cn,en,vals in sld_rows])
    sld_en=table(['SLD measure, USD million','Baseline','Stress','More member cash'],[[en,*[f'{v:.2f}' for v in vals]] for cn,en,vals in sld_rows])
    header_cn=['链编号','本轮模拟的机制','基准均值','压力均值','缓解均值','单位']
    header_en=['Chain IDs','Mechanism simulated','Baseline mean','Stress mean','Mitigation mean','Units']
    cn=f'''# 扩展传导链情景模拟：中文结果

**这是合成数据的机制实验，不是实际事故检验、官方风险模型或机器学习验证。** 本轮新增 **{receipt['model_count']}个机制原型、{new}条目录链的部分机制覆盖、{receipt['scenario_count']}种预设情景**，每种100次配对运行，共{receipt['scenario_count']*100:,}组运行、{count:,}条模拟记录。随机种子{receipt['seed']}；批次`{receipt['simulation_id']}`。

加上[前轮DTC/EPN/TBA原型](../synthetic_chain_simulations_2026_10_27/README.md)，共 **{all_models}个机制原型、{len(summary)+len(old_summary)}种情景**。56条v3目录链中，**{new+old_direct}条有部分机制模拟，另{generic}条只有通用故障背景，{unrun}条尚未建立专属模拟**。链的覆盖数量不能当作完整验证数量；本分支没有任何链被标记为完整验证。

## 新增了什么

- 保证金与流动性：GSD、MBSD、NSCC分别建模；区分VM现金流、保证金存量、集中度附加要求和SLD；交叉保证金只展示抵销风险的假设机制。
- 违约与资金：分别展示GSD自有资源和假设剩余损失分配、NSCC多空平仓、GCF双重到期门槛、拍卖发行日资金集中、DTC与NSCC各自的结算银行门槛。
- 服务操作：MMI资金确认、ACATS转户量、Fund/SERV总申赎处理量、登记确认、特定证券chill/lock、DTC加拿大链路和NSCC国际链路分别建模。

## 给定假设下的结果

以下每行使用自身的业务指标和参数，不能按数值大小横向比较业务风险。缓解情景可能投入额外现金、资源、处理能力或改变组合；不是无成本收益。

{table(header_cn,rows_cn)}

金额单位`USD million`为百万美元。比例以百分比展示；假设路径中发生的比例不是实际失败概率。所有均值来自预设模拟分布；均值区间可查[逐情景结果](results/scenario_summary.csv)。图中线段是路径的5%—95%分位范围，不是现实参数的置信区间。

图表：[保证金与流动性](figures/margin_liquidity.png) · [违约与资金](figures/default_funding.png) · [服务操作](figures/service_operations.png)。各面板单位／刻度独立，不用于业务风险排名。

SLD尤其要分开看：增加会员可缴现金改善收取情况和剩余缺口，不改变原先所需金额。

{sld_cn}

NSCC的VM和TEAM-ECS-01保证金追缴在上表分行展示。交叉保证金的“缓解”列只是把假设相关性恢复的替代情景，相关性并非业务可直接控制的行动。许多缓解情景为0，反映所选资源和阈值足够，不是实际系统不会失败的保证。

## 怎样读这些链

流程是：**按目录选择相关事件与业务 → 生成虚拟头寸、订单或资金安排 → 施加预设冲击 → 通过明确的现金／资源／时间／授权约束 → 记录结果 → 和相同基础输入的基准、缓解及无关事件对照比较**。这里没有额外的E乘数；相关性是情景路由条件，不能由随机数据证明。

两个结果尤其需要区分：VM是盯市现金流，保证金是资源要求存量，SLD是单独的流动性支付要求；迟到但完成与观察期末仍未完成也分开记录。资金确认或授权通过，只代表通过本模型的一道门槛，不保证真实完整结算成功。GSD剩余损失按虚拟容量分摊的做法不是官方损失瀑布；不把NSCC多空都向不利方向移动的情景称为一条共同市场价格路径。

## 仍然没有验证什么

- 实际事件是否影响具体会员／服务、实际故障概率、真实参数和官方模型公式。
- 真实外部冲击与上一期PQD内部脆弱度的因果关系、完整`冲击×脆弱度`评分效果和预测模型表现。本轮没有用合成结果拟合或重新训练模型。
- [完整56条覆盖清单](CHAIN_COVERAGE_CN.md)列出未模拟部分；[逐链CSV](results/chain_coverage_CN.csv)保留原始数据缺口。会员名单、实际人工风控决策、法律触发与同意、业务版本和真实结果不能靠随机生成补成证据。
- 原始真实数据库、原31条链检验结果和队友周度评分保持不变。模拟数据只进入独立SQLite库，逐行标记`source_type=synthetic`与`empirical_validation=False`。

## 可复现入口

[README](README.md) · [冻结方案](config/resolved_plan.json) · [全部模型假设](results/model_assumptions.json) · [数值检查](results/verification.json) · [来源与用途](inputs/source_register.json)。配对对照与敏感性设计参考Quant-tech的基准／敏感性指导，不能由此推断真实泛化表现。

公开资料只支持定性机制：[MMI资金确认](https://dtcclearning.com/products-and-services/settlement/mmi.html)、[ACATS服务范围](https://dtcclearning.com/products-and-services/equities-clearing/acats.html)、[Fund/SERV处理与结算](https://dtcclearning.com/products-and-services/mutual-fund-services/fund-serv.html)、[交叉保证金](https://dtcclearning.com/products-and-services/fixed-income-clearing/cross-margining.html)。模拟数字均为假设，不是这些网页提供的参数；规则证据是之前已保存的版本。
'''
    en=f'''# Expanded transmission-chain scenario simulations

**Synthetic mechanism experiments, not actual incidents, official risk models or machine-learning validation.** This batch adds **{receipt['model_count']} mechanism prototypes, partial mechanism coverage for {new} catalog chains and {receipt['scenario_count']} predeclared scenarios**, each with 100 paired paths: {receipt['scenario_count']*100:,} scenario runs and {count:,} generated records. Seed {receipt['seed']}; batch `{receipt['simulation_id']}`.

Together with the [earlier DTC/EPN/TBA prototypes](../synthetic_chain_simulations_2026_10_27/README.md), there are **{all_models} mechanism prototypes and {len(summary)+len(old_summary)} scenarios**. Among 56 expanded-v3 catalog chains, **{new+old_direct} have partial mechanism simulations, another {generic} have generic outage contexts only, and {unrun} have no dedicated simulation**. Coverage counts are not validation counts. No chain in this branch is marked fully validated.

## Added scope

- Margin/liquidity: separate GSD, MBSD and NSCC books; VM cash flows, margin stocks, concentration add-ons and SLD remain distinct. Cross-margin illustrates assumed offsets.
- Default/funding: GSD own resources and illustrative residual allocation, NSCC long/short close-out, GCF joint deadline gates, auction issue-date funding concentration, and distinct DTC/NSCC settling-bank gates.
- Service operations: MMI funding acknowledgement, ACATS transfer waves, Fund/SERV gross purchase/redemption processing, registration confirmation, explicit security-level chill/lock, DTC Canadian link and NSCC international link.

## Results under declared assumptions

Each row uses its own measures and inputs; the values cannot rank business risk. Mitigation can add cash, resources, capacity or change exposures and is not costless.

{table(header_en,rows_en)}

`USD million` means millions of US dollars. Fraction measures are displayed as percentages; proportions in assumed paths are not real failure probabilities. Means reflect only the specified synthetic distributions. See [all scenario summaries](results/scenario_summary.csv). Figure intervals are 5th–95th path percentiles, not confidence intervals for real-world parameters.

Figures: [Margin/liquidity](figures/margin_liquidity.png) · [Default/funding](figures/default_funding.png) · [Service operations](figures/service_operations.png). Panel measures/scales are independent and do not rank business risk.

SLD calls and collection must be read separately. More available member cash improves collection and the remaining gap without changing the required call.

{sld_en}

NSCC VM and TEAM-ECS-01 margin calls appear as separate rows above. For cross-margin, the mitigation column is only an alternative scenario restoring assumed correlation; correlation is not a directly controllable business action. Zero outcomes in many mitigation cases reflect sufficient chosen resources/thresholds, not guarantees of real-world safety.

## Interpretation

Workflow: **route an event to the catalog mechanism → generate virtual positions/orders/funding → impose a predeclared shock → apply explicit resource/time/authorization constraints → record outcomes → compare paired baseline, stress, mitigation and unrelated controls**. There is no additional E multiplier; applicability is an assumed routing condition, not a relationship established by generated data.

VM is a marked-to-market cash flow, margin is a resource requirement stock, and SLD is a separate liquidity payment requirement. Late-completed and unfinished outcomes are distinct. Passing a funding/authorization gate in a model is not proof that full real-world settlement would complete. The GSD residual-capacity allocation is not the official loss waterfall. The NSCC adverse long/short close-out scenario is not one common market-price path.

## Evidence still missing

- Actual incident-to-member/service exposure, incident frequency, real parameters and official model formulas.
- A causal relationship between external shocks and lagged-PQD vulnerability, a validated full shock×vulnerability score, or predictive model performance. No model was fitted or retrained on synthetic outcomes.
- See [all 56 catalog-chain coverage entries](CHAIN_COVERAGE_EN.md) and the [chain CSV](results/chain_coverage_EN.csv). Actual memberships, discretionary control decisions, legal triggers/consent, service versions and observed outcomes cannot be manufactured as evidence.
- The empirical database, 31-chain empirical results and teammate weekly scores remain unchanged. Every generated record is isolated in a separate SQLite database with `source_type=synthetic` and `empirical_validation=False`.

## Reproduce and inspect

[README](README.md) · [Frozen plan](config/resolved_plan.json) · [Assumptions](results/model_assumptions.json) · [Checks](results/verification.json) · [Sources and uses](inputs/source_register.json). Quant-tech baseline/sensitivity guidance informed experiment design; that does not establish real-world generalization.

Qualitative references: [MMI acknowledgement](https://dtcclearning.com/products-and-services/settlement/mmi.html), [ACATS](https://dtcclearning.com/products-and-services/equities-clearing/acats.html), [Fund/SERV](https://dtcclearning.com/products-and-services/mutual-fund-services/fund-serv.html), [cross-margining](https://dtcclearning.com/products-and-services/fixed-income-clearing/cross-margining.html). None supplies the hypothetical numeric parameters used here. Saved rule evidence retains its original version.
'''
    (ROOT/'RESULTS_CN.md').write_text(cn);(ROOT/'RESULTS_EN.md').write_text(en)
    dump(ROOT/'results/coverage_counts.json',{'new_mechanism_models':receipt['model_count'],'all_mechanism_models':int(all_models),'new_scenarios':len(summary),'all_scenarios':len(summary)+len(old_summary),'new_chain_ids':int(new),'all_partial_mechanism_chain_ids':int(new+old_direct),'generic_context_only_chain_ids':int(generic),'not_simulated_chain_ids':int(unrun),'catalog_chain_ids':len(coverage),'full_chain_validated_in_simulation_branch':0})

if __name__=='__main__':main()

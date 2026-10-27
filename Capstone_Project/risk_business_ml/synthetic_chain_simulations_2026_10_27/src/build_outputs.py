"""Build readable scenario notes and exportable figures from saved simulation rows."""
from pathlib import Path
import json,os
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.qa/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

METRICS={
 'dtc':('DTC_CONTROL','eod_pending_amount_usd_million','USD million','End-horizon pending transactions','期末仍待处理交易金额'),
 'epn':('EPN_POOL','overdue_order_fraction','fraction of orders','Orders overdue at the assumed deadline','超过假设交割时限的订单占比'),
 'tba':('TBA_PIPELINE','peak_overdue_to_initial','fraction of initial assumed stock','Peak overdue notional / initial assumed stock','到期未交收头寸峰值／假设初始头寸'),
}
def read(name):return pd.read_csv(ROOT/'data'/f'{name}.csv',dtype={'scenario_seed':'string'},float_precision='round_trip')

def main():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text());sid=receipt['simulation_id']
    rows=[];frames={}
    for prefix,(model,metric,unit,en,cn) in METRICS.items():
        frame=read(prefix+'_runs');frames[prefix]=frame
        for scenario,part in frame.groupby('scenario_id',sort=False):
            x=part[metric];sample=part.iloc[0]
            rows.append({'model_id':model,'scenario_id':scenario,'scenario_label_en':sample.scenario_label_en,'scenario_label_cn':sample.scenario_label_cn,'metric':metric,'metric_label_en':en,'metric_label_cn':cn,'units':unit,'replications':len(part),'mean':x.mean(),'p05':x.quantile(.05),'p95':x.quantile(.95),'source_type':'synthetic','simulation_id':sid,'empirical_validation':False,'interval_meaning':'5th to95th percentile across hypothetical paths, not a confidence interval or a real-world risk probability'})
    summary=pd.DataFrame(rows);summary.to_csv(ROOT/'results/scenario_summary.csv',index=False,float_format='%.17g')
    draw_charts(summary,frames)
    write_notes(summary,frames,receipt)
    statuses=[]
    definitions=[('ECS-DTC-06','DTC_CONTROL','scenario_explored'),('FICC-MBSD-08','EPN_POOL','scenario_explored'),('FICC-MBSD-02','EPN_POOL','scenario_explored'),('FICC-MBSD-05','EPN_POOL','generic_outage_scenario_only'),('FICC-MBSD-09','EPN_POOL','generic_outage_scenario_only'),('FICC-MBSD-06','TBA_PIPELINE','scenario_explored')]
    for chain,model,state in definitions:
        statuses.append({'catalog_version':'expanded_v3','chain_id':chain,'model_id':model,'simulation_id':sid,'simulation_status':state,'source_type':'synthetic','historical_validation_status':'unchanged; service-specific empirical data remain missing','full_chain_validated':False,'real_world_probability_calibrated':False})
    pd.DataFrame(statuses).to_csv(ROOT/'results/chain_simulation_status.csv',index=False)
    build_schema_note(frames)
    print('Built29 scenario summaries, three individual figures, overview figure, bilingual notes and simulation-only chain labels.')

def draw_charts(summary,frames):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    selected={
      'DTC_CONTROL':[('dtc_baseline','Baseline'),('dtc_funding_shock','Funding + haircut shock'),('dtc_cap_only_rescue','Same shock + cap only'),('dtc_cash_rescue','Same shock + added cash'),('dtc_high_buffer','Same shock + larger buffer')],
      'EPN_POOL':[('epn_baseline','Baseline'),('epn_prolonged_outage','160-min relevant outage'),('epn_severe_outage','290-min relevant outage'),('epn_capacity_rescue','Same outage + all-day capacity')],
      'TBA_PIPELINE':[('tba_baseline','No deferral'),('tba_transient_delay','Transient deferral'),('tba_prolonged_delay','Prolonged deferral'),('tba_earlier_recovery','Same initial shock, earlier recovery')],
    }
    titles={'DTC_CONTROL':'DTC: pending transactions','EPN_POOL':'EPN: overdue deliveries','TBA_PIPELINE':'TBA: peak overdue positions'}
    axes_labels={'DTC_CONTROL':'USD million pending at minute480','EPN_POOL':'Orders overdue at minute300 (%)','TBA_PIPELINE':'Peak overdue / initial assumed stock (%)'}
    def draw(ax,model):
        part=summary.set_index('scenario_id');pairs=selected[model]
        values=part.loc[[x[0] for x in pairs]];scale=1 if model=='DTC_CONTROL' else 100
        means=values['mean'].to_numpy()*scale;low=values.p05.to_numpy()*scale;high=values.p95.to_numpy()*scale
        y=np.arange(len(pairs));colors=['#466f92']*len(pairs);colors[1]='#c58149'
        ax.hlines(y,low,high,color=colors,linewidth=2.4)
        ax.scatter(means,y,color=colors,s=36,zorder=3,clip_on=False)
        ax.set_yticks(y,[x[1] for x in pairs]);ax.set_ylim(len(pairs)-.25,-.5);ax.set_xlim(0,max(1.,float(high.max())*1.26));ax.set_xlabel(axes_labels[model]);ax.set_title(titles[model],loc='left',pad=14,fontweight='bold')
        ax.grid(axis='x',alpha=.16);ax.set_axisbelow(True)
        for value,yy in zip(means,y):ax.annotate(f'{value:.1f}',(value,yy),xytext=(6,-15),textcoords='offset points',fontsize=9,color='#253547')
    fig,axs=plt.subplots(1,3,figsize=(16,6.0),layout='constrained')
    for ax,model in zip(axs,selected):draw(ax,model)
    fig.suptitle('SIMULATED MECHANISMS | 100 paired paths per scenario',fontsize=16,fontweight='bold')
    fig.supxlabel('Dots: simulation means. Lines: 5th–95th path percentiles, NOT confidence intervals. Parameters are hypothetical; panels use different measures.',fontsize=10)
    fig.savefig(ROOT/'figures/simulation_overview.png',dpi=180);plt.close(fig)
    for model in selected:
        fig,ax=plt.subplots(figsize=(9.5,5.5),layout='constrained');draw(ax,model)
        fig.suptitle('SIMULATED ONLY | Hypothetical parameters',fontsize=13,fontweight='bold')
        fig.supxlabel('100 paired paths/scenario. Lines show path percentiles, not confidence intervals.',fontsize=10)
        fig.savefig(ROOT/'figures'/f'{model.lower()}.png',dpi=180);plt.close(fig)
    # Preserve the distinction between observed late completion and censoring.
    epn=frames['epn'];ids=['epn_baseline','epn_prolonged_outage','epn_severe_outage','epn_beyond_horizon','epn_capacity_rescue']
    part=epn.groupby('scenario_id')[['delayed_completed_delivery_count','unfinished_delivery_count']].mean().loc[ids]
    fig,ax=plt.subplots(figsize=(10,5.3),layout='constrained');x=np.arange(len(ids))
    ax.bar(x,part.delayed_completed_delivery_count,label='Completed after deadline',color='#466f92')
    ax.bar(x,part.unfinished_delivery_count,bottom=part.delayed_completed_delivery_count,label='Not completed by horizon',color='#c58149',hatch='//')
    totals=part.sum(axis=1).to_numpy()
    ax.set_xticks(x,['Baseline','160-min outage','290-min outage','Beyond horizon','Higher all-day\ncapacity']);ax.set_ylabel('Mean count out of48 synthetic orders');ax.set_ylim(0,max(totals)*1.20)
    for xx,total in zip(x,totals):ax.annotate(f'{total:.2f}',(xx,total),xytext=(0,6),textcoords='offset points',ha='center')
    ax.set_title('SIMULATED EPN | Late completion and unfinished delivery are separate',loc='left',fontweight='bold');ax.legend(frameon=False);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    fig.savefig(ROOT/'figures/epn_completion_status.png',dpi=180);plt.close(fig)

def write_notes(summary,frames,receipt):
    def mean(prefix,scenario,column):return float(frames[prefix].loc[frames[prefix].scenario_id.eq(scenario),column].mean())
    pending=mean('dtc','dtc_funding_shock','eod_pending_amount_usd_million')
    debit=mean('dtc','dtc_high_buffer','eod_net_debit_usd_million')
    addedcash=mean('dtc','dtc_cash_rescue','cash_funding_received_usd_million')-mean('dtc','dtc_funding_shock','cash_funding_received_usd_million')
    overdue=mean('epn','epn_prolonged_outage','overdue_order_fraction')*100
    unfin=mean('epn','epn_beyond_horizon','unfinished_delivery_count')
    peak=mean('tba','tba_prolonged_delay','peak_overdue_to_initial')*100
    earlier=mean('tba','tba_earlier_recovery','peak_overdue_to_initial')*100
    paths=sum(len(frame) for frame in frames.values());count=receipt['database_store']['records_in_batch']
    en=f'''# Three synthetic transmission-chain prototypes

**SIMULATION ONLY.** These are executed mechanism/implementation experiments, not observations of DTCC members, incidents, production processing or calibrated business risk.

Three models,29 declared scenarios,100 paired replications per scenario: **{paths:,} scenario runs** and **{count:,} generated input/trace/summary records**. Seed20261027. Identity: `{receipt['simulation_id']}`. The29 cases use different assumptions and measures; they are not29 historical events.

| Prototype | Conditional result under the stated assumptions |
|---|---|
| DTC two-constraint queue | Mean pending transactions at the480-minute horizon: **USD{pending:.2f}million** under combined funding delay/shortfall and haircut shock, versus0 in baseline. A larger assumed cap/collateral buffer allows processing but leaves mean outstanding debit **USD{debit:.2f}million**. Extra-cash mitigation adds **USD{addedcash:.2f}million** of assumed cash on average; its benefit is not free. Cap capacity alone does not remove the collateral constraint in these cases. |
| EPN notification-to-pool pipeline | A hypothetical160-minute relevant outage leaves **{overdue:.2f}%** of orders overdue at the assumed delivery deadline, versus0 in baseline. A higher ALL-DAY processing capacity yields0 overdue orders in the paired cases. Beyond-horizon outage leaves **{unfin:.2f}** orders unfinished on average; zero late-completed orders in that case is not evidence of safety. |
| TBA stock-flow ladder | Peak overdue notional averages **{peak:.2f}%** of hypothetical opening TBA stock under prolonged deferral; earlier recovery reduces this measure to **{earlier:.2f}%**. These are gross-notional stock ratios, not losses, cash payment obligations or real failure probabilities. |

## What was checked

Hand-computed fixtures, resource/admission limits, cash and transaction conservation, stock-flow conservation, exact unrelated-event controls, deadlines, horizon censoring, common random inputs and repeat-store idempotency. Runtime controls are in `results/execution_receipt.json`; independent audits and unit-test evidence are in `results/`. Passing a code check does not validate an empirical transmission chain.

## Assumptions that change interpretation

- DTC: a generic single-participant FIFO queue; it is not DTC's production optimization engine. Simulated cash repays debit before prefunding; it is not also credited to collateral. Received securities do not automatically replenish the separate eligible collateral portfolio. Baseline scheduled cash equals generated gross payments by construction. Stress combines50% scheduled amounts,180-minute delay and a haircut increase; some funding arrives outside the horizon, so received cash is not simply50% of baseline.
- EPN: relative cutoff240, delivery deadline300 and horizon480 are arbitrary simulation minutes, not official SIFMA cutoffs. All generated original/corrected valid notices arrive before cutoff; the outage delays processing and delivery. A separate hand-computed fixture covers a late notice that is still delivered on time. Capacity mitigation applies to the ENTIRE day. Nominal queue start/pre-service wait excludes pauses during service. Delayed completions and unfinished orders remain separate.
- TBA: the public2026Q2 broad MBSD unsettled-guarantee amount, USD562billion, is an illustrative scale only. A50% TBA share and25%/75% sensitivity shares are assumptions, not estimates. New flows, maturities, cancellations and deferrals are synthetic. Equal normalized results across share cases follow from linear scaling, not evidence of real business sensitivity. On an unimpaired model day all due positions settle; there is no independently calibrated throughput limit.
- Percentile bars describe variation among hypothetical paths. They are not confidence intervals for DTCC or empirical probabilities. No p-values or synthetic correlations are used to declare a chain validated.

## Data separation

Every generated row is labelled `source_type=synthetic`, with scenario/replication/seed, assumption version, catalog version and simulation ID. Exact unsigned RNG seeds are stored as text. The public anchor is in a separate reference table. The dedicated `data/synthetic_scenarios.sqlite3` is physically separate from the team's real public-data database. Historical missing-data statuses and existing weekly scores remain unchanged; no model was fitted or retrained on synthetic outcomes.

Use `results/chain_simulation_status.csv` for the additional scenario-exploration label. It does not replace the empirical31-chain status table. MBSD05/09 are generic conditional-outage contexts, not identified cyber incidents or affected participants.

## Open and rerun

Start with [README](README.md). See [all scenario results](results/scenario_summary.csv), [frozen plan](config/resolved_plan.json), [assumptions](results/model_assumptions.json), [source register](inputs/source_register.json) and [SQL examples](src/query_synthetic.sql). The full numerical setup is reproducible; the real-world behavior remains to be tested with suitable data.

Mechanism context: [DTCC financial risk controls](https://www.dtcc.com/about/protecting-the-markets/managing-risk/financial-risk-management). Synthetic-data scope: [ONS policy](https://www.ons.gov.uk/aboutus/transparencyandgovernance/datastrategy/datapolicies/syntheticdatapolicy). These sources do not supply our hypothetical numerical parameters. Quant-tech sensitivity/generalization guidance informed the control design.
'''
    cn=f'''# 三个传导链模拟原型：运行结果

**全部为情景模拟。** 本轮检验的是给定假设下的机制和程序，不是DTCC会员、事故或实际系统运行记录，也没有校准真实风险概率。

3个模型、29个预设情景，每个情景100次配对模拟，共 **{paths:,}组情景运行、{count:,}条生成的输入／轨迹／汇总记录**。基础随机种子20261027。版本标识：`{receipt['simulation_id']}`。29种情景不是29次真实历史事件。

| 原型 | 在明确假设下得到的结果 |
|---|---|
| DTC额度／抵押品约束队列 | 资金延迟、资金减少及抵押品折扣共同冲击下，480分钟期末平均仍待处理交易金额为 **{pending:.2f}百万美元**，基准为0。加大假设额度和抵押品缓冲可以放行交易，但仍有平均 **{debit:.2f}百万美元净借记未偿还**，不能称为现金义务已经付清。现金救助情景平均另注入 **{addedcash:.2f}百万美元**，并非无成本改善。仅提高额度在这些设定下无法解除抵押品约束。 |
| EPN通知→资产池交割 | 假设相关中断持续160分钟，平均 **{overdue:.2f}%** 的订单超过假设交割时限，基准为0。提高**全天**处理能力后，本组配对路径中的超期订单为0。超过观察期的中断平均留下 **{unfin:.2f}笔未完成订单**；该情景“已完成但迟交”的数量为0，并不代表没有风险。 |
| TBA头寸滚动 | 持续交收延期下，到期未交收头寸峰值平均为假设初始TBA头寸的 **{peak:.2f}%**；相同初始冲击下提前恢复，该指标为 **{earlier:.2f}%**。这是总名义头寸比例，不是损失、现金支付义务或真实失败概率。 |

## 检查了什么

包括手算样例、额度及抵押品准入、现金／交易守恒、头寸收支守恒、无关事件对照、截止时限、观察期截尾、共同随机输入和重复写库去重。运行控制见 `results/execution_receipt.json`，独立核查和单元测试记录见 `results/`。程序检查通过不等于真实传导链得到验证。

## 必须同时阅读的假设

- **DTC：** 单一虚拟参与者的简化FIFO队列，不复制DTC真实优化引擎。注资先偿还模拟净借记，剩余作为预付现金，不同时增加证券抵押品。收到证券不自动进入独立抵押品池。基准全天计划资金等于生成的总付款额，是人为设定。压力情景同时将计划金额改为50%、推迟180分钟并增加折扣；部分资金超过观察期，因此实际收到的资金并不简单等于基准的50%。
- **EPN：** 通知截止240、交割截止300、观察期480全部是假设的相对分钟，不是SIFMA实际时点。生成的原始／修正有效通知都在截止前到达，中断影响的是后续处理与交割；另有手算测试验证“通知晚到不必然最终迟交”。提高处理能力情景覆盖全天，不只是恢复阶段。名义排队开始／服务前等待不包含处理中暂停。迟交完成与期末未完成分列。
- **TBA：** 2026Q2公开的MBSD广义未交收保证事项名义金额5620亿美元只作规模参照，不是TBA专属头寸。50%份额及25%／75%敏感性份额均是假设。新交易、期限、撤单和延期均为生成。份额改变后归一化指标相同，是线性缩放的结果，不是实证发现。模型正常日可交收全部已到期头寸，未独立校准处理吞吐能力。
- 百分位区间只反映假设路径之间的变化，不是真实业务的置信区间。本轮不使用合成相关性或p值宣布任何链通过。

## 模拟数据与真实数据分开

每条生成记录都带 `source_type=synthetic`、情景编号、配对编号、精确文本形式的随机种子、假设版本、目录版本和模拟批次编号。公开参照数据单独存表。专用数据库 `data/synthetic_scenarios.sqlite3` 与团队真实公开数据库物理分离。原31条链的数据缺口、实证验证状态和周度评分均保持不变；本轮没有用生成结果训练或重新训练预测模型。

`results/chain_simulation_status.csv` 只增加“情景已探索”标签，不替代原实证状态。MBSD05／09仅作为条件性的通用故障情景，不代表已发现真实网络攻击或识别出受影响会员。

## 入口与复现

从 [README](README.md) 开始。查看 [全部情景结果](results/scenario_summary.csv)、[冻结方案](config/resolved_plan.json)、[假设说明](results/model_assumptions.json)、[来源记录](inputs/source_register.json) 和 [SQL示例](src/query_synthetic.sql)。计算设置可以复现，真实业务关系仍需要合适的数据检验。

机制背景：[DTCC风险控制说明](https://www.dtcc.com/about/protecting-the-markets/managing-risk/financial-risk-management)。合成数据用途边界：[ONS政策](https://www.ons.gov.uk/aboutus/transparencyandgovernance/datastrategy/datapolicies/syntheticdatapolicy)。这些来源没有提供本轮假设的数值参数；控制设计参考了Quant-tech有关敏感性和泛化的指导。
'''
    (ROOT/'RESULTS_EN.md').write_text(en);(ROOT/'RESULTS_CN.md').write_text(cn)
    readme='''# Synthetic Chain Simulations / 传导链情景模拟

**SIMULATED ONLY / 全部为假设模拟**。3个模型的配置、数据、程序、结果和检查集中在本文件夹；没有写入真实业务数据库，没有改变原验证状态，也没有自动推送到GitHub。

Start with **[中文结果](RESULTS_CN.md)** or **[English results](RESULTS_EN.md)**.

| Folder / 目录 | Content / 内容 |
|---|---|
| `src/` | Three engines, runner, output builder, independent audits and SQL queries. 三个引擎、运行与独立核查程序。 |
| `config/` | Plan, defaults, seeds and engine hashes frozen before calculations. 计算前冻结的设置。 |
| `inputs/` | Public reference/evidence and original-artifact protection hashes. 公开参照与真实文件保护校验值。 |
| `data/` | Tagged synthetic CSVs and separate `synthetic_scenarios.sqlite3`. 标注为模拟的CSV与独立数据库。 |
| `results/` | Scenario summary, controls, assumptions, audits and simulation-only status. 汇总、假设与检查。 |
| `figures/` | Exportable static scenario figures, all labelled SIMULATED. 所有图均标明模拟。 |

## Run / 运行

Python3.12+ with `requirements.txt` (execution used Python3.13; versions in the receipt).
From this folder:

```bash
python3 -m unittest discover -s tests -v
python3 src/run_simulations.py --seed 20261027 --replications 100
python3 src/build_outputs.py
python3 src/audit_epn_tba.py
python3 src/verify_outputs.py
python3 src/query_store.py
```

The source-generated plan and simulation ID change if engine code or parameters change.
The same batch inserts no duplicate records. Exact unsigned scenario seeds are text in SQLite;
convert with `int(seed_string)` only when initializing an RNG. Inspect the views with a read-only
SQLite connection; example queries are in `src/query_synthetic.sql`. The ZIP ships the compressed
synthetic snapshot; `python3 src/query_store.py` verifies its checksums, restores it if needed,
and then queries it read-only. It never opens the team's real public-data database.

This is a simplified mechanism study, not a production replica, causal validation, real-world
loss/probability model, or a comparison ranking DTCC business lines. No synthetic row is a new
historical event or quarter. The ordinary project database and weekly scoring pipeline do not
read this dedicated store. A real-data anchor constrains scale, not unidentified portfolio shares.
'''
    (ROOT/'README.md').write_text(readme)

def build_schema_note(frames):
    path=ROOT/'results/data_dictionary.json';d={}
    for name in ['dtc_inputs','dtc_events','dtc_runs','epn_inputs','epn_events','epn_runs','tba_inputs','tba_daily','tba_runs']:
        f=read(name)
        d[name]={'rows':len(f),'columns':[{'name':c,'dtype':str(f[c].dtype)} for c in f],'grain':{'dtc_inputs':'scenario/replication/initial resources or scheduled transaction/resource event','dtc_events':'scenario/replication/ordered event state','epn_inputs':'scenario/replication/order','epn_events':'scenario/replication/order outcome','tba_inputs':'scenario/replication/opening cohort or daily new/control row','tba_daily':'scenario/replication/simulated day'}.get(name,'scenario/replication summary'),'source_type':'synthetic'}
    path.write_text(json.dumps(d,indent=2)+'\n')

if __name__=='__main__':main()

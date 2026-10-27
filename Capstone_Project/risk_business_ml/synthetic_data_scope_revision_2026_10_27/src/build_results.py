"""Explain the corrected source scope and missing-link-only results."""
from pathlib import Path
import json
import pandas as pd
from source_policy import ROOT

def main():
    receipt=json.loads((ROOT/'results/execution_receipt.json').read_text())
    f=pd.read_csv(ROOT/'data/gap_runs.csv',float_precision='round_trip',dtype={'scenario_seed':'string'})
    specs={r['scenario_id']:r for r in json.loads((ROOT/'results/scenario_definitions.json').read_text())}
    rows=[]
    for sid,g in f.groupby('scenario_id',sort=False):
        spec=specs[sid];x=g.primary_value
        rows.append({'scenario_id':sid,'model_id':spec['model_id'],'role':spec['role'],'primary_metric':g.primary_metric.iloc[0],
                     'primary_units':g.primary_units.iloc[0],'mean':x.mean(),'p05':x.quantile(.05),'p95':x.quantile(.95),'replications':len(g),
                     'observed_fields_regenerated':False,'source_type':'hybrid_scenario','empirical_validation':False})
    s=pd.DataFrame(rows);s.to_csv(ROOT/'results/scenario_summary.csv',index=False,float_format='%.17g')
    def stress(model):return float(s[s.model_id.eq(model)&s.role.eq('stress')]['mean'].iloc[0])
    auction=stress('auction_missing_cash');tba=stress('tba_missing_ladder')*100;concentration=stress('concentration_missing_members')
    tests=receipt['unit_tests']['tests_run']
    cn=f'''# 修正版：真实数据不生成，只模拟缺失环节

**之前扩展得太宽，现已纠正。** 真实数据优先是选择数据的方法，不是最后给结果贴一个“模拟”标签。已有真实数据的环节仍使用原实证结果；只有尚未取得的变量／过程才进入条件模拟。统计不显著、检验失败或样本较短，不是“缺数据”。

## 56条链如何分流

- **9条沿用真实数据规格**：包括GSD国债波动→保证金、MBSD／NSCC市场波动→VM、NSCC保证金和回测等；个别还需补日历或设计，不能改用随机业务数据。
- **22条部分有真实数据**：保留真实字段、日期、单位和结果，只对缺失环节设置假设。
- **18条缺专属业务数据**：列为可做条件模拟的候选，不代表18条已全部完成新检验。
- **7条先补事实／定义**：例如观察名单、法律应急决定、具体依赖或政策触发，不能随机生成“真的发生过”的证据。

[56条逐环节清单](SOURCE_PRIORITY_CN.md)明确列出已有真实部分、禁止生成的字段和允许的模拟范围；[CSV](results/source_priority_CN.csv)可直接筛选。

## 已按新规则运行的三个示范

| 链与示范 | 固定使用的真实数据 | 仅模拟的缺失部分 | 本轮检查 |
|---|---|---|---|
| GSD拍卖资金路径 | 2026年9月实际发行日期、37条记录、合计2.658万亿美元**发行供给金额** | 未知实际获配／清算参与／净额转换比例、可用资金和延迟 | 资金及未付款项守恒；原日期和供给金额不变 |
| MBSD TBA期限路径 | 2026Q2广义未交收保证事项名义金额**5620亿美元** | 未披露的TBA份额、到期期限和延期 | 头寸守恒；不能把广义总额当成真实TBA专属金额 |
| NSCC会员集中度路径 | 2026Q2前五会员持仓季度平均份额**36.49%**；峰值**40.25%**另列 | 与真实平均份额相容的虚拟会员分布及假设加收函数 | 前五总份额、排序和总量守恒；不虚构真实会员身份 |

共15种情景，每种100次配对运行，**1,500组运行、62,500条情景／轨迹记录**；{tests}项单元检查通过。程序会拒绝对已知真实字段提出生成请求，并核对冻结源文件没有被改动。

在当前假设下，压力情景的平均输出分别为：拍卖路径峰值未付款项**{auction:,.2f}百万美元**；TBA路径峰值到期未交收／假设TBA初始存量**{tba:.2f}%**；集中度路径假设加收**{concentration:.4f}个归一化单位**（总敞口设为100，**不是美元**）。这些只表示缺失参数取当前假设时的模型结果，不是实际GSD缺口、真实TBA失败比例或真实NSCC加收金额。完整情景值见[结果表](results/scenario_summary.csv)。

## 这种检验能回答什么

流程是：**保留已有真实数据 → 只为缺失变量定义合理假设与范围 → 检查资金／头寸／排序等约束 → 比较基准、压力、缓解和无关事件对照 → 报告假设敏感性**。

它能检查“如果缺失环节是这样的，后果会怎样”和程序是否自洽；不能证明真实历史中冲击已经传到该业务。模拟出来的会员分布并不是真实会员数据；NSCC季度平均份额不是某一天或季末头寸。拍卖供给金额也不是实际获配或GSD义务。原真实检验、真实数据库和队友评分均未被替代或修改。

更严谨的区分是：有事实依据但缺内部过程时，可做条件模拟；连事实、业务依赖或法律触发都没有确认时，先标为未确认，不能用随机标签补成事件证据。已采集资料中缺失，也不等于已证明公开数据永远拿不到。

来源、字段及程序：[冻结真实输入](inputs/observed_source_manifest.json) · [字段级来源](results/field_provenance.json) · [具体假设](results/model_assumptions.json) · [运行凭证](results/execution_receipt.json)。此前131种广泛假设情景保留为历史程序实验，不再作为当前“补缺数据”的覆盖口径。
'''
    en=f'''# Corrected scope: preserve real data; simulate missing steps only

**The earlier expansion was too broad and has been corrected.** Source precedence must determine the inputs, not merely appear as a synthetic-data label afterward. Existing real-data tests remain authoritative, including weak or insignificant results. A failed threshold or short sample is not missing data.

## Source routes across56chains

- **9 use existing real-data specifications.** Some calendar/design work remains; do not generate replacement business observations.
- **22 preserve observed components and permit simulation only for missing steps.**
- **18 lack dedicated service data and are conditional-simulation candidates.** This is not a claim that18new tests are complete.
- **7 require facts/definitions first.** Actual legal decisions, Watch List actions, dependencies and triggers cannot be manufactured as evidence.

The[56-chain ledger](SOURCE_PRIORITY_EN.md) and[CSV](results/source_priority_EN.csv) identify observed components, forbidden replacements and permitted assumptions.

## Three corrected runnable examples

| Chain/example | Real data held fixed | Missing quantities assumed | Checks |
|---|---|---|---|
| GSD auction funding | Actual September2026issue dates and37records totalling USD2.658trillion **offered supply** | Unknown award/clearing participation/netting conversion and cash availability/delay | Cash and unpaid-obligation conservation; dates and offered amounts unchanged |
| MBSD TBA ladder | Actual2026Q2 broad unsettled-guarantee notional, **USD562billion** | Undisclosed TBA share, maturity ladder and deferral | Stock conservation; broad total is not actual TBA-only stock |
| NSCC member concentration | Actual2026Q2 top-five position-share quarterly average **36.49%**, with peak **40.25%** separate | Compatible virtual member allocation and hypothetical add-on rule | Aggregate, rank and normalization constraints; no real identities inferred |

There are15scenarios with100paired paths each: **1,500runs and62,500scenario/trace records**; {tests}unit checks passed. The source policy rejects generation requests for observed fields and verifies unchanged frozen files.

Under the current stress assumptions, means are **USD{auction:,.2f}million** peak unpaid auction obligations, **{tba:.2f}%** peak overdue / assumed initial TBA stock, and **{concentration:.4f}normalized exposure units** for the hypothetical concentration add-on (total100, **not dollars**). These are not observed GSD shortfalls, actual TBA failure rates or actual NSCC calls. See[all scenarios](results/scenario_summary.csv).

## What this tests

**Preserve real observations → assume only missing quantities/ranges → enforce resource/stock/rank constraints → compare baseline, stress, mitigation and unrelated controls → report sensitivity to assumptions.**

This answers what would happen under explicit missing-link assumptions and checks implementation coherence. It cannot establish that a real historical event reached a business. A virtual member distribution is not an observed book; quarterly-average concentration is not a daily or quarter-end portfolio. Offered supply is not awarded supply or a GSD obligation. Original empirical tests, the real database and teammate scores are unchanged.

Conditional simulation is appropriate when facts are supported but an internal process is missing. Unconfirmed incidents, dependencies or legal triggers remain unconfirmed, rather than being filled with random event labels. Missing from collected data is not proof that public data are permanently unavailable.

[Frozen sources](inputs/observed_source_manifest.json) · [Field-level provenance](results/field_provenance.json) · [Assumptions](results/model_assumptions.json) · [Execution receipt](results/execution_receipt.json). Earlier131broad hypothetical scenarios remain historical implementation experiments, not the current gap-only coverage count.
'''
    # Only fixed prose replacements; never modify identifiers or paths.
    for a,b in [('across56chains','across 56 chains'),('The[','The ['),('and[','and ['),('September2026issue','September 2026 issue'),('and37records','and 37 records'),('USD2.658trillion','USD 2.658 trillion'),('Actual2026Q2','Actual 2026Q2'),('USD562billion','USD 562 billion'),('are15scenarios','are 15 scenarios'),('with100paired','with 100 paired'),('1,500runs','1,500 runs'),('and62,500scenario','and 62,500 scenario'),('}unit','} unit'),('total100','total 100'),('See[','See ['),('Earlier131broad','Earlier 131 broad')]:en=en.replace(a,b)
    en=en.replace(f'{tests}unit',f'{tests} unit').replace(f'USD{auction:,.2f}million',f'USD {auction:,.2f} million').replace(f'{concentration:.4f}normalized',f'{concentration:.4f} normalized')
    (ROOT/'RESULTS_CN.md').write_text(cn);(ROOT/'RESULTS_EN.md').write_text(en)
    print('Built corrected bilingual results for3missing-link examples.')

if __name__=='__main__':main()

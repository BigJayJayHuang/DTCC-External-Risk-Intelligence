"""Create and execute the reader-facing analysis notebook and Chinese guide."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import nbformat as nbf
import pandas as pd
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from nbconvert import HTMLExporter

from analyze import CHINESE_RISK_LABELS, RISK_FEATURES, RISK_LABELS, TARGET_LABELS

ROOT = Path(__file__).resolve().parents[1]


def markdown_table(df):
    columns = [str(c) for c in df.columns]
    result = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df.iterrows():
        result.append("| " + " | ".join(str(v).replace("|", "/") for v in row) + " |")
    return "\n".join(result)


def guide_and_dictionary(quality, summary, associations, models):
    dictionary = [
        ("vix_change_pct", "市场波动变化", "100 × (本季度 VIX 平均 / 上季度平均 − 1)", "%", "VIXCLS", "Clearing and Settlement Financial Risks / margin sensitivity proxy", "波动环境代理，不能代替 FICC 组合 VaR 或保证金不足标签"),
        ("rate_change_pp", "利率重新定价", "本季度末 10 年期美债收益率 − 上季度末收益率", "percentage points", "DGS10", "Clearing and Settlement Financial Risks / interest-rate exposure proxy", "利率上升不必然导致业务表现下降，个体头寸未知"),
        ("credit_change_index", "信用条件变化", "本季度 NFCICREDIT 平均 − 上季度平均", "index points", "NFCICREDIT", "Clearing and Settlement Financial Risks / credit conditions proxy", "全国信用环境代理，不能视作某会员违约概率"),
        ("funding_basis_max_bps", "资金市场压力代理", "同一日期 SOFR − EFFR，以基点计算，取季度最大值", "basis points", "SOFR and EFFR", "Clearing and Settlement Financial Risks / liquidity conditions proxy", "市场融资利差代理，不能视作 FICC 自身流动性缺口"),
        ("fed_regulatory_announcements", "监管公告活动", "官方档案中 bcreg + enforcement 公告篇数", "headlines per quarter", "Federal Reserve press archives", "Legal and Regulatory Compliance / external communication proxy", "包含与 DTCC 无直接关系的公告，数量不是严重度、合规成本或已确认事件数"),
        ("fed_monetary_announcements", "货币政策公告活动", "官方档案中 monetary 公告篇数", "headlines per quarter", "Federal Reserve press archives", "Strategic / external policy communication proxy", "包含政策与设施公告，不能解释为加息次数或政策收紧强度"),
    ]
    pd.DataFrame(dictionary, columns=["feature", "名称", "definition", "units", "source", "taxonomy_related_scope", "interpretation_limit"]).to_csv(ROOT / "data/risk_proxy_dictionary.csv", index=False)
    business_definitions = [
        ("revenue_usd", "Total revenues", "reported quarter or full year minus nine-month YTD", "USD"),
        ("expenses_usd", "Total expenses", "reported quarter or full year minus nine-month YTD", "USD"),
        ("operating_income_usd", "Total operating income", "revenue minus operating expenses, not net income", "USD"),
        ("net_income_usd", "Net income / loss", "includes non-operating items and taxes", "USD"),
        ("operating_margin_pct", "Operating profit margin", "100 × operating_income / revenue", "percent"),
        ("net_margin_pct", "Net profit margin", "100 × net_income / revenue", "percent"),
        ("revenue_growth_pct", "Quarterly revenue growth", "100 × (revenue[q] / revenue[q−1] − 1)", "percent QoQ"),
        ("operating_margin_change_pp", "Quarterly operating margin change", "operating_margin_pct[q] − operating_margin_pct[q−1]", "percentage points"),
        ("net_margin_change_pp", "Quarterly net margin change", "net_margin_pct[q] − net_margin_pct[q−1]", "percentage points"),
        ("daily_notional_growth_pct", "Quarterly daily clearing notional growth", "100 × (daily_notional[q] / daily_notional[q−1] − 1)", "percent QoQ"),
        ("daily_sides_growth_pct", "Quarterly daily clearing sides growth", "100 × (daily_sides[q] / daily_sides[q−1] − 1)", "percent QoQ"),
        ("target_lag1", "Previous quarter of the same target", "only this control is median-imputed within each training fold, with missingness indicator", "same unit as target"),
    ]
    pd.DataFrame(business_definitions, columns=["field", "meaning", "calculation", "units"]).to_csv(ROOT / "data/business_metric_dictionary.csv", index=False)
    correlations = associations.sort_values("abs_spearman", ascending=False).head(6)
    labels = {"revenue_growth_pct": "收入环比增长", "operating_margin_change_pp": "营业利润率环比变化",
              "net_margin_change_pp": "净利润率环比变化", "daily_notional_growth_pct": "日均清算金额环比增长", "daily_sides_growth_pct": "日均清算 sides 环比增长"}
    leaders = pd.DataFrame([{"业务口径": r.entity, "业务指标": labels[r.metric], "风险代理": CHINESE_RISK_LABELS[r.risk_feature],
                             "季度数": r.n_quarters, "Spearman ρ": f"{r.spearman_rho:+.3f}", "Pearson r": f"{r.pearson_r:+.3f}"}
                            for _, r in correlations.iterrows()])
    result_table = pd.DataFrame([{"业务口径": r.entity, "业务指标": labels[r.metric], "训练/测试季度": f"{r.train_n}/{r.test_n}",
                                "测试 MAE": f"{r.test_mae:.2f}", "加入风险后误差减少": f"{r.mae_improvement_vs_controls_pct:+.1f}%"}
                               for _, r in models[models.model == "controls_plus_risks"].iterrows()])
    report = f"""# 风险类型与业务指标关联分析

数据采集日期：2026-10-05。业务资料最晚为 2026Q2。此分析回答‘不同类型风险环境与业务指标怎样一起变化’。

已完成 6 个风险代理 × 13 个业务指标序列，共 78 组关联分析，并训练 13 组 Ridge 模型，与季度规律和上一季指标的基线比较。
目前观察到一些同向或反向关系，但没有一组通过探索性的 5% 多重比较检验。13 个模型中，{summary['risk_models_beating_controls_on_test_mae']} 个加入风险后留出期 MAE 较小。测试期只有 2–4 个季度，尚不能证明模型具有稳定解释能力。

## 主要观察

{markdown_table(leaders)}

Spearman ρ 比较排序上的同向关系，Pearson r 比较线性关系。正值表示风险代理较高时业务变化通常也较高，负值表示通常较低。相关系数不是风险概率，也不是因果影响比例。

GSD 清算数量增长与波动变化的同向关系值得进一步核实。FICC 收入增长与融资利差的相关性受 2020 年影响：排除 2020 年后，Pearson r 从约 0.50 降至约 0.22。清算量或收入增加，也可能伴随更高的工作负荷和风险暴露，不能据此判断清算更安全。

收入还受收费政策、会员返还和一次性回扣影响，这些并未被模型单独控制。例如 NSCC 2021 年报告披露当年回扣 7,500 万美元，FICC 2020 年报告披露 2019 年一次性回扣 2,600 万美元（两份年报的物理第 10 页）。因此不能把收入波动全部归因于外部风险。

## 本次使用了哪些数据

- 65 份 FICC、NSCC、DTC 财务报告，提取 {quality['business_quarter_rows']} 个公司季度记录。FICC 包含 2019Q4–2026Q2 的 27 季，DTC 为 25 季，NSCC 为 23 季。
- FICC/GSD、FICC/MBSD 的 2020Q4–2026Q2 活动数据，共 23 个季度。sides 是交易方数口径，不等于交易笔数；daily notional 是日均清算名义金额，不是收入。
- 6 组 FRED 风险序列，共 {quality['risk_observations']:,} 个日期/序列记录（含节假日缺失值）。VIX、国债收益率和融资利率为日频，信用条件为周频。
- 2019–2026 年美联储官方档案中 {quality['historical_fed_headlines']:,} 条有效公告标题，加上原来的 75 条新闻，去重后保留 {quality['all_unique_news_documents']:,} 份新闻证据。历史模型的公告数量只使用美联储这一来源。

公司财务口径覆盖 FICC，以及与 ECS 有关的 NSCC 和 DTC。NSCC 还包含财富管理等活动，DTC 还包含资产服务等活动，两者均不是 ECS 的独立分部业绩。其余八条 kickoff 业务线没有足够的历史量化数据，本次未给它们编造结果。

## 风险指标的含义

{markdown_table(pd.DataFrame([{'风险代理': r[1], '计算': r[2], '单位': r[3]} for r in dictionary]))}

市场波动、利率、信用和资金条件是外部金融环境代理。它们可与项目分类中的清算与结算金融风险关联，但不能代替会员头寸、保证金覆盖、违约或流动性缺口数据。
监管/货币政策公告仅衡量沟通活动，未判断公告方向、相关性或严重程度。新闻仍保留未审核状态，模型没有把关键词候选分类当作正确风险标签。

## 处理了哪些数据问题

- 财务报告原始金额为美元千元，统一换成美元。三个月与累计六/九个月分开保存。Q4 在必要时用全年减前三季度累计得到，保留计算式、文件、页码和来源链接。
- 164 次直接季度值与累计推导值核对，最大差异为 1,000 美元（原始千元精度），没有超过该精度的冲突。
- DTC 2022Q4、NSCC 2020Q3/2020Q4/2025Q4 缺少可恢复的数据，保留缺失。环比和上一季控制变量先补全日历索引，避免把跨两个季度的变化误当成环比。
- 2021Q3 GSD/MBSD 的 XLSX 金额未按美元填入。对应 PDF 确认其数值为美元百万，已按原始单位恢复并记录证据。
- 2022Q3 GSD/MBSD 金额在 XLSX 和 PDF 中均出现无法确认的数量级问题，金额观察被排除。因此 2022Q3/2022Q4 的金额环比缺失，不影响 sides 数量序列。
- 2024Q4 缺少 XLSX，从 PDF 第 23 页恢复 GSD/MBSD 数据；金额保留美元百万的原始取整精度。
- NSCC 的 OTC/Exchange 说明随历史时期变化，保留两类原始数据并排除清算活动建模，没有相加。
- PQD 中重复披露的全年财务数、滚动 12 个月事故数均未当作独立季度目标。

## 机器学习如何检验关联

每个公司/指标单独建模，以季度为独立时间样本，不把多个公司同一季度当成新增独立时间观察。
业务目标为收入环比增长、营业利润率变化和净利润率变化；GSD/MBSD 另外研究日均清算金额与 sides 的环比增长。

模型是带正则化的线性回归 Ridge，适合样本少、风险指标可能互相关联的情形。
‘基线’包含季度规律和上一季业务变化，‘加入风险’在基线基础上加入六项风险代理。
只对缺失的上一季控制变量使用训练集的中位数，并加缺失标记；真实业务目标和风险观察不填造。

训练最晚到 2025Q2。在训练期内部，用四组按日历前后排列的验证窗口挑选正则化强度（1、10、100）。留出 2025Q3–2026Q2 做最终比较。标准化和中位数只在各次训练数据上计算。

{markdown_table(result_table)}

MAE 是平均绝对误差。收入和清算量目标以‘增长率百分点’读误差，利润率变化以‘利润率百分点’读误差。‘加入风险后误差减少’为正表示改善，为负表示误差增大，不能跨不同单位直接比较 MAE。
NSCC 仅 2025Q3、2026Q2 两个留出季度可计算环比，相关测试尤其薄弱。

描述性关联使用全部可用季度；测试期没有参与模型参数或超参数选择。统计表另列 95% 的四季度成块重采样区间、季度/趋势调整后的相关性、去掉某一年后的敏感性及探索性的循环时间平移检验。
循环平移检验依赖时间稳定性，而这几年经历制度和市场变化，因此 p/q 值只能作探索性参考；重采样区间也不是因果区间或经过多重比较调整的区间。

## 目前能用于项目的结论

可以将 GSD 活动与市场波动、FICC 收入与资金条件的关系列为待审核的业务关联线索。不能输出‘某条新闻导致业务损失多少’、‘某业务风险概率为多少’或全部十条业务线的风险评分。
数据为今天下载的历史最新版本，信用条件历史值可能修订；业务比较列也可能是后期披露。因此这里做的是历史同季度关联实验，尚未验证真正按当时已知信息运行的预测。

下一步最有价值的数据是：逐事件的业务相关性和风险分类人工审核、明确的生效日期/严重程度，以及业务月度或周度清算失败、保证金需求、流动性缺口、系统中断、监管整改成本等目标。用真实日期保留未知项，不把没有采集到的信息记成‘没有风险’。历史季度财务无法支撑每周风险模型。

## 打开结果与重跑

- `Risk_Business_Associations.ipynb`：已执行的完整分析，含图和结果。
- `Risk_Business_Associations.html`：无需安装 Python 即可打开的同一份 notebook 预览。
- `results/risk_business_associations.csv`：78 组关联、季度数、不确定性和敏感性。
- `results/model_comparison.csv` 与 `results/holdout_predictions.csv`：模型比较及逐季度实际值/估计值。
- `data/business_metric_provenance.csv`：每个财务值的来源和推导过程。
- `data/risk_proxy_dictionary.csv`：六类风险代理定义与解释边界。
- `raw/`：使用的原始公开报告、市场数据和公告档案。

Python 3.12 环境，在本文件夹中执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/prepare_data.py
.venv/bin/python src/analyze.py
.venv/bin/python src/build_delivery.py
.venv/bin/python src/validate_delivery.py
```

这些命令用本包的已采集快照重算，不会自动把未来新数据拼入历史实验。模型 `.joblib` 仅加载可信的本包文件。所有工作在本地完成，未创建 DevX 云资源。

## 来源与归属

财务/PQD 原始资料：[DTCC Financial Statements](https://www.dtcc.com/legal/financial-statements)、[DTCC Policy and Compliance](https://www.dtcc.com/legal/policy-and-compliance)。具体下载 URL 和文件哈希在原始来源清单中。

- CBOE, CBOE Volatility Index: VIX [VIXCLS]，从 [FRED](https://fred.stlouisfed.org/series/VIXCLS) 取得。
- Board of Governors of the Federal Reserve System (US)，Market Yield on U.S. Treasury Securities at 10-Year [DGS10] / 2-Year [DGS2]，从 [FRED DGS10](https://fred.stlouisfed.org/series/DGS10)、[FRED DGS2](https://fred.stlouisfed.org/series/DGS2) 取得。
- Federal Reserve Bank of New York，Secured Overnight Financing Rate [SOFR]、Effective Federal Funds Rate [EFFR]，从 [FRED SOFR](https://fred.stlouisfed.org/series/SOFR)、[FRED EFFR](https://fred.stlouisfed.org/series/EFFR) 取得。
- Federal Reserve Bank of Chicago，Chicago Fed National Financial Conditions Credit Subindex [NFCICREDIT]，从 [FRED](https://fred.stlouisfed.org/series/NFCICREDIT) 取得。上述 FRED 来源均经 Federal Reserve Bank of St. Louis 分发，采集日期 2026-10-05。
- Board of Governors of the Federal Reserve System，[官方历史公告](https://www.federalreserve.gov/newsevents/pressreleases.htm)，采集日期 2026-10-05。标题用于数量统计，未将其解释为全部真实事件或 DTCC 专属风险。
- 方法：[scikit-learn 数据泄漏指导](https://scikit-learn.org/stable/common_pitfalls.html)、[Ridge 文档](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)。

本包为私人学术分析交付；公开来源仍保留其归属和许可要求，未进行公开发布。
"""
    (ROOT / "分析结果与使用说明.md").write_text(report)


def build_notebook(quality, summary, associations, metrics):
    cells = []
    md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    cells.append(md("# 风险与业务指标关联分析\n# Risk types and business metric associations\n\nPublic-source Capstone experiment. Collected **2026-10-05**. Business reports through **2026Q2**."))
    gsd = associations[(associations.entity == "FICC/GSD") & (associations.metric == "daily_sides_growth_pct") & (associations.risk_feature == "vix_change_pct")].iloc[0]
    ficc = associations[(associations.entity == "FICC") & (associations.metric == "revenue_growth_pct") & (associations.risk_feature == "funding_basis_max_bps")].iloc[0]
    cells.append(md(f"""## tl;dr

完成 **6 个风险代理 × 13 个业务指标序列 = 78 组关联**和 **13 组 Ridge 机器学习比较**。

- GSD 清算 sides 环比增长与市场波动变化：Spearman ρ = **{gsd.spearman_rho:+.3f}**，n = **{gsd.n_quarters}**。
- FICC 收入环比增长与资金利差代理：Spearman ρ = **{ficc.spearman_rho:+.3f}**，n = **{ficc.n_quarters}**。排除 2020 年后，Pearson r 从 **{ficc.pearson_r:.3f}** 降至 **{ficc.excluding_2020_pearson_r:.3f}**。
- **0/78** 通过探索性的 5% FDR 多重比较检验。测试期 2025Q3–2026Q2，仅 **{summary['risk_models_beating_controls_on_test_mae']}/13** 个模型加入风险后误差较小，尚无稳定有效性的证据。

这些是待核实的关联线索。它们不代表风险概率、因果损失或清算安全评价。收入也受收费/返还/回扣影响，当前模型尚未单独控制这些业务因素。只覆盖 FICC 和与 ECS 有关的 NSCC/DTC 法律实体，无法替代全部十条业务线的分析。"""))
    cells.append(md("""## Context & Methods

用户目标：**不同类型 risk 和业务指标的关联**。
金融风险条件使用 VIX、国债收益率、Chicago Fed 信用条件、SOFR/EFFR 资金利差；监管与货币政策使用美联储公告数量。

### Key Assumptions

1. 每个季度是一个时间观察，各实体单独分析。用环比变化缓解水平趋势伪相关，并保留季度/趋势调整的相关性作敏感性比较。
2. 财务源金额为美元千元，转成美元。Q4 必要时用全年减九个月累计；环比先对齐完整季度日历。
3. 公告计数是沟通活动，并非已确认的风险事件数、严重程度或政策收紧标签。
4. 当前版本历史数据可用于回溯关联，尚不是按当时已知信息的预测。未标注新闻不能用于训练真实风险严重度模型。
5. 基线 = 上一季业务变化 + 季节控制；增量模型再加入六个风险代理。Ridge 强度在训练期按日历验证，标准化和中位数填补均只拟合训练数据。业务收费、返还、回扣和结构变化尚未单独控制。
6. 只对缺失的上一季控制变量填补并加标记；缺失的业务目标或风险观察不补造。2022Q3 有疑问的 GSD/MBSD 清算金额被排除。

每项风险的定义与口径边界见下表。"""))
    cells.append(md("### 1. Setup / 载入分析环境"))
    cells.append(code("""from pathlib import Path
import sys, json, importlib.metadata
import numpy as np
import pandas as pd
from IPython.display import display
import matplotlib.pyplot as plt

ROOT = Path.cwd()
if not (ROOT / 'src' / 'analyze.py').exists():
    ROOT = ROOT / 'risk_business_ml'
assert (ROOT / 'src' / 'analyze.py').exists(), 'Open this notebook from its extracted project directory.'
sys.path.insert(0, str(ROOT / 'src'))
from analyze import association_analysis, fit_models, RISK_FEATURES
from presentation import correlation_heatmap, association_uncertainty, model_comparison, ficc_holdout, source_coverage, scatter_examples
get_ipython().run_line_magic('matplotlib', 'inline')
pd.set_option('display.max_colwidth', 55)
pd.set_option('display.precision', 3)
display(pd.DataFrame({'package': ['Python', 'numpy', 'pandas', 'scikit-learn'],
                     'version': [sys.version.split()[0], *[importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scikit-learn']]]}))"""))
    cells.append(code("""risk_definitions = pd.read_csv(ROOT / 'data/risk_proxy_dictionary.csv')
display(risk_definitions[['feature', '名称', 'definition', 'units']])"""))
    cells.append(md("""## Data

使用 **65** 份财务报告、**22** 个 PQD XLSX 及用于核对单位/恢复缺失季度的 PDF；保留原始文件、来源链接、文件哈希及页码。
风险数据为 **6** 组历史市场序列与 **1,206** 个美联储历史公告标题。原来的 **75** 条新闻仍为未审核证据，因历史覆盖有限，没有拼成假定完整的季度计数。

### 2. Load and verify prepared inputs / 数据覆盖"""))
    cells.append(code("""quality = json.loads((ROOT / 'data/data_quality_summary.json').read_text())
financial = pd.read_csv(ROOT / 'data/business_quarterly_financials.csv')
panel = pd.read_csv(ROOT / 'data/analysis_panel.csv')
assert not financial.duplicated(['entity', 'quarter']).any()
assert not panel.duplicated(['entity', 'metric', 'quarter']).any()
display(pd.DataFrame(quality['financial_coverage']))
display(panel.groupby(['entity', 'metric']).target.agg(['count', 'min', 'max']).reset_index())"""))
    cells.append(code("""fig = source_coverage(financial)
display(fig)
plt.close(fig)"""))
    cells.append(md("NSCC 还有财富管理等活动，DTC 还有资产服务等活动，图中金额均为法律实体财务口径。缺失季度以断线表示；业务金额没有向前填充。"))
    cells.append(md("### 3. Inspect source issues / 单位核对和缺失处理"))
    cells.append(code("""issues = pd.DataFrame(json.loads((ROOT / 'data/pqd_source_quality_issues.json').read_text()))
display(issues[['quarter', 'division', 'original_xlsx_value', 'pdf_value_in_usd', 'action']])
reconciliation = pd.read_csv(ROOT / 'data/financial_reconciliations.csv')
assert reconciliation.difference_usd.abs().max() <= 1000
display(pd.DataFrame({'check': ['Financial three-month vs cumulative reconciliations', 'Largest rounding difference (USD)'],
                      'value': [len(reconciliation), reconciliation.difference_usd.abs().max()]}))"""))
    cells.append(md("2021Q3 根据 PDF 的美元百万单位恢复 XLSX 金额；2022Q3 两个格式仍无法相互确认，金额被排除。2024Q4 用原始 PDF 取整金额补齐。PQD 的全年收入/利润、滚动 12 个月事故数没有当作季度目标。"))
    cells.append(md("""## Results

### 4. Recompute associations / 重新计算关联

每个公司/指标分别比较同季度风险与业务变化。报告 Spearman 与 Pearson，95% 的四季度成块重采样区间（2,000 次），删除某一年后的敏感性，以及季度/趋势调整后的 Pearson。
循环时间平移检验尽量保留风险序列的时间结构，但稳定性假设并不保证成立。p/q 值为探索性参考；没有通过检验也不等于证明不存在关联。"""))
    cells.append(code("""associations = association_analysis(panel)
assert len(associations) == 78
leaders = associations.sort_values('abs_spearman', ascending=False).head(6)
display(leaders[['entity', 'metric', 'risk_label', 'n_quarters', 'spearman_rho', 'pearson_r',
                 'season_trend_adjusted_pearson_r', 'fdr_q_exploratory']])"""))
    cells.append(code("""fig = correlation_heatmap(associations)
display(fig)
plt.close(fig)"""))
    cells.append(md("这张图显示关联的方向和程度，不是损失热力图或风险评分。数量增长可能意味着更多清算活动，也可能增加运营负荷。所有 78 项比较均没有通过探索性 FDR 5%。"))
    cells.append(code("""fig = association_uncertainty(associations)
display(fig)
plt.close(fig)"""))
    cells.append(md("上图按 Spearman 的绝对值选出六项，仅作描述性展示。区间对应 Pearson，未对选取或多重比较作调整，不能将没有跨零的区间当成确定影响。"))
    cells.append(code("""fig = scatter_examples(panel)
display(fig)
plt.close(fig)"""))
    cells.append(md("每个点代表一个季度。资金利差与收入的相关性受 2020 年影响较大；资金利差本身也不能代替 FICC 的流动性缺口。NSCC 2021 年回扣为 7,500 万美元，FICC 披露 2019 年一次性回扣为 2,600 万美元（相应年报物理第 10 页），说明收入还受业务收费/返还政策影响。"))
    cells.append(md("""### 5. Refit ML models / 重新训练机器学习模型

训练截止 **2025Q2**；内部验证窗口为 2023Q3–Q4、2024Q1–Q2、2024Q3–Q4、2025Q1–Q2。每次验证都只用更早的季度训练。
最终留出 **2025Q3–2026Q2**。NSCC 只有 **2025Q3、2026Q2** 两个季度可计算环比；未补造缺失收入。
留出期没有参与超参数挑选。这里评估的是历史同季度映射；某季度的风险值输入同季度业务变化，不是下一季度预测。"""))
    cells.append(code("""models = fit_models(panel)
risk_models = models[models.model == 'controls_plus_risks']
display(risk_models[['entity', 'metric', 'train_n', 'test_n', 'cv_selected_alpha',
                     'test_mae', 'test_r2', 'mae_improvement_vs_controls_pct']])
print('Models with lower test MAE after adding risks:', int((risk_models.mae_improvement_vs_controls_pct > 0).sum()), '/', len(risk_models))"""))
    cells.append(code("""fig = model_comparison(models)
display(fig)
plt.close(fig)"""))
    cells.append(md("正值表示加入风险后误差较小，负值表示误差增大。改善主要见于部分 FICC 清算活动序列，且测试季度很少；不能据此声称模型稳定优于基线。利润率和增长率目标单位不同，MAE 不应跨目标直接相加。"))
    cells.append(code("""predictions = pd.read_csv(ROOT / 'results/holdout_predictions.csv')
fig = ficc_holdout(predictions)
display(fig)
plt.close(fig)"""))
    cells.append(md("### 6. Inspect conditional coefficients / 控制其他变量后的系数"))
    cells.append(code("""coefficients = pd.read_csv(ROOT / 'results/ridge_conditional_coefficients.csv')
ficc_revenue_coefficients = coefficients[(coefficients.entity == 'FICC') &
                                       (coefficients.metric == 'revenue_growth_pct') &
                                       (coefficients.feature_kind == 'risk_proxy')]
display(ficc_revenue_coefficients[['feature', 'conditional_coefficient_per_training_sd',
                                   'coefficient_per_raw_unit', 'selected_alpha']])"""))
    cells.append(md("系数表示控制其他变量后，风险代理提高一个训练期标准差时，模型映射的业务变化增量。正则化会缩小系数。样本很少、变量彼此相关，系数不是因果影响，也不是风险概率。"))
    cells.append(md("""## Takeaways

1. 已建立可重跑的数据整理、关联分析和 Ridge 训练流程，原始公开证据和口径问题均保留。
2. GSD 活动与波动变化、FICC 收入与融资条件可作为人工复核的线索。多数模型加入风险后没有改善，当前证据不足以输出可信的风险损失或评分。
3. 月度/周度机器学习需要同频业务指标；当前季度财务不能制造更多独立样本。网络安全、业务连续性、第三方、数据管理和运营事件需要真实事件审核与业务结果标签。
4. 其余八条业务线和 ECS 独立分部仍缺少目标数据。建议获取业务相关性、严重程度、生效日期及清算失败/保证金/流动性/中断等更直接的风险目标。

完整字段与来源在 `data/`、`raw/` 和《分析结果与使用说明》中。此次所有采集和计算在本地完成。"""))
    cells.append(md("""### Source attribution and methodology

Collected 2026-10-05. [DTCC Financial Statements](https://www.dtcc.com/legal/financial-statements), [DTCC Policy and Compliance](https://www.dtcc.com/legal/policy-and-compliance).

FRED distributes these original providers' series: CBOE [VIXCLS](https://fred.stlouisfed.org/series/VIXCLS); Board of Governors of the Federal Reserve System [DGS10](https://fred.stlouisfed.org/series/DGS10) and [DGS2](https://fred.stlouisfed.org/series/DGS2); Federal Reserve Bank of New York [SOFR](https://fred.stlouisfed.org/series/SOFR) and [EFFR](https://fred.stlouisfed.org/series/EFFR); Federal Reserve Bank of Chicago [NFCICREDIT](https://fred.stlouisfed.org/series/NFCICREDIT). Retrieved from FRED, Federal Reserve Bank of St. Louis. Source ownership and citation requirements remain applicable.

Historical announcement counts: Board of Governors of the Federal Reserve System [press release archives](https://www.federalreserve.gov/newsevents/pressreleases.htm). Original multi-agency feed evidence remains unreviewed.

Implementation: [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html) and [data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html). Exact download URLs, hashes, dates, source files and PDF pages are preserved in the accompanying manifests."""))
    notebook = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3 (Capstone)", "language": "python", "name": "python3"},
                                                      "language_info": {"name": "python", "version": "3.12"}})
    nbf.validate(notebook)
    path = ROOT / "Risk_Business_Associations.ipynb"
    nbf.write(notebook, path)
    # A temporary explicit kernel spec ensures a fresh kernel uses this exact
    # interpreter, without registering anything in the user's global settings.
    with tempfile.TemporaryDirectory(prefix="capstone-kernel-") as kernel_dir:
        spec = Path(kernel_dir) / "capstone"
        spec.mkdir()
        (spec / "kernel.json").write_text(json.dumps({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                                                       "display_name": "Capstone analysis", "language": "python"}))
        manager = KernelManager(kernel_name="capstone", ip="127.0.0.1", kernel_spec_manager=KernelSpecManager(kernel_dirs=[kernel_dir]))
        for cache_path in [".cache/matplotlib", ".cache/ipython", ".cache/jupyter"]:
            (ROOT / cache_path).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
        os.environ.setdefault("IPYTHONDIR", str(ROOT / ".cache/ipython"))
        os.environ.setdefault("JUPYTER_RUNTIME_DIR", str(ROOT / ".cache/jupyter"))
        client = NotebookClient(notebook, km=manager, timeout=180, startup_timeout=30, resources={"metadata": {"path": str(ROOT)}})
        try:
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
    nbf.validate(notebook)
    nbf.write(notebook, path)
    exporter = HTMLExporter(template_name="lab")
    body, _ = exporter.from_notebook_node(notebook)
    (ROOT / "Risk_Business_Associations.html").write_text(body)
    print(json.dumps({"notebook": str(path), "executed_cells": sum(c.cell_type == "code" for c in notebook.cells),
                      "figure_outputs": sum(any(m in o.get("data", {}) for m in ["image/png", "image/svg+xml"])
                                            for c in notebook.cells if c.cell_type == "code" for o in c.outputs),
                      "runtime_errors": sum(o.output_type == "error" for c in notebook.cells if c.cell_type == "code" for o in c.outputs)}, indent=2))


def main():
    quality = json.loads((ROOT / "data/data_quality_summary.json").read_text())
    summary = json.loads((ROOT / "results/analysis_summary.json").read_text())
    associations = pd.read_csv(ROOT / "results/risk_business_associations.csv")
    models = pd.read_csv(ROOT / "results/model_comparison.csv")
    guide_and_dictionary(quality, summary, associations, models)
    build_notebook(quality, summary, associations, models)


if __name__ == "__main__":
    main()

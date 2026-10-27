> **范围已更正（2026-10-27）：** 本文件是此前的广泛假设实验，不再作为“仅补缺失数据”的当前结果。已有真实数据的环节不使用生成值替代。请以[真实数据优先修正版](../synthetic_data_scope_revision_2026_10_27/README.md)及56条逐环节清单为准；原数值留作历史程序实验。

# 扩展传导链情景模拟：中文结果

**这是合成数据的机制实验，不是实际事故检验、官方风险模型或机器学习验证。** 本轮新增 **19个机制原型、20条目录链的部分机制覆盖、102种预设情景**，每种100次配对运行，共10,200组运行、298,200条模拟记录。随机种子20261027；批次`SIM2_a980a9e441f61837`。

加上[前轮DTC/EPN/TBA原型](../synthetic_chain_simulations_2026_10_27/README.md)，共 **22个机制原型、131种情景**。56条v3目录链中，**24条有部分机制模拟，另2条只有通用故障背景，30条尚未建立专属模拟**。链的覆盖数量不能当作完整验证数量；本分支没有任何链被标记为完整验证。

## 新增了什么

- 保证金与流动性：GSD、MBSD、NSCC分别建模；区分VM现金流、保证金存量、集中度附加要求和SLD；交叉保证金只展示抵销风险的假设机制。
- 违约与资金：分别展示GSD自有资源和假设剩余损失分配、NSCC多空平仓、GCF双重到期门槛、拍卖发行日资金集中、DTC与NSCC各自的结算银行门槛。
- 服务操作：MMI资金确认、ACATS转户量、Fund/SERV总申赎处理量、登记确认、特定证券chill/lock、DTC加拿大链路和NSCC国际链路分别建模。

## 给定假设下的结果

以下每行使用自身的业务指标和参数，不能按数值大小横向比较业务风险。缓解情景可能投入额外现金、资源、处理能力或改变组合；不是无成本收益。

| 链编号 | 本轮模拟的机制 | 基准均值 | 压力均值 | 缓解均值 | 单位 |
|---|---|---|---|---|---|
| FICC-GSD-01 | 国债价格变动及波动率假设改变所需保证金。 | 0.00 | 99.78 | 0.00 | USD million |
| FICC-MBSD-01 | 假设MBS因子变动改变VM现金及所需保证金。 | 3.85 | 96.36 | 33.73 | USD million |
| ECS-NSCC-01 | 假设股价变动转为会员VM支付与收款。 | 3.78 | 60.49 | 21.17 | USD million |
| TEAM-ECS-01 | 假设波动率改变Clearing Fund要求及增量现金需求；与VM分列。 | 0.00 | 136.09 | 0.00 | USD million |
| ECS-NSCC-04 | 同一会员证券集中度改变假设保证金加收。 | 0.00 | 31.76 | 0.00 | USD million |
| ECS-NSCC-05 | 最大关联家族流动性敞口转为假设补充存款追缴及未覆盖缺口。 | 0.00 | 168.61 | 168.61 | USD million |
| FICC-GSD-09 | 国债和期货带符号敞口在假设相关性下改变组合风险及所需金额。 | 37.54 | 300.55 | 75.08 | USD million |
| FICC-GSD-06 | 违约后自有资源与剩余损失的假设分配 | 0.00 | 30.22 | 12.06 | USD million |
| ECS-NSCC-06 | 假设多空头寸在延迟平仓中的不利价格变化 | 0.00 | 7.81 | 3.96 | USD million |
| FICC-GSD-05 | 虚拟分配单位的现金与抵押品共同到期门槛 | 0.00 | 76.92 | 0.00 | USD million |
| FICC-GSD-10 | 已假设净额后的发行日现金义务集中 | 0.00 | 92.48 | 0.00 | USD million |
| ECS-DTC-02 | DTC专属虚拟银行映射与日终确认门槛 | 0.00 | 23.69 | 0.00 | USD million |
| ECS-NSCC-07 | NSCC专属虚拟银行映射与日终确认门槛 | 0.00 | 13.43 | 0.00 | USD million |
| ECS-DTC-01 | 假设IPA对发行人简称的融资确认门控，区分到期与发行指令。 | 0.00% | 24.07% | 0.00% | fraction_of_instructions |
| ECS-NSCC-08 | 券商退出引起的假设账户转移集中到达与处理队列。 | 0.00% | 37.89% | 0.00% | fraction_of_instructions |
| WIS-NSCC-02 | 分别生成申购赎回总订单，模拟处理能力与独立赎回预付资金约束。 | 0.00% | 42.49% | 0.00% | fraction_of_instructions |
| AssetSvc-DTC-02 | 证券存入必须通过假设的登记确认门控。 | 0.00% | 25.80% | 0.00% | fraction_of_instructions |
| AssetSvc-DTC-01 | 显式证券级存入冻结仅阻止存入，全面锁定阻止所模拟的存入与划转。 | 0.00% | 13.13% | 0.00% | fraction_of_instructions |
| ECS-DTC-04 | 单独生成DTC加拿大链接依赖及跨境指令中断。 | 0.00% | 29.60% | 0.40% | fraction_of_instructions |
| ECS-NSCC-12 | 另行生成境外机构链接依赖及NSCC跨境指令中断。 | 0.00% | 28.33% | 0.00% | fraction_of_instructions |

金额单位`USD million`为百万美元。比例以百分比展示；假设路径中发生的比例不是实际失败概率。所有均值来自预设模拟分布；均值区间可查[逐情景结果](results/scenario_summary.csv)。图中线段是路径的5%—95%分位范围，不是现实参数的置信区间。

图表：[保证金与流动性](figures/margin_liquidity.png) · [违约与资金](figures/default_funding.png) · [服务操作](figures/service_operations.png)。各面板单位／刻度独立，不用于业务风险排名。

SLD尤其要分开看：增加会员可缴现金改善收取情况和剩余缺口，不改变原先所需金额。

| SLD指标，百万美元 | 基准 | 压力 | 增加会员现金后 |
|---|---|---|---|
| 要求的SLD | 0.00 | 168.61 | 168.61 |
| 实际收取的模拟SLD | 0.00 | 63.46 | 168.61 |
| 模型中剩余流动性缺口 | 0.00 | 105.15 | 0.00 |

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

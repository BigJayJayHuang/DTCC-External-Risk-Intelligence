# DAS-05 转换窗口代理 V：研究结果

As of: 2026-11-17T12:24:21-05:00

已实现“距离下一次名义转换订单提交窗口的等待小时数”。这是公开规则推导的结构性代理，不是实际订单延迟、转换容量或内部缓冲。

当前名义等待：**0.0000 小时**；候选代理分档：**1/5**。0小时仅表示名义窗口开放，不表示服务正常或无风险。

从 2026-10-29 起重建 470 个小时样本、20 个固定08:00 ET日样本。最长样本等待为 57 小时；跨2026年秋季夏令时切换的周末比普通周末多1小时。

## 计算与分档

先按 America/New_York 找到下一次名义开窗时刻，再以UTC时刻相减。窗口暂按02:00含、18:00不含处理；关闭端点是保守实现假设。

| 等待小时 | 候选分档 |
|---|---|
| 0 | 1 |
| (0, 8] | 2 |
| (8, 24] | 3 |
| (24, 48] | 4 |
| >48 | 5 |

分档是透明的研究规则，尚未校准；不使用自身历史百分位，也不把序数分档当作损失概率。

## 情景演示，非真实事件

以下统一假设冲击S=3，且事件确实需要传统证券与代币形式之间的转换。示例不表示DTCC发生了事故，也不进入事件登记表或真实数据记录。

| Scenario | Time ET | Baseline wait (h) | Candidate V | Illustrative S×V index |
|---|---|---:|---:|---:|
| EXAMPLE-OPEN | 2026-11-13T17:00:00-05:00 | 0 | 1 | 3 |
| EXAMPLE-FRIDAY-CLOSED | 2026-11-13T19:00:00-05:00 | 55 | 5 | 15 |
| EXAMPLE-SUNDAY | 2026-11-15T08:00:00-05:00 | 18 | 3 | 9 |

## 结果边界

- API明确提及节假日拒单，但尚未取得适用于转换订单的日期表。因此以上均是名义周历结果，日历确认后的等待值保持为空；没有套用NYSE、联储或DTC结算假期。
- 已代币化资产的24/7转移与转换订单不同。只有需要转换的机制才可能使用此代理；本模块不自动判断新闻适用性。
- 实际系统状态、参与机构与证券资格、排队及完成时间未知。当前窗口内0小时不表示即时成交、结算或转换完成。
- 本轮使用当前文件重建规则，不声称历史信息时点已核实。2026-10-29以前不回填，不生成2020Q4–2026Q2的DAS运行历史。
- 季度表只是本季度部分样本描述，不能当作上一季度内部V。真实内部V、已接受代理V和正式风险分数均为空；没有改动final16或生产评分。
- 情景中的S和S×V是演示假设；不入真实观察数据库，不表示概率、损失、因果效应或经验验证。

后续检验需要授权订单/事件结果与正式服务日历，观察更长窗口等待是否对应更大的转换延迟或积压，同时控制实际故障、业务量及事件类型。

## Sources

- [DTCC DAS-001 notice](https://files.dtcc.com/download/assets/DAS-001/8a31d732d2d311f1a30ef632b7f70f6d)
- [Official API reference](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content)

Source hashes and policy provenance: `results/source_evidence.json`.
Data: `results/hourly_proxy.csv`, `results/daily_0800_et_proxy.csv`, `results/quarterly_descriptive_summary.csv`.
Hypothetical examples are separate: `results/hypothetical_scenarios.csv`.

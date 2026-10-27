# Real data first; simulate missing steps only / 真实数据优先，只模拟缺口

**本页替代此前“尽量扩展模拟覆盖”的工作范围。** 有真实数据的字段直接使用真实值；只有无法从已采集资料获得的环节才允许设置假设。真实检验不显著、样本少或未达门槛，不是改用生成数据的理由。

**This revision replaces the earlier broad simulation scope.** Observed data remain authoritative. Simulate only missing steps, never substitute generated values because a real test is weak or insignificant.

- [56条逐环节清单 / 56-chain source priority](SOURCE_PRIORITY_CN.md) · [English](SOURCE_PRIORITY_EN.md)
- [中文结果](RESULTS_CN.md) · [English results](RESULTS_EN.md)
- [中文逐链CSV](results/source_priority_CN.csv) · [English CSV](results/source_priority_EN.csv)

| Current route / 当前处理方式 | Chains / 链数 | Meaning / 含义 |
|---|---:|---|
| Real data only / 沿用真实数据 | 9 | Use existing real-data specifications; some calendar/design work remains. 保留真实实证规格，个别仍需日历或检验设计。 |
| Real plus missing steps / 真实＋缺口 | 22 | Keep observed inputs/results; conditional simulation only for missing fields or mechanisms. 只补缺失字段与机制。 |
| Missing service data / 缺专属数据 | 18 | Conditional scenario candidates, not18already completed new tests. 候选范围，不代表18条都已完成。 |
| Resolve facts/definitions / 先补事实与定义 | 7 | Do not generate actual legal decisions, dependencies, membership or triggers. 不随机生成事实、法律决定或真实触发。 |

These are source routes, not validation ratings. 全部是数据处理分类，不是“链已验证”的评级。

## What changed / 改了什么

The broad GSD/MBSD/NSCC market engines are retired from the active gap-testing scope: actual market signals, margin and VM outcomes already exist. Earlier pure-toy concentration, cross-margin, SLD, auction and TBA results must not replace their observed aggregates. The earlier files retain historical implementation results and carry a superseded-scope notice.

GSD、MBSD、NSCC宽泛市场模拟不再计入当前补缺检验；已有市场、保证金和VM数据直接保留。集中度、交叉保证金、SLD、拍卖和TBA也必须逐字段区分真实与缺失，不能整条链重新随机生成。

The corrected runnable examples bind actual source values first, then vary missing quantities only:

1. Actual Treasury issue dates/offered supply → assumed unobserved clearing/obligation share and cash → conditional funding gap.
2. Actual broad MBSD unsettled notional → assumed TBA share/maturity ladder/deferrals → conditional overdue stock.
3. Actual NSCC concentration aggregate → feasible unobserved member distributions → hypothetical add-on in normalized exposure units.

修正版示范先固定真实拍卖、MBSD总头寸及NSCC集中度，再分别改变未知的参与／净额比例、期限分布、会员分布与资源。它们不生成新的真实事件、真实会员名单或官方风控公式。

## Reproduce / 复现

```bash
python3 -m unittest discover -s tests -v
python3 src/build_scope.py
python3 src/run_gap_only.py
python3 src/audit_gap_sources.py
```

`inputs/observed/`contains immutable real-source snapshots. `source_policy.py`rejects requested generation of observed fields. Model outputs remain separate from the empirical database and original tests. EarlierZIP packages are frozen historical snapshots; the current scope is this folder.

`inputs/observed/`保存冻结真实输入；程序禁止生成或覆盖真实字段。结果与团队真实数据库和历史检验分开保存。之前的ZIP保留为历史快照，当前范围以本文件夹为准。

[独立来源与数值核查 / Independent source and arithmetic audit](results/independent_source_audit.json) · [最终检查 / Final checks](results/verification.json)

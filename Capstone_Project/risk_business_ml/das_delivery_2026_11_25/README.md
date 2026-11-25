# DAS public risk monitoring | DAS 公开风险监测

Open `DAS_Risk_Horizon.html` in a browser. The DAS tab opens on the November 25 weekly review. Use the snapshot selector to compare with November 17. The review adds a source-linked action list with suggested reviewers and closure criteria. FICC and ECS provide historical reference snapshots.

在浏览器打开 `DAS_Risk_Horizon.html`，可查看 11 月 25 日核查结果，或用快照选择器对照 11 月 17 日。页面列出跟进事项、建议核查角色和完成标准。FICC 和 ECS 标签页提供历史结果供参考。

[十条业务线影响分析](Weekly_Business_Line_Impact_CN.html)汇总 11 月 12–25 日的英伟达公告、市场波动、Anthropic IPO、DTC 登记系统和 Besu 版本变化。行情截至 11 月 24 日完整收盘。

| Card | Public evidence | Review output |
| --- | --- | --- |
| DAS-01 | DTCC launch announcement and two Besu publisher advisories | Check applicability to DTS. Deployment applicability remains unresolved. |
| DAS-04 | SEC staff terms and DTCC network announcements | Track the January 15, 2027 reporting milestone and planned H2 2027 Solana integration. |

The two monitoring cards carry evidence and review statuses. Formal DAS severity is unscored.

两张监测卡展示证据和核查状态，DAS 正式风险分数留空。

| Outside this release | Reason | 本版取舍 |
| --- | --- | --- |
| DAS-02 · LedgerScan reconciliation | The reviewed evidence describes the reconciliation process. Measuring the internal buffer requires actual breaks, backlog, and resolution times. | 保留账本对账传导链。现有公开证据无法量化真实差异和处理积压。 |
| DAS-03 · Wallet controls and sanctions screening | Public rules describe wallet registration and screening. Measuring controls requires evidence of actual coverage and screening outcomes. | 保留钱包和制裁筛查传导链。现有公开证据无法量化保护覆盖率和筛查结果。 |
| DAS-05 · Conversion and corporate action processing | Omitted from this release. | 本版跳过。 |

## Rebuild and verify

Run `python3 build_delivery.py` from this folder. All build inputs are included. `das_cards.json` contains the latest two DAS card records, and `data_receipt.json` records the input and output hashes. Both HTML files open offline. Source links require internet access.

- `inputs/viewer.html` and `inputs/risk_output.json` are the frozen viewer template and FICC/ECS historical output from [repository revision 28e3460](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/commit/28e346041b31e56cb3125398aa41a30c766454b4).
- `inputs/monitor_evidence.json` contains the public URLs, evidence window, reporting milestone and review states used in this release. [Reviewed DAS monitor snapshot](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/blob/84c856c892f0e5324e2283bb721b6bb0e5369a05/Capstone_Project/risk_business_ml/das_public_monitor_2026_11_17/results/monitor.json).
- `inputs/weekly_review.json` records the current DAS source checks and screening decisions. `inputs/recent_events.json` and `inputs/business_line_analysis.json` support the ten-line brief.

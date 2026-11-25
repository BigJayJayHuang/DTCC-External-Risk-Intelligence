# DAS public risk monitoring | DAS 公开风险监测

Open `DAS_Risk_Horizon.html` in a browser. The DAS tab opens by default, with two cards based on the November 9–17, 2026 evidence window. Select a card to see its transmission chain, supporting sources, and review action. FICC and ECS provide historical reference snapshots.

在浏览器打开 `DAS_Risk_Horizon.html`。默认显示 DAS 两张卡，证据窗口为 2026 年 11 月 9 日至 17 日。点开卡片可查看传导链、来源和核查动作。FICC 和 ECS 标签页提供历史结果供参考。

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

Run `python3 build_delivery.py` from this folder. All build inputs are included. `das_cards.json` contains the two card records, and `data_receipt.json` records the input and output hashes. The HTML opens offline. Source links require internet access.

- `inputs/viewer.html` and `inputs/risk_output.json` are the frozen viewer template and FICC/ECS historical output from [repository revision 28e3460](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/commit/28e346041b31e56cb3125398aa41a30c766454b4).
- `inputs/monitor_evidence.json` contains the public URLs, evidence window, reporting milestone and review states used in this release. [Reviewed DAS monitor snapshot](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/blob/84c856c892f0e5324e2283bb721b6bb0e5369a05/Capstone_Project/risk_business_ml/das_public_monitor_2026_11_17/results/monitor.json).

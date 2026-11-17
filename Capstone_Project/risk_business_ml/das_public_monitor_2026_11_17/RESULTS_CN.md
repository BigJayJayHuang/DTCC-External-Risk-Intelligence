# DAS 公开证据监测：实际运行结果

As of / 核验日：2026-11-17 · 2026-11-09–2026-11-17

本轮将五条研究链收窄为两个可运行的公开监测模块，并准备一个授权订单数据接口。输出待复核发现、未来变更观察、来源证据和报告日历；真实内部V与S×V分数继续为空。

## 实际发现

- [GHSA-hhgq-3gvc-4jhp](https://github.com/besu-eth/besu/security/advisories/GHSA-hhgq-3gvc-4jhp): 2026-11-10，Besu维护方发布安全公告，严重程度为 medium，影响版本 <= 26.10.1，修复版本 26.10.2。需要核对DTS实际版本与配置；尚未确认DAS事故。
- [GHSA-6pcq-hcgg-5q76](https://github.com/besu-eth/besu/security/advisories/GHSA-6pcq-hcgg-5q76): 2026-11-10，Besu维护方发布安全公告，严重程度为 medium，影响版本 <= 26.10.1，修复版本 26.10.2。需要核对DTS实际版本与配置；尚未确认DAS事故。
- [Solana](https://www.dtcc.com/press-releases/2026/dtcc-tokenization-service-to-connect-with-solana): 2027年下半年计划接入，放入未来变更观察，不计作当前生产网络故障暴露。

## 五条链的取舍

| ID | 内容 | 当前处理 | 最少仍需什么 |
|---|---|---|---|
| DAS-01 | 软件安全／基础设施事件 | 启用公开监测 | 实际Besu版本、共识配置、补丁与切换测试记录 |
| DAS-02 | 记录与对账 | 内部指标暂缓 | 对账差异、积压数量、处理能力及时间戳 |
| DAS-03 | 钱包与安全控制 | 内部指标暂缓 | 已注册钱包清单、密钥控制证明与筛查日志 |
| DAS-04 | 监管、资格与网络变更 | 启用公开监测 | 正式启动通知、应急转换能力与受影响头寸 |
| DAS-05 | 转换及公司行动处理 | 授权数据接口已准备 | 实际订单、完成日志、处理能力与公司行动结果 |

## 可计算的日历

- 2026Q4 SEC staff报告期限：**2027-01-15**，距核验日 59 天。提交情况未公开观察到，不能据此判定未提交。
- [SEC source / 监管文件](https://www.sec.gov/files/tm/no-action/dtc-nal-121125.pdf) — 监管宽限的精确到期日保留为空：须确认正式Preliminary Base Version启动及书面通知，不能用新闻日期推算。

## 砍掉的内容

- 不制作2020Q4起的DAS上线前季度模拟，不用模拟值填补内部V。
- 不把币价、Canton Coin交易量、泛NVD漏洞数或公共网页HTTP成功率充当DAS内部脆弱度。
- 不扫描未知Registered Wallet，不把合作方名单当成钱包或托管控制证明。
- 不强行做缺少业务结果变量的机器学习回归；不输出未经支持的风险分数。

## 授权数据接入

[Public API documentation](https://dtcc-da.com/api/tokenization-service/api-reference-guide/content). 公开API说明书已取得，但业务接口需要参与机构账号。本轮未请求业务访问权限，也未调用业务接口。已提供只有表头的CSV模板，收到授权真实导出后可计算去重订单数、状态分布与明确确认的完成耗时。这些是运行结果指标，并非内部缓冲V。

Current order input: `awaiting_authorized_data`

## 运行与证据

Sources retrieved: 12/12. Raw files, dates and SHA-256 hashes are in inputs/source_manifest.json. Findings remain review-only. No production event register or existing final16 scoring was modified.

公开文件已由现有AWS API解读；10条解读事实经过本地原文复核。API原始结果中的引用错误、资格边界及不受支持的到期日期已单独记录修订，不代表业务方签字或实证验证。

Stale API fact IDs (excluded until source review): []

Rebuild: `python3 src/build_monitor.py --as-of 2026-11-17 --window-start 2026-11-09`
Refresh public sources: `python3 src/collect_public.py` (network; no paid model call).
Read new documents through the existing AWS API: `python3 src/read_public_with_aws.py --invoke` (explicit manual call; cached attempt prevents accidental repeat).
Import: `python3 src/import_monitor_db.py` (portable SQLite; optional targeted existing-database import).

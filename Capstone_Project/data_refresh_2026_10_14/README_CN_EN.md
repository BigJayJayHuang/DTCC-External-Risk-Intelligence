# 十条业务线公开数据更新｜2026-10-14

本次新闻筛选区间为 **2026-10-07 至 2026-10-14**，即 10 月 6 日之后。已知发布时间换算为 America/New_York；只有来源日期的记录保留时区不确定标记。10 月 14 日是抓取时点内的部分日。抓取时间、新闻发布日期和数据报告期分别保存。

- 本期保存 **142 条**新闻、通知及监管文件记录。文档不等于独立事件。
- **73 条**有可提取原文，1 条保存官方公开表格；66 条 Federal Register 文件有完整 API 元数据，但网页原文受到自动访问限制；2 条其他原文下载被拒绝。
- 抓取 **19 个**市场序列，其中 **12 个**有本期观察，合计 **52 个非缺失数值**。两条旧货币基金周度序列停于 2021 年，未作为本期信号使用。
- 补充 FICC 日度活动 **28 个指标值**，并取得 GSD/MBSD 共用的月度成交历史，最新月份 **2026-09**。
- 新增整理：ECS/ITP 月度运营快照 **18 行**，ETF 参考名单 **6156 行**，RDS 公开周报 **8 份**，WIS 行业货币基金资产表 **36 行**。
- Asset Services 承销历史共 **188 个月 / 752 行**，最新为 **2026-08**。另提取并去重公开业务规模指标 **20 个**。

上述业务历史和快照是本次新取得的材料，报告期各异；不能把它们统称为 10 月的新业务结果。PQD 和官方财务目录仍到 **2026Q2**，旧季度样本和模型报告保留。本次只更新采集、处理和候选映射，未重新训练模型，也未生成新的业务风险分数。

## 每条业务分别需要什么

| 业务 | 公开信息与已取得的输入 | 关键内部指标缺口 |
|---|---|---|
| FICC | 回购/国债利率、交易失败、Sponsored 活动、GSD/MBSD 月度成交量、规则和 PQD | 最新保证金/资金覆盖仍依赖下一次季度披露 |
| ECS | 股市波动、ETF 名单、NSCC/DTC 处理量、净额化率和失败率快照 | 完整每月服务质量、积压与纯 ECS 财务 |
| RDS | EU/UK EMIR 周报、UK SFTR、TIW CDS 数据、报告规则和数据质量公告 | 拒绝/更正率、及时性、客户和辖区集中度 |
| WIS | 行业基金资产与资金流代理、基金/保险/私募规模快照、服务公告 | 分产品处理量、异常率、赎回积压和独立财务 |
| ITP | CTM/TradeSuite ID 量、确认与同日匹配率、ALERT、T+1 信息 | 连续历史异常率、时延、SSI 错误与客户集中度 |
| Asset Services | 月度发行笔数/金额、公司行动/税务通知、托管规模 | 公司行动履约、支付差错、对账与发行人集中度 |
| DAS | 证券代币化服务/规则公告、DTC 披露框架、外围数字资产环境 | 服务交易量、余额、转换/结算失败和链集中度 |
| DDA | 平台/互操作性公告、外部漏洞和云服务事件 | 平台可用性、API 延迟、修复时效和供应商暴露 |
| Data Services | 共用 ETF、承销、CDS、货币市场资料和数据质量公告 | 数据延迟、完整性、订阅留存和独立收入 |
| Consulting | 规则、期限、行业准备情况和咨询主题公告 | 项目积压、利用率、交付周期和项目利润率 |

## 共用数据如何避免重复

来源登记中的每个 URL 只有一个采集任务。一个来源可对应多个业务，关联保存于 `shared_source_business_mapping.csv`。新闻按规范化原文 URL 去重，文档与业务关系另存于 `news_business_links.csv`。网络传输失败的重试保留尝试记录，不因业务数量重复抓取。

例如：GSD 与 MBSD 的月度成交数据来自同一个 XML 文件；ECS 和 ITP 的运营指标共用 Equities by the Numbers；DAS 和 DDA 共用数字资产公告；RDS 与 Data Services 共用 CDS 与公开报告；WIS 与 Data Services 共用行业货币基金资产。相同 TIW 市场份额指标合并为一个事实并保留两个页面的证据。

DTC 资产数量在不同产品页面有 1.4M 与 1.44M 两种披露精度，分别保留来源和口径，不把它们加总。法律实体 NSCC/DTC 的收入、保证金不能直接分配给其下所有业务。

## 首先打开哪些文件

| 文件 | 内容 |
|---|---|
| `data/ten_business_data_requirements.csv` | 十条业务所需信息、脆弱度指标、来源和频率 |
| `data/shared_source_business_mapping.csv` | 数据源与业务的多对多关系 |
| `data/news_increment_2026_10_07_to_14.csv` / `.jsonl` | 本期文档，原始证据路径与候选标签 |
| `data/market_increment_2026_10_07_to_14.csv` | 本期市场观察，保留缺失值 |
| `data/market_observations_updated.csv` | 接续旧历史后的当前版本，适合后续研究 |
| `data/daily_market_signals_increment.csv` | 原有七个指标的日度监测值与历史门槛 |
| `data/ficc_daily_operations_increment.csv` | 本期回购指数、失败金额和 Sponsored 活动 |
| `data/ficc_gsd_mbsd_monthly_volumes.csv` | 共用来源提取的 GSD/MBSD 月度成交量 |
| `data/ecs_itp_monthly_operations_snapshot.csv` | 处理量、确认率、匹配率及失败率 |
| `data/asset_services_underwriting_monthly.csv` | 承销月度历史，按证券类别保存 |
| `data/rds_report_inventory.csv` | RDS 报告日期、地区和原文件索引 |
| `data/wis_industry_money_market_assets.csv` | 整体行业资产表，含基金/投资者层级 |
| `data/business_public_snapshot_metrics.csv` | 官方页面披露的业务规模，报告期与下限/估计标记 |
| `data/business_internal_data_gaps.csv` | 尚未公开取得的内部业务指标 |
| `data/source_and_content_gaps.csv` | 下载拒绝、原文缺口等实际问题 |
| `Public_Data_Refresh_Quality_Checks_CN.ipynb` | 已执行的证据、主键、日期、单位及关联检查 |
| `shared_public_data.sqlite3` | 一次保存事实，单独保存业务关联的共享数据库 |

## 复现与范围

采集器只使用公开 URL，没有登录内部系统或创建云资源。原始响应和 SHA-256 保存在 `raw/` 与 `source_manifest.json`；旧输入副本固定在 `inputs/prior/`。ICI 表格由公开网页读取后整理，其自动 HTML 下载返回 403，因此证据明确标为公开表格转录，而非成功下载 HTML。

在现有 Capstone 项目中可依次运行以下脚本。当前目录是 10 月 14 日的固定快照，同一 URL 的再次运行复用已保存响应，用于恢复/复现。以后更新应另建日期目录并更新来源窗口，不能用此缓存冒充新抓取。

```bash
risk_business_ml/.venv/bin/python data_refresh_2026_10_14/src/collect_public_data.py
risk_business_ml/.venv/bin/python data_refresh_2026_10_14/src/process_public_data.py
risk_business_ml/.venv/bin/python data_refresh_2026_10_14/src/build_business_plan.py
risk_business_ml/.venv/bin/python data_refresh_2026_10_14/src/execute_quality_notebook.py
```

需要 Python、pandas、numpy、BeautifulSoup、python-dateutil、openpyxl、pypdf、nbformat、nbclient、ipykernel 和 nbconvert；原项目的环境已具备这些依赖。采集使用系统 curl，无 API key。`process_public_data.py` 复用原有新闻清洗助手及旧输入，完整实时复现应在现有项目内运行。固定快照的质量检查可读取随包固定的旧输入。

## English handoff

This snapshot refreshes public news published after October 6 through the October 14 collection time and extends the collection plan to all ten kickoff business lines. Shared sources and documents are stored once, with business relationships maintained separately. Quantitative data include current market observations, FICC daily/monthly activity, ECS/ITP operations snapshots, RDS public repository reports, WIS industry fund assets, Asset Services underwriting history, and public business-scale measures.

Reporting periods are retained. PQD and financial statements remain at 2026Q2, while other sources have different lags. Public proxies do not establish DTCC exposure, causal effects, segment revenue, or calibrated risk. DAS, DDA and Consulting still lack complete public internal KPI histories. Earlier research outputs are unchanged; this update does not retrain models.

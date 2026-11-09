# DAS 与团队数据流程的衔接 / DAS alignment with the team pipeline

这份补充根据用户提供的三张截图在本地整理。用户选择不上传图片到 AWS；图片和图片文字均未再发送给 API。官方公开文件的 AWS 阅读是另一项已执行的工作。

This note uses the three user-supplied screenshots locally. The user declined AWS upload; neither the images nor an extracted substitute were sent to the API. The separate AWS reading of official public documents was completed earlier.

| 数据层 / Layer | 原有16卡 / Existing16 | 新增DAS5卡 / New DAS5 |
|---|---|---|
| 市场外部冲击S / Market shock S | 6张卡使用市场指标；新闻仍可能补充事件信号 / Six use market indicators; news may still supplement them | 不直接套用国债、回购或VIX指标；先论证与DTS流程的传导关系 / No automatic reuse of Treasury, repo or VIX signals |
| 新闻事件S / News/event S | 另外10张主要依赖事件；先筛选再复核 / Other ten mainly rely on event evidence | 监测已部署网络中断、钱包安全事件、资格/监管变化、转换窗口和公司行动事件；不是看到“crypto”就打分 / Service-specific events, not generic crypto headlines |
| PQD真实内部V / Observed PQD V | 6张使用PQD / Six use PQD | 尚未取得DAS对应季度内部缓冲数据 / DAS internal quarterly buffers unavailable |
| 真实公开代理V / Observed public-proxy V | 10张使用真实公开代理序列 / Ten use actual public proxy series | 可研究，但当前尚未取得并接受可靠的DAS专属代理序列；不能把外部冲击重复充作V / Candidates only; no accepted DAS-specific proxy series yet |
| 模拟内部V / Simulated internal V | 与前两层分开 / Separate from observations | 可以测试流程和参数；2020Q4–2026Q2属于上线前反事实，不能当历史实测 / Functional tests only; historical values would be counterfactual/prelaunch |

**DAS当前状态：** 5条候选链已有定义、保护性缓冲指标和数据索要清单。真实内部V缺失，公开代理V尚未获得可用序列，模拟V本批次没有生成。保留115个季度空值，不输出S×V风险排名。公开代理是否适用必须逐卡核对其是否覆盖DTS实际部署和业务暴露；泛化的网络漏洞数、币价或全市场波动不等于DAS内部脆弱度。

**Current DAS status:** Five candidate mechanisms, protective-buffer definitions and data requests are prepared. Internal V remains missing, no usable public-proxy V series has been accepted, and no simulated V was generated in this batch. The115 quarterly positions remain null; no S×V ranking is issued. Public proxies need deployment/exposure checks; generic vulnerability counts, crypto prices and broad market volatility are not automatically DAS internal vulnerability.

**新闻接口：** 最新Google新闻分支有47个查询、覆盖原有16卡，尚无DAS。未来DAS采集可沿用document_id、标题、发布时点、采集时点、原文URL/Google跳转URL、来源层级、正文范围及文本哈希等字段。必须先扩展可审核的卡片目录和分类schema，当前没有修改生产分类器或开启新的自动调用。

**News integration:** The latest Google-news branch has47 queries for the original16 cards and none for DAS. Reuse its document identity, publication/ingestion times, publisher/redirect URLs, source tier, content scope and text hashes. Extending the reviewable card catalog/schema is required before production DAS classification; this batch does not change the production classifier or enable unattended calls.

**运行状态核实：** [2026-11-09每日任务](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/actions/runs/42547021653)显示failure，但该次采集、验证和共享快照发布成功；最后一步因CFTC403及8个RDS接口404而报错。因此，不能直接说“从10/28起整个任务一直停止”。本次只核对了最新5个计划任务，未证明10/28以来全部情况。11月2–8日保留92条Google结果，是一周的实测记录，不是每周固定90条的保证。

**Runtime verification:** The linked latest run is red, but collection, validation and shared-snapshot publication succeeded; the final check reports CFTC403 and eight RDS404s. The whole collector therefore was not stopped in that run. Only the latest five scheduled runs were checked. The92 retained Google items for November2–8 are a measured one-week count, not a recurring quota.

[中文DAS汇总](README_CN.md) · [English DAS summary](README_EN.md) · [核实记录 / Live-check receipt](results/team_pipeline_live_checks.json)

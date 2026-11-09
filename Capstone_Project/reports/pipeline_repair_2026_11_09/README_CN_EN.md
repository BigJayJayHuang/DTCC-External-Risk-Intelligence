# 数据与新闻采集修复 / Data and news pipeline repair

核验日期 / Checked: **2026-11-09** · 分支 / Branch: `feat/news-source-repair-20261109`

## 中文

本轮处理三张截图中提出的数据更新、新闻证据和运行状态问题。截图仅在本地参考，未上传 AWS；本轮 AWS / 付费模型调用为 **0**。修复在独立审阅分支中，未合并 main，也未重新训练模型、修改历史评分、季度 V 或人工事件签字。

| 问题 | 已完成的处理 | 实际验证结果与限制 |
|---|---|---|
| 每日任务报红，被理解为全部停止更新 | 分开报告快照发布状态与数据源完整性；失败请求继续告警 | 核对的最新线上任务中，采集、验证、发布成功，最后的部分来源检查失败；这不能推出“10 月 28 日后全部停止” |
| CFTC 新闻源失效 | 根据官方停用 RSS 的说明，改为有发布日期的官方公告索引，保留同一个来源 ID | HTTP 200；37 条公告，最新发布日期 11 月 9 日。索引不是全文 |
| RDS 一个周报 404 导致其他周报被回滚 | 每期 CSV 独立写入；重试近期缺口；保留部分成功状态 | 8 个来源均取得 10 月 16、23、30 日文件；两份 UK SFTR 取得 11 月 6 日文件。6 份 EU/UK EMIR 最新文件仍为 404 |
| 房贷利率、成交量未接入日更评分输入 | 加入 FRED 房贷利率；评分读取器合并最新数据库记录；每日任务刷新当年 Cboe 文件并保留历史文件 | 房贷利率至 11 月 5 日；Cboe 至 11 月 6 日，新增 63 条场所—交易日记录。2018–2025 原文件未变 |
| 官方新闻没有进入周度流程、例行公告较多 | 将每日官方 news.csv 接入周度流程；保留严格匹配，并新增宽关键词候选召回与排除审计 | 新候选仅进入审阅队列，不直接生成已确认事件；见下方可重现结果 |
| Google 跳转、摘要/正文范围不清 | 保留已有摘要和来源；只有合法、可访问的出版方链接才抓正文；截断正文明确标为 article_excerpt | 本次 85 条 Google 候选仍只有标题，不能当成读过全文。三篇官方正文抽查中，两篇 HTTP 403，一篇正文提取失败，均未绕过限制 |
| 日期或去重可能丢失证据 | 先限定发布日期窗口，再抓正文；不以采集时间冒充发布日期；重复新闻合并来源、关键词和卡片提示 | 日期排除及去重均保留审计；同标题跨较长时间不再直接视为重复 |
| 失败的模型调用可能被重复计费 | 调用前持久保存预留额；有未核销或中断记录时阻止新增付费周批次 | 原有未知费用预留 **USD 0.092103** 保留，本轮没有重试该请求 |

### 最新数据与检验范围

本轮是从审阅分支种子快照进行的**定向本地刷新**，不是线上持久数据库的完整恢复或替换。23 个不同来源中，17 个完全成功、6 个部分成功；`failed_sources` 中的 6 项就是这 6 个部分成功来源，不能把它们重复相加。新增 4,586 条记录、修订 23 条；数据库完整性与外键检查通过。完整本地验证快照保留在此工作树，未替换共享 `data-latest` 发布。

| 输入 | 本次实际最新观测日期 |
|---|---|
| DGS10、BAA10Y | 2026-11-05 |
| SOFR、EFFR、VIXCLS | 2026-11-06 |
| MORTGAGE30US | 2026-11-05 |
| Cboe 全市场成交量 | 2026-11-06 |

数据新鲜度不等于一周覆盖完整。DGS10、BAA10Y 本次只返回到周四，评分端原有完整周检查保留；不补造周五数据。`market_refresh_live.json` 记录首次 Cboe 刷新当时的状态，`final_market_input_audit.json` 记录随后完成 FRED 更新后的状态，二者处于本次验证的不同阶段。

原有 16 卡 V 当前分为 **6 张 PQD、10 张真实公开代理序列**；公开代理不等于 DTCC 内部缓冲的实测值，主面板不含模拟 V。可用时间仍按来源滞后处理，例如 FICC-GSD-11 在本次核验日使用 2026Q1，不能强行换成尚未可用的 Q2。事件登记中 EV0007 也处于活跃状态，EV0006 是当前相关卡片的主导事件；“只有一个事件生效”并不准确。本轮没有补签或伪造新事件。

### 候选召回与交付

最初实际联网采集得到 85 条 Google 候选，严格词组筛选使当周 113 条官方公告全部被排除。核对发现其中包括 NSCC ETF 检查调整、17ad-22 豁免通知和 CFTC 结算相关公告，因此增加宽关键词召回。**这些只是需要审阅的业务/监管候选，尚不能据此认定负面风险或确定传导路径。**

修正后，113 条当周官方公告中保留 91 条候选、排除 22 条，合并 85 条 Google 候选后共 **176 条**（46 条有摘要、130 条只有标题）。不同官方 URL 不因标题相似而合并，避免把 GOV 不同编号公告或不同交易所的相似规则通知误删。离线重放结果见 [candidate_replay.json](evidence/candidate_replay.json)，完整候选队列见 [candidate_review_queue.csv](data/candidate_review_queue.csv)。重放只使用本轮真实采集的标题、摘要和日期，不生成新闻，也不调用模型。宽筛选会提高召回率，同时增加噪声，后续仍需核对机制、原文和人工确认。

所有材料集中在本目录：`data/` 是有限范围的真实输入与候选队列，`evidence/` 是联网响应、时间范围、测试及保护文件核验。发布包中的健康状态在上传前生成，为 `not_confirmed`；上传后的 GitHub recovery artifact 才记录 `published`，不能混用这两个阶段。Cboe recovery artifact 单独上传，保持原数据库 artifact 的下载目录契约。

**195 项验证测试 + 39 项数据库测试全部通过，共 234 项；两份工作流通过 actionlint。98 份受保护文件逐字节与基线一致。** 复现与测试命令、结果见 [acceptance.json](evidence/acceptance.json)。可从 `Capstone_Project/` 运行以下**不调用 AWS**的检查：

```bash
python reports/pipeline_repair_2026_11_09/replay_candidates.py
python -m validation.refresh_scoring_inputs --audit
python -m validation.weekly_news_run --week-start 2026-11-02 --cap 3 --collect-only
```

第三条会重新联网采集公开新闻；前两条仅检查本地材料。部署需审阅并合并相应分支；本轮没有启用任何新的定时模型调用。

## English

This repair addresses freshness, news evidence and pipeline-status issues raised in the three screenshots. The screenshots stayed local. **No AWS or paid-model calls were made.** Changes are on a separate review branch; main, historical scores, quarterly V, event registrations and sign-offs remain unchanged.

The CFTC source now uses its dated official press-release index following the agency's temporary RSS suspension: HTTP 200, 37 notices, latest publication November 9. Weekly RDS files now commit independently, so a missing period cannot discard other successfully collected periods. All eight sources supplied October 16/23/30 reports; both UK SFTR sources supplied November 6. Six November 6 EU/UK EMIR files still return 404 and remain explicit gaps.

FRED mortgage rates now join the daily database and scoring-input reader. The daily workflow refreshes the current-year Cboe file while preserving prior years. Mortgage observations reach November 5; Cboe reaches November 6, with 63 new venue-day rows. SOFR, EFFR and VIX reach November 6; DGS10 and BAA10Y reach November 5. Existing complete-week checks remain in place; no missing observations are invented.

The targeted local refresh covered 23 distinct sources: 17 fully successful and six partially successful. The six failed-source entries refer to those same partial sources, not six additional sources. It added 4,586 records and revised 23; database integrity and foreign keys pass. This uses the review branch's seed snapshot and is **not a replacement for the full durable online database**. The full verification snapshot stays local; the shared `data-latest` release was not replaced.

Daily official news now feeds the weekly collection stage. The first live collection produced 85 Google headline-only candidates, while the old strict lexical filter excluded all 113 in-window official notices. Inspection found potentially useful NSCC and regulatory notices among those exclusions. Broad, auditable keyword recall now supplements strict matches, retaining 91 official candidates and excluding 22. The merged queue contains **176 candidates: 46 with summaries and 130 headline-only**. Different official URLs are preserved even when their templated titles are similar. Offline replay results and the review queue are linked above. These are unverified context/event candidates, not accepted events or evidence of adverse impact. Broader recall also increases noise.

Summaries, publication dates, source provenance and card-search hints are retained. Allowed HTML/PDF evidence supports hashed local caches, and truncated text is explicitly `article_excerpt`. Publisher access restrictions remain respected. The 85 Google items have unresolved publisher links and remain headline-only; three official-body spot checks yielded two HTTP 403 responses and one extraction failure. No claim of full-text coverage is made. Date exclusions and deduplication preserve audit evidence; collection time never replaces publication time.

Snapshot publication and source completeness now have separate statuses. The latest inspected online run published its snapshot despite a final partial-source failure check; this does not establish that every run since October 28 stopped updating. A bundle built before upload records publication as `not_confirmed`; the post-upload recovery artifact records `published`. Cboe recovery files use a separate artifact to preserve the database download layout.

The original 16-card V panel comprises six PQD cards and ten real public-proxy cards, with no simulated V in its main ranking. Public proxies are not observed DTCC internal buffers. Source availability lags remain enforced. EV0007 is also active; EV0006 drives the relevant current card. No new event was accepted during this repair.

An unresolved **USD 0.092103** reservation from an earlier failed model call remains untouched. Durable in-flight reservations now block another paid weekly batch until uncertain charges are reconciled. Collection-only and dry-run modes remain available without paid calls. **All 234 offline tests passed** (195 validation and 39 database); both workflows passed actionlint, and 98 protected files match the base byte for byte. Test results, protected-file comparisons and live evidence are collected under `evidence/`; no unattended model execution was enabled.

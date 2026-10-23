# 团队共享公开数据库

这是**每天更新、供团队下载查询的数据库快照**。GitHub 保存采集代码，并通过 GitHub Actions 自动采集；它不是一个可远程连接的 SQL 数据库服务器。

最新本地同步已将线上发布版与研究批次合并，共 **63,344 条记录**。合并凭证见 `logs/latest_github_sync.json`，快照校验值和实际记录数见 `data/snapshot_manifest.json`。下文10月21日导入凭证保留当时的批次记录数。

**10月21日研究数据导入：** 新增12,714条回购、国债拍卖、基金流量和PQD证据记录，本地数据库共55,436条。详见[中英文导入说明](../risk_business_ml/new_reference_chain_tests_2026_10_21/DATABASE_UPDATE_CN_EN.md)与[SQL示例](research_queries.sql)。本次新增来源是批次导入，尚未新增每日采集适配器；本地快照更新不表示GitHub发布包已更新。

## 队友怎么使用

打开 [完整项目下载页](https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence/releases/tag/data-latest)，只下载 **`Capstone_Project_Complete.zip`**。解压后，数据库、校验文件、CSV 和日志都在 `Capstone_Project/capstone_database/` 内。`logs/latest_update.json` 说明更新时间、失败来源及需要人工复核的来源。

会使用 Python 的队友可以：

```bash
git clone https://github.com/BigJayJayHuang/DTCC-External-Risk-Intelligence.git
cd DTCC-External-Risk-Intelligence
cd Capstone_Project/capstone_database
python3 download_latest.py
python3 query.py
```

如果已经下载并解压完整包，进入上述数据库目录，直接运行 `python3 query.py` 即可。`download_latest.py` 会下载最新完整包，但只替换本机的数据库与校验文件。队友不需要运行采集程序，也不需要采集 API 密钥。查询示例见英文 README。每个队友查询自己的下载副本；请不要把一个正在写入的 SQLite 文件放在同步文件夹里供多人共同修改。

## 更新安排与范围

工作流计划每天 **22:17 UTC** 运行，即纽约夏令时 18:17、冬令时 17:17。GitHub 排程可能延迟。工作流在默认分支上且 Actions 启用后生效；也可以在 Actions 页面手动点击 Run workflow。它在 GitHub 上运行，不依赖你的电脑开机。

数据涵盖十条业务线：FICC、ECS、RDS、WIS、ITP、Asset Services、DAS、DDA、Data Services、Consulting。共享来源只采集一次，数据库另存它与各业务线的对应关系。

已经导入市场历史、官方新闻、FICC 日度及月度数据、ECS/ITP 月度快照、ETF 名单、承销数据、RDS 公开报告、行业基金数据、外部技术与灾害信息，以及 23 个季度的 GSD/MBSD/NSCC PQD 和提取证据。各类数据保留原来的频率、单位、司法辖区和法律实体范围，不把季度数据变成虚假的日度观察值。

采集程序保留旧版本、来源链接、证据哈希和采集日志。历史公开原始文件保存在完整包的旧采集文件夹中；当前数据库快照保留结构化数据和证据引用。每日工作流更新数据库后，重新发布一个完整项目 ZIP，历史分析保持不变。失败的来源保留上次有效数据，记录失败；成功来源仍会更新。部分来源失败时，快照仍会发布，同时工作流显示失败，方便维护者处理。每次运行还有保留 30 天的恢复副本。

## 仍需人工处理的地方

DTCC 动态 PQD/财务/新闻目录以及 ICI 页面尚未确认可稳定自动解析的结构化入口，当前保留已有数据并明确标记人工复核，不会把旧数据标成新数据。新季度 PQD 和财务披露还需要检查、提取并复核后纳入。DAS、DDA、Consulting 的内部业绩和运行指标仍然缺失，公开新闻和市场代理不能替代这些指标。

新闻的业务线标签只是候选关系，不代表已确认影响；CISA 或云平台事件不证明 DTCC 实际暴露。数据库更新不重跑机器学习，也不生成可靠风险评分。

仓库目前是**公开仓库**，所以任何人都能读取；写入权限由仓库所有者管理。这里只放公开来源数据和代码，不上传项目 PPT、内部资料、私人文档或凭证。完整维护说明和数据边界见 [README.md](README.md)。

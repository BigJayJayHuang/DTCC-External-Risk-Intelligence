# Capstone 公开信息采集原型

这是给 External Risk Intelligence & Horizon-Scanning 项目写的第一版数据采集样例。
它读取机构主动提供的公开 RSS，把不同来源整理成统一格式，保留原始证据，并识别重复文档和内容修改。

**先打开 `output/preview.html` 看实际结果，再读代码。**

这个版本已在本地实跑；没有部署到 DevX AWS，也没有创建任何云资源。来源选择见 [SOURCES.md](SOURCES.md)。

## 运行

需要 Python 3.10 或以上。只使用 Python 标准库，不用安装第三方包，不用 API key。

```bash
cd "/Users/shanpeiyuan/Capstone Project/public_news_prototype"
python3 collect.py
```

Windows 或云端环境中，进入这个文件夹后运行 `python collect.py` 或 `python3 collect.py`。

默认读取 5 个官方订阅，每个来源最多保留 20 条有效、去重后的记录，优先保留有已知发布时间的较新记录。
RSS 只包含发布者提供的近期窗口，不是完整历史数据库，也不保证覆盖当天所有公告。

只运行一个来源：

```bash
python3 collect.py --only fed_press --limit 10
```

程序不会登录网站、绕过付费墙或访问内部系统。每个来源只请求一次订阅，不逐篇下载正文。
遇到拒绝访问、限流、超时或非 RSS 响应，会记录错误并继续处理其他来源。退出码：0 全部成功，2 部分成功，1 全部失败。
网络错误可先根据运行报告检查域名访问、环境出口配置及来源服务状态，不应绕过访问限制。

## 程序怎么工作

```text
sources.json 中的订阅地址
    ↓ fetch：下载公开 XML，并保存原始响应及抓取时间
    ↓ parse_feed：解析标题、摘要、原文链接、原始发布时间
    ↓ clean / normalize_date：清洗 HTML、统一时区
    ↓ candidate_tags：给出关键词命中的候选业务标签及依据
    ↓ upsert：识别新文档、重复文档、内容修订
    ↓ SQLite + JSONL + 本地浏览结果页面
```

你日常维护的主要内容是：数据源是否能访问、正文和日期字段是否完整、是否重复，以及样本标签是否需要修改。

## 输出文件

| 文件 | 用途 |
|---|---|
| `output/preview.html` | 双击后用浏览器查看本次采集文档，点击标题回到原文 |
| `output/latest_documents.jsonl` | 本次运行的数据，一行一个 JSON，供队友读入分析程序 |
| `output/latest_run_report.json` | 每个来源的成功/失败、新增/更新/未变化计数及最新发布时间 |
| `output/news.sqlite3` | 跨运行去重的累计文档表和内容修订历史 |
| `output/runs/<运行编号>/raw/` | 本次原始 XML、响应元数据与内容哈希 |
| `output/runs/<运行编号>/documents.jsonl` | 本次采集快照，后续运行不会覆盖 |
| `output/runs/<运行编号>/run_report.json` | 该次运行的来源健康情况 |

`latest_*` 和预览只展示**本次**结果，失败来源不会被旧数据悄悄替代；累计数据仍保留在 SQLite 和历史快照中。
`raw_file` 相对 `output/` 定位原始证据。`documents` 保存最新观察，`versions` 保存内容每次改变时的记录。

Python 读取结果：

```python
import json
from pathlib import Path

documents = [json.loads(line) for line in
             Path("output/latest_documents.jsonl").read_text(encoding="utf-8").splitlines()]
for document in documents[:3]:
    print(document["title"], document["url"])
```

## 核心字段

| 字段 | 意义 |
|---|---|
| `document_id` | 来源 ID + 规范化原文 URL 的稳定哈希 |
| `source_id` / `source_name` | 信息发布者 |
| `url` / `source_feed_url` | 原文和订阅地址 |
| `title` / `source_summary` | 原文标题与发布者在 RSS 中提供的摘要 |
| `published_at_raw` / `published_at_utc` | 来源时间原值与统一 UTC 时间；缺失或时区不明时保留空值 |
| `collected_at_utc` | 这次下载完成时间，不能冒充文章发布时间 |
| `event_time` / `effective_time` | 事件发生/生效时间，当前未提取，均为 null |
| `business_lines_candidate` / `risk_families_candidate` | 规则初筛结果，不是已验证的风险判断 |
| `tag_evidence` / `tag_rule_version` | 命中的词、规则及版本 |
| `quality_flags` | 缺摘要、摘要重复标题、摘要疑似截断、日期异常等 |
| `change_status` | 本次观察为 new / updated / unchanged |
| `revision` / `content_hash` | 文档内容版本和哈希 |
| `review_status` | 当前均为 unreviewed，等待人工审核 |

`severity` 和 `impact_analysis` 当前均为 null。`ai_generated=false` 表示采集内容及分类未调用生成式模型，不代表代码没有使用 AI 辅助开发。
风险类别为原型自拟，需与队友/项目方共同确定。

## 这个样例的边界

- 采集粒度是**文档**。同一事件的多篇报道尚未归并，不应把文档数量直接当成事件数量或风险强度。
- 只做同一来源内、同一规范化 URL 的文档去重。不同 URL 的转载、不同来源的重复新闻不会自动合并。
- 只读取 RSS 标题与摘要，未抓取文章全文。有些来源无摘要，有些摘要等于标题或被截断，字段提示会显示。
- 候选标签来自简单关键词匹配；“未匹配”不等于无关，命中也不等于存在业务影响。DAS 与 DDA 分别保存，数字资产宽泛词可能同时命中，需人工区分。
- 同一 URL 的标题、摘要或来源时间变化会产生新版本；全文变更但 RSS 不变时，本版本无法发现。
- RSS 条目从近期列表消失不等于事件撤回或风险消除。
- 来源最新文章发布时间由报告给出；抓取成功不代表内容足够新，也不代表覆盖全面。
- 没有自动生成“事件如何影响 DTCC”的因果解释或严重程度。这需要全文证据、业务背景与人工验证。
- 单进程本地原型；不要并发运行多个采集实例。尚未实现生产级调度、自动重试、历史回填和事件聚类。

## 测试

```bash
python3 -m unittest -v
```

合成测试在临时目录运行，验证时区、缺失日期、HTML 错误页、危险链接、标签词边界、重复运行、版本保留和部分失败。
实际运行数据在 `output/`；测试数据不会混入其中。

## 后续在 DevX AWS 使用

程序本身可以迁入已获准、支持 Python 的 DevX 工作环境；当前尚未验证你的 AWS 权限、外网出口或具体服务。
先在该环境手动运行一个来源，确认数据存放位置；再选择组织允许的计算、存储和定时执行方式。
不要把本地 SQLite 多进程写入模式直接当成云端生产设计。

遵循你提供的 DevX 规则：只使用符合 White 分类要求的数据；公开可读不自动等于已完成分类确认。
本原型不连接 DTCC 内网，不包含客户/会员数据或凭证；公开网站链接只是来源引用，不是创建云资源名称。
未来创建资源时使用正式业务单元前缀、标签并控制成本，名称中不使用禁止词。
DevX 可能被清除，应将代码、配置、样例和演示保存到组织允许的持久位置。

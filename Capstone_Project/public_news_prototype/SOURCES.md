# 公开消息来源清单

核实日期：2026-09-25。来源与业务的对应关系是根据项目 PPT 提出的研究建议，具体文章仍需人工判断。
本轮优先使用发布机构的一手公告，便于核对原文、发布时间和更新内容。网站公开访问与组织 White 分类是不同问题。

## 已接入的五个官方来源

| 来源与官方订阅说明 | 可以关注的消息 | 建议关联的项目领域 | 本原型方式 |
|---|---|---|---|
| [Federal Reserve](https://www.federalreserve.gov/feeds/feeds.htm) | 货币政策、银行监管、流动性相关公告 | FICC、宏观与市场环境；其他业务视事件决定 | 官方新闻 RSS |
| [SEC](https://www.sec.gov/about/rss-feeds) | 证券监管、市场结构、清算和信息披露公告 | FICC、ECS、ITP、DAS，按具体事件区分 | 官方新闻 RSS；不等于完整规则库 |
| [CFTC](https://www.cftc.gov/RSS/index.htm) | 衍生品监管、清算与报告规则相关消息 | RDS、衍生品市场及跨业务监管变化 | 官方一般新闻 RSS |
| [ECB](https://www.ecb.europa.eu/home/html/rss.en.html) | 欧洲货币政策、讲话与新闻发布 | 全球市场背景、欧洲相关业务环境 | 官方新闻/讲话 RSS |
| [BIS](https://www.bis.org/rss) | 金融稳定、资本流动性、金融市场基础设施相关公告 | 清算风险、运营韧性、数字资产研究背景 | 官方媒体发布 RSS |

所有接入 URL 在 `sources.json` 中，可按 `id` 单独运行。无登录或 API key。
五个来源都是候选池，不代表每一条新闻都与项目相关，更不代表已覆盖十条业务线。

## 建议下一批接入

以下已核实存在公开页面，但**本版没有编写或验证自动采集适配器**。

| 来源 | 在项目中的用途 | 下一步获取方式 |
|---|---|---|
| [DTCC 官方新闻](https://www.dtcc.com/press-releases) | 业务背景、产品与流程变动；帮助建立业务知识库 | 调查官方订阅/列表结构和使用条件，只使用公开页面 |
| [CME 官方新闻](https://www.cmegroup.com/media-room/press-releases.html) | 同业与潜在竞争动态，尤其国债和回购清算 | 核实可用订阅或公开新闻接口，再写适配器 |
| [ICE 官方国债清算公告示例](https://ir.theice.com/press/news-details/2026/ICE-Clear-Credits-Treasury-Clearing-Service-Receives-SEC-Approval-and-is-Now-Operationally-Live/default.aspx) | FICC 对应市场的同业动态 | 从官方新闻入口核实持续更新方式，保留发布机构自述属性 |
| [FSB 新闻发布](https://www.fsb.org/content_types/press-releases/) | 非银金融、私人信贷、网络与系统性风险 | 核实订阅方式，筛选相关主题 |
| [IMF 新闻](https://www.imf.org/en/news) | 宏观、地缘事件的经济影响和金融稳定背景 | 核实新闻入口和报告元数据，后续按需处理 PDF |

项目 PPT 提到了 Risk.net 等新闻来源。商业新闻可以作为补充，但本原型没有假定任何免费全文接口或订阅授权；先核实机构订阅与使用条件，再考虑接入。

## 选择与扩展顺序

先以 FICC 相关主题验证流程：从 Fed/SEC/BIS 提取候选消息，人工核查标题、链接和日期是否正确。
随后补入 DTCC 与 CME/ICE 的公开业务消息，让“外部事件—业务背景—同业动态”的材料更完整。
若团队优先选择 RDS，应进一步覆盖相关司法辖区的监管来源，当前五个 feed 不足以支持全面监控。
官方公告对地缘事件和突发新闻的覆盖有限，完整版本还需要另行评估具有使用许可的新闻来源。

下一阶段应为少量高相关文档获取获准使用的全文，并标注事件时间、规则生效时间、业务映射理由。
不要仅凭标题中的词就直接生成严重程度或因果链结论。

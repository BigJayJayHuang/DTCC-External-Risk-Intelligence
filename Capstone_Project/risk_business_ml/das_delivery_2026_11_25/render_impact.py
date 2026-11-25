"""Render a self-contained, source-linked brief of the ten project business lines."""

import json
from html import escape


def links(sources):
    return " · ".join(
        f'<a href="{escape(source["url"])}" target="_blank" rel="noopener noreferrer">{escape(source["name"])}</a>'
        for source in sources
    )


def render_impact(inputs):
    events = json.loads((inputs / "recent_events.json").read_text(encoding="utf-8"))
    analysis = json.loads((inputs / "business_line_analysis.json").read_text(encoding="utf-8"))
    line_ids = ("FICC", "ECS", "RDS", "WIS", "ITP", "Asset Services", "DAS", "DDA", "Data Services", "Consulting")
    if tuple(line["key"] for line in analysis["lines"]) != line_ids:
        raise ValueError("Business line coverage differs from the project taxonomy")
    event_cards = []
    for event in events["events"]:
        event_cards.append(f"""<article>
          <div class="eyebrow">{escape(event["date"])}</div>
          <h3>{escape(event["title"])}</h3>
          <p>{escape(event["fact"])}</p>
          <p class="muted">{escape(event["boundary"])}</p>
          <p class="links">{links(event["sources"])}</p>
        </article>""")

    market_rows = "".join(
        f"<tr><th scope='row'>{escape(row['date'])}</th><td>{row['sp500']:,.2f}</td>"
        f"<td>{row['nasdaq']:,.2f}</td><td>{row['vix']:.2f}</td>"
        f"<td>{row.get('shares_bn', '—')}</td></tr>"
        for row in events["market_points"]
    )
    line_sections = []
    for line in analysis["lines"]:
        line_id = line["key"].lower().replace(" ", "-")
        line_sections.append(f"""<article id="{line_id}">
          <div class="eyebrow">{escape(line["name"])}</div>
          <h3>{escape(line["key"])}</h3>
          <p class="tag">{escape(line["priority"])}</p>
          <dl>
            <dt>英伟达、股市与发行</dt><dd>{escape(line["equity"])}</dd>
            <dt>利率与融资</dt><dd>{escape(line["funding"])}</dd>
            <dt>监管及数字资产事项</dt><dd>{escape(line["other"])}</dd>
            <dt>验证所需的业务数据</dt><dd>{escape(line["check"])}</dd>
          </dl>
        </article>""")
    nav = " ".join(
        f'<a href="#{key.lower().replace(" ", "-")}">{escape(key)}</a>' for key in line_ids
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DTCC 十条业务线影响分析 · 2026-11-25</title>
<style>
:root{{color-scheme:light;font:16px/1.58 system-ui,sans-serif;color:#202b36;background:#f5f7fa}}
body{{margin:0}}
main{{max-width:1140px;margin:auto;padding:36px 20px 60px}}
h1,h2,h3{{line-height:1.25;margin:0 0 12px}}
h1{{font-size:clamp(1.9rem,5vw,3rem)}}
h2{{margin-top:30px}}
p{{margin:8px 0}}
a{{color:#084d77;text-underline-offset:3px}}
.eyebrow,.muted{{color:#4c5a66}}
.eyebrow,.links,nav{{font-size:.88rem}}
.intro{{max-width:800px}}
.summary{{background:#e9f1f6;border-radius:10px;padding:16px 18px;margin-top:18px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
article,details{{background:#fff;border:1px solid #dce3e8;border-radius:10px;padding:16px 18px}}
article h3{{margin:6px 0}}
article:target{{border-color:#09688f;box-shadow:0 0 0 2px #d8eef8}}
nav{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}}
nav a{{background:#fff;border:1px solid #dce3e8;border-radius:5px;padding:4px 8px}}
.tag{{display:inline-block;color:#154f5a;background:#e5f3f2;border-radius:4px;padding:2px 7px;font-size:.9rem}}
dl{{margin:10px 0 0}}dt{{font-weight:650}}dd{{margin:0 0 8px}}
details{{margin-top:12px}}summary{{cursor:pointer;font-weight:650}}
table{{border-collapse:collapse;width:100%;margin-top:10px;font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:4px 8px;border-bottom:1px solid #dce3e8}}
th:first-child{{text-align:left}}
footer{{border-top:1px solid #dce3e8;margin:28px 0 0;padding-top:10px;color:#4c5a66}}
@media(max-width:750px){{.grid{{grid-template-columns:1fr}}main{{padding-top:22px}}th,td{{padding:4px}}}}
</style>
</head>
<body>
<main>
  <p class="eyebrow">2026 年 11 月 25 日核查 · 行情截至 11 月 24 日完整收盘（纽约时间）</p>
  <h1>DTCC 十条业务线影响分析</h1>
  <p class="intro">使用公司公告、市场行情和监管文件追踪 11 月 12–25 日的变化。卡片给出业务传导路径和验证指标。实际保证金、交收异常、经营损失及风险分数均未由本期公开资料确认。</p>
  <div class="summary">
    <b>本期优先核查</b>
    <p><a href="#ecs">ECS</a> 和 <a href="#itp">ITP</a> 检查股市急涨急跌有没有带来清算、匹配和交收压力。<a href="#ficc">FICC</a> 单独核查美债利率及回购。<a href="#asset-services">Asset Services</a> 跟踪英伟达股息、ANT 新股及 DRS 实施。<a href="#das">DAS</a> 与 <a href="#dda">DDA</a> 分别核查各自产品对 Besu 更新的适用性。</p>
  </div>
  <h2>公开证据</h2>
  <div class="grid">{"".join(event_cards)}</div>
  <details><summary>查看事件前后市场收盘数据</summary>
    <table aria-label="2026 年 11 月选定交易日的市场收盘数据">
      <thead><tr><th scope="col">日期</th><th scope="col">标普 500</th><th scope="col">纳斯达克综合</th><th scope="col">VIX</th><th scope="col">成交量（十亿股）</th></tr></thead>
      <tbody>{market_rows}</tbody>
    </table>
    <p class="links">{links(events["market_sources"])}</p>
  </details>
  <h2>逐业务线分析</h2>
  <nav aria-label="业务线">{nav}</nav>
  <div class="grid">{"".join(line_sections)}</div>
  <footer><a href="DAS_Risk_Horizon.html#das">打开 DAS 周度核查页</a> · 业务路径依据项目传导链及公开服务说明，核查优先级依据事件与业务流程的直接程度。</footer>
</main>
</body>
</html>
"""

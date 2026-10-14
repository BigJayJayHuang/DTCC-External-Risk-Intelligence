#!/usr/bin/env python3
"""公开 RSS 采集演示：只使用 Python 标准库，不需要账号或 API key。

流程：下载 feed → 保存原始响应 → 解析清洗 → 候选标签 → 去重/版本 → 导出。
摘要来自 feed 本身。没有抓取文章全文，也没有生成 AI 风险结论。
"""
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import uuid
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
RULE_VERSION = "candidate-keywords-v2"
MAX_BYTES = 5_000_000

# 仅为演示用候选路由规则，不是项目方认可的风险分类标准或影响判断。
# 同一条规则可以关联多个业务，DAS 和 DDA 保留独立标签。
RULES = [
    ("treasury_repo", ["treasury", "treasuries", "repo", "repurchase agreement", "FICC", "mortgage-backed"], ["FICC"], ["market_liquidity"]),
    ("monetary_policy", ["FOMC", "monetary policy", "federal funds", "interest rates"], ["FICC"], ["macro_market"]),
    ("equity_etf", ["equities", "equity clearing", "ETF", "exchange-traded fund", "NSCC"], ["ECS"], ["market_activity"]),
    ("settlement_cycle", ["T+1", "T+0", "settlement cycle", "trade affirmation"], ["ECS", "ITP"], ["operational_change"]),
    ("trade_reporting", ["trade reporting", "transaction reporting", "trade repository", "EMIR", "SFTR"], ["RDS"], ["regulatory_change"]),
    ("funds_insurance", ["mutual fund", "private credit", "annuity", "annuities", "insurance processing"], ["WIS"], ["market_activity"]),
    ("asset_servicing", ["corporate action", "corporate actions", "securities custody", "underwriting", "IPO", "IPOs", "initial public offerings"], ["Asset Services"], ["market_activity"]),
    ("digital_assets", ["tokenization", "tokenisation", "tokenized", "tokenised", "stablecoin", "stablecoins", "digital assets", "crypto assets", "blockchain"], ["DAS", "DDA"], ["digital_asset_change"]),
    ("market_data", ["market data", "data transparency", "reference data"], ["Data Services"], ["data_change"]),
    ("readiness", ["regulatory readiness", "clearing mandate"], ["Consulting"], ["regulatory_change"]),
    ("cyber_resilience", ["cyber", "ransomware", "operational resilience", "third-party service provider"], [], ["operational_cyber"]),
    ("regulatory", ["proposed rule", "final rule", "rulemaking", "regulatory framework"], [], ["regulatory_change"]),
    ("financial_stability", ["financial stability", "liquidity coverage", "Basel III"], [], ["financial_stability"]),
]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PlainText(HTMLParser):
    """Remove markup, including script/style content, from publisher feed excerpts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(value):
    parser = PlainText()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def normalize_url(value, base):
    p = urlsplit(urljoin(base, value.strip()))
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise ValueError("Missing or unsafe article URL")
    # 只删除已知跟踪参数。不能删掉可能决定文章身份的查询参数。
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(query), ""))


def normalize_date(value):
    """Never substitute collection time for an unknown publication time."""
    if not value:
        return None, "missing_publication_time"
    try:
        d = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None, "unparseable_publication_time"
    if d.tzinfo is None:
        return None, "publication_timezone_unknown"
    return d.astimezone(timezone.utc).isoformat(timespec="seconds"), None


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(node, *names):
    for name in names:
        for child in node:
            if local_name(child.tag) == name:
                return "".join(child.itertext()).strip()
    return ""


def candidate_tags(title, summary):
    text = title + "\n" + summary
    evidence, businesses, risks = [], set(), set()
    for rule_id, terms, lines, families in RULES:
        # Word boundaries prevent repo matching report and ETF matching unrelated words.
        matches = [t for t in terms if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, re.I)]
        if matches:
            businesses.update(lines)
            risks.update(families)
            evidence.append({"rule": rule_id, "matched_terms": matches,
                             "business_lines": lines, "risk_families": families})
    return sorted(businesses), sorted(risks), evidence


def parse_feed(payload, source, collected_at, raw_file):
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("DTD/entity declarations are not accepted")
    root = ET.fromstring(payload)
    kind = local_name(root.tag)
    if kind not in {"rss", "RDF", "feed"}:
        raise ValueError("Response is not RSS/Atom (possibly an HTML error page)")
    entries = [n for n in root.iter() if local_name(n.tag) in {"item", "entry"}]
    records, rejected = [], []
    for i, node in enumerate(entries):
        title = clean(child_text(node, "title"))
        link = child_text(node, "link")
        if local_name(node.tag) == "entry":
            link = next((c.get("href", "") for c in node if local_name(c.tag) == "link"
                         and c.get("rel", "alternate") == "alternate"), "")
        if not title or not link:
            rejected.append({"index": i, "reason": "missing_title_or_link"})
            continue
        try:
            url = normalize_url(link, source["feed_url"])
        except ValueError as exc:
            rejected.append({"index": i, "reason": str(exc)})
            continue
        summary = clean(child_text(node, "description", "summary"))
        date_raw = child_text(node, "pubDate", "published", "date")
        date_utc, issue = normalize_date(date_raw)
        flags = [issue] if issue else []
        if not summary:
            flags.append("missing_feed_summary")
        elif summary.casefold() == title.casefold():
            flags.append("feed_summary_repeats_title")
        elif summary.endswith(("…", "...")):
            flags.append("feed_summary_may_be_truncated")
        if date_utc and date_utc > collected_at:
            flags.append("publication_after_collection")
        businesses, risks, evidence = candidate_tags(title, summary)
        document = {
            "document_id": digest(source["id"] + "\n" + url),
            "source_id": source["id"], "source_name": source["name"],
            "source_feed_url": source["feed_url"], "url": url, "title": title,
            "source_item_id": child_text(node, "guid", "id") or None,
            "published_at_raw": date_raw or None, "published_at_utc": date_utc,
            "source_updated_at_raw": child_text(node, "updated") or None,
            "event_time": None, "effective_time": None,
            "source_summary": summary, "text_scope": "feed_summary_only",
            "business_lines_candidate": businesses, "risk_families_candidate": risks,
            "tag_evidence": evidence, "tag_rule_version": RULE_VERSION,
            "review_status": "unreviewed", "ai_generated": False,
            "severity": None, "impact_analysis": None, "quality_flags": flags,
            "collected_at_utc": collected_at, "raw_file": raw_file,
        }
        # 仅源内容变化产生修订；重新抓取时间、原始文件路径、规则版本不影响版本。
        fact_keys = ["title", "url", "source_item_id", "published_at_raw",
                     "source_updated_at_raw", "source_summary"]
        document["content_hash"] = digest(json.dumps({k: document[k] for k in fact_keys}, sort_keys=True))
        records.append(document)
    return records, {"feed_entries": len(entries), "rejected_entries": rejected}


def open_database(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, revision INTEGER NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT NOT NULL, revision INTEGER NOT NULL, observed_at TEXT NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY (id, revision));
    """)
    return con


def upsert(con, document):
    old = con.execute("SELECT content_hash, revision, first_seen FROM documents WHERE id=?",
                      (document["document_id"],)).fetchone()
    state = "new" if old is None else ("unchanged" if old[0] == document["content_hash"] else "updated")
    revision = 1 if old is None else old[1] + (state == "updated")
    document = dict(document, revision=revision,
                    first_seen_at_utc=old[2] if old else document["collected_at_utc"],
                    last_seen_at_utc=document["collected_at_utc"])
    payload = json.dumps(document, ensure_ascii=False)
    con.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?)",
                (document["document_id"], document["content_hash"], revision,
                 document["first_seen_at_utc"], document["last_seen_at_utc"], payload))
    if state != "unchanged":
        con.execute("INSERT INTO versions VALUES (?,?,?,?)",
                    (document["document_id"], revision, document["collected_at_utc"], payload))
    return dict(document, change_status=state)


def fetch(source, timeout, user_agent):
    request = Request(source["feed_url"], headers={"User-Agent": user_agent,
                      "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("Feed exceeds the 5 MB prototype limit")
        metadata = {"http_status": response.status, "final_url": response.url,
                    "content_type": response.headers.get("Content-Type"),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "sha256": digest(payload)}
        return payload, metadata


def write_jsonl(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def render_preview(path, records, report):
    """Local review page, escaped source text, no external assets or JavaScript."""
    e = lambda x: html.escape(str(x or ""), quote=True)
    status_rows = "".join(f'<tr><td>{e(s["source_id"])}</td><td>{e(s["status"])}</td>'
                          f'<td>{s.get("retained", 0)}</td><td>{e(s.get("error", ""))}</td></tr>'
                          for s in report["sources"])
    cards = []
    for r in sorted(records, key=lambda r: r["published_at_utc"] or "", reverse=True):
        terms = "; ".join(", ".join(t["matched_terms"]) for t in r["tag_evidence"])
        cards.append(f'''<article><p class="meta">{e(r['source_name'])} · {e(r['published_at_utc'] or r['published_at_raw'])}</p>
        <h2><a href="{e(r['url'])}" target="_blank" rel="noopener noreferrer">{e(r['title'])}</a></h2>
        <p>{e(r['source_summary']) or '此订阅未提供摘要，请打开原文。'}</p>
        <p class="meta">候选业务：{e(', '.join(r['business_lines_candidate'])) or '未匹配'}<br>
        匹配依据：{e(terms) or '无关键词命中'}<br>
        数据提示：{e(', '.join(r['quality_flags'])) or '无字段异常'} · 待人工核查</p></article>''')
    path.write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1"><title>公开信息采集样例</title>
    <style>body{{max-width:960px;margin:40px auto;padding:0 22px;font:17px/1.65 system-ui;color:#19323d;background:#fafbfc}}
    h1{{font-size:32px}}h2{{font-size:20px}}a{{color:#156588}}article{{padding:22px 0;border-top:1px solid #d8e0e4}}
    .meta{{font-size:14px;color:#526670}}table{{border-collapse:collapse;width:100%;margin:24px 0}}td,th{{text-align:left;padding:9px;border-bottom:1px solid #d8e0e4;overflow-wrap:anywhere}}p{{overflow-wrap:anywhere}}</style>
    <h1>公开信息采集样例</h1><p>采集时间（UTC）：{e(report['started_at_utc'])} · 本次 {len(records)} 条文档</p>
    <p>原型采集的是 RSS 标题、发布者提供的摘要和原文链接，未抓取全文。关键词标签仅供初筛，尚未确认业务影响。
    一条文档不等于一个独立事件。此页面不代表完整的当前风险图景。</p>
    <table><thead><tr><th>来源</th><th>本次状态</th><th>文档数</th><th>错误</th></tr></thead><tbody>{status_rows}</tbody></table>
    {''.join(cards)}</html>''', encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=BASE / "sources.json")
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--only", nargs="+", help="Only these source IDs")
    parser.add_argument("--limit", type=int, default=20, help="Max valid feed entries per source")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--user-agent", default="CapstonePublicNewsPrototype/0.1 (educational RSS reader)")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.timeout <= 0:
        parser.error("--limit and --timeout must be positive")
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    ids = [s["id"] for s in sources]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z0-9_]+", x) for x in ids):
        parser.error("Source IDs must be unique lowercase alphanumeric/underscore names")
    if args.only and set(args.only) - set(ids):
        parser.error("Unknown source ID")
    sources = [s for s in sources if s.get("enabled", True) and (not args.only or s["id"] in args.only)]
    if not sources:
        parser.error("No enabled sources selected")
    started = utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out = args.output.resolve()
    run_dir = out / "runs" / run_id
    (run_dir / "raw").mkdir(parents=True)
    report = {"run_id": run_id, "mode": "live", "started_at_utc": started,
              "limits": {"entries_per_source": args.limit, "scope": "current RSS window; not historical backfill"},
              "sources": []}
    con = open_database(out / "news.sqlite3")
    records = []
    for source in sources:
        status = {"source_id": source["id"], "feed_url": source["feed_url"],
                  "status": "error", "new": 0, "updated": 0, "unchanged": 0}
        print(f"Fetching {source['id']} ...", flush=True)
        raw_path = run_dir / "raw" / (source["id"] + ".xml")
        try:
            payload, metadata = fetch(source, args.timeout, args.user_agent)
            collected_at = utc_now()
            raw_path.write_bytes(payload)
            dump(raw_path.with_suffix(".metadata.json"), dict(metadata, collected_at_utc=collected_at, source=source))
            parsed, parse_stats = parse_feed(payload, source, collected_at, str(raw_path.relative_to(out)))
            status.update(metadata, **parse_stats)
            parsed.sort(key=lambda r: r["published_at_utc"] or "", reverse=True)
            unique = {}
            for record in parsed:
                unique.setdefault(record["document_id"], record)
            retained = list(unique.values())[:args.limit]
            status.update(duplicate_entries=len(parsed) - len(unique),
                          limited_entries=max(0, len(unique) - args.limit), retained=len(retained))
            batch = []
            counts = {"new": 0, "updated": 0, "unchanged": 0}
            with con:
                for record in retained:
                    saved = upsert(con, record)
                    counts[saved["change_status"]] += 1
                    batch.append(saved)
            status.update(counts)
            records.extend(batch)
            status["status"] = "ok" if retained else ("empty" if not parsed and not parse_stats["rejected_entries"] else "invalid_entries")
            status["latest_publication_utc"] = max((r["published_at_utc"] or "" for r in retained), default="") or None
        except Exception as exc:
            # Failure is visible. No bypass, credentials, or silent fake sample data.
            status["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR: {status['error']}", flush=True)
        report["sources"].append(status)
        time.sleep(0.5)
    report["finished_at_utc"] = utc_now()
    report["totals"] = {key: sum(s[key] for s in report["sources"]) for key in ("new", "updated", "unchanged")}
    report["collected_documents"] = len(records)
    report["successful_sources"] = sum(s["status"] in {"ok", "empty"} for s in report["sources"])
    report["total_stored_documents"] = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    con.close()
    write_jsonl(run_dir / "documents.jsonl", records)
    write_jsonl(out / "latest_documents.jsonl", records)
    dump(run_dir / "run_report.json", report)
    dump(out / "latest_run_report.json", report)
    render_preview(out / "preview.html", records, report)
    print(json.dumps({k: report[k] for k in ("run_id", "successful_sources", "collected_documents", "totals")}, ensure_ascii=False, indent=2))
    print(f"Preview: {out / 'preview.html'}")
    # 0=all sources succeeded, 2=partial success, 1=no source succeeded.
    return 0 if report["successful_sources"] == len(sources) else (2 if report["successful_sources"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())

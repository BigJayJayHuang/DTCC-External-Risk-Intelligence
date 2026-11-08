"""Publisher RSS feeds with summaries and publisher URLs, a broad keyword pre-filter (no AI), and full-text extraction.

    python -m validation.publisher_feeds [--out-dir DIR] [--google data/events/classifier_inputs/week_2026-11-02/google_news.csv]

1. Fetch every feed in publisher_feeds_config.json (CNBC, MarketWatch, Yahoo Finance, Nasdaq, Federal Reserve, SEC) with
   an honest User-Agent, at most one request every 2 seconds, after checking the host's robots.txt.
2. Keep an item when its headline or summary contains any single keyword from any card's query list
   (news_queries.csv; case-insensitive, word-boundary match). Matched keywords and card hints are recorded.
   Existing Google News items are added too; they stay headline-only.
3. For kept items with a publisher URL, fetch the page (robots.txt permitting) and extract the main article text.
   Paywalled pages (schema.org isAccessibleForFree = false, or HTTP 401/402/403) and failed extractions fall back
   to the RSS summary. Text is truncated to about 1,000 words. content_scope is full_text, summary or headline_only.
   Full texts are written only to the git-ignored fulltext cache; the CSVs hold headline, URL, summary, scope and
   the text's sha256.
"""
from __future__ import annotations

import argparse, csv, difflib, email.utils, hashlib, html, json, os, re, urllib.error, urllib.parse, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from . import google_news as G

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("publisher_feeds_config.json")
SOURCE_ID = "publisher_rss"
FIELDS = ["document_id", "title", "url", "publication_date", "published_at_utc", "summary", "source_id", "feed_id", "outlet",
          "source_tier", "matched_keywords", "matched_card_ids", "content_scope", "fulltext_status", "text_words", "text_sha256",
          "text_file", "google_link", "last_seen"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ HTTP client: honest UA, rate limit, robots.txt
class Client:
    def __init__(self, config, limiter=None, opener=None):
        self.config = config
        self.limiter = limiter or G.RateLimiter(config["min_request_interval_seconds"])
        self.opener = opener or urllib.request.build_opener()
        self.robots: dict[str, urllib.robotparser.RobotFileParser | bool] = {}
        self.log: list[dict] = []

    def user_agent(self, url: str) -> str:
        host = urllib.parse.urlparse(url).hostname or ""
        if host == "sec.gov" or host.endswith(".sec.gov"):
            return os.environ.get(self.config["sec_user_agent_env"]) or self.config["user_agent"]
        return self.config["user_agent"]

    def get(self, url: str, max_bytes: int | None = None, kind: str = "page"):
        self.limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent(url), "Accept-Language": "en-US,en;q=0.8"})
        entry = {"kind": kind, "url": url, "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            with self.opener.open(req, timeout=self.config["timeout_seconds"]) as r:
                body = r.read(max_bytes + 1 if max_bytes else -1)
                entry.update(status=r.status, final_url=r.geturl(), bytes=len(body), content_type=r.headers.get("Content-Type", ""))
                self.log.append(entry)
                return r.status, body, r.geturl(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            entry.update(status=e.code, bytes=0)
        except Exception as e:     # network error: recorded, never retried
            entry.update(status=None, error=type(e).__name__)
        self.log.append(entry)
        return entry["status"], b"", url, ""

    def allowed(self, url: str) -> bool:
        p = urllib.parse.urlparse(url)
        key = f"{p.scheme}://{p.netloc}"
        if key not in self.robots:
            status, body, _, _ = self.get(key + "/robots.txt", 500_000, kind="robots")
            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.decode("utf-8", "replace").splitlines())
                self.robots[key] = rp
            else:   # RFC 9309: 4xx means no restrictions; 5xx or no answer means do not crawl
                self.robots[key] = status is not None and 400 <= status < 500
        rp = self.robots[key]
        return rp.can_fetch(self.user_agent(url), url) if isinstance(rp, urllib.robotparser.RobotFileParser) else bool(rp)


# ------------------------------------------------------------------ feeds
def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _date(s: str):
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None


def parse_feed(body: bytes) -> list[dict]:
    root = ET.fromstring(body)
    items = []
    for it in root.iter():
        tag = it.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda name: next((c for c in it if c.tag.rsplit("}", 1)[-1] == name), None)
        title = strip_html((get("title").text if get("title") is not None else "") or "")
        link_el = get("link")
        link = (link_el.text or "").strip() if link_el is not None and (link_el.text or "").strip() else (link_el.attrib.get("href", "") if link_el is not None else "")
        desc_el = get("description") if get("description") is not None else (get("summary") if get("summary") is not None else get("content"))
        summary = strip_html(desc_el.text if desc_el is not None and desc_el.text else "")
        when = None
        for name in ("pubDate", "published", "updated", "date"):
            el = get(name)
            if el is not None and (when := _date((el.text or "").strip())):
                break
        if title and link:
            items.append({"title": title, "url": link, "summary": summary if summary != title else "", "published": when})
    return items


# ------------------------------------------------------------------ broad keyword pre-filter (no AI)
def keyword_index(queries) -> dict[str, set[str]]:
    index = defaultdict(set)
    for card, q in queries:
        for term in G.query_terms(q):
            index[term.lower()].add(card)
    return dict(index)


def keyword_hits(text: str, index: dict[str, set[str]]) -> dict[str, list[str]]:
    hits = {}
    for kw, cards in index.items():
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])", text, re.I):
            hits[kw] = sorted(cards)
    return hits


# ------------------------------------------------------------------ full text
class _Paragraphs(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "aside", "header", "form", "noscript", "figure", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = Counter(); self.article = []; self.other = []; self.buf = None; self.in_article = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth[tag] += 1
        elif tag == "article":
            self.in_article += 1
        elif tag == "p" and not sum(self.depth.values()):
            self.buf = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth[tag]:
            self.depth[tag] -= 1
        elif tag == "article" and self.in_article:
            self.in_article -= 1
        elif tag == "p" and self.buf is not None:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(text) >= 40:
                (self.article if self.in_article else self.other).append(text)
            self.buf = None

    def handle_data(self, data):
        if self.buf is not None:
            self.buf.append(data)


def _jsonld_articles(page: str):
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(html.unescape(block.strip()))
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                types = obj.get("@type"); types = types if isinstance(types, list) else [types]
                if any(str(t).endswith(("Article", "BlogPosting")) for t in types if t):
                    yield obj
                stack += obj.get("@graph", []) if isinstance(obj.get("@graph"), list) else []


def extract(page: str):
    """Returns (text, status). Paywalled pages never yield text, even if the HTML contains it."""
    articles = list(_jsonld_articles(page))
    if any(str(a.get("isAccessibleForFree", "")).lower() == "false" for a in articles):
        return "", "paywalled"
    body = next((a["articleBody"] for a in articles if isinstance(a.get("articleBody"), str) and len(a["articleBody"].split()) >= 80), "")
    if body:
        return re.sub(r"\s+", " ", html.unescape(body)).strip(), "ok_jsonld"
    p = _Paragraphs()
    try:
        p.feed(page)
    except Exception:
        return "", "extract_failed"
    paras = p.article or p.other
    text = " ".join(paras)
    return (text, "ok_paragraphs") if len(text.split()) >= 80 else ("", "extract_failed")


def truncate(text: str, words: int) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + (" …" if len(parts) > words else "")


def fetch_fulltext(item: dict, client: Client, config: dict, cache_dir: Path) -> dict:
    url = item["url"]
    if urllib.parse.urlparse(url).hostname in ("news.google.com",) or not url.startswith("http"):
        return {"fulltext_status": "no_publisher_url"}
    if not client.allowed(url):
        return {"fulltext_status": "robots_disallowed"}
    status, body, final, ctype = client.get(url, config["max_article_bytes"], kind="article")
    if status in (401, 402, 403):
        return {"fulltext_status": "paywalled_or_forbidden_http_%s" % status}
    if status != 200 or not body:
        return {"fulltext_status": f"http_{status}"}
    if "html" not in ctype.lower():
        return {"fulltext_status": "not_html"}
    text, how = extract(body.decode("utf-8", "replace"))
    if not text:
        return {"fulltext_status": how}
    text = truncate(text, config["fulltext_max_words"])
    name = sha(url.encode())[:24] + ".txt"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / name).write_text(text, encoding="utf-8")
    return {"fulltext_status": how, "text_sha256": sha(text.encode("utf-8")), "text_words": len(text.split()),
            "text_file": str((cache_dir / name).relative_to(PROJECT))}


# ------------------------------------------------------------------ build
def dedupe(rows: list[dict], threshold: float) -> tuple[list[dict], int]:
    """By URL, then near-identical title; a publisher item wins over a Google News item."""
    rows = sorted(rows, key=lambda r: (r["source_id"] != SOURCE_ID, r.get("published_at_utc") or ""))
    kept, seen_urls, dup = [], set(), 0
    for r in rows:
        nt = G.norm_title(r["title"])
        twin = next((k for k in kept if difflib.SequenceMatcher(None, nt, G.norm_title(k["title"])).ratio() >= threshold), None)
        if r["url"] in seen_urls or twin is not None:
            dup += 1
            if twin is not None and r.get("google_link") and not twin.get("google_link"):
                twin["google_link"] = r["google_link"]
            continue
        seen_urls.add(r["url"]); kept.append(r)
    return kept, dup


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--google", type=Path, default=PROJECT / "data/events/classifier_inputs/week_2026-11-02/google_news.csv")
    p.add_argument("--skip-fulltext", action="store_true")
    a = p.parse_args(argv)
    config = json.loads(CONFIG.read_text())
    now = datetime.now(timezone.utc)
    out = a.out_dir or PROJECT / "data/events/classifier_inputs" / f"feeds_{now.date().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = PROJECT / config["fulltext_cache_dir"]
    index = keyword_index(G.load_queries())
    client = Client(config)
    stats = defaultdict(Counter)
    rows, dropped = [], []
    for feed in config["feeds"]:
        if not client.allowed(feed["url"]):
            stats[feed["id"]]["robots_disallowed_feed"] += 1
            continue
        status, body, _, _ = client.get(feed["url"], 5_000_000, kind="feed")
        stats[feed["id"]]["feed_http_" + str(status)] += 1
        if status != 200 or not body:
            continue
        try:
            items = parse_feed(body)
        except ET.ParseError:
            stats[feed["id"]]["feed_parse_error"] += 1
            continue
        for it in items:
            stats[feed["id"]]["fetched"] += 1
            hits = keyword_hits(it["title"] + "\n" + it["summary"], index)
            row = {"document_id": sha(it["url"].encode()), "title": it["title"], "url": it["url"], "publication_date": "",
                   "published_at_utc": it["published"].isoformat(timespec="seconds") if it["published"] else "",
                   "summary": it["summary"], "source_id": SOURCE_ID, "feed_id": feed["id"], "outlet": feed["outlet"],
                   "source_tier": feed["source_tier"], "matched_keywords": json.dumps(hits, ensure_ascii=False),
                   "matched_card_ids": "|".join(sorted({c for cs in hits.values() for c in cs})), "last_seen": now.isoformat(timespec="seconds")}
            if not it["published"]:
                stats[feed["id"]]["no_publication_date"] += 1
            if hits:
                stats[feed["id"]]["kept_prefilter"] += 1; rows.append(row)
            else:
                dropped.append({k: row[k] for k in ("feed_id", "outlet", "published_at_utc", "title", "url")})
    if a.google and a.google.exists():
        with a.google.open(encoding="utf-8", newline="") as f:
            for g in csv.DictReader(f):
                hits = keyword_hits(g["title"], index)
                stats["google_news_existing"]["fetched"] += 1; stats["google_news_existing"]["kept_prefilter"] += 1
                rows.append({**{k: g.get(k, "") for k in ("document_id", "title", "url", "publication_date", "published_at_utc", "source_id", "outlet", "source_tier", "google_link")},
                             "summary": "", "feed_id": "google_news_existing", "matched_keywords": json.dumps(hits, ensure_ascii=False),
                             "matched_card_ids": g.get("matched_card_ids", ""), "content_scope": "headline_only", "fulltext_status": "google_headline_only",
                             "last_seen": g.get("last_seen", "")})
    rows, dups = dedupe(rows, config["title_similarity_threshold"])
    for r in rows:
        if r["source_id"] != SOURCE_ID:
            continue
        ft = {"fulltext_status": "skipped"} if a.skip_fulltext else fetch_fulltext(r, client, config, cache_dir)
        r.update(ft)
        r["content_scope"] = "full_text" if ft.get("text_file") else ("summary" if r["summary"] else "headline_only")
        stats[r["feed_id"]]["scope_" + r["content_scope"]] += 1
        stats[r["feed_id"]]["fulltext_" + ft["fulltext_status"]] += 1
    for r in rows:
        if r["source_id"] != SOURCE_ID:
            stats[r["feed_id"]]["scope_headline_only"] += 1
    rows.sort(key=lambda r: (r.get("published_at_utc") or "", r["document_id"]))
    with (out / "classifier_input.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    with (out / "prefilter_dropped.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feed_id", "outlet", "published_at_utc", "title", "url"], lineterminator="\n"); w.writeheader(); w.writerows(dropped)
    dates = sorted(r["published_at_utc"][:10] for r in rows if r.get("published_at_utc"))
    summary = {"collected_utc": now.isoformat(timespec="seconds"), "user_agent": config["user_agent"],
               "sec_user_agent_override": bool(os.environ.get(config["sec_user_agent_env"])),
               "per_source": {k: dict(v) for k, v in stats.items()}, "duplicates_merged": dups, "items_to_classifier": len(rows),
               "scope_totals": dict(Counter(r["content_scope"] for r in rows)),
               "published_range": [dates[0], dates[-1]] if dates else None,
               "requests": [{"kind": k, "status": s, "n": n} for (k, s), n in Counter((e["kind"], e.get("status")) for e in client.log).items()],
               "robots": {h: ("parsed" if not isinstance(v, bool) else ("allow_all" if v else "disallow_all")) for h, v in client.robots.items()},
               "config_sha256": sha(CONFIG.read_bytes()), "queries_sha256": sha(G.QUERIES.read_bytes())}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "request_log.json").write_text(json.dumps(client.log, indent=2) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()

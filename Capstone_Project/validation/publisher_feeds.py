"""Publisher RSS feeds with summaries and publisher URLs, a broad keyword pre-filter (no AI), and full-text extraction.

    python -m validation.publisher_feeds [--out-dir DIR] [--google data/events/classifier_inputs/week_2026-11-02/google_news.csv]

1. Fetch every feed in publisher_feeds_config.json (CNBC, MarketWatch, Yahoo Finance, Nasdaq, Federal Reserve, SEC) with
   an honest User-Agent, at most one request every 2 seconds, after checking the host's robots.txt.
2. Keep an item when its headline or summary contains any single keyword from any card's query list
   (news_queries.csv; case-insensitive, word-boundary match). Matched keywords and card hints are recorded.
   Existing Google News and pre-filtered official-feed items are added too.
3. For kept items with a publisher URL, fetch the page (robots.txt permitting) and extract the main article text.
   Paywalled pages (schema.org isAccessibleForFree = false, or HTTP 401/402/403) and failed extractions fall back
   to the RSS summary. Truncated text is explicitly article_excerpt, not full_text.
   Full texts are written only to the git-ignored fulltext cache; the CSVs hold headline, URL, summary, scope and
   the text's sha256.
"""
from __future__ import annotations

import argparse, csv, difflib, email.utils, hashlib, html, ipaddress, json, os, re, shutil, subprocess, tempfile, urllib.error, urllib.parse, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from . import alpha_vantage_news as AV
from . import google_news as G

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = Path(__file__).with_name("publisher_feeds_config.json")
SOURCE_ID = "publisher_rss"
FIELDS = ["document_id", "title", "url", "publication_date", "published_at_utc", "summary", "source_id", "feed_id", "outlet",
          "source_tier", "matched_keywords", "matched_card_ids", "content_scope", "fulltext_status", "text_words", "text_sha256",
          "text_file", "google_link", "last_seen", "publisher_url", "outlet_url", "url_resolution", "matched_queries",
          "selected_for_card_ids", "keep_rule", "headline_term_match", "duplicate_evidence", "text_truncated", "original_text_words",
          "content_source_url", "raw_sha256", "raw_file"]

OFFICIAL_META = {
    "federal_register": ("Federal Register", "official"), "dtcc_notice_feed": ("DTCC", "dtcc"),
    "dtcc_insight_20261014": ("DTCC", "dtcc"), "sec_press": ("SEC", "regulator"),
    "cftc_press": ("CFTC", "regulator"), "fed_press": ("Federal Reserve", "regulator"),
    "fca_rss": ("FCA", "regulator"), "ecb_press": ("ECB", "official"),
    "esma_news": ("ESMA", "regulator"), "bis_press": ("BIS", "official"),
}
# Non-US official publishers reach the model only when title or summary names a US market link (exclusion audit otherwise)
NON_US_OFFICIAL = {"fca_rss", "ecb_press", "esma_news", "bis_press"}
US_TERMS_CASE = re.compile(r"(?<![A-Za-z0-9])(US|U\.S\.|SEC|CFTC|DTCC|FICC|NSCC|DTC)(?![A-Za-z0-9])")
US_TERMS_ANY_CASE = re.compile(r"(?<![A-Za-z0-9])(United States|Federal Reserve|Treasury)(?![A-Za-z0-9])", re.I)
UK_TREASURY = re.compile(r"(?<![A-Za-z0-9])(HM|His Majesty['’]s|Her Majesty['’]s) Treasury(?![A-Za-z0-9])", re.I)   # never a US link
LOCAL_TEXT_SCOPES = {"full_text", "article_excerpt"}      # body lives in the git-ignored cache; CSV keeps only its hash


def us_link(text: str) -> bool:
    """A US term in the text; "HM Treasury" / "His Majesty's Treasury" are removed first, so the UK Treasury alone does
    not count (a separate US term in the same text still does)."""
    text = UK_TREASURY.sub(" ", text)
    return bool(US_TERMS_CASE.search(text) or US_TERMS_ANY_CASE.search(text))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ HTTP client: honest UA, rate limit, robots.txt
def public_https_url(url: str) -> bool:
    """Reject local/private URL forms without DNS queries or network side effects.

    This lexical guard does not claim to validate DNS resolution or prevent DNS
    rebinding; the configured public-source inventory remains the source boundary.
    """
    if not isinstance(url, str) or re.search(r'[\x00-\x20\x7f]', url):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or '').rstrip('.').lower()
        if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            return False
    except ValueError:
        return False
    if '%' in host or '\\' in host:
        return False
    try:
        address = ipaddress.ip_address(host)
        return address.is_global and not address.is_multicast and not address.is_unspecified
    except ValueError:
        pass
    labels = host.split('.')
    if len(labels) < 2 or any(label in {'localhost', 'local', 'internal', 'localdomain', 'lan', 'home', 'metadata'} for label in labels):
        return False
    if any(host == suffix or host.endswith('.' + suffix) for suffix in ('nip.io', 'sslip.io', 'localtest.me', 'lvh.me')):
        return False
    # inet_aton-compatible shortened/octal/hex forms must not be interpreted as
    # ordinary hostnames (e.g.127.1 or0x7f.0.0.1).
    if all(re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)', label) for label in labels):
        return False
    return all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', label) for label in labels)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed):
        super().__init__(); self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if not public_https_url(target):
            raise urllib.error.HTTPError(req.full_url, 403, 'Unsafe redirect destination rejected', headers, fp)
        kind = getattr(req, '_capstone_kind', 'page')
        if kind != 'robots' and not self.allowed(target):
            raise urllib.error.HTTPError(req.full_url, 403, 'Redirect destination disallowed by robots policy', headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None:
            redirected._capstone_kind = kind
        return redirected


class Client:
    def __init__(self, config, limiter=None, opener=None):
        self.config = config
        self.limiter = limiter or G.RateLimiter(config["min_request_interval_seconds"])
        self.opener = opener or urllib.request.build_opener(_SafeRedirect(self.allowed))
        self.robots: dict[str, urllib.robotparser.RobotFileParser | bool] = {}
        self.log: list[dict] = []

    def user_agent(self, url: str) -> str:
        host = urllib.parse.urlparse(url).hostname or ""
        if host == "sec.gov" or host.endswith(".sec.gov"):
            return os.environ.get(self.config["sec_user_agent_env"]) or self.config["user_agent"]
        return self.config["user_agent"]

    def get(self, url: str, max_bytes: int | None = None, kind: str = "page"):
        if not public_https_url(url):
            self.log.append({'kind': kind, 'url': '[rejected unsafe URL]', 'status': None, 'error': 'UnsafeURL'})
            return None, b'', '', ''
        self.limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent(url), "Accept-Language": "en-US,en;q=0.8"})
        req._capstone_kind = kind
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
        if not public_https_url(url):
            return False
        p = urllib.parse.urlparse(url)
        key = f"{p.scheme}://{p.netloc}"
        if key not in self.robots:
            status, body, _, _ = self.get(key + "/robots.txt", 500_000, kind="robots")
            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(body.decode("utf-8", "replace").splitlines())
                self.robots[key] = rp
            else:
                # Missing robots may be crawled under RFC9309. Explicit access
                # denial, server failure or no response stays fail-closed.
                self.robots[key] = status is not None and 400 <= status < 500 and status not in (401, 403, 429)
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
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
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
    """Broad retrieval hints: retain phrases and their constituent words.

    This intentionally has higher recall than Google's all-terms query rule.
    A match only sends an item for review; it does not establish relevance,
    event validity or a risk score.
    """
    index = defaultdict(set)
    for card, q in queries:
        for term in G.query_terms(q):
            terms = {term.lower()}
            if re.search(r"\s", term):
                terms.update(word.lower() for word in term.split())
            for keyword in sorted(terms):
                index[keyword].add(card)
    return dict(index)


def keyword_hits(text: str, index: dict[str, set[str]]) -> dict[str, list[str]]:
    hits = {}
    for kw, cards in index.items():
        # Plurals retain ordinary settlement/settlements notices without the
        # broader verb/inflection matches that would turn bank into banking.
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![A-Za-z0-9])", text, re.I):
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
        if self.buf is not None and not sum(self.depth.values()):
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
    url = item.get("publisher_url") or item["url"]
    if not public_https_url(url):
        return {"fulltext_status": "unsafe_publisher_url"}
    if urllib.parse.urlparse(url).hostname in ("news.google.com",) or not url.startswith("http"):
        return {"fulltext_status": "no_publisher_url"}
    if not client.allowed(url):
        return {"fulltext_status": "robots_disallowed"}
    status, body, final, ctype = client.get(url, config["max_article_bytes"], kind="article")
    if status in (401, 402, 403):
        return {"fulltext_status": "paywalled_or_forbidden_http_%s" % status}
    if status != 200 or not body:
        return {"fulltext_status": f"http_{status}"}
    if len(body) > config["max_article_bytes"]:
        return {"fulltext_status": "article_byte_limit_exceeded"}
    if body.startswith(b"%PDF"):
        if not shutil.which("pdftotext"):
            return {"fulltext_status": "pdf_extractor_unavailable"}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "article.pdf"
            source.write_bytes(body)
            try:
                text = subprocess.check_output(["pdftotext", "-layout", str(source), "-"], timeout=30, stderr=subprocess.DEVNULL).decode("utf-8", "replace")
            except (subprocess.SubprocessError, OSError):
                return {"fulltext_status": "pdf_extract_failed"}
        text, how = re.sub(r"\s+", " ", text).strip(), "ok_pdf"
        if len(text.split()) < 30:
            return {"fulltext_status": "pdf_extract_failed"}
    elif "html" in ctype.lower():
        text, how = extract(body.decode("utf-8", "replace"))
    else:
        return {"fulltext_status": "not_html"}
    if not text:
        return {"fulltext_status": how}
    original_words = len(text.split())
    text = truncate(text, config["fulltext_max_words"])
    name = sha(url.encode())[:24] + ".txt"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / name).write_text(text, encoding="utf-8")
    raw_path = cache_dir / "raw" / (sha(body) + (".pdf" if body.startswith(b"%PDF") else ".html"))
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(body)
    return {"fulltext_status": how, "text_sha256": sha(text.encode("utf-8")), "text_words": len(text.split()),
            "text_file": str((cache_dir / name).relative_to(PROJECT)), "text_truncated": original_words > config["fulltext_max_words"],
            "original_text_words": original_words, "content_source_url": final, "raw_sha256": sha(body),
            "raw_file": str(raw_path.relative_to(PROJECT))}


# ------------------------------------------------------------------ build
def _published(row):
    return _date(row.get("published_at_utc") or row.get("publication_date") or "")


def _publication_day(row):
    """Match the classifier's date precedence; collection time is never a fallback."""
    value = row.get("publication_date") or row.get("published_at_utc") or ""
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def window_candidates(rows, start=None, end=None):
    kept, excluded = [], []
    for row in rows:
        when = _publication_day(row)
        reason = "unknown_publication_date" if when is None else "outside_requested_window" if start and not start <= when <= end else None
        if reason:
            excluded.append({**{k: row.get(k, "") for k in ("document_id", "source_id", "feed_id", "publication_date", "published_at_utc", "title", "url")},
                             "reason": reason, "window_start": start.isoformat() if start else "", "window_end": end.isoformat() if end else ""})
        else:
            kept.append(row)
    return kept, excluded


def _merge_matches(target, other):
    """Keep collection hints and alternate-source provenance when records coalesce."""
    for field in ("matched_card_ids", "selected_for_card_ids"):
        target[field] = "|".join(sorted(set(filter(None, ((target.get(field) or "") + "|" + (other.get(field) or "")).split("|")))))
    for field in ("matched_queries", "matched_keywords"):
        merged = defaultdict(set)
        for row in (target, other):
            try:
                mapping = json.loads(row.get(field) or "{}")
            except (ValueError, TypeError):
                mapping = {}
            if isinstance(mapping, dict):
                for k, values in mapping.items():
                    if isinstance(values, list):
                        merged[k].update(str(v) for v in values)
        target[field] = json.dumps({k: sorted(v) for k, v in sorted(merged.items())}, ensure_ascii=False)
    if other.get("google_link") and not target.get("google_link"):
        target["google_link"] = other["google_link"]
    previous = json.loads(target.get("duplicate_evidence") or "[]")
    previous.append({k: other.get(k, "") for k in ("document_id", "source_id", "feed_id", "url", "google_link", "published_at_utc", "publication_date")})
    target["duplicate_evidence"] = json.dumps(previous, ensure_ascii=False)


def dedupe(rows: list[dict], threshold: float) -> tuple[list[dict], int]:
    """Prefer original provenance without coalescing distinct official records.

    Official notices often reuse titles/templates: different URLs retain their
    own evidence even within one day. Cross-publisher/Google title matches still
    require publication dates within two days; identical URLs may coalesce.
    """
    def official(row):
        return row["source_id"] in OFFICIAL_META or row.get("feed_id", "").startswith("official:")

    def rank(row):
        priority = 0 if official(row) else 1 if row["source_id"] == SOURCE_ID else 2
        pub = _published(row)
        return priority, -(pub.timestamp() if pub else 0)
    rows = sorted(rows, key=rank)
    kept, by_url, dup = [], {}, 0
    for r in rows:
        nt = G.norm_title(r["title"])
        when = _published(r)
        twin = by_url.get(r["url"])
        if twin is None and when:
            twin = next((k for k in kept if not (official(r) and official(k))
                         and _published(k) and abs(when - _published(k)) <= timedelta(days=2)
                         and difflib.SequenceMatcher(None, nt, G.norm_title(k["title"])).ratio() >= threshold), None)
        if twin is not None:
            dup += 1
            _merge_matches(twin, r)
            by_url[r["url"]] = twin
            continue
        by_url[r["url"]] = r; kept.append(r)
    return kept, dup


def official_rows(path: Path, queries, start: date, end: date):
    """Retrieve official candidates with strict and broad, separately labelled rules.

    Google's historical all-terms filter is unchanged. Its misses receive the
    same broad title/summary keyword recall as publisher RSS; matched_queries
    on fallback rows are query-origin hints, not proof of all-terms matching.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = set(json.loads(G.CONFIG.read_text())["official_source_ids"])
    eligible, scope_exclusions = window_candidates([r for r in rows if r.get("source_id") in ids], start, end)
    queries = list(queries)
    index = keyword_index(queries)
    query_keywords = [(card, query, set(keyword_index([(card, query)]))) for card, query in queries]
    kept, _ = G.prefilter_official(eligible, queries, ids, start, end)
    identity = lambda row: (row.get("source_id"), row.get("document_id"), row.get("url"))
    strict_ids = {identity(row) for row in kept}
    strict_count = len(kept)
    dropped = []
    for row in kept:
        hits = keyword_hits(html.unescape(row.get("title", "")) + "\n" + html.unescape(row.get("summary", "")), index)
        row["matched_keywords"] = json.dumps(hits, ensure_ascii=False)
        row["keep_rule"] = row.get("keep_rule") or "all_terms_official_title_summary_match"
    for original in eligible:
        if identity(original) in strict_ids:
            continue
        hits = keyword_hits(html.unescape(original.get("title", "")) + "\n" + html.unescape(original.get("summary", "")), index)
        if not hits:
            dropped.append({"document_id": original["document_id"], "source_id": original["source_id"],
                            "publication_date": _publication_day(original).isoformat(),
                            "title": original.get("title", ""), "url": original.get("url", ""),
                            "reason": "no broad card keyword matched title or summary"})
            continue
        hints = defaultdict(list)
        for card, query, keywords in query_keywords:
            if keywords.intersection(hits):
                hints[card].append(query)
        cards = "|".join(sorted({card for group in hits.values() for card in group}))
        kept.append({**original, "matched_keywords": json.dumps(hits, ensure_ascii=False),
                     "matched_card_ids": cards, "selected_for_card_ids": cards,
                     "matched_queries": json.dumps(dict(hints), ensure_ascii=False),
                     "keep_rule": "broad_official_keyword_match"})
    non_us = [row for row in kept if row["source_id"] in NON_US_OFFICIAL
              and not us_link(html.unescape(row.get("title", "")) + "\n" + html.unescape(row.get("summary", "")))]
    for row in non_us:
        dropped.append({"document_id": row["document_id"], "source_id": row["source_id"],
                        "publication_date": _publication_day(row).isoformat(), "title": row.get("title", ""), "url": row.get("url", ""),
                        "reason": "non-US official source without a US term (US, United States, SEC, CFTC, Federal Reserve, "
                                  "Treasury, DTCC, FICC, NSCC, DTC) in title or summary"})
    kept = [row for row in kept if row not in non_us]
    for row in kept:
        outlet, tier = OFFICIAL_META.get(row["source_id"], ("Official publisher", "official"))
        row.update(feed_id="official:" + row["source_id"], outlet=row.get("outlet") or outlet,
                   source_tier=row.get("source_tier") or tier)
    return kept, dropped, {"input_rows": len(rows), "kept": len(kept), "filtered_out": len(dropped),
                           "non_us_official_without_us_term": len(non_us),
                           "kept_strict_all_terms": strict_count, "kept_broad_keyword_fallback": len(kept) - strict_count,
                           "input_sha256": sha(path.read_bytes()), "window": [start.isoformat(), end.isoformat()],
                           "scope_exclusions": scope_exclusions,
                           "unsupported_source_rows": sum(r.get("source_id") not in ids for r in rows)}


def recall_filter(rows: list[dict], queries) -> tuple[list[dict], list[dict]]:
    """Strict all-terms query match on title + summary, else the broad keyword recall (same rules as official rows)."""
    queries = list(queries)
    index = keyword_index(queries)
    query_keywords = [(card, query, set(keyword_index([(card, query)]))) for card, query in queries]
    kept, dropped = [], []
    for r in rows:
        text = html.unescape(r.get("title", "")) + "\n" + html.unescape(r.get("summary", ""))
        strict, hits = G.matched_queries(text, queries), keyword_hits(text, index)
        if strict:
            cards = "|".join(sorted(strict))
            kept.append({**r, "matched_card_ids": cards, "selected_for_card_ids": cards, "matched_queries": json.dumps(strict, ensure_ascii=False),
                         "matched_keywords": json.dumps(hits, ensure_ascii=False), "keep_rule": "all_terms_title_summary_match"})
        elif hits:
            hints = defaultdict(list)
            for card, query, keywords in query_keywords:
                if keywords.intersection(hits):
                    hints[card].append(query)
            cards = "|".join(sorted({c for group in hits.values() for c in group}))
            kept.append({**r, "matched_card_ids": cards, "selected_for_card_ids": cards, "matched_queries": json.dumps(dict(hints), ensure_ascii=False),
                         "matched_keywords": json.dumps(hits, ensure_ascii=False), "keep_rule": "broad_keyword_match"})
        else:
            dropped.append({"document_id": r["document_id"], "source_id": r["source_id"], "published_at_utc": r.get("published_at_utc", ""),
                            "title": r.get("title", ""), "url": r.get("url", ""), "reason": "no card query or broad keyword matched title or summary"})
    return kept, dropped


def alphavantage_rows(path: Path) -> list[dict]:
    majors = set(json.loads(G.CONFIG.read_text())["major_media_outlets"])
    out = []
    for r in AV.load_items(path):
        out.append({"document_id": r["document_id"], "title": r["title"], "url": r["url"], "publication_date": "",
                    "published_at_utc": r["published_at_utc"], "summary": r["summary"], "source_id": AV.SOURCE_ID,
                    "feed_id": "alphavantage:" + r["request_topics"], "outlet": r["source"] or r["source_domain"],
                    "source_tier": "major_media" if r["source"] in majors else "other", "text_file": r["text_file"],
                    "text_sha256": r["summary_sha256"], "text_words": len(r["summary"].split()), "last_seen": ""})
    return out


def text_chars(row: dict) -> int:
    return len((row.get("summary") or "").strip()) if (row.get("summary") or "").strip() != (row.get("title") or "").strip() else 0


def av_dedupe(rows: list[dict], threshold: float) -> tuple[list[dict], list[dict]]:
    """Alpha Vantage items against Google / official / publisher items: same URL, or near-identical titles within two
    days. The version with more text is kept (ties keep the non-Alpha Vantage item); every match is recorded."""
    others = [r for r in rows if r["source_id"] != AV.SOURCE_ID]
    avs = [r for r in rows if r["source_id"] == AV.SOURCE_ID]
    removed, matches = set(), []
    for a in avs:
        na, wa = G.norm_title(a["title"]), _published(a)
        best = None
        for o in others:
            if id(o) in removed:
                continue
            if o["url"] == a["url"]:
                best = (o, "url", 1.0); break
            wo = _published(o)
            if wa and wo and abs(wa - wo) <= timedelta(days=2):
                ratio = difflib.SequenceMatcher(None, na, G.norm_title(o["title"])).ratio()
                if ratio >= threshold and (best is None or ratio > best[2]):
                    best = (o, "title", ratio)
        if best is None:
            continue
        o, how, ratio = best
        keep_av = text_chars(a) > text_chars(o)
        winner, loser = (a, o) if keep_av else (o, a)
        _merge_matches(winner, loser)
        removed.add(id(loser))
        matches.append({"av_document_id": a["document_id"], "av_title": a["title"], "av_url": a["url"], "other_source_id": o["source_id"],
                        "other_feed_id": o.get("feed_id", ""), "other_document_id": o["document_id"], "other_title": o["title"],
                        "other_url": o["url"], "match": how, "title_similarity": round(ratio, 3), "kept": "alphavantage" if keep_av else "other",
                        "av_text_chars": text_chars(a), "other_text_chars": text_chars(o)})
    return [r for r in rows if id(r) not in removed], matches


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--google", type=Path, default=PROJECT / "data/events/classifier_inputs/week_2026-11-02/google_news.csv")
    p.add_argument("--official", type=Path, help="Daily pipeline news.csv; card-query pre-filtered before classification")
    p.add_argument("--week-start", type=date.fromisoformat)
    p.add_argument("--week-end", type=date.fromisoformat)
    p.add_argument("--skip-fulltext", action="store_true")
    p.add_argument("--alphavantage", type=Path, help="alphavantage_items.csv from validation.alpha_vantage_news (summaries read from the local cache)")
    a = p.parse_args(argv)
    if bool(a.week_start) != bool(a.week_end):
        p.error("--week-start and --week-end must be provided together")
    if a.week_start and a.week_start > a.week_end:
        p.error("--week-start must not be after --week-end")
    config = json.loads(CONFIG.read_text())
    now = datetime.now(timezone.utc)
    out = a.out_dir or PROJECT / "data/events/classifier_inputs" / f"feeds_{now.date().isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = PROJECT / config["fulltext_cache_dir"]
    queries = G.load_queries()
    index = keyword_index(queries)
    client = Client(config)
    stats = defaultdict(Counter)
    rows, dropped, official_dropped, window_excluded, av_dropped, av_matches = [], [], [], [], [], []
    official_summary = {"status": "not_requested"}
    window_start = a.week_start or (G.last_full_week(datetime.now(ZoneInfo("America/New_York")).date()) if a.official else None)
    window_end = a.week_end or (window_start + timedelta(days=6) if window_start else None)
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
                rows.append({**g, "summary": g.get("summary", ""), "feed_id": "google_news_existing", "matched_keywords": json.dumps(hits, ensure_ascii=False),
                             "matched_card_ids": g.get("matched_card_ids", ""),
                             "last_seen": g.get("last_seen", "")})
    if a.official:
        incoming, official_dropped, official_summary = official_rows(a.official, queries, window_start, window_end)
        window_excluded.extend(official_summary.pop("scope_exclusions"))
        rows.extend(incoming)
        for row in incoming:
            stats[row["feed_id"]]["kept_prefilter"] += 1
    if a.alphavantage:
        incoming = alphavantage_rows(a.alphavantage)
        stats["alphavantage"]["fetched"] += len(incoming)
        incoming, av_dropped = recall_filter(incoming, queries)
        stats["alphavantage"]["kept_prefilter"] += len(incoming)
        stats["alphavantage"]["prefilter_dropped"] += len(av_dropped)
        rows.extend(incoming)
    rows, excluded = window_candidates(rows, window_start, window_end)
    window_excluded.extend(excluded)
    for row in window_excluded:
        stats[row.get("feed_id") or "official:" + row["source_id"]][row["reason"]] += 1
    rows, av_matches = av_dedupe(rows, config["title_similarity_threshold"])
    for m in av_matches:
        stats["alphavantage"][f"duplicate_of_{m['other_source_id']}_kept_{m['kept']}"] += 1
    rows, dups = dedupe(rows, config["title_similarity_threshold"])
    for r in rows:
        if r["source_id"] == AV.SOURCE_ID:            # summary only: the article page is never fetched
            ft = {"fulltext_status": "not_requested_alphavantage_summary"}
            r.update(ft); r["content_scope"] = "summary"
        else:
            ft = {"fulltext_status": "skipped"} if a.skip_fulltext else fetch_fulltext(r, client, config, cache_dir)
            r.update(ft)
            r["content_scope"] = ("article_excerpt" if ft.get("text_truncated") else "full_text") if ft.get("text_file") else ("summary" if r.get("summary") else "headline_only")
        stats[r["feed_id"]]["scope_" + r["content_scope"]] += 1
        stats[r["feed_id"]]["fulltext_" + ft["fulltext_status"]] += 1
    rows.sort(key=lambda r: (r.get("published_at_utc") or "", r["document_id"]))
    # No article bodies in the CSV: full text, excerpts and Alpha Vantage summaries stay in the local cache (hash kept).
    written = [{**r, "summary": ""} if r["content_scope"] in LOCAL_TEXT_SCOPES or r["source_id"] == AV.SOURCE_ID else r for r in rows]
    with (out / "classifier_input.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n"); w.writeheader(); w.writerows(written)
    G.write_csv(out / "alphavantage_prefilter_dropped.csv", av_dropped,
                ["document_id", "source_id", "published_at_utc", "title", "url", "reason"])
    G.write_csv(out / "alphavantage_dedup.csv", av_matches,
                ["av_document_id", "av_title", "av_url", "other_source_id", "other_feed_id", "other_document_id", "other_title", "other_url",
                 "match", "title_similarity", "kept", "av_text_chars", "other_text_chars"])
    with (out / "prefilter_dropped.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feed_id", "outlet", "published_at_utc", "title", "url"], lineterminator="\n"); w.writeheader(); w.writerows(dropped)
    G.write_csv(out / "official_prefilter_dropped.csv", official_dropped,
                ["document_id", "source_id", "publication_date", "title", "url", "reason"])
    G.write_csv(out / "outside_window.csv", window_excluded,
                ["document_id", "source_id", "feed_id", "publication_date", "published_at_utc", "title", "url", "reason", "window_start", "window_end"])
    dates = sorted(r["published_at_utc"][:10] for r in rows if r.get("published_at_utc"))
    summary = {"collected_utc": now.isoformat(timespec="seconds"), "user_agent": config["user_agent"],
               "sec_user_agent_override": bool(os.environ.get(config["sec_user_agent_env"])),
               "per_source": {k: dict(v) for k, v in stats.items()}, "duplicates_merged": dups, "items_to_classifier": len(rows),
               "scope_totals": dict(Counter(r["content_scope"] for r in rows)),
               "published_range": [dates[0], dates[-1]] if dates else None,
               "requests": [{"kind": k, "status": s, "n": n} for (k, s), n in Counter((e["kind"], e.get("status")) for e in client.log).items()],
               "robots": {h: ("parsed" if not isinstance(v, bool) else ("allow_all" if v else "disallow_all")) for h, v in client.robots.items()},
               "official_input": official_summary,
               "alphavantage": {"input": str(a.alphavantage) if a.alphavantage else None, "prefilter_dropped": len(av_dropped),
                                "duplicates_with_other_sources": len(av_matches),
                                "kept_alphavantage_version": sum(m["kept"] == "alphavantage" for m in av_matches)},
               "requested_window": [window_start.isoformat(), window_end.isoformat()] if window_start else None,
               "window_exclusions": dict(Counter(row["reason"] for row in window_excluded)),
               "config_sha256": sha(CONFIG.read_bytes()), "queries_sha256": sha(G.QUERIES.read_bytes())}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "request_log.json").write_text(json.dumps(client.log, indent=2) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()

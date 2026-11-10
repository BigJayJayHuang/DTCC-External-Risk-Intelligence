"""Weekly Google News RSS candidates plus a keyword pre-filter for the official feeds.

    python -m validation.google_news --week-start 2026-11-02 --official <news.csv> [--out-dir DIR] [--offline-from DIR]

Builds one classifier input CSV for llm_classifier.py (same columns as the daily news export, plus extras):

- Google News RSS: one search per (card_id, query) row in news_queries.csv, for one Monday-Sunday week
  (default: the last full week). Honest User-Agent, at most one request every 2 seconds, no browser.
  Items keep title, snippet, outlet, published time, the Google link and, when resolvable without a browser,
  the publisher URL. Deduplicated by URL and near-identical title; at most 25 items kept per card; every item
  records which card queries matched it. content_scope = "headline_snippet".
- Official feeds (Federal Register, DTCC, SEC/CFTC/Fed, FCA/ECB/ESMA/BIS): kept only when a card query matches
  title + summary with the same keywords; everything filtered out is listed.

Matched card_ids reach the classifier as hints only (query_hint_card_ids); the model still decides relevance.
No model is called here.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import email.utils
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
QUERIES = Path(__file__).with_name("news_queries.csv")
CONFIG = Path(__file__).with_name("google_news_config.json")
EXTRA_FIELDS = ["outlet", "outlet_url", "source_tier", "google_link", "publisher_url", "url_resolution",
                "matched_card_ids", "matched_queries", "selected_for_card_ids", "keep_rule", "headline_term_match",
                "content_scope"]
KEEP_ALL_TERMS, KEEP_MAJOR = "all_terms_headline_match", "major_media_outlet"
BASE_FIELDS = ["document_id", "title", "url", "publication_date", "published_at_utc", "summary", "source_id", "last_seen"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ window
def last_full_week(today: date) -> date:
    """Monday of the last Monday-Sunday week that has fully ended before `today`."""
    return today - timedelta(days=today.weekday() + 7)


def week_window(monday: date):
    if monday.weekday() != 0:
        raise ValueError("--week-start must be a Monday")
    return monday, monday + timedelta(days=6)


def search_query(query: str, monday: date) -> str:
    """Google operators are date-exclusive: after:<Sunday before> before:<Monday after> covers Mon..Sun."""
    start, end = week_window(monday)
    return f"{query} after:{(start - timedelta(days=1)).isoformat()} before:{(end + timedelta(days=1)).isoformat()}"


def feed_url(config: dict, query: str, monday: date) -> str:
    return config["feed_url"] + "?" + urllib.parse.urlencode({"q": search_query(query, monday), **config["feed_params"]})


# ------------------------------------------------------------------ queries and keyword matching
def load_queries(path: Path = QUERIES) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [(r["card_id"].strip(), r["query"].strip()) for r in csv.DictReader(f) if r["card_id"].strip() and r["query"].strip()]


def query_terms(query: str) -> list[str]:
    """Quoted phrases and bare words; all must appear (Google's default AND)."""
    return [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', query)]


def _term_regex(term: str) -> re.Pattern:
    # Case-insensitive, not inside a longer word; a plural/inflection suffix is allowed (spike/spikes/spiked).
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?:s|es|d|ed|ing)?(?![A-Za-z0-9])", re.I)


def query_matches(query: str, text: str) -> bool:
    return all(_term_regex(t).search(text) for t in query_terms(query))


def matched_queries(text: str, queries: list[tuple[str, str]]) -> dict[str, list[str]]:
    out = defaultdict(list)
    for card, q in queries:
        if query_matches(q, text):
            out[card].append(q)
    return dict(out)


# ------------------------------------------------------------------ HTTP (honest client, rate-limited)
class RateLimiter:
    def __init__(self, interval: float, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep, self.last = interval, clock, sleep, None

    def wait(self):
        if self.last is not None:
            remaining = self.interval - (self.clock() - self.last)
            if remaining > 0:
                self.sleep(remaining)
        self.last = self.clock()


def http_get(url: str, config: dict, limiter: RateLimiter):
    limiter.wait()
    req = urllib.request.Request(url, headers={"User-Agent": config["user_agent"], "Accept": "application/rss+xml, application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=config["timeout_seconds"]) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


# ------------------------------------------------------------------ RSS parsing
def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def resolve_publisher(google_link: str) -> tuple[str, str]:
    """Offline only: old-style article ids embed the publisher URL. Current ids do not, and the link
    redirects through a JavaScript page, so they stay unresolved (no browser, no undocumented API)."""
    try:
        aid = urllib.parse.urlparse(google_link).path.rsplit("/", 1)[-1]
        import base64
        raw = base64.urlsafe_b64decode(aid + "=" * (-len(aid) % 4))
        m = re.search(rb"https?://[\x21-\x7e]+", raw)
        if m:
            return m.group(0).decode("ascii"), "decoded_offline"
    except Exception:
        pass
    return "", "not_resolvable_without_browser"


def parse_rss(body: bytes, config: dict) -> list[dict]:
    items = []
    for it in ET.fromstring(body).findall("./channel/item"):
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None else ""
        outlet_url = src.attrib.get("url", "") if src is not None else ""
        raw_title = html.unescape((it.findtext("title") or "").strip())
        title = raw_title[: -len(" - " + outlet)].strip() if outlet and raw_title.endswith(" - " + outlet) else raw_title
        snippet = _strip_html(it.findtext("description") or "")
        for part in (raw_title, title, outlet):        # the feed description repeats headline and outlet
            if part and snippet.startswith(part):
                snippet = snippet[len(part):].strip()
            if part and snippet.endswith(part):
                snippet = snippet[: -len(part)].strip()
        published = email.utils.parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        link = (it.findtext("link") or "").strip()
        publisher_url, resolution = resolve_publisher(link)
        items.append({"title": title, "snippet": snippet, "outlet": outlet, "outlet_url": outlet_url,
                      "published_at_utc": published.isoformat(timespec="seconds"), "google_link": link,
                      "publisher_url": publisher_url, "url_resolution": resolution})
    return items


def source_tier(item: dict, config: dict) -> str:
    host = urllib.parse.urlparse(item.get("publisher_url") or item.get("outlet_url") or "").hostname or ""
    for suffix, tier in config["tier_by_outlet_host"].items():
        if host == suffix or host.endswith("." + suffix):
            return tier
    return "major_media" if item["outlet"] in set(config["major_media_outlets"]) else "other"


# ------------------------------------------------------------------ headline filter (Google matches loosely)
def headline_term_match(item: dict) -> str:
    """full: all terms of a query that returned the item appear in the headline; partial: some term does; none."""
    qs = [q for qlist in item["matches"].values() for q in qlist]
    if any(query_matches(q, item["title"]) for q in qs):
        return "full"
    return "partial" if any(_term_regex(t).search(item["title"]) for q in qs for t in query_terms(q)) else "none"


def headline_filter(items: list[dict], config: dict):
    """Keep items whose headline contains all terms of a query that returned them, plus every item from a
    major-media outlet whatever its headline overlap. Each kept item records the rule that kept it."""
    kept, dropped = [], []
    for i in items:
        i["headline_term_match"] = headline_term_match(i)
        if i["headline_term_match"] == "full":
            i["keep_rule"] = KEEP_ALL_TERMS
        elif source_tier(i, config) == "major_media":
            i["keep_rule"] = KEEP_MAJOR
        else:
            i["keep_rule"] = None
        (kept if i["keep_rule"] else dropped).append(i)
    return kept, dropped


# ------------------------------------------------------------------ dedup and per-card cap
def dedupe(hits: list[dict], threshold: float) -> list[dict]:
    """hits: one dict per (query, item). Merge by resolved URL, then by near-identical normalized title."""
    merged: list[dict] = []
    by_url: dict[str, dict] = {}
    for h in sorted(hits, key=lambda h: (h["published_at_utc"], h["google_link"])):
        key = h["publisher_url"] or h["google_link"]
        target = by_url.get(key)
        if target is None:
            nt = norm_title(h["title"])
            target = next((m for m in merged if difflib.SequenceMatcher(None, nt, m["_norm"]).ratio() >= threshold), None)
        if target is None:
            target = {**{k: v for k, v in h.items() if k not in ("card_id", "query")}, "_norm": norm_title(h["title"]),
                      "matches": defaultdict(list), "duplicates": []}
            merged.append(target)
        elif key != (target["publisher_url"] or target["google_link"]):
            target["duplicates"].append({"title": h["title"], "outlet": h["outlet"], "google_link": h["google_link"]})
        by_url[key] = target
        if h["query"] not in target["matches"][h["card_id"]]:
            target["matches"][h["card_id"]].append(h["query"])
    return merged


def cap_per_card(items: list[dict], cards: list[str], limit: int) -> list[dict]:
    """Keep at most `limit` items selected for each card: most matched queries first, then newest."""
    selected = {}
    for card in cards:
        mine = [i for i in items if card in i["matches"]]
        mine.sort(key=lambda i: (len(i["matches"][card]), i["published_at_utc"]), reverse=True)
        for i in mine[:limit]:
            selected.setdefault(id(i), i).setdefault("selected_for", []).append(card)
    return sorted(selected.values(), key=lambda i: (i["published_at_utc"], i["google_link"]))


# ------------------------------------------------------------------ official-feed pre-filter
def prefilter_official(rows: list[dict], queries, official_ids, start: date, end: date):
    kept, dropped = [], []
    for r in rows:
        pub = (r.get("publication_date") or r.get("published_at_utc") or "")[:10]
        if r.get("source_id") not in official_ids or not (start.isoformat() <= pub <= end.isoformat()):
            continue
        text = html.unescape(r.get("title", "")) + "\n" + html.unescape(r.get("summary", ""))
        m = matched_queries(text, queries)
        if m:
            kept.append({**r, "matched_card_ids": "|".join(sorted(m)), "matched_queries": json.dumps(m, ensure_ascii=False),
                         "selected_for_card_ids": "|".join(sorted(m))})
        else:
            dropped.append({"document_id": r["document_id"], "source_id": r["source_id"], "publication_date": pub,
                            "title": r.get("title", ""), "url": r.get("url", ""), "reason": "no card query matched title or summary"})
    return kept, dropped


# ------------------------------------------------------------------ build
def collect(config, queries, monday, out_dir: Path, fetch=None, offline_dir: Path | None = None, now=None):
    start, end = week_window(monday)
    now = now or datetime.now(timezone.utc)
    limiter = RateLimiter(config["min_request_interval_seconds"])
    raw_dir = out_dir / "google_news_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetch or (lambda url: http_get(url, config, limiter))
    hits, manifest = [], []
    for n, (card, q) in enumerate(queries):
        url = feed_url(config, q, monday)
        name = f"{n:02d}_{card}_{sha(q.encode())[:8]}.xml"
        if offline_dir is not None:
            status, body = 200, (offline_dir / name).read_bytes()
        else:
            status, body = fetch(url)
            if status == 200:
                (raw_dir / name).write_bytes(body)
        entry = {"card_id": card, "query": q, "url": url, "http_status": status, "bytes": len(body),
                 "sha256": sha(body) if body else None, "raw_file": f"google_news_raw/{name}" if status == 200 else None}
        if status == 429:
            entry["note"] = "rate limited; collection stopped"
            manifest.append(entry)
            break
        items = parse_rss(body, config) if status == 200 and body else []
        in_week = [i for i in items if start.isoformat() <= i["published_at_utc"][:10] <= end.isoformat()]
        entry.update(items=len(items), items_in_week=len(in_week))
        manifest.append(entry)
        hits += [{**i, "card_id": card, "query": q} for i in in_week]
    merged = dedupe(hits, config["title_similarity_threshold"])
    cards = list(dict.fromkeys(c for c, _ in queries))
    passed, filtered = headline_filter(merged, config) if config.get("headline_filter", True) else (merged, [])
    kept = cap_per_card(passed, cards, config["max_items_per_card"])
    rows = []
    for i in kept:
        url = i["publisher_url"] or i["google_link"]
        rows.append({"document_id": sha(url.encode()), "title": i["title"], "url": url,
                     "publication_date": "", "published_at_utc": i["published_at_utc"], "summary": i["snippet"],
                     "source_id": config["source_id"], "last_seen": now.isoformat(timespec="seconds"),
                     "outlet": i["outlet"], "outlet_url": i["outlet_url"], "source_tier": source_tier(i, config),
                     "google_link": i["google_link"], "publisher_url": i["publisher_url"], "url_resolution": i["url_resolution"],
                     "matched_card_ids": "|".join(sorted(i["matches"])), "matched_queries": json.dumps(dict(i["matches"]), ensure_ascii=False),
                     "selected_for_card_ids": "|".join(i["selected_for"]), "keep_rule": i.get("keep_rule") or "",
                     "headline_term_match": i.get("headline_term_match", ""), "content_scope": config["content_scope"]})
    stats = {"queries": len(queries), "requests": len(manifest), "http_errors": sum(e["http_status"] != 200 for e in manifest),
             "raw_hits_in_week": len(hits), "after_dedup": len(merged), "kept_after_cap": len(rows),
             "duplicates_merged": len(hits) - len(merged),
             "headline_filter": {"passed": len(passed), "dropped": len(filtered),
                                 "passed_by_rule": dict(Counter(i["keep_rule"] for i in passed)),
                                 "passed_by_headline_term_match": dict(Counter(i.get("headline_term_match") for i in passed))},
             "dropped_by_card_cap": len(passed) - len(rows),
             "kept_by_rule": dict(Counter(r["keep_rule"] for r in rows))}
    filtered_rows = [{"title": i["title"], "outlet": i["outlet"], "published_at_utc": i["published_at_utc"], "google_link": i["google_link"],
                      "matched_card_ids": "|".join(sorted(i["matches"])), "matched_queries": json.dumps(dict(i["matches"]), ensure_ascii=False),
                      "headline_term_match": i.get("headline_term_match", ""),
                      "reason": "headline lacks all terms of every query that returned it, and the outlet is not on the major-media list"}
                     for i in filtered]
    return rows, manifest, stats, filtered_rows


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    tz_today = datetime.now(ZoneInfo("America/New_York")).date()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--week-start", type=date.fromisoformat, default=last_full_week(tz_today), help="Monday (default: last full week)")
    p.add_argument("--official", type=Path, required=True, help="news.csv export of the daily pipeline")
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--offline-from", type=Path, help="re-parse saved raw RSS files instead of fetching")
    a = p.parse_args(argv)
    config, queries = json.loads(CONFIG.read_text()), load_queries()
    start, end = week_window(a.week_start)
    out = a.out_dir or PROJECT / "data/events/classifier_inputs" / f"week_{start.isoformat()}"
    out.mkdir(parents=True, exist_ok=True)
    prior = json.loads((out / "summary.json").read_text()) if a.offline_from and (out / "summary.json").exists() else {}
    collected = prior.get("collected_utc")
    now = datetime.fromisoformat(collected) if collected else None
    rows, manifest, stats, google_dropped = collect(config, queries, start, out, offline_dir=a.offline_from, now=now)
    with a.official.open(encoding="utf-8-sig", newline="") as f:
        official = list(csv.DictReader(f))
    kept, dropped = prefilter_official(official, queries, set(config["official_source_ids"]), start, end)
    fields = BASE_FIELDS + EXTRA_FIELDS
    write_csv(out / "google_news.csv", rows, fields)
    write_csv(out / "official_prefilter_kept.csv", kept, fields)
    write_csv(out / "official_prefilter_filtered_out.csv", dropped, ["document_id", "source_id", "publication_date", "title", "url", "reason"])
    write_csv(out / "classifier_input.csv", rows + kept, fields)
    write_csv(out / "google_news_filtered_out.csv", google_dropped,
              ["title", "outlet", "published_at_utc", "google_link", "matched_card_ids", "matched_queries", "headline_term_match", "reason"])
    per_card = {c: {"google_news": sum(c in r["matched_card_ids"].split("|") for r in rows),
                    "google_news_selected_for": sum(c in r["selected_for_card_ids"].split("|") for r in rows),
                    "official_kept": sum(c in r["matched_card_ids"].split("|") for r in kept)}
                for c in dict.fromkeys(c for c, _ in queries)}
    official_window = [r for r in official if r.get("source_id") in set(config["official_source_ids"])
                       and start.isoformat() <= (r.get("publication_date") or r.get("published_at_utc") or "")[:10] <= end.isoformat()]
    summary = {"week_start": start.isoformat(), "week_end": end.isoformat(),
               "collected_utc": collected or datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "reparsed_from_saved_raw_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") if a.offline_from else None,
               "google_news": stats, "google_news_per_outlet_tier": dict(Counter(r["source_tier"] for r in rows)),
               "google_news_url_resolution": dict(Counter(r["url_resolution"] for r in rows)),
               "official": {"rows_in_week": len(official_window), "by_source": dict(Counter(r["source_id"] for r in official_window)),
                            "kept": len(kept), "kept_by_source": dict(Counter(r["source_id"] for r in kept)), "filtered_out": len(dropped)},
               "classifier_input_rows": len(rows) + len(kept), "per_card": per_card,
               "official_input_sha256": sha(a.official.read_bytes()), "queries_sha256": sha(QUERIES.read_bytes()),
               "config_sha256": sha(CONFIG.read_bytes()), "content_scope": config["content_scope"]}
    if not a.offline_from:   # a re-parse keeps the original fetch record
        (out / "fetch_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()

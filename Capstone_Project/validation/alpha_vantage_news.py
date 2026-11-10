"""Alpha Vantage NEWS_SENTIMENT source for the weekly news run (one request per topic).

OFF BY DEFAULT. NEWS_SENTIMENT is a premium endpoint: the documentation marks it "Premium", and on 2026-11-10 a free key
got "This is a premium endpoint. You may subscribe to any of the premium plans ..." (see
data/events/weekly/2026-11-02/run_20261110T031359Z/inputs/alphavantage/). Enable it with
`weekly_news_run --alphavantage` only with a premium key in ALPHAVANTAGE_API_KEY.

    python -m validation.alpha_vantage_news --week-start 2026-11-02 --out-dir <dir>

- The API key is read only from the environment variable ALPHAVANTAGE_API_KEY. It is never printed, logged or written:
  request logs hold the parameters without it, and any error text is scrubbed of it.
- Official topic names (Alpha Vantage documentation, NEWS_SENTIMENT `topics`): financial_markets ("Financial Markets"),
  economy_monetary ("Economy - Monetary Policy"), finance ("Finance"), economy_macro ("Economy - Macro/Overall").
  Several topics in one request are ANDed by the API, so each topic is its own request.
- time_from / time_to cover the Monday 00:00 to Sunday 23:59 week (YYYYMMDDTHHMM, UTC as in the documentation),
  sort=LATEST, limit=1000.
- Free-tier limits: at least 12.5 s between requests (5 per minute) and at most 25 per UTC day, counted in a local
  usage ledger. If the API answers with a message instead of a feed (rate limit, premium notice), the remaining topics
  are not requested.
- Kept per article: title, url, source, source_domain, time_published, summary and topic names (sentiment scores are
  ignored). Summaries and raw responses stay in the git-ignored data/events/fulltext_cache/alphavantage/ folder; the
  run folder gets alphavantage_items.csv (no summary, only its sha256) and alphavantage_requests.json.
"""
import argparse, csv, hashlib, json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ID = "alphavantage_news"
KEY_ENV = "ALPHAVANTAGE_API_KEY"
ENDPOINT = "https://www.alphavantage.co/query"
TOPICS = ["financial_markets", "economy_monetary", "finance", "economy_macro"]
MIN_INTERVAL_SECONDS = 12.5          # 5 requests per minute
DAILY_LIMIT = 25
CACHE = PROJECT / "data/events/fulltext_cache/alphavantage"     # git-ignored (data/events/fulltext_cache/)
ITEM_FIELDS = ["document_id", "title", "url", "source", "source_domain", "time_published", "published_at_utc",
               "summary_sha256", "summary_chars", "topics", "request_topics", "text_file"]
USER_AGENT = json.loads((Path(__file__).with_name("publisher_feeds_config.json")).read_text())["user_agent"]


class KeyMissing(SystemExit):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def api_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise KeyMissing(f"{KEY_ENV} is not set; the Alpha Vantage source needs it (nothing was requested).")
    return key


def scrub(text: str, key: str) -> str:
    return str(text).replace(key, "[key]") if key else str(text)


def http_fetch(params: dict, key: str, timeout: int = 60) -> tuple[int, bytes]:
    """The key exists only in this local URL; the URL is never logged or returned."""
    url = ENDPOINT + "?" + urllib.parse.urlencode({**params, "apikey": key})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except urllib.error.URLError as e:
        raise RuntimeError(scrub(f"Alpha Vantage request failed: {e.reason}", key)) from None


class Usage:
    """Per-UTC-day request counter in the local cache; refuses request 26."""
    def __init__(self, path: Path, today: str):
        self.path, self.today = Path(path), today
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    @property
    def used_today(self) -> int:
        return int(self.data.get(self.today, 0))

    def reserve(self):
        if self.used_today >= DAILY_LIMIT:
            raise SystemExit(f"Alpha Vantage daily limit reached ({DAILY_LIMIT} requests on {self.today} UTC)")
        self.data[self.today] = self.used_today + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")


def published_utc(value: str) -> str:
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat(timespec="seconds")


def collect(monday: date, out_dir: Path, *, fetch=http_fetch, key: str | None = None, cache: Path = CACHE,
            sleep=time.sleep, clock=time.monotonic, now: datetime | None = None) -> dict:
    """Requests each topic once for the week; returns {"rows": [...with summary in memory...], "stats": {...}}."""
    key = key if key is not None else api_key()
    now = now or datetime.now(timezone.utc)
    sunday = monday + timedelta(days=6)
    week_cache = Path(cache) / monday.isoformat()
    week_cache.mkdir(parents=True, exist_ok=True)
    usage = Usage(Path(cache) / "usage.json", now.date().isoformat())
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    log, items, last, stopped = [], {}, None, False
    for n, topic in enumerate(TOPICS):
        params = {"function": "NEWS_SENTIMENT", "topics": topic, "time_from": monday.strftime("%Y%m%dT0000"),
                  "time_to": sunday.strftime("%Y%m%dT2359"), "sort": "LATEST", "limit": "1000"}
        stopped = stopped or any(e.get("stop") for e in log)
        if stopped:
            log.append({"topic": topic, "params": params, "status": "not_requested", "reason": "earlier response was not a news feed"})
            continue
        if last is not None:
            wait = MIN_INTERVAL_SECONDS - (clock() - last)
            if wait > 0:
                sleep(wait)
        usage.reserve()
        last = clock()
        entry = {"topic": topic, "params": params, "requested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            status, body = fetch(params, key)
        except Exception as e:                       # never let a message carry the key
            entry.update(status="request_error", error=scrub(str(e), key), stop=True); log.append(entry); continue
        entry["http_status"] = status
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except (ValueError, UnicodeDecodeError):
            data = {}
        if status != 200 or not isinstance(data.get("feed"), list):
            message = next((data[k] for k in ("Information", "Note", "Error Message") if k in data), "") if isinstance(data, dict) else ""
            entry.update(status="no_feed", message=scrub(message, key)[:500], stop=True); log.append(entry); continue
        (week_cache / f"raw_{topic}.json").write_bytes(body)            # raw response (summaries) stays local
        entry.update(status="ok", items=len(data["feed"]), raw_sha256=sha(body))
        for a in data["feed"]:
            url, title = (a.get("url") or "").strip(), (a.get("title") or "").strip()
            if not url or not title or not a.get("time_published"):
                entry["skipped_incomplete"] = entry.get("skipped_incomplete", 0) + 1
                continue
            row = items.setdefault(url, {"title": title, "url": url, "source": a.get("source", ""), "source_domain": a.get("source_domain", ""),
                                         "time_published": a["time_published"], "published_at_utc": published_utc(a["time_published"]),
                                         "summary": (a.get("summary") or "").strip(),
                                         "topics": sorted({t.get("topic", "") for t in a.get("topics") or [] if t.get("topic")}),
                                         "request_topics": []})
            row["request_topics"].append(topic)
        log.append(entry)
    rows = []
    for url, r in sorted(items.items(), key=lambda kv: (kv[1]["published_at_utc"], kv[0])):
        doc = sha(url.encode())
        text_file = week_cache / f"{doc[:24]}.summary.txt"
        text_file.write_text(r["summary"], encoding="utf-8")
        rows.append({**r, "document_id": doc, "summary_sha256": sha(r["summary"].encode("utf-8")), "summary_chars": len(r["summary"]),
                     "text_file": str(text_file.relative_to(PROJECT)) if text_file.is_relative_to(PROJECT) else str(text_file)})
    with (out_dir / "alphavantage_items.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ITEM_FIELDS, extrasaction="ignore", lineterminator="\n"); w.writeheader()
        w.writerows({**r, "topics": "|".join(r["topics"]), "request_topics": "|".join(r["request_topics"])} for r in rows)
    stats = {"requests_this_run": sum(1 for e in log if e["status"] != "not_requested"), "requests_used_today_utc": usage.used_today,
             "daily_limit": DAILY_LIMIT, "per_topic": {e["topic"]: e.get("items", e["status"]) for e in log},
             "unique_articles": len(rows), "with_summary": sum(1 for r in rows if r["summary"]),
             "window_utc": [params_from(monday), params_to(monday)], "errors": [e for e in log if e["status"] not in ("ok",)]}
    (out_dir / "alphavantage_requests.json").write_text(json.dumps({"requests": log, "stats": stats}, indent=2, ensure_ascii=False) + "\n")
    return {"rows": rows, "stats": stats, "items_csv": out_dir / "alphavantage_items.csv"}


def params_from(monday: date) -> str:
    return monday.strftime("%Y%m%dT0000")


def params_to(monday: date) -> str:
    return (monday + timedelta(days=6)).strftime("%Y%m%dT2359")


def load_items(path: Path) -> list[dict]:
    """Rows from alphavantage_items.csv with the summary read back from the local cache (sha256 checked)."""
    out = []
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            cache_path = (PROJECT / r["text_file"]).resolve()
            cache_path.relative_to(PROJECT.resolve())                  # must stay inside the project
            summary = cache_path.read_text(encoding="utf-8")
            if sha(summary.encode("utf-8")) != r["summary_sha256"]:
                raise ValueError("Alpha Vantage summary cache does not match its sha256 for " + r["url"])
            out.append({**r, "summary": summary})
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--week-start", type=date.fromisoformat, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args(argv)
    if a.week_start.weekday() != 0:
        p.error("--week-start must be a Monday")
    print(json.dumps(collect(a.week_start, a.out_dir)["stats"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

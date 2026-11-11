"""Display order of a card's related news (standard library only; used by docs/data/export_risk_output.py).

Display-only: nothing here changes scores, statuses, events or narratives, and no item is removed. The dashboard detail
view shows the top items (config top_n, 5) and lists every item under "Show all". Deterministic, no model:

  0. items the reviewed card front cites (pinned, always at the top): the headline source, then items whose outlet
     what_happened names (see validation/card_front_checks.cited_news);
  1. then, in tiers: priority outlet with a card keyword; card keyword only; priority outlet only; neither. A card
     keyword is a query keyword of the card (validation/news_queries.csv; each quoted phrase is one keyword, each bare
     word another, matched as the Google filter matches them: case-insensitive, whole word, plural or inflection suffix
     allowed); priority outlets are in validation/related_news_display.json;
  2. within a tier, newest first (publication time from the week's committed collection files, matched by URL);
     undated last; ties keep the original order.

Items matching any exclude term (political commentary, crypto, gold, oil, sterling, currency …) never enter the top,
even when the title has a card keyword, unless they are pinned.
Labelled items (e.g. "membership/onboarding") are summarised in one line at the top of the section and are not ranked.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CONFIG = HERE / "related_news_display.json"
QUERIES = HERE / "news_queries.csv"


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def query_terms(query: str) -> list[str]:
    """Quoted phrases and bare words (the same parsing as validation.google_news.query_terms)."""
    return [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', query)]


def term_regex(term: str) -> re.Pattern:
    """Case-insensitive, not inside a longer word; a plural / inflection suffix is allowed (as validation.google_news)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?:s|es|d|ed|ing)?(?![A-Za-z0-9])", re.I)


def card_keywords(path: Path = QUERIES) -> dict[str, list[str]]:
    """card_id -> query keywords, in file order, without duplicates."""
    out: dict[str, list[str]] = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for t in query_terms(row["query"]):
                if t.lower() not in (k.lower() for k in out.setdefault(row["card_id"], [])):
                    out[row["card_id"]].append(t)
    return out


def week_dates(week: str, root: Path = PROJECT / "data" / "events") -> dict[str, str]:
    """url -> earliest publication time (ISO, UTC) in the week's committed collection files."""
    files = sorted(list((root / "classifier_inputs" / f"week_{week}").glob("*.csv")) +
                   list((root / "weekly" / week).glob("*/inputs/**/*.csv")))
    dates: dict[str, str] = {}
    for f in files:
        with f.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                url, when = row.get("url") or "", row.get("published_at_utc") or row.get("publication_date") or ""
                if url and when and (url not in dates or when < dates[url]):
                    dates[url] = when
    return dates


def first_match(title: str, terms) -> str | None:
    return next((t for t in terms if term_regex(t).search(title or "")), None)


def priority_outlet(outlet: str, config: dict) -> str | None:
    o = (outlet or "").strip().lower()
    return next((name for name, aliases in config["priority_outlets"].items() if o in aliases), None)


def rank(related: list[dict], keywords: list[str], dates: dict[str, str], config: dict, pinned=()) -> list[dict]:
    """One entry per related-news item, in display order: {index, top, pinned, published, keyword, priority_outlet,
    excluded, label, reason}. Pinned items first (cited by the reviewed card front: [(index, why)], in that order),
    then ranked items (top ones at the start), then excluded ones, then labelled ones. Pinned items are always in the
    top, even when excluded or labelled."""
    entries = []
    for i, n in enumerate(related or []):
        title, label = n.get("title") or "", n.get("label") or None
        kw = first_match(title, keywords)
        outlet = priority_outlet(n.get("outlet") or "", config)
        when = dates.get(n.get("url") or "")
        excluded = None
        for group, terms in config["exclude"].items():           # absolute: a card keyword does not lift it
            hit = first_match(title, terms)
            if hit:
                excluded = f"{group} (“{hit}”)"; break
        entries.append({"index": i, "top": False, "pinned": False, "published": when[:10] if when else None, "keyword": kw,
                        "priority_outlet": outlet, "excluded": excluded, "label": label, "_when": when or ""})
    why = {}
    for i, w in pinned:
        if 0 <= i < len(entries) and i not in why:
            why[i] = w
    pins = [entries[i] for i in why]
    for e in pins:
        e["pinned"] = True
    rest = [e for e in entries if not e["pinned"]]
    ranked = _order([e for e in rest if not e["label"] and not e["excluded"]])
    excluded = _order([e for e in rest if not e["label"] and e["excluded"]])
    labelled = _order([e for e in rest if e["label"]], by_signal=False)
    for e in (pins + ranked)[:max(config.get("top_n", 5), len(pins))]:
        e["top"] = True
    for e in entries:
        parts = []
        if e["pinned"]:
            parts.append(f"cited by the reviewed card front ({why[e['index']]})")
        elif e["label"]:
            parts.append(f"labelled {e['label']} (summarised at the top)")
        elif e["excluded"]:
            parts.append("excluded from the top: " + e["excluded"])
        else:
            parts.append(f"card keyword “{e['keyword']}”" if e["keyword"] else "no card keyword")
            parts.append(f"priority outlet ({e['priority_outlet']})" if e["priority_outlet"] else "not a priority outlet")
        parts.append(f"published {e['published']}" if e["published"] else "publication date unknown")
        e["reason"] = "; ".join(parts)
        del e["_when"]
    return pins + ranked + excluded + labelled


TIERS = {(True, True): 0, (True, False): 1, (False, True): 2, (False, False): 3}   # (keyword, priority outlet) -> tier


def _order(entries: list[dict], by_signal: bool = True) -> list[dict]:
    """Tiers (priority outlet with a card keyword; keyword only; priority outlet only; neither), then newest first
    (undated last), ties in original order (stable sorts)."""
    out = sorted(entries, key=lambda e: e["index"])
    out = sorted(out, key=lambda e: e["_when"], reverse=True)          # "" (undated) sorts last; stable for equal times
    return sorted(out, key=lambda e: TIERS[(e["keyword"] is not None, e["priority_outlet"] is not None)]) if by_signal else out


def label_sources(related: list[dict], config: dict) -> list[str]:
    """Source names implied by labelled related news, e.g. "DTCC member notices" for membership/onboarding."""
    labels = {n.get("label") for n in related or [] if n.get("label")}
    return [name for label, name in config.get("label_sources", {}).items() if label in labels]

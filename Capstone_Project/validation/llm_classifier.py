"""Review-only Bedrock news classification; never modifies the event register.

python -m validation.llm_classifier --start YYYY-MM-DD --end YYYY-MM-DD --dry-run [--prompt-version v1.3 --prompt-cache on]
Authentication: BEDROCK_PROFILE (default devx-bedrock), using AWS SSO.
Prompt v1.2 (default, unchanged) puts everything in the system prompt. Prompt v1.3 puts the static rules and card
catalog in the system prompt followed by a Converse cachePoint, and the per-item recent events and article in the
user message.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import os
import re
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from . import event_scoring as E

PROJECT = Path(__file__).resolve().parents[1]
PROMPT = Path(__file__).with_name("llm_event_classifier_prompt.md")
PROMPT_V13 = Path(__file__).with_name("llm_event_classifier_prompt_v1.3.md")
PROMPT_V14 = Path(__file__).with_name("llm_event_classifier_prompt_v1.4.md")
PROMPT_V15 = Path(__file__).with_name("llm_event_classifier_prompt_v1.5.md")
PROMPT_V16 = Path(__file__).with_name("llm_event_classifier_prompt_v1.6.md")
PROMPT_FILES = {"v1.2": PROMPT, "v1.3": PROMPT_V13, "v1.4": PROMPT_V14, "v1.5": PROMPT_V15, "v1.6": PROMPT_V16}
SPLIT_PROMPTS = {"v1.3", "v1.4", "v1.5", "v1.6"}   # static system text + cachePoint, per-item user message
EVENT_TYPE_PROMPTS = {"v1.5", "v1.6"}               # prompts that define event_type (Amendment D)
GEO_PROMPTS = {"v1.6"}                              # prompts that define geography and new_information
GEOGRAPHIES = ["us", "non_us_with_us_link", "non_us"]
EVENT_TYPES = ["market_move", "regulatory", "firm_specific", "operational", "cyber", "other"]
HEADLINE_SCOPES = {"headline_only", "headline_snippet"}
CONFIG = Path(__file__).with_name("llm_classifier_config.json")
REGISTER = PROJECT / "data/events/event_register.csv"
MAJOR = PROJECT / "data/events/major_participants.csv"
NEWS = PROJECT / "capstone_database/exports/news.csv"
TOOL = "submit_event_classification"
MILLION = Decimal(1_000_000)
CSV_FIELDS = [
    "event_id", "document_id", "is_relevant", "same_as_event_id", "title", "summary",
    "card_ids", "certainty", "reach", "reach_basis", "named_participants",
    "announced_date", "effect_date", "stage", "source_tier", "outlet", "source_url",
    "url", "evidence_quote", "evidence_quotes", "llm_confidence", "notes", "event_type", "geography", "new_information", "published_date",
    "entered_by", "needs_review", "validation_passed", "validation_reasons",
    "original_certainty", "original_reach", "model_id", "base_model_id", "region",
    "prompt_version", "input_tokens", "output_tokens", "cache_read_input_tokens",
    "cache_write_input_tokens", "estimated_cost_usd", "response_mode", "fence_fallback",
    "attempts", "content_scope", "review_basis", "article_file", "raw_output_file",
]
GOOGLE_NEWS_SOURCE = "google_news_rss"
PUBLISHER_SOURCE = "publisher_rss"
COLLECTOR_SCOPES = {"full_text", "summary", "headline_only"}
HINT_NOTE = ("Card ids whose keyword search query matched this item. Retrieval hint only; "
             "it is not a relevance decision or a card assignment.")
SOURCE_NAMES = {
    "sec_press": ("SEC", "regulator"), "cftc_press": ("CFTC", "regulator"),
    "fed_press": ("Federal Reserve", "regulator"), "esma_news": ("ESMA", "regulator"),
    "fca_rss": ("FCA", "regulator"), "federal_register": ("Federal Register", "official"),
    "dtcc_notice_feed": ("DTCC", "dtcc"), "dtcc_insight_20261014": ("DTCC", "dtcc"),
    "bis_press": ("BIS", "official"), "ecb_press": ("ECB", "official"),
}


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def public_path(path: Path) -> str:
    """Only portable project-relative paths enter tracked artifacts."""
    try:
        return path.resolve().relative_to(PROJECT.resolve()).as_posix()
    except ValueError:
        return path.name


def publication_date(row: dict) -> str:
    # Never substitute last_seen/ingestion time for publication time.
    value = row.get("publication_date", "").strip() or row.get("published_at_utc", "").strip()
    return date.fromisoformat(value[:10]).isoformat()


def load_news(path: Path, start: date, end: date, limit: int | None):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    chosen, rejected, seen, latest, outside = [], Counter(), set(), None, Counter()
    for row in rows:
        try:
            published = publication_date(row)
        except ValueError:
            rejected["missing_or_invalid_publication_date"] += 1
            continue
        latest = max(latest or published, published)
        if not start.isoformat() <= published <= end.isoformat():
            outside[row.get("feed_id") or row.get("source_id") or "unknown"] += 1
            continue
        if not row.get("url") or not row.get("title"):
            rejected["missing_title_or_url"] += 1
            continue
        identity = row.get("document_id") or row["url"]
        if identity in seen or row["url"] in seen:
            rejected["duplicate_document_or_url"] += 1
            continue
        seen.update([identity, row["url"]])
        title = html.unescape(row["title"]).strip()
        summary = html.unescape(row.get("summary", "")).strip()
        has_summary = bool(summary and summary != title)
        scope = "publisher_feed_summary" if has_summary else "headline_only"
        text = title + ("\n\n" + summary if has_summary else "")
        outlet, tier = SOURCE_NAMES.get(row.get("source_id"), (urlparse(row["url"]).hostname or "unknown", "other"))
        if row.get("source_id") == GOOGLE_NEWS_SOURCE:
            # Outlet and tier come from the collector (google_news.py), never from the model.
            outlet, tier, scope = row.get("outlet") or outlet, row.get("source_tier") or "other", "headline_snippet"
        if row.get("source_id") == PUBLISHER_SOURCE:
            outlet, tier = row.get("outlet") or outlet, row.get("source_tier") or "other"
        row_scope = (row.get("content_scope") or "").strip()
        if row_scope in COLLECTOR_SCOPES:   # set by publisher_feeds.py
            scope = row_scope
            if scope == "full_text":
                # Full text lives only in the git-ignored cache; the CSV holds its hash.
                body = (PROJECT / row["text_file"]).read_text(encoding="utf-8")
                if sha(body.encode("utf-8")) != row.get("text_sha256"):
                    raise ValueError("full-text cache does not match text_sha256 for " + row["url"])
                text = title + "\n\n" + body
            elif scope == "summary" and has_summary:
                text = title + "\n\n" + summary
            else:
                scope, text = "headline_only", title
        article = {"document_id": identity, "title": title, "url": row["url"],
                   "published_date": published, "source_id": row.get("source_id", ""),
                   "outlet": outlet, "source_tier": tier, "content_scope": scope, "text": text}
        hints = [c for c in (row.get("matched_card_ids") or "").split("|") if c]
        if hints:   # keyword-search hints only; the model still decides relevance and cards
            article["query_hint_card_ids"] = hints
            article["query_hint_note"] = HINT_NOTE
        chosen.append(article)
    chosen.sort(key=lambda r: (r["published_date"], r["document_id"]))
    available = len(chosen)
    if limit is not None:
        chosen = chosen[:limit]
    return chosen, {"source_rows": len(rows), "eligible_articles": available,
                    "selected_articles": len(chosen), "input_rejections": dict(rejected),
                    "outside_date_window_by_source": dict(outside),
                    "latest_publication_date": latest}


def prompt_parts(path: Path):
    source = path.read_text(encoding="utf-8")
    parts = source.split("\n---\n", 2)
    if len(parts) != 3:
        raise ValueError("Prompt must retain its system-body/catalog delimiters")
    body = parts[1].strip()
    catalog = parts[2][parts[2].index("| card_id"):].strip()
    cards = re.findall(r"^\| ((?:FICC|ECS|XE)-[A-Z0-9-]+) \|", catalog, re.M)
    if len(set(cards)) != 16:
        raise ValueError("Expected the original 16-card catalog")
    return body, catalog, set(cards), "event-rubric-v1.2:" + sha(path.read_bytes())[:12]


def prompt_parts_v13(path: Path = PROMPT_V13, label: str = "v1.3"):
    """v1.3: header / static system text / per-item user template / card catalog. Returns the system text with the
    catalog filled in (identical for every item, so it can be cached), the user template, cards and version."""
    parts = path.read_text(encoding="utf-8").split("\n---\n")
    if len(parts) != 4:
        raise ValueError("Prompt v1.3 must have header, system, user and catalog sections")
    system_body, user_template = parts[1].strip(), parts[2].strip()
    start = parts[3].index("Scope note:") if "Scope note:" in parts[3] else parts[3].index("| card_id")   # catalog v2 scope note
    catalog = parts[3][start:].strip()
    cards = re.findall(r"^\| ((?:FICC|ECS|XE)-[A-Z0-9-]+) \|", catalog, re.M)
    if len(set(cards)) != 16:
        raise ValueError("Expected the original 16-card catalog")
    if any(k in system_body for k in ("{RECENT_EVENTS}", "{ARTICLE}")) or "{CARD_CATALOG}" in user_template \
            or system_body.count("{CARD_CATALOG}") != 1 or not all(k in user_template for k in ("{RECENT_EVENTS}", "{ARTICLE}")):
        raise ValueError("Static system text and per-item user template are not separated as required")
    return system_body.replace("{CARD_CATALOG}", catalog), user_template, set(cards), f"classifier-prompt-{label}:" + sha(path.read_bytes())[:12]


def render_user_v13(template: str, register: list[dict], article: dict):
    recent = [r for r in register if r["announced_date"] and r["announced_date"] <= article["published_date"]]
    values = {"RECENT_EVENTS": json.dumps(recent, ensure_ascii=False), "ARTICLE": json.dumps(article, ensure_ascii=False)}
    return re.sub(r"\{(RECENT_EVENTS|ARTICLE)\}", lambda m: values[m[1]], template), {r["event_id"] for r in recent}


def load_register(path: Path) -> list[dict]:
    events = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        events.append({"event_id": row["event_id"], "title": row["title"],
                       "card_ids": (row.get("card_ids") or row.get("chain_id", "")).split("|"),
                       "announced_date": row.get("announced_date", ""), "effect_date": row.get("effect_date", "")})
    return events


def render_prompt(body: str, catalog: str, register: list[dict], article: dict):
    recent = [r for r in register if r["announced_date"] and r["announced_date"] <= article["published_date"]]
    values = {"CARD_CATALOG": catalog, "RECENT_EVENTS": json.dumps(recent, ensure_ascii=False),
              "ARTICLE": json.dumps(article, ensure_ascii=False)}
    # One pass: literal placeholder-looking text in an article is never interpolated.
    prompt = re.sub(r"\{(CARD_CATALOG|RECENT_EVENTS|ARTICLE)\}", lambda m: values[m[1]], body)
    return prompt, {r["event_id"] for r in recent}


def output_schema(cards: set[str], event_type: bool = False, geo: bool = False) -> dict:
    properties = {
        "is_relevant": {"const": True}, "same_as_event_id": {"type": ["string", "null"]},
        "title": {"type": "string"}, "summary": {"type": "string"},
        "card_ids": {"type": "array", "items": {"type": "string", "enum": sorted(cards)}, "minItems": 1},
        "certainty": {"type": "integer", "enum": [0, 1, 2]}, "reach": {"type": "integer", "enum": [0, 1, 2]},
        "reach_basis": {"type": "string", "enum": ["market_wide", "business_line", "major_participant", "group", "single"]},
        "named_participants": {"type": "array", "items": {"type": "string"}},
        "announced_date": {"type": ["string", "null"], "format": "date"},
        "effect_date": {"type": ["string", "null"], "format": "date"},
        "stage": {"anyOf": [{"type": "integer", "enum": [1, 2, 3, 4]}, {"type": "null"}]},
        "source_tier": {"type": "string", "enum": ["regulator", "dtcc", "issuer_filing", "official", "major_media", "other"]},
        "outlet": {"type": "string"}, "url": {"type": "string"},
        "evidence_quotes": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "confidence": {"type": "number"}, "notes": {"type": "string"},
    }
    if event_type:
        properties["event_type"] = {"type": "string", "enum": EVENT_TYPES}
    if geo:
        properties["geography"] = {"type": "string", "enum": GEOGRAPHIES}
        properties["new_information"] = {"type": ["boolean", "null"]}
    relevant = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    irrelevant = {"type": "object", "properties": {"is_relevant": {"const": False}, "notes": {"type": "string"}},
                  "required": ["is_relevant", "notes"], "additionalProperties": False}
    # The transport envelope permits the prompt's two-field irrelevant record
    # without making 17 fields optional (Bedrock strict mode allows only 12).
    return {"type": "object", "properties": {"classification": {"anyOf": [relevant, irrelevant]}},
            "required": ["classification"], "additionalProperties": False}


FLAT_TOOL_DESCRIPTION = ("Submit the classification record specified by the system prompt. Every field is required: "
                         "when is_relevant is false, set every field except notes to null.")


def output_schema_flat(cards: set[str], event_type: bool = False, geo: bool = False) -> dict:
    """One flat object: every field always present, null where it does not apply. No anyOf/oneOf/if-then/const."""
    enum_or_null = lambda kind, values: {"type": [kind, "null"], "enum": [*values, None]}
    properties = {
        "is_relevant": {"type": "boolean"},
        "same_as_event_id": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]}, "summary": {"type": ["string", "null"]},
        "card_ids": {"type": ["array", "null"], "items": {"type": "string", "enum": sorted(cards)}},
        "certainty": enum_or_null("integer", [0, 1, 2]), "reach": enum_or_null("integer", [0, 1, 2]),
        "reach_basis": enum_or_null("string", ["market_wide", "business_line", "major_participant", "group", "single"]),
        "named_participants": {"type": ["array", "null"], "items": {"type": "string"}},
        "announced_date": {"type": ["string", "null"], "format": "date"},
        "effect_date": {"type": ["string", "null"], "format": "date"},
        "stage": enum_or_null("integer", [1, 2, 3, 4]),
        "source_tier": enum_or_null("string", ["regulator", "dtcc", "issuer_filing", "official", "major_media", "other"]),
        "outlet": {"type": ["string", "null"]}, "url": {"type": ["string", "null"]},
        "evidence_quotes": {"type": ["array", "null"], "items": {"type": "string"}},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
    }
    if event_type:
        properties["event_type"] = enum_or_null("string", EVENT_TYPES)
    if geo:
        properties["geography"] = enum_or_null("string", GEOGRAPHIES)
        properties["new_information"] = {"type": ["boolean", "null"]}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


RELEVANT_REQUIRED = ["title", "summary", "card_ids", "certainty", "reach", "reach_basis", "announced_date",
                     "effect_date", "source_tier", "outlet", "url", "evidence_quotes", "confidence"]
OPTIONAL_LIST_FIELDS = ["named_participants"]    # optional: null means none named


CORE_FIELDS = ["is_relevant", "card_ids", "certainty", "reach", "evidence_quotes"]   # must be present (value may be null)


def prepare_flat(record, cards: set[str], event_type: bool = False, geo: bool = False):
    """Fill missing optional fields with null, then validate (strict mode off). Returns (internal-shape record,
    filled field names). Core fields (plus event_type when the prompt defines it) must be present. Raises on any
    violation; the caller sends the answer to failed.jsonl, without retry."""
    if not isinstance(record, dict):
        raise ValueError("flat record is not a JSON object")
    schema = output_schema_flat(cards, event_type, geo)
    core = CORE_FIELDS + (["event_type"] if event_type else []) + (["geography"] if geo else [])
    absent = [k for k in core if k not in record]
    if absent:
        raise ValueError("missing core field(s): " + ", ".join(absent))
    filled = [k for k in schema["properties"] if k not in record]
    record = {**record, **{k: ("" if k == "notes" else None) for k in filled}}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)
    if not record["is_relevant"]:
        if not record["notes"].strip():
            raise ValueError("irrelevant record without a reason in notes")
        return {"is_relevant": False, "notes": record["notes"]}, filled
    record = {**record, **{k: [] for k in OPTIONAL_LIST_FIELDS if record[k] is None}}
    missing = [k for k in RELEVANT_REQUIRED + (["event_type"] if event_type else []) + (["geography"] if geo else []) if record[k] is None]
    if missing:
        raise ValueError("relevant record with null fields: " + ", ".join(missing))
    if not record["card_ids"] or not record["evidence_quotes"]:
        raise ValueError("relevant record needs at least one card_id and one evidence quote")
    if geo:   # new_information belongs to same_as_event_id: boolean when set, null otherwise
        if record["same_as_event_id"] is None:
            record["new_information"] = None
        elif record["new_information"] is None:
            raise ValueError("new_information must be true or false when same_as_event_id is set")
    return dict(record), filled


def validate_flat(record, cards: set[str], event_type: bool = False, geo: bool = False) -> dict:
    return prepare_flat(record, cards, event_type, geo)[0]


def build_request(prompt: str, schema: dict, config: dict, strict: bool = True) -> dict:
    return {"modelId": config["model_id"], "system": [{"text": prompt}],
            "messages": [{"role": "user", "content": [{"text": "Classify the supplied article."}]}],
            "inferenceConfig": {"temperature": 0, "maxTokens": config["max_tokens"]},
            "toolConfig": {"tools": [{"toolSpec": {"name": TOOL, "description": "Submit the classification record specified by the system prompt."
                                                    if strict else FLAT_TOOL_DESCRIPTION,
                                                    "strict": strict, "inputSchema": {"json": schema}}}],
                           "toolChoice": {"tool": {"name": TOOL}}}}


def build_request_v13(system: str, user: str, schema: dict, config: dict, cache: bool, strict: bool = True) -> dict:
    """Static prefix (tool + system text) first, then a cachePoint; per-item text only in the user message."""
    request = build_request(system, schema, config, strict)
    if cache:
        request["system"].append({"cachePoint": {"type": "default"}})
    request["messages"] = [{"role": "user", "content": [{"text": user}]}]
    return request


def review_basis(article: dict, reasons: list[str]) -> list[str]:
    """Every LLM candidate needs human review; headline-only input is named explicitly."""
    basis = ["all LLM candidates require human review"]
    if article.get("content_scope") in HEADLINE_SCOPES:
        basis.append("headline-only input (" + article["content_scope"] + ")")
    if reasons:
        basis.append("validation flags present")
    return basis


class ResponseParseError(ValueError):
    def __init__(self, message, fence_fallback=False):
        super().__init__(message)
        self.fence_fallback = fence_fallback


def parse_response(response: dict, flat: bool = False):
    if response.get("stopReason") not in {"tool_use", "end_turn"}:
        raise ValueError("incomplete_response:" + str(response.get("stopReason")))
    content = response.get("output", {}).get("message", {}).get("content", [])
    tools = [p["toolUse"] for p in content if "toolUse" in p]
    if tools:
        if len(tools) != 1 or tools[0].get("name") != TOOL:
            raise ValueError("unexpected_or_multiple_tools")
        value = tools[0].get("input")
        if flat:
            if not isinstance(value, dict):
                raise ValueError("invalid_tool_input")
            return value, "tool", False
        if not isinstance(value, dict) or set(value) != {"classification"}:
            raise ValueError("invalid_tool_envelope")
        return value["classification"], "tool", False
    text = "".join(p.get("text", "") for p in content).strip()
    fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text, re.S | re.I)
    if fence:
        text = fence[1]
    try:
        return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON number"))), "text", fence is not None
    except ValueError as exc:
        raise ResponseParseError(str(exc), fence_fallback=fence is not None) from None


def check_classification(result: dict, article: dict, schema: dict, cards: set[str], recent: set[str], major: set[str],
                         headline_rules: bool = False):
    Draft202012Validator(schema, format_checker=FormatChecker()).validate({"classification": result})
    if not result["is_relevant"]:
        return result, []
    checked = copy.deepcopy(result)
    reasons = []
    if not 1 <= len(result["card_ids"]) <= 3 or len(set(result["card_ids"])) != len(result["card_ids"]):
        reasons.append("card_ids must contain 1-3 distinct catalog IDs")
    if not 0 <= result["confidence"] <= 1:
        reasons.append("confidence outside [0,1]")
    if not result["title"].strip() or len(result["title"].split()) > 12:
        reasons.append("title empty or longer than 12 words")
    if not result["summary"].strip():
        reasons.append("empty summary")
    if result["url"] != article["url"]:
        reasons.append("URL differs from supplied article")
    if result["same_as_event_id"] is not None and result["same_as_event_id"] not in recent:
        reasons.append("same_as_event_id absent from supplied event register")
    if result["stage"] is not None and "XE-MEMBER" not in result["card_ids"]:
        reasons.append("stage supplied for a non-member card")
    if any(not q.strip() or q not in article["text"] for q in result["evidence_quotes"]):
        reasons.append("evidence quote not found verbatim in supplied article text")
    # Source authority comes from the supplied feed, never the model's assertion.
    if result["source_tier"] != article["source_tier"]:
        reasons.append("source_tier differs from input source classification")
    if headline_rules and article.get("content_scope") in HEADLINE_SCOPES:   # prompt v1.3 headline-only rules
        if result["confidence"] > 0.6:
            reasons.append("headline-only item with confidence above 0.6")
        if "headline_only" not in result["notes"]:
            reasons.append("headline-only item without 'headline_only' in notes")
    if result["announced_date"] is None or result["effect_date"] is None:
        reasons.append("missing announced_date or effect_date; existing Event checks require both")
        return checked, list(dict.fromkeys(reasons))
    event = E.Event(event_id=article["document_id"], card_ids=result["card_ids"].copy(), title=result["title"],
                    announced_date=date.fromisoformat(result["announced_date"]), effect_date=date.fromisoformat(result["effect_date"]),
                    certainty=result["certainty"], reach=result["reach"], evidence_quotes=result["evidence_quotes"],
                    sources=[{"url": article["url"], "outlet": article["outlet"], "tier": article["source_tier"]}],
                    llm_confidence=result["confidence"], stage=result["stage"], named_participants=result["named_participants"],
                    reach_basis=result["reach_basis"])
    event = E.validate(event, [article["text"]], cards, major)
    checked.update(card_ids=event.card_ids, certainty=event.certainty, reach=event.reach, stage=event.stage)
    return checked, list(dict.fromkeys(reasons + event.review_reasons))


def cost_without_cache(usage: dict, prices: dict) -> Decimal:
    """The same request priced as if nothing were cached: cache reads and writes count as ordinary input."""
    total_input = usage.get("inputTokens", 0) + usage.get("cacheReadInputTokens", 0) + usage.get("cacheWriteInputTokens", 0)
    return token_cost({"inputTokens": total_input, "outputTokens": usage.get("outputTokens", 0)}, prices)


def token_cost(usage: dict, prices: dict) -> Decimal:
    fields = [("inputTokens", "input_per_million"), ("outputTokens", "output_per_million"),
              ("cacheReadInputTokens", "cache_read_per_million"), ("cacheWriteInputTokens", "cache_write_per_million")]
    return sum((Decimal(usage.get(field, 0)) * Decimal(prices[rate]) / MILLION for field, rate in fields), Decimal(0))


def estimate_request(request: dict, prices: dict):
    byte_count = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
    # Offline estimate, not an observed tokenizer count. Reserve a deliberately
    # conservative byte-based input allowance plus chat/tool framing before calls.
    estimate = token_cost({"inputTokens": (byte_count + 2) // 3 + 512,
                           "outputTokens": prices["expected_output_tokens"]}, prices)
    reserve = token_cost({"inputTokens": byte_count + 2048, "outputTokens": request["inferenceConfig"]["maxTokens"]}, prices)
    return estimate, reserve


def estimate_cached_run(requests: list[dict], prices: dict) -> Decimal:
    """Offline estimate when the system text is cached: the static prefix is written once, then read; the rest of each
    request is ordinary input. Same byte-based token approximation as estimate_request; not observed tokenization."""
    total = Decimal(0)
    for n, request in enumerate(requests):
        static = len(json.dumps([request["system"][0], request["toolConfig"]], ensure_ascii=False).encode("utf-8")) // 3
        whole = (len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 2) // 3 + 512
        cache = {"cacheWriteInputTokens": static} if n == 0 else {"cacheReadInputTokens": static}
        total += token_cost({"inputTokens": whole - static, "outputTokens": prices["expected_output_tokens"], **cache}, prices)
    return total


def safe_error(exc) -> dict:
    # Some botocore/urllib3 exceptions carry response=None; never let error reporting itself raise.
    response = getattr(exc, "response", None)
    response = response if isinstance(response, dict) else {}
    error = response.get("Error") if isinstance(response.get("Error"), dict) else {}
    message = error.get("Message") or (type(exc).__name__ + (": " + str(exc)[:300] if str(exc) else ""))
    # Exception repr/tracebacks may disclose machine paths or credential providers.
    message = re.sub(r"(?:/Users/|/home/|/private/)[^\s\"']+", "[local-path]", message)
    message = re.sub(r"(?:AKIA|ASIA)[A-Z0-9]{16}", "[redacted-access-key]", message)
    return {"code": error.get("Code", type(exc).__name__), "message": message,
            "http_status": response.get("ResponseMetadata", {}).get("HTTPStatusCode")}


def invoke(runtime, request: dict, error_callback, retries: int, base_delay: float, sleeper=time.sleep):
    for attempt in range(retries + 1):
        try:
            return runtime.converse(**request), attempt + 1
        except Exception as exc:
            error = safe_error(exc)
            error_callback(attempt + 1, error)
            throttled = error["code"] == "ThrottlingException" or error["http_status"] == 429
            if not throttled or attempt == retries:
                raise
            sleeper(base_delay * 2 ** attempt)
    raise AssertionError("unreachable")


def csv_writer(path: Path):
    handle = path.open("x", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    writer.writeheader()
    return handle, writer


def csv_row(article: dict, result: dict, checked: dict, reasons: list[str], config: dict,
            version: str, usage: dict, cost: Decimal, mode: str, fallback: bool, attempts: int,
            article_path: Path, raw_path: Path, candidate_id: str):
    row = {k: checked.get(k, "") for k in CSV_FIELDS}
    row.update(event_id=candidate_id, document_id=article["document_id"], entered_by="llm", needs_review="Y",
               is_relevant="Y", source_url=article["url"], url=article["url"],
               card_ids="|".join(checked["card_ids"]), named_participants="|".join(checked["named_participants"]),
               evidence_quote=" || ".join(checked["evidence_quotes"]), evidence_quotes=json.dumps(checked["evidence_quotes"], ensure_ascii=False),
               llm_confidence=checked["confidence"], validation_passed="N" if reasons else "Y",
               validation_reasons=json.dumps(reasons, ensure_ascii=False), original_certainty=result["certainty"], original_reach=result["reach"],
               model_id=config["model_id"], base_model_id=config["base_model_id"], region=config["region"], prompt_version=version,
               input_tokens=usage.get("inputTokens", 0), output_tokens=usage.get("outputTokens", 0),
               cache_read_input_tokens=usage.get("cacheReadInputTokens", 0), cache_write_input_tokens=usage.get("cacheWriteInputTokens", 0),
               estimated_cost_usd=str(cost), response_mode=mode, fence_fallback="Y" if fallback else "N", attempts=attempts,
               content_scope=article["content_scope"], review_basis=json.dumps(review_basis(article, reasons)),
               published_date=article["published_date"],
               article_file=public_path(article_path), raw_output_file=public_path(raw_path))
    return row


def aws_session(config: dict):
    """Interactive SSO locally; short-lived role credentials in a runner."""
    import boto3
    mode = os.environ.get("BEDROCK_AUTH_MODE", "profile")
    if mode == "profile":
        return boto3.Session(profile_name=os.environ.get("BEDROCK_PROFILE", "devx-bedrock"), region_name=config["region"])
    if mode != "workload":
        raise ValueError("BEDROCK_AUTH_MODE must be profile or workload")
    session = boto3.Session(region_name=config["region"])
    credentials = session.get_credentials()
    if credentials is None or not credentials.token:
        raise ValueError("Workload authentication requires temporary role credentials")
    return session


def run(args, session=None):
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config["temperature"] != 0 or config["max_tokens"] != 2000 or not 0 <= config["throttling_retries"] <= 2:
        raise ValueError("Required: temperature 0, max_tokens 2000, at most two throttling retries")
    budget = args.budget if args.budget is not None else Decimal(str(config["default_budget_usd"]))
    if budget <= 0 or not budget.is_finite():
        raise ValueError("Budget must be finite and positive")
    if args.start > args.end or args.max_articles is not None and args.max_articles < 1:
        raise ValueError("Invalid date window or --max-articles")
    prompt_version = getattr(args, "prompt_version", "v1.2")
    cache = prompt_version in SPLIT_PROMPTS and getattr(args, "prompt_cache", "on") == "on"
    prompt_path = PROMPT_FILES[prompt_version]
    originals = {p: sha(p.read_bytes()) for p in (args.register, *PROMPT_FILES.values())}
    articles, coverage = load_news(args.news, args.start, args.end, args.max_articles)
    if prompt_version == "v1.2":
        body, catalog, cards, version = prompt_parts(PROMPT)
    else:
        system_text, user_template, cards, version = prompt_parts_v13(prompt_path, prompt_version)
    register = load_register(args.register)
    with args.major.open(encoding="utf-8-sig", newline="") as handle:
        major = {r["name"] for r in csv.DictReader(handle) if r.get("name")}
    response_schema = getattr(args, "response_schema", "strict-anyof")   # CLI default: flat
    flat = response_schema == "flat"
    with_type = prompt_version in EVENT_TYPE_PROMPTS
    with_geo = prompt_version in GEO_PROMPTS
    schema = output_schema(cards, with_type, with_geo)          # internal shape used by check_classification
    tool_schema = output_schema_flat(cards, with_type, with_geo) if flat else schema
    Draft202012Validator.check_schema(tool_schema)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run ID")
    suffix = "_dry_run" if args.dry_run else ""
    run_dir = args.output_dir / "classifier_runs" / (run_id + suffix)
    run_dir.mkdir(parents=True, exist_ok=False)
    requests = []
    for article in articles:
        if prompt_version == "v1.2":
            prompt, recent_ids = render_prompt(body, catalog, register, article)
            request = build_request(prompt, tool_schema, config, strict=not flat)
        else:
            user, recent_ids = render_user_v13(user_template, register, article)
            request = build_request_v13(system_text, user, tool_schema, config, cache, strict=not flat)
        estimate, reserve = estimate_request(request, config["pricing"])
        requests.append((article, request, recent_ids, estimate, reserve))
    summary = {"run_id": run_id, "run_date": args.run_date.isoformat(), "dry_run": args.dry_run,
               "start": args.start.isoformat(), "end": args.end.isoformat(), "coverage": coverage,
               "input_sha256": sha(args.news.read_bytes()), "register_sha256": originals[args.register],
               "prompt_sha256": originals[prompt_path], "prompt_version": version, "prompt_file": public_path(prompt_path),
               "prompt_cache": cache, "config": config,
               "classifier_sha256": sha(Path(__file__).read_bytes()), "schema_sha256": sha(json.dumps(tool_schema, sort_keys=True).encode()),
               "response_schema": response_schema, "tool_strict": not flat,
               "model_id": config["model_id"], "region": config["region"], "budget_usd": str(budget),
               "estimated_full_run_cost_usd": str(sum((r[3] for r in requests), Decimal(0))),
               "conservative_full_run_reservation_usd": str(sum((r[4] for r in requests), Decimal(0))),
               "estimated_full_run_cost_with_cache_usd": str(estimate_cached_run([r[1] for r in requests], config["pricing"])) if cache else None,
               "estimate_method": "UTF-8 request bytes/3 + 512 input tokens; expected output tokens from config; not observed tokenization",
               "reservation_method": "UTF-8 request bytes + 2048 input tokens and the maxTokens output limit, before each paid request",
               "articles_processed": 0, "relevant": 0, "irrelevant": 0, "failed_checks": 0,
               "failed_check_reasons": {}, "invocation_failures": 0, "candidates_per_card": {},
               "fence_fallbacks": 0, "tool_responses": 0, "text_responses": 0, "throttling_retries": 0,
               "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0,
               "estimated_cost_usd": "0", "estimated_cost_without_cache_usd": "0", "unreported_cost_reserve_usd": "0",
               "status": "dry_run" if args.dry_run else "running"}
    dump(run_dir / "summary.json", summary)
    if args.dry_run:
        with (run_dir / "prepared_requests.jsonl").open("x", encoding="utf-8") as handle:
            for article, request, _, estimate, reserve in requests:
                handle.write(json.dumps({"document_id": article["document_id"], "url": article["url"],
                                         "request": request, "estimated_cost_usd": str(estimate), "reservation_usd": str(reserve)}, ensure_ascii=False) + "\n")
        print(json.dumps(summary, indent=2), flush=True)
        return summary
    candidates_path = args.output_dir / f"candidates_{args.run_date.isoformat()}.csv"
    if candidates_path.exists():
        raise FileExistsError("Candidate CSV already exists; refusing to overwrite review work")
    if session is None:
        from botocore.config import Config
        session = aws_session(config)
        # All SDK retries are disabled. Only invoke() retries explicit throttling.
        sdk_config = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=config["read_timeout_seconds"])
        sts = session.client("sts", config=sdk_config)
        bedrock = session.client("bedrock", config=sdk_config)
        runtime = session.client("bedrock-runtime", config=sdk_config)
    else:
        sts, bedrock, runtime = (session.client(name) for name in ("sts", "bedrock", "bedrock-runtime"))
    if sts.get_caller_identity()["Account"] != config["expected_account_id"]:
        raise ValueError("AWS account does not match the approved config")
    try:
        availability = bedrock.get_foundation_model_availability(modelId=config["base_model_id"])
        # Record the check exactly once; agreement NOT_AVAILABLE is not a gate.
        availability.pop("ResponseMetadata", None)
    except Exception as exc:
        availability = {"check_error": safe_error(exc)}
    dump(run_dir / "availability_before.json", availability)
    summary["availability_before"] = availability
    spent, unknown_reserve, uncached = Decimal(0), Decimal(0), Decimal(0)
    filled_counts = Counter()
    failures, counts = Counter(), Counter()
    candidate_handle, candidate_writer = csv_writer(candidates_path)
    irrelevant_handle = (run_dir / "irrelevant.jsonl").open("x", encoding="utf-8")
    failure_handle = (run_dir / "failed.jsonl").open("x", encoding="utf-8")
    try:
        for index, (article, request, recent_ids, _, reserve) in enumerate(requests):
            if spent + unknown_reserve + reserve > budget:
                summary["status"] = "budget_limit"
                break
            key = sha((article["document_id"] + "|" + article["url"]).encode())[:24]
            raw_path = run_dir / "raw" / (key + ".json")
            # Full texts are never committed: the .fulltext.txt suffix is git-ignored.
            article_path = run_dir / "articles" / (key + (".fulltext.txt" if article["content_scope"] == "full_text" else ".txt"))
            article_path.parent.mkdir(parents=True, exist_ok=True)
            article_path.write_text(article["text"], encoding="utf-8")
            attempts = []
            def record_error(number, error):
                attempts.append(error)
                dump(run_dir / "raw" / f"{key}_attempt_{number}_error.json", error)
            try:
                response, attempt_count = invoke(runtime, request, record_error, config["throttling_retries"], config["retry_base_seconds"])
            except Exception as exc:
                error = safe_error(exc)
                summary["invocation_failures"] += 1
                summary["throttling_retries"] += max(0, len(attempts) - 1)
                failure_handle.write(json.dumps({"document_id": article["document_id"], "url": article["url"], "prompt_version": version, "invocation_error": error}, ensure_ascii=False) + "\n")
                failure_handle.flush()
                access = error["code"] in {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException"} or any(t in error["message"].lower() for t in ("subscription", "marketplace", "use case", "not authorized"))
                if error["http_status"] is None:  # A network failure might follow a billed request.
                    unknown_reserve += reserve
                summary["status"] = "access_or_subscription_error" if access else "invocation_error"
                summary["invocation_error"] = error
                print(json.dumps({"stopped": summary["status"], "error": error}), flush=True)
                break
            # Preserve model output before any parsing or validation; omit HTTP headers.
            dump(raw_path, {"document_id": article["document_id"], "url": article["url"], "model_id": config["model_id"],
                            "prompt_version": version, "request_sha256": sha(json.dumps(request, sort_keys=True).encode()),
                            "output": response.get("output"), "stopReason": response.get("stopReason"),
                            "usage": response.get("usage", {}), "metrics": response.get("metrics", {}), "attempts": attempt_count,
                            "sdk_retry_attempts": response.get("ResponseMetadata", {}).get("RetryAttempts", 0)})
            usage = response.get("usage", {})
            if any(type(usage.get(field, 0)) is not int or usage.get(field, 0) < 0 for field in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens")) or "inputTokens" not in usage or "outputTokens" not in usage:
                unknown_reserve += reserve
                summary["articles_processed"] += 1
                summary["failed_checks"] += 1
                failures.update(["missing_or_invalid_token_usage"])
                failure_handle.write(json.dumps({"document_id": article["document_id"], "url": article["url"], "reasons": ["missing_or_invalid_token_usage"]}) + "\n")
                summary["status"] = "cost_accounting_error"
                break
            cost = token_cost(usage, config["pricing"])
            spent += cost
            uncached += cost_without_cache(usage, config["pricing"])
            summary["articles_processed"] += 1
            summary["throttling_retries"] += attempt_count - 1
            for source, target in [("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
                                   ("cacheReadInputTokens", "cache_read_input_tokens"), ("cacheWriteInputTokens", "cache_write_input_tokens")]:
                summary[target] += usage.get(source, 0)
            reasons = []
            try:
                result, mode, fallback = parse_response(response, flat=flat)
                if flat:   # failure -> failed.jsonl below; never retried
                    result, filled = prepare_flat(result, cards, with_type, with_geo)
                    filled_counts.update(filled)
                summary["fence_fallbacks"] += int(fallback)
                summary[mode + "_responses"] += 1
                if isinstance(result, dict) and result.get("is_relevant") is True:
                    summary["relevant"] += 1
                checked, reasons = check_classification(result, article, schema, cards, recent_ids, major,
                                                        headline_rules=prompt_version in SPLIT_PROMPTS)
                if result["is_relevant"]:
                    counts.update(checked["card_ids"])
                    row = csv_row(article, result, checked, reasons, config, version, usage, cost, mode, fallback, attempt_count,
                                  article_path, raw_path, "CAND-" + args.run_date.isoformat() + "-" + key)
                    candidate_writer.writerow(row)
                    candidate_handle.flush()
                else:
                    summary["irrelevant"] += 1
                    irrelevant_handle.write(json.dumps({"document_id": article["document_id"], "url": article["url"], "prompt_version": version,
                                                        "response_mode": mode, "classification": result,
                                                        "raw_output_file": public_path(raw_path), "usage": usage, "estimated_cost_usd": str(cost)}, ensure_ascii=False) + "\n")
                    irrelevant_handle.flush()
            except Exception as exc:
                # Local validation failures are never retried with another model call.
                if isinstance(exc, ResponseParseError):
                    summary["fence_fallbacks"] += int(exc.fence_fallback)
                    summary["text_responses"] += 1
                detail = ("schema:" + str(list(exc.absolute_path)) + ":" + exc.message) if isinstance(exc, ValidationError) else str(exc)
                reasons = ["parse_or_schema_error:" + type(exc).__name__ + ":" + detail[:500]]
            if reasons:
                summary["failed_checks"] += 1
                failures.update(reasons)
                failure_handle.write(json.dumps({"document_id": article["document_id"], "url": article["url"], "prompt_version": version,
                                                 "response_schema": response_schema, "reasons": reasons,
                                                 "raw_output_file": public_path(raw_path)}, ensure_ascii=False) + "\n")
                failure_handle.flush()
            summary.update(estimated_cost_usd=str(spent), estimated_cost_without_cache_usd=str(uncached),
                           candidates_per_card=dict(counts), failed_check_reasons=dict(failures))
            dump(run_dir / "summary.json", summary)
            if (index + 1) % 10 == 0 or index + 1 == len(requests):
                print(json.dumps({"processed": summary["articles_processed"], "selected": len(requests), "relevant": summary["relevant"],
                                  "failed_checks": summary["failed_checks"], "estimated_cost_usd": str(spent)}), flush=True)
            if spent > budget:  # Halt if reported usage ever exceeds the conservative reservation.
                summary["status"] = "budget_estimate_exceeded"
                break
        else:
            summary["status"] = "complete"
    finally:
        candidate_handle.close(); irrelevant_handle.close(); failure_handle.close()
        summary.update(estimated_cost_usd=str(spent), estimated_cost_without_cache_usd=str(uncached),
                       unreported_cost_reserve_usd=str(unknown_reserve), filled_missing_fields=dict(filled_counts),
                       candidates_per_card=dict(counts), failed_check_reasons=dict(failures),
                       articles_unprocessed=len(articles) - summary["articles_processed"],
                       event_register_unchanged=sha(args.register.read_bytes()) == originals[args.register],
                       prompt_unchanged=all(sha(f.read_bytes()) == originals[f] for f in PROMPT_FILES.values()))
        dump(run_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    if not summary["event_register_unchanged"] or not summary["prompt_unchanged"]:
        raise RuntimeError("Protected prompt/register changed during the run")
    return summary


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--news", type=Path, default=NEWS)
    p.add_argument("--register", type=Path, default=REGISTER)
    p.add_argument("--major", type=Path, default=MAJOR)
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--output-dir", type=Path, default=PROJECT / "data/events")
    p.add_argument("--max-articles", type=int)
    p.add_argument("--budget", type=Decimal)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run-id")
    p.add_argument("--prompt-version", choices=sorted(PROMPT_FILES), default="v1.2")
    p.add_argument("--response-schema", choices=["flat", "strict-anyof"], default="flat",
                   help="flat: one object, all fields present (null if n/a), strict off, validated in code. "
                        "strict-anyof: the earlier strict schema (forced is_relevant=false in practice; kept to reproduce old runs)")
    p.add_argument("--prompt-cache", choices=["on", "off"], default="on", help="v1.3/v1.4: Converse cachePoint after the static system text")
    p.add_argument("--run-date", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/New_York")).date())
    return p


def main():
    try:
        summary = run(parser().parse_args())
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "message": safe_error(exc)["message"]}), flush=True)
        raise SystemExit(1) from None
    if summary["status"] not in {"complete", "dry_run", "budget_limit"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

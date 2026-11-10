"""Checks for AI-drafted so_what / so_now_what text (standard library only; also used by docs/data/export_risk_output.py).

    check(so_what, so_now_what, record_input, facts_used=None) -> list of flags (empty = passes)

- Every number in the text must come from the input JSON: the same value at the shown precision (1.5409 -> "1.54"),
  a 0-1 share shown as a percentile or percent (0.97 -> "97th", "97%"), or a date the input contains (2026-12-31 ->
  "Dec 31, 2026", "December 31", "2026-12-31"). Numbers inside identifiers (FICC-GSD-03, 2026Q2) are not read as numbers.
- so_what: at most 2 sentences and 45 words; so_now_what: at most 2 sentences and 40 words.
- Banned phrases: must, should raise, should increase, recommend that DTCC, will cause, guarantee(d/s).
- A public-proxy V or Low chain confidence must be mentioned; a shared signal must be mentioned (card id or name).
- facts_used may only name fields of the input.
A row with any flag is never published.
"""
from __future__ import annotations

import json
import re
from datetime import date

LIMITS = {"so_what": (2, 45), "so_now_what": (2, 40)}
BANNED = re.compile(r"\b(must|should raise|should increase|recommend that DTCC|will cause|guarantee[sd]?)\b", re.I)
NUMBER = re.compile(r"(?<![\w.\-+/])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s?(?:%|bp|×|x|th|st|nd|rd))?"
                    r"(?:\s+(trillion|billion|million|thousand|bn))?(?![\w\-])", re.I)
SCALE = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "thousand": 1e3}
ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                      "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
TEXT_DATE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", re.I)
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
TEMPLATE_SO_WHAT = "No scored shock this week."
TEMPLATE_SO_NOW_WHAT = "See the transmission chain for what would trigger a score."
REVIEW_LABEL = "AI-written, reviewed by analyst"


def _walk(value, path=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v, path)
    else:
        yield path, value


def input_numbers(record_input: dict) -> tuple[list[float], set[tuple[int, int, int]]]:
    """All numbers in the input: numeric values, plus digit groups and ISO dates inside strings."""
    nums, dates = [], set()
    for _, v in _walk(record_input):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            nums.append(float(v))
        elif isinstance(v, str):
            for y, m, d in ISO_DATE.findall(v):
                dates.add((int(y), int(m), int(d)))
            nums.extend(float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", v))
    for y, m, d in dates:
        nums.extend([y, m, d])
    return nums, dates


def field_names(record_input: dict) -> set[str]:
    names = set()
    for path, _ in _walk(record_input):
        parts = path.split(".")
        names.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return names


def _matches(value: float, decimals: int, percentish: bool, nums: list[float], scale: float = 1.0) -> bool:
    for x in nums:
        if scale != 1.0:                                   # 28015313200 -> "28.0 billion"
            if round(x / scale, decimals) == round(value, decimals):
                return True
            continue
        if round(x, decimals) == round(value, decimals):
            return True
        if percentish and 0 <= x <= 1 and round(x * 100, decimals) == round(value, decimals):
            return True
        if 0 <= x <= 1 and decimals == 0 and round(x * 100) == value:           # 0.86 -> 86th / 86
            return True
    return False


def unsupported_numbers(text: str, record_input: dict) -> list[str]:
    nums, dates = input_numbers(record_input)
    bad = []
    masked = text
    for m in TEXT_DATE.finditer(text):                    # textual dates must be input dates
        mon, day, year = MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2)), m.group(3)
        if not any(dm == mon and dd == day and (not year or dy == int(year)) for dy, dm, dd in dates):
            bad.append(m.group(0))
        masked = masked.replace(m.group(0), " ")
    for m in ISO_DATE.finditer(text):
        if (int(m.group(1)), int(m.group(2)), int(m.group(3))) not in dates:
            bad.append(m.group(0))
        masked = masked.replace(m.group(0), " ")
    for m in NUMBER.finditer(masked):
        token = m.group(0)
        value = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        decimals = len(m.group(2)) - 1 if m.group(2) else 0
        scale = SCALE.get((m.group(3) or "").lower(), 1.0)
        percentish = bool(re.search(r"(%|th|st|nd|rd)$", token.strip())) and scale == 1.0
        if not _matches(value, decimals, percentish, nums, scale):
            bad.append(token.strip())
    return bad


ABBREVIATIONS = re.compile(r"\b(?:[A-Z]\.){2,}|\b(?:e\.g|i\.e|vs|approx|No)\.", re.I)


def sentences(text: str) -> int:
    """Sentence count; abbreviations such as U.S., e.g. and vs. do not end a sentence."""
    t = ABBREVIATIONS.sub("X", text.strip())
    if not t:
        return 0
    return len(SENTENCE_END.findall(t)) + (0 if t[-1] in ".!?" else 1)


def check(so_what: str, so_now_what: str, record_input: dict, facts_used=None) -> list[str]:
    flags = []
    for name, text in (("so_what", so_what), ("so_now_what", so_now_what)):
        if not isinstance(text, str) or not text.strip():
            flags.append(f"{name}: empty"); continue
        max_sent, max_words = LIMITS[name]
        if len(text.split()) > max_words:
            flags.append(f"{name}: {len(text.split())} words > {max_words}")
        if sentences(text) > max_sent:
            flags.append(f"{name}: {sentences(text)} sentences > {max_sent}")
        for phrase in sorted({m.group(0).lower() for m in BANNED.finditer(text)}):
            flags.append(f"{name}: banned phrase '{phrase}'")
        bad = unsupported_numbers(text, record_input)
        if bad:
            flags.append(f"{name}: numbers not in the input: {', '.join(bad)}")
    both = f"{so_what or ''} {so_now_what or ''}"
    if record_input.get("V_tier") == "public_proxy" and "proxy" not in both.lower():
        flags.append("public-proxy V not mentioned")
    if str(record_input.get("chain_confidence", "")).lower() == "low" and not re.search(r"\blow\b.*\bconfidence\b|\bconfidence\b.*\blow\b", both, re.I):
        flags.append("Low chain confidence not mentioned")
    for shared in record_input.get("shared_signal") or []:
        names = [shared.get("card_id", ""), shared.get("card_name", "")]
        if not any(n and n.lower() in both.lower() for n in names):
            flags.append(f"shared signal with {shared.get('card_id')} not mentioned")
    if facts_used is not None:
        known = field_names(record_input)
        unknown = [f for f in facts_used if f not in known]
        if unknown:
            flags.append("facts_used names unknown fields: " + ", ".join(unknown))
    return flags


# ------------------------------------------------------------------ prompt v2 style checks (flags on v2 drafts only)
# Not applied to reviewed text at export: they test the v2 drafting rules, not publication safety.
SERIES_CODES = re.compile(r"\b(DGS10|MORTGAGE30US|BAA10Y|VIXCLS|[a-z0-9]+(?:_[a-z0-9]+)+)\b|\|\s*Δ")
NEXT_LATEST_PQD = re.compile(r"\bnext\b[^.;]{0,60}\bPQD\b[^.;]{0,60}\b\d{4}\s?Q[1-4]\b|\bnext\b[^.;]{0,40}\b\d{4}\s?Q[1-4]\b", re.I)
FIRM_STRESS = re.compile(r"\b(?:member|firm|dealer|bank)s?['’]?\s+(?:credit\s+)?(?:stress|distress)\b|"
                         r"\bstress (?:at|in|among) (?:specific|individual|particular) (?:firms|members|dealers|banks)\b", re.I)
V_MEANING = re.compile(r"(versus|relative to|compared with) its own history|\blevel \d of 5\b", re.I)


def style_flags(so_what: str, so_now_what: str, record_input: dict) -> list[str]:
    """Prompt v2 rules: plain names, latest (not next) PQD quarter, no firm-specific wording for market-wide signals,
    V meaning given. The shared-signal and number rules are in check()."""
    both = f"{so_what or ''} {so_now_what or ''}"
    flags = []
    codes = sorted({m.group(0) for m in SERIES_CODES.finditer(both)})
    if codes:
        flags.append("series codes instead of plain names: " + ", ".join(codes))
    if any(not re.search(r"\b(latest|last|most recent)\b", m.group(0), re.I) for m in NEXT_LATEST_PQD.finditer(both)):
        # "next … 2026Q2" calls the latest quarter the next one, unless the quarter is labelled latest / last
        flags.append("latest available PQD quarter described as the next release")
    if (record_input.get("signal") or {}).get("scope") == "market-wide" and FIRM_STRESS.search(both):
        flags.append("market-wide signal described as stress at specific firms")
    if record_input.get("V") is not None and not V_MEANING.search(both):
        flags.append("V meaning not given (level k of 5 versus its own history)")
    return flags


def load_input(path, record_id: str) -> dict | None:
    """Narrative input for a record from the run's inputs.jsonl (one JSON object per card, with record_ids)."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if record_id in row.get("record_ids", []):
                return row["input"]
    return None

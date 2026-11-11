"""Checks and fixed texts for the card front layer (standard library only; also used by docs/data/export_risk_output.py
and docs/data/validate_output.py).

The card front is what a business-line GM reads in 10 seconds: headline, what happened, a three-step short chain, one
"so what" sentence, one playbook action and a sources line. The technical detail (S × V, percentiles, daily values,
the v3.1 narrative) stays in the analyst view. Display only: nothing here changes S, V, severity, status or ranking.

- playbook_flags(row): one card_playbook.csv row (chain_short_1..3, action_k_text): chain labels at most 6 words,
  2-3 actions of at most 15 words that start with a verb, no risk-parameter / policy, legal or regulatory decisions,
  no firm names, no banned phrases, no numbers.
- publication_flags(front, record_input, actions): the checks the export re-runs before it publishes a reviewed front:
  word and sentence limits, numbers only from the input, banned phrases, no percentiles / "V k of 5" / series codes /
  jargon, no firm-specific wording for market-wide signals, so_now_what_front equal to a playbook action.
- drafting_flags(front, record_input): reviewer hints on drafts only (not re-run at export): the headline introduces
  words that are not in the input, is not grounded in the source it names, so_what_front does not follow chain steps
  2/3, its wording does not match the size of this week's signal (S 1-3 vs 4-5), superlatives outside a headline that
  cites them, predictions ("likely", "will"), or what_happened restating a related-news headline as fact. A superlative
  or a restated headline in what_happened is accepted when the sentence names that headline's outlet ("MarketWatch
  reported ..."). Hyphens inside words are ignored when words are compared ("sell-off" = "selloff").
- sources_line(record, ...): short source names, e.g. "FRED (VIX, SOFR, EFFR) · DTCC quarterly disclosures · MarketWatch".
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_NC_PATH = Path(__file__).with_name("narrative_checks.py")
_spec = importlib.util.spec_from_file_location("narrative_checks_for_front", _NC_PATH)
NC = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(NC)

FRONT_LIMITS = {"headline": 10, "what_happened": 20, "so_what_front": 20}     # words; what_happened and so_what_front: 1 sentence
CHAIN_WORDS, ACTION_WORDS = 6, 15
FRONT_REVIEW_LABEL = "AI-drafted · analyst-reviewed"
TEMPLATE_WHAT_HAPPENED = {"no_relevant_news": "No market signal or relevant news this week.",
                          "news_not_scanned": "No market signal this week; news not yet scanned.",
                          "data_incomplete": "Market data incomplete this week."}
ACTION_KINDS = {"communicate", "prepare", "verify", "escalate", "monitor"}
VERBS = {"alert", "brief", "tell", "inform", "notify", "remind", "share", "confirm", "check", "verify", "review", "ask",
         "prepare", "plan", "schedule", "escalate", "flag", "monitor", "watch", "track", "follow", "coordinate", "contact",
         "update", "test", "refresh", "keep", "agree", "line", "walk", "reconfirm", "rehearse", "send", "set", "engage"}
POLICY = re.compile(r"\b(change|changes|changing|raise|raising|lower|lowering|increase|increasing|decrease|cut|cutting|tighten|"
                    r"loosen|adjust|adjusting|reduce|widen|impose|waive|suspend|recalibrate|override)\b[^.;]{0,40}?\b(margins?|haircuts?|"
                    r"limits?|rules?|parameters?|requirements?|fees?|thresholds?|polic(?:y|ies)|add-ons?|multipliers?)\b"
                    r"|\b(?:margin|haircut|risk[- ]parameter|limit|rule|policy) (?:change|increase|decrease|decision)s?\b", re.I)
LEGAL = re.compile(r"\b(legal|counsel|lawyers?|litigation|lawsuit|enforcement|no-action|comment letter|lobby\w*|petition\w*)\b"
                   r"|\b(seek|request|file|apply for|submit|ask for)\b[^.;]{0,30}\b(relief|exemption|waiver|extension|approval|rule change)\b", re.I)
ALLOWED_CAPS = set("""DTCC NSCC FICC GSD MBSD DTC ECS ITP Member Members CNS ACATS SFT MMI EPN GCF CCIT TBA SOFR EFFR VIX Baa MBS PQD GM GMs US U.S. Treasury
Treasuries Fedwire SEC CFTC Fed FRED Cboe T+1 T+0 Sponsored Agent Clearing Fund Watch List Required Deposit Deposits Supplemental Liquidity
Corporation Repo Settlement Settling Equity Fixed Income Mortgage-Backed Securities Division Government I""".split())
JARGON = re.compile(r"\bpercentiles?\b|\b\d+(?:st|nd|rd|th)\b|\bV\s?\d\b|\bof 5\b|\bS\s?\d\b|\bseverity\b|\bPQD\b|\bbp\b|\bbasis points?\b|"
                    r"\bquantitative disclosure\b|\bproxy\b|\bz-score\b|\bshock score\b", re.I)
SCORE_TERMS = re.compile(r"\bpercentiles?\b|\b\d+(?:st|nd|rd|th)\b|\bV\s?\d\b|\bof 5\b|\bS\s?\d\b|\bseverity\b|\bPQD\b|\bz-score\b|\bshock score\b", re.I)
SUPERLATIVE = re.compile(r"\b(record|worst|best|unprecedented|biggest|largest|highest|lowest|historic)\b", re.I)
SPECULATIVE = re.compile(r"\b(likely|will|certain(?:ly)?|expected to|inevitabl\w*)\b", re.I)
FIRM_WORDING = re.compile(r"\b(?:specific|individual|particular|certain|some|weak|weaker|struggling|troubled|distressed)\s+"
                          r"(?:clearing\s+)?(?:firms?|members?|banks?|dealers?|brokers?|participants?)\b|"
                          r"\b(?:firms?|members?|banks?|dealers?|brokers?|participants?)\s+(?:is|are|may be|could be)\s+"
                          r"(?:failing|struggling|in trouble|under (?:stress|strain|pressure)|distressed|at risk of default)\b", re.I)
ESCALATING = re.compile(r"\b(jump\w*|surg\w*|spik\w*|soar\w*|sharp\w*|plung\w*|bigger|biggest|much (?:higher|larger|bigger)|heavy|heavier|"
                        r"swell\w*|spiral\w*)\b", re.I)
CALMING = re.compile(r"\b(calm\w*|quiet\w*|eas(?:e|ed|ing)|steady|stable|modest\w*|small(?:er)?|normal|unchanged|subdued|muted)\b", re.I)
GENERIC = set("""week this weeks today daily more less higher lower bigger larger smaller extra calls call payments payment cash need needs
watch rise rises rising risen falls fall falling swing swings move moves moved jump jumps spike spikes surge surges sharp elevated steady
normal modest quiet calm stable demand watchlist check checks could possibly likely possible mild moderate around near still also ahead
upcoming nears approaching deadline deadlines days within under over amid after before market markets""".split())
_STOP = NC.STOP | {"into", "onto", "over", "under", "your", "about", "amid", "after", "before", "this", "week"}


def words(text: str | None) -> int:
    return len((text or "").split())


def _stems(text: str) -> set[str]:
    """Content-word stems (first 5 letters). Hyphens inside words are dropped first, so "sell-off" = "selloff"."""
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", "", (text or "").lower())
    return {w[:5] for w in re.findall(r"[a-z][a-z\-']+", text) if len(w) > 3 and w not in _STOP}


def _names_outlet(text: str, outlet: str | None) -> bool:
    """The sentence names the outlet, e.g. "MarketWatch reported ..." (outlet "Bloomberg.com" also matches "Bloomberg")."""
    name = re.sub(r"\.(com|net|org)$", "", (outlet or "").strip(), flags=re.I)
    return bool(name) and re.search(rf"\b{re.escape(name)}\b", text or "", re.I) is not None


def _actions(row: dict) -> list[tuple[str, str]]:
    return [(row.get(f"action_{k}_id", ""), (row.get(f"action_{k}_text") or "").strip()) for k in (1, 2, 3)
            if (row.get(f"action_{k}_text") or "").strip()]


def _names(text: str) -> list[str]:
    """Capitalised words after the first word that are not known DTCC / market terms (possible firm names)."""
    tokens = re.findall(r"[A-Za-z][A-Za-z&.+\-']*", text)
    return [t for t in tokens[1:] if t[0].isupper() and t.rstrip(".") not in ALLOWED_CAPS and t not in ALLOWED_CAPS]


def action_flags(text: str, label: str = "action") -> list[str]:
    flags = []
    if not text.strip():
        return [f"{label}: empty"]
    if words(text) > ACTION_WORDS:
        flags.append(f"{label}: {words(text)} words > {ACTION_WORDS}")
    first = re.sub(r"[^a-z]", "", text.split()[0].lower())
    if first not in VERBS:
        flags.append(f"{label}: does not start with a verb ('{text.split()[0]}')")
    if POLICY.search(text):
        flags.append(f"{label}: risk-parameter or policy decision ('{POLICY.search(text).group(0)}')")
    if LEGAL.search(text):
        flags.append(f"{label}: legal or regulatory decision ('{LEGAL.search(text).group(0)}')")
    names = _names(text)
    if names:
        flags.append(f"{label}: possible firm or proper name: {', '.join(names)}")
    for phrase in sorted({m.group(0).lower() for m in NC.BANNED.finditer(text)}):
        flags.append(f"{label}: banned phrase '{phrase}'")
    if re.search(r"\d", text):
        flags.append(f"{label}: contains a number (actions are static per card)")
    return flags


def playbook_flags(row: dict, kinds: dict | None = None) -> list[str]:
    """Rules for one card_playbook.csv row (the effective text: corrected columns already applied)."""
    flags = []
    for k in (1, 2, 3):
        label = (row.get(f"chain_short_{k}") or "").strip()
        if not label:
            flags.append(f"chain_short_{k}: empty")
        elif words(label) > CHAIN_WORDS:
            flags.append(f"chain_short_{k}: {words(label)} words > {CHAIN_WORDS}")
        if re.search(r"\d", label):
            flags.append(f"chain_short_{k}: contains a number")
    actions = _actions(row)
    if not 2 <= len(actions) <= 3:
        flags.append(f"{len(actions)} actions (2-3 expected)")
    ids = [a for a, _ in actions]
    if any(not a for a in ids) or len(set(ids)) != len(ids):
        flags.append("action ids missing or repeated")
    for (aid, text) in actions:
        flags += action_flags(text, aid or "action")
    if kinds is not None:
        bad = [k for k in kinds.values() if k not in ACTION_KINDS]
        if bad:
            flags.append("unknown action kind: " + ", ".join(bad))
        if len(set(kinds.values())) < 2:
            flags.append("all actions of one kind")
    return flags


def market_wide(record_input: dict) -> bool:
    return (record_input.get("signal") or {}).get("scope") == "market-wide" or any(
        s.get("scope") == "market-wide" for s in record_input.get("S_signals") or [])


def publication_flags(front: dict, record_input: dict, actions: dict[str, str]) -> list[str]:
    """front: headline, what_happened, so_what_front, action_id, so_now_what_front. actions: action_id -> playbook text."""
    flags = []
    for name, limit in FRONT_LIMITS.items():
        text = front.get(name) or ""
        if not text.strip():
            flags.append(f"{name}: empty"); continue
        if words(text) > limit:
            flags.append(f"{name}: {words(text)} words > {limit}")
        if name != "headline" and NC.sentences(text) > 1:
            flags.append(f"{name}: {NC.sentences(text)} sentences > 1")
        bad = NC.unsupported_numbers(text, record_input)
        if bad:
            flags.append(f"{name}: numbers not in the input: {', '.join(bad)}")
        for phrase in sorted({m.group(0).lower() for m in NC.BANNED.finditer(text)}):
            flags.append(f"{name}: banned phrase '{phrase}'")
        terms = JARGON if name != "what_happened" else SCORE_TERMS      # what_happened may give units (bp, basis points)
        jargon = sorted({m.group(0) for m in terms.finditer(text)} | {m.group(0) for m in NC.SERIES_CODES.finditer(text)})
        if jargon:
            flags.append(f"{name}: {'jargon or score terms' if name != 'what_happened' else 'score terms'}: {', '.join(jargon)}")
        if market_wide(record_input) and FIRM_WORDING.search(text):
            flags.append(f"{name}: market-wide signal described as a problem at specific firms ('{FIRM_WORDING.search(text).group(0)}')")
    aid, now = front.get("action_id") or "", front.get("so_now_what_front") or ""
    if aid not in actions:
        flags.append(f"action_id '{aid}' is not a playbook action of this card")
    elif now != actions[aid]:
        flags.append("so_now_what_front is not the playbook action text, word for word")
    return flags


def _source_text(record_input: dict, source: str) -> str | None:
    sig, event = record_input.get("signal") or {}, record_input.get("driving_event") or {}
    if source == "signal":
        return " ".join(str(x) for x in (sig.get("plain_name"), sig.get("description"), record_input.get("S_set_by")) if x) or None
    if source == "driving_event":
        return event.get("title")
    m = re.fullmatch(r"related_news:(\d+)", source or "")
    items = (record_input.get("related_news") or {}).get("top_items") or []
    if m and int(m.group(1)) < len(items):
        return items[int(m.group(1))]["title"]
    return None


def headline_outlet(record_input: dict, source: str) -> str | None:
    m = re.fullmatch(r"related_news:(\d+)", source or "")
    items = (record_input.get("related_news") or {}).get("top_items") or []
    return items[int(m.group(1))].get("outlet") or None if m and int(m.group(1)) < len(items) else None


def drafting_flags(front: dict, record_input: dict) -> list[str]:
    """Reviewer hints on drafts (grounding, chain, size of the signal); not re-run at export."""
    flags = []
    headline, so_what = front.get("headline") or "", front.get("so_what_front") or ""
    source = _source_text(record_input, front.get("headline_source") or "")
    if source is None:
        flags.append(f"headline_source '{front.get('headline_source')}' is not the signal, the driving event or a related-news item")
    elif not (_stems(headline) & _stems(source)):
        flags.append("headline shares no words with the source it names")
    pb = record_input.get("playbook") or {}
    chain = record_input.get("transmission_chain") or {}
    known = " ".join(str(v) for _, v in NC._walk({k: v for k, v in record_input.items()}) if isinstance(v, str))
    new = sorted(w for w in _stems(headline) - _stems(known) if w not in {g[:5] for g in GENERIC})
    if new:
        flags.append("headline words not in the input (possible new event): " + ", ".join(new))
    steps = " ".join([*(pb.get("chain_short") or [])[1:], chain.get("mechanism", ""), chain.get("dtcc_process", "")])
    if not (_stems(so_what) & _stems(steps)):
        flags.append("so_what_front does not follow chain steps 2/3")
    what = front.get("what_happened") or ""
    items = (record_input.get("related_news") or {}).get("top_items") or []
    for name, text in (("what_happened", what), ("so_what_front", so_what)):
        m = SUPERLATIVE.search(text)
        attributed = name == "what_happened" and m and any(
            m.group(0).lower() in i.get("title", "").lower() and _names_outlet(text, i.get("outlet")) for i in items)
        if m and not attributed:
            flags.append(f"{name}: superlative ('{m.group(0)}'); allowed only in a headline that cites it, or in what_happened "
                         "attributed to the outlet whose headline says it")
    sup = SUPERLATIVE.search(headline)
    if sup and sup.group(0).lower() not in (source or "").lower():
        flags.append(f"headline: superlative not in the cited source ('{sup.group(0)}')")
    for name, text in (("headline", headline), ("so_what_front", so_what)):
        if SPECULATIVE.search(text):
            flags.append(f"{name}: prediction ('{SPECULATIVE.search(text).group(0)}'); use may / can")
    for n, item in enumerate(items):
        if len(_stems(what) & _stems(item.get("title", ""))) >= 4 and not _names_outlet(what, item.get("outlet")):
            flags.append(f"what_happened restates related-news headline {n} ({item.get('outlet')}) as fact; attribute it or use the signal")
    s = record_input.get("S")
    text = f"{headline} {so_what}"
    if isinstance(s, int) and s <= 3 and ESCALATING.search(text):
        flags.append(f"wording stronger than this week's signal (S {s}): '{ESCALATING.search(text).group(0)}'")
    if isinstance(s, int) and s >= 4 and CALMING.search(text):
        flags.append(f"wording weaker than this week's signal (S {s}): '{CALMING.search(text).group(0)}'")
    return flags


# ------------------------------------------------------------------ sources line (non-AI, from the record)
FRED_SHORT = {"VIXCLS": "VIX", "SOFR": "SOFR", "EFFR": "EFFR", "DGS10": "10-year Treasury", "BAA10Y": "Baa spread", "MORTGAGE30US": "mortgage rate"}
OTHER_SHORT = {"CBOE_CONSOLIDATED": "Cboe volume data"}
PROXY_SHORT = {"ECS-NSCC-03": "Cboe volume data", "ECS-SET-01": "SEC fails-to-deliver data", "XE-DISRUPT": "Nasdaq trade-halt history",
               "XE-SETTLEBANK": "Nasdaq index data", "XE-CYBER": "NIST vulnerability database", "FICC-GSD-11": "OFR Hedge Fund Monitor",
               "FICC-MBSD-02": "New York Fed household debt data", "ECS-NSCC-08": "Yahoo Finance (broker-dealer index)",
               "ECS-NSCC-09": "New York Fed markets data", "ECS-DTC-01": "Federal Reserve CP release"}


def sources_line(record: dict, signal_series: dict, headline_outlet_name: str | None = None) -> str:
    """record: a scoring v1.3 record. signal_series: field -> series codes (export SIGNAL_SERIES)."""
    fred, other = [], []
    for mc in record.get("market_chains") or []:
        for s in signal_series.get(mc["field"], []):
            (fred if s in FRED_SHORT else other).append(FRED_SHORT.get(s) or OTHER_SHORT.get(s, s))
    parts = [f"FRED ({', '.join(dict.fromkeys(fred))})"] if fred else []
    parts += other
    ids = record.get("event_manual", {}).get("driving_event_ids") or []
    for e in record.get("event_manual", {}).get("events") or []:
        if e["event_id"] in ids and e.get("outlet"):
            parts.append(e["outlet"])
    if record.get("V_tier") == "pqd":
        parts.append("DTCC quarterly disclosures")
    elif record.get("V_tier") == "public_proxy":
        parts.append(PROXY_SHORT.get(record.get("card_id"), "public proxy data"))
    if headline_outlet_name:
        parts.append(headline_outlet_name)
    return " · ".join(dict.fromkeys(parts))


# ------------------------------------------------------------------ reviewed rows (used by the export)
def reviewed(row: dict) -> str | None:
    """'approve' or 'edit' when the row has that decision and a reviewer, else None."""
    d = (row.get("decision") or "").strip().lower()
    return d if d in ("approve", "edit") and (row.get("reviewer") or "").strip() else None


def _pick(row: dict, key: str, decision: str) -> str:
    corrected = (row.get("corrected_" + key) or "").strip()
    return corrected if decision == "edit" and corrected else (row.get(key) or "").strip()


def action_kinds(row: dict) -> dict:
    """action_id -> kind, the reviewer's corrected kind when given."""
    return {row[f"action_{k}_id"]: ((row.get(f"corrected_action_{k}_kind") or "").strip().lower() or row.get(f"action_{k}_kind", ""))
            for k in (1, 2, 3) if (row.get(f"action_{k}_text") or "").strip()}


def effective_row(row: dict) -> dict:
    """The playbook row with the reviewer's corrected text and kinds applied (for edit)."""
    d = reviewed(row) or "approve"
    eff = dict(row)
    for k in ("chain_short_1", "chain_short_2", "chain_short_3", "action_1_text", "action_2_text", "action_3_text"):
        eff[k] = _pick(row, k, d)
    if d == "edit":
        for k in (1, 2, 3):
            if (row.get(f"corrected_action_{k}_kind") or "").strip():
                eff[f"action_{k}_kind"] = row[f"corrected_action_{k}_kind"].strip().lower()
    return eff


def effective_playbook(row: dict) -> dict | None:
    """A reviewed playbook row that passes playbook_flags: {chain_short: [3], actions: {id: text}, reviewer}; else None."""
    decision = reviewed(row)
    if not decision:
        return None
    eff = {k: _pick(row, k, decision) for k in ("chain_short_1", "chain_short_2", "chain_short_3", "action_1_text", "action_2_text", "action_3_text")}
    eff.update({f"action_{k}_id": row.get(f"action_{k}_id", "") for k in (1, 2, 3)})
    if playbook_flags(eff):
        return None
    return {"chain_short": [eff["chain_short_1"], eff["chain_short_2"], eff["chain_short_3"]],
            "actions": dict(_actions(eff)), "reviewer": row["reviewer"].strip(), "decision": decision}


def effective_front(row: dict, playbook: dict | None, record_input: dict | None) -> dict | None:
    """A reviewed front row: corrected text for edit, so_now_what_front taken from the reviewed playbook for the
    (corrected) action_id; publication_flags must pass against the stored input. Else None."""
    decision = reviewed(row)
    if not decision or playbook is None or record_input is None:
        return None
    front = {k: _pick(row, k, decision) for k in ("headline", "headline_source", "what_happened", "so_what_front", "action_id")}
    front["so_now_what_front"] = playbook["actions"].get(front["action_id"], "")
    if publication_flags(front, record_input, playbook["actions"]):
        return None
    return {**front, "decision": decision, "reviewer": row["reviewer"].strip()}

"""AI-drafted so_what / so_now_what for one scored week (display only), written to a review sheet.

    python -m validation.narratives --week 2026-11-02 --cap 0.50 [--dry-run]

- Input per card: the scoring v1.3 record (results/scoring/v1.3_indicator/weekly_scores_v1.3_<week>.json) and the
  transmission chain the dashboard export shows. One model call per scored card: the two records of a cross-entity card
  (e.g. xe-member-ficc / xe-member-ecs) share one call and one text.
- Records with any other status get fixed, non-AI template text and no call.
- Model: config of validation/llm_classifier_config.json (us.anthropic.claude-sonnet-4-6, temperature 0), prompt
  validation/narrative_prompt_v1.md with the system text cached, forced tool `submit_narrative`, flat schema with strict
  mode off, validated in code; then validation/narrative_checks.py. Every flag is recorded; flagged rows are never
  published.
- Hard USD cap: before each call the worst case (input estimate + max_tokens output) must fit under the cap.
- Writes data/narratives/runs/<week>/<run_id>/ (inputs.jsonl, raw/, summary.json) and
  data/narratives/review_narratives_<week>.csv (never overwritten: a later run gets a _<run_id> suffix).
Never changes S, V, severity, status or ranking, and never writes the event register, sign-offs or docs/.
"""
import argparse, csv, hashlib, importlib.util, json, re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from . import llm_classifier as C
from . import narrative_checks as NC
from .paths import PROJECT

REPO = PROJECT.parent
PROMPT = Path(__file__).with_name("narrative_prompt_v1.md")
PROMPTS = {"v1": PROMPT, "v2": Path(__file__).with_name("narrative_prompt_v2.md"), "v3": Path(__file__).with_name("narrative_prompt_v3.md"),
           "v3.1": Path(__file__).with_name("narrative_prompt_v3.1.md")}
DEFAULT_PROMPT = "v3.1"            # weekly default (WEEKLY_RUNBOOK step 6); v1, v2 and v3 are kept for reproducibility
# Prompt v2: plain names for the six market signals; all are market-wide (never stress at specific firms)
SIGNAL_PLAIN = {
    "ust10_abs_change": "daily move in the 10-year Treasury yield, bp",
    "sofr_effr_adjusted": "SOFR−EFFR repo funding spread (quarter-end adjusted), bp",
    "baa_widen20": "20-day widening of the Baa corporate bond spread over the 10-year Treasury yield, bp",
    "vix_jump": "VIX relative to its 20-day average (ratio)",
    "mbs_spread_abs_wchg": "weekly change in the 30-year mortgage rate minus 10-year Treasury yield spread, bp",
    "consolidated_shares": "US consolidated equity volume relative to the median of prior weekly peaks (ratio)",
}
V_PLAIN = {"stress_loss_to_im": "stress loss to initial margin", "payment_to_qlr": "largest payment obligation to qualifying liquid resources",
           "top5_client_share": "top-five client share of activity", "max(GSD, NSCC) PQD 18.2.2 percentile": "top-five open-position share (PQD 18.2.2)"}
SCORES = PROJECT / "results/scoring/v1.3_indicator"
OUT = PROJECT / "data/narratives"
TOOL = "submit_narrative"
MAX_TOKENS = 800
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["so_what", "so_now_what", "facts_used", "caveats"],
          "properties": {"so_what": {"type": "string"}, "so_now_what": {"type": "string"},
                         "facts_used": {"type": "array", "items": {"type": "string"}},
                         "caveats": {"type": "array", "items": {"type": "string"}}}}
SHEET_FIELDS = ["record_id", "card_id", "card_name", "business_line", "status", "S", "V", "severity", "generated_by",
                "so_what", "so_now_what", "facts_used", "caveats", "check_flags", "prompt_version", "model", "input_file",
                "input_sha256", "decision", "reviewer", "corrected_so_what", "corrected_so_now_what"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prompt_parts(path: Path = PROMPT):
    parts = path.read_text(encoding="utf-8").split("\n---\n")
    if len(parts) != 3 or "{RECORD}" not in parts[2] or "{RECORD}" in parts[1]:
        raise ValueError("narrative prompt must have header, system and user sections; {RECORD} only in the user section")
    label = re.sub(r"^narrative_prompt_", "narrative-prompt-", path.stem)          # narrative-prompt-v1 / -v2
    return parts[1].strip(), parts[2].strip(), label + ":" + sha(path.read_bytes())[:12]


def export_module():
    """The dashboard export (docs/data/export_risk_output.py), for the exact transmission chain it shows."""
    spec = importlib.util.spec_from_file_location("export_risk_output", REPO / "docs/data/export_risk_output.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def chain_context():
    ex = export_module()
    cards = {c["card_id"]: c for c in json.loads(ex.CARD_REGISTRY.read_text())}
    chains = {c["chain_id"]: c for c in json.loads(ex.CHAIN_REGISTRY.read_text())["chains"]}
    return lambda r: ex.transmission(r, cards, chains)[1]


def tidy(value):
    """Round floats to 4 decimals (removes float noise such as 8.000000000000052) for the model and the checks."""
    if isinstance(value, float):
        return round(value, 4) + 0.0
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [tidy(v) for v in value]
    return value


def build_input(records: list[dict], week_records: list[dict], transmission) -> dict:
    """Structured facts for one card (the records of a cross-entity card share them)."""
    return tidy(_build_input(records, week_records, transmission))


def _build_input(records: list[dict], week_records: list[dict], transmission) -> dict:
    r = records[0]
    chains = [transmission(x) for x in records]
    chain = {"world_event": chains[0]["event"], "mechanism": chains[0]["mechanism"], "dtcc_process": chains[0]["dtcc_process"]}
    if any(c != chains[0] for c in chains[1:]):          # cross-entity card whose lines show different chains
        chain["dtcc_process"] = "; ".join(f"{x['business_line']}: {c['dtcc_process']}" for x, c in zip(records, chains))
    sig = r.get("signal")
    signal = None if not sig else {k: sig.get(k) for k in ("name", "description", "value", "percentile", "prior_weeks")}
    if sig and sig.get("daily_values"):
        signal["daily_values"] = [{"date": d["date"], "value": d["value"]} for d in sig["daily_values"]]
    ev = r["event_manual"]
    driving = next((e for e in ev["events"] if ev["driving_event_ids"] and e["event_id"] == ev["driving_event_ids"][0]), None)
    names = {x["card_id"]: x["title"] for x in week_records}
    related = r.get("related_news") or []
    return {"card_id": r["card_id"], "card_name": r["title"], "business_lines": [x["business_line"] for x in records],
            "transmission_chain": chain,
            "status": r["status"], "S": r["S"], "S_source": r["S_source"], "signal": signal,
            "driving_event": None if not driving else {"title": driving["title"], "effect_date": driving["effect_date"],
                                                       "outlet": driving.get("outlet"), "source_url": (driving.get("source_urls") or [None])[0]},
            "V": r["V"], "V_tier": r["V_tier"], "V_driver": r["V_driver"], "V_quarter": r["V_quarter"], "V_flags": r["V_flags"],
            "severity": r["severity"], "chain_confidence": r["chain_confidence"]["level"],
            # Amendment B: the shared field may be one of several chains that set this card's S (not only `signal`)
            "shared_signal": [{"card_id": c, "card_name": names.get(c, c), "signal_fields": (r.get("shared_signal_fields") or {}).get(c, []),
                               "note": "this card's S also comes from the shared field(s)"} for c in r.get("shared_signal") or []],
            "S_signal_fields": sorted({mc["field"] for mc in r.get("market_chains") or [] if mc.get("S") is not None and mc.get("S") == r.get("S_market")}),
            "related_news": {"top_titles": [n["title"] for n in related[:5]],
                             "label_counts": dict(Counter(n["label"] for n in related if n.get("label")))}}


def build_input_v2(records: list[dict], week_records: list[dict], transmission) -> dict:
    """v1 input plus: every field that sets S (all tied chains, plain names), market-wide scope, the latest available PQD
    quarter, and a one-line meaning of V."""
    inp = build_input(records, week_records, transmission)
    r = records[0]
    if inp.get("signal"):
        inp["signal"]["plain_name"] = SIGNAL_PLAIN.get(inp["signal"]["name"], inp["signal"]["description"])
        inp["signal"]["scope"] = "market-wide"
    inp["S_signals"] = tidy([{"field": mc["field"], "plain_name": SIGNAL_PLAIN.get(mc["field"], mc["description"]), "scope": "market-wide",
                              "weekly_peak": mc.get("weekly_peak"), "percentile": mc.get("percentile"), "prior_weeks": mc.get("prior_weeks"),
                              "S": mc["S"]} for mc in r.get("market_chains") or [] if mc.get("S") is not None and mc["S"] == r.get("S_market")])
    if r["V_tier"] == "pqd":
        inp["latest_available_pqd_quarter"] = r["V_quarter"]
        inp["V_source"] = "PQD (DTCC public quantitative disclosure)"
    else:
        inp["V_source"] = "public proxy (" + (r["V_driver"] or "") + "), not DTCC data"
    if r["V"] is not None:
        what = V_PLAIN.get(r.get("V_metric") or "", r["V_driver"] or "this buffer measure")
        unit = ""
        for line in ("GSD", "MBSD", "NSCC"):
            if f"({line})" in (r["V_driver"] or ""):
                unit = f" for {line}"
        inp["V_meaning"] = f"V {r['V']} = this buffer measure ({what}{unit}) sits at level {r['V']} of 5 versus its own history"
    return inp


def v_level(v: int) -> str:
    return "low" if v <= 2 else "medium" if v == 3 else "high"


def build_input_v3(records: list[dict], week_records: list[dict], transmission) -> dict:
    """v2 input plus V_short ("V k of 5 (low/medium/high vs own history)") and S_set_by (the first signal or the event)."""
    inp = build_input_v2(records, week_records, transmission)
    if inp.get("V") is not None:
        inp["V_short"] = f"V {inp['V']} of 5 ({v_level(inp['V'])} vs own history)"
    if inp.get("S_signals"):
        inp["S_set_by"] = inp["S_signals"][0]["plain_name"]
    elif inp.get("driving_event"):
        inp["S_set_by"] = f"event: {inp['driving_event']['title']} (effect {inp['driving_event']['effect_date']})"
    return inp


_SOURCES = {}
FRED_PLAIN = {"VIXCLS": "VIX index (FRED)", "SOFR": "SOFR (FRED)", "EFFR": "effective fed funds rate (FRED)",
              "DGS10": "10-year Treasury yield (FRED)", "BAA10Y": "Baa corporate spread over the 10-year Treasury (FRED)",
              "MORTGAGE30US": "30-year mortgage rate (Freddie Mac survey, via FRED)"}


def public_sources(record: dict) -> list[str]:
    """Public data sources for a card: its signal series and, for public-proxy V, the proxy series (names only)."""
    if not _SOURCES:
        import runpy
        ex = export_module()
        _SOURCES.update(series=ex.SERIES_SOURCE, fields=ex.SIGNAL_SERIES, proxy=runpy.run_path(str(ex.FINAL16_CONFIG))["PUBLIC_PROXY"])
    names = []
    for mc in record.get("market_chains") or []:
        for series in _SOURCES["fields"].get(mc["field"], []):
            names.append(_SOURCES["series"].get(series, (FRED_PLAIN.get(series, f"FRED series {series}"),))[0])
    if record.get("V_tier") == "public_proxy" and record["card_id"] in _SOURCES["proxy"]:
        names.append(re.sub(r"\s*\(existing repo files\)", "", _SOURCES["proxy"][record["card_id"]]["source"]))
    return list(dict.fromkeys(names))


def build_input_v31(records: list[dict], week_records: list[dict], transmission) -> dict:
    """v3 input plus related-news items with their outlets (for a verbatim, attributed headline) and watch_sources."""
    inp = build_input_v3(records, week_records, transmission)
    related = records[0].get("related_news") or []
    inp["related_news"]["top_items"] = [{"title": n["title"], "outlet": n.get("outlet", "")} for n in related[:5]]
    inp["watch_sources"] = public_sources(records[0])
    return inp


def build_request(system: str, user: str, config: dict) -> dict:
    return {"modelId": config["model_id"], "system": [{"text": system}, {"cachePoint": {"type": "default"}}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"temperature": config["temperature"], "maxTokens": MAX_TOKENS},
            "toolConfig": {"tools": [{"toolSpec": {"name": TOOL, "description": "Submit so_what, so_now_what, facts_used and caveats for the card.",
                                                   "inputSchema": {"json": SCHEMA}}}],
                           "toolChoice": {"tool": {"name": TOOL}}}}


def parse(response: dict) -> dict:
    if response.get("stopReason") not in ("tool_use", "end_turn"):
        raise ValueError("incomplete_response:" + str(response.get("stopReason")))
    tools = [p["toolUse"] for p in response.get("output", {}).get("message", {}).get("content", []) if "toolUse" in p]
    if len(tools) != 1 or tools[0].get("name") != TOOL or not isinstance(tools[0].get("input"), dict):
        raise ValueError("expected exactly one submit_narrative call")
    value = tools[0]["input"]
    Draft202012Validator(SCHEMA).validate(value)                 # strict mode is off: the schema is enforced here
    return value


def worst_case(system: str, user: str, prices: dict) -> Decimal:
    tokens_in = Decimal(len((system + user).encode("utf-8")) // 2 + 200)   # generous: ~4 chars per token in practice
    return (tokens_in * Decimal(prices["input_per_million"]) + Decimal(MAX_TOKENS) * Decimal(prices["output_per_million"])) / Decimal(1_000_000)


def run(week: str, cap: Decimal, dry_run: bool = False, session=None, run_id: str | None = None, out: Path = OUT,
        scores_dir: Path = SCORES, transmission=None, prompt: str = DEFAULT_PROMPT, compare_with: Path | None = None,
        sheet_path: Path | None = None, published_from: Path | None = None) -> dict:
    """prompt "v2" with compare_with=<reviewed sheet>: a comparison file next to the sheet, never the review sheet."""
    doc = json.loads((scores_dir / f"weekly_scores_v1.3_{week}.json").read_text())
    config = json.loads(C.CONFIG.read_text())
    system, user_template, version = prompt_parts(PROMPTS[prompt])
    if compare_with is not None and prompt not in ("v2", "v3"):
        raise ValueError("comparison mode supports prompts v2 and v3")
    make_input = {"v1": build_input, "v2": build_input_v2, "v3": build_input_v3, "v3.1": build_input_v31}[prompt]
    transmission = transmission or chain_context()
    run_id = run_id or "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / "runs" / week / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    records = doc["records"]
    groups = {}
    for r in records:
        if r["status"] == "scored":
            groups.setdefault(r["card_id"], []).append(r)
    inputs = {cid: make_input(rs, records, transmission) for cid, rs in groups.items()}
    with (run_dir / "inputs.jsonl").open("w", encoding="utf-8") as f:
        for cid, rs in groups.items():
            f.write(json.dumps({"card_id": cid, "record_ids": [r["record_id"] for r in rs], "input": inputs[cid]}, ensure_ascii=False) + "\n")
    input_path = run_dir / "inputs.jsonl"
    input_file = str(input_path.relative_to(PROJECT)) if input_path.is_relative_to(PROJECT) else str(input_path)
    summary = {"week": week, "run_id": run_id, "prompt_version": version, "model": config["model_id"], "cap_usd": str(cap),
               "dry_run": dry_run, "cards_called": len(groups), "records": len(records), "template_records": sum(r["status"] != "scored" for r in records),
               "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0,
               "estimated_cost_usd": "0", "estimated_cost_without_cache_usd": "0", "status": "started"}
    users = {cid: user_template.replace("{RECORD}", json.dumps(inputs[cid], ensure_ascii=False, indent=1)) for cid in groups}
    estimate = sum(worst_case(system, users[c], config["pricing"]) for c in groups)
    summary["worst_case_estimate_usd"] = str(estimate.quantize(Decimal("0.0001")))
    if dry_run:
        with (run_dir / "prepared_requests.jsonl").open("w", encoding="utf-8") as f:       # derived from scores only; no article text
            for c in groups:
                f.write(json.dumps(build_request(system, users[c], config), ensure_ascii=False) + "\n")
        summary["status"] = "dry_run"
        C.dump(run_dir / "summary.json", summary)
        return summary
    if session is None:
        from botocore.config import Config
        session = C.aws_session(config)
        sdk = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=config["read_timeout_seconds"])
        sts, runtime = session.client("sts", config=sdk), session.client("bedrock-runtime", config=sdk)
    else:
        sts, runtime = session.client("sts"), session.client("bedrock-runtime")
    if sts.get_caller_identity()["Account"] != config["expected_account_id"]:
        raise ValueError("AWS account does not match the approved config")
    spent, uncached, results = Decimal(0), Decimal(0), {}
    for cid in groups:
        reserve = worst_case(system, users[cid], config["pricing"])
        if spent + reserve > cap:
            summary["status"] = "budget_limit"; break
        request = build_request(system, users[cid], config)
        try:
            response, _ = C.invoke(runtime, request, lambda n, e: C.dump(run_dir / "raw" / f"{cid}_attempt_{n}_error.json", e),
                                   config["throttling_retries"], config["retry_base_seconds"])
        except Exception as exc:
            summary.update(status="invocation_error", invocation_error=C.safe_error(exc), unreported_cost_reserve_usd=str(reserve)); break
        usage = response.get("usage", {})
        cost = C.token_cost(usage, config["pricing"]); spent += cost; uncached += C.cost_without_cache(usage, config["pricing"])
        for src, dst in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"), ("cacheReadInputTokens", "cache_read_input_tokens"),
                         ("cacheWriteInputTokens", "cache_write_input_tokens")):
            summary[dst] += usage.get(src, 0)
        C.dump(run_dir / "raw" / f"{cid}.json", {"card_id": cid, "request_sha256": sha(json.dumps(request, sort_keys=True).encode()),
                                                "output": response.get("output"), "stopReason": response.get("stopReason"), "usage": usage,
                                                "estimated_cost_usd": str(cost)})
        try:
            value = parse(response)
            flags = NC.check(value["so_what"], value["so_now_what"], inputs[cid], value["facts_used"])
            if prompt in ("v2", "v3", "v3.1"):
                flags += NC.style_flags(value["so_what"], value["so_now_what"], inputs[cid], version=prompt)
        except Exception as exc:
            value, flags = {"so_what": "", "so_now_what": "", "facts_used": [], "caveats": []}, [f"invalid output: {exc}"[:300]]
        results[cid] = (value, flags)
    summary.update(estimated_cost_usd=str(spent), estimated_cost_without_cache_usd=str(uncached))
    if summary["status"] == "started":
        summary["status"] = "complete"
    if compare_with is not None:
        if prompt == "v3":
            return write_comparison_v3(summary, run_dir, week, compare_with, results, inputs, out)
        return write_comparison(summary, run_dir, week, compare_with, results, inputs, out)
    rows = []
    for r in records:
        base = {"record_id": r["record_id"], "card_id": r["card_id"], "card_name": r["title"], "business_line": r["business_line"],
                "status": r["status"], "S": r["S"], "V": r["V"], "severity": r["severity"], "prompt_version": version,
                "decision": "", "reviewer": "", "corrected_so_what": "", "corrected_so_now_what": ""}
        if r["status"] != "scored":
            rows.append({**base, "generated_by": "template", "so_what": NC.TEMPLATE_SO_WHAT, "so_now_what": NC.TEMPLATE_SO_NOW_WHAT,
                         "facts_used": "", "caveats": "", "check_flags": "", "model": "", "input_file": "", "input_sha256": ""})
            continue
        value, flags = results.get(r["card_id"], ({"so_what": "", "so_now_what": "", "facts_used": [], "caveats": []}, ["not generated (stopped before this card)"]))
        rows.append({**base, "generated_by": "ai", "so_what": value["so_what"], "so_now_what": value["so_now_what"],
                     "facts_used": json.dumps(value["facts_used"], ensure_ascii=False), "caveats": json.dumps(value["caveats"], ensure_ascii=False),
                     "check_flags": json.dumps(flags, ensure_ascii=False), "model": config["model_id"], "input_file": input_file,
                     "input_sha256": sha(json.dumps(inputs[r["card_id"]], sort_keys=True, ensure_ascii=False).encode())})
    fields = SHEET_FIELDS
    if published_from is not None:       # the currently published text, next to each draft, for comparison only
        published = published_text(published_from)
        for row in rows:
            row["published_so_what"], row["published_so_now_what"] = published.get(row["record_id"], ("", ""))
        i = SHEET_FIELDS.index("so_now_what") + 1
        fields = SHEET_FIELDS[:i] + ["published_so_what", "published_so_now_what"] + SHEET_FIELDS[i:]
    if sheet_path is not None:
        sheet = Path(sheet_path)                                    # never overwritten ("x" below)
    else:
        sheet = out / f"review_narratives_{week}.csv"
        if sheet.exists():
            sheet = out / f"review_narratives_{week}_{run_id}.csv"
    with sheet.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    summary.update(review_sheet=str(sheet.relative_to(PROJECT)) if sheet.is_relative_to(PROJECT) else str(sheet),
                   flagged_cards=sum(1 for _, f in results.values() if f))
    C.dump(run_dir / "summary.json", summary)
    return summary


def published_text(sheet: Path) -> dict:
    """record_id -> (so_what, so_now_what) as the dashboard export publishes them from a reviewed sheet: corrected text
    for edit, generated text for approve, fixed text for template rows; nothing for undecided or rejected rows."""
    out = {}
    with Path(sheet).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = (r.get("decision") or "").strip().lower()
            if r["generated_by"] == "template":
                out[r["record_id"]] = (NC.TEMPLATE_SO_WHAT, NC.TEMPLATE_SO_NOW_WHAT)
            elif d in ("approve", "edit") and (r.get("reviewer") or "").strip():
                pick = lambda k: (r.get("corrected_" + k) or "").strip() if d == "edit" and (r.get("corrected_" + k) or "").strip() else r[k]
                out[r["record_id"]] = (pick("so_what"), pick("so_now_what"))
    return out


COMPARE_FIELDS = ["card_id", "record_ids", "edited_so_what", "edited_so_now_what", "v2_so_what", "v2_so_now_what", "v2_check_flags",
                  "v2_style_flags", "latest_not_next_pqd", "no_firm_specific_wording", "plain_names", "shared_signal_mentioned",
                  "v_meaning_given", "unsupported_inference"]


def write_comparison(summary, run_dir, week, sheet, results, inputs, out):
    """Edited (reviewed) text next to the v2 draft, with the problems the reviewer fixed checked on the v2 text."""
    with Path(sheet).open(encoding="utf-8", newline="") as f:
        edited = {}
        for r in csv.DictReader(f):
            if r["generated_by"] == "ai":
                edited.setdefault(r["card_id"], {"rows": [], **r})["rows"].append(r["record_id"])
    rows = []
    for cid, (value, flags) in results.items():
        e = edited.get(cid, {"rows": []})
        style = NC.style_flags(value["so_what"], value["so_now_what"], inputs[cid]) if value["so_what"] else ["not generated"]
        yes = lambda bad: "no" if any(bad in f for f in style + flags) else "yes"
        rows.append({"card_id": cid, "record_ids": "|".join(e["rows"]),
                     "edited_so_what": e.get("corrected_so_what") or e.get("so_what", ""), "edited_so_now_what": e.get("corrected_so_now_what") or e.get("so_now_what", ""),
                     "v2_so_what": value["so_what"], "v2_so_now_what": value["so_now_what"],
                     "v2_check_flags": json.dumps([f for f in flags if f not in style], ensure_ascii=False), "v2_style_flags": json.dumps(style, ensure_ascii=False),
                     "latest_not_next_pqd": yes("latest available PQD"), "no_firm_specific_wording": yes("specific firms"),
                     "plain_names": yes("series codes"), "shared_signal_mentioned": "n/a" if not inputs[cid].get("shared_signal") else yes("shared signal"),
                     "v_meaning_given": yes("V meaning"), "unsupported_inference": "read: no code check"})
    path = out / f"comparison_narratives_v2_{week}.csv"
    if path.exists():
        path = out / f"comparison_narratives_v2_{week}_{summary['run_id']}.csv"
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COMPARE_FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    summary.update(comparison_file=str(path.relative_to(PROJECT)) if path.is_relative_to(PROJECT) else str(path))
    C.dump(run_dir / "summary.json", summary)
    return summary


COMPARE_FIELDS_V3 = ["card_id", "record_ids", "edited_so_what", "edited_so_now_what", "edited_words", "v2_so_what", "v2_so_now_what", "v2_words",
                     "v3_so_what", "v3_so_now_what", "v3_words", "v3_check_flags", "v3_style_flags", "within_limits", "latest_not_next_pqd",
                     "no_firm_specific_wording", "plain_names", "shared_signal_mentioned", "v_short_form", "no_interpretive_words",
                     "no_pqd_on_proxy", "only_setting_signal_in_so_what", "unsupported_inference"]


def words(a: str, b: str) -> str:
    return f"{len((a or '').split())}/{len((b or '').split())}"


def write_comparison_v3(summary, run_dir, week, sheet, results, inputs, out):
    """Reviewed text, the v2 draft (from comparison_narratives_v2_<week>.csv when present) and the v3 draft, with the
    review's problems checked on v3 and word counts (so_what/so_now_what) for all three."""
    with Path(sheet).open(encoding="utf-8", newline="") as f:
        edited = {}
        for r in csv.DictReader(f):
            if r["generated_by"] == "ai":
                edited.setdefault(r["card_id"], {"rows": [], **r})["rows"].append(r["record_id"])
    v2 = {}
    v2_path = out / f"comparison_narratives_v2_{week}.csv"
    if v2_path.exists():
        with v2_path.open(encoding="utf-8", newline="") as f:
            v2 = {r["card_id"]: r for r in csv.DictReader(f)}
    rows = []
    for cid, (value, flags) in results.items():
        e, p2 = edited.get(cid, {"rows": []}), v2.get(cid, {})
        style = NC.style_flags(value["so_what"], value["so_now_what"], inputs[cid], version="v3") if value["so_what"] else ["not generated"]
        base = [f for f in flags if f not in style]
        yes = lambda *bad: "no" if any(b in f for b in bad for f in style + base) else "yes"
        es, en = e.get("corrected_so_what") or e.get("so_what", ""), e.get("corrected_so_now_what") or e.get("so_now_what", "")
        rows.append({"card_id": cid, "record_ids": "|".join(e["rows"]), "edited_so_what": es, "edited_so_now_what": en, "edited_words": words(es, en),
                     "v2_so_what": p2.get("v2_so_what", ""), "v2_so_now_what": p2.get("v2_so_now_what", ""),
                     "v2_words": words(p2.get("v2_so_what", ""), p2.get("v2_so_now_what", "")) if p2 else "",
                     "v3_so_what": value["so_what"], "v3_so_now_what": value["so_now_what"], "v3_words": words(value["so_what"], value["so_now_what"]),
                     "v3_check_flags": json.dumps(base, ensure_ascii=False), "v3_style_flags": json.dumps(style, ensure_ascii=False),
                     "within_limits": yes("words >", "sentences >"), "latest_not_next_pqd": yes("latest available PQD"),
                     "no_firm_specific_wording": yes("specific firms"), "plain_names": yes("series codes"),
                     "shared_signal_mentioned": "n/a" if not inputs[cid].get("shared_signal") else yes("shared signal"),
                     "v_short_form": yes("short form", "V ratio name"), "no_interpretive_words": yes("interpretive"),
                     "no_pqd_on_proxy": "n/a" if inputs[cid].get("V_tier") != "public_proxy" else yes("PQD mentioned"),
                     "only_setting_signal_in_so_what": yes("second tied signal", "lacks the percentile"), "unsupported_inference": "read: no code check"})
    path = out / f"comparison_narratives_v3_{week}.csv"
    if path.exists():
        path = out / f"comparison_narratives_v3_{week}_{summary['run_id']}.csv"
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COMPARE_FIELDS_V3, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    summary.update(comparison_file=str(path.relative_to(PROJECT)) if path.is_relative_to(PROJECT) else str(path))
    C.dump(run_dir / "summary.json", summary)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--week", required=True, help="Monday, YYYY-MM-DD")
    p.add_argument("--cap", type=Decimal, required=True, help="hard USD cap for the model calls")
    p.add_argument("--dry-run", action="store_true", help="build inputs and requests, estimate the cost, no model calls")
    p.add_argument("--prompt", choices=sorted(PROMPTS), default=DEFAULT_PROMPT, help=f"default {DEFAULT_PROMPT}")
    p.add_argument("--compare-with", type=Path, help="reviewed sheet: write a v2/v3 comparison file instead of a review sheet")
    p.add_argument("--sheet", type=Path, help="write the review sheet to this new file (never overwritten)")
    p.add_argument("--published-from", type=Path, help="reviewed sheet whose published text is added as published_* columns")
    a = p.parse_args(argv)
    if date.fromisoformat(a.week).weekday() != 0:
        p.error("--week must be a Monday")
    if not a.cap.is_finite() or a.cap <= 0:
        p.error("--cap must be positive")
    print(json.dumps(run(a.week, a.cap, a.dry_run, prompt=a.prompt, compare_with=a.compare_with, sheet_path=a.sheet,
                         published_from=a.published_from), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

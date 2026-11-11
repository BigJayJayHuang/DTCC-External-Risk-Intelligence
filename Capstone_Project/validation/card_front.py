"""AI-drafted card front layer (display only), written to review sheets.

    python -m validation.card_front playbook --cap 0.30 [--dry-run]            # one-time: data/narratives/card_playbook.csv
    python -m validation.card_front front --week 2026-11-02 --cap 0.20 [--dry-run]

- playbook: one model call per final16 card (16). Input: card id and name, business lines, risk family, and the card's
  default transmission chain on each business line (week-independent: the first component chain on that line).
  Output: chain_short_1/2/3 and 2-3 suggested actions (ids <card_id>.a1..a3 assigned in code). Writes
  data/narratives/card_playbook.csv (never overwritten: a later run gets a _<run_id> suffix) with empty
  decision / reviewer / corrected columns.
- front: one call per scored card of the week (a cross-entity pair shares one call). Input: the narrative v3.1 input
  (validation.narratives.build_input_v31) plus the card's playbook (chain_short, actions) from --playbook. Output:
  headline, headline_source, what_happened, so_what_front, action_id, so_now_what_front, action_reason. Writes
  data/narratives/review_front_<week>.csv (never overwritten) with one row per scored record.
- Records with any other status get fixed, non-AI front text in the export (card name and
  card_front_checks.TEMPLATE_WHAT_HAPPENED); no call and no sheet row.
- Model: validation/llm_classifier_config.json (us.anthropic.claude-sonnet-4-6, temperature 0), system text cached,
  forced tool, flat schema with strict mode off, validated in code; then validation/card_front_checks.py. Every flag
  is recorded in the sheet.
- Hard USD cap: before each call the worst case (input estimate + max_tokens output) must fit under what is left.
Never changes S, V, severity, status or ranking, and never writes the event register, sign-offs or docs/.
"""
import argparse, csv, hashlib, json, re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from . import card_front_checks as F
from . import llm_classifier as C
from . import narratives as N
from .paths import PROJECT

OUT = PROJECT / "data/narratives"
PLAYBOOK = OUT / "card_playbook.csv"
PROMPT_PLAYBOOK = Path(__file__).with_name("card_playbook_prompt_v1.md")
PROMPT_FRONT = Path(__file__).with_name("card_front_prompt_v1.md")
REFERENCE_WEEK = "2026-11-02"                   # the scores file that lists each card's business lines
MAX_TOKENS = 700
_S = {"type": "string"}
PLAYBOOK_TOOL, FRONT_TOOL = "submit_card_playbook", "submit_card_front"
PLAYBOOK_SCHEMA = {"type": "object", "additionalProperties": False,
                   "required": ["chain_short_1", "chain_short_2", "chain_short_3", "action_1_text", "action_1_kind",
                                "action_2_text", "action_2_kind", "action_3_text", "action_3_kind"],
                   "properties": {k: _S for k in ["chain_short_1", "chain_short_2", "chain_short_3", "action_1_text", "action_1_kind",
                                                  "action_2_text", "action_2_kind", "action_3_text", "action_3_kind"]}}
FRONT_KEYS = ["headline", "headline_source", "what_happened", "so_what_front", "action_id", "so_now_what_front", "action_reason"]
FRONT_SCHEMA = {"type": "object", "additionalProperties": False, "required": FRONT_KEYS, "properties": {k: _S for k in FRONT_KEYS}}
PLAYBOOK_FIELDS = ["card_id", "card_name", "business_lines", "chain_short_1", "chain_short_2", "chain_short_3",
                   "action_1_id", "action_1_kind", "action_1_text", "action_2_id", "action_2_kind", "action_2_text",
                   "action_3_id", "action_3_kind", "action_3_text", "check_flags", "source_chain_ids", "prompt_version", "model",
                   "decision", "reviewer", "corrected_chain_short_1", "corrected_chain_short_2", "corrected_chain_short_3",
                   "corrected_action_1_text", "corrected_action_2_text", "corrected_action_3_text",
                   "corrected_action_1_kind", "corrected_action_2_kind", "corrected_action_3_kind"]
FRONT_FIELDS = ["record_id", "card_id", "card_name", "business_line", "status", "severity", "headline", "headline_source",
                "what_happened", "so_what_front", "action_id", "so_now_what_front", "action_reason", "alternative_actions",
                "chain_short", "sources_line", "check_flags", "drafting_flags", "prompt_version", "model", "input_file",
                "input_sha256", "decision", "reviewer", "corrected_headline", "corrected_what_happened",
                "corrected_so_what_front", "corrected_action_id", "corrected_headline_source"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prompt_parts(path: Path):
    system, user, label = N.prompt_parts(path)
    return system, user, path.stem.replace("_", "-") + ":" + label.split(":")[1]


def build_request(system: str, user: str, config: dict, tool: str, schema: dict, description: str) -> dict:
    return {"modelId": config["model_id"], "system": [{"text": system}, {"cachePoint": {"type": "default"}}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"temperature": config["temperature"], "maxTokens": MAX_TOKENS},
            "toolConfig": {"tools": [{"toolSpec": {"name": tool, "description": description, "inputSchema": {"json": schema}}}],
                           "toolChoice": {"tool": {"name": tool}}}}


def parse(response: dict, tool: str, schema: dict) -> dict:
    if response.get("stopReason") not in ("tool_use", "end_turn"):
        raise ValueError("incomplete_response:" + str(response.get("stopReason")))
    tools = [p["toolUse"] for p in response.get("output", {}).get("message", {}).get("content", []) if "toolUse" in p]
    if len(tools) != 1 or tools[0].get("name") != tool or not isinstance(tools[0].get("input"), dict):
        raise ValueError(f"expected exactly one {tool} call")
    value = tools[0]["input"]
    Draft202012Validator(schema).validate(value)              # strict mode is off: the schema is enforced here
    return value


def worst_case(system: str, user: str, prices: dict) -> Decimal:
    tokens_in = Decimal(len((system + user).encode("utf-8")) // 2 + 300)
    return (tokens_in * Decimal(prices["input_per_million"]) + Decimal(MAX_TOKENS) * Decimal(prices["output_per_million"])) / Decimal(1_000_000)


def clients(session, config):
    if session is None:
        from botocore.config import Config
        session = C.aws_session(config)
        sdk = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=config["read_timeout_seconds"])
        sts, runtime = session.client("sts", config=sdk), session.client("bedrock-runtime", config=sdk)
    else:
        sts, runtime = session.client("sts"), session.client("bedrock-runtime")
    if sts.get_caller_identity()["Account"] != config["expected_account_id"]:
        raise ValueError("AWS account does not match the approved config")
    return runtime


def call_all(users: dict, system: str, config: dict, cap: Decimal, run_dir: Path, summary: dict, session, tool: str, schema: dict,
             description: str) -> dict:
    """One forced-tool call per key, under the cap. Returns key -> parsed value or an Exception."""
    runtime = clients(session, config)
    spent, uncached, results = Decimal(0), Decimal(0), {}
    for key, user in users.items():
        reserve = worst_case(system, user, config["pricing"])
        if spent + reserve > cap:
            summary["status"] = "budget_limit"; break
        request = build_request(system, user, config, tool, schema, description)
        try:
            response, _ = C.invoke(runtime, request, lambda n, e: C.dump(run_dir / "raw" / f"{key}_attempt_{n}_error.json", e),
                                   config["throttling_retries"], config["retry_base_seconds"])
        except Exception as exc:
            summary.update(status="invocation_error", invocation_error=C.safe_error(exc), unreported_cost_reserve_usd=str(reserve)); break
        usage = response.get("usage", {})
        cost = C.token_cost(usage, config["pricing"]); spent += cost; uncached += C.cost_without_cache(usage, config["pricing"])
        for src, dst in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"), ("cacheReadInputTokens", "cache_read_input_tokens"),
                         ("cacheWriteInputTokens", "cache_write_input_tokens")):
            summary[dst] += usage.get(src, 0)
        C.dump(run_dir / "raw" / f"{key}.json", {"key": key, "request_sha256": sha(json.dumps(request, sort_keys=True).encode()),
                                                "output": response.get("output"), "stopReason": response.get("stopReason"), "usage": usage,
                                                "estimated_cost_usd": str(cost)})
        try:
            results[key] = parse(response, tool, schema)
        except Exception as exc:
            results[key] = exc
    summary.update(estimated_cost_usd=str(spent), estimated_cost_without_cache_usd=str(uncached))
    if summary["status"] == "started":
        summary["status"] = "complete"
    return results


def new_summary(kind: str, run_id: str, version: str, config: dict, cap: Decimal, dry_run: bool, **extra) -> dict:
    return {"kind": kind, "run_id": run_id, "prompt_version": version, "model": config["model_id"], "cap_usd": str(cap), "dry_run": dry_run,
            **extra, "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_write_input_tokens": 0,
            "estimated_cost_usd": "0", "estimated_cost_without_cache_usd": "0", "status": "started"}


def new_file(path: Path, run_id: str) -> Path:
    return path.with_name(f"{path.stem}_{run_id}{path.suffix}") if path.exists() else path


def write_csv(path: Path, fields: list, rows: list):
    with path.open("x", encoding="utf-8", newline="") as f:            # never overwritten
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT)) if path.is_relative_to(PROJECT) else str(path)


# ------------------------------------------------------------------ playbook
def playbook_inputs(scores_dir: Path = N.SCORES, week: str = REFERENCE_WEEK) -> dict:
    """card_id -> playbook input; the default chain per business line (first component chain on that line)."""
    ex = N.export_module()
    cards = {c["card_id"]: c for c in json.loads(ex.CARD_REGISTRY.read_text())}
    chains = {c["chain_id"]: c for c in json.loads(ex.CHAIN_REGISTRY.read_text())["chains"]}
    records = json.loads((scores_dir / f"weekly_scores_v1.3_{week}.json").read_text())["records"]
    out = {}
    for r in records:
        comps = cards[r["card_id"]]["component_ids"]
        cid = next((c for c in comps if c.split("-")[0] == r["business_line"]), comps[0])
        c = chains[cid]
        entry = out.setdefault(r["card_id"], {"card_id": r["card_id"], "card_name": r["title"], "business_lines": [], "risk_family": r["risk_family"],
                                             "chains": []})
        entry["business_lines"].append(r["business_line"])
        step = {"business_line": r["business_line"], "chain_id": cid, "world_event": c["world_event"]["EN"], "mechanism": c["mechanism"]["EN"],
                "dtcc_process": c["dtcc_process"]["EN"]}
        if not any((s["world_event"], s["mechanism"], s["dtcc_process"]) == (step["world_event"], step["mechanism"], step["dtcc_process"])
                   for s in entry["chains"]):
            entry["chains"].append(step)
    return out


def run_playbook(cap: Decimal, dry_run: bool = False, session=None, run_id: str | None = None, out: Path = OUT,
                 scores_dir: Path = N.SCORES) -> dict:
    config = json.loads(C.CONFIG.read_text())
    system, user_template, version = prompt_parts(PROMPT_PLAYBOOK)
    run_id = run_id or "playbook_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / "runs" / "playbook" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    inputs = playbook_inputs(scores_dir)
    model_inputs = {cid: {k: v for k, v in inp.items()} | {"chains": [{k: v for k, v in s.items() if k != "chain_id"} for s in inp["chains"]]}
                    for cid, inp in inputs.items()}
    with (run_dir / "inputs.jsonl").open("w", encoding="utf-8") as f:
        for cid, inp in inputs.items():
            f.write(json.dumps({"card_id": cid, "input": model_inputs[cid], "chain_ids": [s["chain_id"] for s in inp["chains"]]}, ensure_ascii=False) + "\n")
    users = {cid: user_template.replace("{RECORD}", json.dumps(model_inputs[cid], ensure_ascii=False, indent=1)) for cid in inputs}
    summary = new_summary("playbook", run_id, version, config, cap, dry_run, cards=len(inputs), reference_week=REFERENCE_WEEK)
    summary["worst_case_estimate_usd"] = str(sum(worst_case(system, u, config["pricing"]) for u in users.values()).quantize(Decimal("0.0001")))
    if dry_run:
        summary["status"] = "dry_run"; C.dump(run_dir / "summary.json", summary); return summary
    results = call_all(users, system, config, cap, run_dir, summary, session, PLAYBOOK_TOOL, PLAYBOOK_SCHEMA,
                       "Submit chain_short and the suggested actions for the card.")
    rows = []
    for cid, inp in inputs.items():
        row = {k: "" for k in PLAYBOOK_FIELDS}
        row.update(card_id=cid, card_name=inp["card_name"], business_lines="|".join(inp["business_lines"]), prompt_version=version,
                   model=config["model_id"], source_chain_ids="|".join(s["chain_id"] for s in inp["chains"]))
        value = results.get(cid)
        if isinstance(value, dict):
            row.update({k: value[k].strip() for k in ("chain_short_1", "chain_short_2", "chain_short_3")})
            kinds = {}
            for k in (1, 2, 3):
                text = value[f"action_{k}_text"].strip()
                if text:
                    row.update({f"action_{k}_id": f"{cid}.a{k}", f"action_{k}_text": text, f"action_{k}_kind": value[f"action_{k}_kind"].strip().lower()})
                    kinds[f"{cid}.a{k}"] = row[f"action_{k}_kind"]
            flags = F.playbook_flags(row, kinds)
        else:
            flags = ["not generated (stopped before this card)"] if value is None else [f"invalid output: {value}"[:300]]
        row["check_flags"] = json.dumps(flags, ensure_ascii=False)
        rows.append(row)
    sheet = new_file(out / PLAYBOOK.name, run_id)
    write_csv(sheet, PLAYBOOK_FIELDS, rows)
    summary.update(playbook_sheet=rel(sheet), flagged_cards=sum(1 for r in rows if json.loads(r["check_flags"])))
    C.dump(run_dir / "summary.json", summary)
    return summary


def load_draft_playbook(path: Path) -> dict:
    """card_id -> {chain_short, actions [{action_id, text}]} as drafted (the corrected text when a reviewer edited it)."""
    out = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            d = F.reviewed(r) or "approve"
            pick = lambda k: F._pick(r, k, d)
            out[r["card_id"]] = {"chain_short": [pick(f"chain_short_{k}") for k in (1, 2, 3)],
                                 "actions": [{"action_id": r[f"action_{k}_id"], "text": pick(f"action_{k}_text")} for k in (1, 2, 3)
                                             if pick(f"action_{k}_text")]}
    return out


# ------------------------------------------------------------------ front
def run_front(week: str, cap: Decimal, dry_run: bool = False, session=None, run_id: str | None = None, out: Path = OUT,
              scores_dir: Path = N.SCORES, transmission=None, playbook_path: Path = PLAYBOOK, sheet_path: Path | None = None) -> dict:
    doc = json.loads((scores_dir / f"weekly_scores_v1.3_{week}.json").read_text())
    config = json.loads(C.CONFIG.read_text())
    system, user_template, version = prompt_parts(PROMPT_FRONT)
    playbook = load_draft_playbook(playbook_path)
    transmission = transmission or N.chain_context()
    run_id = run_id or "front_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / "runs" / week / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    records = doc["records"]
    groups = {}
    for r in records:
        if r["status"] == "scored":
            groups.setdefault(r["card_id"], []).append(r)
    inputs = {cid: {**N.build_input_v31(rs, records, transmission), "playbook": playbook[cid]} for cid, rs in groups.items()}
    with (run_dir / "inputs.jsonl").open("w", encoding="utf-8") as f:
        for cid, rs in groups.items():
            f.write(json.dumps({"card_id": cid, "record_ids": [r["record_id"] for r in rs], "input": inputs[cid]}, ensure_ascii=False) + "\n")
    users = {cid: user_template.replace("{RECORD}", json.dumps(inputs[cid], ensure_ascii=False, indent=1)) for cid in groups}
    summary = new_summary("front", run_id, version, config, cap, dry_run, week=week, cards_called=len(groups), records=len(records),
                          playbook=rel(Path(playbook_path)), playbook_sha256=sha(Path(playbook_path).read_bytes()))
    summary["worst_case_estimate_usd"] = str(sum(worst_case(system, u, config["pricing"]) for u in users.values()).quantize(Decimal("0.0001")))
    if dry_run:
        summary["status"] = "dry_run"; C.dump(run_dir / "summary.json", summary); return summary
    results = call_all(users, system, config, cap, run_dir, summary, session, FRONT_TOOL, FRONT_SCHEMA,
                       "Submit the card front: headline, what happened, so what, one playbook action.")
    input_file = rel(run_dir / "inputs.jsonl")
    ex = N.export_module()
    rows = []
    for r in records:
        if r["status"] != "scored":
            continue
        cid, inp = r["card_id"], inputs[r["card_id"]]
        actions = {a["action_id"]: a["text"] for a in inp["playbook"]["actions"]}
        value = results.get(cid)
        if isinstance(value, dict):
            value = {k: v.strip() for k, v in value.items()}
            flags = F.publication_flags(value, inp, actions)
            dflags = F.drafting_flags(value, inp)
        else:
            value = {k: "" for k in FRONT_KEYS}
            flags = ["not generated (stopped before this card)"] if results.get(cid) is None else [f"invalid output: {results[cid]}"[:300]]
            dflags = []
        row = {k: "" for k in FRONT_FIELDS}
        row.update({k: value[k] for k in FRONT_KEYS})
        row.update(record_id=r["record_id"], card_id=cid, card_name=r["title"], business_line=r["business_line"], status=r["status"],
                   severity=r["severity"], chain_short=" → ".join(inp["playbook"]["chain_short"]),
                   alternative_actions=" | ".join(f"{a}: {t}" for a, t in actions.items() if a != value["action_id"]),
                   sources_line=F.sources_line(r, ex.SIGNAL_SERIES, F.headline_outlet(inp, value["headline_source"])),
                   check_flags=json.dumps(flags, ensure_ascii=False), drafting_flags=json.dumps(dflags, ensure_ascii=False),
                   prompt_version=version, model=config["model_id"], input_file=input_file,
                   input_sha256=sha(json.dumps(inp, sort_keys=True, ensure_ascii=False).encode()))
        rows.append(row)
    sheet = Path(sheet_path) if sheet_path else new_file(out / f"review_front_{week}.csv", run_id)
    write_csv(sheet, FRONT_FIELDS, rows)
    summary.update(review_sheet=rel(sheet), flagged_cards=len({r["card_id"] for r in rows if json.loads(r["check_flags"])}),
                   drafting_flagged_cards=len({r["card_id"] for r in rows if json.loads(r["drafting_flags"])}))
    C.dump(run_dir / "summary.json", summary)
    return summary


def recheck(playbook_path: Path = PLAYBOOK, front_path: Path | None = None) -> dict:
    """Recompute check_flags (and drafting_flags) of the playbook and a front sheet in place from the drafted text and
    the stored inputs, e.g. after a change to card_front_checks.py. No model call; text and review columns untouched."""
    def rewrite(path, update):
        with Path(path).open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []
        for r in rows:
            update(r)
        with Path(path).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(rows)
        return rows

    def pb(r):
        if r["chain_short_1"]:
            draft = {k: v for k, v in r.items() if not k.startswith("corrected_")}       # the drafted text and kinds
            r["check_flags"] = json.dumps(F.playbook_flags(draft, F.action_kinds(draft)), ensure_ascii=False)
    res = {"playbook_flagged": sum(1 for r in rewrite(playbook_path, pb) if json.loads(r["check_flags"]))}
    if front_path is not None:
        def fr(r):
            if not r["input_file"] or not r["headline"]:
                return
            inp = F.NC.load_input(PROJECT / r["input_file"], r["record_id"])
            if sha(json.dumps(inp, sort_keys=True, ensure_ascii=False).encode()) != r["input_sha256"]:
                raise ValueError(f"{r['record_id']}: stored input does not match input_sha256")
            actions = {a["action_id"]: a["text"] for a in inp["playbook"]["actions"]}
            r["check_flags"] = json.dumps(F.publication_flags(r, inp, actions), ensure_ascii=False)
            r["drafting_flags"] = json.dumps(F.drafting_flags(r, inp), ensure_ascii=False)
        rows = rewrite(front_path, fr)
        res.update(front_flagged=len({r["card_id"] for r in rows if json.loads(r["check_flags"])}),
                   front_drafting_flagged=len({r["card_id"] for r in rows if json.loads(r["drafting_flags"])}))
    return res


def check_reviewed(playbook_path: Path = PLAYBOOK, front_path: Path | None = None) -> dict:
    """Every check on the reviewed text (corrected columns applied), without writing anything or calling a model:
    playbook rows (playbook_flags with the effective kinds), front rows (publication_flags against the stored input
    and the reviewed playbook; drafting_flags with the reviewed chain_short). Unreviewed rows are reported as such."""
    with Path(playbook_path).open(encoding="utf-8", newline="") as f:
        pb_rows = list(csv.DictReader(f))
    failures, reviewed_pb = [], {}
    for r in pb_rows:
        d = F.reviewed(r)
        if not d:
            failures.append({"sheet": "playbook", "row": r["card_id"], "flags": ["not reviewed (decision approve/edit and reviewer)"]}); continue
        eff = F.effective_row(r)
        flags = F.playbook_flags(eff, F.action_kinds(eff))
        if flags:
            failures.append({"sheet": "playbook", "row": r["card_id"], "flags": flags})
        reviewed_pb[r["card_id"]] = F.effective_playbook(r)
    if front_path is not None:
        with Path(front_path).open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                d = F.reviewed(r)
                if not d:
                    failures.append({"sheet": "front", "row": r["record_id"], "flags": ["not reviewed (decision approve/edit and reviewer)"]}); continue
                inp = F.NC.load_input(PROJECT / r["input_file"], r["record_id"])
                if sha(json.dumps(inp, sort_keys=True, ensure_ascii=False).encode()) != r["input_sha256"]:
                    failures.append({"sheet": "front", "row": r["record_id"], "flags": ["stored input does not match input_sha256"]}); continue
                pb = reviewed_pb.get(r["card_id"])
                front = {k: F._pick(r, k, d) for k in ("headline", "headline_source", "what_happened", "so_what_front", "action_id")}
                front["so_now_what_front"] = (pb or {"actions": {}})["actions"].get(front["action_id"], "")
                flags = F.publication_flags(front, inp, (pb or {"actions": {}})["actions"]) if pb else ["playbook row of this card not usable"]
                reviewed_inp = {**inp, "playbook": {"chain_short": pb["chain_short"], "actions": [{"action_id": a, "text": t} for a, t in pb["actions"].items()]}} if pb else inp
                flags += F.drafting_flags(front, reviewed_inp)
                if flags:
                    failures.append({"sheet": "front", "row": r["record_id"], "flags": flags})
    return {"playbook_rows": len(pb_rows), "failures": failures}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    rc = sub.add_parser("recheck", help="recompute the flag columns from the drafts and stored inputs (no model call)")
    rc.add_argument("--front", type=Path, help="front review sheet to recheck as well")
    rc.add_argument("--playbook", type=Path, default=PLAYBOOK)
    cr = sub.add_parser("check-reviewed", help="run every check on the reviewed text (no writes, no model call)")
    cr.add_argument("--front", type=Path, help="reviewed front sheet")
    cr.add_argument("--playbook", type=Path, default=PLAYBOOK)
    pb = sub.add_parser("playbook", help="draft data/narratives/card_playbook.csv (one-time card config)")
    fr = sub.add_parser("front", help="draft the front layer of one scored week")
    fr.add_argument("--week", required=True, help="Monday, YYYY-MM-DD")
    fr.add_argument("--playbook", type=Path, default=PLAYBOOK)
    for s in (pb, fr):
        s.add_argument("--cap", type=Decimal, required=True, help="hard USD cap for the model calls")
        s.add_argument("--dry-run", action="store_true", help="inputs and worst-case cost, no model calls")
    a = p.parse_args(argv)
    if a.cmd == "recheck":
        print(json.dumps(recheck(a.playbook, a.front), indent=2)); return
    if a.cmd == "check-reviewed":
        res = check_reviewed(a.playbook, a.front)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        raise SystemExit(1 if res["failures"] else 0)
    if not a.cap.is_finite() or a.cap <= 0:
        p.error("--cap must be positive")
    if a.cmd == "playbook":
        res = run_playbook(a.cap, a.dry_run)
    else:
        if date.fromisoformat(a.week).weekday() != 0:
            p.error("--week must be a Monday")
        res = run_front(a.week, a.cap, a.dry_run, playbook_path=a.playbook)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

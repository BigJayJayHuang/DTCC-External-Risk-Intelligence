"""Strict-mode diagnostic: the same v1.4 request (cache on) with the forced tool in strict mode and with strict off.

    python -m validation.llm_strict_diagnostic --budget 0.10 [--out-dir DIR]

Two inputs x two modes = at most 4 Bedrock calls, in this order: strict on (example 1, golden), strict off (example 1,
golden). Before each call a worst-case cost is reserved (static prefix as a fresh cache write, the rest as input, and
the full 1,200 output-token limit); a call that could exceed the budget is not made. Strict-off output is validated in
code against the same schema. Never writes the event register.
"""
import argparse, copy, json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from . import llm_classifier as C

GOLDEN = C.PROJECT / "validation/fixtures/golden_set_20261107.csv"
EXAMPLE_1 = "Dow plunges 1,100 points as bank stocks lead broad selloff"


def inputs():
    golden = [a for a in C.load_news(GOLDEN, date(2026, 11, 2), date(2026, 11, 8), None)[0]
              if a["title"].startswith("Tech stocks log worst day since 2020")]
    example = {"document_id": "diagnostic-example-1", "title": EXAMPLE_1, "url": "https://example.invalid/diagnostic-example-1",
               "published_date": "2026-11-05", "source_id": "diagnostic", "outlet": "diagnostic input", "source_tier": "other",
               "content_scope": "headline_only", "text": EXAMPLE_1}
    return [("v1.4 worked example 1", example), ("golden: Tech stocks log worst day since 2020", golden[0])]


def reservation(request: dict, prices: dict, observed: dict | None) -> Decimal:
    if observed:   # token counts seen for this prompt shape; dynamic part padded 20%
        static, dynamic = observed["static"], int(observed["dynamic"] * 1.2) + 200
    else:          # byte-based, padded 20%
        static = len(json.dumps([request["system"][0], request["toolConfig"]], ensure_ascii=False).encode()) // 3 * 6 // 5
        dynamic = len(json.dumps(request["messages"], ensure_ascii=False).encode()) // 3 * 6 // 5 + 200
    return C.token_cost({"cacheWriteInputTokens": static, "inputTokens": dynamic, "outputTokens": request["inferenceConfig"]["maxTokens"]}, prices)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--budget", type=Decimal, default=Decimal("0.10"))
    p.add_argument("--out-dir", type=Path, default=C.PROJECT / "data/events/diagnostics/strict_mode_20261108")
    a = p.parse_args(argv)
    config = json.loads(C.CONFIG.read_text())
    system, user_t, cards, version = C.prompt_parts_v13(C.PROMPT_V14, "v1.4")
    schema = C.output_schema(cards)
    register = C.load_register(C.REGISTER)
    register_sha = C.sha(C.REGISTER.read_bytes())
    a.out_dir.mkdir(parents=True, exist_ok=False)
    from botocore.config import Config
    session = C.aws_session(config)
    sdk = Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=config["read_timeout_seconds"])
    if session.client("sts", config=sdk).get_caller_identity()["Account"] != config["expected_account_id"]:
        raise SystemExit("AWS account does not match the approved config")
    runtime = session.client("bedrock-runtime", config=sdk)
    calls, spent, observed = [], Decimal(0), None
    plan = [(strict, label, art) for strict in (True, False) for label, art in inputs()]
    base = C.build_request_v13(system, C.render_user_v13(user_t, register, plan[0][2])[0], schema, config, cache=True)
    C.dump(a.out_dir / "tool_schema_in_use.json", base["toolConfig"])
    for n, (strict, label, art) in enumerate(plan, 1):
        user, recent = C.render_user_v13(user_t, register, art)
        request = C.build_request_v13(system, user, schema, config, cache=True)
        request["toolConfig"]["tools"][0]["toolSpec"]["strict"] = strict
        reserve = reservation(request, config["pricing"], observed)
        if spent + reserve > a.budget:
            calls.append({"call": n, "strict": strict, "input": label, "skipped": f"budget: spent {spent} + reserve {reserve} > {a.budget}"})
            break
        errors = []
        try:
            response, attempts = C.invoke(runtime, request, lambda i, e: errors.append(e), config["throttling_retries"], config["retry_base_seconds"])
        except Exception as exc:
            calls.append({"call": n, "strict": strict, "input": label, "invocation_error": C.safe_error(exc)})
            break
        usage = response.get("usage", {})
        cost = C.token_cost(usage, config["pricing"]); spent += cost
        total_in = usage.get("inputTokens", 0) + usage.get("cacheReadInputTokens", 0) + usage.get("cacheWriteInputTokens", 0)
        static = usage.get("cacheReadInputTokens", 0) + usage.get("cacheWriteInputTokens", 0)
        observed = {"static": max(static, (observed or {}).get("static", 0)), "dynamic": max(total_in - static, (observed or {}).get("dynamic", 0))}
        rec = {"call": n, "strict": strict, "input": label, "document_id": art["document_id"], "content_scope": art["content_scope"],
               "prompt_version": version, "stopReason": response.get("stopReason"), "usage": usage, "estimated_cost_usd": str(cost),
               "raw_output": response.get("output"), "attempts": attempts}
        try:
            result, mode, fallback = C.parse_response(response)
            rec.update(response_mode=mode, fence_fallback=fallback, is_relevant=result.get("is_relevant"), card_ids=result.get("card_ids"))
            schema_errors = sorted(e.message for e in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors({"classification": result}))
            rec["schema_valid_in_code"] = not schema_errors
            rec["schema_errors"] = schema_errors[:5]
        except Exception as exc:
            rec.update(parse_error=f"{type(exc).__name__}: {exc}"[:400])
        calls.append(rec)
        C.dump(a.out_dir / f"call_{n}_{'strict' if strict else 'nonstrict'}.json", rec)
    summary = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model_id": config["model_id"], "prompt_version": version,
               "budget_usd": str(a.budget), "estimated_cost_usd": str(spent), "calls": [{k: v for k, v in c.items() if k != "raw_output"} for c in calls],
               "event_register_unchanged": C.sha(C.REGISTER.read_bytes()) == register_sha}
    C.dump(a.out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

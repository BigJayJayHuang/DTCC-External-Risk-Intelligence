"""Prepare, reserve and reconcile incremental Bedrock batches; no register writes."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from . import llm_classifier as C

RUNTIME = C.PROJECT / "data/events/daily_runtime"
BOOTSTRAP = C.PROJECT / "data/events/classifier_runs/phase2_20261105_v2"


def read_state(path, config):
    state = json.loads(path.read_text()) if path.exists() else {
        "version": 1, "account_id": config["expected_account_id"], "requests": {},
        "daily_cost_usd": {}, "reservations": {}, "completed_runs": {}, "bootstrap_runs": [],
    }
    if state["version"] != 1 or state["account_id"] != config["expected_account_id"]:
        raise ValueError("Daily state version/account mismatch")
    for value in state["daily_cost_usd"].values():
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid daily spend in state")
    return state


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pending")
    C.dump(temporary, state)
    temporary.replace(path)


@contextmanager
def state_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def request_hash(request):
    return C.sha(json.dumps(request, sort_keys=True).encode())


def bootstrap(state, folder):
    """Import the paid, audited Phase 2 run once; never call the model again."""
    if not folder.exists() or folder.name in state["bootstrap_runs"]:
        return
    summary = json.loads((folder / "summary.json").read_text())
    if summary["status"] != "complete" or not summary["event_register_unchanged"] or not summary["prompt_unchanged"]:
        raise ValueError("Bootstrap requires a completed protected-register run")
    records = [json.loads(p.read_text()) for p in sorted((folder / "raw").glob("*.json"))]
    cost = sum((C.token_cost(r["usage"], summary["config"]["pricing"]) for r in records), Decimal(0))
    if len(records) != summary["articles_processed"] or cost != Decimal(summary["estimated_cost_usd"]):
        raise ValueError("Bootstrap evidence does not reconcile")
    for record in records:
        state["requests"][record["request_sha256"]] = {
            "run_id": summary["run_id"], "document_id": record["document_id"], "url": record["url"],
        }
    day = summary["run_date"]
    state["daily_cost_usd"][day] = str(Decimal(state["daily_cost_usd"].get(day, "0")) + cost)
    state["bootstrap_runs"].append(folder.name)


def guards(config_path):
    return {"config": C.sha(config_path.read_bytes()), "prompt": C.sha(C.PROMPT.read_bytes()),
            "register": C.sha(C.REGISTER.read_bytes()), "major_participants": C.sha(C.MAJOR.read_bytes()),
            "classifier_code": C.sha(Path(C.__file__).read_bytes()), "daily_code": C.sha(Path(__file__).read_bytes())}


def select_news(news, selected, target, start, end):
    wanted = {(a["document_id"], a["url"]) for a in selected}
    found = set()
    with news.open(encoding="utf-8-sig", newline="") as source, target.open("x", encoding="utf-8", newline="") as output:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            key = (row.get("document_id") or row.get("url"), row.get("url"))
            if key not in wanted or key in found:
                continue
            try:
                published = C.publication_date(row)
            except ValueError:
                continue
            if start.isoformat() <= published <= end.isoformat():
                writer.writerow(row)
                found.add(key)
    if found != wanted:
        raise ValueError("Selected source rows could not be reproduced")


def prepare(args):
    config = json.loads(args.config.read_text())
    if args.lookback_days < 1 or args.max_articles < 1:
        raise ValueError("Lookback and max articles must be positive")
    if not args.budget.is_finite() or not 0 < args.budget <= Decimal(str(config["default_budget_usd"])):
        raise ValueError("Daily budget must be positive and no greater than the configured cap")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        raise ValueError("Invalid run ID")
    start = args.run_date - timedelta(days=args.lookback_days - 1)
    with state_lock(args.state_file):
        state = read_state(args.state_file, config)
        bootstrap(state, BOOTSTRAP)
        if state["reservations"]:
            raise ValueError("Unreconciled daily reservation: recover that run before starting another")
        if args.run_id in state["completed_runs"]:
            raise ValueError("Daily run ID already completed")
        articles, coverage = C.load_news(args.news, start, args.run_date, None)
        body, catalog, cards, _ = C.prompt_parts(C.PROMPT)
        register = C.load_register(C.REGISTER)
        schema = C.output_schema(cards)
        pending = []
        for article in articles:
            prompt, _ = C.render_prompt(body, catalog, register, article)
            request = C.build_request(prompt, schema, config)
            digest = request_hash(request)
            if digest not in state["requests"]:
                pending.append((article, request, digest))
        selected = pending[:args.max_articles]
        spent = Decimal(state["daily_cost_usd"].get(args.run_date.isoformat(), "0"))
        remaining = max(Decimal(0), args.budget - spent)
        run_dir = args.output_dir / args.run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        select_news(args.news, [r[0] for r in selected], run_dir / "selected_news.csv", start, args.run_date)
        estimated = sum((C.estimate_request(r[1], config["pricing"])[0] for r in selected), Decimal(0))
        invoke = bool(selected) and remaining > 0 and not args.dry_run
        plan = {"version": 1, "run_id": args.run_id, "run_date": args.run_date.isoformat(),
                "start": start.isoformat(), "end": args.run_date.isoformat(), "dry_run": args.dry_run,
                "status": "dry_run" if args.dry_run else "ready" if invoke else "no_new_requests" if not selected else "daily_budget_exhausted",
                "invoke": invoke, "coverage": coverage, "already_classified": len(articles) - len(pending),
                "pending_articles": len(pending), "selected_articles": len(selected), "deferred_by_max_articles": len(pending) - len(selected),
                "estimated_selected_cost_usd": str(estimated), "daily_budget_usd": str(args.budget),
                "previous_daily_cost_usd": str(spent), "remaining_daily_budget_usd": str(remaining),
                "request_hashes": [r[2] for r in selected], "guards": guards(args.config),
                "source_news_sha256": C.sha(args.news.read_bytes()),
                "selected_news_sha256": C.sha((run_dir / "selected_news.csv").read_bytes())}
        C.dump(run_dir / "plan.json", plan)
        if not args.dry_run:
            if invoke:
                # This full remaining-budget reservation is published BEFORE any
                # paid call. An interrupted run blocks retries until recovered.
                state["reservations"][args.run_id] = {"run_date": args.run_date.isoformat(), "amount_usd": str(remaining),
                                                       "plan_sha256": C.sha((run_dir / "plan.json").read_bytes())}
                state["daily_cost_usd"][args.run_date.isoformat()] = str(spent + remaining)
            else:
                state["completed_runs"][args.run_id] = {"status": plan["status"], "estimated_cost_usd": "0"}
                handle, _ = C.csv_writer(run_dir / f"candidates_{args.run_date.isoformat()}.csv")
                handle.close()
                C.dump(run_dir / "daily_summary.json", {"plan": plan, "result": {
                    "status": plan["status"], "articles_processed": 0, "articles_unprocessed": len(selected),
                    "relevant": 0, "irrelevant": 0, "failed_checks": 0, "estimated_cost_usd": "0",
                    "availability_check": "not_needed_without_model_invocation"}})
            write_state(args.state_file, state)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("invoke=" + str(invoke).lower() + "\n")
    return plan


def checked_plan(args):
    plan = json.loads(args.plan.read_text())
    if plan["guards"] != guards(args.config):
        raise ValueError("Code, config or protected inputs changed after prepare")
    if C.sha((args.plan.parent / "selected_news.csv").read_bytes()) != plan["selected_news_sha256"]:
        raise ValueError("Prepared news changed")
    state = read_state(args.state_file, json.loads(args.config.read_text()))
    if plan["run_id"] in state["completed_runs"]:
        raise ValueError("Run already reconciled; unreported usage requires manual review")
    reservation = state["reservations"].get(plan["run_id"])
    if not reservation or reservation["plan_sha256"] != C.sha(args.plan.read_bytes()):
        raise ValueError("No matching durable reservation for prepared run")
    return plan, state, reservation


def reconcile(args):
    with state_lock(args.state_file):
        plan, state, reservation = checked_plan(args)
        folder = args.plan.parent / "classifier_runs" / plan["run_id"]
        summary = json.loads((folder / "summary.json").read_text())
        if summary["status"] == "running" or not summary["event_register_unchanged"] or not summary["prompt_unchanged"]:
            raise ValueError("Run incomplete: keep full reservation and recover the evidence")
        observed = Decimal(0)
        for path in (folder / "raw").glob("*.json"):
            raw = json.loads(path.read_text())
            if "request_sha256" not in raw:
                continue  # A rejected/throttled attempt, not a model response.
            if raw["request_sha256"] not in plan["request_hashes"]:
                raise ValueError("Unexpected request in run evidence")
            usage = raw.get("usage", {})
            if "inputTokens" in usage and "outputTokens" in usage:
                observed += C.token_cost(usage, summary["config"]["pricing"])
            state["requests"][raw["request_sha256"]] = {
                "run_id": plan["run_id"], "document_id": raw["document_id"], "url": raw["url"],
            }
        if observed != Decimal(summary["estimated_cost_usd"]):
            raise ValueError("Raw token costs do not match summary; retain reservation")
        unknown = Decimal(summary["unreported_cost_reserve_usd"])
        day = reservation["run_date"]
        state["daily_cost_usd"][day] = str(Decimal(state["daily_cost_usd"][day]) - Decimal(reservation["amount_usd"]) + observed + unknown)
        if unknown:
            state["reservations"][plan["run_id"]].update(amount_usd=str(unknown), status="unreported_usage_requires_review")
        else:
            del state["reservations"][plan["run_id"]]
        state["completed_runs"][plan["run_id"]] = {"status": summary["status"], "estimated_cost_usd": str(observed),
                                                   "unreported_cost_reserve_usd": str(unknown)}
        write_state(args.state_file, state)
        C.dump(args.plan.parent / "daily_summary.json", {"plan": plan, "result": summary})
    return summary


def execute(args, session=None):
    plan, _, reservation = checked_plan(args)
    batch_args = argparse.Namespace(config=args.config, register=C.REGISTER, major=C.MAJOR,
        news=args.plan.parent / "selected_news.csv", start=date.fromisoformat(plan["start"]),
        end=date.fromisoformat(plan["end"]), max_articles=None, budget=Decimal(reservation["amount_usd"]),
        dry_run=False, run_date=date.fromisoformat(plan["run_date"]), run_id=plan["run_id"], output_dir=args.plan.parent)
    C.run(batch_args, session=session)
    return reconcile(args)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "execute", "reconcile"])
    p.add_argument("--state-file", type=Path, default=RUNTIME / "state.json")
    p.add_argument("--config", type=Path, default=C.CONFIG)
    p.add_argument("--plan", type=Path)
    p.add_argument("--news", type=Path, default=C.NEWS)
    p.add_argument("--output-dir", type=Path, default=RUNTIME)
    p.add_argument("--run-id", default=datetime.now(ZoneInfo("America/New_York")).strftime("daily-%Y%m%dT%H%M%S%f"))
    p.add_argument("--run-date", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/New_York")).date())
    p.add_argument("--lookback-days", type=int, default=28)
    p.add_argument("--max-articles", type=int, default=100)
    p.add_argument("--budget", type=Decimal, default=Decimal(10))
    p.add_argument("--dry-run", action="store_true")
    return p


def main():
    args = parser().parse_args()
    try:
        if args.command != "prepare" and args.plan is None:
            raise ValueError("--plan is required for execution/reconciliation")
        result = prepare(args) if args.command == "prepare" else execute(args) if args.command == "execute" else reconcile(args)
        print(json.dumps(result, indent=2), flush=True)
        if args.command != "prepare" and result["status"] not in {"complete", "budget_limit"}:
            raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc) if isinstance(exc, ValueError) else C.safe_error(exc)}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

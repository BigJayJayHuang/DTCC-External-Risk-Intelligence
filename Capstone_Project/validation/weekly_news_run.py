"""Weekly news run: collect, pre-filter, estimate, classify, group, apply the context rule, write the review sheet.

    python -m validation.weekly_news_run --week-start 2026-11-09 --cap 3

Steps for one Monday-Sunday week (the week must be over unless --allow-partial-week):
  1. Google News RSS (news_queries.csv; headline filter; 25 per card) -> inputs/google/
  2. Publisher feeds (publisher_feeds_config.json; keyword pre-filter; full text where allowed) + the Google items
     -> inputs/feeds/classifier_input.csv
  3. Dry run with prompt v1.5, flat schema, caching. Stops if the cache-aware estimate is above --cap.
  4. Classify with the same settings, hard budget --cap.
  5. Group candidates into proposed events, apply Amendment D (market-move news on indicator cards = context).
  6. Write data/events/review/review_<Monday>.csv (never overwritten) and append context rows to
     data/events/context_news.csv.
Never writes the event register or sign-offs. See data/events/WEEKLY_RUNBOOK.md.
"""
import argparse, csv, hashlib, json, re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from . import google_news as G
from . import llm_classifier as C
from . import publisher_feeds as P
from . import review_sheet as RS

WEEKLY = C.PROJECT / "data/events/weekly"
REVIEW_DIR = C.PROJECT / "data/events/review"
PROMPT_VERSION = "v1.5"


def unresolved_reservations(week_dir: Path, current_run: Path) -> list[dict]:
    """Read original classifier receipts; a later resume does not clear an unknown bill."""
    pending=[]
    for path in sorted(Path(week_dir).glob('*/classifier_runs/*/summary.json')):
        if current_run in path.parents:continue
        value=json.loads(path.read_text())
        reserve=Decimal(str(value.get('unreported_cost_reserve_usd','0')))
        inflight=Decimal(str(value.get('inflight_reservation_usd','0')))
        if not reserve.is_finite() or reserve<0:
            raise ValueError('Invalid cost reservation in '+str(path))
        if reserve>0 or inflight>0 or value.get('status')=='running':
            pending.append({'summary_file':str(path),'unreported_cost_reserve_usd':str(max(reserve,inflight)),'status':value.get('status')})
    return pending


def classifier_args(news: Path, out: Path, monday: date, sunday: date, cap: Decimal, run_date: date, dry_run: bool):
    return argparse.Namespace(config=C.CONFIG, register=C.REGISTER, major=C.MAJOR, news=news, start=monday, end=sunday,
                              max_articles=None, budget=cap, dry_run=dry_run, run_date=run_date, run_id="v15", output_dir=out,
                              prompt_version=PROMPT_VERSION, prompt_cache="on", response_schema="flat")


def run_week(week_start: date, cap: Decimal, *, today: date | None = None, allow_partial: bool = False, run_id: str | None = None,
             weekly_dir: Path = WEEKLY, review_dir: Path = REVIEW_DIR, context_path: Path = RS.CONTEXT_NEWS,
             collect_google=G.collect, collect_feeds=P.main, classify=C.run, official_news: Path = C.NEWS,
             collect_only: bool = False, dry_run: bool = False, offline_google_from: Path | None = None) -> dict:
    monday, sunday = G.week_window(week_start)
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    if not allow_partial and today <= sunday:
        raise SystemExit(f"The week {monday}..{sunday} is not over yet (today {today}); use --allow-partial-week to run anyway.")
    if not cap.is_finite() or cap <= 0:
        raise SystemExit("--cap must be finite and positive")
    if collect_only and dry_run:
        raise SystemExit("Choose --collect-only or --dry-run")
    run_id = run_id or "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id):
        raise ValueError('Invalid weekly run ID')
    out = weekly_dir / monday.isoformat() / run_id
    out.mkdir(parents=True, exist_ok=False)
    result = {"week_start": monday.isoformat(), "week_end": sunday.isoformat(), "cap_usd": str(cap), "run_dir": str(out),
              "prompt_version": PROMPT_VERSION, "status": "started", "paid_calls": 0,
              "collect_only":collect_only,"dry_run":dry_run}
    def finish(status, **kw):
        result.update(status=status, **kw)
        (out / "weekly_summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return result

    # 1-2. collect and pre-filter
    g_dir = out / "inputs" / "google"
    google_kwargs = {"offline_dir":offline_google_from} if offline_google_from else {}
    g_rows, g_manifest, g_stats, g_dropped = collect_google(json.loads(G.CONFIG.read_text()), G.load_queries(), monday, g_dir, **google_kwargs)
    G.write_csv(g_dir / "google_news.csv", g_rows, G.BASE_FIELDS + G.EXTRA_FIELDS)
    (g_dir/'fetch_manifest.json').write_text(json.dumps(g_manifest,indent=2)+'\n')
    (g_dir/'filtered_out.json').write_text(json.dumps(g_dropped,ensure_ascii=False,indent=2)+'\n')
    if not Path(official_news).is_file():
        return finish('stopped_official_export_unavailable',official_input=str(official_news),
                      reason='Restore or refresh the daily official news export; it must not be silently omitted.')
    result['official_input']={"path":str(official_news),"sha256":hashlib.sha256(Path(official_news).read_bytes()).hexdigest()}
    feeds = collect_feeds(["--out-dir", str(out / "inputs" / "feeds"), "--google", str(g_dir / "google_news.csv"),
                           "--official",str(official_news),"--week-start",monday.isoformat(),"--week-end",sunday.isoformat()])
    news = out / "inputs" / "feeds" / "classifier_input.csv"
    result.update(google=g_stats, feeds={k: feeds.get(k) for k in ("items_to_classifier", "scope_totals", "published_range","official_input","per_source")})
    if collect_only:
        return finish('collected_for_review_no_model_calls',classifier_input=str(news),
                      next_step='Review evidence coverage; use --dry-run for a cost estimate without invoking AWS.')

    # 3. dry run and cap check
    run_date = today
    dry = classify(classifier_args(news, out, monday, sunday, cap, run_date, dry_run=True))
    estimate = Decimal(str(dry.get("estimated_full_run_cost_with_cache_usd") or dry["estimated_full_run_cost_usd"]))
    result.update(items_in_window=dry["coverage"]["selected_articles"], estimate_with_cache_usd=str(estimate))
    if dry_run:
        return finish('dry_run_no_model_calls',estimate_above_cap=estimate>cap,classifier_input=str(news))
    if estimate > cap:
        return finish("stopped_estimate_above_cap")
    pending=unresolved_reservations(out.parent,out)
    if pending:
        return finish('stopped_unresolved_prior_cost_reserve',pending_reservations=pending,
                      next_step='Reconcile prior interrupted request costs before starting another paid weekly batch. Collection and dry-run modes remain available.')

    # 4. classify
    result['paid_calls']=None  # Exact paid-call count belongs to the classifier receipt.
    real = classify(classifier_args(news, out, monday, sunday, cap, run_date, dry_run=False))
    result.update(classifier={k: real.get(k) for k in ("status", "relevant", "irrelevant", "failed_checks", "input_tokens", "output_tokens",
                                                      "cache_read_input_tokens", "cache_write_input_tokens", "estimated_cost_usd")})
    result['classifier']['unreported_cost_reserve_usd']=real.get('unreported_cost_reserve_usd','0')
    # A transport interruption may leave an unresolved reservation. Preserve it;
    # do not automatically resume or represent the run as a clean completion.
    if Decimal(str(real.get('unreported_cost_reserve_usd','0')))>0:
        return finish('stopped_unresolved_cost_reserve',next_step='Reconcile the saved response/reservation before any new paid call.')
    if real.get("status") not in ("complete", "budget_limit"):
        return finish("stopped_classifier_" + str(real.get("status")))

    # 5-6. group, context rule, review sheet, context news
    candidates = out / f"candidates_{run_date.isoformat()}.csv"
    rows, ctx = RS.build(candidates, monday) if candidates.exists() else ([], [])
    review_dir.mkdir(parents=True, exist_ok=True)
    sheet = review_dir / f"review_{monday.isoformat()}.csv"
    if sheet.exists():   # never overwrite a sheet that may already hold decisions
        sheet = review_dir / f"review_{monday.isoformat()}_{run_id}.csv"
    with sheet.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RS.FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    added = RS.append_context(context_path, ctx)
    tiers = {t: sum(r["review_tier"] == t for r in rows) for t in ("required", "auto", "context")}
    return finish("complete" if real.get("status") == "complete" else "partial_budget_limit", review_sheet=str(sheet),
                  proposed_events=len(rows), tiers=tiers, context_rows_added=added,
                  next_step="Review the 'required' rows, then run: python -m validation.promote_reviewed --sheet " + str(sheet))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--week-start", type=date.fromisoformat, default=G.last_full_week(datetime.now(ZoneInfo("America/New_York")).date()))
    p.add_argument("--cap", type=Decimal, required=True, help="hard USD cap for the model calls of this week")
    p.add_argument("--allow-partial-week", action="store_true")
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--collect-only',action='store_true',help='Collect/filter/cache evidence only; never invoke a model')
    modes.add_argument('--dry-run',action='store_true',help='Collect and estimate locally; never invoke a model')
    p.add_argument('--official',type=Path,default=C.NEWS,help='Daily official-news CSV; always included through the keyword filter')
    p.add_argument('--offline-google-from',type=Path,help='Reparse an existing RSS batch instead of repeating Google requests')
    a = p.parse_args(argv)
    print(json.dumps(run_week(a.week_start, a.cap, allow_partial=a.allow_partial_week,official_news=a.official,
                             collect_only=a.collect_only,dry_run=a.dry_run,offline_google_from=a.offline_google_from), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

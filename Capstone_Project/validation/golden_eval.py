"""Score a classifier run against a golden-set fixture.

    python -m validation.golden_eval --fixture validation/fixtures/golden_set_20261107.csv \
        --run-dir data/events/golden_runs/20261107/classifier_runs/<run_id> --candidates <candidates csv>

Writes GOLDEN_REPORT.md next to the run and prints the metrics as JSON. Reads only; calls no model.
"""
import argparse, csv, json
from decimal import Decimal
from pathlib import Path

from .llm_classifier import PROJECT


def outcomes(run_dir: Path, candidates: Path):
    out = {}
    if candidates.exists():
        with candidates.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                raw = json.loads((PROJECT / r["raw_output_file"]).read_text())
                tool_input = next(p["toolUse"]["input"] for p in raw["output"]["message"]["content"] if "toolUse" in p)
                original = tool_input.get("classification", tool_input)   # strict-anyof envelope or flat object
                out[r["document_id"]] = {"is_relevant": True, "event_type": r.get("event_type") or "", "card_ids": r["card_ids"].split("|"), "certainty": int(r["certainty"]),
                                         "reach": int(r["reach"]), "original_certainty": original["certainty"], "original_reach": original["reach"],
                                         "confidence": float(r["llm_confidence"]), "notes": r["notes"], "effect_date": r["effect_date"],
                                         "flags": json.loads(r["validation_reasons"]), "evidence_quotes": json.loads(r["evidence_quotes"]),
                                         "review_basis": json.loads(r.get("review_basis") or "[]")}
    for name in ("irrelevant.jsonl", "failed.jsonl"):
        p = run_dir / name
        for line in (p.read_text().splitlines() if p.exists() else []):
            x = json.loads(line)
            if name == "irrelevant.jsonl":
                out[x["document_id"]] = {"is_relevant": False, "notes": x["classification"]["notes"], "flags": []}
            elif x["document_id"] not in out:
                out[x["document_id"]] = {"is_relevant": None, "notes": "", "flags": x.get("reasons") or [str(x.get("invocation_error"))]}
    return out


def evaluate(fixture: Path, run_dirs, candidates):
    with fixture.open(encoding="utf-8", newline="") as f:
        gold = list(csv.DictReader(f))
    run_dirs = [run_dirs] if isinstance(run_dirs, Path) else run_dirs
    candidates = [candidates] if isinstance(candidates, Path) else candidates
    res = {}
    for rd, cand in zip(run_dirs, candidates):     # several partial runs of one golden set
        res.update(outcomes(rd, cand))
    rows, m = [], {"expected_relevant": 0, "found_with_acceptable_card": 0, "found_other_card": 0,
                   "negatives": 0, "false_positives": 0, "borderline": []}
    for g in gold:
        r = res.get(g["document_id"], {"is_relevant": None, "notes": "not processed", "flags": []})
        quote_ok = None
        if r.get("is_relevant"):
            quote_ok = not any("not found verbatim" in f for f in r["flags"])
        ok_cards = set(filter(None, g["acceptable_card_ids"].split("|")))
        verdict = ""
        if g["expected"] == "relevant":
            m["expected_relevant"] += 1
            if r.get("is_relevant") and ok_cards & set(r["card_ids"]):
                m["found_with_acceptable_card"] += 1; verdict = "found (acceptable card)"
            elif r.get("is_relevant"):
                m["found_other_card"] += 1; verdict = "found, other card"
            else:
                verdict = "missed"
        elif g["expected"] == "irrelevant":
            m["negatives"] += 1
            if r.get("is_relevant"):
                m["false_positives"] += 1; verdict = "FALSE POSITIVE"
            else:
                verdict = "correct" if r.get("is_relevant") is False else "not processed"
        else:
            verdict = "borderline: " + ("marked relevant" if r.get("is_relevant") else "marked irrelevant")
            m["borderline"].append({"title": g["title"], "is_relevant": r.get("is_relevant"), "card_ids": r.get("card_ids"), "notes": r.get("notes")})
        rows.append({"title": g["title"], "outlet": g["outlet"], "expected": g["expected"] + (f" ({g['acceptable_card_ids'].replace('|', ' / ')})" if ok_cards else ""),
                     "verdict": verdict, **r, "quote_matched": quote_ok})
    return rows, m


def markdown(rows, m, summary):
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    lines = ["# Golden-set result: " + summary["run_id"], "",
             f"Prompt `{summary['prompt_version']}` (cache {'on' if summary.get('prompt_cache') else 'off'}), model `{summary['model_id']}`. "
             f"Items processed: {summary['articles_processed']}; status `{summary['status']}`.", "",
             "| # | Headline (outlet) | Expected | Result | is_relevant | event_type | card_ids | certainty (model→checked) | reach (model→checked) | confidence | notes | validate() / check flags | quote matched |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        cert = f"{r['original_certainty']}→{r['certainty']}" if r.get("is_relevant") else ""
        reach = f"{r['original_reach']}→{r['reach']}" if r.get("is_relevant") else ""
        lines.append(f"| {n} | {esc(r['title'])} ({esc(r['outlet'])}) | {esc(r['expected'])} | {esc(r['verdict'])} | {r.get('is_relevant')} | {r.get('event_type', '') or ''} | "
                     f"{', '.join(r.get('card_ids') or [])} | {cert} | {reach} | {r.get('confidence', '')} | {esc(r.get('notes', ''))} | "
                     f"{esc('; '.join(r.get('flags') or [])) or '—'} | {'' if r['quote_matched'] is None else ('yes' if r['quote_matched'] else 'no')} |")
    lines += ["", f"- Expected relevant found with an acceptable card: **{m['found_with_acceptable_card']} of {m['expected_relevant']}** "
                  f"(found with another card only: {m['found_other_card']}).",
              f"- Non-borderline negatives wrongly marked relevant: **{m['false_positives']} of {m['negatives']}**.",
              f"- Borderline: " + "; ".join(f"{b['title']} → is_relevant={b['is_relevant']}, cards={b['card_ids']}" for b in m["borderline"]),
              f"- Tokens: {summary['input_tokens']:,} input, {summary['output_tokens']:,} output, "
              f"{summary['cache_write_input_tokens']:,} cache write, {summary['cache_read_input_tokens']:,} cache read.",
              f"- Estimated cost: USD {summary['estimated_cost_usd']} with caching; USD {summary.get('estimated_cost_without_cache_usd', 'n/a')} "
              "if the same tokens had been billed without caching (cache rates: verify on the AWS Bedrock pricing page)."]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, action="append", required=True, help="repeatable; later runs fill items earlier runs did not process")
    p.add_argument("--candidates", type=Path, action="append", required=True, help="one per --run-dir, same order")
    p.add_argument("--report", type=Path, help="default: GOLDEN_REPORT.md in the first run dir")
    a = p.parse_args()
    rows, m = evaluate(a.fixture, a.run_dir, a.candidates)
    runs = [json.loads((d / "summary.json").read_text()) for d in a.run_dir]
    summary = dict(runs[0], run_id=" + ".join(r["run_id"] for r in runs), status=" + ".join(r["status"] for r in runs),
                   articles_processed=sum(r["articles_processed"] for r in runs))
    for k in ("input_tokens", "output_tokens", "cache_write_input_tokens", "cache_read_input_tokens"):
        summary[k] = sum(r[k] for r in runs)
    for k in ("estimated_cost_usd", "estimated_cost_without_cache_usd"):
        summary[k] = str(sum(Decimal(r.get(k) or "0") for r in runs))
    (a.report or a.run_dir[0] / "GOLDEN_REPORT.md").write_text(markdown(rows, m, summary), encoding="utf-8")
    print(json.dumps(m, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

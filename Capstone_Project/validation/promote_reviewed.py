"""Promote reviewed proposed events from a review sheet into the event register.

    python -m validation.promote_reviewed --sheet data/events/review/review_2026-11-02.csv [--register PATH] [--dry-run]

Rules:
- review_tier "required": inserted only with decision = approve or edit, and entered_by = the reviewer (who must be
  named). A "required" row with no decision stops the whole run before anything is written.
- review_tier "auto": inserted with entered_by = "llm-auto", review_status = "unreviewed" and needs_review = "Y",
  unless decision = reject. approve/edit on an auto row makes it a reviewed row like above.
- decision = reject: never inserted.
- edit: corrected_card_ids / corrected_certainty / corrected_reach / corrected_title / corrected_announced_date /
  corrected_effect_date / corrected_reach_basis / corrected_sources (JSON list of {url, outlet, source_tier}) replace the
  proposed values when filled. S for the sign-off list is recomputed from the corrected values.
- Event ids are never reused: numbering continues after the highest id in the register and in register_changelog.csv.
- A row with same_as_event_id updates an existing register event: it is listed for a manual merge, never inserted.
- review_tier "duplicate" (a recorded event with no new information) is never inserted; "date_review" needs a
  decision like "required".
- Amendment D: a review_tier "context" row is never inserted (its items live in context_news.csv); for other rows
  only scored_card_ids enter the register, never the cards on which the event is context.
- S >= 4 still needs a matching row in event_signoffs.csv, exactly as today: scoring's apply_signoff() clears the
  S >= 4 review flag only when a sign-off with the same event_id, certainty and reach and max_S >= S exists.
  The script prints which inserted events will need one.
- llm-auto rows are inserted only once SCORING_SPEC_v1.3.md has an approved Amendment C (unreviewed AI events kept
  off the main page and labelled "AI-classified, not reviewed").
- Idempotent: each register row records its proposal_id; proposals already present are skipped.
The register is rewritten atomically (temporary file, then replace). Never touches event_signoffs.csv.
"""
import argparse, csv, json, os, re, tempfile
from datetime import date
from pathlib import Path

from . import event_scoring as E
from .llm_classifier import PROJECT, PROMPT_V14, REGISTER, prompt_parts_v13

SPEC = PROJECT / "results/scoring/v1.3_indicator/SCORING_SPEC_v1.3.md"
DECISIONS = {"", "approve", "edit", "reject"}
EXTRA_COLUMNS = ["review_status", "proposal_id"]
TIER_ORDER = ["regulator", "dtcc", "official", "issuer_filing", "major_media", "other"]
REACH_BASES = {"market_wide", "business_line", "major_participant", "group", "single"}
CHANGELOG = PROJECT / "data/events/register_changelog.csv"


def corrected_sources(r: dict):
    raw = (r.get("corrected_sources") or "").strip()
    if not raw:
        return None
    value = json.loads(raw)
    if not isinstance(value, list) or not value or not all(isinstance(s, dict) and str(s.get("url", "")).startswith(("https://", "http://"))
                                                          and s.get("outlet") and s.get("source_tier") in TIER_ORDER for s in value):
        raise ValueError("corrected_sources must be a non-empty JSON list of {url, outlet, source_tier}")
    return value


class PromotionError(ValueError):
    pass


def amendment_c_approved(spec: Path = SPEC) -> bool:
    return bool(re.search(r"^## Amendment C[^\n]*\n\nApproved: ", spec.read_text(encoding="utf-8"), re.M)) if spec.exists() else False


def check_sheet(rows: list[dict], catalog: set[str]) -> None:
    problems = []
    for r in rows:
        pid, d = r["proposed_event_id"], (r.get("decision") or "").strip().lower()
        if d not in DECISIONS:
            problems.append(f"{pid}: decision '{r['decision']}' is not approve, edit or reject")
        if r["review_tier"] in ("required", "date_review") and not d:
            problems.append(f"{pid}: review_tier {r['review_tier']} needs a decision")
        if d in ("approve", "edit") and not (r.get("reviewer") or "").strip():
            problems.append(f"{pid}: decision {d} needs a reviewer")
        if d == "edit":
            cards = [c for c in (r.get("corrected_card_ids") or "").split("|") if c]
            if any(c not in catalog for c in cards):
                problems.append(f"{pid}: corrected_card_ids not in the catalog")
            for k in ("corrected_certainty", "corrected_reach"):
                if (r.get(k) or "").strip() not in ("", "0", "1", "2"):
                    problems.append(f"{pid}: {k} must be 0, 1 or 2")
            for k in ("corrected_announced_date", "corrected_effect_date"):
                if (r.get(k) or "").strip():
                    try:
                        date.fromisoformat(r[k].strip())
                    except ValueError:
                        problems.append(f"{pid}: {k} must be YYYY-MM-DD")
            if (r.get("corrected_reach_basis") or "").strip() not in {""} | REACH_BASES:
                problems.append(f"{pid}: corrected_reach_basis must be one of {sorted(REACH_BASES)}")
            try:
                corrected_sources(r)
            except (ValueError, TypeError) as e:
                problems.append(f"{pid}: {e}")
        if (r.get("route_context_card_ids") or "").strip() and d != "reject":
            problems.append(f"{pid}: route_context_card_ids only goes with decision reject")
    if problems:
        raise PromotionError("Review sheet not ready; nothing written:\n  " + "\n  ".join(problems))


def register_row(r: dict, event_id: str, today: str) -> dict:
    d = (r.get("decision") or "").strip().lower()
    reviewed = d in ("approve", "edit")
    edit = d == "edit"
    scored = [c for c in (r.get("scored_card_ids") or "").split("|") if c]
    cards = [c for c in (r.get("corrected_card_ids") or "").split("|") if c] if edit and r.get("corrected_card_ids") else (scored or r["card_ids"].split("|"))
    certainty = r["corrected_certainty"] if edit and (r.get("corrected_certainty") or "").strip() else r["certainty"]
    reach = r["corrected_reach"] if edit and (r.get("corrected_reach") or "").strip() else r["reach"]
    pick = lambda k: r["corrected_" + k].strip() if edit and (r.get("corrected_" + k) or "").strip() else r[k]
    fixed = corrected_sources(r) if edit else None
    sources = fixed if fixed else json.loads(r["sources"])
    note = f"Promoted from {r['proposed_event_id']} ({d or 'auto, not reviewed'}); candidates {r['candidate_ids']}."
    if (r.get("reviewer_notes") or "").strip():
        note += " Reviewer notes: " + r["reviewer_notes"].strip()
    return {"event_id": event_id, "chain_id": cards[0], "title": pick("title"), "announced_date": pick("announced_date"), "effect_date": pick("effect_date"),
            "certainty": certainty, "reach": reach, "evidence_quote": " || ".join(json.loads(r["evidence_quotes"])),
            "source_url": " ; ".join(s["url"] for s in sources), "entered_by": r["reviewer"].strip() if reviewed else "llm-auto",
            "needs_review": "N" if reviewed else "Y", "notes": note, "card_ids": "|".join(cards),
            "stage": r.get("stage", ""), "source_tier": min((s["source_tier"] for s in sources), key=TIER_ORDER.index),
            "outlet": "; ".join(dict.fromkeys(s["outlet"] for s in sources)), "llm_confidence": r["confidence"],
            "named_participants": r.get("named_participants", ""), "reach_basis": pick("reach_basis"), "updated_date": today,
            "prompt_version": r.get("prompt_version", ""), "model": r.get("model", ""), "article_file": "",
            "review_status": "reviewed" if reviewed else "unreviewed", "proposal_id": r["proposed_event_id"]}


def recomputed_s(row: dict, r: dict) -> int | None:
    """S of the register row as it will be scored in the sheet's week (rubric v1.2)."""
    week = re.match(r"PE-(\d{4}-\d{2}-\d{2})-", r["proposed_event_id"])
    if not week:
        return int(r["would_be_S"]) if str(r.get("would_be_S", "")).strip() else None
    ev = E.Event(event_id=row["event_id"], card_ids=row["card_ids"].split("|"), title=row["title"],
                 announced_date=date.fromisoformat(row["announced_date"]), effect_date=date.fromisoformat(row["effect_date"]),
                 certainty=int(row["certainty"]), reach=int(row["reach"]), evidence_quotes=[], sources=[])
    return E.event_score(ev, date.fromisoformat(week[1]))["S"]


def promote(sheet: Path, register: Path, dry_run: bool = False, today: str | None = None, spec: Path = SPEC,
            changelog: Path = CHANGELOG) -> dict:
    _, _, catalog, _ = prompt_parts_v13(PROMPT_V14, "v1.4")
    with sheet.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    check_sheet(rows, catalog)
    with register.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header, existing = list(reader.fieldnames), list(reader)
    header += [c for c in EXTRA_COLUMNS if c not in header]
    present = {r.get("proposal_id") for r in existing if r.get("proposal_id")}
    removed = []
    if changelog.exists():
        with changelog.open(encoding="utf-8", newline="") as f:
            removed = [r["event_id"] for r in csv.DictReader(f)]
    numbers = [int(m[1]) for e in [r["event_id"] for r in existing] + removed if (m := re.fullmatch(r"EV(\d+)", e))]
    next_no = max(numbers, default=0) + 1
    today = today or date.today().isoformat()
    result = {"inserted": [], "skipped_already_promoted": [], "rejected": [], "manual_merge": [], "context_not_promoted": [], "duplicate_not_promoted": [],
              "needs_signoff_for_S_ge_4": []}
    new = []
    for r in rows:
        d = (r.get("decision") or "").strip().lower()
        pid = r["proposed_event_id"]
        if pid in present:
            result["skipped_already_promoted"].append(pid); continue
        if d == "reject":
            result["rejected"].append(pid); continue
        if r.get("review_tier") == "context":
            result["context_not_promoted"].append(pid); continue
        if r.get("review_tier") == "duplicate":       # same_as event with no new information: related news only
            result["duplicate_not_promoted"].append(pid); continue
        if (r.get("same_as_event_id") or "").strip():
            result["manual_merge"].append({"proposal": pid, "existing_event": r["same_as_event_id"]}); continue
        if d not in ("approve", "edit") and not amendment_c_approved(spec):
            raise PromotionError(f"{pid}: llm-auto rows need an approved Amendment C in {spec.name}; nothing written")
        row = register_row(r, f"EV{next_no:04d}", today)
        next_no += 1
        new.append(row)
        result["inserted"].append({"event_id": row["event_id"], "proposal": pid, "entered_by": row["entered_by"], "review_status": row["review_status"]})
        s_now = recomputed_s(row, r)
        result["inserted"][-1]["S_in_week"] = s_now
        if s_now is not None and s_now >= 4:
            result["needs_signoff_for_S_ge_4"].append(row["event_id"])
    if new and not dry_run:
        fd, tmp = tempfile.mkstemp(dir=register.parent, prefix=".register.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            w.writeheader(); w.writerows(existing + new)
        os.replace(tmp, register)
    result["dry_run"] = dry_run
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sheet", type=Path, required=True)
    p.add_argument("--register", type=Path, default=REGISTER)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    try:
        print(json.dumps(promote(a.sheet, a.register, a.dry_run), indent=2))
    except PromotionError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()

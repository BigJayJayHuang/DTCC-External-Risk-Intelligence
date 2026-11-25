"""Build a local DAS edition of the project's existing Risk Horizon viewer."""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"
MONITOR = INPUTS / "monitor_evidence.json"
VIEWER = INPUTS / "viewer.html"
BASE = INPUTS / "risk_output.json"
OUTPUT = HERE / "DAS_Risk_Horizon.html"


def build_data():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    source = json.loads(MONITOR.read_text(encoding="utf-8"))
    summary = source["summary"]
    as_of = summary["as_of_date"]
    snapshot = f"das-public-{as_of}"
    urls = {row["source_id"]: row["url"] for row in source["sources"]}
    deadline = next(row for row in source["deadlines"] if row["deadline_id"] == "SEC-REPORT-2026-12-31")
    reviews = [r for r in source["findings"] if r["review_status"] == "APPLICABILITY_REVIEW_REQUIRED"]
    plans = [r for r in source["findings"] if r["review_status"] == "FUTURE_CHANGE_WATCHLIST"]
    if (len(reviews) != 2 or len(plans) != 1
            or deadline["submission_status"] != "NOT_PUBLICLY_OBSERVED"):
        raise ValueError("New source evidence requires content review")
    if "DAS" in data["lines"] or any(row["business_line"] == "DAS" for row in data["items"]):
        raise ValueError("DAS is already in the reference scoring data")

    def card(code, family, title, headline, mechanism, process, impact, action, state, evidence):
        return {
            "id": code.lower(), "card_id": code, "business_line": "DAS", "snapshot": snapshot,
            "region": "US", "risk_family": family, "title": f"{code} · {title}", "updated_at": as_of,
            "status": "monitoring_only", "review_status": state, "confidence": "Public evidence",
            "shock": None, "vulnerability": None, "severity": None, "show_on_main": False,
            "what_happened": headline,
            "transmission": {"event": headline, "mechanism": mechanism, "dtcc_process": process},
            "so_what": impact, "so_now_what": action,
            "sources": [{"name": name, "url": urls[key]} for name, key in evidence],
        }

    cards = [
        card("DAS-01", "Cyber", "Technology dependency watch",
             f"{len(reviews)} Besu publisher advisories captured in the reviewed evidence window.",
             "A publisher advisory warrants review when its affected dependency matches the DTS integration.",
             "DTS infrastructure continuity and tokenization workflow.",
             "DTCC identifies private Besu as a DTS integration. Public evidence leaves deployment applicability unresolved.",
             "Track publisher changes and official service notices. Review if DTS scope or incident evidence changes.",
             "Applicability pending", [
                 ("DTCC Tokenization Service launch", "launch"),
                 ("Besu publisher advisory A", "besu_qbft"), ("Besu publisher advisory B", "besu_ibft"),
             ]),
        card("DAS-04", "Regulatory", "Reporting calendar and network changes",
             f"Q4 2026 SEC staff reporting milestone: {deadline['deadline']}. DTCC plans Solana integration for H2 2027.",
             "Published requirements and network announcements determine which obligations and scope changes to track.",
             "DTS regulatory reporting and service eligibility.",
             "The reporting date is derived from the reviewed SEC staff terms. Submission status is unobserved. Solana is a planned integration.",
             "Track the reporting milestone and effective launch or eligibility notices. Confirm formal commencement before dating relief expiry.",
             "Scheduled and planned", [
                 ("SEC staff no-action letter", "sec_letter"), ("DTCC Solana announcement", "solana"),
                 ("DTCC Tokenization Service launch", "launch"),
             ]),
    ]
    data["items"].extend(cards)
    data["snapshots"].insert(0, {"id": snapshot, "date": as_of, "label": f"DAS public evidence · {as_of}"})
    data["lines"]["DAS"] = {"summary": {
        snapshot: f"Two public monitoring cards. Evidence window {summary['window_start']} to {as_of}. Formal severity unscored."
    }}
    data["das_public_snapshot"] = snapshot
    return data


def replace_one(body, old, new):
    if body.count(old) != 1:
        raise ValueError(f"Viewer template changed near {old[:75]}")
    return body.replace(old, new, 1)


def render(data):
    body = VIEWER.read_text(encoding="utf-8")
    body = re.sub(r'^<link rel="(?:preconnect|stylesheet)" href="https://fonts\.[^\n]+\n', "", body, flags=re.M)
    edits = [
        ("<title>Risk Horizon</title>", "<title>Risk Horizon | DAS public monitoring</title>"),
        ('const PARAMS=new URLSearchParams(location.search);\nconst DATA_URL=PARAMS.get("data")||"data/risk_output.json";',
         "const OFFLINE_DATA=JSON.parse(document.getElementById('offline-data').textContent);"),
        ('const LINE_KEYS=Object.keys(LINE_META);', 'const LINE_KEYS=["DAS","FICC","ECS"];'),
        ('const state={line:"FICC"', 'const state={line:"DAS"'),
        ('try{const s=localStorage.getItem("rh-line"); if(s&&LINE_META[s]) state.line=s;}catch(e){}\n', ''),
        ('try{localStorage.setItem("rh-line",state.line)}catch(e){};', ''),
        ('data_incomplete:"Incomplete"};', 'data_incomplete:"Incomplete",monitoring_only:"Monitoring"};'),
        ('Incomplete:"Data incomplete"};', 'Incomplete:"Data incomplete",Monitoring:"Public watch"};'),
        ('High:0,Medium:0,Low:0,Pending:0,Unscanned:0,Incomplete:0',
         'High:0,Medium:0,Low:0,Pending:0,Unscanned:0,Incomplete:0,Monitoring:0'),
        ('function sevBox(i){', 'function sevBox(i){\n'
         '  if(i.status==="monitoring_only") return \'<span class="sev Pending"><span class="l">PUBLIC WATCH</span></span>\';'),
        ('function scoreChip(i){return', 'function scoreChip(i){'
         'if(i.status==="monitoring_only") return \'<span class="chip o">\'+esc(i.review)+\'</span>\';return'),
        ('How the score was built</h3>', '${i.status==="monitoring_only"?"Evidence and score status":"How the score was built"}</h3>'),
        ('<span class="eq">${i.score!=null?',
         '<span class="eq">${i.status==="monitoring_only"?"Formal severity unscored":i.score!=null?'),
        ('Prototype – indicator-based scores and hand-entered events only; news is not yet scanned.',
         '${state.line==="DAS"?"DAS public evidence snapshot":"Historical indicator and manual-event scoring"}'),
        ('    <span class="saved">✓ Opens on ${esc(L)} next time</span>\n', ''),
        ('<span class="ct" aria-label="${counts[k]} items">${counts[k]}</span>',
         '${k===L?\'<span class="ct">\'+counts[k]+\'</span>\':""}'),
        ('SNAPS.map((s,n)=>', 'SNAPS.filter(s=>ALL().some(i=>i.line===state.line&&i.snapshot===s.id)).map((s,n)=>'),
        ('  const i=it, ai=', '  state.snap=it.snapshot;\n  const i=it, ai='),
        ('function footer(){\n', 'function footer(){\n'
         '  if(state.line==="DAS") return \'<footer class="method">Public evidence review. '
         'Formal severity is unscored for these cards.</footer>\';\n'),
        ('${esc(L)} — the few things that matter ${state.range==="week"?"this week":"in this period"}',
         '${esc(L)} ${L==="DAS"?"public risk monitoring":"risk brief"}'),
        ('if(L&&L!==state.line){state.line=L;try{localStorage.setItem("rh-line",L)}catch(e){}}',
         'if(L){state.line=L; if(!ALL().some(i=>i.line===L&&i.snapshot===state.snap)) {\n'
         '    const available=SNAPS.find(s=>ALL().some(i=>i.line===L&&i.snapshot===s.id));\n'
         '    if(available && (state.snap===DATA.das_public_snapshot || L==="DAS")) state.snap=available.id;\n  }}'),
        ('  route();};}', '  renderList();};}'),
    ]
    for old, new in edits:
        body = replace_one(body, old, new)
    body = body.replace('["Pending","Unscanned","Incomplete"].filter(k=>c[k])',
                        '["Pending","Unscanned","Incomplete","Monitoring"].filter(k=>c[k])')
    # A monitoring page has a count by evidence state. The ranked severity
    # counts are retained for the original scoring snapshots.
    start = body.index('    <div class="sumrow">')
    end = body.index('    </div>', start) + len('    </div>')
    original = body[start:end]
    body = (body[:start] + '${L==="DAS"?' + chr(96)
            + '<div class="sumrow"><span class="cnt">${c.Monitoring} public watch cards</span></div>'
            + chr(96) + ':' + chr(96) + original + chr(96) + '}' + body[end:])
    first = body.index("  try{\n    const r=await fetch(DATA_URL")
    last = body.index("  SNAPS=asArr(DATA.snapshots)", first)
    body = body[:first] + "  DATA=OFFLINE_DATA;\n" + body[last:]
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return replace_one(body, "<script>\n", f'<script type="application/json" id="offline-data">{payload}</script>\n<script>\n')


def main():
    data = build_data()
    base_items = json.loads(BASE.read_text(encoding="utf-8"))["items"]
    assert [r for r in data["items"] if r["business_line"] != "DAS"] == base_items
    cards = [r for r in data["items"] if r["business_line"] == "DAS"]
    assert [r["card_id"] for r in cards] == ["DAS-01", "DAS-04"]
    assert all(r["shock"] is r["vulnerability"] is r["severity"] is None for r in cards)
    OUTPUT.write_text(render(data), encoding="utf-8")
    (HERE / "das_cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "data_receipt.json").write_text(json.dumps({
        "public_evidence_as_of": data["snapshots"][0]["date"],
        "included_das_cards": [r["card_id"] for r in cards],
        "historical_reference_records": len(base_items),
        "historical_reference_records_preserved": True,
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (VIEWER, BASE, MONITOR, OUTPUT)},
    }, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()

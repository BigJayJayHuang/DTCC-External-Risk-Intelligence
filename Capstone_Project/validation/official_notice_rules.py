"""Amendment G (SCORING_SPEC_v1.3.md): rules for official notices, applied to title + summary, ignoring case.

    rule(text) -> ("override" | "skip" | "membership" | None, detail, card_id or None)
    sro_filer(title) -> filer name of a Federal Register SRO rule filing, or None

G1 override (stress terms) wins over G2 skip and G3 membership. G4 (SRO filings capped at auto) is applied in
review_sheet.py, after the classifier.
"""
import re

LABEL_MEMBERSHIP = "membership/onboarding"
OVERRIDE = re.compile(r"\b(cease[sd]? to act|watch[- ]?list|restrict(?:ion|ions|ed)?|suspen(?:sion|sions|ded|d)|"
                      r"default(?:s|ed)?|wind[- ]?down|margin|clearing fund|liquidity)\b", re.I)
SKIP = [("DTCC additional account activation or retirement", re.compile(r"\badditional account (activation|retirement)\b", re.I)),
        ("fee or depositary-fee notification", re.compile(r"\b(depositary[- ])?fees? notification\b", re.I)),
        ("tax-relief notice", re.compile(r"\btax relief\b", re.I)),
        ("routine corporate-action notice", re.compile(r"\bcorporate[- ]actions?\b|\bCA Web\b", re.I))]
NEW_MEMBER = re.compile(r"\bnew (participant in the netting system|agent clearing member|sponsoring member|sponsored member|"
                        r"(?:(?:NSCC|GSD|MBSD|FICC) )?(?:full[- ]service |clearing |netting )?member)\b", re.I)
FICC = re.compile(r"\b(government securities division|mortgage[- ]backed securities division|GSD|MBSD|FICC|fixed income clearing)\b", re.I)
NSCC = re.compile(r"\b(NSCC|national securities clearing)\b", re.I)
SRO = re.compile(r"^\s*Self-Regulatory Organizations\s*[;:]\s*([^;]+?)\s*;", re.I)
DTCC_FILERS = re.compile(r"\b(fixed income clearing corporation|national securities clearing corporation|depository trust company)\b", re.I)


def rule(text: str) -> tuple[str | None, str, str | None]:
    if OVERRIDE.search(text):
        return "override", "G1: stress term " + repr(OVERRIDE.search(text).group(0)), None
    for name, pattern in SKIP:
        if pattern.search(text):
            return "skip", "Amendment G2: " + name, None
    m = NEW_MEMBER.search(text)
    if m:
        if FICC.search(text):
            return "membership", "Amendment G3: " + m.group(0), "FICC-GSD-03"
        if NSCC.search(text):
            return "membership", "Amendment G3: " + m.group(0), "ECS-NSCC-LIQ"
    return None, "", None


def sro_filer(title: str) -> str | None:
    m = SRO.match(title or "")
    return m.group(1).strip() if m else None


def capped_sro_filing(title: str) -> bool:
    """G4: an SRO rule filing whose filer is not FICC, NSCC or DTC."""
    filer = sro_filer(title)
    return bool(filer) and not DTCC_FILERS.search(filer)


def display_title(row: dict) -> str:
    """DTCC notice titles are notice numbers; the first sentence of the summary names the member."""
    summary = (row.get("summary") or "").strip()
    head = re.split(r"\s+Notice:\s", summary, maxsplit=1)[0].strip() if summary else ""
    return head or row.get("title", "")

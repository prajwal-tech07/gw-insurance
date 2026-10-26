"""Read an insurer's rejection / settlement letter and judge each reason it gives.

Verdicts: valid, questionable, likely_wrong, not_sure. Each one cites the rule it
rests on. This is guidance to help write a complaint, not legal advice.
"""

import re
from datetime import date

from app.analyzer.reasons import REASON_LABELS, REASONS
from app.engine.calculator import rupees
from app.engine.dates import add_months, months_between
from app.models import AnalysisResult, AnalyzeInput, Finding
from app.precedents.store import search
from app.rules import rule_for

AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s*(\d[\d,]*(?:\.\d{1,2})?)", re.I)
CLAUSE = re.compile(r"\b(?:clause|section|condition|exclusion|code)\s*(?:no\.?\s*)?[-:]?\s*[\dIVX]+(?:\.\d+)*|code[- ]?excl\s*\d+"
                    r"|\b\d{1,2}\.\d{1,2}(?:\.\d{1,2})?\b(?!\s*%)", re.I)
EXEMPT_FROM_PROPORTIONATE = re.compile(r"pharmacy|medicine|drug|implant|device|stent|investigation|diagnostic|lab\b|test|icu|intensive care", re.I)
SPECIFIC_FIRST = ("pre_existing_non_disclosure", "waiting_period", "not_requiring_hospitalisation")
DOCS_RULE_START = date(2024, 5, 29)


def sentences(text: str) -> list[str]:
    text = re.sub(r"\b(rs|no|dr|mr|mrs|ms)\.", r"\1", text, flags=re.I)
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def detect_reasons(text: str) -> dict[str, str]:
    """reason code -> the sentence that shows it."""
    found: dict[str, str] = {}
    for sentence in sentences(text):
        for code, (_, pattern) in REASONS.items():
            if code not in found and pattern.search(sentence):
                found[code] = sentence
    if "exclusion" in found and any(c in found for c in SPECIFIC_FIRST):
        found.pop("exclusion")  # "excluded as pre-existing" is about the specific reason
    return found


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def _judge(code: str, evidence: str, inp: AnalyzeInput) -> Finding:
    label = REASON_LABELS[code]
    terms = inp.terms
    on = inp.admission_date or date.today()
    start = terms.first_inception_date if terms else None
    months = months_between(start, on) if start else None

    def f(verdict: str, explanation: str, what_to_do: str, rule_ids: list[str] | None = None) -> Finding:
        return Finding(reason_code=code, reason_label=label, evidence=evidence, verdict=verdict,
                       explanation=explanation, what_to_do=what_to_do, rule_ids=rule_ids or [])

    if code == "pre_existing_non_disclosure":
        mora = rule_for("moratorium", on)
        if months is not None and mora and mora.months and months >= mora.months and "fraud" not in evidence.lower():
            return f("likely_wrong",
                     f"You have {months} months of continuous cover (since {_fmt(start)}). After {mora.months} months, "
                     "IRDAI's moratorium rule says a claim cannot be contested for non-disclosure or misrepresentation, "
                     "except proven fraud.",
                     "Quote the moratorium rule and attach proof of continuous cover (old policies, renewal or portability letters).",
                     [mora.id])
        extra = ""
        if terms and start and terms.waiting.pre_existing_months:
            done = add_months(start, terms.waiting.pre_existing_months)
            if on >= done:
                extra = (f" Your pre-existing disease waiting period ended on {_fmt(done)}, so a declared "
                         "pre-existing condition would now be covered.")
        return f("questionable",
                 "The insurer must prove, with medical records, that the condition was diagnosed before the policy began "
                 "and was knowingly hidden. Consumer courts often reject non-disclosure rejections based only on "
                 "suspicion or a 'known case of' line in a discharge summary." + extra,
                 "Ask the insurer for the records it relies on and a copy of your proposal form. Get your doctor to "
                 "certify when the condition was first diagnosed.",
                 ["CRC-01"])

    if code == "waiting_period":
        mentioned = re.search(r"(\d{2})\s*months", evidence)
        if months is not None:
            period = int(mentioned.group(1)) if mentioned else None
            if period is None and terms:
                periods = [p for p in (terms.waiting.specific_disease_months, terms.waiting.pre_existing_months) if p]
                period = max(periods) if periods else None
            if period:
                if months >= period:
                    return f("likely_wrong",
                             f"Your cover has run for {months} months since {_fmt(start)}, longer than the {period}-month "
                             "waiting period.",
                             "Point out the date your continuous cover began, with proof of renewals/portability.")
                return f("valid",
                         f"Your cover has run for {months} months, so the {period}-month waiting period had not ended "
                         f"(it ends on {_fmt(add_months(start, period))}).",
                         "Check whether earlier policies you ported from should count towards the waiting period.")
        return f("not_sure",
                 "Waiting periods count from the first policy, and continue across renewals and portability.",
                 "Add your policy's start date (Policies tab) to check this, and include any earlier ported policy.")

    if code == "not_requiring_hospitalisation":
        return f("questionable",
                 "Several consumer courts have overturned rejections made only because the stay was under 24 hours or "
                 "could have been 'OPD', because modern treatment often needs shorter stays. Day-care procedures are "
                 "covered without a 24-hour stay.",
                 "Get a letter from the treating doctor explaining why admission was medically necessary. Check the "
                 "day-care list in your policy.")

    if code == "proportionate_deduction":
        if terms and terms.room_rent_waiver:
            return f("likely_wrong", "Your policy has a room-rent waiver, so no proportionate cut should apply.",
                     "Point to the room-rent waiver in your policy schedule.")
        if terms and terms.room_rent.kind == "none":
            return f("likely_wrong", "Your policy has no room-rent limit, so no proportionate cut should apply.",
                     "Point to the room-rent clause in your policy.")
        if inp.hospital_differential_billing is False:
            return f("likely_wrong",
                     "IRDAI says insurers must not apply proportionate cuts where the hospital does not charge "
                     "differently by room category.",
                     "Get a letter from the hospital saying its charges do not depend on the room category.",
                     ["PROP-03"])
        if EXEMPT_FROM_PROPORTIONATE.search(evidence):
            return f("likely_wrong",
                     "The cut seems to include medicines, implants, tests or ICU charges. Under IRDAI's norms the "
                     "proportionate cut applies only to associate expenses such as nursing, doctor and OT charges, "
                     "never to pharmacy, implants, diagnostics or ICU.",
                     "Ask for the line-by-line calculation and a refund of the cut on medicines, implants, tests and ICU.",
                     ["PROP-01", "PROP-02"])
        return f("valid",
                 "A proportionate cut on nursing, doctor and OT charges is allowed when the room was above your limit.",
                 "Check the amount with the Bill Check tab, which applies the IRDAI limits.", ["PROP-01"])

    if code == "non_payable":
        if terms and terms.consumables_cover:
            return f("likely_wrong", "You have a consumables add-on, which normally covers List I items.",
                     "Point to the consumables cover in your policy schedule.", ["LIST-01"])
        return f("valid",
                 "Insurers may refuse IRDAI List I items unless you have a consumables add-on. List II-IV items "
                 "should not be billed separately by the hospital at all.",
                 "Check each item in Bill Check. For List II-IV items, ask the hospital to refund or absorb them.",
                 ["LIST-01"])

    if code == "sub_limit":
        if terms is not None and not terms.sub_limits:
            return f("questionable", "Your saved policy terms show no sub-limit for this treatment.",
                     "Ask the insurer to name the clause that sets this sub-limit.")
        names = ", ".join(s.name for s in terms.sub_limits) if terms else ""
        return f("valid" if names else "not_sure",
                 f"Your policy has sub-limits ({names})." if names else "Check whether your policy sets a sub-limit for this treatment.",
                 "Check that the capped amount matches the clause.")

    if code == "reasonable_customary":
        return f("questionable",
                 "IRDAI has not precisely defined 'reasonable and customary'. Insurers often use it to cut doctor or "
                 "hospital fees without showing their basis.",
                 "Ask the insurer in writing for the data it used (charges at comparable hospitals in your city).")

    if code == "documents":
        if on >= DOCS_RULE_START:
            return f("likely_wrong",
                     "IRDAI's rules say no claim shall be rejected or closed for want of documents; insurers and TPAs "
                     "should collect documents from the hospital.",
                     "Reply listing the documents already given, and ask the insurer to collect anything else from the hospital.",
                     ["DOCS-01"])
        return f("questionable", "Insurers cannot keep asking for documents already supplied or not reasonably obtainable.",
                 "Reply listing the documents already given.")

    if code == "late_intimation":
        ids = ["DELAY-01"] + (["DOCS-01"] if on >= DOCS_RULE_START else [])
        return f("likely_wrong" if on >= DOCS_RULE_START else "questionable",
                 "IRDAI has told insurers not to reject genuine claims only because they were intimated or submitted late.",
                 "Explain the reason for the delay and ask for the claim to be decided on merit.", ids)

    if code == "policy_cancellation":
        return f("questionable",
                 "A consumer court (NCDRC, 2025) held an insurer's unilateral policy cancellation and claim refusal unjustified.",
                 "Ask for the legal ground for the cancellation and the notice that was sent.")

    if code == "fraud":
        return f("not_sure", "Fraud is a serious allegation that the insurer must prove.",
                 "Get legal advice before replying, and do not sign anything you do not agree with.")

    return f("not_sure",
             "The insurer must name the exact exclusion clause it relies on.",
             "Ask for the clause and check whether your treatment really falls under it.", ["CRC-01"])


def analyze(inp: AnalyzeInput) -> AnalysisResult:
    text = inp.letter_text
    reasons = detect_reasons(text)
    findings = [_judge(code, evidence, inp) for code, evidence in reasons.items()]

    clause_cited = bool(CLAUSE.search(text))
    if not clause_cited:
        findings.append(Finding(
            reason_code="no_clause", reason_label="No policy clause cited", evidence="",
            verdict="questionable",
            explanation="The letter does not cite a specific policy clause. IRDAI requires rejections to state the "
                        "specific policy terms relied on, approved by the Claims Review Committee.",
            what_to_do="Ask for the clause and the Claims Review Committee approval in writing.", rule_ids=["CRC-01"]))
    if not reasons:
        findings.insert(0, Finding(
            reason_code="unknown", reason_label="Reason not recognised", evidence="", verdict="not_sure",
            explanation="Could not identify the reason for the rejection or deduction.",
            what_to_do="Ask the insurer to state the reason and the policy clause in writing."))

    amounts = [float(m.group(1).replace(",", "")) for m in AMOUNT.finditer(text)]
    verdicts = {f.verdict for f in findings}
    if "likely_wrong" in verdicts:
        strength = "strong"
    elif "questionable" in verdicts:
        strength = "moderate"
    elif verdicts == {"valid"}:
        strength = "weak"
    else:
        strength = "unclear"

    disputed = None
    if inp.claimed_amount is not None and inp.settled_amount is not None:
        disputed = max(0.0, inp.claimed_amount - inp.settled_amount)
    challengeable = sum(f.verdict in ("likely_wrong", "questionable") for f in findings)
    summary = f"{challengeable} of {len(findings)} point(s) can be challenged."
    if disputed:
        summary += f" Amount in dispute: {rupees(disputed)}."

    query = text + " " + " ".join(REASON_LABELS[c] for c in reasons)
    precedents = search(query, list(reasons))
    return AnalysisResult(findings=findings, amounts_found=amounts, clause_cited=clause_cited,
                          case_strength=strength, summary=summary, precedents=precedents)

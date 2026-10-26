"""Draft the three complaint texts from the analysis findings.

Templates fill every fact; the optional AI step only rewrites wording and is
checked so that no number or reference is lost.
"""

import re
from datetime import date
from typing import Any

from app.ai import complete_text
from app.engine.calculator import rupees
from app.models import DraftInput, DraftResult, Finding
from app.rules import get_rule, rule_for

CHALLENGE = ("likely_wrong", "questionable")


def _d(value: date | None, fallback: str = "[date]") -> str:
    return value.strftime("%d %b %Y") if value else fallback


def _refs(f: Finding) -> str:
    """'Rule title (source document, year)': the form to cite in a letter. Full details are on the Rules page."""
    refs = []
    for rule_id in f.rule_ids:
        rule = get_rule(rule_id)
        year = f", {rule.effective_from.year}" if rule.effective_from else ""
        refs.append(f"{rule.title} ({rule.source.name}{year})")
    return "; ".join(refs)


def _grounds(findings: list[Finding]) -> list[str]:
    lines = []
    for f in findings:
        if f.verdict not in CHALLENGE:
            continue
        line = f"{f.reason_label}: {f.explanation}"
        if f.rule_ids:
            line += f" Basis: {_refs(f)}."
        lines.append(line)
    return lines


def _outcome(inp: DraftInput) -> str:
    if inp.paid_amount > 0:
        return f"you settled only {rupees(inp.paid_amount)} on {_d(inp.rejection_date)}"
    return f"you rejected the claim on {_d(inp.rejection_date)}"


def insurer_letter(inp: DraftInput, today: date) -> str:
    disputed = max(0.0, inp.claimed_amount - inp.paid_amount)
    grounds = _grounds(inp.findings) or [
        "The decision is not supported by the policy terms. Please state the specific clause and evidence relied on."]
    patient = inp.patient_name or inp.complainant_name
    lines = [
        "To,",
        "The Grievance Redressal Officer,",
        inp.insurer,
        "",
        f"Date: {_d(today)}",
        "",
        f"Subject: Grievance against the decision on claim no. {inp.claim_number or '[claim no.]'} under policy no. {inp.policy_number}",
        "",
        "Dear Sir/Madam,",
        "",
        (f"I, {inp.complainant_name}, hold the above policy. {patient} was admitted to {inp.hospital or '[hospital]'} on "
         f"{_d(inp.admission_date)}. A claim of {rupees(inp.claimed_amount)} was made, and {_outcome(inp)}."),
        "",
        "I dispute this decision for the following reasons:",
    ]
    lines += [f"{i}. {g}" for i, g in enumerate(grounds, 1)]
    if inp.extra_facts.strip():
        lines += ["", inp.extra_facts.strip()]
    lines += [
        "",
        "I request you to:",
        f"- re-examine the claim and pay the balance of {rupees(disputed)}, with interest as per IRDAI regulations;",
        "- if you maintain your decision, give me in writing the specific policy clause relied on, the medical or other "
        "evidence used, and the approval of your Claims Review Committee.",
        "",
        "Please resolve this grievance within 14 days, as required by IRDAI. Otherwise I will escalate it to IRDAI "
        "(Bima Bharosa) and the Insurance Ombudsman.",
        "",
        "Yours faithfully,",
        inp.complainant_name,
    ]
    lines += [x for x in (inp.address, inp.phone, inp.email) if x.strip()]
    lines += ["", "Enclosures: claim form, rejection/settlement letter, hospital bills, discharge summary, doctor's certificate."]
    return "\n".join(lines)


def bima_bharosa_text(inp: DraftInput) -> str:
    disputed = max(0.0, inp.claimed_amount - inp.paid_amount)
    grounds = [f.reason_label for f in inp.findings if f.verdict in CHALLENGE]
    ref = f" (grievance ref. {inp.grievance_reference})" if inp.grievance_reference else ""
    return (
        f"Insurer: {inp.insurer}. Policy no. {inp.policy_number}. Claim no. {inp.claim_number or '[claim no.]'}. "
        f"Claim of {rupees(inp.claimed_amount)} for hospitalisation on {_d(inp.admission_date)}; {_outcome(inp)}. "
        f"I complained to the insurer{ref} and it was not resolved within 14 days / I am not satisfied with the reply. "
        f"Grounds: {'; '.join(grounds) if grounds else 'decision not supported by the policy terms'}. "
        f"Relief sought: payment of {rupees(disputed)} with interest."
    )


def ombudsman_text(inp: DraftInput, today: date) -> str:
    disputed = max(0.0, inp.claimed_amount - inp.paid_amount)
    grounds = _grounds(inp.findings) or ["The decision is not supported by the policy terms."]
    cap = rule_for("ombudsman_cap", today)
    lines = [
        "COMPLAINT TO THE INSURANCE OMBUDSMAN (Rule 14, Insurance Ombudsman Rules, 2017)",
        "",
        f"1. Complainant: {inp.complainant_name}" + (f", {inp.address}" if inp.address else ""),
        f"   Contact: {', '.join(x for x in (inp.phone, inp.email) if x) or '[phone / email]'}",
        f"2. Insurer (branch/office): {inp.insurer}",
        f"3. Policy no.: {inp.policy_number}   Claim no.: {inp.claim_number or '[claim no.]'}",
        f"4. Facts: {inp.patient_name or inp.complainant_name} was hospitalised at {inp.hospital or '[hospital]'} on "
        f"{_d(inp.admission_date)}. A claim of {rupees(inp.claimed_amount)} was made and {_outcome(inp).replace('you ', 'the insurer ')}.",
        "5. Grounds of complaint:",
    ]
    lines += [f"   {i}. {g}" for i, g in enumerate(grounds, 1)]
    lines += [
        f"6. Loss suffered: {rupees(disputed)} (plus interest).",
        f"7. Relief sought: direct the insurer to pay {rupees(disputed)} with interest.",
        "8. Declarations:",
        f"   (a) I made a written representation to the insurer on {_d(inp.grievance_filed_on, '[date of your complaint]')}"
        f"{' (ref. ' + inp.grievance_reference + ')' if inp.grievance_reference else ''}, which was rejected / not "
        "answered within one month / answered unsatisfactorily.",
        "   (b) This complaint is made within one year of the insurer's reply (or of the one-month period ending).",
        "   (c) The same matter is not pending before, or decided by, any court, consumer forum or arbitrator.",
        "",
        "Attach: policy copy, claim documents, rejection/settlement letter, your complaint to the insurer and its reply.",
        "File online on the Council for Insurance Ombudsmen website (cioins.co.in) or at the Ombudsman office for your area.",
    ]
    if cap and cap.amount and disputed > cap.amount:
        lines.append(f"Note: the Ombudsman can award at most {rupees(cap.amount)}. For a larger claim, consider the consumer commission.")
    return "\n".join(lines)


NUMBERS = re.compile(r"\d[\d,]*")


def polish(letter: str, client: Any = None) -> tuple[str | None, str | None]:
    """AI rewrite for tone; rejected if any number or reference from the template is missing."""
    text, error = complete_text(
        "You improve the clarity and tone of complaint letters written by Indian health insurance policyholders. "
        "Keep every fact, amount, date, policy/claim number and rule reference exactly as written. "
        "Do not add facts, legal claims or threats. Return only the letter.",
        letter, client)
    if not text:
        return None, error
    missing = set(NUMBERS.findall(letter)) - set(NUMBERS.findall(text))
    if missing:
        return None, "the rewrite changed some numbers, so the original wording was kept"
    return text, None


def draft(inp: DraftInput, today: date | None = None, client: Any = None) -> DraftResult:
    today = today or date.today()
    letter = insurer_letter(inp, today)
    notes = ["Check every detail before sending. This is a draft to help you, not legal advice."]
    polished = False
    if inp.polish_with_ai:
        better, error = polish(letter, client)
        if better:
            letter, polished = better, True
        else:
            notes.append(f"AI polishing was not applied ({error}).")
    return DraftResult(
        insurer_letter=letter,
        bima_bharosa_text=bima_bharosa_text(inp),
        ombudsman_text=ombudsman_text(inp, today),
        amount_disputed=max(0.0, inp.claimed_amount - inp.paid_amount),
        polished_by_ai=polished,
        notes=notes,
    )

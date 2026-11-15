"""Death claim helper: what the family must send, whether the insurer can question the policy,
when it must pay, other money the family may be owed, and the letters to send.

Life insurers: Section 45 (3-year rule) and IRDAI's 15/45-day settlement timeline apply.
For accident or health policies the insurer's own claim timeline applies, so we say so.
"""

import json
from datetime import date, timedelta
from functools import lru_cache

from app.config import DATA_DIR
from app.engine.calculator import rupees
from app.engine.dates import add_months, add_years
from app.models import DeathClaimInput, DeathClaimResult, Note, OtherCover
from app.rules import rule_for

LIFE_KINDS = ("term_life", "life_savings")
NO_INVESTIGATION_DAYS = 15
INVESTIGATION_DAYS = 45


def _fmt(d: date | None, fallback: str = "[date]") -> str:
    return d.strftime("%d %b %Y") if d else fallback


def _ids(group: str, on: date) -> list[str]:
    rule = rule_for(group, on)
    return [rule.id] if rule else []


@lru_cache(maxsize=1)
def _other_cover() -> tuple[dict, ...]:
    return tuple(json.loads((DATA_DIR / "other_cover.json").read_text(encoding="utf-8"))["items"])


def other_money(cause: str) -> list[OtherCover]:
    return [OtherCover(name=i["name"], what=i["what"], how=i["how"], source_url=i["source_url"], status=i["status"])
            for i in _other_cover() if i["applies"] == "any" or (i["applies"] == "accident" and cause == "accident")]


def policy_date(inp: DeathClaimInput) -> date | None:
    """Section 45 counts from the later of the policy start (issue / risk) and the revival date."""
    dates = [d for d in (inp.policy_start, inp.revival_date) if d]
    return max(dates) if dates else None


def contest_status(inp: DeathClaimInput) -> tuple[str, str, date | None, list[str]]:
    on = inp.date_of_death
    ids = _ids("life_incontestable", on)
    if inp.kind not in LIFE_KINDS:
        return ("not_applicable", "The 3-year rule (Section 45) is for life insurance. For this policy, the insurer "
                "must still give its reasons in writing if it rejects the claim.", None, [])
    start = policy_date(inp)
    if start is None:
        return ("unknown", "Add the policy start date (and the revival date, if the policy was ever revived) to check "
                "whether the insurer can still question the policy.", None, ids)
    three = add_years(start, 3)
    since = "revival" if inp.revival_date and inp.revival_date == start else "start"
    if on >= three:
        return ("no", f"The death was more than 3 years after the policy {since} ({_fmt(start)}). The insurer cannot "
                "question the policy on any ground, including wrong or missing facts in the proposal form.", three, ids)
    return ("limited", f"The death was within 3 years of the policy {since} ({_fmt(start)}; 3 years end on "
            f"{_fmt(three)}). The insurer can question the claim only for fraud or for a wrong or hidden material "
            "fact in the proposal form, must have legally tenable evidence, and must give its reasons in writing. "
            "Early claims like this are often investigated, so keep medical records ready.",
            three, ids + _ids("life_claim_process", on))


def documents(inp: DeathClaimInput) -> list[str]:
    docs = [
        "Claim form (from the insurer's website or branch), signed by the claimant",
        "Death certificate issued by the municipal corporation, panchayat or registrar",
        "Original policy document (if lost, ask the insurer for its process; it usually wants an indemnity bond)",
        "Claimant's ID and address proof (KYC) and a photo",
        "Claimant's bank details: cancelled cheque or the first page of the passbook",
    ]
    if inp.place_of_death == "hospital":
        docs.append("Hospital discharge or death summary and the treatment records")
    elif inp.cause in ("illness", "unknown"):
        docs.append("Medical records of the last illness and a doctor's certificate of the cause of death (insurers often ask for these)")
    if inp.cause in ("accident", "suicide"):
        docs += ["First Information Report (FIR) from the police",
                 "Post-mortem report",
                 "Police inquest / panchnama and the final police report (usually asked for)"]
    if inp.claimant_is_nominee is not True:
        docs.append("If the claimant is not the nominee (or there is no nominee): proof of being a legal heir, such as a "
                    "legal heir certificate or succession certificate, as the insurer asks")
    if inp.assigned_to_lender:
        docs.append("Loan account statement showing the amount outstanding on the date of death")
    return docs


def deadline(inp: DeathClaimInput, today: date) -> tuple[date | None, int | None, str, list[Note]]:
    notes: list[Note] = []
    life = inp.kind in LIFE_KINDS
    tat = _ids("death_claim_timeline", inp.date_of_death)
    claim_process = _ids("life_claim_process", inp.date_of_death)
    if inp.intimated_on is None:
        if life:
            return None, None, ("Intimate the claim now, online, at a branch or through the call centre. The insurer must "
                                f"settle within {NO_INVESTIGATION_DAYS} days of intimation ({INVESTIGATION_DAYS} days if it "
                                "investigates), so the clock starts when you tell it."), [
                Note(level="info", rule_ids=claim_process, text=(
                    "A claim cannot be rejected or closed only because it was intimated late or a document is missing."))]
        return None, None, "Intimate the claim to the insurer now and ask it, in writing, for its claim timeline.", notes
    if not life:
        return None, None, ("IRDAI's 15/45-day death claim timeline is for life insurance. Ask this insurer in writing for "
                            "its decision date, and complain if it does not reply."), notes
    days = INVESTIGATION_DAYS if inp.under_investigation else NO_INVESTIGATION_DAYS
    due = inp.intimated_on + timedelta(days=days)
    left = (due - today).days
    kind = "with an investigation" if inp.under_investigation else "without an investigation"
    if left >= 0:
        note = (f"The insurer must settle by {_fmt(due)} ({days} days from intimation on {_fmt(inp.intimated_on)}, {kind}). "
                f"{'That is today.' if left == 0 else f'{left} days left.'}")
    else:
        note = (f"The insurer is {-left} days late: it had to settle by {_fmt(due)} ({days} days from intimation on "
                f"{_fmt(inp.intimated_on)}). It now owes interest at the bank rate plus 2% from {_fmt(inp.intimated_on)} "
                "until payment, and must pay it with the claim without being asked.")
        notes.append(Note(level="bad", rule_ids=tat, text="Send the follow-up letter below to the insurer's grievance officer. "
                          "If there is no answer within 14 days, complain on Bima Bharosa and then to the Insurance Ombudsman."))
    return due, left, note, notes


def _cause_notes(inp: DeathClaimInput) -> list[Note]:
    notes: list[Note] = []
    start = policy_date(inp)
    if inp.cause == "suicide" and inp.kind in LIFE_KINDS:
        ids = _ids("suicide_clause", inp.date_of_death)
        if start and inp.date_of_death < add_months(start, 12):
            notes.append(Note(level="info", rule_ids=ids, text=(
                "The death was within 12 months of the policy start or revival. Most life policies exclude this, but "
                "the nominee is still entitled to at least 80% of the premiums paid (or the fund value of a unit-linked "
                "policy). Claim it.")))
        else:
            notes.append(Note(level="info", rule_ids=ids, text=(
                "Most life policies exclude suicide only in the first 12 months after the start or revival. "
                "Check the policy's suicide clause and claim the full benefit.")))
        notes.append(Note(level="info", text=(
            "If you or someone in the family needs to talk, Tele-MANAS (call 14416) offers free support at any hour.")))
    if inp.cause == "accident":
        notes.append(Note(level="info", text=(
            "Accidental death: claim every accident cover too, such as an accidental death rider, a personal accident "
            "policy, PMSBY, the owner-driver cover of a vehicle policy, and card or account covers.")))
        if inp.has_accident_cover and inp.kind in LIFE_KINDS:
            notes.append(Note(level="info", text="Ask the insurer to pay the accidental death benefit along with the basic sum assured."))
    if inp.assigned_to_lender:
        notes.append(Note(level="info", rule_ids=_ids("loan_assignment", inp.date_of_death), text=(
            "The policy is assigned to a lender: the lender gets only the loan outstanding on the date of death, and the "
            "insurer must pay the balance straight to the nominee. Ask both for the figures in writing.")))
    if inp.claimant_is_nominee is False:
        notes.append(Note(level="warn", text=(
            "As the claimant is not the nominee, the insurer will ask for proof that you are a legal heir. If there is a "
            "nominee, they should usually make the claim.")))
    return notes


def _who(inp: DeathClaimInput) -> str:
    relation = f", {inp.claimant_relation} of the deceased" if inp.claimant_relation else ""
    nominee = " and the nominee under this policy" if inp.claimant_is_nominee else ""
    return f"I am {inp.claimant_name or '[your name]'}{relation}{nominee}."


def _signature(inp: DeathClaimInput) -> list[str]:
    return ["", "Yours faithfully,", inp.claimant_name or "[your name]"] + [x for x in (inp.phone, inp.email) if x.strip()]


def intimation_letter(inp: DeathClaimInput, docs: list[str], today: date) -> str:
    place = {"hospital": " in hospital", "home": " at home", "other": ""}[inp.place_of_death]
    cause = {"accident": " in an accident", "illness": " after an illness", "suicide": "", "unknown": ""}[inp.cause]
    life = inp.kind in LIFE_KINDS
    timeline = (f" Please settle it within the time IRDAI sets ({NO_INVESTIGATION_DAYS} days from this intimation, or "
                f"{INVESTIGATION_DAYS} days if an investigation is needed).") if life else ""
    lines = [
        "To,", "The Claims Department,", inp.insurer or "[insurer]", "", f"Date: {_fmt(today)}", "",
        f"Subject: Intimation of death claim under policy no. {inp.policy_number or '[policy no.]'}", "",
        "Dear Sir/Madam,", "",
        (f"I write to inform you that {inp.life_assured or '[name of the deceased]'}, insured under the above policy, "
         f"died on {_fmt(inp.date_of_death)}{place}{cause}. {_who(inp)}"),
        "",
        (f"Please register this claim and give me a claim reference number. If you need any document not enclosed, "
         f"please ask for all of them at once.{timeline}"),
        "",
        "I enclose copies of:",
    ]
    lines += [f"{i}. {d}" for i, d in enumerate(docs, 1)]
    lines += ["", "Please pay the claim to my bank account (details enclosed)."]
    return "\n".join(lines + _signature(inp))


def interest_owed(inp: DeathClaimInput, today: date) -> float | None:
    """Simple interest at bank rate + 2% a year, from intimation to today (DEATH-TAT), if the rate was given."""
    if inp.bank_rate is None or not inp.cover_amount or inp.intimated_on is None:
        return None
    return round(inp.cover_amount * (inp.bank_rate + 2) / 100 * (today - inp.intimated_on).days / 365)


def follow_up_letter(inp: DeathClaimInput, due: date, today: date, interest: float | None = None) -> str:
    late = (today - due).days
    amount = f" of {rupees(inp.cover_amount)}" if inp.cover_amount else ""
    lines = [
        "To,", "The Grievance Redressal Officer,", inp.insurer or "[insurer]", "", f"Date: {_fmt(today)}", "",
        f"Subject: Delay in settling the death claim under policy no. {inp.policy_number or '[policy no.]'}", "",
        "Dear Sir/Madam,", "",
        (f"I intimated the death claim{amount} for {inp.life_assured or '[name of the deceased]'} on "
         f"{_fmt(inp.intimated_on)}. {_who(inp)}"),
        "",
        (f"Under the IRDAI Master Circular on Protection of Policyholders' Interests, 2024, the claim had to be settled by "
         f"{_fmt(due)}. It is now {late} days late."),
        "",
        "I request you to:",
        "- settle the claim within 14 days of this letter;",
        (f"- pay interest at the bank rate plus 2% from {_fmt(inp.intimated_on)} until the date of payment, as the "
         "circular requires" + (f" (about {rupees(interest)} up to today, at a bank rate of {inp.bank_rate:g}%);"
                                if interest is not None else ";")),
        "- if you need anything more from me, list it all in one reply.",
        "",
        "If this is not resolved within 14 days, I will complain to IRDAI on Bima Bharosa and to the Insurance Ombudsman.",
    ]
    return "\n".join(lines + _signature(inp))


def help_with_claim(inp: DeathClaimInput, today: date | None = None) -> DeathClaimResult:
    today = today or date.today()
    if inp.date_of_death > today:
        raise ValueError("The date of death cannot be in the future.")
    if inp.intimated_on and inp.intimated_on < inp.date_of_death:
        raise ValueError("The claim cannot be intimated before the date of death.")
    if inp.intimated_on and inp.intimated_on > today:
        raise ValueError("The date the claim was intimated cannot be in the future.")
    if inp.policy_start and inp.policy_start > inp.date_of_death:
        raise ValueError("The policy start date is after the date of death. Check both dates.")
    if inp.revival_date and inp.policy_start and inp.revival_date < inp.policy_start:
        raise ValueError("The revival date cannot be before the policy start date.")
    contestable, contest_note, contest_until, contest_ids = contest_status(inp)
    docs = documents(inp)
    due, left, deadline_note, deadline_notes = deadline(inp, today)
    notes = [Note(level="good" if contestable == "no" else "warn" if contestable == "limited" else "info",
                  rule_ids=contest_ids, text=contest_note)] + deadline_notes + _cause_notes(inp)
    steps = [
        "Get several copies of the death certificate: every insurer, bank and the EPFO will want one.",
        "Intimate every policy the person had, even ones you are unsure about." if inp.intimated_on is None
        else "Keep the claim reference number and copies of everything you send, with the date sent.",
        "Send the documents together; if the insurer asks for more, ask it to list everything in one go.",
        "Check the other money below: government schemes, EPF insurance, employer, loan and card covers.",
        "If the insurer is late or rejects the claim, write to its grievance officer; after 14 days escalate on Bima "
        "Bharosa, then to the Insurance Ombudsman (free, claims up to Rs 50 lakh).",
    ]
    late = left is not None and left < 0
    interest = interest_owed(inp, today) if late else None
    return DeathClaimResult(
        contestable=contestable, contest_note=contest_note, contest_until=contest_until, notes=notes, documents=docs,
        deadline=due, days_left=left, deadline_note=deadline_note, steps=steps, other_money=other_money(inp.cause),
        intimation_letter=intimation_letter(inp, docs, today),
        follow_up_letter=follow_up_letter(inp, due, today, interest) if late and due else None,
        interest_due=interest,
    )

"""Family insurance vault: every policy the family holds, checked for gaps a family finds out about too late.

Checks: missing nominee or policy number, premiums due or lapsed (with the grace period
for life and health policies), the 3-year rule for life policies, loan assignments, and
where the papers are kept. The emergency sheet lists everything for the family.
"""

from datetime import date, timedelta

from app.engine.calculator import rupees
from app.engine.dates import add_years
from app.engine.renewal import grace_days, renewal_events
from app.ics import Event, uid_part
from app.models import DueStatus, Note, SavedPolicy, VaultEntry, VaultEntryData, VaultKind, VaultSummary
from app.rules import rule_for

LIFE_KINDS: set[VaultKind] = {"term_life", "life_savings"}
NOMINEE_KINDS: set[VaultKind] = LIFE_KINDS | {"personal_accident", "health", "critical_illness"}
HEALTH_GRACE_KINDS: set[VaultKind] = {"health", "critical_illness"}
DUE_SOON_DAYS = 30

KIND_LABEL: dict[str, str] = {
    "health": "Health insurance", "term_life": "Term life insurance",
    "life_savings": "Life insurance (endowment / money-back / ULIP)", "personal_accident": "Personal accident insurance",
    "critical_illness": "Critical illness insurance", "motor": "Vehicle insurance", "home": "Home insurance",
    "travel": "Travel insurance", "other": "Other insurance",
}
RELATION_LABEL = {"spouse": "spouse", "child": "child", "parent": "parent", "sibling": "brother/sister",
                  "other_relative": "other relative", "other": "other"}
MODE_LABEL = {"yearly": "yearly", "half_yearly": "half-yearly", "quarterly": "quarterly", "monthly": "monthly",
              "single": "single premium"}
PER_YEAR = {"yearly": 1, "half_yearly": 2, "quarterly": 4, "monthly": 12, "single": 0}


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def _ids(group: str, on: date) -> list[str]:
    rule = rule_for(group, on)
    return [rule.id] if rule else []


def entry_grace_days(e: VaultEntryData) -> int:
    """Grace period IRDAI guarantees: life and health policies only. Other general policies have none."""
    return grace_days(e.premium_mode) if e.kind in LIFE_KINDS | HEALTH_GRACE_KINDS else 0


def due_status(e: VaultEntryData, today: date) -> tuple[DueStatus, int | None, date | None]:
    if e.end_date and e.end_date < today:
        return "ended", None, None
    if e.next_due is None:
        return "none", None, None
    days = (e.next_due - today).days
    grace = entry_grace_days(e)
    grace_until = e.next_due + timedelta(days=grace) if grace else None
    if days >= 0:
        return ("due_soon" if days <= DUE_SOON_DAYS else "ok"), days, grace_until
    if grace_until and today <= grace_until:
        return "grace", days, grace_until
    return "lapsed", days, grace_until


def _due_notes(e: VaultEntryData, status: DueStatus, days: int | None, grace_until: date | None, today: date) -> list[Note]:
    life, health = e.kind in LIFE_KINDS, e.kind in HEALTH_GRACE_KINDS
    group = "life_grace" if life else "health_grace"
    what = "Renewal" if e.kind not in LIFE_KINDS else "Premium"
    if status == "none":
        if e.premium_mode == "single" and life:
            return []
        return [Note(level="info", text="Add the next premium or renewal date to get reminders.")]
    if status == "ok":
        return []
    if status == "due_soon":
        when = "today" if days == 0 else f"in {days} days"
        extra = f" If you miss it, the grace period runs until {_fmt(grace_until)}." if grace_until else \
            " There is no grace period guaranteed for this kind of policy: renew before it ends."
        return [Note(level="warn", rule_ids=_ids(group, today) if grace_until else [],
                     text=f"{what} due on {_fmt(e.next_due)} ({when}).{extra}")]
    if status == "grace":
        if life:
            text = (f"The premium was due on {_fmt(e.next_due)}. You are in the grace period until {_fmt(grace_until)}: "
                    "the life cover continues until then. Pay before that date or the policy lapses.")
        else:
            text = (f"The renewal was due on {_fmt(e.next_due)}. Renew by {_fmt(grace_until)} (grace period) to keep "
                    "waiting-period credits and bonus.")
        return [Note(level="warn", rule_ids=_ids(group, today), text=text)]
    if status == "lapsed":
        if life:
            return [Note(level="bad", rule_ids=_ids("life_grace", today), text=(
                f"The premium due on {_fmt(e.next_due)} was not paid within the grace period, so the policy has "
                "probably lapsed and the life cover has stopped. Ask the insurer how to revive it: revival usually "
                "needs the unpaid premiums with interest, and sometimes a health declaration."))]
        if health:
            return [Note(level="bad", rule_ids=_ids("health_grace", today), text=(
                f"The grace period ended on {_fmt(grace_until)}. Contact the insurer today: a lapse can restart "
                "waiting periods."))]
        if e.kind == "motor":
            return [Note(level="bad", text=(
                f"This vehicle policy expired on {_fmt(e.next_due)}. Driving without at least third-party insurance is "
                "an offence under the Motor Vehicles Act: renew before using the vehicle."))]
        return [Note(level="bad", text=f"Expired on {_fmt(e.next_due)}. Renew it if you still need this cover.")]
    # ended
    if e.kind == "life_savings":
        return [Note(level="info", rule_ids=_ids("unclaimed_amounts", today), text=(
            f"Matured on {_fmt(e.end_date)}. If the maturity amount has not been paid, claim it: money unpaid for "
            "12 months becomes an 'unclaimed amount'."))]
    return [Note(level="info", text=f"The cover ended on {_fmt(e.end_date)}.")]


def check_entry(e: VaultEntryData, today: date) -> tuple[list[Note], DueStatus, int | None, date | None]:
    status, days, grace_until = due_status(e, today)
    notes = _due_notes(e, status, days, grace_until, today)
    active = status != "ended"
    life = e.kind in LIFE_KINDS

    if not e.policy_number.strip():
        notes.append(Note(level="warn", text="Add the policy number: it is the first thing your family will need to claim."))
    if active and e.kind in NOMINEE_KINDS and not e.nominee.strip():
        if life or e.kind == "personal_accident":
            notes.append(Note(level="bad" if life else "warn", rule_ids=_ids("nomination", today) if life else [], text=(
                "No nominee recorded. The insurer pays a death claim to the nominee; without one the family may need a "
                "succession certificate, which can take months. Add a nominee through the insurer: it can be changed "
                "at any time.")))
        else:
            notes.append(Note(level="warn", text=(
                "No nominee recorded. If the policyholder dies, any claim money is paid to the nominee: add one "
                "through the insurer.")))
    if active and life and e.nominee.strip():
        if e.nominee_relation in ("sibling", "other_relative", "other"):
            notes.append(Note(level="info", rule_ids=_ids("beneficial_nominee", today), text=(
                f"Only a spouse, parent or child can be a 'beneficial nominee'. {e.nominee} may receive the money only "
                "on behalf of the legal heirs. If you want them to keep it, also make a Will.")))
        elif not e.nominee_relation:
            notes.append(Note(level="info", text="Add the nominee's relation to the policyholder."))
    if active and e.assigned_to_lender:
        notes.append(Note(level="info", rule_ids=_ids("loan_assignment", today), text=(
            "Assigned to a lender: on a death claim the lender gets only the loan still outstanding, and the rest is "
            "paid to the nominee. Keep the loan account details with the policy.")))
    if not e.documents_at.strip():
        notes.append(Note(level="warn", text=(
            "Write down where the policy papers are kept (or that they are in DigiLocker or email), so your family "
            "can find them.")))
    if active and life and e.start_date:
        start = max(e.start_date, e.revival_date) if e.revival_date else e.start_date
        since = "revival" if e.revival_date and e.revival_date >= e.start_date else "start"
        three = add_years(start, 3)
        if today < three:
            notes.append(Note(level="info", rule_ids=_ids("life_incontestable", today), text=(
                f"Until {_fmt(three)} (3 years from the policy {since}), the insurer can question this policy for fraud "
                "or for wrong or missing facts in the proposal form. Keep a copy of the proposal form you signed.")))
        else:
            notes.append(Note(level="good", rule_ids=_ids("life_incontestable", today), text=(
                f"More than 3 years since the policy {since} ({_fmt(start)}): it can no longer be questioned on any "
                "ground.")))
    return notes, status, days, grace_until


def validate(e: VaultEntryData) -> VaultEntryData:
    """Reject impossible dates before saving (shown to the user as a 400 message)."""
    if e.start_date:
        if e.revival_date and e.revival_date < e.start_date:
            raise ValueError("The revival date cannot be before the policy start date.")
        if e.end_date and e.end_date < e.start_date:
            raise ValueError("The end or maturity date cannot be before the policy start date.")
    if not e.insurer.strip() or not e.holder.strip():
        raise ValueError("Enter the insurer and the policyholder.")
    return e


def to_entry(entry_id: int, data: VaultEntryData, today: date | None = None) -> VaultEntry:
    today = today or date.today()
    notes, status, days, grace_until = check_entry(data, today)
    return VaultEntry(**data.model_dump(), id=entry_id, checks=notes, due_status=status, days_to_due=days,
                      grace_until=grace_until)


def _entry_lines(i: int, e: VaultEntry) -> list[str]:
    title = f"{i}. {KIND_LABEL[e.kind]}: {e.insurer}" + (f" ({e.plan_name})" if e.plan_name else "")
    people = f"Policyholder: {e.holder}" + (f" | Insured: {e.insured}" if e.insured else "")
    money = []
    if e.cover_amount:
        money.append(f"Cover: {rupees(e.cover_amount)}")
    if e.premium:
        money.append(f"Premium: {rupees(e.premium)} {MODE_LABEL[e.premium_mode]}")
    if e.next_due and e.due_status != "ended":
        money.append(f"next due {_fmt(e.next_due)}")
    if e.end_date:
        money.append(f"ends {_fmt(e.end_date)}")
    nominee = e.nominee or "NOT RECORDED"
    if e.nominee and e.nominee_relation:
        nominee += f" ({RELATION_LABEL[e.nominee_relation]})"
    lines = [title, f"   Policy no.: {e.policy_number or 'NOT RECORDED'}", f"   {people}"]
    if money:
        lines.append("   " + " | ".join(money))
    lines.append(f"   Nominee: {nominee}" + (" | Assigned to a lender" if e.assigned_to_lender else ""))
    extra = [x for x in (f"Papers kept at: {e.documents_at}" if e.documents_at else "",
                         f"Claim helpline: {e.claim_helpline}" if e.claim_helpline else "",
                         f"Agent: {e.agent_contact}" if e.agent_contact else "") if x]
    if extra:
        lines.append("   " + " | ".join(extra))
    if e.notes:
        lines.append(f"   Notes: {e.notes}")
    return lines


def emergency_sheet(entries: list[VaultEntry], policies: list[SavedPolicy], today: date) -> str:
    lines = ["FAMILY INSURANCE SHEET",
             f"Made with ClaimSaathi on {_fmt(today)}. Keep it with your important papers and tell your family where it is.",
             ""]
    if entries:
        lines.append("POLICIES")
        for i, e in enumerate(entries, 1):
            lines += _entry_lines(i, e)
        lines.append("")
    if policies:
        lines.append("HEALTH POLICIES (full terms saved in ClaimSaathi, My policies)")
        for p in policies:
            t = p.terms
            renews = f", renews {_fmt(t.period_end)}" if t.period_end else ""
            lines.append(f"- {p.name}, {t.insurer or 'insurer not set'}: sum insured {rupees(t.sum_insured)}{renews}")
        lines.append("")
    if not entries and not policies:
        lines += ["No policies added yet.", ""]
    lines += [
        "IF SOMEONE IS ADMITTED TO HOSPITAL",
        "- Show the health card or policy number at the hospital's insurance (TPA) desk and ask for cashless treatment.",
        "- The insurer must decide a cashless request within 1 hour and approve the discharge within 3 hours.",
        "",
        "IF SOMEONE DIES",
        "- Tell every insurer as soon as possible. A claim cannot be rejected only because it was intimated late.",
        "- Life insurers must settle a death claim within 15 days of intimation (45 days if they investigate), or pay interest.",
        "- Also check: PMJJBY / PMSBY (bank account schemes), EDLI (for EPF members), employer cover, and cover linked to loans and cards.",
        "- Search for forgotten policies: https://bimabharosa.irdai.gov.in/Home/UnclaimedAmount",
        "- ClaimSaathi's Death claim tab lists the documents and drafts the letters.",
    ]
    return "\n".join(lines)


def summary(rows: list[tuple[int, VaultEntryData]], policies: list[SavedPolicy], today: date | None = None) -> VaultSummary:
    today = today or date.today()
    entries = [to_entry(i, d, today) for i, d in rows]
    live = [e for e in entries if e.due_status not in ("ended", "lapsed")]

    def cover(kinds: set[str]) -> float:
        return sum(e.cover_amount for e in live if e.kind in kinds)

    return VaultSummary(
        entries=entries,
        health_policies=len(policies),
        life_cover=cover(LIFE_KINDS),
        accident_cover=cover({"personal_accident"}),
        health_cover=cover({"health"}) + sum(p.terms.sum_insured for p in policies),
        yearly_premium=sum(e.premium * PER_YEAR[e.premium_mode] for e in entries if e.due_status != "ended"),
        missing_nominee=sum(1 for e in entries if e.kind in NOMINEE_KINDS and e.due_status != "ended" and not e.nominee.strip()),
        due_soon=sum(1 for e in entries if e.due_status in ("due_soon", "grace")),
        emergency_sheet=emergency_sheet(entries, policies, today),
    )


def calendar_events(rows: list[tuple[int, VaultEntryData]], policies: list[SavedPolicy], today: date | None = None) -> list[Event]:
    """Reminders for every vault premium or renewal and every saved health policy."""
    today = today or date.today()
    events: list[Event] = []
    for entry_id, e in rows:
        if e.next_due is None or (e.end_date and e.end_date < today):
            continue
        label = f"{KIND_LABEL[e.kind]} - {e.insurer}" + (f" ({e.policy_number})" if e.policy_number else "")
        what = "premium" if e.kind in LIFE_KINDS else "renewal"
        base = f"vault-{entry_id}-{uid_part(e.insurer)}"
        plan = [(e.next_due - timedelta(days=15), "due-15", f"{label}: {what} due in 15 days"),
                (e.next_due, "due-0", f"{label}: {what} due today")]
        grace = entry_grace_days(e)
        if grace:
            plan.append((e.next_due + timedelta(days=grace - 3), "grace", f"{label}: grace period ends in 3 days"))
        for day, tag, summary_text in plan:
            if day >= today:
                events.append(Event(uid=f"{base}-{tag}-{day:%Y%m%d}", day=day, summary=summary_text,
                                    description=f"{summary_text}. Due date: {_fmt(e.next_due)}."))
    for p in policies:
        events += renewal_events(p.id, p.name, p.terms, today)
    return events

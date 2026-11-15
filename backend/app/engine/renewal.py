"""Renewal guard: when to renew, what a lapse would cost, and benefits to use before renewal.

A health policy renewed on time (or within the grace period) keeps every credit:
waiting periods served, moratorium months and bonus. A lapse can restart them all.
"""

from datetime import date, timedelta

from app.engine.calculator import rupees
from app.engine.dates import add_months, months_between
from app.extraction.benefits import BY_KEY
from app.ics import Event, uid_part
from app.models import Note, PolicyTerms, PremiumMode, RenewalInput, RenewalStatus
from app.rules import rule_for

RENEW_SOON_DAYS = 45
SENIOR_AGE = 60
SENIOR_CAP_PERCENT = 10


def grace_days(mode: PremiumMode) -> int:
    return 15 if mode == "monthly" else 30


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def credits_at_stake(terms: PolicyTerms, today: date) -> list[str]:
    """What a lapse could cost: continuous-cover months, waiting periods served, bonus."""
    out: list[str] = []
    start = terms.first_inception_date
    if start and start <= today:
        months = months_between(start, today)
        out.append(f"{months} months of continuous cover (since {_fmt(start)})")
        w = terms.waiting
        for label, period in (("Pre-existing disease waiting period", w.pre_existing_months),
                              ("Specific disease waiting period", w.specific_disease_months),
                              ("Maternity waiting period", w.maternity_months)):
            if not period:
                continue
            done = add_months(start, period)
            if today >= done:
                out.append(f"{label} ({period} months): fully served on {_fmt(done)}")
            else:
                out.append(f"{label} ({period} months): {months} months served, ends on {_fmt(done)}")
        mora = rule_for("moratorium", today)
        if mora and mora.months:
            if months >= mora.months:
                out.append(f"Moratorium: after {mora.months} months, claims can no longer be contested for non-disclosure")
            else:
                out.append(f"Moratorium: {months} of {mora.months} months done")
    if terms.cumulative_bonus_amount > 0:
        out.append(f"Cumulative bonus of {rupees(terms.cumulative_bonus_amount)}")
    return out


def unused_benefits(terms: PolicyTerms) -> list[str]:
    """Yearly benefits not used in the current policy year (they usually do not carry over)."""
    out = []
    for b in terms.benefits:
        info = BY_KEY.get(b.key)
        if not info or not info.resets_yearly or b.status != "covered":
            continue
        used_this_year = b.last_used is not None and (terms.period_start is None or b.last_used >= terms.period_start)
        if not used_this_year:
            out.append(info.name + (f" ({b.limit})" if b.limit else ""))
    return out


def premium_check(inp: RenewalInput) -> Note | None:
    old, new = inp.current_premium, inp.renewal_premium
    if not old or new is None:
        return None
    change = (new / old - 1) * 100
    if change <= 0:
        return Note(level="good", text=f"The renewal premium is {abs(change):.1f}% {'lower' if change < 0 else 'the same'}.")
    text = f"The premium rises by {change:.1f}% ({rupees(old)} to {rupees(new)})."
    rule = rule_for("senior_premium_cap")
    senior = inp.oldest_member_age is not None and inp.oldest_member_age >= SENIOR_AGE
    if senior and change > SENIOR_CAP_PERCENT and inp.terms.policy_kind != "group" and rule:
        return Note(level="warn", rule_ids=[rule.id], text=(
            f"{text} For people aged {SENIOR_AGE} and above, IRDAI told insurers not to raise individual health "
            f"premiums by more than {SENIOR_CAP_PERCENT}% a year without consulting IRDAI first. Ask the insurer in "
            "writing why it went up and whether IRDAI was consulted. If you are not satisfied, complain to the "
            "insurer and then on Bima Bharosa."))
    return Note(level="info", text=(
        f"{text} Common reasons: moving into a higher age band, a higher sum insured, or the insurer revising its "
        "rates. Ask the insurer for the reason in writing."))


def renewal_status(inp: RenewalInput, today: date | None = None) -> RenewalStatus:
    today = today or date.today()
    terms = inp.terms
    end = terms.period_end
    at_stake = credits_at_stake(terms, min(today, end) if end else today)  # credits stop growing once it ends
    unused = unused_benefits(terms)
    check = premium_check(inp)
    grace = rule_for("health_grace", today)
    grace_ids = [grace.id] if grace else []

    if end is None:
        return RenewalStatus(status="unknown", headline="Add the policy end date ('Current period to') to get renewal reminders.",
                             at_stake=at_stake, notes=[], unused_benefits=unused, premium_check=check)

    days = grace_days(terms.premium_mode)
    grace_until = end + timedelta(days=days)
    days_left = (end - today).days
    notes: list[Note] = []
    renew = rule_for("health_renewal", today)
    port = rule_for("portability_credits", today)

    if today <= end:
        status = "due_soon" if days_left <= RENEW_SOON_DAYS else "active"
        when = "today" if days_left == 0 else f"in {days_left} days"
        headline = f"Renew by {_fmt(end)} ({when})."
        notes.append(Note(level="info", rule_ids=grace_ids, text=(
            f"If you miss it, you get a {days}-day grace period, until {_fmt(grace_until)}. Renewing within it keeps "
            "all your credits.")))
        if status == "due_soon" and renew:
            notes.append(Note(level="info", rule_ids=[renew.id], text=(
                "The insurer cannot refuse to renew because you made claims, and cannot ask fresh medical questions "
                "unless you raise the sum insured.")))
        if port:
            notes.append(Note(level="info", rule_ids=[port.id], text=(
                "Thinking of switching insurer? Port this policy instead of buying a new one, so your credits move "
                "with you. Start well before the renewal date, as the new insurer must accept you first.")))
    elif today <= grace_until:
        status = "grace"
        headline = f"Your policy ended on {_fmt(end)}. Renew by {_fmt(grace_until)} (grace period) to keep your credits."
        if terms.premium_mode in ("yearly", "single"):
            notes.append(Note(level="warn", rule_ids=grace_ids, text=(
                "Treatment during this gap may not be covered: IRDAI guarantees cover in the grace period only for "
                "premiums paid in instalments. Renew today.")))
        else:
            notes.append(Note(level="info", rule_ids=grace_ids, text=(
                "You pay in instalments: IRDAI says cover continues during the grace period for instalment "
                "premiums. Pay now to keep it that way.")))
        if renew:
            notes.append(Note(level="info", rule_ids=[renew.id], text=(
                "The insurer cannot refuse to renew because you made claims.")))
    else:
        status = "lapsed"
        headline = f"The grace period ended on {_fmt(grace_until)}. Call the insurer today."
        notes.append(Note(level="bad", rule_ids=grace_ids, text=(
            "If the policy has lapsed, a new policy would start the waiting periods again and the credits below "
            "could be lost. Ask the insurer in writing whether it can still be renewed, and keep the reply.")))

    return RenewalStatus(status=status, renew_by=end, grace_until=grace_until, days_left=days_left, headline=headline,
                         at_stake=at_stake, notes=notes, unused_benefits=unused if status != "lapsed" else [],
                         premium_check=check)


def renewal_events(policy_id: int, name: str, terms: PolicyTerms, today: date | None = None) -> list[Event]:
    """Calendar reminders before the renewal date and before the grace period ends."""
    today = today or date.today()
    end = terms.period_end
    if end is None:
        return []
    grace_until = end + timedelta(days=grace_days(terms.premium_mode))
    unused = unused_benefits(terms)
    extra = (" Use before renewal: " + "; ".join(unused) + ".") if unused else ""
    base = f"policy-{policy_id}-{uid_part(name)}"
    keep = " Renew on time to keep your waiting-period credits and bonus."
    plan = [
        (end - timedelta(days=30), "renew-30", f"Renew {name} in 30 days", f"{name} ends on {_fmt(end)}.{keep}{extra}"),
        (end - timedelta(days=7), "renew-7", f"Renew {name} this week", f"{name} ends on {_fmt(end)}.{keep}{extra}"),
        (end, "renew-0", f"Renew {name} today", f"{name} ends today.{keep}"),
        (grace_until - timedelta(days=3), "grace", f"Last days of the grace period: {name}",
         f"The grace period for {name} ends on {_fmt(grace_until)}. After that the policy may lapse."),
    ]
    return [Event(uid=f"{base}-{tag}-{day:%Y%m%d}", day=day, summary=summary, description=desc)
            for day, tag, summary, desc in plan if day >= today]

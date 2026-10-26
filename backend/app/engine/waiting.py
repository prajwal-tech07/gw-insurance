"""Waiting periods and the moratorium, checked against the admission date."""

from datetime import date

from app.engine.dates import add_months, months_between
from app.engine.text import matching_terms
from app.models import PolicyTerms, WaitingStatus
from app.rules import rule_for

MATERNITY_TERMS = ["maternity", "delivery", "pregnan", "caesarean", "cesarean", "c section", "lscs", "childbirth"]


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def _period_status(name: str, period: str, start: date, months: int, admission: date,
                   blocked_text: str, ok_text: str) -> WaitingStatus:
    covered_from = add_months(start, months)
    if admission < covered_from:
        return WaitingStatus(name=name, period=period, covered_from=covered_from, status="blocked",
                             explanation=f"{blocked_text} Covered from {_fmt(covered_from)}.")
    return WaitingStatus(name=name, period=period, covered_from=covered_from, status="ok",
                         explanation=f"{ok_text} (completed on {_fmt(covered_from)}).")


def check_waiting(terms: PolicyTerms, admission: date, diagnosis: str = "",
                  is_accident: bool = False, is_pre_existing: bool | None = None) -> list[WaitingStatus]:
    w = terms.waiting
    start = terms.first_inception_date
    out: list[WaitingStatus] = []

    # 1. Initial waiting period
    period = f"{w.initial_days} days"
    if is_accident:
        out.append(WaitingStatus(name="Initial waiting period", period=period, status="not_applicable",
                                 explanation="Accidents are covered from day one."))
    elif start is None:
        out.append(WaitingStatus(name="Initial waiting period", period=period, status="unknown",
                                 explanation="Add the date your cover first started to check this."))
    else:
        covered_from = date.fromordinal(start.toordinal() + w.initial_days)
        status = "blocked" if admission < covered_from else "ok"
        text = ("Only accidents are covered in the first days of a new policy."
                if status == "blocked" else "Initial waiting period is over.")
        out.append(WaitingStatus(name="Initial waiting period", period=period, covered_from=covered_from,
                                 status=status, explanation=f"{text} Covered from {_fmt(covered_from)}."))

    # 2. Pre-existing diseases
    ped_rule = rule_for("ped_max_waiting", terms.period_start or admission)
    if w.pre_existing_months is None:
        out.append(WaitingStatus(name="Pre-existing disease waiting period", period="not found",
                                 status="unknown",
                                 explanation="The policy's pre-existing disease waiting period was not found. Add it to check."))
    else:
        months = w.pre_existing_months
        period = f"{months} months"
        rule_ids = []
        cap_note = ""
        if ped_rule and ped_rule.months and months > ped_rule.months:
            rule_ids.append(ped_rule.id)
            cap_note = (f" Note: IRDAI caps this at {ped_rule.months} months for policies from "
                        f"{_fmt(ped_rule.effective_from) if ped_rule.effective_from else 'that period'}; ask your insurer.")
        if is_pre_existing is False:
            status = WaitingStatus(name="Pre-existing disease waiting period", period=period,
                                   status="not_applicable",
                                   explanation="You said this condition did not exist before the policy started.")
        elif start is None:
            status = WaitingStatus(name="Pre-existing disease waiting period", period=period, status="unknown",
                                   explanation="Add the date your cover first started to check this.")
        else:
            status = _period_status("Pre-existing disease waiting period", period, start, months, admission,
                                    "Treatment of a pre-existing disease is not covered yet.",
                                    "Pre-existing disease waiting period is over")
            if is_pre_existing is None and status.status == "blocked":
                status.status = "unknown"
                status.explanation = ("If this condition existed before the policy started, it is not covered yet. "
                                      f"Covered from {_fmt(status.covered_from)}.") if status.covered_from else status.explanation
        status.explanation += cap_note
        status.rule_ids = rule_ids
        out.append(status)

    # 3. Specific diseases (cataract, hernia, ...)
    if w.specific_disease_months and w.specific_diseases:
        period = f"{w.specific_disease_months} months"
        hits = matching_terms(diagnosis, w.specific_diseases) if diagnosis else []
        if not diagnosis:
            out.append(WaitingStatus(name="Specific disease waiting period", period=period, status="unknown",
                                     explanation="Enter the diagnosis to check the specific-disease list."))
        elif not hits:
            out.append(WaitingStatus(name="Specific disease waiting period", period=period, status="not_applicable",
                                     explanation="The diagnosis is not on the policy's specific-disease list."))
        elif start is None:
            out.append(WaitingStatus(name=f"Specific disease waiting period ({hits[0]})", period=period,
                                     status="unknown", explanation="Add the date your cover first started to check this."))
        else:
            out.append(_period_status(f"Specific disease waiting period ({hits[0]})", period, start,
                                      w.specific_disease_months, admission,
                                      f"'{hits[0]}' has a {period} waiting period.",
                                      f"'{hits[0]}' waiting period is over"))

    # 4. Maternity
    if diagnosis and matching_terms(diagnosis, MATERNITY_TERMS):
        if w.maternity_months is None:
            out.append(WaitingStatus(name="Maternity waiting period", period="not found", status="unknown",
                                     explanation="Check whether the policy covers maternity and after how long."))
        elif start is None:
            out.append(WaitingStatus(name="Maternity waiting period", period=f"{w.maternity_months} months",
                                     status="unknown", explanation="Add the date your cover first started to check this."))
        else:
            out.append(_period_status("Maternity waiting period", f"{w.maternity_months} months", start,
                                      w.maternity_months, admission, "Maternity is not covered yet.",
                                      "Maternity waiting period is over"))

    # 5. Moratorium
    mora = rule_for("moratorium", admission)
    if mora and mora.months and start is not None:
        continuous = months_between(start, admission)
        covered_from = add_months(start, mora.months)
        if continuous >= mora.months:
            out.append(WaitingStatus(
                name="Moratorium (protection from non-disclosure disputes)", period=f"{mora.months} months",
                covered_from=covered_from, status="ok", rule_ids=[mora.id],
                explanation=(f"You have {continuous} months of continuous cover. The insurer cannot contest this "
                             "claim for non-disclosure or misrepresentation, except proven fraud.")))
        else:
            out.append(WaitingStatus(
                name="Moratorium (protection from non-disclosure disputes)", period=f"{mora.months} months",
                covered_from=covered_from, status="not_applicable", rule_ids=[mora.id],
                explanation=(f"Starts after {mora.months} months of continuous cover, on {_fmt(covered_from)}. "
                             "Until then the insurer can question non-disclosure.")))
    return out

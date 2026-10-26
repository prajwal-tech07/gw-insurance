"""Before admission: compare room options and warn about what the policy will not pay."""

from app.engine.calculator import calculate_claim, rupees
from app.engine.classifier import normalize
from app.engine.text import matching_terms
from app.models import BillCategory, BillItem, ClaimInput, EstimateInput, EstimateResult, OptionResult

ROOM_WORDS = {"room", "ac", "a", "c", "ward", "category"}


def _category_rent(inp: EstimateInput) -> float | None:
    """For limits like 'single private room': the hospital's rent for that category, if listed."""
    if inp.terms.room_rent.kind != "category" or not inp.terms.room_rent.category:
        return None
    wanted = set(normalize(inp.terms.room_rent.category).split()) - ROOM_WORDS
    for opt in inp.room_options:
        if wanted and wanted <= set(normalize(opt.name).split()):
            return opt.rent_per_day
    return None


def estimate(inp: EstimateInput) -> EstimateResult:
    category_rent = _category_rent(inp)
    options: list[OptionResult] = []
    for opt in inp.room_options:
        items = list(inp.items)
        if inp.room_days > 0:
            items.append(BillItem(description=f"Room rent - {opt.name}", amount=opt.rent_per_day * inp.room_days,
                                  category=BillCategory.room_rent))
        if inp.icu_days > 0 and inp.icu_rent_per_day > 0:
            items.append(BillItem(description="ICU charges", amount=inp.icu_rent_per_day * inp.icu_days,
                                  category=BillCategory.icu))
        claim = ClaimInput(
            admission_date=inp.admission_date, patient_age=inp.patient_age, diagnosis=inp.diagnosis,
            is_accident=inp.is_accident, is_pre_existing=inp.is_pre_existing, room_days=inp.room_days,
            icu_days=inp.icu_days, hospital_differential_billing=inp.hospital_differential_billing,
            eligible_category_rent_per_day=category_rent, items=items,
        )
        options.append(OptionResult(option=opt, result=calculate_claim(inp.terms, claim)))

    best = min(options, key=lambda o: (o.result.you_pay, o.option.rent_per_day))
    worst = max(options, key=lambda o: o.result.you_pay)
    first = options[0].result
    eligible = best.result.eligible_room_rent_per_day

    if best.result.blocked:
        recommendation = ("This claim is likely to be rejected (see the warnings). "
                          f"If it is accepted, the insurer would pay about {rupees(best.result.payable_if_covered)}.")
    else:
        recommendation = (f"Choose '{best.option.name}': the insurer pays about {rupees(best.result.insurer_pays)} "
                          f"and you pay about {rupees(best.result.you_pay)}.")
        extra = worst.result.you_pay - best.result.you_pay
        rent_gap = (worst.option.rent_per_day - best.option.rent_per_day) * inp.room_days
        if worst is not best and extra > 0:
            recommendation += (f" '{worst.option.name}' would cost you {rupees(extra)} more")
            if extra > rent_gap + 1:
                recommendation += (f", not just the {rupees(rent_gap)} extra rent, because the insurer cuts related "
                                   "charges in proportion")
            recommendation += "."

    warnings: list[str] = []
    for o in options:
        for issue in o.result.issues:
            if issue.level in ("block", "warn") and issue.message not in warnings:
                warnings.append(issue.message)

    questions = [
        "Is this hospital in my insurer's network for cashless treatment?",
        "What is the daily rent for each room category? Do doctor, nursing and OT charges change with the room category?",
        "Can I get an itemised estimate (surgeon, anaesthetist, OT, medicines, implants, tests)?",
        "Please send the cashless pre-authorisation request as soon as I am admitted. The insurer must decide within 1 hour.",
        "At discharge, the insurer must give final approval within 3 hours of your request. If it is late, the extra charges are the insurer's.",
    ]
    if eligible:
        questions.insert(1, f"Do you have a room at or below {rupees(eligible)} per day? That is my policy's limit.")
    if any(i.category == BillCategory.implants for o in options[:1] for i in o.result.items):
        questions.append("Which implant is planned and what does it cost? Is there an equivalent lower-cost option?")
    for sub in inp.terms.sub_limits:
        if inp.diagnosis and matching_terms(inp.diagnosis, sub.keywords or [sub.name]):
            questions.append(f"My policy caps {sub.name} treatment. Can the package be kept within that limit?")
    if any(i.irdai_list == "I" for i in first.items):
        questions.append("Can I bring my own items such as gloves and masks, or is there a package rate that includes them?")
    if any(i.irdai_list in ("II", "III", "IV") for i in first.items):
        questions.append("Some estimate lines should be part of room, OT or treatment charges. Can you include them instead of billing separately?")

    return EstimateResult(
        options=options,
        recommended=best.option.name,
        recommendation=recommendation,
        eligible_room_rent_per_day=eligible,
        waiting=first.waiting,
        warnings=warnings,
        questions=questions,
        items_you_pay=[i for i in best.result.items if i.deducted > 0],
    )

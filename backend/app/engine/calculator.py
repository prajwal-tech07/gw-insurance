"""Deterministic claim calculator.

The AI never does this maths. Every rupee deducted is recorded as a Step with the
rule it came from, so the result can always answer "why Rs X?".

Order of steps:
 1. waiting periods / exclusions        (can block the claim)
 2. IRDAI List I-IV items removed
 3. room-rent limit + proportionate cut on associate expenses only
 4. ICU per-day limit
 5. sub-limit for the procedure
 6. deductible and co-pay               (order set per policy)
 7. sum insured (+ bonus) cap
"""

from app.engine.classifier import classify_item
from app.engine.text import matching_terms, significant_words
from app.engine.waiting import check_waiting
from app.extraction.parsing import inr
from app.models import (
    BillCategory,
    ClaimInput,
    ClaimResult,
    ClassifiedItem,
    Issue,
    ItemResult,
    PolicyTerms,
    RoomLimit,
    Step,
    SubLimit,
)

# Charges that move with the room category (IRDAI "associate medical expenses").
ASSOCIATE = {BillCategory.nursing, BillCategory.professional_fees, BillCategory.ot_charges}


def rupees(x: float) -> str:
    return inr(x)


def per_day_limit(limit: RoomLimit, sum_insured: float, category_rent: float | None = None) -> float | None:
    if limit.kind == "percent_of_si" and limit.percent:
        value = sum_insured * limit.percent / 100
        return min(value, limit.amount) if limit.amount else value
    if limit.kind == "fixed" and limit.amount:
        return limit.amount
    if limit.kind == "category":
        return category_rent
    return None


def sub_limit_cap(sub: SubLimit, sum_insured: float) -> float | None:
    caps = []
    if sub.amount:
        caps.append(sub.amount)
    if sub.percent_of_si:
        caps.append(sum_insured * sub.percent_of_si / 100)
    return min(caps) if caps else None


class _Line:
    def __init__(self, item: ClassifiedItem):
        self.item = item
        self.payable = item.amount
        self.reasons: list[str] = []

    def cut(self, amount: float, reason: str) -> None:
        amount = min(amount, self.payable)
        if amount > 0:
            self.payable -= amount
            self.reasons.append(reason)

    def result(self) -> ItemResult:
        return ItemResult(
            description=self.item.description,
            category=self.item.category,
            irdai_list=self.item.irdai_list,
            billed=round(self.item.amount, 2),
            payable=round(self.payable, 2),
            deducted=round(self.item.amount - self.payable, 2),
            reasons=self.reasons,
        )


def calculate_claim(terms: PolicyTerms, claim: ClaimInput) -> ClaimResult:
    steps: list[Step] = []
    issues: list[Issue] = []
    lines = [_Line(classify_item(i)) for i in claim.items]
    total_billed = sum(line.item.amount for line in lines)

    def running() -> float:
        return sum(line.payable for line in lines)

    # 1. Waiting periods and exclusions --------------------------------------
    waiting = check_waiting(terms, claim.admission_date, claim.diagnosis, claim.is_accident, claim.is_pre_existing)
    blocked = False
    for w in waiting:
        if w.status == "blocked":
            blocked = True
            issues.append(Issue(level="block", code="waiting_period", message=f"{w.name}: {w.explanation}",
                                rule_ids=w.rule_ids))
        elif w.status == "unknown" and w.name.startswith("Pre-existing") and w.covered_from:
            issues.append(Issue(level="warn", code="ped_unknown", message=w.explanation))

    if terms.sum_insured <= 0:
        blocked = True
        issues.append(Issue(level="block", code="no_sum_insured",
                            message="The sum insured is missing. Add it to the policy terms."))

    if claim.diagnosis:
        for exclusion in terms.exclusions:
            words = significant_words(exclusion)
            if words and matching_terms(claim.diagnosis, words):
                issues.append(Issue(level="warn", code="possible_exclusion",
                                    message=(f"The diagnosis may fall under the exclusion '{exclusion}'. "
                                             "Check the exact clause; insurers must cite it if they reject.")))

    # 2. IRDAI List I-IV items -----------------------------------------------
    before = running()
    optional_total = subsumed_total = 0.0
    for line in lines:
        lst = line.item.irdai_list
        if lst == "I":
            if terms.consumables_cover:
                line.reasons.append("Optional item (List I) covered by your consumables add-on")
            else:
                optional_total += line.payable
                line.cut(line.payable, "IRDAI List I optional item: not paid by your policy")
        elif lst in ("II", "III", "IV"):
            subsumed_total += line.payable
            line.cut(line.payable, f"IRDAI List {lst}: should be part of room/procedure/treatment charges")
    removed = before - running()
    if removed > 0:
        steps.append(Step(name="Items insurers do not pay separately",
                          detail=(f"{rupees(optional_total)} optional items (List I) and "
                                  f"{rupees(subsumed_total)} items that belong inside other charges (Lists II-IV)"),
                          deducted=round(removed, 2), running_total=round(running(), 2), rule_ids=["LIST-01"]))
    if optional_total > 0:
        issues.append(Issue(level="info", code="consumables_addon",
                            message=(f"{rupees(optional_total)} of optional items is not covered. A consumables "
                                     "add-on would usually cover List I items."), rule_ids=["LIST-01"]))
    if subsumed_total > 0:
        issues.append(Issue(level="warn", code="subsumed_items",
                            message=(f"The hospital billed {rupees(subsumed_total)} for items that should be inside "
                                     "room, procedure or treatment charges. Ask the hospital to remove them."),
                            rule_ids=["LIST-01"]))

    # 3. Room rent and proportionate deduction --------------------------------
    room_lines = [l for l in lines if l.item.category == BillCategory.room_rent and l.payable > 0]
    room_total = sum(l.payable for l in room_lines)
    actual_per_day = eligible = None
    ratio = None
    if room_total > 0:
        if claim.room_days <= 0:
            issues.append(Issue(level="warn", code="room_days_missing",
                                message="Room rent is billed but the number of room days is 0. Enter the days."))
        else:
            actual_per_day = room_total / claim.room_days
    if terms.room_rent_waiver:
        if room_total > 0:
            issues.append(Issue(level="info", code="room_waiver",
                                message="Your room-rent waiver add-on removes the room-rent limit."))
    else:
        eligible = per_day_limit(terms.room_rent, terms.sum_insured, claim.eligible_category_rent_per_day)
        if terms.room_rent.kind == "category" and eligible is None and room_total > 0:
            issues.append(Issue(level="warn", code="category_rent_needed",
                                message=(f"Your room limit is a category ('{terms.room_rent.category or 'room category'}'). "
                                         "Enter the hospital's daily rent for that category to check for a proportionate cut.")))

    if eligible is not None and actual_per_day is not None and actual_per_day > eligible:
        ratio = eligible / actual_per_day
        before = running()
        for l in room_lines:
            l.cut(l.payable * (1 - ratio),
                  f"Room rent above your limit of {rupees(eligible)}/day (you chose {rupees(actual_per_day)}/day)")
        steps.append(Step(name="Room rent limit",
                          detail=f"Eligible {rupees(eligible)}/day x {claim.room_days} days; room chosen {rupees(actual_per_day)}/day",
                          deducted=round(before - running(), 2), running_total=round(running(), 2)))
        if claim.hospital_differential_billing:
            before = running()
            for l in lines:
                if l.item.category in ASSOCIATE and l.payable > 0:
                    l.cut(l.payable * (1 - ratio),
                          f"Proportionate cut: only {ratio:.1%} paid because the room was above your limit")
            steps.append(Step(name="Proportionate deduction",
                              detail=(f"Nursing, doctor and OT charges paid at {ratio:.1%}. Not applied to ICU, "
                                      "medicines, consumables, implants or tests."),
                              deducted=round(before - running(), 2), running_total=round(running(), 2),
                              rule_ids=["PROP-01", "PROP-02"]))
        else:
            steps.append(Step(name="Proportionate deduction",
                              detail="Not applied: the hospital does not bill differently by room category.",
                              running_total=round(running(), 2), rule_ids=["PROP-03"]))

    # 4. ICU limit ------------------------------------------------------------
    icu_lines = [l for l in lines if l.item.category == BillCategory.icu and l.payable > 0]
    icu_total = sum(l.payable for l in icu_lines)
    if icu_total > 0:
        if claim.icu_days <= 0:
            issues.append(Issue(level="warn", code="icu_days_missing",
                                message="ICU charges are billed but ICU days is 0. Enter the days."))
        else:
            icu_cap = per_day_limit(terms.icu_limit, terms.sum_insured)
            if icu_cap is not None and icu_total / claim.icu_days > icu_cap:
                allowed = icu_cap * claim.icu_days
                share = allowed / icu_total
                before = running()
                for l in icu_lines:
                    l.cut(l.payable * (1 - share), f"ICU limit {rupees(icu_cap)}/day")
                steps.append(Step(name="ICU limit",
                                  detail=f"ICU paid up to {rupees(icu_cap)}/day x {claim.icu_days} days (no proportionate cut on other charges)",
                                  deducted=round(before - running(), 2), running_total=round(running(), 2),
                                  rule_ids=["PROP-02"]))

    # Claim-level steps start here
    payable = running()

    # 5. Sub-limit --------------------------------------------------------------
    if claim.diagnosis:
        caps = []
        for sub in terms.sub_limits:
            if matching_terms(claim.diagnosis, sub.keywords or [sub.name]):
                cap = sub_limit_cap(sub, terms.sum_insured)
                if cap is not None:
                    caps.append((cap, sub.name))
        if caps:
            cap, name = min(caps)
            if payable > cap:
                cut = payable - cap
                payable = cap
                steps.append(Step(name=f"Sub-limit: {name}", detail=f"This treatment is capped at {rupees(cap)}",
                                  deducted=round(cut, 2), running_total=round(payable, 2)))

    # 6. Deductible and co-pay --------------------------------------------------
    deductible = terms.deductible
    if terms.policy_kind == "super_top_up":
        deductible = max(0.0, deductible - claim.deductible_already_met)

    copay_applies = terms.copay_percent > 0
    if copay_applies and terms.copay_min_age is not None:
        if claim.patient_age is None:
            issues.append(Issue(level="warn", code="age_needed",
                                message=f"Co-pay of {terms.copay_percent:g}% applies from age {terms.copay_min_age}. Enter the patient's age; it is applied for now."))
        elif claim.patient_age < terms.copay_min_age:
            copay_applies = False

    def apply_deductible(amount: float) -> float:
        if deductible <= 0:
            return amount
        cut = min(amount, deductible)
        steps.append(Step(name="Deductible", detail=f"You bear the first {rupees(deductible)}",
                          deducted=round(cut, 2), running_total=round(amount - cut, 2)))
        return amount - cut

    def apply_copay(amount: float) -> float:
        if not copay_applies:
            return amount
        cut = amount * terms.copay_percent / 100
        steps.append(Step(name="Co-pay", detail=f"You pay {terms.copay_percent:g}% of the admissible amount",
                          deducted=round(cut, 2), running_total=round(amount - cut, 2)))
        return amount - cut

    if terms.deductible_before_copay:
        payable = apply_copay(apply_deductible(payable))
    else:
        payable = apply_deductible(apply_copay(payable))

    # 7. Sum insured cap ----------------------------------------------------------
    available = max(0.0, terms.sum_insured + terms.cumulative_bonus_amount - claim.si_already_used)
    if payable > available:
        cut = payable - available
        payable = available
        steps.append(Step(name="Sum insured limit",
                          detail=f"Only {rupees(available)} of cover is left this year",
                          deducted=round(cut, 2), running_total=round(payable, 2)))

    payable = round(payable, 2)
    insurer_pays = 0.0 if blocked else payable
    return ClaimResult(
        total_billed=round(total_billed, 2),
        insurer_pays=insurer_pays,
        you_pay=round(total_billed - insurer_pays, 2),
        payable_if_covered=payable,
        blocked=blocked,
        proportion_applied=round(ratio, 4) if ratio is not None else None,
        eligible_room_rent_per_day=round(eligible, 2) if eligible is not None else None,
        actual_room_rent_per_day=round(actual_per_day, 2) if actual_per_day is not None else None,
        items=[l.result() for l in lines],
        steps=steps,
        issues=issues,
        waiting=waiting,
    )

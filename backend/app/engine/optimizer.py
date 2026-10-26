"""Several policies, one hospital bill: which order to claim in.

Each policy's admissible amount A on the whole bill is worked out by the claim
calculator under its own terms. Policies are then claimed in order. The amount still
unpaid (above a policy's deductible) is claimed under the next policy, which settles
it under its own terms, i.e. pays its share A/bill of it, never more than A minus its
deductible, nor more than the cover it has left (IRDAI: the disallowed amount can be
claimed under another policy). Every order is tried (at most 5! = 120) and ranked by
your out-of-pocket cost, then the bonus you lose.
"""

from itertools import permutations

from app.engine.calculator import calculate_claim, rupees
from app.models import ClaimInput, OptimizeInput, OptimizeResult, OrderResult, PolicyForClaim, PolicyPayout


def _admissible(p: PolicyForClaim, claim: ClaimInput) -> float:
    """What this policy would pay on the whole bill, before its deductible and cover limit."""
    terms = p.terms.model_copy(update={"deductible": 0.0, "cumulative_bonus_amount": 1e12})
    result = calculate_claim(terms, claim.model_copy(update={"si_already_used": 0.0, "deductible_already_met": 0.0}))
    return 0.0 if result.blocked else result.payable_if_covered


def _deductible(p: PolicyForClaim) -> float:
    if p.terms.policy_kind == "super_top_up":
        return max(0.0, p.terms.deductible - p.deductible_already_met)
    return p.terms.deductible


def _cover_left(p: PolicyForClaim) -> float:
    return max(0.0, p.terms.sum_insured + p.terms.cumulative_bonus_amount - p.si_already_used)


def _run(order: tuple[PolicyForClaim, ...], admissible: dict[str, float], total: float) -> OrderResult:
    paid = 0.0
    payouts = []
    for p in order:
        full = admissible[p.label]
        deductible = _deductible(p)
        unpaid_above_deductible = total - max(paid, deductible)
        share = full / total if total > 0 else 0.0
        pays = max(0.0, min(full - deductible, unpaid_above_deductible * share, _cover_left(p), total - paid))
        paid += pays
        lost = p.terms.no_claim_bonus_at_risk if pays > 0 and p.terms.policy_kind != "group" else 0.0
        payouts.append(PolicyPayout(label=p.label, pays=round(pays, 2), bonus_lost=lost))
    return OrderResult(order=[p.label for p in order], payouts=payouts, total_paid=round(paid, 2),
                       out_of_pocket=round(total - paid, 2), bonus_lost=sum(x.bonus_lost for x in payouts))


def optimize(inp: OptimizeInput) -> OptimizeResult:
    labels = [p.label for p in inp.policies]
    if len(set(labels)) != len(labels):
        raise ValueError("Give each policy a different name.")
    total = sum(i.amount for i in inp.claim.items)
    admissible = {p.label: _admissible(p, inp.claim) for p in inp.policies}

    by_label = {p.label: p for p in inp.policies}

    def rank(r: OrderResult) -> tuple[float, float, int, float]:
        # Tie-breaks: employer (group) policies first, as they usually carry no bonus to protect;
        # then base policies before top-ups, the order in which claims are normally filed.
        groups_first = sum(i for i, label in enumerate(r.order) if by_label[label].terms.policy_kind == "group")
        top_ups_last = -sum(i * _deductible(by_label[label]) for i, label in enumerate(r.order))
        return (r.out_of_pocket, r.bonus_lost, groups_first, top_ups_last)

    results = sorted((_run(order, admissible, total) for order in permutations(inp.policies)), key=rank)
    best, worst = results[0], results[-1]

    used = [x for x in best.payouts if x.pays > 0]
    explanation = []
    if not used:
        explanation.append("None of these policies is likely to pay this bill (check waiting periods and terms).")
    else:
        steps = ", then ".join(f"{x.label} ({rupees(x.pays)})" for x in used)
        explanation.append(f"Claim {steps}.")
        explanation.append(f"You pay {rupees(best.out_of_pocket)} of the {rupees(total)} bill.")
        if best.bonus_lost:
            explanation.append(f"You lose about {rupees(best.bonus_lost)} of no-claim bonus.")
        else:
            explanation.append("No no-claim bonus is lost.")
    if worst.out_of_pocket > best.out_of_pocket or worst.bonus_lost > best.bonus_lost:
        explanation.append(
            f"The worst order ({' then '.join(worst.order)}) would cost you {rupees(worst.out_of_pocket - best.out_of_pocket)} "
            f"more and lose {rupees(max(0.0, worst.bonus_lost - best.bonus_lost))} more bonus.")
    explanation.append("Each insurer settles under its own terms; together they never pay more than the bill.")
    return OptimizeResult(total_billed=round(total, 2), best=best, all_orders=results, explanation=explanation,
                          rule_ids=["MULTI-01"])

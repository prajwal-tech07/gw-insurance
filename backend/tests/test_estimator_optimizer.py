from datetime import date

import pytest

from app.engine.estimator import estimate
from app.engine.optimizer import optimize
from app.models import BillItem, EstimateInput, OptimizeInput, PolicyForClaim, RoomLimit, RoomOption

from factories import claim, policy

OTHER_COSTS = [
    BillItem(description="Nursing charges", amount=6_000),
    BillItem(description="Surgeon fees", amount=50_000),
    BillItem(description="OT charges", amount=20_000),
    BillItem(description="Pharmacy charges", amount=30_000),
    BillItem(description="Lab investigations", amount=10_000),
    BillItem(description="Gloves sterile", amount=500),
]


def test_estimator_recommends_room_within_limit_and_explains_proportionate_cost():
    inp = EstimateInput(terms=policy(), admission_date=date(2026, 9, 10), patient_age=45, diagnosis="appendicitis",
                        room_days=3, items=OTHER_COSTS,
                        room_options=[RoomOption(name="Single AC", rent_per_day=6_000),
                                      RoomOption(name="Twin sharing", rent_per_day=4_500)])
    r = estimate(inp)
    assert r.recommended == "Twin sharing"
    single = next(o for o in r.options if o.option.name == "Single AC").result
    twin = next(o for o in r.options if o.option.name == "Twin sharing").result
    assert twin.you_pay == 500  # only the List I gloves
    # Single AC: 4,500 extra rent but you pay far more because of the proportionate cut.
    assert single.you_pay == pytest.approx(16_166.67, abs=0.01)
    assert "not just the Rs 4,500 extra rent" in r.recommendation
    assert r.eligible_room_rent_per_day == 5_000
    assert any("Rs 5,000 per day" in q for q in r.questions)
    assert any(i.description == "Gloves sterile" for i in r.items_you_pay)


def test_estimator_flags_waiting_period():
    inp = EstimateInput(terms=policy(first_inception_date=date(2025, 10, 1)), admission_date=date(2026, 9, 10),
                        diagnosis="hernia repair", room_days=2, items=OTHER_COSTS,
                        room_options=[RoomOption(name="General ward", rent_per_day=2_000)])
    r = estimate(inp)
    assert r.options[0].result.blocked
    assert "likely to be rejected" in r.recommendation
    assert any("hernia" in w for w in r.warnings)


def test_estimator_uses_category_tariff_for_category_limits():
    terms = policy(room_rent=RoomLimit(kind="category", category="single private room"))
    inp = EstimateInput(terms=terms, admission_date=date(2026, 9, 10), room_days=3, items=OTHER_COSTS,
                        room_options=[RoomOption(name="Single private AC", rent_per_day=5_000),
                                      RoomOption(name="Deluxe suite", rent_per_day=10_000)])
    r = estimate(inp)
    deluxe = next(o for o in r.options if o.option.name == "Deluxe suite").result
    assert deluxe.proportion_applied == 0.5
    assert r.recommended == "Single private AC"


def test_optimizer_claims_group_policy_first_to_protect_bonus():
    group = PolicyForClaim(label="Company policy", terms=policy(policy_kind="group", sum_insured=300_000,
                                                                  room_rent=RoomLimit()))
    personal = PolicyForClaim(label="Personal policy", terms=policy(sum_insured=500_000, room_rent=RoomLimit(),
                                                                     no_claim_bonus_at_risk=50_000))
    items = [BillItem(description="Surgery charges", amount=350_000)]
    r = optimize(OptimizeInput(policies=[personal, group], claim=claim(items=items, room_days=0)))
    assert r.best.order == ["Company policy", "Personal policy"]
    assert [p.pays for p in r.best.payouts] == [300_000, 50_000]
    assert r.best.out_of_pocket == 0
    assert r.best.bonus_lost == 50_000
    personal_only = next(o for o in r.all_orders if o.order[0] == "Personal policy")
    assert personal_only.payouts[0].pays == 350_000 and personal_only.bonus_lost == 50_000


def test_optimizer_super_top_up_deductible_met_by_base_policy():
    base = PolicyForClaim(label="Base", terms=policy(sum_insured=300_000, room_rent=RoomLimit()))
    stu = PolicyForClaim(label="Super top-up", terms=policy(policy_kind="super_top_up", sum_insured=1_000_000,
                                                             deductible=300_000, room_rent=RoomLimit()))
    items = [BillItem(description="Surgery charges", amount=700_000)]
    r = optimize(OptimizeInput(policies=[stu, base], claim=claim(items=items, room_days=0)))
    assert r.best.order == ["Base", "Super top-up"]
    assert [p.pays for p in r.best.payouts] == [300_000, 400_000]
    assert r.best.out_of_pocket == 0
    reverse = next(o for o in r.all_orders if o.order[0] == "Super top-up")
    assert reverse.out_of_pocket == 0  # top-up pays above 3L, base covers the first 3L


def test_optimizer_second_policy_pays_disallowed_amount_under_its_own_terms():
    # Policy A has a room-rent limit (pays 118,333.33 of 134,800). Policy B has no room limit
    # but a 10% co-pay, so it settles the unpaid 16,466.67 at 90% of its own admissible share.
    a = PolicyForClaim(label="A", terms=policy())
    b = PolicyForClaim(label="B", terms=policy(room_rent=RoomLimit(), copay_percent=10))
    r = optimize(OptimizeInput(policies=[a, b], claim=claim()))
    ab = next(o for o in r.all_orders if o.order == ["A", "B"])
    b_share = (134_800 - 800) * 0.9 / 134_800  # B skips the 800 of List I/II items, then 10% co-pay
    assert ab.payouts[0].pays == pytest.approx(118_333.33, abs=0.01)
    assert ab.payouts[1].pays == pytest.approx(16_466.67 * b_share, abs=0.01)
    assert ab.total_paid <= 134_800


def test_optimizer_rejects_duplicate_names():
    p = PolicyForClaim(label="Same", terms=policy())
    with pytest.raises(ValueError):
        optimize(OptimizeInput(policies=[p, p], claim=claim()))

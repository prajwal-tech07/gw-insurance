from datetime import date

import pytest

from app.engine.calculator import calculate_claim
from app.models import BillItem, RoomLimit

from factories import claim, policy

BILL_TOTAL = 134_800


def test_hand_worked_example():
    # Room limit 1% of 5L = 5,000/day; chosen 6,000/day -> ratio 5/6.
    # Room 18,000 -> 15,000; nursing 6,000 -> 5,000; surgeon 50,000 -> 41,666.67; OT 20,000 -> 16,666.67
    # Pharmacy 30,000 and lab 10,000 untouched; gloves (List I) and admission kit (List II) removed.
    r = calculate_claim(policy(), claim())
    assert r.total_billed == BILL_TOTAL
    assert r.insurer_pays == pytest.approx(118_333.33, abs=0.01)
    assert r.you_pay == pytest.approx(16_466.67, abs=0.01)
    assert r.proportion_applied == pytest.approx(5 / 6, abs=1e-4)
    assert r.eligible_room_rent_per_day == 5_000
    assert r.actual_room_rent_per_day == 6_000
    assert not r.blocked
    by_desc = {i.description: i for i in r.items}
    assert by_desc["Pharmacy charges"].payable == 30_000  # PROP-01: no cut on medicines
    assert by_desc["Lab investigations"].payable == 10_000  # PROP-01: no cut on tests
    assert by_desc["Gloves sterile"].payable == 0
    assert by_desc["Admission kit"].irdai_list == "II"
    step_names = [s.name for s in r.steps]
    assert step_names == ["Items insurers do not pay separately", "Room rent limit", "Proportionate deduction"]
    assert sum(s.deducted for s in r.steps) == pytest.approx(r.you_pay, abs=0.02)


def test_room_within_limit_has_no_proportionate_cut():
    items = claim().items
    items[0] = BillItem(description="Room rent single AC", amount=15_000)  # exactly 5,000/day
    r = calculate_claim(policy(), claim(items=items))
    assert r.proportion_applied is None
    assert r.insurer_pays == 15_000 + 6_000 + 50_000 + 20_000 + 30_000 + 10_000


def test_no_differential_billing_means_only_room_rent_is_cut():
    r = calculate_claim(policy(), claim(hospital_differential_billing=False))
    assert r.insurer_pays == 15_000 + 6_000 + 50_000 + 20_000 + 30_000 + 10_000
    assert any("PROP-03" in s.rule_ids for s in r.steps)


def test_copay_for_senior_citizens_only():
    terms = policy(copay_percent=10, copay_min_age=60)
    assert calculate_claim(terms, claim(patient_age=45)).insurer_pays == pytest.approx(118_333.33, abs=0.01)
    senior = calculate_claim(terms, claim(patient_age=65))
    assert senior.insurer_pays == pytest.approx(106_500.00, abs=0.01)


def test_icu_limit_caps_icu_without_touching_other_charges():
    items = [
        BillItem(description="Room rent", amount=10_000),  # 2 days x 5,000: within limit
        BillItem(description="ICU charges", amount=36_000),  # 3 days x 12,000 > 10,000 cap
        BillItem(description="Nursing charges", amount=4_000),
    ]
    r = calculate_claim(policy(), claim(items=items, room_days=2, icu_days=3))
    assert r.insurer_pays == 10_000 + 30_000 + 4_000
    assert any(s.name == "ICU limit" for s in r.steps)


def test_initial_waiting_period_blocks_illness_but_not_accident():
    terms = policy(first_inception_date=date(2026, 9, 1))
    ill = calculate_claim(terms, claim())
    assert ill.blocked and ill.insurer_pays == 0
    assert ill.payable_if_covered == pytest.approx(118_333.33, abs=0.01)
    assert ill.you_pay == BILL_TOTAL
    accident = calculate_claim(terms, claim(is_accident=True, diagnosis="fracture after fall"))
    assert not accident.blocked


def test_cataract_sub_limit():
    items = [BillItem(description="Cataract surgery package OT charges", amount=60_000)]
    r = calculate_claim(policy(), claim(items=items, diagnosis="Cataract right eye", room_days=0))
    assert r.insurer_pays == 40_000
    assert any(s.name == "Sub-limit: Cataract" for s in r.steps)


def test_consumables_addon_pays_list_one_items_only():
    r = calculate_claim(policy(consumables_cover=True), claim())
    by_desc = {i.description: i for i in r.items}
    assert by_desc["Gloves sterile"].payable == 500
    assert by_desc["Admission kit"].payable == 0  # List II stays unpaid
    assert r.insurer_pays == pytest.approx(118_833.33, abs=0.01)


def test_room_rent_waiver_removes_limit():
    r = calculate_claim(policy(room_rent_waiver=True), claim())
    assert r.proportion_applied is None
    assert r.insurer_pays == 18_000 + 6_000 + 50_000 + 20_000 + 30_000 + 10_000


def test_super_top_up_deductible_counts_bills_already_borne():
    terms = policy(policy_kind="super_top_up", deductible=300_000, room_rent=RoomLimit())
    items = [BillItem(description="Surgery charges", amount=250_000)]
    r = calculate_claim(terms, claim(items=items, room_days=0, deductible_already_met=100_000))
    assert r.insurer_pays == 50_000


def test_sum_insured_cap_uses_cover_left():
    terms = policy(sum_insured=100_000, room_rent=RoomLimit())
    items = [BillItem(description="Surgery charges", amount=130_000)]
    r = calculate_claim(terms, claim(items=items, room_days=0, si_already_used=20_000))
    assert r.insurer_pays == 80_000


def test_cumulative_bonus_adds_to_cover():
    terms = policy(sum_insured=100_000, cumulative_bonus_amount=25_000, room_rent=RoomLimit())
    items = [BillItem(description="Surgery charges", amount=130_000)]
    assert calculate_claim(terms, claim(items=items, room_days=0)).insurer_pays == 125_000


def test_deductible_and_copay_order_is_per_policy():
    items = [BillItem(description="Surgery charges", amount=100_000)]
    c = claim(items=items, room_days=0)
    first_ded = policy(room_rent=RoomLimit(), deductible=10_000, copay_percent=20, deductible_before_copay=True)
    first_copay = policy(room_rent=RoomLimit(), deductible=10_000, copay_percent=20, deductible_before_copay=False)
    assert calculate_claim(first_ded, c).insurer_pays == 72_000  # (100k - 10k) * 0.8
    assert calculate_claim(first_copay, c).insurer_pays == 70_000  # 100k * 0.8 - 10k


def test_category_room_limit_needs_hospital_tariff():
    terms = policy(room_rent=RoomLimit(kind="category", category="single private room"))
    r = calculate_claim(terms, claim())
    assert any(i.code == "category_rent_needed" for i in r.issues)
    r2 = calculate_claim(terms, claim(eligible_category_rent_per_day=5_000))
    assert r2.insurer_pays == pytest.approx(118_333.33, abs=0.01)


def test_missing_sum_insured_blocks():
    r = calculate_claim(policy(sum_insured=0), claim())
    assert r.blocked and any(i.code == "no_sum_insured" for i in r.issues)


def test_possible_exclusion_warns():
    terms = policy(exclusions=["Obesity / weight control treatment"])
    r = calculate_claim(terms, claim(diagnosis="Bariatric surgery for morbid obesity"))
    assert any(i.code == "possible_exclusion" for i in r.issues)

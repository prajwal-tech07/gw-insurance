"""Shared test fixtures: a typical policy and the hand-worked example bill."""

from datetime import date

from app.models import BillItem, ClaimInput, PolicyTerms, RoomLimit, SubLimit, WaitingPeriods


def policy(**overrides) -> PolicyTerms:
    base = dict(
        policy_name="Test Health Policy",
        insurer="Test Insurer",
        sum_insured=500_000,
        room_rent=RoomLimit(kind="percent_of_si", percent=1),  # Rs 5,000/day
        icu_limit=RoomLimit(kind="percent_of_si", percent=2),  # Rs 10,000/day
        waiting=WaitingPeriods(initial_days=30, pre_existing_months=36, specific_disease_months=24,
                               specific_diseases=["cataract", "hernia", "knee replacement"], maternity_months=24),
        sub_limits=[SubLimit(name="Cataract", keywords=["cataract"], amount=40_000)],
        first_inception_date=date(2022, 4, 1),
    )
    base.update(overrides)
    return PolicyTerms(**base)


def example_items() -> list[BillItem]:
    return [
        BillItem(description="Room rent single AC", amount=18_000),  # Rs 6,000/day x 3
        BillItem(description="Nursing charges", amount=6_000),
        BillItem(description="Surgeon fees", amount=50_000),
        BillItem(description="OT charges", amount=20_000),
        BillItem(description="Pharmacy charges", amount=30_000),
        BillItem(description="Lab investigations", amount=10_000),
        BillItem(description="Gloves sterile", amount=500),  # List I
        BillItem(description="Admission kit", amount=300),  # List II
    ]


def claim(**overrides) -> ClaimInput:
    base = dict(admission_date=date(2026, 9, 10), patient_age=45, diagnosis="appendicitis",
                room_days=3, items=example_items())
    base.update(overrides)
    return ClaimInput(**base)

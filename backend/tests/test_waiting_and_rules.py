from datetime import date

from app.engine.dates import add_months, months_between
from app.engine.waiting import check_waiting
from app.rules import all_rules, get_rule, rule_for

from factories import policy


def by_name(statuses, prefix):
    return next(s for s in statuses if s.name.startswith(prefix))


def test_month_helpers():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2022, 4, 1), 36) == date(2025, 4, 1)
    assert months_between(date(2022, 4, 1), date(2027, 4, 1)) == 60
    assert months_between(date(2022, 4, 15), date(2027, 4, 14)) == 59


def test_pre_existing_blocked_inside_waiting_period():
    terms = policy(first_inception_date=date(2025, 1, 1))
    s = by_name(check_waiting(terms, date(2026, 6, 1), "diabetes", is_pre_existing=True), "Pre-existing")
    assert s.status == "blocked" and s.covered_from == date(2028, 1, 1)


def test_pre_existing_unknown_flags_risk_instead_of_blocking():
    terms = policy(first_inception_date=date(2025, 1, 1))
    s = by_name(check_waiting(terms, date(2026, 6, 1), "diabetes", is_pre_existing=None), "Pre-existing")
    assert s.status == "unknown"


def test_specific_disease_matched_from_diagnosis():
    terms = policy(first_inception_date=date(2025, 6, 1))
    s = by_name(check_waiting(terms, date(2026, 6, 1), "Inguinal hernia repair"), "Specific disease")
    assert s.status == "blocked" and "hernia" in s.name
    other = by_name(check_waiting(terms, date(2026, 6, 1), "dengue fever"), "Specific disease")
    assert other.status == "not_applicable"


def test_maternity_waiting():
    terms = policy(first_inception_date=date(2025, 6, 1))
    s = by_name(check_waiting(terms, date(2026, 6, 1), "Normal delivery"), "Maternity")
    assert s.status == "blocked"


def test_moratorium_uses_rule_in_force_on_admission_date():
    terms = policy(first_inception_date=date(2018, 1, 1))
    before = by_name(check_waiting(terms, date(2024, 3, 1), "x"), "Moratorium")
    after = by_name(check_waiting(terms, date(2024, 4, 1), "x"), "Moratorium")
    assert before.rule_ids == ["MORA-96"] and before.status == "not_applicable"  # 74 months < 96
    assert after.rule_ids == ["MORA-60"] and after.status == "ok"  # 75 months >= 60


def test_ped_cap_note_when_policy_exceeds_irdai_cap():
    terms = policy(waiting=policy().waiting.model_copy(update={"pre_existing_months": 48}),
                   period_start=date(2025, 4, 1))
    s = by_name(check_waiting(terms, date(2026, 6, 1), "x", is_pre_existing=True), "Pre-existing")
    assert "PED-36" in s.rule_ids and "36 months" in s.explanation


def test_rule_versions_switch_on_their_dates():
    assert rule_for("moratorium", date(2024, 3, 31)).months == 96
    assert rule_for("moratorium", date(2024, 4, 1)).months == 60
    assert rule_for("ombudsman_cap", date(2023, 11, 9)).amount == 3_000_000
    assert rule_for("ombudsman_cap", date(2023, 11, 10)).amount == 5_000_000
    assert rule_for("cashless_timelines", date(2024, 7, 1)) is None


def test_every_rule_has_a_source_and_unique_id():
    rules = all_rules()
    assert len({r.id for r in rules}) == len(rules)
    for r in rules:
        assert r.source.url.startswith("https://")
        assert r.plain and r.title
    assert get_rule("LIST-01").status == "in_force"

import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.extraction.bills import parse_bill_csv, parse_bill_text
from app.extraction.documents import pdf_pages
from app.extraction.heuristic import find_icu, find_room_rent, find_sub_limits, find_copay
from app.extraction.llm import ai_extract, parse_ai_value
from app.extraction.parsing import inr, parse_amount, parse_date, parse_duration_months
from app.extraction.service import extract_policy, find_quote
from app.samples import DEMO_POLICY_PAGES, SAMPLE_BILL, demo_policy_pdf


@pytest.fixture(scope="module")
def demo_pages():
    pages, warnings = pdf_pages(demo_policy_pdf())
    assert warnings == []
    return pages


@pytest.fixture(scope="module")
def demo_result(demo_pages):
    return extract_policy(demo_pages, use_ai=False)


def test_parsers():
    assert parse_amount("Rs. 5,00,000") == 500_000
    assert parse_amount("₹ 5 lakh") == 500_000
    assert parse_amount("INR 1.5 crore") == 15_000_000
    assert parse_duration_months("thirty six (36) months") == 36
    assert parse_duration_months("two years of continuous cover") == 24
    assert parse_date("01/04/2022") == date(2022, 4, 1)
    assert parse_date("1st April, 2022") == date(2022, 4, 1)
    assert parse_date("01-Apr-2022") == date(2022, 4, 1)
    assert inr(500000) == "Rs 5,00,000" and inr(1234567) == "Rs 12,34,567"


def test_demo_policy_terms(demo_result):
    t = demo_result.terms
    assert demo_result.method == "rules"
    assert t.insurer == "Suraksha Sample General Insurance Co. Ltd."
    assert t.policy_name == "Family Health Shield (Sample)"
    assert t.policy_kind == "individual"
    assert t.sum_insured == 500_000
    assert (t.room_rent.kind, t.room_rent.percent, t.room_rent.amount) == ("percent_of_si", 1.0, 5000)
    assert (t.icu_limit.kind, t.icu_limit.percent, t.icu_limit.amount) == ("percent_of_si", 2.0, None)
    assert (t.copay_percent, t.copay_min_age) == (10.0, 60)
    assert t.deductible == 0
    assert t.cumulative_bonus_amount == 50_000
    assert t.waiting.initial_days == 30
    assert t.waiting.pre_existing_months == 36
    assert t.waiting.specific_disease_months == 24
    assert t.waiting.maternity_months == 24
    assert {"cataract", "hernia", "knee replacement", "prostat"} <= set(t.waiting.specific_diseases)
    assert {s.name: s.amount for s in t.sub_limits} == {"Cataract": 40_000, "Knee replacement": 150_000}
    assert t.consumables_cover is False and t.room_rent_waiver is False
    assert len(t.exclusions) >= 14 and "Obesity/ Weight Control" in t.exclusions
    assert "30-day waiting period" in t.exclusions
    assert t.first_inception_date == date(2022, 4, 1)
    assert (t.period_start, t.period_end) == (date(2026, 4, 1), date(2027, 3, 31))
    assert (t.pre_hospitalisation_days, t.post_hospitalisation_days) == (30, 60)


def test_every_found_field_cites_a_page(demo_result):
    fields = {f.key: f for f in demo_result.fields}
    assert fields["room_rent"].citation.page == 2
    assert "1% of Sum Insured" in fields["room_rent"].citation.quote
    assert fields["sum_insured"].citation.page == 1
    for f in demo_result.fields:
        if f.source != "not_found":
            assert f.citation and f.citation.quote


IRDAI_STANDARD_WORDING = [(1, (
    "Room Rent, Boarding, Nursing Expenses all inclusive as provided by the Hospital / Nursing Home up to 2% of "
    "the sum insured subject to maximum of Rs. 5,000/- per day. Intensive Care Unit (ICU) charges / Intensive "
    "Cardiac Care Unit (ICCU) charges all inclusive as provided by the Hospital / Nursing Home up to 5% of the sum "
    "insured subject to maximum of Rs. 10,000/- per day. Cataract Treatment: The Company shall indemnify medical "
    "expenses incurred for treatment of Cataract, subject to a limit of 25% of Sum Insured or INR 40,000/- per eye, "
    "whichever is lower, per each eye in one policy period. Co-payment: Each and every claim under the Policy shall "
    "be subject to a Co-payment of 5% applicable to claim amount admissible and payable."))]


def test_irdai_standard_wording():
    room = find_room_rent(IRDAI_STANDARD_WORDING).value
    icu = find_icu(IRDAI_STANDARD_WORDING).value
    assert (room.percent, room.amount) == (2.0, 5000)
    assert (icu.percent, icu.amount) == (5.0, 10000)
    sub = find_sub_limits(IRDAI_STANDARD_WORDING).value[0]
    assert (sub.name, sub.amount, sub.percent_of_si) == ("Cataract", 40_000, 25.0)
    assert find_copay(IRDAI_STANDARD_WORDING).value == (5.0, None)


def test_bill_text_parsing_skips_totals_and_headers():
    items, skipped = parse_bill_text(SAMPLE_BILL)
    assert len(items) == 13
    assert sum(i.amount for i in items) == 153_900
    assert items[0].description == "Room Rent - Single AC Room" and items[0].amount == 18_000
    assert any("Gross Total" in s for s in skipped)
    assert all("Tab" not in s for s in skipped)


def test_bill_text_keeps_medicine_strengths():
    items, _ = parse_bill_text("TAB PAN 40   120.00\nINJ CEFTRIAXONE 1GM  2  450.00  900.00")
    assert [(i.description, i.amount) for i in items] == [("TAB PAN 40", 120.0), ("INJ CEFTRIAXONE 1GM", 900.0)]


def test_bill_csv():
    items, _ = parse_bill_csv("Description,Amount,Category\nRoom rent,5000,room_rent\nMedicines,2000,\nTotal,7000,\n")
    assert [(i.description, i.amount, i.category) for i in items] == [
        ("Room rent", 5000, "room_rent"), ("Medicines", 2000, None)]


# ---------------------------------------------------------------- AI path, with a fake client

def _fake_client(payload):
    response = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(payload))])
    create = lambda **kwargs: response  # noqa: E731
    return SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


def _empty_payload():
    from app.extraction.heuristic import FIELDS
    return {k: {"value": "", "page": 0, "quote": "", "confidence": 0} for k, _, _ in FIELDS}


def test_ai_values_are_verified_against_the_document(demo_pages):
    payload = _empty_payload()
    payload["sum_insured"] = {"value": "Rs 5,00,000", "page": 1, "quote": "Sum Insured: Rs. 5,00,000", "confidence": 0.95}
    payload["copay"] = {"value": "20% for all claims", "page": 2, "quote": "Co-payment of 20% on all claims", "confidence": 0.9}
    payload["deductible"] = {"value": "Rs 25,000", "page": 1, "quote": "Deductible: Rs 25,000 per claim", "confidence": 0.9}
    result = extract_policy(demo_pages, client=_fake_client(payload))
    fields = {f.key: f for f in result.fields}
    assert result.method == "ai+rules"
    assert fields["sum_insured"].source == "ai+rules" and not fields["sum_insured"].needs_review
    # The AI's co-pay quote is not in the document: the rule-based value is kept and flagged.
    assert fields["copay"].source == "rules" and fields["copay"].needs_review
    assert result.terms.copay_percent == 10
    # A made-up value with no matching quote is never trusted silently.
    assert fields["deductible"].needs_review and result.terms.deductible == 0


def test_ai_failure_falls_back_to_rules(demo_pages):
    def boom(**kwargs):
        raise RuntimeError("network down")
    client = SimpleNamespace(messages=SimpleNamespace(create=boom), beta=SimpleNamespace(messages=SimpleNamespace(create=boom)))
    fields, error = ai_extract(demo_pages, client)
    assert fields is None and error == "RuntimeError"
    result = extract_policy(demo_pages, client=client)
    assert result.method == "rules" and result.terms.sum_insured == 500_000
    assert any("AI reader not used" in w for w in result.warnings)


def test_ai_refusal_is_handled(demo_pages):
    response = SimpleNamespace(stop_reason="refusal", content=[])
    create = lambda **kwargs: response  # noqa: E731
    client = SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert ai_extract(demo_pages, client) == (None, "the model declined the request")


def test_parse_ai_values():
    assert parse_ai_value("room_rent", "1% of sum insured, max Rs 5,000 per day").value.amount == 5000
    assert parse_ai_value("copay", "10% for insured aged 60 and above").value == (10.0, 60)
    subs = parse_ai_value("sub_limits", "Cataract: 25% of SI or Rs 40,000 per eye; Hernia: Rs 50,000").value
    assert [(s.name, s.amount, s.percent_of_si) for s in subs] == [("Cataract", 40_000, 25.0), ("Hernia", 50_000, None)]
    assert parse_ai_value("policy_period", "01/04/2026 to 31/03/2027").value == (date(2026, 4, 1), date(2027, 3, 31))
    assert parse_ai_value("consumables_cover", "no").value is False


def test_find_quote_tolerates_spacing_but_not_inventions():
    assert find_quote(DEMO_POLICY_PAGES, 2, "up to 1%   of Sum Insured per day,") == 2
    assert find_quote(DEMO_POLICY_PAGES, 1, "Room Rent, Boarding and Nursing expenses up to 1%") == 2
    assert find_quote(DEMO_POLICY_PAGES, 1, "co-payment of 50% on every claim") is None

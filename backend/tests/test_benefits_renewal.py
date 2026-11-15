from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.engine.renewal import renewal_events, renewal_status, unused_benefits
from app.extraction.benefits import catalogue, find_benefits
from app.extraction.documents import pdf_pages
from app.extraction.heuristic import find_pre_post
from app.extraction.service import extract_policy, find_quote
from app.ics import Event, calendar
from app.main import app
from app.models import PolicyBenefit, RenewalInput
from app.samples import DEMO_POLICY_PAGES, demo_policy_pdf
from tests.factories import policy


@pytest.fixture(scope="module")
def demo_benefits():
    pages, _ = pdf_pages(demo_policy_pdf())
    return {b.key: b for b in extract_policy(pages, use_ai=False).terms.benefits}


# ---------------------------------------------------------------- benefits finder

def test_demo_policy_benefits(demo_benefits):
    b = demo_benefits
    assert {"health_checkup", "teleconsultation", "ayush", "day_care", "domiciliary", "restore", "ambulance",
            "pre_post", "opd"} <= set(b)
    assert b["health_checkup"].status == "covered" and b["health_checkup"].limit == "Rs 1,500 once every policy year"
    assert b["ambulance"].limit == "Rs 2,000 per hospitalisation"
    assert b["pre_post"].limit == "30 days before / 60 days after"
    assert b["opd"].status == "not_covered" and b["opd"].limit is None
    assert all(x.citation and x.citation.page == 2 for x in b.values())


def test_benefit_quotes_are_exact(demo_benefits):
    # Each quote must be findable in the document, like the policy terms' citations.
    for key, benefit in demo_benefits.items():
        if key == "pre_post":
            continue
        assert find_quote(DEMO_POLICY_PAGES, benefit.citation.page, benefit.citation.quote) == 2, key
    assert "Rs. 1,500" in demo_benefits["health_checkup"].citation.quote


def test_exclusion_context_and_definitions():
    pages = [
        (1, "SECTION 2 - DEFINITIONS\nDomiciliary hospitalisation means treatment at home.\n"
            "OPD treatment is the one in which the insured visits a clinic.\n"
            "SECTION 3 - COVERAGE\nAYUSH treatment is covered up to the sum insured, subject to the policy exclusions.\n"),
        (2, "SECTION 4 - EXCLUSIONS\n1. Out-patient treatment\n2. Health check-up costs\n"
            "SECTION 5 - OPTIONAL COVERS\nDaily hospital cash of Rs. 1,000 per day.\n"),
    ]
    found = {b.key: b for b in find_benefits(pages)}
    assert "domiciliary" not in found  # only defined, never granted
    assert found["ayush"].status == "covered"  # "subject to exclusions" is boilerplate, not an exclusion
    assert found["opd"].status == "not_covered" and found["opd"].citation.page == 2
    assert found["health_checkup"].status == "not_covered"
    assert found["hospital_cash"].status == "optional" and found["hospital_cash"].limit == "Rs 1,000 per day"


def test_running_headers_do_not_end_an_exclusion_list():
    header = "ACME HEALTH INSURANCE CO. LTD."
    pages = [(1, f"{header}\nPERMANENT EXCLUSIONS\n1. Cosmetic surgery\n"),
             (2, f"{header}\n2. Out-patient (OPD) treatment\n")]
    assert {b.key: b.status for b in find_benefits(pages)}["opd"] == "not_covered"


def test_conflicting_mentions_are_flagged():
    pages = [(1, "Teleconsultation is available free on our app."),
             (2, "Teleconsultation is not covered for insured persons above 80.")]
    tele = find_benefits(pages)[0]
    assert tele.status == "covered" and (tele.note or "").startswith("Page 2 also has a condition or exclusion")


# Patterns seen in real policy wordings (IFFCO-Tokio, ICICI Lombard, Niva Bupa), reduced to short cases.

def test_table_of_contents_and_passing_mentions_are_not_benefits():
    pages = [(1, "Preventive Health Check-up ............................ 12\nHospital Daily Cash ........ 14\n"),
             (2, "Travel or transportation expenses, other than ambulance service charges.\n"
                 "Surgeon fees (including consultation through telemedicine as per the guidelines).\n"
                 "Domiciliary Hospitalization means treatment at home. "
                 "The patient takes treatment at home on account of non-availability of room/bed in a hospital.\n"
                 "Each wellness point is valued at INR 0.25 and can be used for gym memberships.\n")]
    found = {b.key: b for b in find_benefits(pages)}
    assert set(found) == {"wellness"} and found["wellness"].limit is None  # "INR 0.25" is not a limit


def test_limit_belongs_to_the_benefit_the_sentence_is_about():
    pages = [(1, "Modern Treatment Methods: The following procedures will be covered either as in patient or as part "
                 "of Domiciliary Hospitalization or day care treatment up to 50% of the sum insured.")]
    found = {b.key: b for b in find_benefits(pages)}
    assert found["modern_treatment"].limit == "50% of sum insured"
    assert found["domiciliary"].limit is None and found["day_care"].limit is None


def test_negation_far_from_the_benefit_does_not_apply():
    sentence = ("Medical Second Opinion: This service may be obtained through electronic mode from an empaneled expert "
                "and is subject to the following conditions: it has to be requested by the insured, the opinion is given "
                "without examining the patient, and any liability for errors in it is not covered by us.")
    assert find_benefits([(1, sentence)])[0].status == "covered"


def test_minor_exclusion_heading_ends_at_the_next_numbered_clause():
    page = ("10. Emergency Assistance Services: we arrange evacuation.\nSpecific exclusions:\n"
            "a) Trips over 90 days, and any teleconsultation abroad\n"
            "11. Wellness Services: - This policy provides, at no additional cost, these services:\n"
            "(a) Cashless Telemedicine Consultation: Insured persons can book unlimited video consultations.\n")
    found = {b.key: b for b in find_benefits([(1, page)])}
    assert found["teleconsultation"].status == "covered" and found["wellness"].status == "covered"


def test_claim_deadline_is_not_the_post_hospitalisation_period():
    deadline = (1, "Send the bills (for post-hospitalisation expenses, within 30 days from the completion of the "
                   "post-hospitalisation period) to us.")
    assert find_pre_post([deadline]) is None
    cover = (2, "Post-hospitalisation medical expenses for 90 days after discharge are covered.")
    assert find_pre_post([deadline, cover]).value == (None, 90)


def test_wrapped_sentence_lines_are_not_headings():
    page = ("SECTION C - EXCLUSIONS\n1. Out-patient treatment\n"
            "part of post-bite treatment and as covered in the\n"
            "continuous coverage after the date of inception of\n"
            "2. Domiciliary hospitalisation\n")
    assert {b.key: b.status for b in find_benefits([(1, page)])} == {"opd": "not_covered", "domiciliary": "not_covered"}


def test_pre_policy_checkup_is_not_a_benefit():
    pages = [(1, "A pre-policy medical check-up is required for persons aged 45 and above.")]
    assert find_benefits(pages) == []


def test_catalogue_keys_unique():
    keys = [b.key for b in catalogue()]
    assert len(keys) == len(set(keys)) and "health_checkup" in keys


# ---------------------------------------------------------------- renewal guard

def terms_for_renewal(**overrides):
    base = dict(period_start=date(2026, 4, 1), period_end=date(2027, 3, 31), cumulative_bonus_amount=50_000,
                benefits=[PolicyBenefit(key="health_checkup", limit="Rs 1,500 once every policy year"),
                          PolicyBenefit(key="teleconsultation")])
    base.update(overrides)
    return policy(**base)


@pytest.mark.parametrize("today, status, days_left", [
    (date(2026, 11, 3), "active", 148),
    (date(2027, 2, 14), "due_soon", 45),
    (date(2027, 3, 31), "due_soon", 0),
    (date(2027, 4, 1), "grace", -1),
    (date(2027, 4, 30), "grace", -30),
    (date(2027, 5, 1), "lapsed", -31),
])
def test_renewal_status_by_date(today, status, days_left):
    r = renewal_status(RenewalInput(terms=terms_for_renewal()), today)
    assert (r.status, r.days_left) == (status, days_left)
    assert r.grace_until == date(2027, 4, 30)


def test_monthly_premium_grace_is_15_days():
    r = renewal_status(RenewalInput(terms=terms_for_renewal(premium_mode="monthly")), date(2027, 4, 10))
    assert r.status == "grace" and r.grace_until == date(2027, 4, 15)
    assert "instalments" in r.notes[0].text and r.notes[0].rule_ids == ["GRACE-HEALTH"]


def test_yearly_grace_warns_about_cover_gap():
    r = renewal_status(RenewalInput(terms=terms_for_renewal()), date(2027, 4, 10))
    assert r.notes[0].level == "warn" and "may not be covered" in r.notes[0].text


def test_credits_at_stake():
    r = renewal_status(RenewalInput(terms=terms_for_renewal()), date(2027, 3, 1))
    text = " | ".join(r.at_stake)
    assert "59 months of continuous cover" in text
    assert "Pre-existing disease waiting period (36 months): fully served on 01 Apr 2025" in text
    assert "Moratorium: 59 of 60 months done" in text
    assert "Cumulative bonus of Rs 50,000" in text
    lapsed = renewal_status(RenewalInput(terms=terms_for_renewal()), date(2027, 9, 1))
    assert "59 months of continuous cover" in " | ".join(lapsed.at_stake)  # counted to the end date, not today
    assert lapsed.unused_benefits == []


def test_unused_benefits_reset_each_policy_year():
    terms = terms_for_renewal()
    assert unused_benefits(terms) == ["Free health check-up (Rs 1,500 once every policy year)"]  # teleconsult: not yearly
    used_last_year = terms.model_copy(update={"benefits": [PolicyBenefit(key="health_checkup", last_used=date(2025, 12, 1))]})
    assert unused_benefits(used_last_year) == ["Free health check-up"]
    used = terms.model_copy(update={"benefits": [PolicyBenefit(key="health_checkup", last_used=date(2026, 6, 1))]})
    assert unused_benefits(used) == []
    excluded = terms.model_copy(update={"benefits": [PolicyBenefit(key="opd", status="not_covered")]})
    assert unused_benefits(excluded) == []


def test_unknown_end_date():
    r = renewal_status(RenewalInput(terms=policy()), date(2026, 11, 3))
    assert r.status == "unknown" and r.renew_by is None


def test_premium_check():
    terms = terms_for_renewal()
    senior = renewal_status(RenewalInput(terms=terms, current_premium=40_000, renewal_premium=46_000,
                                         oldest_member_age=67), date(2027, 3, 1)).premium_check
    assert senior.level == "warn" and senior.rule_ids == ["SENIOR-PREM-10"] and "15.0%" in senior.text
    young = renewal_status(RenewalInput(terms=terms, current_premium=40_000, renewal_premium=46_000,
                                        oldest_member_age=40), date(2027, 3, 1)).premium_check
    assert young.level == "info" and not young.rule_ids
    small = renewal_status(RenewalInput(terms=terms, current_premium=40_000, renewal_premium=43_000,
                                        oldest_member_age=67), date(2027, 3, 1)).premium_check
    assert small.level == "info"  # 7.5% is within the cap
    lower = renewal_status(RenewalInput(terms=terms, current_premium=40_000, renewal_premium=38_000), date(2027, 3, 1))
    assert lower.premium_check.level == "good"
    assert renewal_status(RenewalInput(terms=terms), date(2027, 3, 1)).premium_check is None


def test_renewal_events_and_ics():
    events = renewal_events(7, "Family Health Shield", terms_for_renewal(), date(2027, 3, 1))
    assert [e.day for e in events] == [date(2027, 3, 1), date(2027, 3, 24), date(2027, 3, 31), date(2027, 4, 27)]
    assert "Use before renewal: Free health check-up" in events[0].description
    assert renewal_events(7, "X", terms_for_renewal(), date(2027, 6, 1)) == []

    text = calendar(events, now=datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc))
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 4 and "DTSTART;VALUE=DATE:20270331" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in text.split("\r\n"))


def test_ics_escaping_and_folding():
    long = "Renew policy, today; check \\ notes\n" + "₹" * 60
    text = calendar([Event(uid="x", day=date(2027, 1, 1), summary=long, description="a,b")],
                    now=datetime(2027, 1, 1, tzinfo=timezone.utc))
    lines = text.split("\r\n")
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    unfolded = text.replace("\r\n ", "")
    assert "SUMMARY:Renew policy\\, today\\; check \\\\ notes\\n" + "₹" * 60 in unfolded
    assert "DESCRIPTION:a\\,b" in unfolded


# ---------------------------------------------------------------- API

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_extract_returns_benefits_and_they_save(client):
    r = client.post("/api/policies/extract", files={"file": ("policy.pdf", demo_policy_pdf(), "application/pdf")},
                    data={"use_ai": "false"})
    terms = r.json()["terms"]
    assert {b["key"] for b in terms["benefits"]} >= {"health_checkup", "ayush", "opd"}
    terms["period_end"] = "2099-03-31"
    saved = client.post("/api/policies", json={"name": "With benefits", "terms": terms}).json()
    assert saved["terms"]["benefits"] == terms["benefits"] and saved["terms"]["premium_mode"] == "yearly"

    ics = client.get(f"/api/policies/{saved['id']}/renewal.ics")
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert ics.text.count("BEGIN:VEVENT") == 4
    client.delete(f"/api/policies/{saved['id']}")


def test_renewal_endpoint_and_errors(client):
    terms = terms_for_renewal().model_dump(mode="json")
    r = client.post("/api/renewal", json={"terms": terms, "current_premium": 1000, "renewal_premium": 1200,
                                          "oldest_member_age": 70})
    assert r.status_code == 200 and r.json()["premium_check"]["rule_ids"] == ["SENIOR-PREM-10"]
    assert client.post("/api/renewal", json={"terms": terms, "oldest_member_age": 500}).status_code == 422
    no_end = client.post("/api/policies", json={"name": "No end", "terms": {"sum_insured": 100000}}).json()
    assert client.get(f"/api/policies/{no_end['id']}/renewal.ics").status_code == 400
    assert client.get("/api/policies/99999/renewal.ics").status_code == 404
    client.delete(f"/api/policies/{no_end['id']}")


def test_old_saved_terms_without_new_fields_still_load(client):
    created = client.post("/api/policies", json={"name": "Old", "terms": {"sum_insured": 200000}}).json()
    assert created["terms"]["benefits"] == [] and created["terms"]["premium_mode"] == "yearly"
    assert len(client.get("/api/benefits").json()) == len(catalogue())
    client.delete(f"/api/policies/{created['id']}")

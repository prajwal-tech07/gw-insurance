import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.alerts import build_alerts
from app.main import app
from app.models import ComplaintData, DeathClaimInput, SavedPolicy, ScamInput, VaultEntryData
from app.samples import SAMPLE_GENUINE_RENEWAL, SAMPLE_SCAM_BONUS, SAMPLE_SCAM_KYC
from app.scam.checker import check_link, check_message
from app.vault.checks import calendar_events, check_entry, summary
from app.vault.death_claim import help_with_claim
from tests.factories import policy

TODAY = date(2026, 11, 3)


def entry(**overrides) -> VaultEntryData:
    base = dict(kind="term_life", insurer="Sample Life Insurance", policy_number="TL-1", holder="R. Sample",
                insured="R. Sample", cover_amount=1_00_00_000, premium=12_000, premium_mode="yearly",
                start_date=date(2020, 5, 1), next_due=date(2027, 5, 1), nominee="S. Sample", nominee_relation="spouse",
                documents_at="Blue file, bedroom cupboard")
    base.update(overrides)
    return VaultEntryData(**base)


def codes(notes) -> str:
    return " | ".join(n.text for n in notes)


# ---------------------------------------------------------------- vault checks

def test_complete_life_policy_has_only_good_news():
    notes, status, days, grace = check_entry(entry(), TODAY)
    assert status == "ok" and days == 179 and grace == date(2027, 5, 31)
    assert [n.level for n in notes] == ["good"] and notes[0].rule_ids == ["LIFE-45"]


@pytest.mark.parametrize("next_due, status", [
    (date(2026, 11, 20), "due_soon"),
    (date(2026, 10, 20), "grace"),  # 14 days late, 30-day grace
    (date(2026, 9, 1), "lapsed"),
])
def test_life_due_status(next_due, status):
    notes, s, _, _ = check_entry(entry(next_due=next_due), TODAY)
    assert s == status
    if status == "grace":
        assert "life cover continues" in notes[0].text and notes[0].rule_ids == ["LIFE-GRACE"]
    if status == "lapsed":
        assert notes[0].level == "bad" and "revive" in notes[0].text


def test_monthly_life_grace_is_15_days():
    _, s, _, grace = check_entry(entry(premium_mode="monthly", next_due=date(2026, 10, 15)), TODAY)
    assert s == "lapsed" and grace == date(2026, 10, 30)


def test_motor_has_no_grace_and_warns_about_the_law():
    notes, s, _, grace = check_entry(entry(kind="motor", next_due=date(2026, 11, 1), nominee=""), TODAY)
    assert s == "lapsed" and grace is None
    assert "Motor Vehicles Act" in notes[0].text
    assert "nominee" not in codes(notes).lower()  # no nominee check for vehicle cover


def test_missing_details_are_flagged():
    notes, *_ = check_entry(entry(policy_number="", nominee="", documents_at="", next_due=None), TODAY)
    text = codes(notes)
    assert "Add the next premium or renewal date" in text
    assert "Add the policy number" in text
    assert "No nominee recorded" in text and any(n.level == "bad" and n.rule_ids == ["NOMINEE-01"] for n in notes)
    assert "where the policy papers are kept" in text


def test_nominee_relation_and_assignment():
    notes, *_ = check_entry(entry(nominee="A. Friend", nominee_relation="other", assigned_to_lender=True), TODAY)
    assert any(n.rule_ids == ["NOM-39"] and "Will" in n.text for n in notes)
    assert any(n.rule_ids == ["ASSIGN-01"] for n in notes)


def test_three_year_rule_counts_from_revival():
    notes, *_ = check_entry(entry(start_date=date(2018, 1, 1), revival_date=date(2025, 2, 1)), TODAY)
    rule = next(n for n in notes if n.rule_ids == ["LIFE-45"])
    assert rule.level == "info" and "01 Feb 2028" in rule.text and "revival" in rule.text


def test_matured_savings_policy():
    notes, s, *_ = check_entry(entry(kind="life_savings", end_date=date(2026, 6, 1)), TODAY)
    assert s == "ended" and notes[0].rule_ids == ["UNCLAIMED-01"]
    assert "nominee" not in codes(notes).lower()


def test_single_premium_life_needs_no_due_date():
    notes, s, *_ = check_entry(entry(premium_mode="single", next_due=None), TODAY)
    assert s == "none" and "next premium" not in codes(notes)


def test_summary_and_emergency_sheet():
    saved = SavedPolicy(id=1, name="Family Health Shield", created_at="", updated_at="",
                        terms=policy(period_end=date(2027, 3, 31)))
    rows = [(1, entry()), (2, entry(kind="personal_accident", cover_amount=25_00_000, premium=1_000, nominee="",
                                    next_due=date(2026, 11, 10))),
            (3, entry(kind="life_savings", cover_amount=5_00_000, premium=2_000, premium_mode="monthly",
                      end_date=date(2026, 1, 1)))]
    s = summary(rows, [saved], TODAY)
    assert s.life_cover == 1_00_00_000  # the matured policy is not counted
    assert s.accident_cover == 25_00_000 and s.health_cover == 500_000
    assert s.yearly_premium == 13_000  # 12,000 + 1,000; the ended policy is left out
    assert s.missing_nominee == 1 and s.due_soon == 1 and s.health_policies == 1
    sheet = s.emergency_sheet
    assert "FAMILY INSURANCE SHEET" in sheet and "Policy no.: TL-1" in sheet and "Nominee: S. Sample (spouse)" in sheet
    assert "Nominee: NOT RECORDED" in sheet and "Family Health Shield" in sheet
    assert "bimabharosa.irdai.gov.in/Home/UnclaimedAmount" in sheet


def test_calendar_events_cover_vault_and_health_policies():
    saved = SavedPolicy(id=1, name="Health", created_at="", updated_at="", terms=policy(period_end=date(2027, 3, 31)))
    events = calendar_events([(1, entry()), (2, entry(kind="motor", next_due=date(2026, 12, 1)))], [saved], TODAY)
    titles = [e.summary for e in events]
    assert any("Term life" in t and "grace period ends" in t for t in titles)
    assert not any("Vehicle" in t and "grace" in t for t in titles)  # no grace for motor policies
    assert any(t.startswith("Renew Health") for t in titles)
    assert all(e.day >= TODAY for e in events)


# ---------------------------------------------------------------- death claims

def claim(**overrides) -> DeathClaimInput:
    base = dict(kind="term_life", insurer="Sample Life", policy_number="TL-1", life_assured="R. Sample",
                claimant_name="S. Sample", claimant_relation="wife", claimant_is_nominee=True,
                policy_start=date(2019, 6, 1), date_of_death=date(2026, 10, 1), cause="illness",
                place_of_death="hospital")
    base.update(overrides)
    return DeathClaimInput(**base)


def test_old_policy_cannot_be_contested():
    r = help_with_claim(claim(), TODAY)
    assert r.contestable == "no" and r.notes[0].level == "good" and r.notes[0].rule_ids == ["LIFE-45"]
    assert any("discharge or death summary" in d for d in r.documents)
    assert not any("legal heir" in d for d in r.documents)
    assert r.deadline is None and "Intimate the claim now" in r.deadline_note
    assert any(n.rule_ids == ["LIFE-CLAIM-01"] for n in r.notes)
    assert "Intimation of death claim under policy no. TL-1" in r.intimation_letter and r.follow_up_letter is None


def test_early_claim_is_limited_and_revival_counts():
    r = help_with_claim(claim(policy_start=date(2015, 1, 1), revival_date=date(2025, 3, 1)), TODAY)
    assert r.contestable == "limited" and r.contest_until == date(2028, 3, 1)
    assert "revival" in r.contest_note and "LIFE-CLAIM-01" in r.notes[0].rule_ids


def test_deadline_on_time_and_late():
    on_time = help_with_claim(claim(intimated_on=date(2026, 10, 25)), TODAY)
    assert on_time.deadline == date(2026, 11, 9) and on_time.days_left == 6 and on_time.follow_up_letter is None
    investigated = help_with_claim(claim(intimated_on=date(2026, 10, 1), under_investigation=True), TODAY)
    assert investigated.deadline == date(2026, 11, 15) and investigated.days_left == 12
    late = help_with_claim(claim(intimated_on=date(2026, 10, 5), cover_amount=50_00_000), TODAY)
    assert late.days_left == -14 and "bank rate plus 2%" in late.deadline_note
    assert any(n.level == "bad" and n.rule_ids == ["DEATH-TAT"] for n in late.notes)
    assert "14 days late" in late.follow_up_letter and "Rs 50,00,000" in late.follow_up_letter


def test_accident_documents_and_other_money():
    r = help_with_claim(claim(cause="accident", place_of_death="other", claimant_is_nominee=None,
                              assigned_to_lender=True), TODAY)
    docs = " | ".join(r.documents)
    assert "First Information Report" in docs and "Post-mortem report" in docs and "legal heir" in docs
    assert "Loan account statement" in docs
    names = [o.name for o in r.other_money]
    assert any(n.startswith("PMSBY") for n in names) and any(n.startswith("Vehicle") for n in names)
    assert any(n.rule_ids == ["ASSIGN-01"] for n in r.notes)
    assert not any(o.name.startswith("PMSBY") for o in help_with_claim(claim(), TODAY).other_money)


def test_suicide_clause():
    early = help_with_claim(claim(cause="suicide", policy_start=date(2026, 3, 1)), TODAY)
    assert any(n.rule_ids == ["LIFE-SUICIDE"] and "80%" in n.text for n in early.notes)
    assert any("14416" in n.text for n in early.notes)
    later = help_with_claim(claim(cause="suicide"), TODAY)
    assert any(n.rule_ids == ["LIFE-SUICIDE"] and "full benefit" in n.text for n in later.notes)


def test_non_life_policies():
    r = help_with_claim(claim(kind="personal_accident", intimated_on=date(2026, 10, 2)), TODAY)
    assert r.contestable == "not_applicable" and r.deadline is None and "Ask this insurer" in r.deadline_note
    assert "15 days" not in r.intimation_letter


@pytest.mark.parametrize("overrides, message", [
    (dict(date_of_death=date(2027, 1, 1)), "date of death cannot be in the future"),
    (dict(intimated_on=date(2026, 9, 1)), "cannot be intimated before the date of death"),
    (dict(intimated_on=date(2026, 12, 1)), "cannot be in the future"),
    (dict(policy_start=date(2026, 10, 15)), "start date is after the date of death"),
    (dict(revival_date=date(2019, 1, 1)), "revival date cannot be before"),
])
def test_impossible_dates_are_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        help_with_claim(claim(**overrides), TODAY)


def test_unknown_start():
    assert help_with_claim(claim(policy_start=None), TODAY).contestable == "unknown"


# ---------------------------------------------------------------- scam checker

def flags(text: str) -> tuple[str, set[str]]:
    r = check_message(ScamInput(text=text))
    return r.risk, {f.code for f in r.flags}


def test_samples():
    risk, found = flags(SAMPLE_SCAM_BONUS)
    assert risk == "high" and {"pay_to_receive", "regulator", "bonus_lure", "urgency", "pay_personal_account"} <= found
    bonus = check_message(ScamInput(text=SAMPLE_SCAM_BONUS))
    assert bonus.phone_numbers == ["9000000000"]
    regulator = next(f for f in bonus.flags if f.code == "regulator")
    assert regulator.rule_ids == ["SPURIOUS-01"] and "Mr. Sharma" in regulator.evidence  # "Mr." does not end a sentence
    kyc = check_message(ScamInput(text=SAMPLE_SCAM_KYC))
    assert kyc.risk == "high" and {"otp_request", "app_file", "kyc_update", "threat"} <= {f.code for f in kyc.flags}
    assert [(link.domain, link.level) for link in kyc.links] == [("bit.ly", "medium"), ("sample-bima-kyc.xyz", "high")]
    genuine = check_message(ScamInput(text=SAMPLE_GENUINE_RENEWAL))
    assert genuine.risk == "low" and genuine.flags == [] and "does not prove" in genuine.headline


@pytest.mark.parametrize("text, code", [
    ("आपका बोनस लंबित है। राशि प्राप्त करने के लिए जीएसटी शुल्क जमा करें।", "pay_to_receive"),
    ("Your bonus of Rs 3 lakh is pending. Pay GST of Rs 5,000 to release it.", "pay_to_receive"),  # two sentences
    ("Sir aapka OTP bata dijiye, refund process ho jayega", "otp_request"),
    ("Please install AnyDesk so our team can help with your claim", "remote_access"),
    ("Scan this QR code to receive your refund of Rs 4,999.", "qr_to_receive"),
    ("This is CBI. A case registered against your Aadhaar. You will be arrested today.", "digital_arrest"),
    ("Congratulations! You have won a lucky draw of Rs 25 lakh.", "prize"),
    ("Surrender your old LIC policy and buy this new plan with guaranteed 18% return.", "surrender_switch"),
    ("This plan is better than an FD with guaranteed double money in 5 years.", "guaranteed_returns"),
    ("We can get your rejected claim approved. Our fee is 20% in advance.", "claim_fixer"),
    ("Send your Aadhaar and PAN card photo on WhatsApp to this number.", "documents"),
    ("Earn agency commission on your policy by paying a small registration fee.", "agent_commission"),
])
def test_red_flags(text, code):
    assert code in flags(text)[1]


@pytest.mark.parametrize("text", [
    "482913 is your OTP for payment of Rs 12,500 at Sample Insurance. Do not share it with anyone.",
    "Your claim amount of Rs 50,000 has been paid to your account after deducting non-payable charges.",
    "For accident claims, submit a copy of the FIR from the police and the post-mortem report.",
    "Pay your renewal premium easily using Google Pay or PhonePe on our app.",
    "Beware of spurious calls: IRDAI is not involved in selling policies or announcing bonus.",
    "Your premium of Rs 18,450 incl. GST is due on 31 Mar 2027. Please share your feedback on our service.",
    "Please update your address with pin code in your policy records.",
    "Your premium of Rs 18,450 incl. GST is due. Pay on our app to protect your no-claim bonus.",
])
def test_genuine_messages_stay_low(text):
    assert flags(text) == ("low", set())


def test_links():
    assert check_link("https://bimabharosa.irdai.gov.in/Home/UnclaimedAmount").level == "info"
    assert check_link("http://192.168.10.5/claim").level == "high"
    assert check_link("www.lic-bonus-refund.online/pay").level == "high"
    assert check_link("tinyurl.com/abc.").text == "tinyurl.com/abc"
    assert check_link("https://www.healthinsure-renew.com").level == "medium"
    assert check_link("https://example.com/page").level == "info"
    r = check_message(ScamInput(text="Visit insurance.Inform us. See www.sample.com today."))
    assert [link.domain for link in r.links] == ["sample.com"]


@pytest.mark.parametrize("text", ["a." * 10_000, ("abc-" * 2000 + ".") * 2, "a.b.c.d.e.f.g.h.i.j.k " * 900])
def test_long_pastes_are_checked_quickly(text):
    # The old link pattern took about 20 seconds on "a.a.a.a..."; this must stay well under a second.
    started = time.perf_counter()
    check_message(ScamInput(text=text[:20_000]))
    assert time.perf_counter() - started < 2


def test_links_glued_to_words_are_found():
    r = check_message(ScamInput(text="Claim here:https://sample-claim.top/pay.apk now"))
    assert [(link.domain, link.level) for link in r.links] == [("sample-claim.top", "high")]


def test_three_medium_flags_make_high_risk():
    risk, found = flags("Your policy will be blocked. Update KYC now. Reply within 2 hours.")
    assert {"threat", "kyc_update", "urgency"} <= found and risk == "high"
    assert flags("Reply within 2 hours please.")[0] == "medium"


# ---------------------------------------------------------------- alerts and API

def test_alerts():
    saved = SavedPolicy(id=1, name="Health", created_at="", updated_at="",
                        terms=policy(period_start=date(2025, 12, 1), period_end=date(2026, 11, 30),
                                     benefits=[{"key": "health_checkup"}]))
    complaint = ComplaintData(title="Room rent cut", grievance_filed_on=date(2026, 10, 22))
    out = build_alerts([saved], [(1, entry(next_due=date(2026, 10, 25))), (2, entry(nominee=""))],
                       [(1, complaint)], today=TODAY)
    assert out[0].level == "bad"  # sorted most urgent first
    texts = [(a.tab, a.title, a.text) for a in out]
    assert any(t == "policies" and "renewal" in title for t, title, _ in texts)
    assert any(t == "policies" and "Free health check-up" in text for t, _, text in texts)
    assert any(t == "vault" and "grace period" in text for t, _, text in texts)
    assert any(t == "vault" and "No nominee" in text for t, _, text in texts)
    assert any(t == "complaints" and "Insurer must resolve" in text for t, _, text in texts)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_vault_api(client):
    body = entry().model_dump(mode="json") | {"next_due": "2099-05-01"}
    created = client.post("/api/vault", json=body)
    assert created.status_code == 200, created.text
    eid = created.json()["id"]
    assert created.json()["due_status"] == "ok"
    listed = client.get("/api/vault").json()
    assert any(e["id"] == eid for e in listed["entries"]) and "FAMILY INSURANCE SHEET" in listed["emergency_sheet"]
    updated = client.put(f"/api/vault/{eid}", json=body | {"nominee": ""}).json()
    assert any("No nominee" in n["text"] for n in updated["checks"])
    ics = client.get("/api/vault/calendar.ics")
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text
    assert client.post("/api/vault", json=body | {"insurer": ""}).status_code == 422
    assert client.post("/api/vault", json=body | {"kind": "pets"}).status_code == 422
    blank = client.post("/api/vault", json=body | {"holder": "   "})
    assert blank.status_code == 400 and "policyholder" in blank.json()["detail"]
    early = client.post("/api/vault", json=body | {"start_date": "2020-01-01", "end_date": "2019-01-01"})
    assert early.status_code == 400 and "before the policy start" in early.json()["detail"]
    assert client.put(f"/api/vault/{eid}", json=body | {"revival_date": "2010-01-01"}).status_code == 400
    assert client.put("/api/vault/99999", json=body).status_code == 404
    assert client.delete(f"/api/vault/{eid}").status_code == 200
    assert client.delete(f"/api/vault/{eid}").status_code == 404
    assert isinstance(client.get("/api/alerts").json(), list)


def test_death_claim_and_scam_api(client):
    r = client.post("/api/death-claim", json={"kind": "term_life", "date_of_death": "2026-01-10",
                                              "policy_start": "2020-01-01", "intimated_on": "2026-01-12"})
    assert r.status_code == 200 and r.json()["contestable"] == "no" and r.json()["follow_up_letter"]
    future = client.post("/api/death-claim", json={"date_of_death": "2999-01-01"})
    assert future.status_code == 400 and "future" in future.json()["detail"]
    scam = client.post("/api/scam-check", json={"text": SAMPLE_SCAM_BONUS})
    assert scam.status_code == 200 and scam.json()["risk"] == "high" and len(scam.json()["report"]) == 4
    assert client.post("/api/scam-check", json={"text": "hi"}).status_code == 422
    for name in ("scam-bonus", "scam-kyc", "genuine-renewal"):
        assert "SAMPLE" in client.get(f"/api/samples/{name}").json()["text"]


# ---------------------------------------------------------------- interest, post-hospitalisation bills, overcharges

def test_interest_on_a_late_death_claim():
    r = help_with_claim(claim(date_of_death=date(2026, 9, 1), intimated_on=date(2026, 9, 4), cover_amount=10_00_000, bank_rate=6.25), TODAY)
    # 60 days late from intimation: 10,00,000 x 8.25% x 60/365 = 13,562
    assert r.days_left < 0 and r.interest_due == 13_562
    assert "about Rs 13,562 up to today, at a bank rate of 6.25%" in r.follow_up_letter
    assert help_with_claim(claim(date_of_death=date(2026, 9, 1), intimated_on=date(2026, 9, 4), cover_amount=10_00_000), TODAY).interest_due is None
    assert help_with_claim(claim(intimated_on=date(2026, 10, 30), bank_rate=6.25,
                                 cover_amount=10_00_000), TODAY).interest_due is None  # not late yet


def test_post_hospitalisation_tracker():
    from app.engine.post_hosp import track
    from app.models import PostHospData
    data = PostHospData(title="Knee surgery", discharge_date=date(2026, 9, 10), post_days=60, bills=[
        {"on": "2026-09-20", "description": "Physiotherapy", "amount": 4000},
        {"on": "2026-10-15", "description": "Medicines", "amount": 2500.5},
        {"on": "2026-11-20", "description": "Late visit", "amount": 900}])
    t = track(1, data, TODAY)
    assert t.window_ends == date(2026, 11, 9) and t.days_left == 6 and t.status == "closing"
    assert t.claimable == 6500.5 and t.outside == ["Late visit (20 Nov 2026)"]
    assert track(1, data, date(2026, 12, 1)).status == "closed" and track(1, data, date(2026, 9, 11)).status == "open"
    alerts = build_alerts([], [], [], [(1, data)], today=TODAY)
    assert alerts[0].tab == "bill" and "Knee surgery" in alerts[0].title


def test_duplicate_bill_lines(client):
    from app.engine.bill_checks import overcharges
    from app.models import BillItem
    items = [BillItem(description="CT Scan Brain", amount=6000), BillItem(description="CT  scan brain", amount=6000),
             BillItem(description="CT Scan Brain", amount=3000), BillItem(description="Medicines", amount=500)]
    issues = overcharges(items)
    assert len(issues) == 1 and "billed 2 times" in issues[0].message and "Rs 6,000 should come off" in issues[0].message
    r = client.post("/api/bills/parse-text", json={"text": "X-Ray Chest 1,200.00\nX-Ray Chest 1,200.00\nPharmacy 500.00"}).json()
    assert [i["code"] for i in r["overcharges"]] == ["duplicate_line"]


def test_post_hosp_api(client):
    body = {"title": "Appendix", "discharge_date": "2099-01-01", "post_days": 30,
            "bills": [{"on": "2099-01-05", "description": "Medicines", "amount": 800}]}
    created = client.post("/api/post-hosp", json=body).json()
    assert created["status"] == "open" and created["claimable"] == 800
    tid = created["id"]
    updated = client.put(f"/api/post-hosp/{tid}", json=body | {"post_days": 60}).json()
    assert updated["window_ends"] == "2099-03-02"
    assert any(t["id"] == tid for t in client.get("/api/post-hosp").json())
    assert client.post("/api/post-hosp", json=body | {"post_days": 0}).status_code == 422
    assert client.put("/api/post-hosp/99999", json=body).status_code == 404
    assert client.delete(f"/api/post-hosp/{tid}").status_code == 200
    assert client.delete(f"/api/post-hosp/{tid}").status_code == 404

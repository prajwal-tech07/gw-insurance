import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.samples import SAMPLE_BILL, SAMPLE_PARTIAL_LETTER, demo_policy_pdf


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def saved_terms(client):
    r = client.post("/api/policies/extract", files={"file": ("policy.pdf", demo_policy_pdf(), "application/pdf")},
                    data={"use_ai": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "rules"  # AI is disabled in tests
    saved = client.post("/api/policies", json={"name": "Sample policy", "terms": body["terms"]})
    assert saved.status_code == 200
    return saved.json()


def test_health_and_reference_data(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["ai_enabled"] is False
    assert len(client.get("/api/rules").json()) >= 15
    assert len(client.get("/api/irdai-lists").json()["items"]) == 146
    assert client.get("/api/checklist").json()["discharge"]
    pdf = client.get("/api/samples/policy.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "Room Rent" in client.get("/api/samples/bill").json()["text"]
    assert client.get("/api/samples/nope").status_code == 404


def test_policy_crud(client, saved_terms):
    pid = saved_terms["id"]
    assert saved_terms["terms"]["sum_insured"] == 500000
    assert any(p["id"] == pid for p in client.get("/api/policies").json())
    terms = saved_terms["terms"] | {"copay_percent": 20}
    updated = client.put(f"/api/policies/{pid}", json={"name": "Renamed", "terms": terms}).json()
    assert updated["name"] == "Renamed" and updated["terms"]["copay_percent"] == 20
    client.put(f"/api/policies/{pid}", json={"name": "Sample policy", "terms": saved_terms["terms"]})
    assert client.get("/api/policies/99999").status_code == 404


def test_estimate_and_calculate(client, saved_terms):
    terms = saved_terms["terms"]
    est = client.post("/api/estimate", json={
        "terms": terms, "admission_date": "2026-09-10", "patient_age": 45, "diagnosis": "appendicitis",
        "room_days": 3, "room_options": [{"name": "Single AC", "rent_per_day": 6000},
                                         {"name": "Twin sharing", "rent_per_day": 4500}],
        "items": [{"description": "Surgeon fees", "amount": 50000}, {"description": "Pharmacy", "amount": 30000}],
    })
    assert est.status_code == 200, est.text
    assert est.json()["recommended"] == "Twin sharing"

    parsed = client.post("/api/bills/parse-text", json={"text": SAMPLE_BILL}).json()
    assert parsed["total"] == 153900 and len(parsed["items"]) == 13
    calc = client.post("/api/claims/calculate", json={"terms": terms, "claim": {
        "admission_date": "2026-09-11", "patient_age": 45, "diagnosis": "appendicitis", "room_days": 3,
        "items": [{"description": i["description"], "amount": i["amount"]} for i in parsed["items"]]}})
    assert calc.status_code == 200
    result = calc.json()
    assert result["proportion_applied"] == pytest.approx(0.8333, abs=1e-4)
    assert 0 < result["insurer_pays"] < result["total_billed"]

    file_parse = client.post("/api/bills/parse", files={"file": ("bill.txt", SAMPLE_BILL.encode(), "text/plain")})
    assert file_parse.json()["total"] == 153900


def test_waiting_periods_endpoint(client, saved_terms):
    r = client.post("/api/waiting-periods", json={"terms": saved_terms["terms"], "admission_date": "2023-01-10",
                                                  "diagnosis": "cataract"})
    statuses = {s["name"]: s["status"] for s in r.json()}
    assert statuses["Specific disease waiting period (cataract)"] == "blocked"


def test_optimizer_endpoint_and_value_error(client, saved_terms):
    terms = saved_terms["terms"]
    claim = {"admission_date": "2026-09-11", "room_days": 0, "items": [{"description": "Surgery charges", "amount": 100000}]}
    ok = client.post("/api/optimize", json={"policies": [{"label": "A", "terms": terms},
                                                         {"label": "B", "terms": terms}], "claim": claim})
    assert ok.status_code == 200
    # Age unknown, so the 10% co-pay is applied: A pays 90,000; the unpaid 10,000 goes to B,
    # which applies its own 10% co-pay and pays 9,000.
    assert [p["pays"] for p in ok.json()["best"]["payouts"]] == [90000, 9000]
    assert ok.json()["best"]["out_of_pocket"] == 1000
    dup = client.post("/api/optimize", json={"policies": [{"label": "A", "terms": terms},
                                                          {"label": "A", "terms": terms}], "claim": claim})
    assert dup.status_code == 400 and "different name" in dup.json()["detail"]


def test_rejection_draft_and_tracker(client, saved_terms):
    analysis = client.post("/api/rejections/analyze", json={
        "letter_text": SAMPLE_PARTIAL_LETTER, "terms": saved_terms["terms"], "admission_date": "2026-09-11",
        "claimed_amount": 153900, "settled_amount": 112400}).json()
    assert analysis["case_strength"] == "strong"
    letter = client.post("/api/rejections/read-letter",
                         files={"file": ("letter.txt", SAMPLE_PARTIAL_LETTER.encode(), "text/plain")}).json()
    assert "Proportionate deduction" in letter["text"]

    drafted = client.post("/api/complaints/draft", json={
        "complainant_name": "A. Sample", "insurer": "Suraksha Sample General Insurance Co. Ltd.",
        "policy_number": "SAMPLE/HS/000123", "claimed_amount": 153900, "paid_amount": 112400,
        "findings": analysis["findings"]}).json()
    assert drafted["amount_disputed"] == 41500 and "Grievance Redressal Officer" in drafted["insurer_letter"]

    created = client.post("/api/complaints", json={"title": "Room rent cut", "insurer": "Sample",
                                                   "amount_disputed": 41500, "grievance_filed_on": "2026-10-01"}).json()
    cid = created["id"]
    assert len(created["deadlines"]) == 3 and created["next_action"]
    updated = client.put(f"/api/complaints/{cid}", json=created | {"insurer_outcome": "rejected",
                                                                  "insurer_reply_on": "2026-10-10"}).json()
    assert "Ombudsman" in updated["next_action"]
    assert any(c["id"] == cid for c in client.get("/api/complaints").json())
    assert client.delete(f"/api/complaints/{cid}").status_code == 200
    assert client.delete(f"/api/complaints/{cid}").status_code == 404


def test_precedents_endpoints(client):
    assert len(client.get("/api/precedents/all").json()) >= 12
    r = client.get("/api/precedents", params={"q": "diabetes not disclosed", "reason": "pre_existing_non_disclosure"}).json()
    assert r["matches"] and r["similar_cases"] >= 1


def test_upload_errors(client):
    assert client.post("/api/policies/extract", files={"file": ("x.pdf", b"", "application/pdf")}).status_code == 400
    bad_pdf = client.post("/api/policies/extract", files={"file": ("x.pdf", b"%PDF-broken", "application/pdf")})
    assert bad_pdf.status_code == 400 and "Could not open the PDF" in bad_pdf.json()["detail"]
    photo = client.post("/api/bills/parse", files={"file": ("bill.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert photo.status_code == 400 and "Tesseract" in photo.json()["detail"]


def test_delete_policy(client):
    created = client.post("/api/policies", json={"name": "Temp", "terms": {"sum_insured": 100000}}).json()
    assert client.delete(f"/api/policies/{created['id']}").status_code == 200
    assert client.delete(f"/api/policies/{created['id']}").status_code == 404

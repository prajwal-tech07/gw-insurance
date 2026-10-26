from datetime import date
from types import SimpleNamespace

from app.analyzer.rejection import analyze, detect_reasons
from app.complaints.drafter import draft
from app.complaints.tracker import timeline
from app.models import AnalyzeInput, ComplaintData, DraftInput
from app.precedents.store import all_cases, load_seed, search
from app.precedents.import_cases import main as import_main
from app.samples import SAMPLE_PARTIAL_LETTER, SAMPLE_REJECTION_LETTER

from factories import policy


def verdicts(result):
    return {f.reason_code: f.verdict for f in result.findings}


def test_partial_settlement_letter():
    r = analyze(AnalyzeInput(letter_text=SAMPLE_PARTIAL_LETTER, terms=policy(), admission_date=date(2026, 9, 11),
                             claimed_amount=153_900, settled_amount=112_400))
    v = verdicts(r)
    assert v["proportionate_deduction"] == "likely_wrong"  # cut applied to pharmacy, tests and ICU
    assert v["non_payable"] == "valid"
    assert v["reasonable_customary"] == "questionable"
    assert v["no_clause"] == "questionable"
    assert r.case_strength == "strong"
    assert "Rs 41,500" in r.summary
    assert 26_400 in r.amounts_found
    prop = next(f for f in r.findings if f.reason_code == "proportionate_deduction")
    assert prop.rule_ids == ["PROP-01", "PROP-02"]


def test_non_disclosure_after_moratorium_is_likely_wrong():
    terms = policy(first_inception_date=date(2019, 6, 1))
    r = analyze(AnalyzeInput(letter_text=SAMPLE_REJECTION_LETTER, terms=terms, admission_date=date(2026, 9, 2)))
    f = next(f for f in r.findings if f.reason_code == "pre_existing_non_disclosure")
    assert f.verdict == "likely_wrong" and f.rule_ids == ["MORA-60"]
    assert "87 months" in f.explanation


def test_non_disclosure_before_moratorium_is_questionable_with_precedents():
    terms = policy(first_inception_date=date(2024, 6, 1))
    r = analyze(AnalyzeInput(letter_text=SAMPLE_REJECTION_LETTER, terms=terms, admission_date=date(2026, 9, 2)))
    assert verdicts(r)["pre_existing_non_disclosure"] == "questionable"
    assert r.precedents.similar_cases >= 5
    assert any("pre_existing_non_disclosure" in m.case.reason_codes for m in r.precedents.matches[:3])
    assert "too few" in r.precedents.confidence_note
    assert r.precedents.policyholder_win_rate is not None


def test_documents_and_delay_rules_depend_on_date():
    letter = "Your claim is closed as documents were not submitted. There was also delay in intimation of the claim."
    new = analyze(AnalyzeInput(letter_text=letter, admission_date=date(2025, 1, 10)))
    old = analyze(AnalyzeInput(letter_text=letter, admission_date=date(2023, 1, 10)))
    assert verdicts(new)["documents"] == "likely_wrong" and verdicts(old)["documents"] == "questionable"
    assert verdicts(new)["late_intimation"] == "likely_wrong"


def test_waiting_period_check_uses_policy_start():
    letter = "The claim is repudiated as the ailment falls under the 24 months waiting period as per clause 4.2."
    early = analyze(AnalyzeInput(letter_text=letter, terms=policy(first_inception_date=date(2025, 6, 1)),
                                 admission_date=date(2026, 6, 1)))
    late = analyze(AnalyzeInput(letter_text=letter, terms=policy(first_inception_date=date(2023, 6, 1)),
                                admission_date=date(2026, 6, 1)))
    assert verdicts(early)["waiting_period"] == "valid"
    assert verdicts(late)["waiting_period"] == "likely_wrong"
    assert early.clause_cited


def test_exclusion_dropped_when_specific_reason_present():
    reasons = detect_reasons("The claim is excluded as the condition is pre-existing.")
    assert "pre_existing_non_disclosure" in reasons and "exclusion" not in reasons


def test_unknown_letter():
    r = analyze(AnalyzeInput(letter_text="We are unable to process your request at this time."))
    assert r.findings[0].reason_code == "unknown"


def test_precedent_seed_cases_load_and_search():
    cases = all_cases()
    seed_ids = {c.id for c in load_seed()}
    assert len(seed_ids) == 12 and seed_ids <= {c.id for c in cases}
    assert all(c.source_url.startswith("https://") for c in cases)
    r = search("rejected because hospitalisation was less than 24 hours", ["not_requiring_hospitalisation"])
    assert r.matches[0].case.reason_codes == ["not_requiring_hospitalisation"]
    assert "Reports mostly cover cases the policyholder won" in r.bias_note


def test_import_cases_csv(tmp_path):
    csv_file = tmp_path / "cases.csv"
    csv_file.write_text(
        "id,title,forum,forum_level,insurer,policy_type,reason_codes,reason_text,outcome,summary,reasoning,source_name,source_url,claim_amount\n"
        "test-1,A vs B,District Commission X,district,Some Insurer,Mediclaim,documents|late_intimation,Late documents,"
        "insurer,Summary,Reasoning,Test,https://example.com/case,\"1,00,000\"\n", encoding="utf-8")
    assert import_main([str(csv_file)]) == 0
    assert any(c.id == "test-1" and c.claim_amount == 100_000 for c in all_cases())
    bad = tmp_path / "bad.csv"
    bad.write_text(csv_file.read_text(encoding="utf-8").replace("documents|late_intimation", "made_up_code"), encoding="utf-8")
    assert import_main([str(bad)]) == 1


def _draft_input(**overrides):
    analysis = analyze(AnalyzeInput(letter_text=SAMPLE_PARTIAL_LETTER, terms=policy(), admission_date=date(2026, 9, 11)))
    base = dict(complainant_name="A. Sample", insurer="Suraksha Sample General Insurance Co. Ltd.",
                policy_number="SAMPLE/HS/000123", claim_number="SAMPLE-CL-7781", hospital="City Care Hospital",
                admission_date=date(2026, 9, 11), claimed_amount=153_900, paid_amount=112_400,
                rejection_date=date(2026, 9, 25), grievance_filed_on=date(2026, 10, 1), findings=analysis.findings)
    base.update(overrides)
    return DraftInput(**base)


def test_draft_letters_contain_facts_and_rules():
    d = draft(_draft_input(), today=date(2026, 10, 1))
    assert d.amount_disputed == 41_500
    assert "Rs 41,500" in d.insurer_letter and "SAMPLE-CL-7781" in d.insurer_letter
    assert "within 14 days" in d.insurer_letter
    assert "Proportionate (room-rent) deduction" in d.insurer_letter
    assert "norms for proportionate deductions, 2020" in d.insurer_letter  # rule source cited
    assert "draft" not in d.insurer_letter
    assert "Non-payable items" not in d.insurer_letter  # valid deductions are not disputed
    assert "Rule 14" in d.ombudsman_text and "01 Oct 2026" in d.ombudsman_text
    assert "Relief sought: payment of Rs 41,500" in d.bima_bharosa_text
    assert not d.polished_by_ai


def _client(text):
    response = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])
    create = lambda **kwargs: response  # noqa: E731
    return SimpleNamespace(messages=SimpleNamespace(create=create), beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_ai_polish_is_rejected_if_numbers_change():
    inp = _draft_input(polish_with_ai=True)
    bad = draft(inp, today=date(2026, 10, 1), client=_client("Dear insurer, please pay me."))
    assert not bad.polished_by_ai and any("changed some numbers" in n for n in bad.notes)
    original = draft(_draft_input(), today=date(2026, 10, 1)).insurer_letter
    good = draft(inp, today=date(2026, 10, 1), client=_client(original.replace("Dear Sir/Madam", "Dear Sir or Madam")))
    assert good.polished_by_ai and "Dear Sir or Madam" in good.insurer_letter


def test_tracker_deadlines_and_next_action():
    data = ComplaintData(title="Room rent cut", grievance_filed_on=date(2026, 10, 1))
    waiting = timeline(1, data, today=date(2026, 10, 5))
    assert waiting.deadlines[0].due == date(2026, 10, 15) and waiting.deadlines[0].status == "upcoming"
    assert "Wait for the insurer" in waiting.next_action
    overdue = timeline(1, data, today=date(2026, 10, 20))
    assert "Bima Bharosa" in overdue.next_action and overdue.deadlines[0].status == "passed"
    no_reply = timeline(1, data, today=date(2026, 11, 5))
    assert "Ombudsman" in no_reply.next_action
    assert no_reply.deadlines[2].due == date(2027, 11, 1)
    rejected = data.model_copy(update={"insurer_reply_on": date(2026, 10, 10), "insurer_outcome": "rejected"})
    r = timeline(1, rejected, today=date(2026, 10, 12))
    assert r.deadlines[2].due == date(2027, 10, 10) and r.deadlines[0].status == "done"
    assert "10 Oct 2027" in r.next_action

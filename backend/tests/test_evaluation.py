import json

from app.evaluation.classifier_eval import cross_validate
from app.evaluation.run_eval import CASES_DIR, EvalCase, evaluate, load_cases, main, summary


def test_synthetic_cases_match_hand_calculations():
    rows = evaluate(load_cases(CASES_DIR))
    synthetic = [r for r in rows if r.source == "synthetic"]
    assert len(synthetic) >= 5 and all(r.within_tolerance for r in synthetic)
    assert summary(rows)["synthetic"]["mean_abs_error_pct"] == 0


def test_real_claim_template_is_valid_and_skipped():
    EvalCase(**json.loads((CASES_DIR / "_template_real_claim.json").read_text(encoding="utf-8")))
    assert all(not c.id.startswith("real-001") for c in load_cases(CASES_DIR))


def test_cli_runs(capsys):
    assert main([]) == 0
    assert "within 5%" in capsys.readouterr().out


def test_hybrid_classifier_beats_model_alone():
    r = cross_validate()
    assert r["hybrid_accuracy"] >= r["model_accuracy"] and r["hybrid_accuracy"] >= 0.85

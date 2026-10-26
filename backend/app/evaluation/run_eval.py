"""Compare the claim engine's estimate with what insurers actually paid.

Usage (from the backend folder):
    python -m app.evaluation.run_eval            # cases in app/evaluation/cases/
    python -m app.evaluation.run_eval --dir my_cases --json

Each case is a JSON file: {"id", "source": "real"|"synthetic", "description",
"terms": PolicyTerms, "claim": ClaimInput, "actual_settlement": number}.
Copy cases/_template_real_claim.json to add a real settled claim. Only "real"
cases measure real-world accuracy; "synthetic" ones check the maths.
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from app.engine.calculator import calculate_claim
from app.models import ClaimInput, PolicyTerms

CASES_DIR = Path(__file__).with_name("cases")
TOLERANCE = 0.05


class EvalCase(BaseModel):
    id: str
    source: str = Field(pattern="^(real|synthetic)$")
    description: str = ""
    terms: PolicyTerms
    claim: ClaimInput
    actual_settlement: float = Field(ge=0)


class EvalRow(BaseModel):
    id: str
    source: str
    actual: float
    estimate: float
    error: float
    error_pct: float | None
    within_tolerance: bool


def load_cases(directory: Path) -> list[EvalCase]:
    return [EvalCase(**json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(directory.glob("*.json")) if not p.name.startswith("_")]


def evaluate(cases: list[EvalCase]) -> list[EvalRow]:
    rows = []
    for case in cases:
        estimate = calculate_claim(case.terms, case.claim).insurer_pays
        error = estimate - case.actual_settlement
        pct = abs(error) / case.actual_settlement if case.actual_settlement else None
        within = abs(error) <= 1 if case.actual_settlement == 0 else (pct is not None and pct <= TOLERANCE)
        rows.append(EvalRow(id=case.id, source=case.source, actual=case.actual_settlement, estimate=estimate,
                            error=round(error, 2), error_pct=round(pct, 4) if pct is not None else None,
                            within_tolerance=within))
    return rows


def summary(rows: list[EvalRow]) -> dict[str, dict[str, float | int | None]]:
    out = {}
    for source in ("real", "synthetic"):
        group = [r for r in rows if r.source == source]
        pcts = [r.error_pct for r in group if r.error_pct is not None]
        out[source] = {
            "cases": len(group),
            "within_5_percent": sum(r.within_tolerance for r in group),
            "mean_abs_error_pct": round(sum(pcts) / len(pcts), 4) if pcts else None,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=CASES_DIR)
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    args = parser.parse_args(argv)
    rows = evaluate(load_cases(args.dir))
    stats = summary(rows)
    if args.json:
        print(json.dumps({"rows": [r.model_dump() for r in rows], "summary": stats}, indent=2))
        return 0
    print(f"{'case':32} {'source':10} {'actual':>12} {'estimate':>12} {'error %':>8}  ok")
    for r in rows:
        pct = f"{r.error_pct * 100:.1f}" if r.error_pct is not None else "-"
        print(f"{r.id:32} {r.source:10} {r.actual:12,.0f} {r.estimate:12,.0f} {pct:>8}  {'yes' if r.within_tolerance else 'NO'}")
    for source, s in stats.items():
        if s["cases"]:
            mae = f"{s['mean_abs_error_pct'] * 100:.1f}%" if s["mean_abs_error_pct"] is not None else "-"
            print(f"\n{source}: {s['within_5_percent']}/{s['cases']} within 5% of the actual payout; mean error {mae}")
    if not stats["real"]["cases"]:
        print("\nNo real settled claims yet. Add some (see cases/_template_real_claim.json) to measure real accuracy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

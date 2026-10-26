"""Add court cases to the database.

Usage (from the backend folder):
    python -m app.precedents.import_cases my_cases.csv
    python -m app.precedents.import_cases my_cases.json

CSV columns are the Case fields (see app/models.py). Separate several reason codes
with '|', e.g. "pre_existing_non_disclosure|exclusion". Leave unknown values empty.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app import db
from app.analyzer.reasons import REASON_LABELS
from app.models import Case
from app.precedents.store import all_cases

NUMBER_FIELDS = ("claim_amount", "awarded_amount")


def _row_to_case(row: dict[str, str]) -> Case:
    data: dict[str, object] = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
    for key, value in list(data.items()):
        if value == "":
            data[key] = None
    data["reason_codes"] = [r.strip() for r in str(data.get("reason_codes") or "").split("|") if r.strip()]
    for key in NUMBER_FIELDS:
        if data.get(key) is not None:
            data[key] = float(str(data[key]).replace(",", ""))
    return Case(**data)


def load(path: Path) -> list[Case]:
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw["cases"] if isinstance(raw, dict) else raw
        return [Case(**c) for c in items]
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [_row_to_case(r) for r in csv.DictReader(f)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        cases = load(args.file)
    except (ValidationError, ValueError, KeyError) as exc:
        print(f"Could not read {args.file}: {exc}", file=sys.stderr)
        return 1
    unknown = {r for c in cases for r in c.reason_codes if r not in REASON_LABELS}
    if unknown:
        print(f"Unknown reason codes: {sorted(unknown)}. Valid codes: {sorted(REASON_LABELS)}", file=sys.stderr)
        return 1
    all_cases()  # make sure the seed cases are present first
    db.upsert_cases(cases, source="imported")
    print(f"Imported {len(cases)} case(s). The database now has {len(db.list_cases())}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

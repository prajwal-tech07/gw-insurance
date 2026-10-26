import json

import pytest
from sklearn.model_selection import StratifiedKFold, cross_val_score

from app.config import DATA_DIR
from app.engine.classifier import build_model, classify_item, match_irdai, training_data
from app.models import BillCategory, BillItem


@pytest.mark.parametrize("line, category", [
    ("ROOM RENT SINGLE AC", BillCategory.room_rent),
    ("ICU BED CHARGES", BillCategory.icu),
    ("INJ. CEFTRIAXONE 1GM", BillCategory.pharmacy),
    ("CAP. OMEPRAZOLE 20MG", BillCategory.pharmacy),
    ("SURGEON FEES", BillCategory.professional_fees),
    ("NURSING SERVICE CHARGES", BillCategory.nursing),
    ("X-RAY CHEST PA", BillCategory.diagnostics),
    ("CORONARY STENT DES", BillCategory.implants),
    ("RECOVERY ROOM CHARGES", BillCategory.ot_charges),
    ("SYRINGE 10ML", BillCategory.consumables),
    ("Dr Rao consultation", BillCategory.professional_fees),
])
def test_categories(line, category):
    assert classify_item(BillItem(description=line, amount=1)).category == category


@pytest.mark.parametrize("line, list_id, item", [
    ("GLOVES STERILE", "I", "Gloves"),
    ("OXYGEN MASK", "I", "Oxygen mask"),
    ("FACE MASK", "II", "Face mask"),
    ("OT CAPS", "II", "Caps"),
    ("ADMISSION KIT", "II", "Admission kit"),
    ("REGISTRATION CHARGES", "IV", "Admission/registration charges"),
    ("X RAY FILM", "III", "X-ray film"),
    ("COTTON BANDAGE", "III", "Cotton bandage"),
    ("FOOD & BEVERAGES", "I", "Food charges (other than patient's diet provided by hospital)"),
])
def test_irdai_list_matches(line, list_id, item):
    m = match_irdai(line)
    assert m is not None and m.list_id == list_id and m.item == item


@pytest.mark.parametrize("line", [
    "CAP. OMEPRAZOLE 20MG", "NURSING SERVICE CHARGES", "X-RAY CHEST PA", "PATIENT DIET",
    "BLOOD SUGAR FASTING", "OXYGEN CHARGES", "INJ. CEFTRIAXONE", "CD4 COUNT",
])
def test_payable_lines_do_not_match_lists(line):
    assert match_irdai(line) is None


def test_list_sizes_match_irdai_circular():
    raw = json.loads((DATA_DIR / "irdai_lists.json").read_text(encoding="utf-8"))
    counts = {}
    for item in raw["items"]:
        counts[item["list"]] = counts.get(item["list"], 0) + 1
    assert counts == {"I": 68, "II": 37, "III": 23, "IV": 18}


def test_model_cross_validated_accuracy():
    texts, labels = training_data()
    scores = cross_val_score(build_model(), texts, labels,
                             cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=0))
    assert scores.mean() >= 0.80

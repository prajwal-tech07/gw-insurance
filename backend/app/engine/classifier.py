"""Hospital bill line classifier.

Three layers, most explainable first:
1. IRDAI List I-IV match (hand-written patterns)  -> is the line payable at all?
2. Keyword rules per category                     -> what kind of charge is it?
3. A small TF-IDF + logistic regression model      -> settles ties and unknown lines.
"""

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline

from app.config import DATA_DIR
from app.models import BillCategory, BillItem, ClassifiedItem

REVIEW_THRESHOLD = 0.5

CATEGORY_RULES: dict[BillCategory, re.Pattern[str]] = {
    BillCategory.implants: re.compile(
        r"\b(implants?|stents?|iol|intraocular|prosthes[ie]s|plates?|screws?|mesh|pacemaker"
        r"|valve|nail|k wire|bone cement|tkr|thr)\b"
    ),
    BillCategory.icu: re.compile(r"\b(icu|iccu|nicu|picu|micu|sicu|ccu|hdu|intensive care|critical care)\b"),
    BillCategory.ot_charges: re.compile(
        r"\b(ot|o t|operation theat(re|er)|theat(re|er)|surgery charges|procedure charges|procedure room"
        r"|cath lab|labour room|recovery room|operation charges)\b"
    ),
    BillCategory.professional_fees: re.compile(
        r"\b(surgeons?|anaesth\w*|anesth\w*|consult\w*|doctors?|dr|physician|visit|professional|specialist"
        r"|cardiologist|neurologist|intensivist|paediatrician|pediatrician|obstetrician"
        r"|gyn(a)?ecologist|orthop(a)?edic)\b"
    ),
    BillCategory.nursing: re.compile(r"\b(nursing|nurse|rmo|dmo|duty medical|resident medical)\b"),
    BillCategory.diagnostics: re.compile(
        r"\b(x ray|xray|mri|ct|hrct|usg|ultrasound|ultrasonography|ecg|echo|echocardiography|cbc|lft|kft|rft"
        r"|lab|laboratory|pathology|radiology|culture|biopsy|histopath\w*|investigations?|hba1c|lipid"
        r"|urine routine|electrolytes|crp|ns1|angiography|thyroid|d dimer|troponin|abg|rt pcr|doppler"
        r"|pet|scan|tests?|profile|count)\b"
    ),
    BillCategory.pharmacy: re.compile(
        r"\b(tab|tabs|tablets?|inj|injection|cap|capsules?|syp|syrup|iv fluids?|ns|dns|rl|medicines?"
        r"|pharmacy|drugs?|ointment|antibiotics?|insulin|respules|infusion|drops|cream|mg|gm|iu)\b"
    ),
    BillCategory.consumables: re.compile(
        r"\b(syringes?|needles?|cannula|catheter|iv set|infusion set|sutures?|vicryl|ryles|dressing|bandages?|tube"
        r"|stopcock|extension line|consumables?|stapler|oxygen|gloves?|masks?|drain|electrodes?)\b"
    ),
    BillCategory.room_rent: re.compile(r"\b(room|bed|ward|accommodation|boarding|suite|lodging|tariff)\b"),
    BillCategory.ambulance: re.compile(r"\bambulance\b"),
}


@dataclass(frozen=True)
class ListMatch:
    list_id: str
    item: str
    span: int


def normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=1)
def _irdai_patterns() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    raw = json.loads((DATA_DIR / "irdai_lists.json").read_text(encoding="utf-8"))
    compiled = []
    for entry in raw["items"]:
        for pattern in entry["patterns"]:
            compiled.append((entry["list"], entry["item"], re.compile(pattern)))
    return tuple(compiled)


@lru_cache(maxsize=1)
def irdai_list_descriptions() -> dict[str, str]:
    return json.loads((DATA_DIR / "irdai_lists.json").read_text(encoding="utf-8"))["lists"]


def match_irdai(description: str) -> ListMatch | None:
    """The IRDAI list item this bill line matches; the longest match wins."""
    text = normalize(description)
    best: ListMatch | None = None
    for list_id, item, pattern in _irdai_patterns():
        m = pattern.search(text)
        if m and (best is None or len(m.group(0)) > best.span):
            best = ListMatch(list_id, item, len(m.group(0)))
    return best


@lru_cache(maxsize=1)
def training_data() -> tuple[list[str], list[str]]:
    with open(DATA_DIR / "bill_training.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r["description"] for r in rows], [r["category"] for r in rows]


def build_model() -> Pipeline:
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), preprocessor=normalize),
        LogisticRegression(max_iter=3000, C=8.0),
    )


@lru_cache(maxsize=1)
def _model() -> Pipeline:
    texts, labels = training_data()
    model = build_model()
    model.fit(texts, labels)
    return model


def rule_categories(description: str) -> set[BillCategory]:
    text = normalize(description)
    return {cat for cat, pattern in CATEGORY_RULES.items() if pattern.search(text)}


def predict_category(description: str, allowed: set[BillCategory] | None = None,
                     model: Pipeline | None = None) -> tuple[BillCategory, float]:
    """Model prediction, optionally restricted to the categories the rules allowed."""
    model = model or _model()
    probs = model.predict_proba([description])[0]
    ranked = sorted(zip(model.classes_, probs), key=lambda p: p[1], reverse=True)
    for label, prob in ranked:
        cat = BillCategory(label)
        if allowed is None or cat in allowed:
            return cat, float(prob)
    label, prob = ranked[0]
    return BillCategory(label), float(prob)


def categorize(description: str, model: Pipeline | None = None) -> tuple[BillCategory, float, str]:
    """(category, confidence, method) for one bill line."""
    matched = rule_categories(description)
    if len(matched) == 1:
        return next(iter(matched)), 0.95, "rules"
    if len(matched) > 1:
        cat, prob = predict_category(description, matched, model)
        return cat, max(prob, 0.7), "model"
    cat, prob = predict_category(description, None, model)
    return cat, prob, "model"


def classify_item(item: BillItem) -> ClassifiedItem:
    if item.category is not None:
        category, confidence, method = item.category, 1.0, "user"
    else:
        category, confidence, method = categorize(item.description)

    match = match_irdai(item.description)
    irdai_list = item.irdai_list or (match.list_id if match else None)
    matched_item = match.item if match else None

    if irdai_list:
        reason = f"IRDAI List {irdai_list}: {irdai_list_descriptions()[irdai_list]}"
        if matched_item:
            reason += f" (matched '{matched_item}')"
        payable = False
    else:
        reason = f"Classified as {category.value.replace('_', ' ')}"
        payable = True

    return ClassifiedItem(
        description=item.description,
        amount=item.amount,
        category=category,
        irdai_list=irdai_list,
        matched_item=matched_item,
        confidence=round(confidence, 3),
        method=method,
        needs_review=method == "model" and confidence < REVIEW_THRESHOLD,
        payable_separately=payable,
        reason=reason,
    )


def classify_items(items: list[BillItem]) -> list[ClassifiedItem]:
    return [classify_item(i) for i in items]

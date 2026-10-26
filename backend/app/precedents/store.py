"""Find past rulings similar to a user's rejection, and summarise how they went.

The outcome estimate is a similarity-weighted vote over similar cases (k-nearest
neighbours). It reports how many cases it is based on, and warns about bias.
"""

import json
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app import db
from app.analyzer.reasons import REASON_LABELS
from app.config import db_path
from app.models import Case, PrecedentMatch, PrecedentSearchResult

SEED_FILE = Path(__file__).with_name("seed_cases.json")
REASON_BOOST = 0.35
SIMILAR_SCORE = 0.25
MIN_RELIABLE = 10
OUTCOME_VALUE = {"policyholder": 1.0, "partly": 0.5, "insurer": 0.0}
BIAS_NOTE = ("These are consumer court rulings reported in the news. Reports mostly cover cases the policyholder won, "
             "and only disputed claims reach court, so real-world odds are lower than these numbers suggest.")

_seeded: set[str] = set()


def load_seed() -> list[Case]:
    raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return [Case(**c) for c in raw["cases"]]


def all_cases() -> list[Case]:
    key = str(db_path())
    if key not in _seeded:
        db.upsert_cases(load_seed(), source="seed")
        _seeded.add(key)
    return db.list_cases()


def _document(c: Case) -> str:
    labels = " ".join(REASON_LABELS.get(r, r) for r in c.reason_codes)
    return f"{c.reason_text}. {labels}. {c.summary} {c.reasoning}"


def search(text: str, reason_codes: list[str] | None = None, k: int = 5) -> PrecedentSearchResult:
    cases = all_cases()
    reason_codes = reason_codes or []
    if not cases or not text.strip():
        return PrecedentSearchResult(matches=[], total_cases=len(cases), similar_cases=0,
                                     outcome_counts={"policyholder": 0, "insurer": 0, "partly": 0},
                                     policyholder_win_rate=None, confidence_note="Enter some text to search.",
                                     bias_note=BIAS_NOTE)

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vectorizer.fit_transform([_document(c) for c in cases] + [text])
    sims = cosine_similarity(matrix[len(cases)], matrix[: len(cases)]).ravel()

    scored = []
    for case, sim in zip(cases, sims):
        overlap = bool(set(reason_codes) & set(case.reason_codes))
        scored.append((min(1.0, float(sim) + (REASON_BOOST if overlap else 0.0)), overlap, case))
    scored.sort(key=lambda s: s[0], reverse=True)

    matches = [PrecedentMatch(case=c, score=round(score, 3)) for score, _, c in scored if score > 0.05][:k]
    similar = [(score, c) for score, overlap, c in scored if overlap or score >= SIMILAR_SCORE]
    counts = Counter(c.outcome for _, c in similar)
    outcome_counts = {o: counts.get(o, 0) for o in ("policyholder", "insurer", "partly")}

    rate = None
    if similar:
        weight = sum(score for score, _ in similar)
        rate = round(sum(score * OUTCOME_VALUE[c.outcome] for score, c in similar) / weight, 3) if weight else None

    n = len(similar)
    if n == 0:
        note = "No similar cases in the database yet."
    elif n < MIN_RELIABLE:
        note = (f"Based on only {n} similar case{'s' if n != 1 else ''}: too few to predict an outcome reliably. "
                "Add more cases to improve this.")
    else:
        note = f"Based on {n} similar cases."
    return PrecedentSearchResult(matches=matches, total_cases=len(cases), similar_cases=n,
                                 outcome_counts=outcome_counts, policyholder_win_rate=rate,
                                 confidence_note=note, bias_note=BIAS_NOTE)

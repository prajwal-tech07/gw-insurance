"""Small text-matching helpers shared by the engine."""

import re

from app.engine.classifier import normalize

STOPWORDS = {
    "treatment", "treatments", "surgery", "surgeries", "expenses", "expense", "related", "charges",
    "hospital", "hospitalisation", "hospitalization", "condition", "conditions", "disease", "diseases",
    "disorder", "disorders", "including", "except", "unless", "other", "their", "which", "arising",
    "caused", "medical", "procedure", "procedures", "therapy", "under", "where", "there", "these",
    "those", "required", "covered", "policy", "insured", "person", "persons", "benefit", "benefits",
}


def contains_term(text: str, term: str) -> bool:
    """True if `term` appears in `text` at a word start (so 'pregnan' matches 'pregnancy')."""
    term_n = normalize(term)
    if not term_n:
        return False
    return re.search(r"\b" + re.escape(term_n), normalize(text)) is not None


def matching_terms(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if contains_term(text, t)]


def significant_words(phrase: str) -> list[str]:
    return [w for w in normalize(phrase).split() if len(w) >= 5 and w not in STOPWORDS]

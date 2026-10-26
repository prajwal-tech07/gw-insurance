"""Combine the rule-based reader with the optional AI reader and verify the AI's quotes."""

import re
from typing import Any

from pydantic import ValidationError

from app.config import llm_enabled
from app.extraction.heuristic import FIELDS, REVIEW_BELOW, Candidate, apply_candidate, extract_candidates
from app.extraction.llm import AIField, ai_extract, parse_ai_value
from app.models import Citation, ExtractedField, ExtractionResult, PolicyTerms


def _norm(text: str) -> str:
    text = text.replace("...", " ").lower()
    text = re.sub(r"[^a-z0-9%₹]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_quote(pages: list[str], page: int, quote: str) -> int | None:
    """The page on which `quote` really appears (cited page first), or None."""
    q = _norm(quote)
    if len(q) < 8:
        return None
    order = ([page] if 1 <= page <= len(pages) else []) + [i for i in range(1, len(pages) + 1) if i != page]
    for p in order:
        text = _norm(pages[p - 1])
        if q in text:
            return p
        words = [w for w in q.split() if len(w) > 2]
        if len(words) >= 5:
            page_words = set(text.split())
            if sum(w in page_words for w in words) / len(words) >= 0.9 and p == page:
                return p
    return None


def _same(a: Candidate, b: Candidate) -> bool:
    return _norm(a.display) == _norm(b.display)


def _merge(key: str, rule: Candidate | None, ai_raw: AIField | None, pages: list[str]) -> tuple[Candidate | None, str, str | None]:
    """Pick the value for one field. Returns (candidate, source, note)."""
    ai = parse_ai_value(key, ai_raw.value) if ai_raw and ai_raw.value.strip() else None
    verified_page = find_quote(pages, ai_raw.page, ai_raw.quote) if ai else None

    if ai and verified_page is not None:
        ai.page, ai.quote = verified_page, ai_raw.quote
        if rule and _same(rule, ai):
            rule.confidence = max(rule.confidence, 0.97)
            return rule, "ai+rules", None
        ai.confidence = min(max(ai_raw.confidence, 0.0), 0.9)
        if rule:
            ai.confidence = min(ai.confidence, 0.6)
            return ai, "ai", f"The rule-based reader found '{rule.display}' on page {rule.page}. Please confirm."
        return ai, "ai", None
    if rule:
        note = "The AI's quote for this could not be found in the document." if ai else None
        return rule, "rules", note
    if ai:
        ai.confidence = 0.3
        return ai, "ai", "The AI's quote could not be found in the document. Check this value."
    return None, "not_found", None


def _build_terms(data: dict[str, Any], warnings: list[str]) -> PolicyTerms:
    for _ in range(10):
        try:
            return PolicyTerms(**data)
        except ValidationError as exc:
            for err in exc.errors():
                top = err["loc"][0]
                if top in data:
                    data.pop(top)
                    warnings.append(f"Ignored an invalid value for '{top}'. Please enter it by hand.")
    return PolicyTerms()


def extract_policy(pages: list[str], use_ai: bool = True, client: Any = None) -> ExtractionResult:
    warnings: list[str] = []
    page_tuples = [(i, t) for i, t in enumerate(pages, 1)]
    rules = extract_candidates(page_tuples)

    ai_fields: dict[str, AIField] | None = None
    if use_ai and (client is not None or llm_enabled()):
        ai_fields, error = ai_extract(pages, client)
        if error:
            warnings.append(f"AI reader not used ({error}); showing the rule-based reader's results.")

    data: dict[str, Any] = {}
    fields: list[ExtractedField] = []
    for key, label, _ in FIELDS:
        cand, source, note = _merge(key, rules.get(key), (ai_fields or {}).get(key), pages)
        if cand is None:
            fields.append(ExtractedField(key=key, label=label, source="not_found", confidence=0, needs_review=True,
                                         note="Not found in the document. Enter it from your policy schedule."))
            continue
        if cand.value is not None:
            apply_candidate(data, key, cand)
        fields.append(ExtractedField(
            key=key, label=label, value=cand.display, confidence=round(cand.confidence, 2),
            citation=Citation(page=cand.page, quote=cand.quote or None), source=source,
            needs_review=cand.confidence < REVIEW_BELOW or note is not None or cand.value is None, note=note))

    if not any(t.strip() for t in pages):
        warnings.append("No text could be read from this document.")
    terms = _build_terms(data, warnings)
    return ExtractionResult(terms=terms, fields=fields, pages=len(pages),
                            method="ai+rules" if ai_fields else "rules", warnings=warnings)

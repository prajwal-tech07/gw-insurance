"""Rule-based policy reader. Works offline and for free.

Every finding keeps the page number and the exact text it came from, so the user
(and the AI cross-check) can verify it. Anything uncertain is marked for review.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from app.extraction.parsing import (
    DATE,
    RUPEE,
    inr,
    parse_date,
    parse_days,
    parse_duration_months,
    to_amount,
)
from app.models import RoomLimit, SubLimit

Page = tuple[int, str]  # (1-based page number, text)
REVIEW_BELOW = 0.8


@dataclass
class Candidate:
    value: Any
    display: str
    page: int | None
    quote: str
    confidence: float


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def snippet(text: str, start: int, end: int, pad: int = 40) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    return ("..." if s > 0 else "") + text[s:e].strip() + ("..." if e < len(text) else "")


def _pick(cands: list[Candidate], key: Callable[[Candidate], Any] = lambda c: c.display) -> Candidate | None:
    """Most common value wins; disagreement lowers confidence."""
    if not cands:
        return None
    counts = Counter(key(c) for c in cands)
    top, _ = counts.most_common(1)[0]
    best = next(c for c in cands if key(c) == top)
    if len(counts) > 1:
        best.confidence = min(best.confidence, 0.6)
    return best


ABBREVIATIONS = re.compile(r"\b(rs|no|max|min|approx|viz|sr|e\.g|i\.e)\.", re.I)
SENTENCE_END = re.compile(r"\.\s+(?=[A-Z0-9(])|;\s|\.$")


def _windows(pages: list[Page], keyword: re.Pattern[str], width: int, stop: re.Pattern[str] | None = None):
    """Text after each keyword match, up to the end of its sentence (or a stop word)."""
    for pno, raw in pages:
        text = flat(raw)
        for m in keyword.finditer(text):
            window = ABBREVIATIONS.sub(r"\1", text[m.start(): m.start() + width])
            keyword_len = len(ABBREVIATIONS.sub(r"\1", m.group(0)))
            end = SENTENCE_END.search(window, keyword_len)
            if end:
                window = window[: end.start()]
            if stop:
                s = stop.search(window, keyword_len)
                if s:
                    window = window[: s.start()]
            yield pno, text, m.start(), window


# ------------------------------------------------------------------ amounts / limits

SUM_INSURED = re.compile(
    rf"sum\s+insured(?:\s*\(\s*(?:in\s+)?{RUPEE}\s*\))?(?:\s+(?:amount|opted|selected|per\s+policy|per\s+family|\(basic\)))?"
    rf"(?:\s+(?:of|is))?\s*[:\-–]?\s*{RUPEE}?\s*(\d[\d,]*(?:\.\d+)?)(\s*(?:lakhs?|lacs?|lac|crores?|cr\b))?",
    re.I,
)


# "INR 50,000/ 1 lac/ 1.5 lac" or "5.5 lakhs and above" list options or conditions, not your cover.
SI_OPTIONS_AFTER = re.compile(r"^\s*(?:/|and\s+above|or\s+above|& above|onwards|to\s+(?:rs\.?|inr|₹)?\s*\d|-\s*\d|in\s+multiples)", re.I)


def find_sum_insured(pages: list[Page]) -> Candidate | None:
    cands = []
    for pno, raw in pages:
        text = flat(raw)
        for m in SUM_INSURED.finditer(text):
            value = to_amount(m.group(1), (m.group(2) or "").strip())
            if value and value >= 10_000:
                options = SI_OPTIONS_AFTER.match(text[m.end(): m.end() + 30])
                cands.append(Candidate(value, inr(value), pno, snippet(text, m.start(), m.end()), 0.4 if options else 0.9))
    confident = [c for c in cands if c.confidence > 0.4]
    return _pick(confident or cands)


PERCENT_OF_SI = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s*)?(?:the\s*)?(?:basic\s+)?(?:sum\s*insured|s\.?\s?i\.?\b)", re.I)
CAP = re.compile(rf"(?:max(?:imum)?(?:\s+of)?|up\s*to|upto|capped\s+at|limited\s+to|not\s+exceeding)\s*{RUPEE}\s*(\d[\d,]*)", re.I)
PER_DAY = re.compile(rf"{RUPEE}\s*(\d[\d,]*)\s*(?:/-)?\s*(?:per\s*day|/\s*day|a\s+day|daily|per\s+diem)", re.I)
CATEGORY = re.compile(
    r"((?:single|shared|twin[- ]sharing|semi[- ]private|private|general|deluxe)\s+(?:private\s+)?(?:a\.?c\.?\s+)?(?:room|ward))",
    re.I)
NO_LIMIT = re.compile(
    r"no\s+(?:room\s*rent\s+|icu\s+)?(?:limit|cap|capping|restriction|sub-?limit)|without\s+any\s+(?:limit|cap|capping)"
    r"|any\s+room(?:\s+category)?|up\s*to\s+(?:the\s+)?sum\s+insured|actuals?\b", re.I)


def parse_room_limit(window: str) -> tuple[RoomLimit, float] | None:
    """(limit, confidence) from a phrase like 'up to 1% of SI subject to max Rs 5,000 per day'."""
    pct = PERCENT_OF_SI.search(window)
    if pct:
        cap = CAP.search(window) or PER_DAY.search(window)
        amount = to_amount(cap.group(1)) if cap else None
        return RoomLimit(kind="percent_of_si", percent=float(pct.group(1)), amount=amount), 0.9
    per_day = PER_DAY.search(window)
    if per_day:
        return RoomLimit(kind="fixed", amount=to_amount(per_day.group(1))), 0.9
    cat = CATEGORY.search(window)
    if cat:
        return RoomLimit(kind="category", category=cat.group(1).strip()), 0.8
    if NO_LIMIT.search(window):
        return RoomLimit(kind="none"), 0.75
    return None


def describe_limit(limit: RoomLimit) -> str:
    if limit.kind == "percent_of_si":
        cap = f", max {inr(limit.amount)}/day" if limit.amount else ""
        return f"{limit.percent:g}% of sum insured per day{cap}"
    if limit.kind == "fixed":
        return f"{inr(limit.amount or 0)} per day"
    if limit.kind == "category":
        return f"Room category: {limit.category}"
    return "No limit"


ROOM_KEY = re.compile(r"room\s*rent|room\s*,?\s*boarding|room\s+charges|room\s+category|accommodation\s+charges", re.I)
ICU_KEY = re.compile(r"\bi\.?c\.?u\.?\b|intensive\s+care|\biccu\b", re.I)


def _find_limit(pages: list[Page], key: re.Pattern[str], stop: re.Pattern[str]) -> Candidate | None:
    cands = []
    for pno, text, start, window in _windows(pages, key, 260, stop):
        parsed = parse_room_limit(window)
        if parsed:
            limit, conf = parsed
            cands.append(Candidate(limit, describe_limit(limit), pno,
                                   snippet(text, start, start + len(window), 10), conf))
    if not cands:
        return None
    best_conf = max(c.confidence for c in cands)
    return _pick([c for c in cands if c.confidence == best_conf])


def find_room_rent(pages: list[Page]) -> Candidate | None:
    return _find_limit(pages, ROOM_KEY, ICU_KEY)


def find_icu(pages: list[Page]) -> Candidate | None:
    return _find_limit(pages, ICU_KEY, ROOM_KEY)


COPAY_KEY = re.compile(r"co-?\s?pay(?:ment)?", re.I)
NO_COPAY = re.compile(r"no\s+co-?\s?pay|co-?\s?pay(?:ment)?\s*[:\-]?\s*(?:nil|none|not\s+applicable|0\s*%)", re.I)
AGE = re.compile(r"(?:aged?\s*(?:of\s*)?|above\s+(?:the\s+age\s+of\s+)?|over\s+|beyond\s+|more\s+than\s+)(\d{2})\s*(?:years|yrs)?"
                 r"|(\d{2})\s*(?:years|yrs)\s*(?:of\s+age\s*)?(?:and|&|or)\s*(?:above|older|more)", re.I)


def find_copay(pages: list[Page]) -> Candidate | None:
    cands = []
    for pno, text, start, window in _windows(pages, COPAY_KEY, 220):
        quote = snippet(text, start, start + len(window), 10)
        if NO_COPAY.search(window):
            cands.append(Candidate((0.0, None), "No co-pay", pno, quote, 0.8))
            continue
        pct = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", window)
        if not pct:
            continue
        age = AGE.search(window)
        min_age = int(age.group(1) or age.group(2)) if age else None
        display = f"{float(pct.group(1)):g}% of every claim" + (f" (age {min_age}+)" if min_age else "")
        cands.append(Candidate((float(pct.group(1)), min_age), display, pno, quote, 0.85))
    return _pick(cands)


DEDUCTIBLE_KEY = re.compile(r"\b(?:aggregate\s+)?deductible\b", re.I)


def find_deductible(pages: list[Page]) -> Candidate | None:
    cands = []
    for pno, text, start, window in _windows(pages, DEDUCTIBLE_KEY, 120):
        quote = snippet(text, start, start + len(window), 10)
        if re.search(r"no\s+deductible|deductible\s*[:\-]?\s*(?:nil|none|not\s+applicable)", window, re.I):
            cands.append(Candidate(0.0, "No deductible", pno, quote, 0.8))
            continue
        m = re.search(rf"{RUPEE}\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?)?|(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?)", window, re.I)
        if m:
            value = to_amount(m.group(1) or m.group(3), m.group(2) or m.group(4))
            if value and value >= 1_000:
                cands.append(Candidate(value, inr(value), pno, quote, 0.85))
    return _pick(cands)


def find_cumulative_bonus(pages: list[Page]) -> Candidate | None:
    for pno, raw in pages:
        text = flat(raw)
        m = re.search(rf"cumulative\s+bonus\s*(?:\(\s*cb\s*\))?\s*(?:accrued|earned|amount)?\s*[:\-]?\s*{RUPEE}\s*(\d[\d,]*)", text, re.I)
        if m:
            value = to_amount(m.group(1))
            return Candidate(value, inr(value), pno, snippet(text, m.start(), m.end()), 0.8)
    for pno, raw in pages:
        text = flat(raw)
        m = re.search(r"(?:cumulative|no[- ]claim)\s+bonus[^.]{0,150}?(\d{1,3})\s*%", text, re.I)
        if m:
            return Candidate(None, f"{m.group(1)}% for each claim-free year (enter the bonus you have earned)",
                             pno, snippet(text, m.start(), m.end()), 0.5)
    return None


# ------------------------------------------------------------------ waiting periods

INITIAL = [
    re.compile(r"initial\s+waiting\s+period\s*(?:of)?\s*[:\-]?\s*(\d{1,3}|thirty|ninety)\s*(?:\(\s*\d+\s*\)\s*)?days", re.I),
    re.compile(r"(?:first|initial)\s+(\d{1,3}|thirty|ninety)\s*(?:\(\s*\d+\s*\)\s*)?days", re.I),
    re.compile(r"(\d{1,3})\s*days\s+(?:waiting|from\s+(?:the\s+)?(?:first\s+)?(?:policy\s+)?(?:commencement|inception|start))", re.I),
]


def find_initial_waiting(pages: list[Page]) -> Candidate | None:
    cands = []
    for pno, raw in pages:
        text = flat(raw)
        for pattern in INITIAL:
            for m in pattern.finditer(text):
                days = parse_days(m.group(0))
                if days and days <= 120:
                    cands.append(Candidate(days, f"{days} days", pno, snippet(text, m.start(), m.end()), 0.85))
    return _pick(cands)


WAIT_CONTEXT = re.compile(r"wait|after|until|expir|excluded|covered|continuous|completion", re.I)
NOT_WAIT = re.compile(r"moratorium|sixty\s+continuous|60\s+continuous|portab|free\s+look|grace", re.I)


TIERED_MONTHS = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{1,2}))?\s*months", re.I)


def _months_near(pages: list[Page], key: re.Pattern[str], width: int = 240) -> list[Candidate]:
    cands = []
    for pno, text, start, window in _windows(pages, key, width):
        if not WAIT_CONTEXT.search(window) or NOT_WAIT.search(window):
            continue
        quote = snippet(text, start, start + min(len(window), 200), 10)
        tiered = TIERED_MONTHS.search(window)
        if tiered:  # e.g. "24/36 months": depends on the condition, so use the longer one
            options = [int(g) for g in tiered.groups() if g]
            longest = max(options)
            cands.append(Candidate(longest, f"{'/'.join(map(str, options))} months depending on the condition "
                                            f"(using {longest} to be safe)", pno, quote, 0.5))
            continue
        months = parse_duration_months(window)
        if months and 6 <= months <= 72:
            cands.append(Candidate(months, f"{months} months", pno, quote, 0.85))
    return cands


PED_KEY = re.compile(r"pre[- ]?existing\s+(?:diseases?|conditions?|illness(?:es)?|ailments?)|\bPED\b", re.I)
SPECIFIC_KEY = re.compile(
    r"specific(?:ied)?\s+(?:diseases?|illness(?:es)?|waiting|conditions?|procedures?)|(?:listed|named)\s+(?:conditions|diseases|illnesses)",
    re.I)
MATERNITY_KEY = re.compile(r"maternity|childbirth", re.I)


def find_ped_waiting(pages: list[Page]) -> Candidate | None:
    return _pick(_months_near(pages, PED_KEY))


def find_specific_waiting(pages: list[Page]) -> Candidate | None:
    return _pick(_months_near(pages, SPECIFIC_KEY))


def find_maternity_waiting(pages: list[Page]) -> Candidate | None:
    return _pick(_months_near(pages, MATERNITY_KEY))


DISEASE_VOCAB: dict[str, list[str]] = {
    "Cataract": ["cataract"],
    "Hernia": ["hernia"],
    "Hydrocele": ["hydrocele"],
    "Piles / haemorrhoids": ["piles", "haemorrhoid", "hemorrhoid"],
    "Fissure / fistula": ["fissure", "fistula"],
    "Sinusitis": ["sinusitis"],
    "Tonsils / adenoids": ["tonsil", "adenoid"],
    "Gall bladder stones": ["gall bladder", "gallbladder", "cholecyst", "gall stone", "gallstone"],
    "Kidney / urinary stones": ["kidney stone", "renal stone", "urolithiasis", "urinary stone", "calculus", "calculi"],
    "Prostate": ["prostat", "bph"],
    "Hysterectomy / uterus": ["hysterectomy", "uterus", "uterine"],
    "Fibroids": ["fibroid"],
    "Joint replacement": ["joint replacement", "knee replacement", "hip replacement"],
    "Osteoarthritis": ["osteoarthritis"],
    "Varicose veins": ["varicose"],
    "Glaucoma": ["glaucoma"],
    "Deviated nasal septum": ["nasal septum", "septoplasty"],
    "Spinal disorders": ["spinal", "disc prolapse", "intervertebral"],
    "Gout": ["gout"],
    "Benign tumours / cysts / polyps": ["benign tumour", "benign tumor", "cyst", "polyp"],
    "Gastric / duodenal ulcers": ["ulcer"],
    "Pancreatitis": ["pancreatitis"],
    "Endometriosis": ["endometriosis"],
    "Polycystic ovaries": ["polycystic"],
}


def find_specific_diseases(pages: list[Page]) -> Candidate | None:
    for idx, (pno, raw) in enumerate(pages):
        text = flat(raw)
        m = SPECIFIC_KEY.search(text)
        if not m:
            continue
        section = text[m.start(): m.start() + 2500]
        if idx + 1 < len(pages) and len(section) < 2500:
            section += " " + flat(pages[idx + 1][1])[: 2500 - len(section)]
        found = [name for name, words in DISEASE_VOCAB.items()
                 if any(re.search(r"\b" + re.escape(w), section, re.I) for w in words)]
        if found:
            terms = sorted({w for name in found for w in DISEASE_VOCAB[name]})
            return Candidate(terms, ", ".join(found), pno, snippet(text, m.start(), m.end(), 80), 0.6)
    return None


# ------------------------------------------------------------------ sub-limits, add-ons, exclusions

PROCEDURES: dict[str, list[str]] = {
    "Cataract": ["cataract"],
    "Knee replacement": ["knee replacement", "total knee"],
    "Hip replacement": ["hip replacement"],
    "Joint replacement": ["joint replacement"],
    "Hernia": ["hernia"],
    "Hysterectomy": ["hysterectomy"],
    "Kidney stones": ["lithotripsy", "kidney stone", "renal stone"],
    "Angioplasty": ["angioplasty", "ptca"],
    "Bypass surgery": ["bypass", "cabg"],
}
LIMIT_WORDS = re.compile(r"limit|maximum|max\b|up\s*to|upto|capped|restricted|whichever\s+is\s+(?:lower|less)|per\s+eye", re.I)


def find_sub_limits(pages: list[Page]) -> Candidate | None:
    found: dict[str, tuple[SubLimit, int, str]] = {}
    for name, words in PROCEDURES.items():
        key = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")", re.I)
        for pno, text, start, window in _windows(pages, key, 170):
            window = re.split(r"[.;](?:\s|$)", window, maxsplit=1)[0]
            if not LIMIT_WORDS.search(window):
                continue
            amt = re.search(rf"{RUPEE}\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/-)?\s*(lakhs?|lacs?)?", window, re.I)
            pct = PERCENT_OF_SI.search(window)
            amount = to_amount(amt.group(1), amt.group(2)) if amt else None
            percent = float(pct.group(1)) if pct else None
            if amount or percent:
                found.setdefault(name, (SubLimit(name=name, keywords=words, amount=amount, percent_of_si=percent),
                                        pno, snippet(text, start, start + len(window), 10)))
                break
    if not found:
        return None
    subs = [v[0] for v in found.values()]
    first = next(iter(found.values()))

    def show(s: SubLimit) -> str:
        parts = [inr(s.amount)] if s.amount else []
        if s.percent_of_si:
            parts.append(f"{s.percent_of_si:g}% of SI")
        return f"{s.name}: {' or '.join(parts)}"

    return Candidate(subs, "; ".join(show(s) for s in subs), first[1], first[2], 0.75)


ADDON_STATE = r"[^.\n]{0,60}?\b(opted|yes|covered|included|applicable|available|not\s+opted|no|not\s+applicable|not\s+covered)\b"


def _find_addon(pages: list[Page], name_pattern: str) -> Candidate | None:
    pattern = re.compile(name_pattern + ADDON_STATE, re.I)
    for pno, raw in pages:
        text = flat(raw)
        m = pattern.search(text)
        if m:
            state = m.group(1).lower()
            on = not (state.startswith("not") or state == "no")
            return Candidate(on, "Yes" if on else "No", pno, snippet(text, m.start(), m.end()), 0.6)
    return None


def find_consumables_cover(pages: list[Page]) -> Candidate | None:
    return _find_addon(pages, r"consumables?\s+(?:cover|benefit|add[- ]?on)")


def find_room_rent_waiver(pages: list[Page]) -> Candidate | None:
    return _find_addon(pages, r"room\s+rent\s+(?:limit\s+)?waiver")


EXCL_CODE = re.compile(r"([A-Z0-9][A-Za-z0-9 ,&/'\-]{3,90}?)\s*[(\[]?\s*Code\s*[-–:]?\s*Excl\s*\d{1,2}", re.I)
BULLET = re.compile(r"^\s*(?:[-•*▪]|\(?[a-z0-9ivx]{1,4}[.)])\s+(.{4,110})$", re.I)


def find_exclusions(pages: list[Page]) -> Candidate | None:
    names: list[str] = []
    first: tuple[int, str] | None = None
    for pno, raw in pages:
        text = flat(raw)
        for m in EXCL_CODE.finditer(text):
            name = re.sub(r"^\(?\d{1,2}[.)]\s+", "", m.group(1)).strip(" ,-:")  # drop list numbering only
            if name and name.lower() not in (n.lower() for n in names):
                names.append(name)
                first = first or (pno, snippet(text, m.start(), m.end(), 0))
    confidence = 0.8
    if not names:
        confidence = 0.55
        for pno, raw in pages:
            lines = raw.splitlines()
            for i, line in enumerate(lines):
                if re.match(r"^\s*(?:permanent\s+|general\s+|standard\s+)?exclusions?\b", line, re.I):
                    for nxt in lines[i + 1: i + 25]:
                        b = BULLET.match(nxt)
                        if b:
                            names.append(b.group(1).strip().rstrip(";.,"))
                    if names:
                        first = (pno, line.strip())
                        break
            if names:
                break
    if not names:
        return None
    names = names[:30]
    shown = "; ".join(names[:6]) + (f" (+{len(names) - 6} more)" if len(names) > 6 else "")
    return Candidate(names, shown, first[0] if first else None, first[1] if first else "", confidence)


# ------------------------------------------------------------------ dates, names, kind

INCEPTION = re.compile(
    r"(?:(?:date\s+of\s+)?(?:first\s+)?(?:policy\s+)?(?:inception|commencement)(?:\s+date)?"
    r"(?:\s+of\s+(?:the\s+)?(?:first\s+)?(?:policy|cover(?:age)?))?(?:\s+with\s+us)?"
    r"|(?:continuous|continuity\s+of)\s+cover(?:age)?\s+since|insured\s+since|member\s+since)\s*[:\-]?\s*" + DATE,
    re.I)
PERIOD = re.compile(r"(?:policy\s+)?period(?:\s+of\s+(?:insurance|cover))?\s*[:\-]?\s*(?:from\s*)?" + DATE
                    + r"[^.]{0,40}?(?:to|till|until|–|-)\s*" + DATE, re.I)


def find_inception(pages: list[Page]) -> Candidate | None:
    for pno, raw in pages:
        text = flat(raw)
        for m in INCEPTION.finditer(text):
            d = parse_date(m.group(1))
            if d:
                return Candidate(d, d.strftime("%d %b %Y"), pno, snippet(text, m.start(), m.end()), 0.85)
    return None


def find_period(pages: list[Page]) -> Candidate | None:
    for pno, raw in pages:
        text = flat(raw)
        for m in PERIOD.finditer(text):
            a, b = parse_date(m.group(1)), parse_date(m.group(2))
            if a and b and b > a:
                return Candidate((a, b), f"{a:%d %b %Y} to {b:%d %b %Y}", pno, snippet(text, m.start(), m.end()), 0.85)
    return None


def find_pre_post(pages: list[Page]) -> Candidate | None:
    pre = post = None
    page = quote = None
    for pno, raw in pages:
        text = flat(raw)
        a = re.search(r"pre[- ]?hospitali[sz]ation[^.]{0,90}?(\d{2,3})\s*days", text, re.I)
        b = re.search(r"post[- ]?hospitali[sz]ation[^.]{0,90}?(\d{2,3})\s*days", text, re.I)
        if a and pre is None:
            pre, page, quote = int(a.group(1)), pno, snippet(text, a.start(), a.end())
        if b and post is None:
            post = int(b.group(1))
            page = page or pno
            quote = quote or snippet(text, b.start(), b.end())
    if pre is None and post is None:
        return None
    return Candidate((pre, post), f"{pre or '?'} days before / {post or '?'} days after", page, quote or "", 0.8)


INSURER = re.compile(
    r"\b((?:The\s+)?[A-Z][A-Za-z&.\-]*(?:\s+[A-Z][A-Za-z&.\-]*){0,5}\s+(?:General\s+|Health\s+|Allied\s+)?"
    r"(?:Insurance|Assurance)\s+(?:Company|Co\.?)(?:\s+(?:of\s+India\s+)?(?:Ltd|Limited)\.?)?)")


def find_insurer(pages: list[Page]) -> Candidate | None:
    for pno, raw in pages[:3]:
        for line in raw.splitlines():  # per line, so a heading never merges into the name
            m = INSURER.search(line)
            if m:
                name = m.group(1).strip()
                return Candidate(name, name, pno, line.strip(), 0.8)
    return None


def find_policy_name(pages: list[Page]) -> Candidate | None:
    for pno, raw in pages[:3]:
        m = re.search(r"(?:policy|product|plan)\s+name\s*[:\-]\s*([^\n]{3,80})", raw, re.I)
        if m:
            name = m.group(1).strip()
            return Candidate(name, name, pno, m.group(0).strip(), 0.85)
    doc_type = re.compile(r"^\s*(?:policy\s+wordings?|prospectus|customer\s+information\s+sheet|policy\s+schedule)\s*[-–:]?\s*", re.I)
    for pno, raw in pages[:1]:
        for line in raw.splitlines()[:15]:
            original = line.strip()
            name = doc_type.sub("", original).split(",")[0].strip(" -–")
            if 4 <= len(name) <= 70 and re.search(r"\b(policy|plan|mediclaim|arogya|health|shield)\b", name, re.I) \
                    and not re.search(r"(insurance|assurance)\s+(company|co)", name, re.I) and name.lower() != "policy":
                return Candidate(name, name, pno, original, 0.5)
    return None


def find_policy_kind(pages: list[Page]) -> Candidate | None:
    text = " ".join(flat(raw) for _, raw in pages[:4])
    for pattern, kind, label in [
        (r"super\s+top[- ]?up", "super_top_up", "Super top-up"),
        (r"\btop[- ]?up\b", "top_up", "Top-up"),
        (r"group\s+(?:mediclaim|health)", "group", "Group (employer) policy"),
        (r"family\s+floater|\bfloater\b", "family_floater", "Family floater"),
        (r"policy\s+type\s*[:\-]?\s*individual|\bindividual\s+(?:policy|cover|plan|basis)", "individual", "Individual"),
    ]:
        m = re.search(pattern, text, re.I)
        if m:
            return Candidate(kind, label, None, snippet(text, m.start(), m.end()), 0.6)
    return None


# ------------------------------------------------------------------ registry

FIELDS: list[tuple[str, str, Callable[[list[Page]], Candidate | None]]] = [
    ("insurer", "Insurer", find_insurer),
    ("policy_name", "Policy name", find_policy_name),
    ("policy_kind", "Policy type", find_policy_kind),
    ("sum_insured", "Sum insured", find_sum_insured),
    ("room_rent", "Room rent limit", find_room_rent),
    ("icu_limit", "ICU limit", find_icu),
    ("copay", "Co-pay", find_copay),
    ("deductible", "Deductible", find_deductible),
    ("cumulative_bonus", "Cumulative bonus", find_cumulative_bonus),
    ("initial_waiting", "Initial waiting period", find_initial_waiting),
    ("ped_waiting", "Pre-existing disease waiting period", find_ped_waiting),
    ("specific_waiting", "Specific disease waiting period", find_specific_waiting),
    ("specific_diseases", "Diseases with a specific waiting period", find_specific_diseases),
    ("maternity_waiting", "Maternity waiting period", find_maternity_waiting),
    ("sub_limits", "Sub-limits", find_sub_limits),
    ("consumables_cover", "Consumables cover", find_consumables_cover),
    ("room_rent_waiver", "Room rent waiver", find_room_rent_waiver),
    ("exclusions", "Exclusions", find_exclusions),
    ("first_inception_date", "Cover first started", find_inception),
    ("policy_period", "Policy period", find_period),
    ("pre_post", "Pre/post hospitalisation", find_pre_post),
]

FIELD_LABELS = {key: label for key, label, _ in FIELDS}


def extract_candidates(pages: list[Page]) -> dict[str, Candidate | None]:
    return {key: finder(pages) for key, _, finder in FIELDS}


def candidate_for_text(key: str, text: str, page: int | None) -> Candidate | None:
    """Re-parse a short text (e.g. an AI-supplied quote) with the same rules as the full reader."""
    finder = next(f for k, _, f in FIELDS if k == key)
    cand = finder([(page or 1, text)])
    if cand:
        cand.page = page
    return cand


def apply_candidate(terms_data: dict[str, Any], key: str, cand: Candidate) -> None:
    """Write one field's value into a PolicyTerms-shaped dict."""
    v = cand.value
    waiting = terms_data.setdefault("waiting", {})
    if key == "insurer":
        terms_data["insurer"] = v
    elif key == "policy_name":
        terms_data["policy_name"] = v
    elif key == "policy_kind":
        terms_data["policy_kind"] = v
    elif key == "sum_insured":
        terms_data["sum_insured"] = v
    elif key == "room_rent":
        terms_data["room_rent"] = v
    elif key == "icu_limit":
        terms_data["icu_limit"] = v
    elif key == "copay":
        terms_data["copay_percent"], terms_data["copay_min_age"] = v
    elif key == "deductible":
        terms_data["deductible"] = v
    elif key == "cumulative_bonus" and v is not None:
        terms_data["cumulative_bonus_amount"] = v
    elif key == "initial_waiting":
        waiting["initial_days"] = v
    elif key == "ped_waiting":
        waiting["pre_existing_months"] = v
    elif key == "specific_waiting":
        waiting["specific_disease_months"] = v
    elif key == "specific_diseases":
        waiting["specific_diseases"] = v
    elif key == "maternity_waiting":
        waiting["maternity_months"] = v
    elif key == "sub_limits":
        terms_data["sub_limits"] = v
    elif key == "consumables_cover":
        terms_data["consumables_cover"] = v
    elif key == "room_rent_waiver":
        terms_data["room_rent_waiver"] = v
    elif key == "exclusions":
        terms_data["exclusions"] = v
    elif key == "first_inception_date":
        terms_data["first_inception_date"] = v
    elif key == "policy_period":
        terms_data["period_start"], terms_data["period_end"] = v
    elif key == "pre_post":
        terms_data["pre_hospitalisation_days"], terms_data["post_hospitalisation_days"] = v

"""Find benefits people often forget they have: health check-ups, teleconsults, AYUSH, home care...

Every finding keeps the page and the sentence it came from. A benefit counts only where
the sentence grants it ("we will cover", "entitled to", "up to Rs 2,000", "Health
Check-up: ..."); passing mentions, definitions and the table of contents are skipped.
A benefit mentioned in an exclusion ("OPD treatment is not covered") or under an
exclusions heading is reported as not covered, and an add-on as optional, so the list
never promises a benefit the policy denies.
"""

import re
from dataclasses import dataclass

from app.extraction.heuristic import ABBREVIATIONS, PERCENT_OF_SI, Candidate, Page, flat
from app.extraction.parsing import RUPEE, inr, to_amount
from app.models import BenefitInfo, BenefitStatus, Citation, PolicyBenefit


@dataclass(frozen=True)
class BenefitType:
    key: str
    name: str
    pattern: re.Pattern[str]
    what: str
    how_to_use: str
    resets_yearly: bool = False
    skip: re.Pattern[str] | None = None  # matches in the sentence that are not this benefit


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


CATALOGUE: list[BenefitType] = [
    BenefitType(
        "health_checkup", "Free health check-up",
        _p(r"health\s*check[- ]?ups?|preventive\s+(?:health|medical)|annual\s+(?:medical\s+)?check[- ]?ups?"),
        "A free or reimbursed health check-up, usually once a policy year or after claim-free years.",
        "Book it through the insurer's app or helpline before the policy year ends. Unused check-ups usually do not carry over.",
        resets_yearly=True,
        skip=_p(r"pre[- ]?(?:policy|acceptance|insurance|proposal)\s+(?:medical\s+|health\s+)?check|medical\s+examination\s+before"),
    ),
    BenefitType(
        "teleconsultation", "Doctor on phone / video",
        _p(r"tele[- ]?consult\w*|tele[- ]?medicine|e[- ]consult\w*|online\s+(?:doctor\s+)?consultation|video\s+consultation"),
        "Talk to a doctor by phone or video, often free.",
        "Use the insurer's app or helpline for minor illnesses and follow-ups before paying a clinic.",
    ),
    BenefitType(
        "opd", "Out-patient (OPD) cover",
        _p(r"out[- ]?patient|\bOPD\b"),
        "Doctor visits, medicines or tests without being admitted, up to a limit.",
        "Keep bills and prescriptions for every doctor visit, medicine and test, and claim them as the policy describes.",
        resets_yearly=True,
        skip=_p(r"(?:out[- ]?patient|\bopd)\s+basis"),  # how a treatment is given, not OPD cover
    ),
    BenefitType(
        "domiciliary", "Treatment at home",
        _p(r"domiciliary|home\s+(?:care\s+)?treatment|home\s+hospitali[sz]ation|treatment\s+at\s+home"),
        "Treatment at home when a doctor advises hospital care but the patient cannot be moved or no bed is available.",
        "Get the doctor's written advice and keep daily treatment records and bills; claim it like a hospital stay.",
    ),
    BenefitType(
        "ayush", "AYUSH treatment",
        _p(r"\bAYUSH\b|ayurved\w*|homo?eopath\w*|\bunani\b|\bsiddha\b|naturopath\w*"),
        "Hospital treatment under Ayurveda, Yoga, Unani, Siddha or Homeopathy.",
        "Use a government-recognised AYUSH hospital and check any limit before admission.",
    ),
    BenefitType(
        "day_care", "Day-care procedures",
        _p(r"day[- ]?care"),
        "Treatments that need less than 24 hours in hospital, such as dialysis, chemotherapy or cataract surgery.",
        "Claim these even without an overnight stay: the 24-hour admission rule does not apply to day-care procedures.",
    ),
    BenefitType(
        "restore", "Sum insured restored",
        _p(r"restor(?:e|ation)\s+(?:benefit|of\s+(?:the\s+)?(?:basic\s+)?sum\s+insured)|recharge\s+(?:benefit|of\s+(?:the\s+)?sum)"
           r"|reinstat\w*\s+(?:benefit|of\s+(?:the\s+)?sum\s+insured)|refill\s+benefit|automatic\s+(?:restoration|recharge)"),
        "If the cover is used up during the year, the insurer tops it up again (often only for a different illness).",
        "If a big claim uses up your sum insured, ask the insurer to apply this benefit for the next admission.",
    ),
    BenefitType(
        "ambulance", "Ambulance charges",
        _p(r"\b(?:road\s+|air\s+)?ambulance\b(?!\s+(?:collar|equipment))"),
        "Ambulance charges to a hospital or between hospitals, up to a limit.",
        "Keep the ambulance bill and payment receipt and send them with the claim.",
    ),
    BenefitType(
        "organ_donor", "Organ donor expenses",
        _p(r"organ\s+donor"),
        "The cost of removing an organ from the donor for your transplant.",
        "Ask the hospital to bill the donor's surgery under your claim.",
    ),
    BenefitType(
        "hospital_cash", "Daily hospital cash",
        _p(r"(?:daily|hospital)\s+cash|daily\s+(?:cash\s+)?allowance"),
        "A fixed amount for each day in hospital, paid on top of the bill.",
        "Ask for it with your hospitalisation claim; it is often missed.",
    ),
    BenefitType(
        "second_opinion", "Second medical opinion",
        _p(r"second\s+(?:medical\s+)?opinion"),
        "A second opinion from another specialist before major treatment.",
        "Ask the insurer for it before a planned surgery or a serious diagnosis.",
    ),
    BenefitType(
        "wellness", "Wellness rewards",
        _p(r"wellness|reward\s+points|healthy\s+(?:days|steps)|fitness\s+(?:reward|discount)"),
        "Points or discounts for staying active, often lowering the renewal premium.",
        "Link the insurer's app or send your step counts or check-up results before renewal.",
        resets_yearly=True,
    ),
    BenefitType(
        "modern_treatment", "Modern treatments",
        _p(r"modern\s+treatments?|advanced\s+(?:treatments?|technolog\w+)|robotic\s+surger\w*|immunotherap\w*"
           r"|oral\s+chemotherap\w*|stem\s+cell|balloon\s+sinuplasty|deep\s+brain\s+stimulation"),
        "Newer treatments such as robotic surgery, immunotherapy or oral chemotherapy, sometimes with a limit.",
        "Check the limit for the treatment before agreeing to it.",
    ),
    BenefitType(
        "mental_health", "Mental illness cover",
        _p(r"mental\s+illness|psychiatric|mental\s+health\s+(?:treatment|care|disorders?)"),
        "Treatment, and in some policies counselling, for mental illness, as the policy describes.",
        "Claim it like any other illness, and use any counselling service the policy offers.",
    ),
    BenefitType(
        "newborn", "Newborn baby cover",
        _p(r"new[- ]?born"),
        "Cover for a newborn baby, sometimes with vaccinations.",
        "Tell the insurer soon after the birth and add the baby as the policy requires.",
    ),
    BenefitType(
        "pre_post", "Bills before and after a hospital stay",
        _p(r"pre[- ]?hospitali[sz]ation|post[- ]?hospitali[sz]ation"),
        "Medicines, tests and doctor visits in the days before admission and after discharge.",
        "Keep every bill from those days and claim them within the policy's time limit; they are often forgotten.",
    ),
]

BY_KEY = {b.key: b for b in CATALOGUE}
ORDER = {b.key: i for i, b in enumerate(CATALOGUE)}


def catalogue() -> list[BenefitInfo]:
    return [BenefitInfo(key=b.key, name=b.name, what=b.what, how_to_use=b.how_to_use, resets_yearly=b.resets_yearly)
            for b in CATALOGUE]




NEGATIVE = _p(r"\bnot\s+(?:be\s+)?(?:covered|payable|admissible|available|included|reimbursed|provided)|\bexclud\w*"
              r"|\bexclusions?\b|\bshall\s+not\b|\bwill\s+not\b|\bno\s+(?:cover|coverage|benefit)\b|\bnot\s+applicable\b"
              r"|\bnot\s+opted\b|code[- ]?excl")
OPTIONAL = _p(r"\boptional\b|\bif\s+opted\b|\badd[- ]?on\b|\brider\b|additional\s+premium|extra\s+premium|where\s+opted")
# Words showing that a sentence grants something, so a passing mention
# ("travel costs other than ambulance charges") is not taken for a benefit.
GRANTS = _p(r"\bcover(?:s|ed)?\b|\bcoverage\b|\bpayable\b|\b(?:we|insurer|company)\s+(?:will|shall)\s+(?:also\s+)?(?:pay|reimburse|indemnify)"
            r"|(?:will|shall)\s+be\s+paid|reimburs\w*|indemnif\w*|\bentitled\b|\bavail(?:s|ed|ing|able)?\b|\bup\s*to\b|\bupto\b|\blimited\s+to\b"
            r"|\bmaximum\s+of\b|\bfree\b|at\s+no\s+(?:extra\s+|additional\s+)?(?:cost|charge)|\brestored?\b|\breinstated?\b")
CARVE_OUT = _p(r"(?:other\s+than|except(?:ing)?|excluding|apart\s+from|but\s+not|save\s+for)\s+(?:the\s+|an?\s+|for\s+)?(?:[\w-]+\s+){0,2}$")
DEFINITION = _p(r"\bmeans\b|\bshall\s+mean\b|\brefers\s+to\b|\bis\s+defined\s+as\b")
TABLE_OF_CONTENTS = re.compile(r"\.{4,}|…{2,}|(?:\.\s){4,}")
CLAUSE_BREAK = _p(r",?\s+but\s+|,\s+whereas\s+|,\s+however,?\s+")
LIMIT_AMOUNT = re.compile(rf"{RUPEE}\s*(\d[\d,]*(?:\.\d+)?)\s*(?:/-)?\s*(lakhs?|lacs?)?", re.I)
LIMIT_PERIOD = _p(r"once\s+(?:in\s+|every\s+)(?:a\s+)?(?:\d+|two|three|four)?\s*(?:continuous\s+|claim[- ]free\s+)?(?:policy\s+)?years?"
                  r"|per\s+policy\s+(?:year|period)|every\s+(?:\d+|two|three|four)\s+(?:claim[- ]free\s+)?years?"
                  r"|per\s+(?:hospitali[sz]ation|admission|claim|day|eye|consultation)")
BOILERPLATE = _p(r"subject\s+to\s+(?:the\s+)?(?:following\s+)?(?:policy\s+)?(?:terms|conditions|exclusions|limits)"
                 r"(?:[\s,&]+(?:and\s+)?(?:terms|conditions|exclusions|limits))*")
LONG_CLAUSE = 400  # table text merged into one long "sentence": judge only the words around the match
NEGATION_BEFORE, NEGATION_AFTER = 60, 120  # "not covered" must be this close to the benefit's name to apply to it
SUBJECT_WITHIN = 40  # the benefit is what the clause is about if named this early; only then is a limit its own
MIN_LIMIT = 10  # rupees: "each point is worth INR 0.25" is not a limit

# Headings set the context of what follows: "SECTION C - EXCLUSIONS" starts an exclusion list,
# "Optional covers" an add-on list. A line counts as a heading only if it is short and names a
# section, so a list item in capitals ("OUT-PATIENT TREATMENT") does not end an exclusion list.
SECTION_PREFIX = re.compile(r"^\s*(?i:section|part|chapter|annexure|appendix)\s*[-–:.]?\s*(?:[A-Z]{1,3}|\d{1,2}|[IVX]{1,4})\b")
SECTION_WORDS = _p(r"\b(?:benefits?|coverage|covers?|conditions|definitions?|exclusions?|general|terms|schedule|grievance"
                   r"|ombudsman|renewal|portability|premium|waiting\s+periods?|annexure|optional|add[- ]?ons?|claims?\s+procedure"
                   r"|operative\s+clause|moratorium|cancellation|free\s+look|disclosure|scope)\b")
NUMBERING = re.compile(r"^\s*(?:[A-Z]|\d{1,2}(?:\.\d{1,2})*|[ivx]{1,4})[.):]\s+|^\s*\d{1,2}(?:\.\d{1,2})+\s+")
TITLE_LINE = re.compile(r"^[A-Z][A-Za-z&/,'() -]{1,70}:?\s*$")
SENTENCE_WORDS = _p(r"\b(?:shall|will|is|are|was|were|of\s+this|under\s+this)\b")
SMALL_WORDS = {"of", "and", "the", "for", "to", "in", "on", "a", "an", "or", "with", "under", "by", "at", "from"}
# A new numbered clause ("11. Wellness Services: ...") ends a minor heading's list ("Specific exclusions:").
NEW_CLAUSE = re.compile(r"^\s*(?:\d{1,2}|[A-Z])[.)]\s+[A-Z][A-Za-z /&()'-]{2,50}\s*[:\-–]")


def _title_case(text: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    return bool(words) and all(w[0].isupper() or w.lower() in SMALL_WORDS for w in words)


def _heading(line: str) -> str | None:
    """'strong' (a section), 'weak' (a minor title such as "Specific exclusions:") or None (not a heading)."""
    s = line.strip()
    if not s or len(s) > 80 or s.endswith((",", ".")):
        return None
    if SECTION_PREFIX.match(s):
        return "strong" if len(s.split()) <= 10 and not SENTENCE_WORDS.search(s) else None
    if not SECTION_WORDS.search(s):
        return None
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 6 and sum(c.isupper() for c in letters) / len(letters) >= 0.8:
        return "strong"
    numbered = NUMBERING.match(s)
    title = s[numbered.end():] if numbered else s
    if TITLE_LINE.match(title) and _title_case(title) and len(s.split()) <= 8 and not SENTENCE_WORDS.search(s):
        return "strong" if numbered else "weak"
    return None


def _is_heading(line: str) -> bool:
    return _heading(line) is not None


def _context(heading: str) -> BenefitStatus:
    if re.search(r"exclu|code[- ]?excl|\bexcl[- ]?\d", heading, re.I):
        return "not_covered"
    if re.search(r"optional|add[- ]?on", heading, re.I):
        return "optional"
    return "covered"


def _running_headers(pages: list[Page]) -> set[str]:
    """Heading-like lines repeated on several pages (page headers): not section headings."""
    seen: dict[str, int] = {}
    for _, raw in pages:
        for line in {flat(x).strip().lower() for x in raw.splitlines() if _is_heading(x)}:
            seen[line] = seen.get(line, 0) + 1
    return {line for line, n in seen.items() if n >= 2} if len(pages) >= 2 else set()


def _segments(pages: list[Page]):
    """(page, heading context, flattened text) blocks. Context carries across pages."""
    repeated = _running_headers(pages)
    context: BenefitStatus = "covered"
    minor = False  # context came from a minor heading, so the next numbered clause ends it
    for pno, raw in pages:
        block: list[str] = []
        for line in raw.splitlines():
            kind = _heading(line)
            if kind and flat(line).strip().lower() in repeated:
                continue
            if kind or (minor and context != "covered" and NEW_CLAUSE.match(line)):
                if block:
                    yield pno, context, flat(" ".join(block))
                    block = []
                if kind:
                    context, minor = _context(line), kind == "weak"
                    continue
                context, minor = "covered", False
            block.append(line)
        if block:
            yield pno, context, flat(" ".join(block))


PROTECTED_DOT = "․"  # stands in for the dot of "Rs." while splitting, so quotes stay exact


def _sentences(text: str) -> list[str]:
    text = ABBREVIATIONS.sub(lambda m: m.group(1) + PROTECTED_DOT, text)
    parts = re.split(r"(?<=[.;!?])\s+", text)
    return [s.strip().replace(PROTECTED_DOT, ".") for s in parts if s.strip()]


def _clause(sentence: str, start: int, end: int) -> tuple[str, int, int]:
    """The part of the sentence the match is in ("A is covered, but B is not"), and the match's place in it."""
    lo, hi = 0, len(sentence)
    for brk in CLAUSE_BREAK.finditer(sentence):
        if brk.end() <= start:
            lo = brk.end()
        elif brk.start() >= end:
            hi = brk.start()
            break
    if hi - lo > LONG_CLAUSE:
        lo, hi = max(lo, start - 150), min(hi, end + 250)
    return sentence[lo:hi], start - lo, end - lo


def _grants(clause: str, start: int, end: int) -> bool:
    if GRANTS.search(clause) or LIMIT_AMOUNT.search(clause) or PERCENT_OF_SI.search(clause):
        return True
    return start <= 30 and re.match(r"\s*(?:\([^)]{0,30}\)\s*)?[:\-–]", clause[end:]) is not None  # "Health Check-up: ..."


def _limit(text: str) -> str | None:
    parts = []
    amount = LIMIT_AMOUNT.search(text)
    if amount:
        value = to_amount(amount.group(1), amount.group(2))
        if value and value >= MIN_LIMIT:
            parts.append(inr(value))
    pct = PERCENT_OF_SI.search(text)
    if pct:
        parts.append(f"{float(pct.group(1)):g}% of sum insured")
    if not parts:
        return None
    period = LIMIT_PERIOD.search(text)
    return " or ".join(parts) + (f" {period.group(0).lower()}" if period else "")


def _quote(sentence: str, start: int, end: int, limit: int = 240) -> str:
    if len(sentence) <= limit:
        return sentence
    s = max(0, start - limit // 2)
    e = min(len(sentence), s + limit)
    return ("..." if s else "") + sentence[s:e].strip() + ("..." if e < len(sentence) else "")


@dataclass
class _Mention:
    benefit: PolicyBenefit
    explicit: bool  # the sentence itself says so, not just the section it is in
    subject: bool = True  # the clause is about this benefit, not just naming it in passing


RANK: dict[BenefitStatus, int] = {"covered": 0, "optional": 1, "not_covered": 2}


def _mention(b: BenefitType, sentence: str, context: BenefitStatus, pno: int) -> _Mention | None:
    m = b.pattern.search(sentence)
    if not m:
        return None
    clause, start, end = _clause(sentence, m.start(), m.end())
    if (b.skip and b.skip.search(clause)) or CARVE_OUT.search(clause[:start]):
        return None
    quote = Citation(page=pno, quote=_quote(sentence, m.start(), m.end()))
    subject = start <= SUBJECT_WITHIN
    near = clause[max(0, start - NEGATION_BEFORE): end + NEGATION_AFTER]
    if NEGATIVE.search(BOILERPLATE.sub(" ", near)):
        return _Mention(PolicyBenefit(key=b.key, status="not_covered", citation=quote), explicit=True, subject=subject)
    if context == "not_covered":
        return _Mention(PolicyBenefit(key=b.key, status="not_covered", citation=quote), explicit=False, subject=subject)
    optional = context == "optional" or OPTIONAL.search(near) is not None
    if not optional and not _grants(clause, start, end):
        return None  # a passing mention, not a statement about this benefit
    return _Mention(PolicyBenefit(key=b.key, status="optional" if optional else "covered",
                                  limit=_limit(clause[start:]) if subject else None, citation=quote),
                    explicit=True, subject=subject)


def find_benefits(pages: list[Page], pre_post: Candidate | None = None) -> list[PolicyBenefit]:
    """Benefits stated in the policy text, best statement first, in catalogue order."""
    found: dict[str, list[_Mention]] = {}
    for pno, context, text in _segments(pages):
        for sentence in _sentences(text):
            if DEFINITION.search(sentence) or TABLE_OF_CONTENTS.search(sentence):
                continue
            for b in CATALOGUE:
                mention = _mention(b, sentence, context, pno)
                if mention:
                    found.setdefault(b.key, []).append(mention)

    if pre_post and isinstance(pre_post.value, tuple) and any(pre_post.value):
        pre, post = pre_post.value
        days = " / ".join(x for x in (f"{pre} days before" if pre else "", f"{post} days after" if post else "") if x)
        found["pre_post"] = [_Mention(PolicyBenefit(key="pre_post", status="covered", limit=days, citation=Citation(
            page=pre_post.page, quote=pre_post.quote or None)), explicit=True)]

    out = []
    for key in sorted(found, key=ORDER.__getitem__):
        # Covered before optional before not covered; among equals, a statement about this benefit
        # rather than one naming it in passing, then one that gives a limit.
        options = sorted(found[key], key=lambda x: (RANK[x.benefit.status], not x.subject, x.benefit.limit is None))
        best = options[0].benefit
        other = next((o.benefit for o in options if o.benefit.status != best.status
                      and (o.explicit or o.benefit.status == "optional")), None)
        if other and other.citation:
            where = f"Page {other.citation.page}" if other.citation.page else "The policy"
            if other.status == "not_covered":
                best.note = f"{where} also has a condition or exclusion for this. Read it before you rely on this benefit."
            else:
                best.note = f"{where} lists this as an optional add-on. Check your policy schedule to see if you have it."
        out.append(best)
    return out

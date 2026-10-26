"""Parsers for Indian rupee amounts, durations and dates as written in policies."""

import re
from datetime import date, datetime

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "nine": 9, "twelve": 12,
    "fifteen": 15, "thirty": 30, "sixty": 60, "ninety": 90, "twenty four": 24, "twenty-four": 24,
    "twentyfour": 24, "thirty six": 36, "thirty-six": 36, "thirtysix": 36, "forty eight": 48,
    "forty-eight": 48, "fortyeight": 48,
}
_WORD_NUM = r"twenty[- ]?four|thirty[- ]?six|forty[- ]?eight|twelve|fifteen|thirty|sixty|ninety|nine|one|two|three|four|five|six"

RUPEE = r"(?:rs\.?|inr|₹|rupees)"
AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|lac|crores?|cr\b)?"

MONTHS_RE = re.compile(
    rf"(\d{{1,2}}|{_WORD_NUM})\s*(?:\(\s*\d{{1,2}}\s*\)\s*)?(?:consecutive\s+|continuous\s+)?months?\b", re.I)
YEARS_RE = re.compile(rf"(\d|{_WORD_NUM})\s*(?:\(\s*\d\s*\)\s*)?(?:consecutive\s+|continuous\s+)?years?\b", re.I)
DAYS_RE = re.compile(rf"(\d{{1,3}}|{_WORD_NUM})\s*(?:\(\s*\d{{1,3}}\s*\)\s*)?days?\b", re.I)

DATE = (r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{4}-\d{2}-\d{2}"
        r"|\d{1,2}(?:st|nd|rd|th)?[\s\-]+[A-Za-z]{3,9}[\s\-,]+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})")


def word_or_int(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token) or NUMBER_WORDS.get(token.replace("-", " "))


def to_amount(number: str, unit: str | None = None) -> float | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit.startswith(("lakh", "lac")):
        value *= 100_000
    elif unit.startswith("cr"):
        value *= 10_000_000
    return value


def parse_amount(text: str) -> float | None:
    """First rupee amount in text, understanding 'Rs 5,00,000', '5 lakh', '₹1 crore'."""
    m = re.search(rf"(?:{RUPEE}\s*)?{AMOUNT}", text, re.I)
    return to_amount(m.group(1), m.group(2)) if m else None


def parse_duration_months(text: str) -> int | None:
    """First 'N months' or 'N years' in text, as months."""
    m_months = MONTHS_RE.search(text)
    m_years = YEARS_RE.search(text)
    candidates = []
    if m_months:
        n = word_or_int(m_months.group(1))
        if n:
            candidates.append((m_months.start(), n))
    if m_years:
        n = word_or_int(m_years.group(1))
        if n:
            candidates.append((m_years.start(), n * 12))
    return min(candidates)[1] if candidates else None


def parse_days(text: str) -> int | None:
    m = DAYS_RE.search(text)
    return word_or_int(m.group(1)) if m else None


def parse_date(text: str) -> date | None:
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().rstrip(".,"))
    text = re.sub(r"[\s,]+", " ", text.replace("-", " ") if re.search(r"[A-Za-z]", text) else text)
    formats = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def inr(value: float) -> str:
    """Indian digit grouping: 500000 -> 'Rs 5,00,000'."""
    whole = int(round(value))
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"Rs {s}"

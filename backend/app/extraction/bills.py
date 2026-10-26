"""Parse hospital bills / estimates (text, CSV, PDF, photo) into bill lines."""

import csv
import io
import re

from app.extraction.documents import file_text
from app.models import BillCategory, BillItem

AMOUNT_AT_END = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(?:/-)?\s*$")
TRAILING_NUMBERS = re.compile(r"(?:\s+[\d,]+(?:\.\d+)?)+$")
SKIP = re.compile(
    r"\b(total|sub ?total|grand total|net (amount|payable|bill)|amount (payable|due|in words)|balance|advance"
    r"|deposit|paid|refund|discount|round(ed)? ?off|bill (no|date)|invoice|uhid|ip ?no|mr ?no|reg(n|istration)? no"
    r"|patient name|age|gstin|phone|mobile|page \d+|date)\b",
    re.I,
)
ENDS_WITH_NO = re.compile(r"\b(no|number)\s*[:.]?$", re.I)


def parse_bill_text(text: str) -> tuple[list[BillItem], list[str]]:
    """Each line ending in an amount becomes a bill line. Returns (items, skipped lines)."""
    items: list[BillItem] = []
    skipped: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = AMOUNT_AT_END.search(line)
        if not m:
            continue
        desc = line[: m.start()]
        desc = re.sub(r"(₹|\brs\.?|\binr)\s*$", "", desc, flags=re.I).strip(" \t:-|")
        numbers = TRAILING_NUMBERS.search(desc)
        if numbers and len(numbers.group(0).split()) >= 2:  # qty and rate columns
            desc = desc[: numbers.start()].strip(" \t:-|")
        if not re.search(r"[A-Za-z]{2,}", desc):
            continue
        if SKIP.search(desc) or ENDS_WITH_NO.search(desc):
            skipped.append(line)
            continue
        amount = float(m.group(1).replace(",", ""))
        if amount > 0:
            items.append(BillItem(description=desc, amount=amount))
    return items, skipped


def _category(value: str) -> BillCategory | None:
    value = value.strip().lower().replace(" ", "_")
    try:
        return BillCategory(value) if value else None
    except ValueError:
        return None


def parse_bill_csv(text: str) -> tuple[list[BillItem], list[str]]:
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        return [], []
    header = [c.strip().lower() for c in rows[0]]
    desc_col = next((i for i, h in enumerate(header) if h in ("description", "item", "particulars", "service", "name")), None)
    amt_col = next((i for i, h in enumerate(header) if h in ("amount", "total", "net", "net amount", "value", "rs", "inr")), None)
    cat_col = next((i for i, h in enumerate(header) if h == "category"), None)
    body = rows[1:] if desc_col is not None or amt_col is not None else rows
    desc_col = 0 if desc_col is None else desc_col
    items, skipped = [], []
    for row in body:
        try:
            amount_cell = row[amt_col] if amt_col is not None else row[-1]
            amount = float(re.sub(r"[^\d.]", "", amount_cell) or "0")
            desc = row[desc_col].strip()
        except (IndexError, ValueError):
            skipped.append(",".join(row))
            continue
        if not desc or amount <= 0 or SKIP.search(desc):
            skipped.append(",".join(row))
            continue
        category = _category(row[cat_col]) if cat_col is not None and cat_col < len(row) else None
        items.append(BillItem(description=desc, amount=amount, category=category))
    return items, skipped


def parse_bill_file(filename: str, data: bytes) -> tuple[list[BillItem], list[str], list[str]]:
    """Returns (items, skipped lines, warnings)."""
    if filename.lower().endswith(".csv"):
        items, skipped = parse_bill_csv(data.decode("utf-8-sig"))
        return items, skipped, []
    pages, warnings = file_text(filename, data)
    items, skipped = parse_bill_text("\n".join(pages))
    return items, skipped, warnings

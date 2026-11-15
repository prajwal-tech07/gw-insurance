"""Overcharge checks on a hospital bill: the same line billed twice is the most common one."""

from collections import Counter

from app.engine.calculator import rupees
from app.engine.classifier import normalize
from app.models import BillItem, Issue


def overcharges(items: list[BillItem]) -> list[Issue]:
    issues = []
    same = Counter((normalize(i.description), round(i.amount, 2)) for i in items if i.amount > 0)
    for (key, amount), count in same.items():
        if count > 1:
            name = next(i.description for i in items if round(i.amount, 2) == amount and normalize(i.description) == key)
            issues.append(Issue(level="warn", code="duplicate_line", message=(
                f"'{name}' for {rupees(amount)} is billed {count} times. Ask the hospital whether this is a "
                f"duplicate: if so, {rupees(amount * (count - 1))} should come off the bill.")))
    return issues

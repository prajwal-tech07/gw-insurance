"""Calendar helpers used for waiting periods and complaint deadlines."""

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year = d.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def add_years(d: date, years: int) -> date:
    return add_months(d, 12 * years)


def months_between(start: date, end: date) -> int:
    """Whole months from start to end (0 if end is before start)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)

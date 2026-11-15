"""Minimal iCalendar (.ics) files for renewal and premium reminders (RFC 5545)."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass
class Event:
    uid: str
    day: date
    summary: str
    description: str


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Split a content line into pieces of at most 75 octets, never inside a UTF-8 character."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + piece for piece in out[1:]]


def uid_part(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "item"


def calendar(events: list[Event], now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ClaimSaathi//Reminders//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH"]
    for e in sorted(events, key=lambda x: (x.day, x.uid)):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}@claimsaathi",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{e.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{e.day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(e.summary)}",
            f"DESCRIPTION:{_escape(e.description)}",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER:PT9H",
            f"DESCRIPTION:{_escape(e.summary)}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(piece for line in lines for piece in _fold(line)) + "\r\n"

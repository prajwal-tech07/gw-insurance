"""Deadlines for a complaint: insurer (14 days) -> Bima Bharosa -> Ombudsman (1 year)."""

from datetime import date, timedelta

from app.engine.dates import add_months, add_years
from app.models import Complaint, ComplaintData, Deadline

DUE_SOON_DAYS = 3


def _deadline(label: str, due: date, today: date, done: bool, rule_ids: list[str]) -> Deadline:
    days_left = (due - today).days
    if done:
        status = "done"
    elif days_left < 0:
        status = "passed"
    elif days_left <= DUE_SOON_DAYS:
        status = "due_soon"
    else:
        status = "upcoming"
    return Deadline(label=label, due=due, days_left=days_left, status=status, rule_ids=rule_ids)


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def timeline(complaint_id: int, data: ComplaintData, today: date | None = None) -> Complaint:
    today = today or date.today()
    filed = data.grievance_filed_on
    replied = data.insurer_reply_on is not None and data.insurer_outcome != "none"
    reply_due = filed + timedelta(days=14)
    no_reply_from = add_months(filed, 1)

    if replied and data.insurer_outcome in ("rejected", "partial"):
        ombudsman_from = data.insurer_reply_on
        ombudsman_by = add_years(data.insurer_reply_on, 1)
    else:
        ombudsman_from = no_reply_from
        ombudsman_by = add_years(no_reply_from, 1)

    deadlines = [
        _deadline("Insurer must resolve your grievance", reply_due, today, replied, ["GRV-14"]),
        _deadline("You can go to the Ombudsman from", ombudsman_from, today, data.ombudsman_filed_on is not None or today >= ombudsman_from, ["OMB-14"]),
        _deadline("Last date to file with the Ombudsman", ombudsman_by, today, data.ombudsman_filed_on is not None, ["OMB-14"]),
    ]

    if data.stage in ("resolved", "closed") or data.insurer_outcome == "resolved":
        action = "Resolved. Keep the insurer's letter and payment proof."
    elif data.stage == "ombudsman":
        action = (f"Ombudsman complaint filed on {_fmt(data.ombudsman_filed_on) if data.ombudsman_filed_on else '[date]'}. "
                  "The Ombudsman must pass an award within 3 months of receiving all requirements; the insurer must "
                  "comply within 30 days of the award.")
    elif replied:
        action = (f"The insurer replied ({data.insurer_outcome}). If you disagree, file with the Insurance Ombudsman "
                  f"before {_fmt(ombudsman_by)}. You can also escalate on Bima Bharosa.")
    elif data.stage == "bima_bharosa":
        action = (f"Escalated on Bima Bharosa. You can also file with the Ombudsman from {_fmt(ombudsman_from)} "
                  f"(last date {_fmt(ombudsman_by)}).")
    elif today <= reply_due:
        action = f"Wait for the insurer's reply. It is due by {_fmt(reply_due)}."
    elif today < no_reply_from:
        action = (f"The 14 days are over without a resolution. Escalate on IRDAI's Bima Bharosa portal now. "
                  f"From {_fmt(no_reply_from)} you can also go to the Ombudsman.")
    else:
        action = (f"No reply for over a month. File with the Insurance Ombudsman (free) before {_fmt(ombudsman_by)}, "
                  "and escalate on Bima Bharosa.")

    return Complaint(id=complaint_id, **data.model_dump(), next_action=action, deadlines=deadlines)

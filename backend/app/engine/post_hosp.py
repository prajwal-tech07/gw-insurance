"""Post-hospitalisation bills: the countdown after discharge and what can still be claimed.

Medicines, tests and follow-up visits in the policy's post-hospitalisation days are covered,
but people forget to keep and claim them. Bills dated outside the window are flagged.
"""

from datetime import date, timedelta

from app.engine.calculator import rupees
from app.models import PostHospData, PostHospTracker

CLOSING_DAYS = 7


def _fmt(d: date) -> str:
    return d.strftime("%d %b %Y")


def track(tracker_id: int, data: PostHospData, today: date | None = None) -> PostHospTracker:
    today = today or date.today()
    ends = data.discharge_date + timedelta(days=data.post_days)
    days_left = (ends - today).days
    inside = [b for b in data.bills if data.discharge_date <= b.on <= ends]
    outside = [f"{b.description} ({_fmt(b.on)})" for b in data.bills if b not in inside]
    claimable = round(sum(b.amount for b in inside), 2)
    if days_left < 0:
        status = "closed"
        step = (f"The {data.post_days}-day window ended on {_fmt(ends)}. Send all {len(inside)} bill(s) "
                f"({rupees(claimable)}) to the insurer now, with the prescriptions and the discharge summary; "
                "check your policy's deadline for post-hospitalisation claims.")
    else:
        status = "closing" if days_left <= CLOSING_DAYS else "open"
        step = (f"Keep every medicine, test and doctor's bill until {_fmt(ends)} ({days_left} days left), with the "
                f"prescriptions. So far {rupees(claimable)} can be claimed. Claim them together once the window ends.")
    return PostHospTracker(**data.model_dump(), id=tracker_id, window_ends=ends, days_left=days_left, status=status,
                           claimable=claimable, outside=outside, next_step=step)

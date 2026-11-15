"""'Needs your attention' items for the home page: renewals, premiums, nominees, complaint deadlines."""

from datetime import date

from app.complaints.tracker import timeline
from app.engine.post_hosp import track
from app.engine.renewal import RENEW_SOON_DAYS, renewal_status
from app.models import Alert, ComplaintData, PostHospData, RenewalInput, SavedPolicy, VaultEntryData
from app.vault.checks import KIND_LABEL, LIFE_KINDS, to_entry

ORDER = {"bad": 0, "warn": 1, "info": 2, "good": 3}


def build_alerts(policies: list[SavedPolicy], vault: list[tuple[int, VaultEntryData]],
                 complaints: list[tuple[int, ComplaintData]], post_hosp: list[tuple[int, PostHospData]] = (),
                 today: date | None = None) -> list[Alert]:
    today = today or date.today()
    out: list[Alert] = []
    for p in policies:
        r = renewal_status(RenewalInput(terms=p.terms), today)
        if r.status in ("due_soon", "grace", "lapsed"):
            out.append(Alert(level="warn" if r.status == "due_soon" else "bad", title=f"{p.name}: renewal",
                             text=r.headline, tab="policies"))
        if r.unused_benefits and r.days_left is not None and 0 <= r.days_left <= RENEW_SOON_DAYS:
            out.append(Alert(level="info", title=f"{p.name}: benefits not used this year",
                             text=f"Use before {r.renew_by:%d %b %Y}: " + "; ".join(r.unused_benefits) + ".", tab="policies"))
    for entry_id, data in vault:
        e = to_entry(entry_id, data, today)
        name = f"{KIND_LABEL[e.kind]} ({e.insurer})"
        due = next((n for n in e.checks if n.level in ("bad", "warn") and e.due_status in ("due_soon", "grace", "lapsed")), None)
        if due:
            out.append(Alert(level=due.level, title=name, text=due.text, tab="vault"))
        if e.kind in LIFE_KINDS and e.due_status != "ended" and not e.nominee.strip():
            out.append(Alert(level="bad", title=name, text="No nominee recorded for this life policy.", tab="vault"))
    for cid, data in complaints:
        if data.stage in ("resolved", "closed"):
            continue
        c = timeline(cid, data, today)
        for d in c.deadlines:
            if d.status == "due_soon":
                out.append(Alert(level="warn", title=c.title, text=f"{d.label}: {d.due:%d %b %Y} ({d.days_left} days left).",
                                 tab="complaints"))
    for tid, data in post_hosp:
        t = track(tid, data, today)
        if t.status == "closing":
            out.append(Alert(level="warn", title=f"{t.title}: post-hospitalisation bills", text=t.next_step, tab="bill"))
    return sorted(out, key=lambda a: ORDER[a.level])

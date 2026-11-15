import { useEffect, useState } from "react";
import { api, downloadFile } from "../api";
import { numOrNull } from "../format";
import type { RenewalStatus, SavedPolicy } from "../types";
import { Badge, ErrorBox, Field, NoteList, Notice, RuleRefs } from "./ui";

const statusTone = { active: "good", due_soon: "warn", grace: "bad", lapsed: "bad", unknown: "muted" } as const;
const statusText = { active: "Active", due_soon: "Renew soon", grace: "In grace period", lapsed: "Grace period over", unknown: "End date missing" } as const;

function daysUntil(iso: string): number {
  const ms = new Date(`${iso}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime();
  return Math.round(ms / 86_400_000);
}

export function RenewalPanel({ policy }: { policy: SavedPolicy }) {
  const [status, setStatus] = useState<RenewalStatus | null>(null);
  const [current, setCurrent] = useState("");
  const [quote, setQuote] = useState("");
  const [age, setAge] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.renewal({ terms: policy.terms }).then(setStatus).catch((e) => setError((e as Error).message));
  }, [policy]);

  async function checkPremium() {
    setError(null);
    try {
      setStatus(await api.renewal({
        terms: policy.terms, current_premium: numOrNull(current), renewal_premium: numOrNull(quote), oldest_member_age: numOrNull(age),
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!status) return <ErrorBox error={error} />;
  // The last reminder is 3 days before the grace period ends; after that there is nothing left to remind.
  const reminders = status.status === "active" || status.status === "due_soon"
    || (status.status === "grace" && status.grace_until != null && daysUntil(status.grace_until) >= 3);

  return (
    <div className="renewal">
      <p>
        <Badge tone={statusTone[status.status]}>{statusText[status.status]}</Badge> {status.headline}
      </p>
      <NoteList notes={status.notes} />
      {status.unused_benefits.length > 0 && (
        <Notice tone="info">
          <strong>Not used this policy year:</strong> {status.unused_benefits.join("; ")}. These usually do not carry over, so use them before renewal.
        </Notice>
      )}
      {status.at_stake.length > 0 && (
        <details>
          <summary>What you keep by renewing on time ({status.at_stake.length})</summary>
          <ul>{status.at_stake.map((x) => <li key={x}>{x}</li>)}</ul>
          <p className="small muted">Moving to another insurer? Port the policy so these move with you. <RuleRefs ids={["PORT-01"]} /></p>
        </details>
      )}
      <details>
        <summary>Got a renewal quote? Check the price rise</summary>
        <div className="grid">
          <Field label="This year's premium (₹)"><input type="number" min={0} value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
          <Field label="Renewal premium quoted (₹)"><input type="number" min={0} value={quote} onChange={(e) => setQuote(e.target.value)} /></Field>
          <Field label="Age of the oldest person covered"><input type="number" min={0} max={120} value={age} onChange={(e) => setAge(e.target.value)} /></Field>
          <button type="button" className="secondary" disabled={!current || !quote} onClick={checkPremium}>Check</button>
        </div>
        {status.premium_check && <NoteList notes={[status.premium_check]} />}
      </details>
      {reminders && (
        <div className="row">
          <button type="button" className="secondary" onClick={() => {
            setError(null);
            downloadFile(api.renewalIcsUrl(policy.id), `renewal-reminders-${policy.id}.ics`).catch((e) => setError((e as Error).message));
          }}>Add renewal reminders to my calendar</button>
          <span className="small muted">Opens in Google, Outlook and phone calendars.</span>
        </div>
      )}
      <ErrorBox error={error} />
    </div>
  );
}

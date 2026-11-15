import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Card, CopyButton, Disclaimer, DownloadButton, ErrorBox, Field, NoteList, Notice, RuleRefs, Spinner } from "../components/ui";
import { inr, niceDate, num, numOrNull, today } from "../format";
import { useApp } from "../state";
import type { DeathClaimInput, DeathClaimKind, DeathClaimResult, VaultEntry } from "../types";
import { KIND_LABEL } from "./Vault";

const LIFE: DeathClaimKind[] = ["term_life", "life_savings"];
const RELATION = { spouse: "spouse", child: "child", parent: "parent", sibling: "brother/sister", other_relative: "relative", other: "", "": "" } as const;

function emptyClaim(): DeathClaimInput {
  return {
    kind: "term_life", insurer: "", policy_number: "", life_assured: "", claimant_name: "", claimant_relation: "",
    claimant_is_nominee: null, cover_amount: 0, policy_start: null, revival_date: null, date_of_death: "",
    place_of_death: "other", cause: "unknown", intimated_on: null, under_investigation: false, assigned_to_lender: false,
    has_accident_cover: false, phone: "", email: "", bank_rate: null,
  };
}

function fromVault(e: VaultEntry, current: DeathClaimInput): DeathClaimInput {
  const kind: DeathClaimKind = (["term_life", "life_savings", "personal_accident", "health"] as string[]).includes(e.kind)
    ? (e.kind as DeathClaimKind) : "other";
  return {
    ...current, kind, insurer: e.insurer, policy_number: e.policy_number, life_assured: e.insured || e.holder,
    cover_amount: e.cover_amount, policy_start: e.start_date, revival_date: e.revival_date,
    assigned_to_lender: e.assigned_to_lender, has_accident_cover: e.kind === "personal_accident" || current.has_accident_cover,
    claimant_name: current.claimant_name || e.nominee, claimant_relation: current.claimant_relation || RELATION[e.nominee_relation],
    claimant_is_nominee: e.nominee ? true : current.claimant_is_nominee,
  };
}

/** Same checks as the server (app/vault/death_claim.py), shown before sending. */
function datesProblem(f: DeathClaimInput): string | null {
  const now = today();
  if (f.date_of_death > now) return "The date of death cannot be in the future.";
  if (f.intimated_on && f.intimated_on < f.date_of_death) return "The claim cannot be intimated before the date of death.";
  if (f.intimated_on && f.intimated_on > now) return "The date the claim was intimated cannot be in the future.";
  if (f.policy_start && f.policy_start > f.date_of_death) return "The policy start date is after the date of death. Check both dates.";
  if (f.revival_date && f.policy_start && f.revival_date < f.policy_start) return "The revival date cannot be before the policy start date.";
  return null;
}

const contestTone ={ no: "good", limited: "warn", not_applicable: "muted", unknown: "muted" } as const;
const contestText = {
  no: "Cannot be questioned", limited: "Can be questioned only for fraud or misstatement", not_applicable: "Not a life policy", unknown: "Add the start date",
} as const;

export function DeathClaim() {
  const [form, setForm] = useState<DeathClaimInput>(emptyClaim);
  const [vault, setVault] = useState<VaultEntry[]>([]);
  const [result, setResult] = useState<DeathClaimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tracked, setTracked] = useState<string | null>(null);
  const { setTab } = useApp();

  useEffect(() => { api.vault().then((v) => setVault(v.entries)).catch(() => setVault([])); }, []);
  const set = <K extends keyof DeathClaimInput>(k: K, v: DeathClaimInput[K]) => setForm({ ...form, [k]: v });
  const life = LIFE.includes(form.kind);

  async function run() {
    setError(null); setTracked(null);
    const problem = datesProblem(form);
    if (problem) { setError(problem); return; }
    setBusy(true);
    try {
      setResult(await api.deathClaim(form));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function track() {
    setError(null);
    try {
      await api.createComplaint({
        title: `Death claim ${form.policy_number || ""} ${form.insurer}`.trim(), insurer: form.insurer, policy_number: form.policy_number,
        claim_number: "", amount_disputed: form.cover_amount, grievance_filed_on: today(), insurer_reply_on: null,
        insurer_outcome: "none", bima_bharosa_filed_on: null, ombudsman_filed_on: null, stage: "insurer",
        notes: "Follow-up letter for a delayed death claim.",
      });
      setTracked("Tracking started in the Complaints tab, from today. Send the follow-up letter today.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const deathClaims = vault.filter((e) => e.kind !== "motor" && e.kind !== "home" && e.kind !== "travel");

  return (
    <div className="page">
      <h2>Death claim help</h2>
      <Notice tone="info">
        We are sorry for your loss. This page lists what to send, whether the insurer can question the policy, when it
        must pay, other money the family may be owed, and drafts the letters. Take it one step at a time.
      </Notice>

      <Card title="1. The policy">
        {deathClaims.length > 0 && (
          <Field label="Fill in from the family vault">
            <select value="" onChange={(e) => {
              const entry = deathClaims.find((x) => String(x.id) === e.target.value);
              if (entry) setForm(fromVault(entry, form));
            }}>
              <option value="">Choose a policy...</option>
              {deathClaims.map((e) => <option key={e.id} value={e.id}>{KIND_LABEL[e.kind]}: {e.insurer} {e.policy_number}</option>)}
            </select>
          </Field>
        )}
        <div className="grid">
          <Field label="Type of policy">
            <select value={form.kind} onChange={(e) => set("kind", e.target.value as DeathClaimKind)}>
              <option value="term_life">Term life</option>
              <option value="life_savings">Life (endowment / money-back / ULIP)</option>
              <option value="personal_accident">Personal accident</option>
              <option value="health">Health</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Insurer"><input value={form.insurer} onChange={(e) => set("insurer", e.target.value)} /></Field>
          <Field label="Policy number"><input value={form.policy_number} onChange={(e) => set("policy_number", e.target.value)} /></Field>
          <Field label="Cover / sum assured (₹)"><input type="number" min={0} value={form.cover_amount || ""} onChange={(e) => set("cover_amount", num(e.target.value))} /></Field>
          <Field label="Policy started on"><input type="date" value={form.policy_start ?? ""} onChange={(e) => set("policy_start", e.target.value || null)} /></Field>
          {life && (
            <Field label="Revived on (if it ever lapsed)">
              <input type="date" value={form.revival_date ?? ""} onChange={(e) => set("revival_date", e.target.value || null)} />
            </Field>
          )}
        </div>
        <label className="check">
          <input type="checkbox" checked={form.assigned_to_lender} onChange={(e) => set("assigned_to_lender", e.target.checked)} />
          <span>The policy was assigned to a bank or lender for a loan</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.has_accident_cover} onChange={(e) => set("has_accident_cover", e.target.checked)} />
          <span>It has an accidental death rider or accident cover</span>
        </label>
      </Card>

      <Card title="2. About the death">
        <div className="grid">
          <Field label="Name of the person who died"><input value={form.life_assured} onChange={(e) => set("life_assured", e.target.value)} /></Field>
          <Field label="Date of death"><input type="date" max={today()} value={form.date_of_death} onChange={(e) => set("date_of_death", e.target.value)} /></Field>
          <Field label="Where">
            <select value={form.place_of_death} onChange={(e) => set("place_of_death", e.target.value as DeathClaimInput["place_of_death"])}>
              <option value="hospital">In hospital</option><option value="home">At home</option><option value="other">Elsewhere</option>
            </select>
          </Field>
          <Field label="Cause">
            <select value={form.cause} onChange={(e) => set("cause", e.target.value as DeathClaimInput["cause"])}>
              <option value="illness">Illness</option><option value="accident">Accident</option>
              <option value="suicide">Suicide</option><option value="unknown">Not known yet</option>
            </select>
          </Field>
        </div>
      </Card>

      <Card title="3. The person claiming">
        <div className="grid">
          <Field label="Your name"><input value={form.claimant_name} onChange={(e) => set("claimant_name", e.target.value)} /></Field>
          <Field label="Your relation to them" hint="e.g. wife, son, mother"><input value={form.claimant_relation} onChange={(e) => set("claimant_relation", e.target.value)} /></Field>
          <Field label="Are you the nominee?">
            <select value={form.claimant_is_nominee == null ? "" : form.claimant_is_nominee ? "yes" : "no"}
              onChange={(e) => set("claimant_is_nominee", e.target.value === "" ? null : e.target.value === "yes")}>
              <option value="">Not sure</option><option value="yes">Yes</option><option value="no">No</option>
            </select>
          </Field>
          <Field label="Phone"><input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="Claim intimated to the insurer on" hint="Leave empty if not yet">
            <input type="date" max={today()} value={form.intimated_on ?? ""} onChange={(e) => set("intimated_on", e.target.value || null)} />
          </Field>
        </div>
        {life && form.intimated_on && (
          <label className="check">
            <input type="checkbox" checked={form.under_investigation} onChange={(e) => set("under_investigation", e.target.checked)} />
            <span>The insurer said it is investigating the claim</span>
          </label>
        )}
        {life && form.intimated_on && (
          <Field label="RBI bank rate today (%), optional" hint="To work out the interest if the insurer is late. Find it on rbi.org.in.">
            <input type="number" min={0} max={25} step="0.01" value={form.bank_rate ?? ""} onChange={(e) => set("bank_rate", numOrNull(e.target.value))} />
          </Field>
        )}
        <div className="row">
          <button type="button" onClick={run} disabled={busy || !form.date_of_death}>Show what to do</button>
          {!form.date_of_death && <span className="small muted">Enter the date of death.</span>}
          {busy && <Spinner />}
        </div>
        <ErrorBox error={error} />
      </Card>

      {result && (
        <>
          <Card title="Can the insurer question the policy?">
            <p><Badge tone={contestTone[result.contestable]}>{contestText[result.contestable]}</Badge></p>
            <NoteList notes={result.notes} />
          </Card>

          <Card title="When the insurer must pay">
            <p>
              {result.days_left != null && (
                <><Badge tone={result.days_left < 0 ? "bad" : result.days_left <= 3 ? "warn" : "info"}>
                  {result.days_left < 0 ? `${-result.days_left} days late` : `${result.days_left} days left`}
                </Badge>{" "}</>
              )}
              {result.deadline_note} {life && <RuleRefs ids={["DEATH-TAT"]} />}
            </p>
            {result.deadline && <p className="small muted">Deadline: {niceDate(result.deadline)}</p>}
            {result.interest_due != null && (
              <Notice tone="warn">Interest the insurer owes so far: <strong>{inr(result.interest_due)}</strong> (bank rate + 2% a year on {inr(form.cover_amount)}, from the date of intimation to today). It is in the follow-up letter.</Notice>
            )}
          </Card>

          <Card title="Documents to send">
            <ol className="checklist">{result.documents.map((d) => <li key={d}>{d}</li>)}</ol>
            <p className="small muted">Send copies and keep the originals unless the insurer asks for them. Note the date you sent everything.</p>
          </Card>

          <Card title="Steps">
            <ol className="checklist">{result.steps.map((s) => <li key={s}>{s}</li>)}</ol>
          </Card>

          <Card title="Other money the family may be owed">
            <ul className="plain">
              {result.other_money.map((o) => (
                <li key={o.name} className="benefit">
                  <strong>{o.name}</strong>{" "}
                  {o.status !== "in_force" && <Badge tone="muted">{o.status === "reported" ? "check the current rules" : "general advice"}</Badge>}
                  <div className="small">{o.what}</div>
                  <div className="small muted">{o.how}{o.source_url && <> <a href={o.source_url} target="_blank" rel="noreferrer">More</a></>}</div>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Letter to the insurer: claim intimation" actions={
            <><CopyButton text={result.intimation_letter} /><DownloadButton text={result.intimation_letter} filename="death-claim-intimation.txt" /></>
          }>
            <pre className="letter">{result.intimation_letter}</pre>
          </Card>

          {result.follow_up_letter && (
            <Card title="Follow-up letter: the insurer is late" actions={
              <><CopyButton text={result.follow_up_letter} /><DownloadButton text={result.follow_up_letter} filename="death-claim-follow-up.txt" /></>
            }>
              <pre className="letter">{result.follow_up_letter}</pre>
              <div className="row">
                <button type="button" onClick={track}>Track the 14-day deadline</button>
                {tracked && <button type="button" className="link" onClick={() => setTab("complaints")}>Open Complaints</button>}
              </div>
              {tracked && <Notice tone="good">{tracked}</Notice>}
            </Card>
          )}
          {form.cover_amount > 0 && <p className="small muted">Claim amount used in the letters: {inr(form.cover_amount)}.</p>}
        </>
      )}
      <Disclaimer />
    </div>
  );
}

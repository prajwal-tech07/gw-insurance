import { useEffect, useState } from "react";
import { api, downloadFile } from "../api";
import { Badge, Card, CopyButton, Disclaimer, DownloadButton, ErrorBox, Field, NoteList, Notice, Stat } from "../components/ui";
import { inr, niceDate, num } from "../format";
import { useApp } from "../state";
import type { DueStatus, NomineeRelation, PremiumMode, VaultEntry, VaultEntryData, VaultKind, VaultSummary } from "../types";

export const KIND_LABEL: Record<VaultKind, string> = {
  term_life: "Term life", life_savings: "Life (endowment / money-back / ULIP)", health: "Health",
  personal_accident: "Personal accident", critical_illness: "Critical illness", motor: "Vehicle", home: "Home",
  travel: "Travel", other: "Other",
};
const LIFE: VaultKind[] = ["term_life", "life_savings"];
const dueTone: Record<DueStatus, "good" | "warn" | "bad" | "muted" | "info"> = {
  none: "muted", ok: "good", due_soon: "warn", grace: "bad", lapsed: "bad", ended: "muted",
};

export function emptyEntry(): VaultEntryData {
  return {
    kind: "term_life", insurer: "", policy_number: "", plan_name: "", holder: "", insured: "", cover_amount: 0, premium: 0,
    premium_mode: "yearly", start_date: null, revival_date: null, next_due: null, end_date: null, nominee: "",
    nominee_relation: "", assigned_to_lender: false, agent_contact: "", claim_helpline: "", documents_at: "", notes: "",
  };
}

/** The editable fields of a saved entry (drops the computed checks). */
export function entryData(e: VaultEntry): VaultEntryData {
  const keys = Object.keys(emptyEntry()) as (keyof VaultEntryData)[];
  return Object.fromEntries(keys.map((k) => [k, e[k]])) as unknown as VaultEntryData;
}

/** Same checks as the server (app/vault/checks.py), shown before sending. */
function datesProblem(e: VaultEntryData): string | null {
  if (e.start_date && e.revival_date && e.revival_date < e.start_date) return "The revival date cannot be before the policy start date.";
  if (e.start_date && e.end_date && e.end_date < e.start_date) return "The end or maturity date cannot be before the policy start date.";
  return null;
}

function dueText(e: VaultEntry): string {
  switch (e.due_status) {
    case "ok": return `due in ${e.days_to_due} days`;
    case "due_soon": return e.days_to_due === 0 ? "due today" : `due in ${e.days_to_due} days`;
    case "grace": return `in grace period until ${niceDate(e.grace_until)}`;
    case "lapsed": return "overdue";
    case "ended": return "ended";
    default: return "no due date";
  }
}

function printSheet(text: string): boolean {
  const w = window.open("", "_blank");
  if (!w) return false;
  const esc = text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] as string));
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Family insurance sheet</title></head>`
    + `<body><pre style="font:14px/1.5 system-ui,sans-serif;white-space:pre-wrap">${esc}</pre></body></html>`);
  w.document.close();
  w.focus();
  w.print();
  return true;
}

function EntryForm({ value, onChange }: { value: VaultEntryData; onChange: (v: VaultEntryData) => void }) {
  const set = <K extends keyof VaultEntryData>(k: K, v: VaultEntryData[K]) => onChange({ ...value, [k]: v });
  const life = LIFE.includes(value.kind);
  return (
    <>
      <div className="grid">
        <Field label="Type of insurance">
          <select value={value.kind} onChange={(e) => set("kind", e.target.value as VaultKind)}>
            {(Object.keys(KIND_LABEL) as VaultKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </Field>
        <Field label="Insurer"><input value={value.insurer} onChange={(e) => set("insurer", e.target.value)} placeholder="e.g. XYZ Life Insurance" /></Field>
        <Field label="Plan name"><input value={value.plan_name} onChange={(e) => set("plan_name", e.target.value)} /></Field>
        <Field label="Policy number"><input value={value.policy_number} onChange={(e) => set("policy_number", e.target.value)} /></Field>
        <Field label="Policyholder (who owns it)"><input value={value.holder} onChange={(e) => set("holder", e.target.value)} /></Field>
        <Field label={life ? "Life insured" : value.kind === "motor" ? "Vehicle" : "People insured"}>
          <input value={value.insured} onChange={(e) => set("insured", e.target.value)} />
        </Field>
        <Field label={value.kind === "motor" ? "Insured value (IDV, ₹)" : "Cover / sum assured (₹)"}>
          <input type="number" min={0} value={value.cover_amount || ""} onChange={(e) => set("cover_amount", num(e.target.value))} />
        </Field>
        <Field label="Premium (₹)"><input type="number" min={0} value={value.premium || ""} onChange={(e) => set("premium", num(e.target.value))} /></Field>
        <Field label="Premium paid">
          <select value={value.premium_mode} onChange={(e) => set("premium_mode", e.target.value as PremiumMode)}>
            <option value="yearly">Yearly</option><option value="half_yearly">Half-yearly</option>
            <option value="quarterly">Quarterly</option><option value="monthly">Monthly</option>
            <option value="single">Single premium</option>
          </select>
        </Field>
      </div>
      <fieldset className="subgrid">
        <legend>Dates</legend>
        <Field label="Policy started"><input type="date" value={value.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} /></Field>
        {life && (
          <Field label="Revived on (if it ever lapsed)" hint="The 3-year rule counts from the revival date">
            <input type="date" value={value.revival_date ?? ""} onChange={(e) => set("revival_date", e.target.value || null)} />
          </Field>
        )}
        <Field label={life ? "Next premium due" : "Renewal date"}>
          <input type="date" value={value.next_due ?? ""} onChange={(e) => set("next_due", e.target.value || null)} />
        </Field>
        <Field label={value.kind === "life_savings" ? "Maturity date" : "Cover ends (if fixed)"}>
          <input type="date" value={value.end_date ?? ""} onChange={(e) => set("end_date", e.target.value || null)} />
        </Field>
      </fieldset>
      <fieldset className="subgrid">
        <legend>Nominee and papers</legend>
        <Field label="Nominee"><input value={value.nominee} onChange={(e) => set("nominee", e.target.value)} /></Field>
        <Field label="Nominee's relation to the policyholder">
          <select value={value.nominee_relation} onChange={(e) => set("nominee_relation", e.target.value as NomineeRelation)}>
            <option value="">Not set</option><option value="spouse">Spouse</option><option value="child">Child</option>
            <option value="parent">Parent</option><option value="sibling">Brother / sister</option>
            <option value="other_relative">Other relative</option><option value="other">Someone else</option>
          </select>
        </Field>
        <Field label="Where the papers are kept" hint="e.g. blue file in the cupboard, DigiLocker, email from the insurer">
          <input value={value.documents_at} onChange={(e) => set("documents_at", e.target.value)} />
        </Field>
        <Field label="Insurer's claim helpline"><input value={value.claim_helpline} onChange={(e) => set("claim_helpline", e.target.value)} /></Field>
        <Field label="Agent / advisor contact"><input value={value.agent_contact} onChange={(e) => set("agent_contact", e.target.value)} /></Field>
        {life && (
          <label className="check">
            <input type="checkbox" checked={value.assigned_to_lender} onChange={(e) => set("assigned_to_lender", e.target.checked)} />
            <span>Assigned to a bank or lender (for a loan)</span>
          </label>
        )}
      </fieldset>
      <Field label="Notes"><input value={value.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
    </>
  );
}

function EntryCard({ e, onEdit, onDeleted }: { e: VaultEntry; onEdit: () => void; onDeleted: () => void }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <Card title={<>{KIND_LABEL[e.kind]}: {e.insurer} <Badge tone={dueTone[e.due_status]}>{dueText(e)}</Badge></>} actions={
      <>
        <button type="button" className="secondary" onClick={onEdit}>Edit</button>
        <button type="button" className="secondary danger" onClick={async () => {
          if (!confirm(`Remove this ${KIND_LABEL[e.kind]} policy from the vault?`)) return;
          try { await api.deleteVaultEntry(e.id); onDeleted(); } catch (err) { setError((err as Error).message); }
        }}>Delete</button>
      </>
    }>
      <p className="small">
        {e.plan_name && <>{e.plan_name} · </>}Policy no. {e.policy_number || "not recorded"} · {e.holder}
        {e.cover_amount > 0 && <> · cover {inr(e.cover_amount)}</>}
        {e.premium > 0 && <> · premium {inr(e.premium)}</>}
        {e.next_due && e.due_status !== "ended" && <> · next due {niceDate(e.next_due)}</>}
        {" "}· Nominee: {e.nominee || "not recorded"}
      </p>
      <NoteList notes={e.checks} />
      <ErrorBox error={error} />
    </Card>
  );
}

export function Vault() {
  const { policies, setTab } = useApp();
  const [data, setData] = useState<VaultSummary | null>(null);
  const [form, setForm] = useState<VaultEntryData | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => api.vault().then(setData).catch((e) => setError((e as Error).message));
  useEffect(() => { void load(); }, [policies]);

  async function save() {
    if (!form) return;
    setError(null);
    const problem = datesProblem(form);
    if (problem) { setError(problem); return; }
    try {
      if (editingId) await api.updateVaultEntry(editingId, form);
      else await api.createVaultEntry(form);
      setNotice(editingId ? "Saved." : "Added to the vault.");
      setForm(null); setEditingId(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const hasDates = !!data && (data.entries.some((e) => e.next_due && e.due_status !== "ended") || policies.some((p) => p.terms.period_end));

  return (
    <div className="page">
      <h2>Family insurance vault</h2>
      <Notice tone="info">
        Every policy your family holds in one place: life, health, accident, vehicle and more. ClaimSaathi checks for the
        gaps families usually find out about too late, like a missing nominee, a lapsed premium or papers nobody can
        find. Everything is stored only on this computer.
      </Notice>

      {data && (
        <div className="stats">
          <Stat label="Life cover" value={data.life_cover} />
          <Stat label="Accident cover" value={data.accident_cover} />
          <Stat label="Health cover" value={data.health_cover} />
          <Stat label="Premiums a year" value={data.yearly_premium} />
        </div>
      )}
      {data && (data.missing_nominee > 0 || data.due_soon > 0) && (
        <div className="row">
          {data.missing_nominee > 0 && <Badge tone="bad">{data.missing_nominee} without a nominee</Badge>}
          {data.due_soon > 0 && <Badge tone="warn">{data.due_soon} due soon or in grace period</Badge>}
        </div>
      )}

      <div className="row">
        <button type="button" onClick={() => { setForm(emptyEntry()); setEditingId(null); setNotice(null); }}>Add a policy</button>
        {hasDates && (
          <button type="button" className="secondary" onClick={() => {
            setError(null);
            downloadFile(api.vaultIcsUrl, "family-insurance-reminders.ics").catch((e) => setError((e as Error).message));
          }}>Add all due dates to my calendar</button>
        )}
      </div>
      <ErrorBox error={error} />
      {notice && <Notice tone="good">{notice}</Notice>}

      {form && (
        <Card title={editingId ? "Edit policy" : "Add a policy"}>
          <EntryForm value={form} onChange={setForm} />
          <div className="row">
            <button type="button" onClick={save} disabled={!form.insurer.trim() || !form.holder.trim()}>Save</button>
            <button type="button" className="secondary" onClick={() => { setForm(null); setEditingId(null); }}>Cancel</button>
            {(!form.insurer.trim() || !form.holder.trim()) && <span className="small muted">Insurer and policyholder are needed.</span>}
          </div>
        </Card>
      )}

      {data && data.entries.length === 0 && !form && <p className="muted">No policies in the vault yet. Add the family's life, accident, vehicle and other policies.</p>}
      {data?.entries.map((e) => (
        <EntryCard key={e.id} e={e} onDeleted={load} onEdit={() => {
          setForm(entryData(e)); setEditingId(e.id); setNotice(null); window.scrollTo({ top: 0, behavior: "smooth" });
        }} />
      ))}

      {policies.length > 0 && (
        <Card title="Health policies from My policies">
          <ul className="plain">
            {policies.map((p) => (
              <li key={p.id}>{p.name} · {p.terms.insurer ?? "insurer not set"} · sum insured {inr(p.terms.sum_insured)}
                {p.terms.period_end && <> · renews {niceDate(p.terms.period_end)}</>}</li>
            ))}
          </ul>
          <button type="button" className="link" onClick={() => setTab("policies")}>Open My policies for renewal and benefit details</button>
        </Card>
      )}

      {data && (
        <Card title="Family emergency sheet" actions={
          <>
            <CopyButton text={data.emergency_sheet} />
            <DownloadButton text={data.emergency_sheet} filename="family-insurance-sheet.txt" />
            <button type="button" className="secondary" onClick={() => {
              if (!printSheet(data.emergency_sheet)) setError("The print window was blocked. Allow pop-ups, or use Download.");
            }}>Print</button>
          </>
        }>
          <p className="small muted">Print this or share it with your family, so they know what exists and where the papers are.</p>
          <pre className="letter">{data.emergency_sheet}</pre>
        </Card>
      )}
      <Disclaimer />
    </div>
  );
}

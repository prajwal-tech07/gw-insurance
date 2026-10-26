import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Card, CopyButton, Disclaimer, ErrorBox, Field, Notice, RuleRefs, Spinner } from "../components/ui";
import { inr, niceDate, num, today } from "../format";
import { useApp } from "../state";
import type { Complaint, ComplaintData, DraftInput, DraftResult } from "../types";

const deadlineTone = { upcoming: "info", due_soon: "warn", passed: "bad", done: "good" } as const;

function emptyDraft(): DraftInput {
  return {
    complainant_name: "", address: "", phone: "", email: "", insurer: "", policy_number: "", claim_number: "",
    patient_name: "", hospital: "", admission_date: null, claimed_amount: 0, paid_amount: 0, rejection_date: null,
    grievance_filed_on: null, grievance_reference: "", findings: [], extra_facts: "", polish_with_ai: false,
  };
}

function TrackerCard({ c, onChanged }: { c: Complaint; onChanged: () => void }) {
  const [edit, setEdit] = useState<ComplaintData>(c);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setEdit(c), [c]);
  const set = <K extends keyof ComplaintData>(k: K, v: ComplaintData[K]) => setEdit({ ...edit, [k]: v });
  return (
    <Card title={`${c.title} · ${inr(c.amount_disputed)}`} actions={
      <button type="button" className="secondary danger" onClick={async () => {
        if (!confirm("Delete this complaint tracker?")) return;
        try { await api.deleteComplaint(c.id); onChanged(); } catch (e) { setError((e as Error).message); }
      }}>Delete</button>
    }>
      <Notice tone="info"><strong>Next step:</strong> {c.next_action}</Notice>
      <ul className="plain">
        {c.deadlines.map((d) => (
          <li key={d.label}>
            <Badge tone={deadlineTone[d.status]}>{d.status === "done" ? "done" : d.days_left >= 0 ? `${d.days_left} days left` : `${-d.days_left} days ago`}</Badge>{" "}
            {d.label}: <strong>{niceDate(d.due)}</strong> <RuleRefs ids={d.rule_ids} />
          </li>
        ))}
      </ul>
      <details>
        <summary>Update status</summary>
        <div className="grid">
          <Field label="Insurer replied on"><input type="date" value={edit.insurer_reply_on ?? ""} onChange={(e) => set("insurer_reply_on", e.target.value || null)} /></Field>
          <Field label="Insurer's answer">
            <select value={edit.insurer_outcome} onChange={(e) => set("insurer_outcome", e.target.value as ComplaintData["insurer_outcome"])}>
              <option value="none">No reply yet</option><option value="rejected">Rejected</option>
              <option value="partial">Partly accepted</option><option value="resolved">Resolved / paid</option>
            </select>
          </Field>
          <Field label="Escalated on Bima Bharosa on"><input type="date" value={edit.bima_bharosa_filed_on ?? ""} onChange={(e) => set("bima_bharosa_filed_on", e.target.value || null)} /></Field>
          <Field label="Filed with Ombudsman on"><input type="date" value={edit.ombudsman_filed_on ?? ""} onChange={(e) => set("ombudsman_filed_on", e.target.value || null)} /></Field>
          <Field label="Stage">
            <select value={edit.stage} onChange={(e) => set("stage", e.target.value as ComplaintData["stage"])}>
              <option value="insurer">With the insurer</option><option value="bima_bharosa">Bima Bharosa (IRDAI)</option>
              <option value="ombudsman">Insurance Ombudsman</option><option value="resolved">Resolved</option><option value="closed">Closed</option>
            </select>
          </Field>
          <Field label="Notes"><input value={edit.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
        </div>
        <button type="button" onClick={async () => {
          try { await api.updateComplaint(c.id, edit); onChanged(); } catch (e) { setError((e as Error).message); }
        }}>Save status</button>
      </details>
      <ErrorBox error={error} />
    </Card>
  );
}

export function Complaints() {
  const { analysis, health } = useApp();
  const [form, setForm] = useState<DraftInput>(emptyDraft);
  const [result, setResult] = useState<DraftResult | null>(null);
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = () => api.listComplaints().then(setComplaints).catch((e) => setError((e as Error).message));
  useEffect(() => { void load(); }, []);

  useEffect(() => {
    if (!analysis) return;
    setForm((f) => ({
      ...f,
      findings: analysis.result.findings,
      claimed_amount: analysis.claimedAmount ?? f.claimed_amount,
      paid_amount: analysis.settledAmount ?? f.paid_amount,
      admission_date: analysis.admissionDate ?? f.admission_date,
      insurer: analysis.policy?.terms.insurer ?? f.insurer,
    }));
  }, [analysis]);

  const set = <K extends keyof DraftInput>(k: K, v: DraftInput[K]) => setForm({ ...form, [k]: v });

  async function makeDraft() {
    setBusy(true); setError(null);
    try {
      setResult(await api.draft(form));
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
        title: `Claim ${form.claim_number || ""} ${form.insurer}`.trim(), insurer: form.insurer, policy_number: form.policy_number,
        claim_number: form.claim_number, amount_disputed: result?.amount_disputed ?? Math.max(0, form.claimed_amount - form.paid_amount),
        grievance_filed_on: form.grievance_filed_on ?? today(), insurer_reply_on: null, insurer_outcome: "none",
        bima_bharosa_filed_on: null, ombudsman_filed_on: null, stage: "insurer", notes: "",
      });
      setNotice("Tracking started. Deadlines are below.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const challenged = form.findings.filter((f) => f.verdict === "likely_wrong" || f.verdict === "questionable");

  return (
    <div className="page">
      <h2>Complain and track</h2>
      <Notice tone="info">
        The path: (1) write to the insurer's Grievance Redressal Officer, who must resolve it within 14 days; (2) if not resolved,
        escalate on IRDAI's Bima Bharosa portal; (3) go to the Insurance Ombudsman (free, up to ₹50 lakh) within one year.{" "}
        <RuleRefs ids={["GRV-14", "OMB-14", "OMB-CAP-50"]} />
      </Notice>

      <Card title="1. Your details">
        {analysis ? (
          <Notice tone="good">Using the analysis of your letter: {challenged.length} point(s) to challenge will go into the letter.</Notice>
        ) : (
          <Notice tone="warn">Tip: analyse the insurer's letter first (Rejected / cut claim tab) so the grounds are filled in.</Notice>
        )}
        <div className="grid">
          <Field label="Your name"><input value={form.complainant_name} onChange={(e) => set("complainant_name", e.target.value)} /></Field>
          <Field label="Address"><input value={form.address} onChange={(e) => set("address", e.target.value)} /></Field>
          <Field label="Phone"><input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
          <Field label="Insurer"><input value={form.insurer} onChange={(e) => set("insurer", e.target.value)} /></Field>
          <Field label="Policy number"><input value={form.policy_number} onChange={(e) => set("policy_number", e.target.value)} /></Field>
          <Field label="Claim number"><input value={form.claim_number} onChange={(e) => set("claim_number", e.target.value)} /></Field>
          <Field label="Patient's name"><input value={form.patient_name} onChange={(e) => set("patient_name", e.target.value)} /></Field>
          <Field label="Hospital"><input value={form.hospital} onChange={(e) => set("hospital", e.target.value)} /></Field>
          <Field label="Admission date"><input type="date" value={form.admission_date ?? ""} onChange={(e) => set("admission_date", e.target.value || null)} /></Field>
          <Field label="Amount claimed (₹)"><input type="number" min={0} value={form.claimed_amount} onChange={(e) => set("claimed_amount", num(e.target.value))} /></Field>
          <Field label="Amount paid (₹)"><input type="number" min={0} value={form.paid_amount} onChange={(e) => set("paid_amount", num(e.target.value))} /></Field>
          <Field label="Date of rejection / settlement letter"><input type="date" value={form.rejection_date ?? ""} onChange={(e) => set("rejection_date", e.target.value || null)} /></Field>
          <Field label="Date you complained to the insurer"><input type="date" value={form.grievance_filed_on ?? ""} onChange={(e) => set("grievance_filed_on", e.target.value || null)} /></Field>
          <Field label="Insurer's grievance reference"><input value={form.grievance_reference} onChange={(e) => set("grievance_reference", e.target.value)} /></Field>
        </div>
        <Field label="Anything else to add (facts only)"><textarea rows={3} value={form.extra_facts} onChange={(e) => set("extra_facts", e.target.value)} /></Field>
        {health?.ai_enabled && (
          <label className="check">
            <input type="checkbox" checked={form.polish_with_ai} onChange={(e) => set("polish_with_ai", e.target.checked)} />
            <span>Polish the wording with AI (rejected automatically if any number changes)</span>
          </label>
        )}
        <div className="row">
          <button type="button" onClick={makeDraft} disabled={busy || !form.complainant_name || !form.insurer || !form.policy_number}>Draft the letters</button>
          {busy && <Spinner />}
        </div>
        <ErrorBox error={error} />
      </Card>

      {result && (
        <>
          {result.notes.map((n, i) => <Notice key={i} tone="warn">{n}</Notice>)}
          <Card title="2. Letter to the insurer" actions={<CopyButton text={result.insurer_letter} />}>
            {result.polished_by_ai && <Badge tone="info">wording polished by AI</Badge>}
            <pre className="letter">{result.insurer_letter}</pre>
          </Card>
          <Card title="3. If not resolved in 14 days: Bima Bharosa (IRDAI)" actions={<CopyButton text={result.bima_bharosa_text} />}>
            <p className="small">Register at <a href="https://bimabharosa.irdai.gov.in" target="_blank" rel="noreferrer">bimabharosa.irdai.gov.in</a> and paste this:</p>
            <pre className="letter">{result.bima_bharosa_text}</pre>
          </Card>
          <Card title="4. Insurance Ombudsman complaint" actions={<CopyButton text={result.ombudsman_text} />}>
            <p className="small">File at <a href="https://www.cioins.co.in" target="_blank" rel="noreferrer">cioins.co.in</a>. It is free.</p>
            <pre className="letter">{result.ombudsman_text}</pre>
          </Card>
          <div className="row"><button type="button" onClick={track}>Start tracking deadlines</button></div>
          {notice && <Notice tone="good">{notice}</Notice>}
        </>
      )}

      <h3>Your complaints</h3>
      {complaints.length === 0 && <p className="muted">No complaints tracked yet.</p>}
      {complaints.map((c) => <TrackerCard key={c.id} c={c} onChanged={load} />)}
      <Disclaimer />
    </div>
  );
}

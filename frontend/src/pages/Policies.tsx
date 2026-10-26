import { useEffect, useState } from "react";
import { api } from "../api";
import { WaitingList } from "../components/ClaimBreakdown";
import { emptyTerms, TermsEditor } from "../components/TermsEditor";
import { Badge, Card, ConsentUpload, Disclaimer, ErrorBox, Field, Notice, Spinner } from "../components/ui";
import { inr, today } from "../format";
import { useApp } from "../state";
import type { ExtractionResult, PolicyTerms, SavedPolicy, WaitingStatus } from "../types";

function confidenceTone(c: number): "good" | "warn" | "bad" {
  return c >= 0.8 ? "good" : c >= 0.5 ? "warn" : "bad";
}

function ExtractionTable({ result }: { result: ExtractionResult }) {
  const { t } = useApp();
  const review = result.fields.filter((f) => f.needs_review).length;
  return (
    <>
      <p>
        Read {result.pages} page(s) using the {result.method === "ai+rules" ? "rule-based reader and the AI, cross-checked" : "rule-based reader"}.{" "}
        {review > 0 && <Badge tone="warn">{review} field(s) to check</Badge>}
      </p>
      {result.warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
      <table className="extraction">
        <thead><tr><th>Term</th><th>Found</th><th>Where</th></tr></thead>
        <tbody>
          {result.fields.map((f) => (
            <tr key={f.key} className={f.needs_review ? "row-review" : ""}>
              <td>{t(`field_${f.key}`)}</td>
              <td>
                {f.value ?? <span className="muted">Not found</span>}
                <div className="badges">
                  {f.source !== "not_found" && <Badge tone={confidenceTone(f.confidence)}>{Math.round(f.confidence * 100)}%</Badge>}
                  {f.source === "ai+rules" && <Badge tone="good">rules + AI agree</Badge>}
                  {f.source === "ai" && <Badge tone="info">AI</Badge>}
                  {f.needs_review && <Badge tone="warn">{t("needsReview")}</Badge>}
                </div>
                {f.note && <div className="small muted">{f.note}</div>}
              </td>
              <td className="small">
                {f.citation?.quote ? <>{f.citation.page ? `${t("page")} ${f.citation.page}: ` : ""}<q>{f.citation.quote}</q></> : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function SavedPolicyCard({ policy, onEdit, onDeleted }: { policy: SavedPolicy; onEdit: () => void; onDeleted: () => void }) {
  const [waiting, setWaiting] = useState<WaitingStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.waitingPeriods(policy.terms, today(), "").then(setWaiting).catch((e) => setError((e as Error).message));
  }, [policy]);
  return (
    <Card title={policy.name} actions={
      <>
        <button type="button" className="secondary" onClick={onEdit}>Edit</button>
        <button type="button" className="secondary danger" onClick={async () => {
          if (!confirm(`Delete "${policy.name}"?`)) return;
          try { await api.deletePolicy(policy.id); onDeleted(); } catch (e) { setError((e as Error).message); }
        }}>Delete</button>
      </>
    }>
      <p>{policy.terms.insurer ?? "Insurer not set"} · Sum insured {inr(policy.terms.sum_insured)}
        {policy.terms.period_end && <> · Renews {policy.terms.period_end}</>}</p>
      <h4>Status today</h4>
      <WaitingList items={waiting} />
      <ErrorBox error={error} />
    </Card>
  );
}

export function Policies() {
  const { health, policies, refreshPolicies } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [draft, setDraft] = useState<PolicyTerms | null>(null);
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [useAi, setUseAi] = useState(true);

  async function read(file: File) {
    setBusy(true); setError(null); setSaved(null);
    try {
      const result = await api.extractPolicy(file, useAi);
      setExtraction(result);
      setDraft(result.terms);
      setName(result.terms.policy_name || file.name);
      setEditingId(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function useSample() {
    setBusy(true); setError(null);
    try {
      const blob = await (await fetch(api.samplePolicyUrl)).blob();
      await read(new File([blob], "sample-policy.pdf", { type: "application/pdf" }));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    setError(null);
    try {
      const policy = editingId
        ? await api.updatePolicy(editingId, name || draft.policy_name, draft)
        : await api.savePolicy(name || draft.policy_name, draft);
      await refreshPolicies();
      setSaved(`Saved "${policy.name}". You can now use it in the other tabs.`);
      setDraft(null); setExtraction(null); setEditingId(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="page">
      <h2>My policies</h2>
      <Card title="Read a policy document">
        <p>Upload your policy schedule and wording (PDF). The schedule has your sum insured and dates; the wording has the limits.</p>
        {health?.ai_enabled && (
          <label className="check">
            <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
            <span>Also use the AI reader and cross-check it against the document</span>
          </label>
        )}
        <ConsentUpload accept=".pdf,.png,.jpg,.jpeg,.txt" onFile={read} label="Upload policy" busy={busy} />
        <div className="row">
          <button type="button" className="secondary" disabled={busy} onClick={useSample}>Try the sample policy</button>
          <a className="button secondary" href={api.samplePolicyUrl}>Download sample PDF</a>
          <button type="button" className="secondary" onClick={() => { setDraft(emptyTerms()); setExtraction(null); setName(""); setEditingId(null); }}>
            Enter terms by hand
          </button>
        </div>
        {busy && <Spinner label="Reading the document..." />}
        <ErrorBox error={error} />
        {saved && <Notice tone="good">{saved}</Notice>}
      </Card>

      {extraction && <Card title="What we found"><ExtractionTable result={extraction} /></Card>}

      {draft && (
        <Card title={editingId ? "Edit policy" : "Check and save the terms"}>
          <Notice tone="info">Check every value against your policy before saving, especially the ones marked "Please check".</Notice>
          <Field label="Save as"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Family floater 2026" /></Field>
          <TermsEditor value={draft} onChange={setDraft} />
          <div className="row">
            <button type="button" onClick={save}>Save policy</button>
            <button type="button" className="secondary" onClick={() => { setDraft(null); setExtraction(null); setEditingId(null); }}>Cancel</button>
          </div>
        </Card>
      )}

      <h3>Saved policies</h3>
      {policies.length === 0 && <p className="muted">No saved policies yet.</p>}
      {policies.map((p) => (
        <SavedPolicyCard key={p.id} policy={p} onDeleted={refreshPolicies}
          onEdit={() => { setDraft(p.terms); setName(p.name); setEditingId(p.id); setExtraction(null); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      ))}
      <Disclaimer />
    </div>
  );
}

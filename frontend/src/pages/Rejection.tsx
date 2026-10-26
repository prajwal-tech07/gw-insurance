import { useState } from "react";
import { api } from "../api";
import { PrecedentSummary } from "../components/CaseList";
import { PolicyPicker } from "../components/PolicyPicker";
import { Badge, Card, ConsentUpload, Disclaimer, ErrorBox, Field, Notice, RuleRefs, Spinner } from "../components/ui";
import { inr, numOrNull } from "../format";
import { useApp } from "../state";
import type { AnalysisResult, SavedPolicy, Verdict } from "../types";

const verdictTone: Record<Verdict, "good" | "warn" | "bad" | "muted"> = {
  likely_wrong: "good", questionable: "warn", valid: "bad", not_sure: "muted",
};
const verdictText: Record<Verdict, string> = {
  likely_wrong: "Likely wrong: challenge it", questionable: "Questionable: ask for proof", valid: "Probably valid", not_sure: "Not sure",
};
const strengthText = { strong: "Strong case", moderate: "Worth challenging", weak: "Weak case", unclear: "Unclear" } as const;
const strengthTone = { strong: "good", moderate: "warn", weak: "bad", unclear: "muted" } as const;

export function Rejection() {
  const { t, setTab, setAnalysis } = useApp();
  const [letter, setLetter] = useState("");
  const [policy, setPolicy] = useState<SavedPolicy | null>(null);
  const [admission, setAdmission] = useState("");
  const [claimed, setClaimed] = useState("");
  const [settled, setSettled] = useState("");
  const [diffBilling, setDiffBilling] = useState<"" | "yes" | "no">("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function wrap(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function analyse() {
    await wrap(async () => {
      if (letter.trim().length < 10) throw new Error("Paste the insurer's letter first.");
      setResult(await api.analyze({
        letter_text: letter, terms: policy?.terms ?? null, admission_date: admission || null,
        claimed_amount: numOrNull(claimed), settled_amount: numOrNull(settled),
        hospital_differential_billing: diffBilling === "" ? null : diffBilling === "yes",
      }));
    });
  }

  return (
    <div className="page">
      <h2>Claim rejected or cut?</h2>
      <Card title="1. The insurer's letter">
        <ConsentUpload accept=".pdf,.txt,.png,.jpg,.jpeg" label="Upload letter" busy={busy}
          onFile={(f) => wrap(async () => { const r = await api.readLetter(f); setLetter(r.text); })} />
        <div className="row">
          <button type="button" className="secondary" disabled={busy} onClick={() => wrap(async () => setLetter((await api.sampleText("partial-letter")).text))}>
            Sample: partly paid claim
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => wrap(async () => setLetter((await api.sampleText("rejection-letter")).text))}>
            Sample: rejected claim
          </button>
        </div>
        <Field label="Letter text"><textarea rows={10} value={letter} onChange={(e) => setLetter(e.target.value)} placeholder="Paste the rejection or settlement letter here" /></Field>
      </Card>

      <Card title="2. Details that make the check sharper (optional)">
        <PolicyPicker value={policy} onChange={setPolicy} label="Your policy (for moratorium, waiting periods and limits)" />
        <div className="grid">
          <Field label="Admission date"><input type="date" value={admission} onChange={(e) => setAdmission(e.target.value)} /></Field>
          <Field label="Amount claimed (₹)"><input type="number" min={0} value={claimed} onChange={(e) => setClaimed(e.target.value)} /></Field>
          <Field label="Amount paid (₹)"><input type="number" min={0} value={settled} onChange={(e) => setSettled(e.target.value)} /></Field>
          <Field label="Does the hospital charge differently by room category?">
            <select value={diffBilling} onChange={(e) => setDiffBilling(e.target.value as "" | "yes" | "no")}>
              <option value="">Not sure</option><option value="yes">Yes</option><option value="no">No</option>
            </select>
          </Field>
        </div>
      </Card>

      <div className="row"><button type="button" onClick={analyse} disabled={busy}>{t("analyse")}</button>{busy && <Spinner />}</div>
      <ErrorBox error={error} />

      {result && (
        <>
          <Card title={<><Badge tone={strengthTone[result.case_strength]}>{strengthText[result.case_strength]}</Badge> {result.summary}</>}
            actions={<button type="button" onClick={() => {
              setAnalysis({ result, claimedAmount: numOrNull(claimed), settledAmount: numOrNull(settled), admissionDate: admission || null, policy });
              setTab("complaints");
            }}>Draft my complaint</button>}>
            {result.findings.map((f, i) => (
              <div className="finding" key={i}>
                <h4><Badge tone={verdictTone[f.verdict]}>{verdictText[f.verdict]}</Badge> {f.reason_label}</h4>
                {f.evidence && <blockquote>{f.evidence}</blockquote>}
                <p>{f.explanation}</p>
                <p><strong>What to do:</strong> {f.what_to_do}</p>
                <RuleRefs ids={f.rule_ids} />
              </div>
            ))}
            {result.amounts_found.length > 0 && <p className="small muted">Amounts in the letter: {result.amounts_found.map((a) => inr(a)).join(", ")}</p>}
          </Card>
          <Card title="Similar consumer court rulings"><PrecedentSummary result={result.precedents} /></Card>
          <Notice tone="info">This is guidance to help you write a complaint, not legal advice. For large or complex claims, consider a lawyer or the consumer commission.</Notice>
        </>
      )}
      <Disclaimer />
    </div>
  );
}

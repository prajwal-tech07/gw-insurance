import { useEffect, useState } from "react";
import { api } from "../api";
import { CaseCard, PrecedentSummary } from "../components/CaseList";
import { Card, ErrorBox, Field, Notice } from "../components/ui";
import type { Case, PrecedentSearchResult } from "../types";

const REASONS: Record<string, string> = {
  "": "Any reason",
  pre_existing_non_disclosure: "Pre-existing disease / non-disclosure",
  waiting_period: "Waiting period",
  not_requiring_hospitalisation: "Hospitalisation not needed / under 24 hours",
  documents: "Documents not submitted",
  exclusion: "Policy exclusion",
  policy_cancellation: "Policy cancelled",
};

export function Cases() {
  const [all, setAll] = useState<Case[]>([]);
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<PrecedentSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.allCases().then(setAll).catch((e) => setError((e as Error).message)); }, []);

  async function find() {
    setError(null);
    try {
      setResult(query.trim() || reason ? await api.searchCases(query || REASONS[reason], reason) : null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const filtered = reason ? all.filter((c) => c.reason_codes.includes(reason)) : all;

  return (
    <div className="page">
      <h2>Consumer court rulings</h2>
      <Notice tone="info">
        Real rulings from consumer commissions, taken from the facts in news reports (each links to its source).
        Ombudsman decisions are not public, so these come from consumer courts. Add more with
        <code> python -m app.precedents.import_cases my_cases.csv</code>.
      </Notice>
      <Card title="Search">
        <div className="grid">
          <Field label="Describe the rejection"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. rejected because diabetes was not disclosed" /></Field>
          <Field label="Reason">
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </div>
        <button type="button" onClick={find}>Search</button>
        <ErrorBox error={error} />
      </Card>
      {result ? <Card title="Matches"><PrecedentSummary result={result} /></Card> : (
        <Card title={`All cases (${filtered.length})`}>{filtered.map((c) => <CaseCard key={c.id} c={c} />)}</Card>
      )}
    </div>
  );
}

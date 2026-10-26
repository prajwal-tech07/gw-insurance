import { useState } from "react";
import { api } from "../api";
import { ClaimBreakdown } from "../components/ClaimBreakdown";
import { ClaimDetails, defaultDetails } from "../components/ClaimDetails";
import { ItemsEditor } from "../components/ItemsEditor";
import { PolicyPicker } from "../components/PolicyPicker";
import { Badge, Card, ConsentUpload, Disclaimer, ErrorBox, Notice, Spinner } from "../components/ui";
import { categoryLabel, inr } from "../format";
import { useApp } from "../state";
import type { BillItem, ClaimResult, ParsedBill, SavedPolicy } from "../types";

function ClassifiedTable({ parsed }: { parsed: ParsedBill }) {
  return (
    <table>
      <thead><tr><th>Line</th><th className="num">Amount</th><th>Detected as</th><th>IRDAI list</th></tr></thead>
      <tbody>
        {parsed.items.map((i, n) => (
          <tr key={n} className={i.needs_review ? "row-review" : ""}>
            <td>{i.description}</td>
            <td className="num">{inr(i.amount)}</td>
            <td>
              {categoryLabel[i.category]} <span className="muted small">({i.method === "rules" ? "rules" : `model ${Math.round(i.confidence * 100)}%`})</span>
              {i.needs_review && <> <Badge tone="warn">check</Badge></>}
            </td>
            <td>{i.irdai_list ? <><Badge tone="warn">List {i.irdai_list}</Badge> <span className="small">{i.matched_item}</span></> : <span className="muted">-</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BillCheck() {
  const { t } = useApp();
  const [policy, setPolicy] = useState<SavedPolicy | null>(null);
  const [details, setDetails] = useState(defaultDetails);
  const [items, setItems] = useState<BillItem[]>([]);
  const [parsed, setParsed] = useState<ParsedBill | null>(null);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applyParsed(p: ParsedBill) {
    setParsed(p);
    setItems(p.items.map((i) => ({ description: i.description, amount: i.amount })));
    setResult(null);
  }

  async function wrap(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const subsumed = result?.items.filter((i) => i.irdai_list && i.irdai_list !== "I") ?? [];

  return (
    <div className="page">
      <h2>Check a hospital bill</h2>
      <Card title="1. The bill">
        <ConsentUpload accept=".pdf,.csv,.txt,.png,.jpg,.jpeg" label="Upload bill" busy={busy}
          onFile={(f) => wrap(async () => applyParsed(await api.parseBillFile(f)))} />
        <div className="row">
          <button type="button" className="secondary" disabled={busy}
            onClick={() => wrap(async () => applyParsed(await api.parseBillText((await api.sampleText("bill")).text)))}>
            {t("loadSample")}
          </button>
        </div>
        {busy && <Spinner />}
        {parsed?.warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}
        {parsed && parsed.skipped.length > 0 && (
          <details><summary>{parsed.skipped.length} line(s) skipped (totals, headers)</summary>
            <ul className="small">{parsed.skipped.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </details>
        )}
        {parsed && parsed.items.length > 0 && <ClassifiedTable parsed={parsed} />}
        <h4>Bill lines (you can edit)</h4>
        <ItemsEditor items={items} onChange={(v) => { setItems(v); setResult(null); }} />
      </Card>

      <Card title="2. Policy and stay">
        <PolicyPicker value={policy} onChange={setPolicy} />
        <ClaimDetails value={details} onChange={setDetails} />
      </Card>

      <div className="row">
        <button type="button" disabled={busy || !items.length} onClick={() => wrap(async () => {
          if (!policy) throw new Error("Choose a policy first.");
          setResult(await api.calculate(policy.terms, {
            ...details, eligible_category_rent_per_day: null, si_already_used: 0, deductible_already_met: 0,
            items: items.filter((i) => i.description.trim() && i.amount > 0),
          }));
        })}>{t("calculate")}</button>
      </div>
      <ErrorBox error={error} />

      {result && (
        <Card title="Result">
          {subsumed.length > 0 && (
            <Notice tone="warn">
              The hospital billed {inr(subsumed.reduce((s, i) => s + i.billed, 0))} for items that IRDAI says belong inside
              room, procedure or treatment charges ({subsumed.map((i) => i.description).join(", ")}). Ask the hospital to remove them.
            </Notice>
          )}
          <ClaimBreakdown result={result} />
        </Card>
      )}
      <Disclaimer />
    </div>
  );
}

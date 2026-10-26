import { useState } from "react";
import { api } from "../api";
import { ClaimDetails, defaultDetails } from "../components/ClaimDetails";
import { ItemsEditor } from "../components/ItemsEditor";
import { Badge, Card, Disclaimer, ErrorBox, Notice, RuleRefs, Spinner } from "../components/ui";
import { inr, num } from "../format";
import { useApp } from "../state";
import type { BillItem, OptimizeResult } from "../types";

interface Pick { selected: boolean; siUsed: number; deductibleMet: number }

export function MultiPolicy() {
  const { policies, setTab } = useApp();
  const [picks, setPicks] = useState<Record<number, Pick>>({});
  const [details, setDetails] = useState(() => ({ ...defaultDetails(), room_days: 0 }));
  const [items, setItems] = useState<BillItem[]>([{ description: "Surgery charges", amount: 350000 }]);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (id: number): Pick => picks[id] ?? { selected: false, siUsed: 0, deductibleMet: 0 };
  const setPick = (id: number, patch: Partial<Pick>) => setPicks({ ...picks, [id]: { ...pick(id), ...patch } });
  const chosen = policies.filter((p) => pick(p.id).selected);

  async function run() {
    setBusy(true); setError(null);
    try {
      if (chosen.length < 2) throw new Error("Choose at least two policies.");
      if (chosen.length > 5) throw new Error("Choose at most five policies.");
      setResult(await api.optimize(
        chosen.map((p) => ({ label: p.name, terms: p.terms, si_already_used: pick(p.id).siUsed, deductible_already_met: pick(p.id).deductibleMet })),
        { ...details, eligible_category_rent_per_day: null, si_already_used: 0, deductible_already_met: 0, items },
      ));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h2>Several policies: which to claim first?</h2>
      <Card title="1. Choose your policies">
        {policies.length < 2 && (
          <Notice tone="warn">Save at least two policies first (e.g. company policy and personal policy).{" "}
            <button type="button" className="link" onClick={() => setTab("policies")}>Go to My policies</button></Notice>
        )}
        <table>
          <thead><tr><th /><th>Policy</th><th>Type</th><th className="num">Cover</th><th className="num">Used this year (₹)</th><th className="num">Deductible already met (₹)</th><th className="num">Bonus at risk</th></tr></thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.id}>
                <td><input type="checkbox" aria-label={`Use ${p.name}`} checked={pick(p.id).selected} onChange={(e) => setPick(p.id, { selected: e.target.checked })} /></td>
                <td>{p.name}</td>
                <td>{p.terms.policy_kind.replace(/_/g, " ")}</td>
                <td className="num">{inr(p.terms.sum_insured + p.terms.cumulative_bonus_amount)}</td>
                <td className="num"><input type="number" min={0} aria-label="Cover used this year" value={pick(p.id).siUsed} onChange={(e) => setPick(p.id, { siUsed: num(e.target.value) })} /></td>
                <td className="num">
                  {p.terms.policy_kind === "super_top_up"
                    ? <input type="number" min={0} aria-label="Deductible already met" value={pick(p.id).deductibleMet} onChange={(e) => setPick(p.id, { deductibleMet: num(e.target.value) })} />
                    : <span className="muted">-</span>}
                </td>
                <td className="num">{inr(p.terms.no_claim_bonus_at_risk)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Set the "no-claim bonus you would lose" for each policy in My policies.</p>
      </Card>

      <Card title="2. The hospital bill">
        <ClaimDetails value={details} onChange={setDetails} />
        <ItemsEditor items={items} onChange={setItems} />
      </Card>

      <div className="row"><button type="button" onClick={run} disabled={busy}>Find the best order</button>{busy && <Spinner />}</div>
      <ErrorBox error={error} />

      {result && (
        <>
          <Card title="Best order">
            <ol>{result.best.payouts.map((p) => <li key={p.label}><strong>{p.label}</strong> pays {inr(p.pays)}{p.bonus_lost > 0 && <> (bonus lost {inr(p.bonus_lost)})</>}</li>)}</ol>
            {result.explanation.map((e, i) => <p key={i}>{e}</p>)}
            <RuleRefs ids={result.rule_ids} />
          </Card>
          <Card title="Every order compared">
            <table>
              <thead><tr><th>Order</th><th className="num">Insurers pay</th><th className="num">You pay</th><th className="num">Bonus lost</th></tr></thead>
              <tbody>
                {result.all_orders.map((o, i) => (
                  <tr key={o.order.join(">")} className={i === 0 ? "row-best" : ""}>
                    <td>{o.order.join(" → ")} {i === 0 && <Badge tone="good">Best</Badge>}</td>
                    <td className="num">{inr(o.total_paid)}</td>
                    <td className="num">{inr(o.out_of_pocket)}</td>
                    <td className="num">{inr(o.bonus_lost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
      <Disclaimer />
    </div>
  );
}

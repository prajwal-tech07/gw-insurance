import { useState } from "react";
import { api } from "../api";
import { ClaimBreakdown, WaitingList } from "../components/ClaimBreakdown";
import { ClaimDetails, defaultDetails } from "../components/ClaimDetails";
import { ItemsEditor } from "../components/ItemsEditor";
import { PolicyPicker } from "../components/PolicyPicker";
import { Badge, Card, CopyButton, Disclaimer, ErrorBox, Field, Notice, Spinner } from "../components/ui";
import { categoryLabel, inr, num, pct } from "../format";
import { useApp } from "../state";
import type { BillItem, EstimateResult, RoomOption, SavedPolicy } from "../types";

const SAMPLE_ESTIMATE: BillItem[] = [
  { description: "Surgeon fees", amount: 50000 },
  { description: "Anaesthetist fees", amount: 12000 },
  { description: "OT charges", amount: 20000 },
  { description: "Nursing charges", amount: 6000 },
  { description: "Medicines", amount: 30000 },
  { description: "Lab investigations", amount: 10000 },
  { description: "Gloves and masks", amount: 800 },
];

export function Estimate() {
  const { t } = useApp();
  const [policy, setPolicy] = useState<SavedPolicy | null>(null);
  const [details, setDetails] = useState(defaultDetails);
  const [icuRent, setIcuRent] = useState(0);
  const [rooms, setRooms] = useState<RoomOption[]>([
    { name: "Single private AC room", rent_per_day: 6000 },
    { name: "Twin sharing room", rent_per_day: 4000 },
  ]);
  const [items, setItems] = useState<BillItem[]>(SAMPLE_ESTIMATE);
  const [result, setResult] = useState<EstimateResult | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!policy) { setError("Choose a policy first."); return; }
    setBusy(true); setError(null);
    try {
      const r = await api.estimate({
        terms: policy.terms, ...details, icu_rent_per_day: icuRent,
        room_options: rooms.filter((r) => r.name.trim()), items: items.filter((i) => i.description.trim()),
      });
      setResult(r);
      setOpen(r.recommended);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h2>Before admission: what will I pay?</h2>
      <Card title="1. Policy and treatment">
        <PolicyPicker value={policy} onChange={setPolicy} />
        <ClaimDetails value={details} onChange={setDetails} />
        {details.icu_days > 0 && (
          <Field label="ICU charge per day (₹)"><input type="number" min={0} value={icuRent} onChange={(e) => setIcuRent(num(e.target.value))} /></Field>
        )}
      </Card>

      <Card title="2. Room options at the hospital">
        {rooms.map((r, i) => (
          <div className="row sub-row" key={i}>
            <input aria-label="Room type" value={r.name} onChange={(e) => setRooms(rooms.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <input aria-label="Rent per day" type="number" min={0} value={r.rent_per_day}
              onChange={(e) => setRooms(rooms.map((x, j) => (j === i ? { ...x, rent_per_day: num(e.target.value) } : x)))} />
            <span className="muted">per day</span>
            {rooms.length > 1 && <button type="button" className="secondary" onClick={() => setRooms(rooms.filter((_, j) => j !== i))}>Remove</button>}
          </div>
        ))}
        <button type="button" className="secondary" onClick={() => setRooms([...rooms, { name: "General ward", rent_per_day: 2000 }])}>Add room option</button>
      </Card>

      <Card title="3. Hospital's estimate (everything except room and ICU rent)">
        <p className="muted small">Sample lines are filled in. Replace them with the hospital's itemised estimate.</p>
        <ItemsEditor items={items} onChange={setItems} />
      </Card>

      <div className="row">
        <button type="button" onClick={run} disabled={busy}>{t("calculate")}</button>
        {busy && <Spinner />}
      </div>
      <ErrorBox error={error} />

      {result && (
        <>
          <Notice tone={result.options.some((o) => o.result.blocked) ? "bad" : "good"}><strong>{result.recommendation}</strong></Notice>
          {result.eligible_room_rent_per_day != null && (
            <p>Your policy's room limit: <strong>{inr(result.eligible_room_rent_per_day)} per day</strong>. A room above this also cuts the doctor, nursing and OT charges in proportion.</p>
          )}
          <Card title="Room options compared">
            <table>
              <thead><tr><th>Room</th><th className="num">Rent/day</th><th className="num">{t("insurerPays")}</th><th className="num">{t("youPay")}</th><th>Cut</th><th /></tr></thead>
              <tbody>
                {result.options.map((o) => (
                  <tr key={o.option.name} className={o.option.name === result.recommended ? "row-best" : ""}>
                    <td>{o.option.name} {o.option.name === result.recommended && <Badge tone="good">Best</Badge>}</td>
                    <td className="num">{inr(o.option.rent_per_day)}</td>
                    <td className="num">{inr(o.result.insurer_pays)}</td>
                    <td className="num">{inr(o.result.you_pay)}</td>
                    <td>{o.result.proportion_applied != null ? `paid at ${pct(o.result.proportion_applied, 1)}` : "none"}</td>
                    <td><button type="button" className="secondary" onClick={() => setOpen(open === o.option.name ? null : o.option.name)}>{open === o.option.name ? "Hide" : "Details"}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {result.options.filter((o) => o.option.name === open).map((o) => (
            <Card key={o.option.name} title={`Breakdown: ${o.option.name}`}><ClaimBreakdown result={o.result} /></Card>
          ))}
          {result.items_you_pay.length > 0 && (
            <Card title="What you will pay yourself in the best option">
              <ul className="plain">
                {result.items_you_pay.map((i, n) => (
                  <li key={n}>{i.description} ({categoryLabel[i.category]}): {inr(i.deducted)}. {i.reasons.join("; ")}</li>
                ))}
              </ul>
            </Card>
          )}
          {result.warnings.length > 0 && (
            <Card title="Warnings">{result.warnings.map((w, i) => <Notice key={i} tone="warn">{w}</Notice>)}</Card>
          )}
          <Card title="Questions to ask the hospital's insurance desk" actions={<CopyButton text={result.questions.map((q) => `- ${q}`).join("\n")} />}>
            <ul>{result.questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
          </Card>
          <Card title="Waiting periods on the admission date"><WaitingList items={result.waiting} /></Card>
        </>
      )}
      <Disclaimer />
    </div>
  );
}

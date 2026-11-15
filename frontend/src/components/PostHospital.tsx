import { useEffect, useState } from "react";
import { api } from "../api";
import { inr, niceDate, num, today } from "../format";
import type { PostHospData, PostHospTracker } from "../types";
import { Badge, Card, ErrorBox, Field, Notice } from "./ui";

const statusTone = { open: "good", closing: "warn", closed: "muted" } as const;
const statusText = { open: "Window open", closing: "Closing soon", closed: "Window over: claim now" } as const;

function dataOf(t: PostHospTracker): PostHospData {
  return { title: t.title, discharge_date: t.discharge_date, post_days: t.post_days, bills: t.bills };
}

function TrackerCard({ t, onChanged }: { t: PostHospTracker; onChanged: () => void }) {
  const [bill, setBill] = useState({ on: today(), description: "", amount: "" });
  const [error, setError] = useState<string | null>(null);
  const save = async (data: PostHospData) => {
    setError(null);
    try { await api.updatePostHosp(t.id, data); onChanged(); } catch (e) { setError((e as Error).message); }
  };
  return (
    <div className="case">
      <div className="card-head">
        <strong>{t.title} <Badge tone={statusTone[t.status]}>{statusText[t.status]}</Badge></strong>
        <button type="button" className="secondary danger" onClick={async () => {
          if (!confirm(`Delete the tracker "${t.title}"?`)) return;
          try { await api.deletePostHosp(t.id); onChanged(); } catch (e) { setError((e as Error).message); }
        }}>Delete</button>
      </div>
      <p className="small">Discharged {niceDate(t.discharge_date)} · {t.post_days}-day window ends <strong>{niceDate(t.window_ends)}</strong> · claimable so far <strong>{inr(t.claimable)}</strong></p>
      <Notice tone={t.status === "closing" ? "warn" : "info"}>{t.next_step}</Notice>
      {t.outside.length > 0 && <Notice tone="bad">Outside the window, so usually not claimable: {t.outside.join("; ")}.</Notice>}
      {t.bills.length > 0 && (
        <table>
          <thead><tr><th>Date</th><th>Bill</th><th className="num">Amount</th><th /></tr></thead>
          <tbody>
            {t.bills.map((b, i) => (
              <tr key={i}>
                <td>{niceDate(b.on)}</td><td>{b.description}</td><td className="num">{inr(b.amount)}</td>
                <td><button type="button" className="link" onClick={() => save({ ...dataOf(t), bills: t.bills.filter((_, j) => j !== i) })}>remove</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="grid">
        <Field label="Bill date"><input type="date" value={bill.on} onChange={(e) => setBill({ ...bill, on: e.target.value })} /></Field>
        <Field label="What for"><input value={bill.description} placeholder="e.g. Medicines, follow-up visit" onChange={(e) => setBill({ ...bill, description: e.target.value })} /></Field>
        <Field label="Amount (₹)"><input type="number" min={0} value={bill.amount} onChange={(e) => setBill({ ...bill, amount: e.target.value })} /></Field>
        <button type="button" disabled={!bill.on || !bill.description.trim() || !bill.amount} onClick={async () => {
          await save({ ...dataOf(t), bills: [...t.bills, { on: bill.on, description: bill.description.trim(), amount: num(bill.amount) }] });
          setBill({ on: bill.on, description: "", amount: "" });
        }}>Add bill</button>
      </div>
      <ErrorBox error={error} />
    </div>
  );
}

/** After discharge: count down the post-hospitalisation window and total the bills to claim. */
export function PostHospital() {
  const [list, setList] = useState<PostHospTracker[]>([]);
  const [form, setForm] = useState<PostHospData>({ title: "", discharge_date: today(), post_days: 60, bills: [] });
  const [error, setError] = useState<string | null>(null);
  const load = () => api.postHosp().then(setList).catch((e) => setError((e as Error).message));
  useEffect(() => { void load(); }, []);

  return (
    <Card title="After discharge: post-hospitalisation bills">
      <p className="small muted">Medicines, tests and follow-up visits after discharge are covered for the days your policy allows (often 60 or 90). People forget to keep and claim them: track them here.</p>
      <div className="grid">
        <Field label="Hospital stay (name it)"><input value={form.title} placeholder="e.g. Father's knee surgery" onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Discharge date"><input type="date" value={form.discharge_date} onChange={(e) => setForm({ ...form, discharge_date: e.target.value })} /></Field>
        <Field label="Post-hospitalisation days" hint="From your policy (My policies shows it)"><input type="number" min={1} max={365} value={form.post_days} onChange={(e) => setForm({ ...form, post_days: num(e.target.value) })} /></Field>
        <button type="button" disabled={!form.title.trim() || !form.discharge_date || form.post_days < 1} onClick={async () => {
          setError(null);
          try { await api.createPostHosp({ ...form, title: form.title.trim() }); setForm({ ...form, title: "" }); await load(); }
          catch (e) { setError((e as Error).message); }
        }}>Start tracking</button>
      </div>
      <ErrorBox error={error} />
      {list.map((t) => <TrackerCard key={t.id} t={t} onChanged={load} />)}
    </Card>
  );
}

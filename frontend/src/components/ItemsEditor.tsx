import { useState } from "react";
import { api } from "../api";
import { categoryLabel, inr, num } from "../format";
import type { BillCategory, BillItem } from "../types";
import { ErrorBox } from "./ui";

const CATEGORIES = Object.keys(categoryLabel) as BillCategory[];

/** Editable list of bill / estimate lines. Category "auto" lets the classifier decide. */
export function ItemsEditor({ items, onChange }: { items: BillItem[]; onChange: (items: BillItem[]) => void }) {
  const [paste, setPaste] = useState("");
  const [error, setError] = useState<string | null>(null);
  const update = (i: number, patch: Partial<BillItem>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const total = items.reduce((s, i) => s + (i.amount || 0), 0);

  async function addPasted() {
    setError(null);
    try {
      const parsed = await api.parseBillText(paste);
      if (!parsed.items.length) {
        setError("No lines with amounts found. Put the amount at the end of each line.");
        return;
      }
      onChange([...items, ...parsed.items.map((i) => ({ description: i.description, amount: i.amount }))]);
      setPaste("");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="items-editor">
      <table>
        <thead>
          <tr><th>Item</th><th className="num">Amount (₹)</th><th>Type</th><th /></tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i}>
              <td><input aria-label="Item" value={it.description} onChange={(e) => update(i, { description: e.target.value })} /></td>
              <td className="num"><input aria-label="Amount" type="number" min={0} value={String(it.amount)} onChange={(e) => update(i, { amount: num(e.target.value) })} /></td>
              <td>
                <select aria-label="Type" value={it.category ?? ""} onChange={(e) => update(i, { category: (e.target.value || null) as BillCategory | null })}>
                  <option value="">Auto-detect</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel[c]}</option>)}
                </select>
              </td>
              <td><button type="button" className="secondary" onClick={() => onChange(items.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr><td>Total</td><td className="num">{inr(total)}</td><td colSpan={2} /></tr>
        </tfoot>
      </table>
      <div className="row">
        <button type="button" className="secondary" onClick={() => onChange([...items, { description: "", amount: 0 }])}>Add line</button>
      </div>
      <details>
        <summary>Paste lines from a bill or estimate</summary>
        <textarea rows={5} placeholder={"Surgeon fees 50,000\nOT charges 20,000"} value={paste} onChange={(e) => setPaste(e.target.value)} />
        <button type="button" className="secondary" disabled={!paste.trim()} onClick={addPasted}>Add pasted lines</button>
        <ErrorBox error={error} />
      </details>
    </div>
  );
}

import { useApp } from "../state";
import type { SavedPolicy } from "../types";
import { Field, Notice } from "./ui";

export function PolicyPicker({ value, onChange, label = "Policy" }: {
  value: SavedPolicy | null; onChange: (p: SavedPolicy | null) => void; label?: string;
}) {
  const { policies, setTab } = useApp();
  if (!policies.length) {
    return (
      <Notice tone="warn">
        No saved policy yet.{" "}
        <button type="button" className="link" onClick={() => setTab("policies")}>Add your policy first</button>.
      </Notice>
    );
  }
  return (
    <Field label={label}>
      <select value={value?.id ?? ""} onChange={(e) => onChange(policies.find((p) => p.id === Number(e.target.value)) ?? null)}>
        <option value="">Choose a saved policy</option>
        {policies.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </Field>
  );
}

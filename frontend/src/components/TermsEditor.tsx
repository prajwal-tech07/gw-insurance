import type { PolicyKind, PolicyTerms, RoomLimit, SubLimit } from "../types";
import { num, numOrNull } from "../format";
import { Field } from "./ui";

export const emptyTerms = (): PolicyTerms => ({
  policy_name: "My health policy", insurer: null, policy_kind: "individual", sum_insured: 0, cumulative_bonus_amount: 0,
  room_rent: { kind: "none", percent: null, amount: null, category: null },
  icu_limit: { kind: "none", percent: null, amount: null, category: null },
  copay_percent: 0, copay_min_age: null, deductible: 0, deductible_before_copay: true, sub_limits: [],
  waiting: { initial_days: 30, pre_existing_months: null, specific_disease_months: null, specific_diseases: [], maternity_months: null },
  exclusions: [], consumables_cover: false, room_rent_waiver: false, first_inception_date: null, period_start: null,
  period_end: null, pre_hospitalisation_days: null, post_hospitalisation_days: null, no_claim_bonus_at_risk: 0,
});

const str = (n: number | null | undefined) => (n == null ? "" : String(n));

function LimitEditor({ label, value, onChange, allowCategory }: {
  label: string; value: RoomLimit; onChange: (v: RoomLimit) => void; allowCategory: boolean;
}) {
  return (
    <fieldset className="subgrid">
      <legend>{label}</legend>
      <Field label="Type">
        <select value={value.kind} onChange={(e) => onChange({ ...value, kind: e.target.value as RoomLimit["kind"] })}>
          <option value="none">No limit</option>
          <option value="percent_of_si">% of sum insured per day</option>
          <option value="fixed">Fixed rupees per day</option>
          {allowCategory && <option value="category">Room category (e.g. single private room)</option>}
        </select>
      </Field>
      {value.kind === "percent_of_si" && (
        <>
          <Field label="% of sum insured per day">
            <input type="number" min={0} step="0.1" value={str(value.percent)} onChange={(e) => onChange({ ...value, percent: numOrNull(e.target.value) })} />
          </Field>
          <Field label="Maximum per day (₹, optional)">
            <input type="number" min={0} value={str(value.amount)} onChange={(e) => onChange({ ...value, amount: numOrNull(e.target.value) })} />
          </Field>
        </>
      )}
      {value.kind === "fixed" && (
        <Field label="₹ per day">
          <input type="number" min={0} value={str(value.amount)} onChange={(e) => onChange({ ...value, amount: numOrNull(e.target.value) })} />
        </Field>
      )}
      {value.kind === "category" && (
        <Field label="Room category">
          <input value={value.category ?? ""} onChange={(e) => onChange({ ...value, category: e.target.value })} />
        </Field>
      )}
    </fieldset>
  );
}

export function TermsEditor({ value, onChange }: { value: PolicyTerms; onChange: (t: PolicyTerms) => void }) {
  const set = <K extends keyof PolicyTerms>(key: K, v: PolicyTerms[K]) => onChange({ ...value, [key]: v });
  const setWaiting = (patch: Partial<PolicyTerms["waiting"]>) => set("waiting", { ...value.waiting, ...patch });
  const setSub = (i: number, patch: Partial<SubLimit>) =>
    set("sub_limits", value.sub_limits.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  return (
    <div className="terms-editor">
      <div className="grid">
        <Field label="Policy name"><input value={value.policy_name} onChange={(e) => set("policy_name", e.target.value)} /></Field>
        <Field label="Insurer"><input value={value.insurer ?? ""} onChange={(e) => set("insurer", e.target.value || null)} /></Field>
        <Field label="Policy type">
          <select value={value.policy_kind} onChange={(e) => set("policy_kind", e.target.value as PolicyKind)}>
            <option value="individual">Individual</option>
            <option value="family_floater">Family floater</option>
            <option value="group">Group (employer)</option>
            <option value="top_up">Top-up</option>
            <option value="super_top_up">Super top-up</option>
          </select>
        </Field>
        <Field label="Sum insured (₹)"><input type="number" min={0} value={str(value.sum_insured)} onChange={(e) => set("sum_insured", num(e.target.value))} /></Field>
        <Field label="Cumulative bonus earned (₹)"><input type="number" min={0} value={str(value.cumulative_bonus_amount)} onChange={(e) => set("cumulative_bonus_amount", num(e.target.value))} /></Field>
        <Field label="No-claim bonus you would lose by claiming (₹)" hint="Used when comparing several policies">
          <input type="number" min={0} value={str(value.no_claim_bonus_at_risk)} onChange={(e) => set("no_claim_bonus_at_risk", num(e.target.value))} />
        </Field>
      </div>

      <div className="grid">
        <LimitEditor label="Room rent limit" value={value.room_rent} onChange={(v) => set("room_rent", v)} allowCategory />
        <LimitEditor label="ICU limit" value={value.icu_limit} onChange={(v) => set("icu_limit", v)} allowCategory={false} />
      </div>

      <div className="grid">
        <Field label="Co-pay (%)"><input type="number" min={0} max={100} value={str(value.copay_percent)} onChange={(e) => set("copay_percent", num(e.target.value))} /></Field>
        <Field label="Co-pay applies from age" hint="Leave empty if it applies to everyone">
          <input type="number" min={0} value={str(value.copay_min_age)} onChange={(e) => set("copay_min_age", numOrNull(e.target.value))} />
        </Field>
        <Field label="Deductible (₹)"><input type="number" min={0} value={str(value.deductible)} onChange={(e) => set("deductible", num(e.target.value))} /></Field>
        <label className="check">
          <input type="checkbox" checked={value.deductible_before_copay} onChange={(e) => set("deductible_before_copay", e.target.checked)} />
          <span>Deductible is applied before co-pay</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={value.consumables_cover} onChange={(e) => set("consumables_cover", e.target.checked)} />
          <span>Consumables add-on (covers IRDAI List I items)</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={value.room_rent_waiver} onChange={(e) => set("room_rent_waiver", e.target.checked)} />
          <span>Room rent waiver add-on</span>
        </label>
      </div>

      <fieldset className="subgrid">
        <legend>Waiting periods</legend>
        <Field label="Initial waiting (days)"><input type="number" min={0} value={str(value.waiting.initial_days)} onChange={(e) => setWaiting({ initial_days: num(e.target.value) })} /></Field>
        <Field label="Pre-existing diseases (months)"><input type="number" min={0} value={str(value.waiting.pre_existing_months)} onChange={(e) => setWaiting({ pre_existing_months: numOrNull(e.target.value) })} /></Field>
        <Field label="Specific diseases (months)"><input type="number" min={0} value={str(value.waiting.specific_disease_months)} onChange={(e) => setWaiting({ specific_disease_months: numOrNull(e.target.value) })} /></Field>
        <Field label="Maternity (months)"><input type="number" min={0} value={str(value.waiting.maternity_months)} onChange={(e) => setWaiting({ maternity_months: numOrNull(e.target.value) })} /></Field>
        <Field label="Diseases with a specific waiting period" hint="Comma separated, e.g. cataract, hernia, knee replacement">
          <input value={value.waiting.specific_diseases.join(", ")}
            onChange={(e) => setWaiting({ specific_diseases: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
        </Field>
      </fieldset>

      <fieldset className="subgrid">
        <legend>Dates</legend>
        <Field label="Cover first started" hint="Your first policy with continuous cover (include ported policies)">
          <input type="date" value={value.first_inception_date ?? ""} onChange={(e) => set("first_inception_date", e.target.value || null)} />
        </Field>
        <Field label="Current period from"><input type="date" value={value.period_start ?? ""} onChange={(e) => set("period_start", e.target.value || null)} /></Field>
        <Field label="Current period to"><input type="date" value={value.period_end ?? ""} onChange={(e) => set("period_end", e.target.value || null)} /></Field>
        <Field label="Pre-hospitalisation (days)"><input type="number" min={0} value={str(value.pre_hospitalisation_days)} onChange={(e) => set("pre_hospitalisation_days", numOrNull(e.target.value))} /></Field>
        <Field label="Post-hospitalisation (days)"><input type="number" min={0} value={str(value.post_hospitalisation_days)} onChange={(e) => set("post_hospitalisation_days", numOrNull(e.target.value))} /></Field>
      </fieldset>

      <fieldset className="subgrid wide">
        <legend>Sub-limits</legend>
        {value.sub_limits.length === 0 && <p className="muted">No sub-limits.</p>}
        {value.sub_limits.map((s, i) => (
          <div className="row sub-row" key={i}>
            <input aria-label="Treatment" placeholder="Treatment" value={s.name} onChange={(e) => setSub(i, { name: e.target.value })} />
            <input aria-label="Limit in rupees" type="number" placeholder="₹ limit" value={str(s.amount)} onChange={(e) => setSub(i, { amount: numOrNull(e.target.value) })} />
            <input aria-label="Limit as % of sum insured" type="number" placeholder="% of SI" value={str(s.percent_of_si)} onChange={(e) => setSub(i, { percent_of_si: numOrNull(e.target.value) })} />
            <input aria-label="Words to match in the diagnosis" placeholder="match words (comma)" value={s.keywords.join(", ")}
              onChange={(e) => setSub(i, { keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean) })} />
            <button type="button" className="secondary" onClick={() => set("sub_limits", value.sub_limits.filter((_, j) => j !== i))}>Remove</button>
          </div>
        ))}
        <button type="button" className="secondary" onClick={() => set("sub_limits", [...value.sub_limits, { name: "", keywords: [], amount: null, percent_of_si: null }])}>
          Add sub-limit
        </button>
      </fieldset>

      <Field label="Exclusions (one per line)">
        <textarea rows={4} value={value.exclusions.join("\n")}
          onChange={(e) => set("exclusions", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} />
      </Field>
    </div>
  );
}

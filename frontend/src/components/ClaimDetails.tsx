import { num, numOrNull, today } from "../format";
import { Field } from "./ui";

export interface ClaimDetailsValue {
  admission_date: string;
  patient_age: number | null;
  diagnosis: string;
  is_accident: boolean;
  is_pre_existing: boolean | null;
  room_days: number;
  icu_days: number;
  hospital_differential_billing: boolean;
}

export const defaultDetails = (): ClaimDetailsValue => ({
  admission_date: today(), patient_age: null, diagnosis: "", is_accident: false, is_pre_existing: null,
  room_days: 3, icu_days: 0, hospital_differential_billing: true,
});

export function ClaimDetails({ value, onChange }: { value: ClaimDetailsValue; onChange: (v: ClaimDetailsValue) => void }) {
  const set = <K extends keyof ClaimDetailsValue>(k: K, v: ClaimDetailsValue[K]) => onChange({ ...value, [k]: v });
  return (
    <div className="grid">
      <Field label="Admission date"><input type="date" value={value.admission_date} onChange={(e) => set("admission_date", e.target.value)} /></Field>
      <Field label="Patient's age"><input type="number" min={0} value={value.patient_age ?? ""} onChange={(e) => set("patient_age", numOrNull(e.target.value))} /></Field>
      <Field label="Diagnosis / treatment" hint="Used for waiting periods, sub-limits and exclusions">
        <input value={value.diagnosis} onChange={(e) => set("diagnosis", e.target.value)} placeholder="e.g. cataract surgery, appendicitis" />
      </Field>
      <Field label="Did the condition exist before the policy started?">
        <select value={value.is_pre_existing == null ? "" : value.is_pre_existing ? "yes" : "no"}
          onChange={(e) => set("is_pre_existing", e.target.value === "" ? null : e.target.value === "yes")}>
          <option value="">Not sure</option>
          <option value="no">No</option>
          <option value="yes">Yes</option>
        </select>
      </Field>
      <Field label="Days in a room"><input type="number" min={0} value={value.room_days} onChange={(e) => set("room_days", num(e.target.value))} /></Field>
      <Field label="Days in ICU"><input type="number" min={0} value={value.icu_days} onChange={(e) => set("icu_days", num(e.target.value))} /></Field>
      <label className="check">
        <input type="checkbox" checked={value.is_accident} onChange={(e) => set("is_accident", e.target.checked)} />
        <span>This is due to an accident</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={value.hospital_differential_billing} onChange={(e) => set("hospital_differential_billing", e.target.checked)} />
        <span>Hospital charges doctor/nursing/OT differently by room category (most do)</span>
      </label>
    </div>
  );
}

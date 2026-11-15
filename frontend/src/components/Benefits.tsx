import { useEffect, useState } from "react";
import { api } from "../api";
import { niceDate, today } from "../format";
import { useApp } from "../state";
import type { BenefitInfo, BenefitStatus, PolicyBenefit, SavedPolicy } from "../types";
import { Badge, ErrorBox } from "./ui";

let cached: BenefitInfo[] | null = null;

/** The benefit catalogue (names and how to use each), fetched once. */
export function useBenefitCatalogue(): Record<string, BenefitInfo> {
  const [list, setList] = useState<BenefitInfo[]>(cached ?? []);
  useEffect(() => {
    if (cached) return;
    api.benefits().then((b) => { cached = b; setList(b); }).catch(() => setList([]));
  }, []);
  return Object.fromEntries(list.map((b) => [b.key, b]));
}

const statusTone = { covered: "good", optional: "warn", not_covered: "muted" } as const;
const statusText = { covered: "Covered", optional: "Optional add-on: check your schedule", not_covered: "Not covered" } as const;

function Citation({ b }: { b: PolicyBenefit }) {
  const { t } = useApp();
  if (!b.citation?.quote) return null;
  return <div className="small muted">{b.citation.page ? `${t("page")} ${b.citation.page}: ` : ""}<q>{b.citation.quote}</q></div>;
}

/** Read-only highlight shown right after a policy is read. */
export function BenefitsFound({ benefits }: { benefits: PolicyBenefit[] }) {
  const catalogue = useBenefitCatalogue();
  const usable = benefits.filter((b) => b.status !== "not_covered");
  const notCovered = benefits.filter((b) => b.status === "not_covered");
  if (!benefits.length) {
    return <p className="muted">No extra benefits were found in this document. Many are listed in the policy wording rather than the schedule: upload the wording too, or add them by hand below.</p>;
  }
  return (
    <>
      <p>We found <strong>{usable.length}</strong> benefit(s) that people often forget to use. Check each against your policy.</p>
      <ul className="plain">
        {usable.map((b) => (
          <li key={b.key} className="benefit">
            <strong>{catalogue[b.key]?.name ?? b.key}</strong> <Badge tone={statusTone[b.status]}>{statusText[b.status]}</Badge>
            {b.limit && <> <Badge tone="info">{b.limit}</Badge></>}
            {catalogue[b.key] && <div className="small">{catalogue[b.key].what} <em>{catalogue[b.key].how_to_use}</em></div>}
            <Citation b={b} />
            {b.note && <div className="small warn-text">{b.note}</div>}
          </li>
        ))}
      </ul>
      {notCovered.length > 0 && (
        <details>
          <summary>Mentioned as not covered ({notCovered.length})</summary>
          <ul className="plain">
            {notCovered.map((b) => (
              <li key={b.key}><strong>{catalogue[b.key]?.name ?? b.key}</strong><Citation b={b} /></li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

/** Edit the benefits before saving: change status or limit, remove, or add from the catalogue. */
export function BenefitsEditor({ value, onChange }: { value: PolicyBenefit[]; onChange: (v: PolicyBenefit[]) => void }) {
  const catalogue = useBenefitCatalogue();
  const [adding, setAdding] = useState("");
  const missing = Object.values(catalogue).filter((c) => !value.some((b) => b.key === c.key));
  const patch = (key: string, p: Partial<PolicyBenefit>) => onChange(value.map((b) => (b.key === key ? { ...b, ...p } : b)));
  return (
    <fieldset className="subgrid wide">
      <legend>Benefits in this policy</legend>
      {value.length === 0 && <p className="muted">None recorded.</p>}
      {value.map((b) => (
        <div className="row sub-row" key={b.key}>
          <span className="benefit-name">{catalogue[b.key]?.name ?? b.key}</span>
          <select aria-label={`Status of ${catalogue[b.key]?.name ?? b.key}`} value={b.status}
            onChange={(e) => patch(b.key, { status: e.target.value as BenefitStatus })}>
            <option value="covered">Covered</option>
            <option value="optional">Optional add-on</option>
            <option value="not_covered">Not covered</option>
          </select>
          <input aria-label="Limit" placeholder="Limit, e.g. ₹2,000 a year" value={b.limit ?? ""}
            onChange={(e) => patch(b.key, { limit: e.target.value || null })} />
          <button type="button" className="secondary" onClick={() => onChange(value.filter((x) => x.key !== b.key))}>Remove</button>
        </div>
      ))}
      {missing.length > 0 && (
        <div className="row">
          <select aria-label="Benefit to add" value={adding} onChange={(e) => setAdding(e.target.value)}>
            <option value="">Add a benefit your policy has...</option>
            {missing.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
          </select>
          <button type="button" className="secondary" disabled={!adding} onClick={() => {
            onChange([...value, { key: adding, status: "covered", limit: null, citation: null, note: null, last_used: null }]);
            setAdding("");
          }}>Add</button>
        </div>
      )}
    </fieldset>
  );
}

/** Saved policy: benefits with "mark as used" for the yearly ones. */
export function SavedBenefits({ policy }: { policy: SavedPolicy }) {
  const { refreshPolicies } = useApp();
  const catalogue = useBenefitCatalogue();
  const [error, setError] = useState<string | null>(null);
  const usable = policy.terms.benefits.filter((b) => b.status !== "not_covered");
  if (!usable.length) {
    return <p className="small muted">No benefits recorded. Click Edit to add them, or upload the policy wording again to find them.</p>;
  }
  const start = policy.terms.period_start;
  const usedThisYear = (b: PolicyBenefit) => b.last_used != null && (start == null || b.last_used >= start);

  async function markUsed(key: string, used: boolean) {
    setError(null);
    const benefits = policy.terms.benefits.map((b) => (b.key === key ? { ...b, last_used: used ? today() : null } : b));
    try {
      await api.updatePolicy(policy.id, policy.name, { ...policy.terms, benefits });
      await refreshPolicies();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <ul className="plain">
        {usable.map((b) => {
          const info = catalogue[b.key];
          return (
            <li key={b.key} className="benefit">
              <strong>{info?.name ?? b.key}</strong>
              {b.status === "optional" && <> <Badge tone="warn">if opted</Badge></>}
              {b.limit && <> <Badge tone="info">{b.limit}</Badge></>}
              {info?.resets_yearly && (usedThisYear(b)
                ? <> <Badge tone="good">used {niceDate(b.last_used)}</Badge>{" "}
                  <button type="button" className="link" onClick={() => markUsed(b.key, false)}>undo</button></>
                : <> <Badge tone="warn">not used this year</Badge>{" "}
                  <button type="button" className="link" onClick={() => markUsed(b.key, true)}>mark as used today</button></>)}
              {info && <div className="small muted">{info.how_to_use}</div>}
            </li>
          );
        })}
      </ul>
      <ErrorBox error={error} />
    </>
  );
}

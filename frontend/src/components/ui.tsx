import { cloneElement, useId, useState, type ReactElement, type ReactNode } from "react";
import { useApp } from "../state";
import { inr } from "../format";

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-head">
          {title && <h3>{title}</h3>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Badge({ tone, children }: { tone: "good" | "warn" | "bad" | "info" | "muted"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** A labelled form control. The label is linked by id, so screen readers announce just the label. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactElement }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = cloneElement(children as ReactElement<Record<string, unknown>>, {
    id, "aria-describedby": hint ? hintId : undefined,
  });
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {control}
      {hint && <span id={hintId} className="field-hint">{hint}</span>}
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="alert alert-bad" role="alert">{error}</div> : null;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "bad" | "good"; children: ReactNode }) {
  return <div className={`alert alert-${tone}`}>{children}</div>;
}

export function Spinner({ label = "Working..." }: { label?: string }) {
  return <span className="spinner" role="status">{label}</span>;
}

export function Disclaimer() {
  const { t } = useApp();
  return <p className="disclaimer">{t("disclaimer")}</p>;
}

export function Stat({ label, value, tone }: { label: string; value: number; tone?: "good" | "bad" }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{inr(value)}</span>
    </div>
  );
}

/** Shows one IRDAI rule by id, with its source link. */
export function RuleRef({ id }: { id: string }) {
  const { rules } = useApp();
  const [open, setOpen] = useState(false);
  const rule = rules[id];
  if (!rule) return <span className="rule-chip">{id}</span>;
  return (
    <span className="rule">
      <button type="button" className="rule-chip" onClick={() => setOpen(!open)} aria-expanded={open}>
        {id}: {rule.title}
      </button>
      {open && (
        <span className="rule-body">
          {rule.plain} <em>Source: {rule.source.name}, {rule.source.reference}.</em>{" "}
          {rule.status !== "in_force" && <em>(Status: {rule.status}; check the latest IRDAI text.)</em>}{" "}
          <a href={rule.source.url} target="_blank" rel="noreferrer">Open source</a>
        </span>
      )}
    </span>
  );
}

export function RuleRefs({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <span className="rule-list">{ids.map((id) => <RuleRef key={id} id={id} />)}</span>;
}

export function ConsentUpload({ accept, onFile, label, busy }: {
  accept: string; onFile: (f: File) => void; label: string; busy?: boolean;
}) {
  const { t } = useApp();
  const [agreed, setAgreed] = useState(false);
  return (
    <div className="upload">
      <label className="check">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        <span>{t("consent")}</span>
      </label>
      <label className={`button ${!agreed || busy ? "disabled" : ""}`}>
        {label}
        <input type="file" accept={accept} disabled={!agreed || busy} hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
      </label>
    </div>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="secondary" onClick={async () => {
      try {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      } catch {
        setDone(false);
      }
    }}>{done ? "Copied" : "Copy"}</button>
  );
}

import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, Card, ErrorBox } from "../components/ui";
import { niceDate } from "../format";
import { useApp } from "../state";
import type { Checklist } from "../types";

export function Guide() {
  const { rules } = useApp();
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.checklist().then(setChecklist).catch((e) => setError((e as Error).message)); }, []);

  const ruleList = Object.values(rules).sort((a, b) => a.group.localeCompare(b.group) || (a.effective_from ?? "").localeCompare(b.effective_from ?? ""));

  return (
    <div className="page">
      <h2>Rules and checklist</h2>
      <ErrorBox error={error} />
      {checklist && (
        <Card title="Documents to collect">
          <div className="three-col">
            <div><h4>Before admission</h4><ul>{checklist.before.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><h4>At discharge</h4><ul>{checklist.discharge.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><h4>After discharge</h4><ul>{checklist.after.map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
          <p className="small muted">{checklist.note}</p>
        </Card>
      )}
      <Card title="IRDAI and Ombudsman rules used by ClaimSaathi">
        <p className="small muted">Each rule has the dates it applies. The engine uses the version in force on your claim date. "reported" means
          the rule was checked in secondary sources only: confirm with the IRDAI text before relying on it in a dispute.</p>
        <table>
          <thead><tr><th>Rule</th><th>What it means for you</th><th>In force</th><th>Source</th></tr></thead>
          <tbody>
            {ruleList.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.id}</strong><br />{r.title}<br /><Badge tone={r.status === "in_force" ? "good" : "warn"}>{r.status}</Badge></td>
                <td>{r.plain}{r.date_note && <div className="small muted">{r.date_note}</div>}</td>
                <td className="small">{r.effective_from ? `from ${niceDate(r.effective_from)}` : "earlier"}{r.effective_to ? ` to ${niceDate(r.effective_to)}` : ""}</td>
                <td className="small"><a href={r.source.url} target="_blank" rel="noreferrer">{r.source.name}</a><br />{r.source.reference}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

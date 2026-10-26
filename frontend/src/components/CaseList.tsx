import { inr, niceDate, pct } from "../format";
import type { Case, PrecedentSearchResult } from "../types";
import { Badge, Notice } from "./ui";

const outcomeTone = { policyholder: "good", insurer: "bad", partly: "warn" } as const;
const outcomeText = { policyholder: "Policyholder won", insurer: "Insurer won", partly: "Partly allowed" } as const;

export function CaseCard({ c, score }: { c: Case; score?: number }) {
  return (
    <article className="case">
      <header>
        <Badge tone={outcomeTone[c.outcome]}>{outcomeText[c.outcome]}</Badge>{" "}
        <strong>{c.title}</strong>
        {score != null && <span className="muted small"> · match {Math.round(score * 100)}%</span>}
      </header>
      <p className="small muted">
        {c.forum}{c.case_number ? `, ${c.case_number}` : ""} · {c.decision_date ? niceDate(c.decision_date) : c.date_note} · {c.insurer}
      </p>
      <p><strong>Insurer's reason:</strong> {c.reason_text}</p>
      <p>{c.summary}</p>
      <p><strong>Why:</strong> {c.reasoning}</p>
      <p className="small">
        {c.claim_amount != null && <>Claim {inr(c.claim_amount)} · </>}
        {c.awarded_amount != null && <>Awarded {inr(c.awarded_amount)} (excluding interest) · </>}
        Source: <a href={c.source_url} target="_blank" rel="noreferrer">{c.source_name}</a>
        {c.detail_level === "news_summary" && <> · <Badge tone="warn">from a short news summary: verify against the order</Badge></>}
      </p>
    </article>
  );
}

export function PrecedentSummary({ result }: { result: PrecedentSearchResult }) {
  const c = result.outcome_counts;
  return (
    <div>
      <p>
        <strong>{result.similar_cases}</strong> similar case(s) out of {result.total_cases} in the database:{" "}
        {c.policyholder ?? 0} won by the policyholder, {c.partly ?? 0} partly, {c.insurer ?? 0} won by the insurer.
        {result.policyholder_win_rate != null && <> Weighted by similarity: <strong>{pct(result.policyholder_win_rate)}</strong> in the policyholder's favour.</>}
      </p>
      <Notice tone="warn">{result.confidence_note} {result.bias_note}</Notice>
      {result.matches.map((m) => <CaseCard key={m.case.id} c={m.case} score={m.score} />)}
    </div>
  );
}

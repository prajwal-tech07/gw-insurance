import { categoryLabel, inr, niceDate, pct } from "../format";
import { useApp } from "../state";
import type { ClaimResult, WaitingStatus } from "../types";
import { Badge, Notice, RuleRefs, Stat } from "./ui";

const waitingTone = { ok: "good", blocked: "bad", unknown: "warn", not_applicable: "muted" } as const;
const waitingText = { ok: "OK", blocked: "Not covered yet", unknown: "Check", not_applicable: "Not applicable" } as const;

export function WaitingList({ items }: { items: WaitingStatus[] }) {
  if (!items.length) return null;
  return (
    <ul className="plain">
      {items.map((w) => (
        <li key={w.name}>
          <Badge tone={waitingTone[w.status]}>{waitingText[w.status]}</Badge> <strong>{w.name}</strong> ({w.period}
          {w.covered_from ? `, covered from ${niceDate(w.covered_from)}` : ""}): {w.explanation} <RuleRefs ids={w.rule_ids} />
        </li>
      ))}
    </ul>
  );
}

export function ClaimBreakdown({ result }: { result: ClaimResult }) {
  const { t } = useApp();
  return (
    <div className="breakdown">
      <div className="stats">
        <Stat label={t("totalBill")} value={result.total_billed} />
        <Stat label={t("insurerPays")} value={result.insurer_pays} tone="good" />
        <Stat label={t("youPay")} value={result.you_pay} tone="bad" />
      </div>
      {result.blocked && (
        <Notice tone="bad">
          This claim is likely to be rejected. If it were accepted, the insurer would pay about {inr(result.payable_if_covered)}.
        </Notice>
      )}
      {result.proportion_applied != null && (
        <Notice tone="warn">
          Room above your limit ({inr(result.actual_room_rent_per_day)}/day vs {inr(result.eligible_room_rent_per_day)}/day):
          nursing, doctor and OT charges are paid at {pct(result.proportion_applied, 1)}.
        </Notice>
      )}
      {result.issues.map((i, n) => (
        <Notice key={n} tone={i.level === "block" ? "bad" : i.level === "warn" ? "warn" : "info"}>
          {i.message} <RuleRefs ids={i.rule_ids} />
        </Notice>
      ))}

      {result.steps.length > 0 && (
        <>
          <h4>How the amount was worked out</h4>
          <table>
            <thead><tr><th>Step</th><th>Why</th><th className="num">Cut</th><th className="num">Left</th></tr></thead>
            <tbody>
              {result.steps.map((s, i) => (
                <tr key={i}>
                  <td>{s.name}</td>
                  <td>{s.detail} <RuleRefs ids={s.rule_ids} /></td>
                  <td className="num">{inr(s.deducted)}</td>
                  <td className="num">{inr(s.running_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h4>Line by line</h4>
      <table>
        <thead><tr><th>Item</th><th>Type</th><th className="num">Billed</th><th className="num">Admissible</th><th>Notes</th></tr></thead>
        <tbody>
          {result.items.map((it, i) => (
            <tr key={i} className={it.deducted > 0 ? "row-cut" : ""}>
              <td>{it.description}</td>
              <td>{categoryLabel[it.category]}{it.irdai_list && <> <Badge tone="warn">List {it.irdai_list}</Badge></>}</td>
              <td className="num">{inr(it.billed)}</td>
              <td className="num">{inr(it.payable)}</td>
              <td className="small">{it.reasons.join("; ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Line amounts are before claim-level steps such as sub-limits, deductible, co-pay and the sum insured.</p>

      {result.waiting.length > 0 && (
        <>
          <h4>Waiting periods</h4>
          <WaitingList items={result.waiting} />
        </>
      )}
    </div>
  );
}

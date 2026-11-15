import { useState } from "react";
import { api, type SampleName } from "../api";
import { Badge, Card, Disclaimer, ErrorBox, Field, Notice, RuleRefs, Spinner } from "../components/ui";
import type { ScamResult } from "../types";

const riskTone = { high: "bad", medium: "warn", low: "info" } as const;
const riskText = { high: "High risk", medium: "Warning signs", low: "No common scam signs" } as const;
const linkTone = { high: "bad", medium: "warn", info: "muted" } as const;

const SAMPLES: { name: SampleName; label: string }[] = [
  { name: "scam-bonus", label: "Sample: fake bonus call" },
  { name: "scam-kyc", label: "Sample: fake KYC message" },
  { name: "genuine-renewal", label: "Sample: genuine renewal reminder" },
];

export function ScamCheck() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ScamResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function wrap(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const check = () => wrap(async () => {
    if (text.trim().length < 5) throw new Error("Paste the message, or describe what the caller said.");
    setResult(await api.scamCheck(text));
  });

  return (
    <div className="page">
      <h2>Is this call or message a scam?</h2>
      <Notice tone="info">
        Fake "IRDAI officers", pending-bonus offers, KYC links and claim "agents" cheat many policyholders. Paste an SMS,
        WhatsApp message or email, or type what a caller said, in English, Hinglish or Hindi. Nothing is stored.
      </Notice>

      <Card title="The message">
        <div className="row">
          {SAMPLES.map((s) => (
            <button key={s.name} type="button" className="secondary" disabled={busy}
              onClick={() => wrap(async () => { setText((await api.sampleText(s.name)).text); setResult(null); })}>
              {s.label}
            </button>
          ))}
        </div>
        <Field label="Message or call details">
          <textarea rows={8} maxLength={20000} value={text} onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Caller said he is from IRDAI and my lapsed policy bonus of Rs 2 lakh will be released if I pay GST..." />
        </Field>
        <div className="row">
          <button type="button" onClick={check} disabled={busy}>Check</button>
          {busy && <Spinner />}
        </div>
        <ErrorBox error={error} />
      </Card>

      {result && (
        <>
          <Notice tone={riskTone[result.risk]}>
            <Badge tone={riskTone[result.risk]}>{riskText[result.risk]}</Badge> <strong>{result.headline}</strong>
          </Notice>

          {result.flags.length > 0 && (
            <Card title={`Red flags (${result.flags.length})`}>
              {result.flags.map((f) => (
                <div key={f.code} className="finding">
                  <strong>{f.title}</strong> <Badge tone={f.level === "high" ? "bad" : "warn"}>{f.level}</Badge>
                  <blockquote>{f.evidence}</blockquote>
                  <p>{f.explanation} <RuleRefs ids={f.rule_ids} /></p>
                </div>
              ))}
            </Card>
          )}

          {(result.links.length > 0 || result.phone_numbers.length > 0) && (
            <Card title="Links and numbers in the message">
              <p className="small muted">Shown as text only: do not open them.</p>
              <ul className="plain">
                {result.links.map((l) => (
                  <li key={l.text}>
                    <Badge tone={linkTone[l.level]}>{l.level === "info" ? "check" : l.level}</Badge> <code>{l.text}</code>
                    <div className="small">{l.note}</div>
                  </li>
                ))}
                {result.phone_numbers.map((p) => <li key={p}><code>{p}</code></li>)}
              </ul>
            </Card>
          )}

          <Card title="What to do">
            <ul>{result.what_to_do.map((w) => <li key={w}>{w}</li>)}</ul>
            <h4>Where to report</h4>
            <ul className="plain">
              {result.report.map((r) => (
                <li key={r.name}>
                  <strong>{r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.name}</a> : r.name}</strong>: {r.how}
                </li>
              ))}
            </ul>
            <p className="small muted">{result.note}</p>
          </Card>
        </>
      )}

      <Card title="Remember">
        <ul>
          <li>IRDAI does not sell policies, announce bonuses or refund money. <RuleRefs ids={["SPURIOUS-01"]} /></li>
          <li>No one genuine asks you to pay a fee, tax or GST to release your own bonus, refund or claim.</li>
          <li>Never share an OTP, PIN or password, and never install an app or scan a QR code because a caller asks.</li>
          <li>Pay premiums only to the insurer's own account, and get a receipt. <RuleRefs ids={["PREM-01"]} /></li>
          <li>Look up old policies and unclaimed money yourself on Bima Bharosa. <RuleRefs ids={["UNCLAIMED-01"]} /></li>
        </ul>
      </Card>
      <Disclaimer />
    </div>
  );
}

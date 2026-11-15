import { useEffect, useState } from "react";
import { api } from "../api";
import { useApp, type Tab } from "../state";
import { Card, Disclaimer, Notice } from "../components/ui";
import type { Alert } from "../types";

const FEATURES: { tab: Tab; icon: string; title: string; text: string }[] = [
  { tab: "policies", icon: "📄", title: "1. Decode your policy", text: "Upload the policy PDF. Every term is shown with the page and the exact sentence it came from, plus benefits you may not be using and renewal reminders." },
  { tab: "estimate", icon: "🏥", title: "2. Before admission", text: "Enter the hospital's estimate and room options. See what the insurer pays and which room avoids the proportionate cut." },
  { tab: "bill", icon: "🧾", title: "3. Check the final bill", text: "Each bill line is checked against IRDAI's Lists I-IV and your limits, step by step, with the rule behind every cut." },
  { tab: "multi", icon: "🔀", title: "4. Several policies", text: "Company policy, personal policy and super top-up: find the claim order that leaves you paying least and keeps your bonus." },
  { tab: "rejection", icon: "⚖️", title: "5. Claim rejected or cut?", text: "Paste the insurer's letter. Each reason is checked against dated IRDAI rules and similar consumer court rulings." },
  { tab: "complaints", icon: "📨", title: "6. Complain and track", text: "Get the insurer letter, Bima Bharosa text and Ombudsman complaint, then track every deadline." },
  { tab: "vault", icon: "🗂️", title: "7. Family insurance vault", text: "All the family's policies in one place, checked for missing nominees, lapsing premiums and lost papers, with a sheet to share." },
  { tab: "death", icon: "🕊️", title: "8. Death claim help", text: "Documents to send, the 3-year rule, the insurer's 15-day deadline, other money the family may be owed, and the letters." },
  { tab: "scam", icon: "🛡️", title: "9. Scam check", text: "Paste a call or message about a bonus, refund or KYC. See the red flags and where to report it." },
];

export function Home() {
  const { setTab, t, health, policies } = useApp();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  useEffect(() => { api.alerts().then(setAlerts).catch(() => setAlerts([])); }, [policies]);

  return (
    <div className="page">
      <section className="hero">
        <h2>{t("appTagline")}</h2>
        <p>
          Most claims are approved, but many pay less than people expect because of room-rent limits, items insurers do
          not pay, sub-limits and waiting periods. ClaimSaathi shows you the cuts before they happen, helps you challenge
          the wrong ones, and keeps the whole family's insurance in order.
        </p>
        <div className="row">
          <button type="button" onClick={() => setTab("policies")}>Start with your policy</button>
          <button type="button" className="secondary" onClick={() => setTab("rejection")}>I have a rejection letter</button>
          <button type="button" className="secondary" onClick={() => setTab("scam")}>Check a suspicious call</button>
        </div>
      </section>

      {alerts.length > 0 && (
        <Card title="Needs your attention">
          {alerts.slice(0, 8).map((a, i) => (
            <Notice key={i} tone={a.level}>
              <strong>{a.title}:</strong> {a.text}{" "}
              <button type="button" className="link" onClick={() => setTab(a.tab)}>Open</button>
            </Notice>
          ))}
          {alerts.length > 8 && <p className="small muted">And {alerts.length - 8} more.</p>}
        </Card>
      )}

      <div className="feature-grid">
        {FEATURES.map((f) => (
          <button type="button" key={f.tab} className="feature" onClick={() => setTab(f.tab)}>
            <span className="feature-icon" aria-hidden>{f.icon}</span>
            <strong>{f.title}</strong>
            <span>{f.text}</span>
          </button>
        ))}
      </div>

      <Card title="How it works">
        <ul className="plain">
          <li><strong>The AI reads, the code calculates.</strong> Payouts are worked out by fixed rules you can see, never guessed by a model.</li>
          <li><strong>Rules with dates.</strong> Each IRDAI rule has its start and end date, so the version in force on your claim date is used.</li>
          <li><strong>Your documents are not stored.</strong> Files are read in memory; only the policy terms and vault details you save are kept on this computer.</li>
          <li>
            Reader: {health ? (health.ai_enabled ? `rules + AI cross-check (${health.ai_model})` : "rule-based (free, offline). Add an API key to turn on the AI cross-check.") : "connecting..."}
            {health && !health.ocr_available && " Photo/scanned-page reading is off (Tesseract not installed)."}
          </li>
        </ul>
      </Card>
      <Disclaimer />
    </div>
  );
}

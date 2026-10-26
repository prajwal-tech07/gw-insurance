import { useApp, type Tab } from "../state";
import { Card, Disclaimer } from "../components/ui";

const FEATURES: { tab: Tab; title: string; text: string }[] = [
  { tab: "policies", title: "1. Decode your policy", text: "Upload the policy PDF. Every term is shown with the page and the exact sentence it came from, so you can check it." },
  { tab: "estimate", title: "2. Before admission", text: "Enter the hospital's estimate and room options. See what the insurer pays and which room avoids the proportionate cut." },
  { tab: "bill", title: "3. Check the final bill", text: "Each bill line is checked against IRDAI's Lists I-IV and your limits, step by step, with the rule behind every cut." },
  { tab: "multi", title: "4. Several policies", text: "Company policy, personal policy and super top-up: find the claim order that leaves you paying least and keeps your bonus." },
  { tab: "rejection", title: "5. Claim rejected or cut?", text: "Paste the insurer's letter. Each reason is checked against dated IRDAI rules and similar consumer court rulings." },
  { tab: "complaints", title: "6. Complain and track", text: "Get the insurer letter, Bima Bharosa text and Ombudsman complaint, then track every deadline." },
];

export function Home() {
  const { setTab, t, health } = useApp();
  return (
    <div className="page">
      <section className="hero">
        <h2>{t("appTagline")}</h2>
        <p>
          Most claims are approved, but many pay less than people expect because of room-rent limits, items insurers do
          not pay, sub-limits and waiting periods. ClaimSaathi shows you the cuts before they happen, and helps you
          challenge the wrong ones.
        </p>
        <div className="row">
          <button type="button" onClick={() => setTab("policies")}>Start with your policy</button>
          <button type="button" className="secondary" onClick={() => setTab("rejection")}>I have a rejection letter</button>
        </div>
      </section>

      <div className="feature-grid">
        {FEATURES.map((f) => (
          <button type="button" key={f.tab} className="feature" onClick={() => setTab(f.tab)}>
            <strong>{f.title}</strong>
            <span>{f.text}</span>
          </button>
        ))}
      </div>

      <Card title="How it works">
        <ul className="plain">
          <li><strong>The AI reads, the code calculates.</strong> Payouts are worked out by fixed rules you can see, never guessed by a model.</li>
          <li><strong>Rules with dates.</strong> Each IRDAI rule has its start and end date, so the version in force on your claim date is used.</li>
          <li><strong>Your documents are not stored.</strong> Files are read in memory; only the policy terms you save are kept on this computer.</li>
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

import { BillCheck } from "./pages/BillCheck";
import { Cases } from "./pages/Cases";
import { Complaints } from "./pages/Complaints";
import { Estimate } from "./pages/Estimate";
import { Guide } from "./pages/Guide";
import { Home } from "./pages/Home";
import { MultiPolicy } from "./pages/MultiPolicy";
import { Policies } from "./pages/Policies";
import { Rejection } from "./pages/Rejection";
import { AppProvider, useApp, type Tab } from "./state";

const TABS: Tab[] = ["home", "policies", "estimate", "bill", "multi", "rejection", "complaints", "cases", "guide"];

const PAGES: Record<Tab, () => JSX.Element> = {
  home: Home, policies: Policies, estimate: Estimate, bill: BillCheck, multi: MultiPolicy,
  rejection: Rejection, complaints: Complaints, cases: Cases, guide: Guide,
};

function Shell() {
  const { tab, setTab, lang, setLang, t, health } = useApp();
  const Page = PAGES[tab];
  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>₹</span>
          <div>
            <h1>ClaimSaathi</h1>
            <span className="tag">Health insurance claim helper</span>
          </div>
        </div>
        <div className="row">
          {health === null && <span className="badge badge-bad">server offline</span>}
          {health && <span className={`badge ${health.ai_enabled ? "badge-good" : "badge-muted"}`}>{health.ai_enabled ? "AI cross-check on" : "Free mode (no AI)"}</span>}
          <button type="button" className="secondary" onClick={() => setLang(lang === "en" ? "hi" : "en")} aria-label="Switch language">
            {lang === "en" ? "हिंदी" : "English"}
          </button>
        </div>
      </header>
      <nav className="tabs" aria-label="Sections">
        {TABS.map((id) => (
          <button type="button" key={id} className={id === tab ? "tab active" : "tab"} aria-current={id === tab ? "page" : undefined}
            onClick={() => { setTab(id); window.scrollTo({ top: 0 }); }}>
            {t(`nav_${id}`)}
          </button>
        ))}
      </nav>
      <main>
        <Page />
      </main>
      <footer className="footer">
        ClaimSaathi · Estimates only, not legal or insurance advice · Uploaded files are processed in memory and not stored.
      </footer>
    </>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}

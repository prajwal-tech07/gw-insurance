import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { translate, type Lang } from "./i18n";
import type { AnalysisResult, Health, Rule, SavedPolicy } from "./types";

export type Tab = "home" | "policies" | "estimate" | "bill" | "multi" | "rejection" | "complaints" | "cases" | "guide";

/** What the rejection analysis hands to the complaint drafter. */
export interface AnalysisHandoff {
  result: AnalysisResult;
  claimedAmount: number | null;
  settledAmount: number | null;
  admissionDate: string | null;
  policy: SavedPolicy | null;
}

interface AppState {
  tab: Tab;
  setTab: (t: Tab) => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
  health: Health | null;
  rules: Record<string, Rule>;
  policies: SavedPolicy[];
  refreshPolicies: () => Promise<void>;
  analysis: AnalysisHandoff | null;
  setAnalysis: (a: AnalysisHandoff | null) => void;
}

const Ctx = createContext<AppState | null>(null);

function storedLang(): Lang {
  try {
    return localStorage.getItem("claimsaathi.lang") === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [tab, setTab] = useState<Tab>("home");
  const [lang, setLangState] = useState<Lang>(storedLang);
  const [health, setHealth] = useState<Health | null>(null);
  const [rules, setRules] = useState<Record<string, Rule>>({});
  const [policies, setPolicies] = useState<SavedPolicy[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisHandoff | null>(null);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("claimsaathi.lang", l);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const refreshPolicies = useCallback(async () => {
    try {
      setPolicies(await api.listPolicies());
    } catch {
      setPolicies([]);
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.rules().then((list) => setRules(Object.fromEntries(list.map((r) => [r.id, r])))).catch(() => setRules({}));
    void refreshPolicies();
  }, [refreshPolicies]);

  const value = useMemo<AppState>(() => ({
    tab, setTab, lang, setLang, t: (key: string) => translate(lang, key), health, rules, policies, refreshPolicies,
    analysis, setAnalysis,
  }), [tab, lang, setLang, health, rules, policies, refreshPolicies, analysis]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}

import type {
  Alert, AnalysisResult, BenefitInfo, BillItem, Case, Checklist, ClaimInput, ClaimResult, ClassifiedItem, Complaint,
  ComplaintData, DeathClaimInput, DeathClaimResult, DraftInput, DraftResult, EstimateInput, EstimateResult,
  ExtractionResult, Health, OptimizeResult, ParsedBill, PolicyForClaim, PolicyTerms, PostHospData, PostHospTracker, PrecedentSearchResult,
  RenewalStatus, Rule, SavedPolicy, ScamResult, VaultEntry, VaultEntryData, VaultSummary, WaitingStatus,
} from "./types";

export type SampleName = "bill" | "partial-letter" | "rejection-letter" | "scam-bonus" | "scam-kyc" | "genuine-renewal";

export class ApiError extends Error {}

function message(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? `${(d as { loc?: unknown[] }).loc?.slice(1).join(".") ?? ""} ${(d as { msg: string }).msg}` : String(d)))
      .join("; ");
  }
  return "Something went wrong.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the ClaimSaathi server. Is the backend running?");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message(detail));
  }
  return res.json() as Promise<T>;
}

/** Download a file from the API (e.g. calendar reminders), showing the server's message if it cannot. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new ApiError("Cannot reach the ClaimSaathi server. Is the backend running?");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message(detail));
  }
  saveBlob(await res.blob(), filename);
}

/** Hand the browser a file to save. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const get = <T>(path: string) => request<T>(path);
const send = <T>(method: string, path: string, body: unknown) =>
  request<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const upload = <T>(path: string, file: File, extra: Record<string, string> = {}) => {
  const form = new FormData();
  form.append("file", file);
  Object.entries(extra).forEach(([k, v]) => form.append(k, v));
  return request<T>(path, { method: "POST", body: form });
};

export const api = {
  health: () => get<Health>("/api/health"),
  rules: () => get<Rule[]>("/api/rules"),
  checklist: () => get<Checklist>("/api/checklist"),
  sampleText: (name: SampleName) => get<{ text: string }>(`/api/samples/${name}`),
  samplePolicyUrl: "/api/samples/policy.pdf",
  benefits: () => get<BenefitInfo[]>("/api/benefits"),
  alerts: () => get<Alert[]>("/api/alerts"),

  extractPolicy: (file: File, useAi: boolean) => upload<ExtractionResult>("/api/policies/extract", file, { use_ai: String(useAi) }),
  listPolicies: () => get<SavedPolicy[]>("/api/policies"),
  savePolicy: (name: string, terms: PolicyTerms) => send<SavedPolicy>("POST", "/api/policies", { name, terms }),
  updatePolicy: (id: number, name: string, terms: PolicyTerms) => send<SavedPolicy>("PUT", `/api/policies/${id}`, { name, terms }),
  deletePolicy: (id: number) => send<{ deleted: number }>("DELETE", `/api/policies/${id}`, {}),
  waitingPeriods: (terms: PolicyTerms, admission_date: string, diagnosis: string) =>
    send<WaitingStatus[]>("POST", "/api/waiting-periods", { terms, admission_date, diagnosis }),
  renewal: (body: { terms: PolicyTerms; current_premium?: number | null; renewal_premium?: number | null; oldest_member_age?: number | null }) =>
    send<RenewalStatus>("POST", "/api/renewal", body),
  renewalIcsUrl: (id: number) => `/api/policies/${id}/renewal.ics`,

  parseBillFile: (file: File) => upload<ParsedBill>("/api/bills/parse", file),
  parseBillText: (text: string) => send<ParsedBill>("POST", "/api/bills/parse-text", { text }),
  classify: (items: BillItem[]) => send<ClassifiedItem[]>("POST", "/api/bills/classify", { items }),
  calculate: (terms: PolicyTerms, claim: ClaimInput) => send<ClaimResult>("POST", "/api/claims/calculate", { terms, claim }),
  estimate: (body: EstimateInput) => send<EstimateResult>("POST", "/api/estimate", body),
  optimize: (policies: PolicyForClaim[], claim: ClaimInput) => send<OptimizeResult>("POST", "/api/optimize", { policies, claim }),

  readLetter: (file: File) => upload<{ text: string; warnings: string[] }>("/api/rejections/read-letter", file),
  analyze: (body: {
    letter_text: string; terms: PolicyTerms | null; admission_date: string | null;
    claimed_amount: number | null; settled_amount: number | null; hospital_differential_billing: boolean | null;
  }) => send<AnalysisResult>("POST", "/api/rejections/analyze", body),
  draft: (body: DraftInput) => send<DraftResult>("POST", "/api/complaints/draft", body),
  listComplaints: () => get<Complaint[]>("/api/complaints"),
  createComplaint: (body: ComplaintData) => send<Complaint>("POST", "/api/complaints", body),
  updateComplaint: (id: number, body: ComplaintData) => send<Complaint>("PUT", `/api/complaints/${id}`, body),
  deleteComplaint: (id: number) => send<{ deleted: number }>("DELETE", `/api/complaints/${id}`, {}),

  vault: () => get<VaultSummary>("/api/vault"),
  createVaultEntry: (body: VaultEntryData) => send<VaultEntry>("POST", "/api/vault", body),
  updateVaultEntry: (id: number, body: VaultEntryData) => send<VaultEntry>("PUT", `/api/vault/${id}`, body),
  deleteVaultEntry: (id: number) => send<{ deleted: number }>("DELETE", `/api/vault/${id}`, {}),
  vaultIcsUrl: "/api/vault/calendar.ics",
  deathClaim: (body: DeathClaimInput) => send<DeathClaimResult>("POST", "/api/death-claim", body),
  postHosp: () => get<PostHospTracker[]>("/api/post-hosp"),
  createPostHosp: (body: PostHospData) => send<PostHospTracker>("POST", "/api/post-hosp", body),
  updatePostHosp: (id: number, body: PostHospData) => send<PostHospTracker>("PUT", `/api/post-hosp/${id}`, body),
  deletePostHosp: (id: number) => send<{ deleted: number }>("DELETE", `/api/post-hosp/${id}`, {}),
  scamCheck: (text: string) => send<ScamResult>("POST", "/api/scam-check", { text }),

  allCases: () => get<Case[]>("/api/precedents/all"),
  searchCases: (q: string, reason = "") =>
    get<PrecedentSearchResult>(`/api/precedents?q=${encodeURIComponent(q)}&reason=${encodeURIComponent(reason)}`),
};

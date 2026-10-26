import type {
  AnalysisResult, BillItem, Case, Checklist, ClaimInput, ClaimResult, ClassifiedItem, Complaint, ComplaintData,
  DraftInput, DraftResult, EstimateInput, EstimateResult, ExtractionResult, Health, OptimizeResult, ParsedBill,
  PolicyForClaim, PolicyTerms, PrecedentSearchResult, Rule, SavedPolicy, WaitingStatus,
} from "./types";

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
  sampleText: (name: "bill" | "partial-letter" | "rejection-letter") => get<{ text: string }>(`/api/samples/${name}`),
  samplePolicyUrl: "/api/samples/policy.pdf",

  extractPolicy: (file: File, useAi: boolean) => upload<ExtractionResult>("/api/policies/extract", file, { use_ai: String(useAi) }),
  listPolicies: () => get<SavedPolicy[]>("/api/policies"),
  savePolicy: (name: string, terms: PolicyTerms) => send<SavedPolicy>("POST", "/api/policies", { name, terms }),
  updatePolicy: (id: number, name: string, terms: PolicyTerms) => send<SavedPolicy>("PUT", `/api/policies/${id}`, { name, terms }),
  deletePolicy: (id: number) => send<{ deleted: number }>("DELETE", `/api/policies/${id}`, {}),
  waitingPeriods: (terms: PolicyTerms, admission_date: string, diagnosis: string) =>
    send<WaitingStatus[]>("POST", "/api/waiting-periods", { terms, admission_date, diagnosis }),

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

  allCases: () => get<Case[]>("/api/precedents/all"),
  searchCases: (q: string, reason = "") =>
    get<PrecedentSearchResult>(`/api/precedents?q=${encodeURIComponent(q)}&reason=${encodeURIComponent(reason)}`),
};

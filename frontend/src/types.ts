// Mirrors backend/app/models.py. Dates are "YYYY-MM-DD" strings.

export interface Citation { page: number | null; quote: string | null }

export type LimitKind = "none" | "percent_of_si" | "fixed" | "category";
export interface RoomLimit { kind: LimitKind; percent: number | null; amount: number | null; category: string | null }

export interface SubLimit { name: string; keywords: string[]; amount: number | null; percent_of_si: number | null }

export interface WaitingPeriods {
  initial_days: number;
  pre_existing_months: number | null;
  specific_disease_months: number | null;
  specific_diseases: string[];
  maternity_months: number | null;
}

export type PolicyKind = "individual" | "family_floater" | "group" | "top_up" | "super_top_up";

export interface PolicyTerms {
  policy_name: string;
  insurer: string | null;
  policy_kind: PolicyKind;
  sum_insured: number;
  cumulative_bonus_amount: number;
  room_rent: RoomLimit;
  icu_limit: RoomLimit;
  copay_percent: number;
  copay_min_age: number | null;
  deductible: number;
  deductible_before_copay: boolean;
  sub_limits: SubLimit[];
  waiting: WaitingPeriods;
  exclusions: string[];
  consumables_cover: boolean;
  room_rent_waiver: boolean;
  first_inception_date: string | null;
  period_start: string | null;
  period_end: string | null;
  pre_hospitalisation_days: number | null;
  post_hospitalisation_days: number | null;
  no_claim_bonus_at_risk: number;
  premium_mode: PremiumMode;
  benefits: PolicyBenefit[];
}

export interface ExtractedField {
  key: string;
  label: string;
  value: string | null;
  confidence: number;
  citation: Citation | null;
  source: "rules" | "ai" | "ai+rules" | "not_found";
  needs_review: boolean;
  note: string | null;
}

export interface ExtractionResult { terms: PolicyTerms; fields: ExtractedField[]; pages: number; method: string; warnings: string[] }

export interface SavedPolicy { id: number; name: string; terms: PolicyTerms; created_at: string; updated_at: string }

export type BillCategory =
  | "room_rent" | "icu" | "nursing" | "professional_fees" | "ot_charges" | "pharmacy"
  | "consumables" | "implants" | "diagnostics" | "ambulance" | "other";
export type IrdaiList = "I" | "II" | "III" | "IV";

export interface BillItem { description: string; amount: number; category?: BillCategory | null; irdai_list?: IrdaiList | null }

export interface ClassifiedItem extends BillItem {
  category: BillCategory;
  matched_item: string | null;
  confidence: number;
  method: "rules" | "model" | "user";
  needs_review: boolean;
  payable_separately: boolean;
  reason: string;
}

export interface ParsedBill { items: ClassifiedItem[]; total: number; skipped: string[]; warnings: string[]; overcharges: Issue[] }

export interface ClaimInput {
  admission_date: string;
  patient_age: number | null;
  diagnosis: string;
  is_accident: boolean;
  is_pre_existing: boolean | null;
  room_days: number;
  icu_days: number;
  hospital_differential_billing: boolean;
  eligible_category_rent_per_day: number | null;
  items: BillItem[];
  si_already_used: number;
  deductible_already_met: number;
}

export interface ItemResult {
  description: string; category: BillCategory; irdai_list: IrdaiList | null;
  billed: number; payable: number; deducted: number; reasons: string[];
}
export interface Step { name: string; detail: string; deducted: number; running_total: number; rule_ids: string[] }
export interface Issue { level: "block" | "warn" | "info"; code: string; message: string; rule_ids: string[] }
export interface WaitingStatus {
  name: string; period: string; covered_from: string | null;
  status: "ok" | "blocked" | "unknown" | "not_applicable"; explanation: string; rule_ids: string[];
}

export interface ClaimResult {
  total_billed: number; insurer_pays: number; you_pay: number; payable_if_covered: number; blocked: boolean;
  proportion_applied: number | null; eligible_room_rent_per_day: number | null; actual_room_rent_per_day: number | null;
  items: ItemResult[]; steps: Step[]; issues: Issue[]; waiting: WaitingStatus[];
}

export interface RoomOption { name: string; rent_per_day: number }
export interface EstimateInput {
  terms: PolicyTerms; admission_date: string; patient_age: number | null; diagnosis: string; is_accident: boolean;
  is_pre_existing: boolean | null; room_days: number; icu_days: number; icu_rent_per_day: number;
  hospital_differential_billing: boolean; room_options: RoomOption[]; items: BillItem[];
}
export interface EstimateResult {
  options: { option: RoomOption; result: ClaimResult }[];
  recommended: string; recommendation: string; eligible_room_rent_per_day: number | null;
  waiting: WaitingStatus[]; warnings: string[]; questions: string[]; items_you_pay: ItemResult[];
}

export interface PolicyForClaim { label: string; terms: PolicyTerms; si_already_used: number; deductible_already_met: number }
export interface PolicyPayout { label: string; pays: number; bonus_lost: number }
export interface OrderResult { order: string[]; payouts: PolicyPayout[]; total_paid: number; out_of_pocket: number; bonus_lost: number }
export interface OptimizeResult { total_billed: number; best: OrderResult; all_orders: OrderResult[]; explanation: string[]; rule_ids: string[] }

export type Verdict = "valid" | "questionable" | "likely_wrong" | "not_sure";
export interface Finding {
  reason_code: string; reason_label: string; evidence: string; verdict: Verdict;
  explanation: string; what_to_do: string; rule_ids: string[];
}

export interface Case {
  id: string; title: string; forum: string; forum_level: "district" | "state" | "national"; place: string | null;
  decision_date: string | null; date_note: string | null; case_number: string | null; insurer: string; policy_type: string;
  reason_codes: string[]; reason_text: string; outcome: "policyholder" | "insurer" | "partly";
  claim_amount: number | null; awarded_amount: number | null; summary: string; reasoning: string;
  source_name: string; source_url: string; detail_level: "article" | "news_summary";
}
export interface PrecedentSearchResult {
  matches: { case: Case; score: number }[]; total_cases: number; similar_cases: number;
  outcome_counts: Record<string, number>; policyholder_win_rate: number | null; confidence_note: string; bias_note: string;
}

export interface AnalysisResult {
  findings: Finding[]; amounts_found: number[]; clause_cited: boolean;
  case_strength: "strong" | "moderate" | "weak" | "unclear"; summary: string; precedents: PrecedentSearchResult;
}

export interface DraftInput {
  complainant_name: string; address: string; phone: string; email: string; insurer: string; policy_number: string;
  claim_number: string; patient_name: string; hospital: string; admission_date: string | null; claimed_amount: number;
  paid_amount: number; rejection_date: string | null; grievance_filed_on: string | null; grievance_reference: string;
  findings: Finding[]; extra_facts: string; polish_with_ai: boolean;
}
export interface DraftResult {
  insurer_letter: string; bima_bharosa_text: string; ombudsman_text: string; amount_disputed: number;
  polished_by_ai: boolean; notes: string[];
}

export type ComplaintStage = "insurer" | "bima_bharosa" | "ombudsman" | "resolved" | "closed";
export interface ComplaintData {
  title: string; insurer: string; policy_number: string; claim_number: string; amount_disputed: number;
  grievance_filed_on: string; insurer_reply_on: string | null; insurer_outcome: "none" | "rejected" | "partial" | "resolved";
  bima_bharosa_filed_on: string | null; ombudsman_filed_on: string | null; stage: ComplaintStage; notes: string;
}
export interface Deadline { label: string; due: string; days_left: number; status: "upcoming" | "due_soon" | "passed" | "done"; rule_ids: string[] }
export interface Complaint extends ComplaintData { id: number; next_action: string; deadlines: Deadline[] }

export interface Rule {
  id: string; group: string; title: string; plain: string; effective_from: string | null; effective_to: string | null;
  status: string; date_note: string | null; source: { name: string; reference: string; url: string; also: string | null };
}

export interface Health { status: string; ai_enabled: boolean; ai_model: string; ocr_available: boolean }

export interface Checklist { before: string[]; discharge: string[]; after: string[]; note: string }

// ---------------------------------------------------------------- hidden benefits and renewal guard

export type PremiumMode = "yearly" | "half_yearly" | "quarterly" | "monthly" | "single";
export type BenefitStatus = "covered" | "optional" | "not_covered";
export interface PolicyBenefit {
  key: string; status: BenefitStatus; limit: string | null; citation: Citation | null; note: string | null; last_used: string | null;
}
export interface BenefitInfo { key: string; name: string; what: string; how_to_use: string; resets_yearly: boolean }

export type Tone = "bad" | "warn" | "info" | "good";
export interface Note { level: Tone; text: string; rule_ids: string[] }

export interface RenewalStatus {
  status: "unknown" | "active" | "due_soon" | "grace" | "lapsed";
  renew_by: string | null; grace_until: string | null; days_left: number | null; headline: string;
  at_stake: string[]; notes: Note[]; unused_benefits: string[]; premium_check: Note | null;
}

// ---------------------------------------------------------------- family vault

export type VaultKind = "health" | "term_life" | "life_savings" | "personal_accident" | "critical_illness" | "motor" | "home" | "travel" | "other";
export type NomineeRelation = "" | "spouse" | "child" | "parent" | "sibling" | "other_relative" | "other";
export interface VaultEntryData {
  kind: VaultKind; insurer: string; policy_number: string; plan_name: string; holder: string; insured: string;
  cover_amount: number; premium: number; premium_mode: PremiumMode; start_date: string | null; revival_date: string | null;
  next_due: string | null; end_date: string | null; nominee: string; nominee_relation: NomineeRelation;
  assigned_to_lender: boolean; agent_contact: string; claim_helpline: string; documents_at: string; notes: string;
}
export type DueStatus = "none" | "ok" | "due_soon" | "grace" | "lapsed" | "ended";
export interface VaultEntry extends VaultEntryData {
  id: number; checks: Note[]; due_status: DueStatus; days_to_due: number | null; grace_until: string | null;
}
export interface VaultSummary {
  entries: VaultEntry[]; health_policies: number; life_cover: number; accident_cover: number; health_cover: number;
  yearly_premium: number; missing_nominee: number; due_soon: number; emergency_sheet: string;
}

// ---------------------------------------------------------------- death claim helper

export type DeathClaimKind = "term_life" | "life_savings" | "personal_accident" | "health" | "other";
export interface DeathClaimInput {
  kind: DeathClaimKind; insurer: string; policy_number: string; life_assured: string; claimant_name: string;
  claimant_relation: string; claimant_is_nominee: boolean | null; cover_amount: number; policy_start: string | null;
  revival_date: string | null; date_of_death: string; place_of_death: "hospital" | "home" | "other";
  cause: "illness" | "accident" | "suicide" | "unknown"; intimated_on: string | null; under_investigation: boolean;
  assigned_to_lender: boolean; has_accident_cover: boolean; phone: string; email: string; bank_rate: number | null;
}
export interface OtherCover { name: string; what: string; how: string; source_url: string; status: string }
export interface DeathClaimResult {
  contestable: "no" | "limited" | "not_applicable" | "unknown"; contest_note: string; contest_until: string | null;
  notes: Note[]; documents: string[]; deadline: string | null; days_left: number | null; deadline_note: string;
  steps: string[]; other_money: OtherCover[]; intimation_letter: string; follow_up_letter: string | null;
  interest_due: number | null;
}

// ---------------------------------------------------------------- scam checker and alerts

export interface ScamFlag { code: string; title: string; level: "high" | "medium"; evidence: string; explanation: string; rule_ids: string[] }
export interface ScamLink { text: string; domain: string; level: "high" | "medium" | "info"; note: string }
export interface ReportChannel { name: string; how: string; url: string | null }
export interface ScamResult {
  risk: "high" | "medium" | "low"; headline: string; flags: ScamFlag[]; links: ScamLink[]; phone_numbers: string[];
  what_to_do: string[]; report: ReportChannel[]; note: string;
}

export interface Alert { level: Tone; title: string; text: string; tab: "policies" | "vault" | "complaints" | "bill" }

export interface PostHospBill { on: string; description: string; amount: number }
export interface PostHospData { title: string; discharge_date: string; post_days: number; bills: PostHospBill[] }
export interface PostHospTracker extends PostHospData {
  id: number; window_ends: string; days_left: number; status: "open" | "closing" | "closed";
  claimable: number; outside: string[]; next_step: string;
}

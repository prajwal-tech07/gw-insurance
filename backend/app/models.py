"""Pydantic schemas shared by the engine, the API and the frontend."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- policy terms

class Citation(BaseModel):
    page: int | None = None
    quote: str | None = None


class RoomLimit(BaseModel):
    """A per-day limit for a normal room or ICU."""

    kind: Literal["none", "percent_of_si", "fixed", "category"] = "none"
    percent: float | None = None  # % of sum insured per day
    amount: float | None = None  # fixed Rs/day, or the cap when kind is percent_of_si
    category: str | None = None  # e.g. "single private AC room"


class SubLimit(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    amount: float | None = None
    percent_of_si: float | None = None


class WaitingPeriods(BaseModel):
    initial_days: int = 30
    pre_existing_months: int | None = None
    specific_disease_months: int | None = None
    specific_diseases: list[str] = Field(default_factory=list)
    maternity_months: int | None = None


PolicyKind = Literal["individual", "family_floater", "group", "top_up", "super_top_up"]
PremiumMode = Literal["yearly", "half_yearly", "quarterly", "monthly", "single"]
BenefitStatus = Literal["covered", "optional", "not_covered"]


class PolicyBenefit(BaseModel):
    """A benefit people often forget they have (health check-up, teleconsult, AYUSH...)."""

    key: str  # catalogue key, see app/extraction/benefits.py
    status: BenefitStatus = "covered"
    limit: str | None = None  # e.g. "Rs 2,000 per policy year"
    citation: Citation | None = None
    note: str | None = None
    last_used: date | None = None


class PolicyTerms(BaseModel):
    policy_name: str = "My health policy"
    insurer: str | None = None
    policy_kind: PolicyKind = "individual"
    sum_insured: float = Field(default=0, ge=0)
    cumulative_bonus_amount: float = Field(default=0, ge=0)
    room_rent: RoomLimit = Field(default_factory=RoomLimit)
    icu_limit: RoomLimit = Field(default_factory=RoomLimit)
    copay_percent: float = Field(default=0, ge=0, le=100)
    copay_min_age: int | None = None  # co-pay applies only at/above this age
    deductible: float = Field(default=0, ge=0)
    deductible_before_copay: bool = True
    sub_limits: list[SubLimit] = Field(default_factory=list)
    waiting: WaitingPeriods = Field(default_factory=WaitingPeriods)
    exclusions: list[str] = Field(default_factory=list)
    consumables_cover: bool = False
    room_rent_waiver: bool = False
    first_inception_date: date | None = None  # start of continuous cover
    period_start: date | None = None
    period_end: date | None = None
    pre_hospitalisation_days: int | None = None
    post_hospitalisation_days: int | None = None
    no_claim_bonus_at_risk: float = Field(default=0, ge=0)  # Rs of bonus lost if claimed
    premium_mode: PremiumMode = "yearly"  # sets the grace period
    benefits: list[PolicyBenefit] = Field(default_factory=list)


class BenefitInfo(BaseModel):
    key: str
    name: str
    what: str
    how_to_use: str
    resets_yearly: bool


class ExtractedField(BaseModel):
    key: str
    label: str
    value: str | None = None
    confidence: float = 0
    citation: Citation | None = None
    source: Literal["rules", "ai", "ai+rules", "not_found"] = "rules"
    needs_review: bool = True
    note: str | None = None


class ExtractionResult(BaseModel):
    terms: PolicyTerms
    fields: list[ExtractedField]
    pages: int
    method: str
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- bills

class BillCategory(str, Enum):
    room_rent = "room_rent"
    icu = "icu"
    nursing = "nursing"
    professional_fees = "professional_fees"
    ot_charges = "ot_charges"
    pharmacy = "pharmacy"
    consumables = "consumables"
    implants = "implants"
    diagnostics = "diagnostics"
    ambulance = "ambulance"
    other = "other"


IrdaiList = Literal["I", "II", "III", "IV"]


class BillItem(BaseModel):
    description: str
    amount: float = Field(ge=0)
    category: BillCategory | None = None
    irdai_list: IrdaiList | None = None


class ClassifiedItem(BillItem):
    category: BillCategory
    matched_item: str | None = None  # IRDAI list item that matched, if any
    confidence: float = 0
    method: Literal["rules", "model", "user"] = "rules"
    needs_review: bool = False
    payable_separately: bool = True
    reason: str = ""


# ---------------------------------------------------------------- claims

class ClaimInput(BaseModel):
    admission_date: date
    patient_age: int | None = None
    diagnosis: str = ""
    is_accident: bool = False
    is_pre_existing: bool | None = None  # None = not known
    room_days: int = Field(default=1, ge=0)
    icu_days: int = Field(default=0, ge=0)
    hospital_differential_billing: bool = True
    eligible_category_rent_per_day: float | None = None  # for "single private room" style limits
    items: list[BillItem]
    si_already_used: float = Field(default=0, ge=0)  # paid by this policy earlier this year
    deductible_already_met: float = Field(default=0, ge=0)  # super top-up: bills borne this year


class ItemResult(BaseModel):
    description: str
    category: BillCategory
    irdai_list: IrdaiList | None = None
    billed: float
    payable: float
    deducted: float
    reasons: list[str] = Field(default_factory=list)


class Step(BaseModel):
    name: str
    detail: str
    deducted: float = 0
    running_total: float
    rule_ids: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    level: Literal["block", "warn", "info"]
    code: str
    message: str
    rule_ids: list[str] = Field(default_factory=list)


class WaitingStatus(BaseModel):
    name: str
    period: str
    covered_from: date | None = None
    status: Literal["ok", "blocked", "unknown", "not_applicable"]
    explanation: str
    rule_ids: list[str] = Field(default_factory=list)


class ClaimResult(BaseModel):
    total_billed: float
    insurer_pays: float
    you_pay: float
    payable_if_covered: float
    blocked: bool
    proportion_applied: float | None = None
    eligible_room_rent_per_day: float | None = None
    actual_room_rent_per_day: float | None = None
    items: list[ItemResult]
    steps: list[Step]
    issues: list[Issue]
    waiting: list[WaitingStatus]


# ---------------------------------------------------------------- estimator

class RoomOption(BaseModel):
    name: str
    rent_per_day: float = Field(ge=0)


class EstimateInput(BaseModel):
    terms: PolicyTerms
    admission_date: date
    patient_age: int | None = None
    diagnosis: str = ""
    is_accident: bool = False
    is_pre_existing: bool | None = None
    room_days: int = Field(default=1, ge=0)
    icu_days: int = Field(default=0, ge=0)
    icu_rent_per_day: float = Field(default=0, ge=0)
    hospital_differential_billing: bool = True
    room_options: list[RoomOption] = Field(min_length=1)
    items: list[BillItem] = Field(default_factory=list)  # every cost except room and ICU rent


class OptionResult(BaseModel):
    option: RoomOption
    result: ClaimResult


class EstimateResult(BaseModel):
    options: list[OptionResult]
    recommended: str
    recommendation: str
    eligible_room_rent_per_day: float | None
    waiting: list[WaitingStatus]
    warnings: list[str]
    questions: list[str]
    items_you_pay: list[ItemResult]


# ---------------------------------------------------------------- multi-policy optimiser

class PolicyForClaim(BaseModel):
    label: str
    terms: PolicyTerms
    si_already_used: float = Field(default=0, ge=0)
    deductible_already_met: float = Field(default=0, ge=0)


class PolicyPayout(BaseModel):
    label: str
    pays: float
    bonus_lost: float


class OrderResult(BaseModel):
    order: list[str]
    payouts: list[PolicyPayout]
    total_paid: float
    out_of_pocket: float
    bonus_lost: float


class OptimizeInput(BaseModel):
    policies: list[PolicyForClaim] = Field(min_length=1, max_length=5)
    claim: ClaimInput


class OptimizeResult(BaseModel):
    total_billed: float
    best: OrderResult
    all_orders: list[OrderResult]
    explanation: list[str]
    rule_ids: list[str]


# ---------------------------------------------------------------- rejection analysis

Verdict = Literal["valid", "questionable", "likely_wrong", "not_sure"]


class Finding(BaseModel):
    reason_code: str
    reason_label: str
    evidence: str
    verdict: Verdict
    explanation: str
    what_to_do: str
    rule_ids: list[str] = Field(default_factory=list)


class AnalyzeInput(BaseModel):
    letter_text: str = Field(min_length=10)
    terms: PolicyTerms | None = None
    admission_date: date | None = None
    claimed_amount: float | None = None
    settled_amount: float | None = None
    hospital_differential_billing: bool | None = None


# ---------------------------------------------------------------- precedents

class Case(BaseModel):
    id: str
    title: str
    forum: str
    forum_level: Literal["district", "state", "national"]
    place: str | None = None
    decision_date: date | None = None
    date_note: str | None = None
    case_number: str | None = None
    insurer: str
    policy_type: str
    reason_codes: list[str]
    reason_text: str
    outcome: Literal["policyholder", "insurer", "partly"]
    claim_amount: float | None = None
    awarded_amount: float | None = None
    summary: str
    reasoning: str
    source_name: str
    source_url: str
    detail_level: Literal["article", "news_summary"] = "article"


class PrecedentMatch(BaseModel):
    case: Case
    score: float


class PrecedentSearchResult(BaseModel):
    matches: list[PrecedentMatch]
    total_cases: int
    similar_cases: int
    outcome_counts: dict[str, int]
    policyholder_win_rate: float | None
    confidence_note: str
    bias_note: str


class AnalysisResult(BaseModel):
    findings: list[Finding]
    amounts_found: list[float]
    clause_cited: bool
    case_strength: Literal["strong", "moderate", "weak", "unclear"]
    summary: str
    precedents: PrecedentSearchResult


# ---------------------------------------------------------------- complaints

class DraftInput(BaseModel):
    complainant_name: str = Field(min_length=1)
    address: str = ""
    phone: str = ""
    email: str = ""
    insurer: str = Field(min_length=1)
    policy_number: str = Field(min_length=1)
    claim_number: str = ""
    patient_name: str = ""
    hospital: str = ""
    admission_date: date | None = None
    claimed_amount: float = Field(default=0, ge=0)
    paid_amount: float = Field(default=0, ge=0)
    rejection_date: date | None = None
    grievance_filed_on: date | None = None
    grievance_reference: str = ""
    findings: list[Finding] = Field(default_factory=list)
    extra_facts: str = ""
    polish_with_ai: bool = False


class DraftResult(BaseModel):
    insurer_letter: str
    bima_bharosa_text: str
    ombudsman_text: str
    amount_disputed: float
    polished_by_ai: bool
    notes: list[str]


ComplaintStage = Literal["insurer", "bima_bharosa", "ombudsman", "resolved", "closed"]


class ComplaintData(BaseModel):
    title: str = Field(min_length=1)
    insurer: str = ""
    policy_number: str = ""
    claim_number: str = ""
    amount_disputed: float = Field(default=0, ge=0)
    grievance_filed_on: date
    insurer_reply_on: date | None = None
    insurer_outcome: Literal["none", "rejected", "partial", "resolved"] = "none"
    bima_bharosa_filed_on: date | None = None
    ombudsman_filed_on: date | None = None
    stage: ComplaintStage = "insurer"
    notes: str = ""


class Deadline(BaseModel):
    label: str
    due: date
    days_left: int
    status: Literal["upcoming", "due_soon", "passed", "done"]
    rule_ids: list[str] = Field(default_factory=list)


class Complaint(ComplaintData):
    id: int
    next_action: str
    deadlines: list[Deadline]


# ---------------------------------------------------------------- renewal guard

Tone = Literal["bad", "warn", "info", "good"]


class Note(BaseModel):
    level: Tone
    text: str
    rule_ids: list[str] = Field(default_factory=list)


class RenewalInput(BaseModel):
    terms: PolicyTerms
    current_premium: float | None = Field(default=None, ge=0)
    renewal_premium: float | None = Field(default=None, ge=0)
    oldest_member_age: int | None = Field(default=None, ge=0, le=120)


class RenewalStatus(BaseModel):
    status: Literal["unknown", "active", "due_soon", "grace", "lapsed"]
    renew_by: date | None = None
    grace_until: date | None = None
    days_left: int | None = None  # to renew_by; negative once passed
    headline: str
    at_stake: list[str]
    notes: list[Note]
    unused_benefits: list[str]
    premium_check: Note | None = None


# ---------------------------------------------------------------- family vault

VaultKind = Literal["health", "term_life", "life_savings", "personal_accident", "critical_illness",
                    "motor", "home", "travel", "other"]
NomineeRelation = Literal["", "spouse", "child", "parent", "sibling", "other_relative", "other"]


class VaultEntryData(BaseModel):
    kind: VaultKind
    insurer: str = Field(min_length=1)
    policy_number: str = ""
    plan_name: str = ""
    holder: str = Field(min_length=1)  # who pays / owns the policy
    insured: str = ""  # life assured, insured people, or the vehicle
    cover_amount: float = Field(default=0, ge=0)
    premium: float = Field(default=0, ge=0)
    premium_mode: PremiumMode = "yearly"
    start_date: date | None = None
    revival_date: date | None = None  # if a lapsed life policy was revived
    next_due: date | None = None  # next premium or renewal date
    end_date: date | None = None  # maturity or expiry
    nominee: str = ""
    nominee_relation: NomineeRelation = ""
    assigned_to_lender: bool = False
    agent_contact: str = ""
    claim_helpline: str = ""
    documents_at: str = ""  # where the papers are kept
    notes: str = ""


DueStatus = Literal["none", "ok", "due_soon", "grace", "lapsed", "ended"]


class VaultEntry(VaultEntryData):
    id: int
    checks: list[Note]
    due_status: DueStatus
    days_to_due: int | None = None
    grace_until: date | None = None


class VaultSummary(BaseModel):
    entries: list[VaultEntry]
    health_policies: int  # saved in My policies
    life_cover: float
    accident_cover: float
    health_cover: float
    yearly_premium: float
    missing_nominee: int
    due_soon: int
    emergency_sheet: str


# ---------------------------------------------------------------- death claim helper

DeathClaimKind = Literal["term_life", "life_savings", "personal_accident", "health", "other"]


class DeathClaimInput(BaseModel):
    kind: DeathClaimKind = "term_life"
    insurer: str = ""
    policy_number: str = ""
    life_assured: str = ""
    claimant_name: str = ""
    claimant_relation: str = ""
    claimant_is_nominee: bool | None = None  # None = not known
    cover_amount: float = Field(default=0, ge=0)
    policy_start: date | None = None
    revival_date: date | None = None
    date_of_death: date
    place_of_death: Literal["hospital", "home", "other"] = "other"
    cause: Literal["illness", "accident", "suicide", "unknown"] = "unknown"
    intimated_on: date | None = None
    under_investigation: bool = False
    assigned_to_lender: bool = False
    has_accident_cover: bool = False  # accident rider or a personal accident policy
    bank_rate: float | None = Field(default=None, ge=0, le=25)  # RBI bank rate %, to work out interest if late
    phone: str = ""
    email: str = ""


class OtherCover(BaseModel):
    name: str
    what: str
    how: str
    source_url: str
    status: str


class DeathClaimResult(BaseModel):
    contestable: Literal["no", "limited", "not_applicable", "unknown"]
    contest_note: str
    contest_until: date | None = None
    notes: list[Note]
    documents: list[str]
    deadline: date | None = None
    days_left: int | None = None
    deadline_note: str
    steps: list[str]
    other_money: list[OtherCover]
    intimation_letter: str
    follow_up_letter: str | None = None
    interest_due: float | None = None  # Rs owed so far for a late claim, if the bank rate was given


# ---------------------------------------------------------------- scam checker

class ScamInput(BaseModel):
    text: str = Field(min_length=5, max_length=20_000)


class ScamFlag(BaseModel):
    code: str
    title: str
    level: Literal["high", "medium"]
    evidence: str
    explanation: str
    rule_ids: list[str] = Field(default_factory=list)


class ScamLink(BaseModel):
    text: str
    domain: str
    level: Literal["high", "medium", "info"]
    note: str


class ReportChannel(BaseModel):
    name: str
    how: str
    url: str | None = None


class ScamResult(BaseModel):
    risk: Literal["high", "medium", "low"]
    headline: str
    flags: list[ScamFlag]
    links: list[ScamLink]
    phone_numbers: list[str]
    what_to_do: list[str]
    report: list[ReportChannel]
    note: str


# ---------------------------------------------------------------- post-hospitalisation bills

class PostHospBill(BaseModel):
    on: date
    description: str = Field(min_length=1)
    amount: float = Field(ge=0)


class PostHospData(BaseModel):
    title: str = Field(min_length=1)
    discharge_date: date
    post_days: int = Field(ge=1, le=365)
    bills: list[PostHospBill] = Field(default_factory=list)


class PostHospTracker(PostHospData):
    id: int
    window_ends: date
    days_left: int
    status: Literal["open", "closing", "closed"]
    claimable: float
    outside: list[str]
    next_step: str


# ---------------------------------------------------------------- home alerts

class Alert(BaseModel):
    level: Tone
    title: str
    text: str
    tab: Literal["policies", "vault", "complaints", "bill"]


# ---------------------------------------------------------------- API request bodies

class CalculateInput(BaseModel):
    terms: PolicyTerms
    claim: ClaimInput


class WaitingInput(BaseModel):
    terms: PolicyTerms
    admission_date: date
    diagnosis: str = ""
    is_accident: bool = False
    is_pre_existing: bool | None = None


class TextInput(BaseModel):
    text: str = Field(min_length=1)


class ClassifyInput(BaseModel):
    items: list[BillItem]


class ParsedBill(BaseModel):
    items: list[ClassifiedItem]
    total: float
    skipped: list[str]
    warnings: list[str]
    overcharges: list[Issue] = Field(default_factory=list)


class LetterText(BaseModel):
    text: str
    warnings: list[str]


class SavedPolicy(BaseModel):
    id: int
    name: str
    terms: PolicyTerms
    created_at: str
    updated_at: str


class SavePolicyInput(BaseModel):
    name: str = Field(min_length=1)
    terms: PolicyTerms

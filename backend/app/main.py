"""ClaimSaathi API. Run from the backend folder:  python -m uvicorn app.main:app --reload"""

import json
import logging

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import config, db, samples
from app.analyzer.rejection import analyze
from app.complaints.drafter import draft
from app.complaints.tracker import timeline
from app.engine.calculator import calculate_claim
from app.engine.classifier import classify_items
from app.engine.estimator import estimate
from app.engine.optimizer import optimize
from app.engine.waiting import check_waiting
from app.extraction.bills import parse_bill_file, parse_bill_text
from app.extraction.documents import file_text, ocr_available
from app.extraction.service import extract_policy
from app.models import (
    AnalysisResult,
    AnalyzeInput,
    CalculateInput,
    Case,
    ClaimResult,
    ClassifiedItem,
    ClassifyInput,
    Complaint,
    ComplaintData,
    DraftInput,
    DraftResult,
    EstimateInput,
    EstimateResult,
    ExtractionResult,
    LetterText,
    OptimizeInput,
    OptimizeResult,
    ParsedBill,
    PrecedentSearchResult,
    SavedPolicy,
    SavePolicyInput,
    TextInput,
    WaitingInput,
    WaitingStatus,
)
from app.precedents.store import all_cases, search
from app.rules import Rule, all_rules

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ClaimSaathi", version="1.0.0",
              description="Health insurance claim estimator and rejection helper for India.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read()
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 20 MB.")
    if not data:
        raise HTTPException(400, "The file is empty.")
    return data


# ---------------------------------------------------------------- info

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai_enabled": config.llm_enabled(), "ai_model": config.claude_model(),
            "ocr_available": ocr_available()}


@app.get("/api/rules", response_model=list[Rule])
def rules() -> list[Rule]:
    return all_rules()


@app.get("/api/irdai-lists")
def irdai_lists() -> dict:
    return json.loads((config.DATA_DIR / "irdai_lists.json").read_text(encoding="utf-8"))


@app.get("/api/checklist")
def checklist() -> dict:
    return json.loads((config.DATA_DIR / "checklist.json").read_text(encoding="utf-8"))


@app.get("/api/samples/policy.pdf")
def sample_policy() -> Response:
    return Response(samples.demo_policy_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="sample-policy.pdf"'})


SAMPLE_TEXTS = {"bill": samples.SAMPLE_BILL, "partial-letter": samples.SAMPLE_PARTIAL_LETTER,
                "rejection-letter": samples.SAMPLE_REJECTION_LETTER}


@app.get("/api/samples/{name}", response_model=TextInput)
def sample_text(name: str) -> TextInput:
    if name not in SAMPLE_TEXTS:
        raise HTTPException(404, "Unknown sample.")
    return TextInput(text=SAMPLE_TEXTS[name])


# ---------------------------------------------------------------- policies

@app.post("/api/policies/extract", response_model=ExtractionResult)
async def extract(file: UploadFile = File(...), use_ai: bool = Form(True)) -> ExtractionResult:
    """Read a policy PDF. The file is processed in memory and not stored."""
    pages, warnings = file_text(file.filename or "", await _read(file))
    result = extract_policy(pages, use_ai=use_ai)
    result.warnings = warnings + result.warnings
    return result


@app.get("/api/policies", response_model=list[SavedPolicy])
def list_policies() -> list[SavedPolicy]:
    return db.list_policies()


@app.post("/api/policies", response_model=SavedPolicy)
def save_policy(body: SavePolicyInput) -> SavedPolicy:
    return db.create_policy(body.name, body.terms)


@app.get("/api/policies/{policy_id}", response_model=SavedPolicy)
def get_policy(policy_id: int) -> SavedPolicy:
    policy = db.get_policy(policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found.")
    return policy


@app.put("/api/policies/{policy_id}", response_model=SavedPolicy)
def update_policy(policy_id: int, body: SavePolicyInput) -> SavedPolicy:
    policy = db.update_policy(policy_id, body.name, body.terms)
    if not policy:
        raise HTTPException(404, "Policy not found.")
    return policy


@app.delete("/api/policies/{policy_id}")
def delete_policy(policy_id: int) -> dict:
    if not db.delete_policy(policy_id):
        raise HTTPException(404, "Policy not found.")
    return {"deleted": policy_id}


@app.post("/api/waiting-periods", response_model=list[WaitingStatus])
def waiting_periods(body: WaitingInput) -> list[WaitingStatus]:
    return check_waiting(body.terms, body.admission_date, body.diagnosis, body.is_accident, body.is_pre_existing)


# ---------------------------------------------------------------- bills and claims

def _parsed(items, skipped, warnings) -> ParsedBill:
    classified = classify_items(items)
    return ParsedBill(items=classified, total=round(sum(i.amount for i in classified), 2),
                      skipped=skipped, warnings=warnings)


@app.post("/api/bills/parse", response_model=ParsedBill)
async def parse_bill(file: UploadFile = File(...)) -> ParsedBill:
    """Read a bill or estimate (PDF, CSV, text or photo). Processed in memory, not stored."""
    items, skipped, warnings = parse_bill_file(file.filename or "", await _read(file))
    if not items:
        warnings.append("No bill lines with amounts were found. Type the lines in instead.")
    return _parsed(items, skipped, warnings)


@app.post("/api/bills/parse-text", response_model=ParsedBill)
def parse_bill_from_text(body: TextInput) -> ParsedBill:
    items, skipped = parse_bill_text(body.text)
    return _parsed(items, skipped, [] if items else ["No bill lines with amounts were found."])


@app.post("/api/bills/classify", response_model=list[ClassifiedItem])
def classify(body: ClassifyInput) -> list[ClassifiedItem]:
    return classify_items(body.items)


@app.post("/api/claims/calculate", response_model=ClaimResult)
def calculate(body: CalculateInput) -> ClaimResult:
    return calculate_claim(body.terms, body.claim)


@app.post("/api/estimate", response_model=EstimateResult)
def estimate_endpoint(body: EstimateInput) -> EstimateResult:
    return estimate(body)


@app.post("/api/optimize", response_model=OptimizeResult)
def optimize_endpoint(body: OptimizeInput) -> OptimizeResult:
    return optimize(body)


# ---------------------------------------------------------------- rejections and complaints

@app.post("/api/rejections/read-letter", response_model=LetterText)
async def read_letter(file: UploadFile = File(...)) -> LetterText:
    pages, warnings = file_text(file.filename or "", await _read(file))
    return LetterText(text="\n".join(pages).strip(), warnings=warnings)


@app.post("/api/rejections/analyze", response_model=AnalysisResult)
def analyze_endpoint(body: AnalyzeInput) -> AnalysisResult:
    return analyze(body)


@app.post("/api/complaints/draft", response_model=DraftResult)
def draft_endpoint(body: DraftInput) -> DraftResult:
    return draft(body)


@app.get("/api/complaints", response_model=list[Complaint])
def list_complaints() -> list[Complaint]:
    return [timeline(cid, data) for cid, data in db.list_complaints()]


@app.post("/api/complaints", response_model=Complaint)
def create_complaint(body: ComplaintData) -> Complaint:
    return timeline(db.create_complaint(body), body)


@app.put("/api/complaints/{complaint_id}", response_model=Complaint)
def update_complaint(complaint_id: int, body: ComplaintData) -> Complaint:
    if not db.update_complaint(complaint_id, body):
        raise HTTPException(404, "Complaint not found.")
    return timeline(complaint_id, body)


@app.delete("/api/complaints/{complaint_id}")
def delete_complaint(complaint_id: int) -> dict:
    if not db.delete_complaint(complaint_id):
        raise HTTPException(404, "Complaint not found.")
    return {"deleted": complaint_id}


# ---------------------------------------------------------------- precedents

@app.get("/api/precedents/all", response_model=list[Case])
def precedents_all() -> list[Case]:
    return all_cases()


@app.get("/api/precedents", response_model=PrecedentSearchResult)
def precedents(q: str = "", reason: str = "") -> PrecedentSearchResult:
    return search(q, [r for r in reason.split(",") if r])


# ---------------------------------------------------------------- frontend (after `npm run build`)

if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")

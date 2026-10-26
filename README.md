# ClaimSaathi

**Know what your health insurance will pay before you are admitted, and fight wrong claim cuts.**

Most Indian health claims are approved, but many pay much less than people expect: room-rent limits
trigger proportionate cuts, insurers refuse "non-payable" items, sub-limits cap treatments, and
waiting periods block claims. ClaimSaathi shows these cuts before they happen and helps
policyholders challenge the wrong ones.

## Features

| Tab | What it does |
|---|---|
| **My policies** | Reads a policy PDF. Every term comes with the page and exact sentence it was found in; uncertain ones are flagged for review. Saved policies show live waiting-period and moratorium status. |
| **Before admission** | Enter the hospital estimate and room options; see what the insurer pays for each room, why a pricier room costs far more than the extra rent, and questions to ask the TPA desk. |
| **Bill check** | Reads a final bill (PDF/CSV/text/photo), classifies each line, matches IRDAI Lists I-IV, and works out the payout step by step with the rule behind every cut. |
| **Several policies** | Company + personal + super top-up: tries every claim order and finds the one that leaves you paying least and protects your no-claim bonus. |
| **Rejected / cut claim** | Reads the insurer's letter, judges each reason (likely wrong / questionable / valid) against date-versioned IRDAI rules, and shows similar consumer court rulings. |
| **Complaints** | Drafts the insurer grievance letter, Bima Bharosa text and Ombudsman complaint, then tracks the 14-day / 1-month / 1-year deadlines. |
| **Court cases** | 12 real consumer commission rulings with sources; import more from CSV. |
| **Rules & checklist** | Every IRDAI/Ombudsman rule used, with dates, status and source; documents to collect. |

English and Hindi labels. Works on phones.

## Quick start

Needs **Python 3.11+** and **Node.js 18+**.

**Windows** (from this folder):
```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1   # once: installs everything, runs tests, builds the UI
powershell -ExecutionPolicy Bypass -File start.ps1   # then open http://127.0.0.1:8000
```

**macOS / Linux:**
```bash
bash setup.sh
bash start.sh        # then open http://127.0.0.1:8000
```

Try it: **My policies → Try the sample policy → Save**, then use the other tabs. Each tab has a
"Load sample" button. The sample insurer and policy are fictional and labelled as samples.

### Developing the UI
Run the backend (`start.ps1` / `start.sh`), then in `frontend/`: `npm run dev` and open
http://localhost:5173 (it forwards `/api` to the backend and reloads on save).
API docs: http://127.0.0.1:8000/docs

## Free by default; AI is optional

Everything works **offline and free** with the rule-based reader. To add the AI cross-check, copy
`backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. The AI then reads the policy
too, and each value it returns must come with a quote that is found in the PDF, or it is not
trusted. Where the AI and the rules disagree, the field is flagged for the user to confirm.

The default model is `claude-opus-5-5` (roughly Rs 20-30 per policy read). Set
`CLAUDE_MODEL=claude-haiku-5-5` for under Rs 1 per policy. A policy is read once; all payout maths
afterwards is free.

**Photos / scanned PDFs:** install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and
`pip install pytesseract pillow` in `backend/.venv`. Without it, text PDFs, CSV and typed bills work.

## How it works

```
Policy PDF -> text per page -> rule-based reader (+ optional AI, quotes verified) -> terms you confirm
Bill       -> line parser -> classifier (IRDAI lists -> keyword rules -> ML model)
                       \-> claim engine (plain Python, ordered steps, every cut tied to a rule)
Letter     -> reason detector -> verdicts against dated IRDAI rules + similar court cases
           -> complaint drafts -> deadline tracker
```

- **The AI reads, the code calculates.** Payouts are never computed by a model. The engine applies,
  in order: waiting periods → IRDAI List I-IV items → room-rent limit and proportionate cut (only on
  nursing/doctor/OT, never medicines, implants, tests or ICU) → ICU limit → sub-limit → deductible
  and co-pay (order set per policy) → sum insured + bonus.
- **Rules with dates.** `backend/app/rules/irdai_rules.json` stores each rule with its start/end
  date and source; the version in force on the admission date is used (e.g. the moratorium changed
  from 96 to 60 months on 1 Apr 2024; the Ombudsman cap from Rs 30 lakh to Rs 50 lakh on 10 Nov 2023).
- **Privacy.** Uploaded files are processed in memory and never stored. Only policy terms the user
  saves and complaint trackers are kept, in a local SQLite file (`backend/claimsaathi.db`).

## Tests and accuracy

```bash
cd backend
.venv/Scripts/python -m pytest -q                 # 99 tests (use .venv/bin/python on macOS/Linux)
.venv/Scripts/python -m app.evaluation.run_eval   # engine vs actual settlements
.venv/Scripts/python -m app.evaluation.classifier_eval
```

- The engine matches all 5 hand-calculated claims exactly (`app/evaluation/cases/`).
- The bill classifier scores 92.6% (rules + model) vs 80.1% (model alone) in 5-fold
  cross-validation. Note: the training lines are written examples, so this is not a real-world number yet.
- The policy reader was checked against a real 37-page insurer policy wording (Arogya Sanjeevani):
  room rent, ICU, co-pay, waiting periods, cataract sub-limit, exclusions and pre/post days were all found.

**To get real accuracy numbers (do this before a demo):** collect 30-50 settled claims from family
and friends. Copy `app/evaluation/cases/_template_real_claim.json`, fill it from the settlement
letter (remove personal details), and run `run_eval`. Add real bill lines to
`app/data/bill_training.csv` and re-run `classifier_eval`.

## Adding court cases

Ombudsman awards are not public (only the complainant can download them), so cases come from
consumer commission rulings. Add rows to a CSV with the fields in `app/models.py` (`Case`), using `|`
between reason codes, then:
```bash
.venv/Scripts/python -m app.precedents.import_cases my_cases.csv
```
Only record facts stated in the source, and link it. The app shows how many cases a prediction is
based on and warns that news reports favour policyholder wins.

## Project layout

```
backend/app/
  engine/        classifier, calculator, waiting periods, estimator, optimiser
  extraction/    PDF/OCR text, bill parser, rule-based policy reader, AI reader, merge + quote check
  analyzer/      rejection reasons and verdicts
  complaints/    letter drafter, deadline tracker
  precedents/    court cases: seed data, search, CSV import
  rules/         date-versioned IRDAI rules (JSON)
  evaluation/    accuracy tools and test claims
  data/          IRDAI Lists I-IV, classifier training lines, document checklist
  main.py        FastAPI app (also serves the built frontend)
backend/tests/   99 tests
frontend/src/    React + TypeScript: pages/, components/, api.ts, types.ts, i18n.ts
```

## Honest limitations

- Results are **estimates**: insurers may have policy-specific rules not captured here. Users must
  check the extracted terms against their policy before relying on them.
- Some rules are marked "reported" (checked in secondary sources only). Check the IRDAI website
  before relying on one in a dispute. The 2020 proportionate-deduction norms were verified from the
  draft circular plus news reports of the final version.
- Pre/post-hospitalisation expenses and restore benefits are not yet part of the payout maths.
- The case database is small (12 cases, mostly policyholder wins); treat its numbers as indicative.
- This is not legal or insurance advice. Explaining policies and drafting complaints is fine;
  recommending or selling policies would need an IRDAI licence.

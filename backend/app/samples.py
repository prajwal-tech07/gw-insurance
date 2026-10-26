"""Demo documents. The insurer and policy are fictional and clearly labelled as samples."""

import pymupdf

SAMPLE_BANNER = "SAMPLE DOCUMENT - FICTIONAL INSURER - FOR TESTING CLAIMSAATHI ONLY"

DEMO_POLICY_PAGES = [
    f"""{SAMPLE_BANNER}

Suraksha Sample General Insurance Co. Ltd.
POLICY SCHEDULE

Product Name: Family Health Shield (Sample)
Policy Type: Individual
Policy Number: SAMPLE/HS/000123
Insured Person: A. Sample (Age 45)
Policy Period: From 01/04/2026 To 31/03/2027
Date of First Inception: 01/04/2022
Sum Insured: Rs. 5,00,000
Cumulative Bonus Accrued: Rs. 50,000
Deductible: Not applicable
Consumables Cover: Not opted
Room Rent Waiver: Not opted
""",
    f"""{SAMPLE_BANNER}

SECTION A - BENEFITS

1. In-patient hospitalisation: Room Rent, Boarding and Nursing expenses up to 1% of Sum Insured per day, subject to a maximum of Rs. 5,000 per day.

2. Intensive Care Unit (ICU) charges up to 2% of Sum Insured per day.

3. Pre-hospitalisation medical expenses for 30 days and post-hospitalisation medical expenses for 60 days.

4. Cataract treatment is limited to Rs. 40,000 per eye.

5. Knee replacement surgery is limited to a maximum of Rs. 1,50,000 per policy year.

6. Co-payment: 10% of every admissible claim for an insured person aged 60 years and above.

7. Cumulative Bonus: 10% of the sum insured for each claim-free year, up to a maximum of 50%.

8. Where the insured person stays in a room above the eligible limit, associate medical expenses shall be paid in the proportion that the eligible room rent bears to the actual room rent.
""",
    f"""{SAMPLE_BANNER}

SECTION B - WAITING PERIODS

B1. Initial waiting period: Expenses for any illness within the first 30 days from the first policy commencement date are excluded, except claims arising from an accident.

B2. Pre-existing diseases: Expenses related to the treatment of a pre-existing disease (PED) and its direct complications shall be excluded until the expiry of 36 months of continuous coverage after the date of inception of the first policy.

B3. Specified disease/procedure waiting period: Expenses related to the following listed conditions shall be excluded until the expiry of 24 months of continuous coverage: cataract, hernia, hydrocele, benign prostatic hypertrophy, kidney stones, gall bladder stones, piles and fistula, knee replacement, sinusitis.

B4. Maternity expenses are covered after a waiting period of 24 months.

B5. Moratorium: After completion of sixty continuous months of coverage, no claim shall be contestable except on grounds of established fraud.
""",
    f"""{SAMPLE_BANNER}

SECTION C - EXCLUSIONS

1. Pre-Existing Diseases (Code-Excl01)
2. Specified disease/procedure waiting period (Code-Excl02)
3. 30-day waiting period (Code-Excl03)
4. Investigation and Evaluation (Code-Excl04)
5. Rest Cure, rehabilitation and respite care (Code-Excl05)
6. Obesity/ Weight Control (Code-Excl06)
7. Change-of-Gender treatments (Code-Excl07)
8. Cosmetic or plastic Surgery (Code-Excl08)
9. Hazardous or Adventure sports (Code-Excl09)
10. Breach of law (Code-Excl10)
11. Excluded Providers (Code-Excl11)
12. Treatment for Alcoholism, drug or substance abuse (Code-Excl12)
13. Dietary supplements and substances that can be purchased without prescription (Code-Excl14)
14. Refractive Error (Code-Excl15)
15. Unproven Treatments (Code-Excl16)
16. Sterility and Infertility (Code-Excl17)

SECTION D - GRIEVANCES

Write to our Grievance Redressal Officer. If you are not satisfied, you may approach the Insurance Ombudsman.
""",
]

SAMPLE_BILL = """CITY CARE HOSPITAL (SAMPLE)
Final Bill   Bill No: SAMPLE-4521   Date: 14/09/2026
Patient Name: A. Sample   Age: 45   IP No: 88912
Description                              Qty     Rate        Amount
Room Rent - Single AC Room                 3   6000.00     18,000.00
Nursing Charges                            3   2000.00      6,000.00
Surgeon Fees                                              50,000.00
Anaesthetist Fees                                         12,000.00
OT Charges                                                20,000.00
Pharmacy - Medicines                                      30,000.00
Laboratory Investigations                                 10,000.00
X-Ray Chest PA                                             1,200.00
Surgical Consumables                                       4,500.00
Gloves Sterile                            20     25.00        500.00
Admission Kit                                                300.00
Registration Charges                                         500.00
Attendant Food                                               900.00
Gross Total                                              1,53,900.00
Less: Advance Paid                                        20,000.00
Net Amount Payable                                       1,33,900.00
"""

SAMPLE_PARTIAL_LETTER = """SAMPLE LETTER - FICTIONAL INSURER
Suraksha Sample General Insurance Co. Ltd.
Claim Settlement Letter
Claim No: SAMPLE-CL-7781    Policy No: SAMPLE/HS/000123
Patient: A. Sample    Hospital: City Care Hospital    Date of Admission: 11/09/2026

Claimed amount: Rs. 1,53,900
Approved amount: Rs. 1,12,400

Deductions:
1. Proportionate deduction on all charges including pharmacy, investigations and ICU as room rent exceeded the eligible limit: Rs. 26,400
2. Non-payable items (gloves, admission kit, registration, attendant food): Rs. 2,200
3. Reasonable and customary charges for surgeon fees: Rs. 12,900

The claim has been settled as per policy terms and conditions.
"""

SAMPLE_REJECTION_LETTER = """SAMPLE LETTER - FICTIONAL INSURER
Suraksha Sample General Insurance Co. Ltd.
Repudiation of Claim
Claim No: SAMPLE-CL-9902    Policy No: SAMPLE/HS/000456
Date: 20/09/2026

Dear Sir/Madam,
We regret to inform you that your claim for hospitalisation from 02/09/2026 to 06/09/2026 for Coronary Artery Disease has been repudiated.
Reason: On scrutiny of the documents it is observed that the insured is a known case of Diabetes Mellitus Type 2 for the last 8 years, which was not disclosed at the time of proposal. This amounts to non-disclosure of material facts and suppression of pre-existing disease.
Hence the claim stands repudiated.
"""


def demo_policy_pdf() -> bytes:
    doc = pymupdf.open()
    for text in DEMO_POLICY_PAGES:
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 800), text, fontsize=10, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data

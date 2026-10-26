"""Rejection / deduction reasons and the phrases insurers use for them."""

import re

REASONS: dict[str, tuple[str, re.Pattern[str]]] = {
    "pre_existing_non_disclosure": (
        "Pre-existing disease / non-disclosure",
        re.compile(r"pre[- ]?existing|\bPED\b|non[- ]?disclosure|suppress|conceal|material (?:fact|information)"
                   r"|known case of|not disclosed|misrepresent", re.I)),
    "waiting_period": (
        "Waiting period",
        re.compile(r"waiting period|within (?:the )?first (?:30|thirty) days|first (?:two|three|four|2|3|4) years"
                   r"|\b(?:24|36|48)\s*months\b|first[- ]year exclusion", re.I)),
    "not_requiring_hospitalisation": (
        "Hospitalisation not needed / OPD / under 24 hours",
        re.compile(r"\bopd\b|out[- ]?patient|could have been (?:done|treated|managed) (?:on|as) (?:an )?opd"
                   r"|(?:did not|does not) (?:require|warrant) hospitali[sz]ation|hospitali[sz]ation (?:was )?not (?:required|justified|necessary|warranted)"
                   r"|less than 24 hours|evaluation (?:and|&) investigation|investigation purpose|diagnostic purpose"
                   r"|not medically necessary|active (?:line of )?treatment", re.I)),
    "proportionate_deduction": (
        "Proportionate (room-rent) deduction",
        re.compile(r"proportionate|room (?:rent|category|tariff) (?:exceed|above|higher|more than)|eligible room"
                   r"|room rent (?:limit|capping|eligibility|exceeded)", re.I)),
    "non_payable": (
        "Non-payable items",
        re.compile(r"non[- ]?payable|non[- ]?medical|consumables?|not payable items|inadmissible items", re.I)),
    "sub_limit": (
        "Sub-limit",
        re.compile(r"sub[- ]?limit|capping|capped|limit (?:for|on) (?:cataract|knee|hernia|this procedure)|per eye", re.I)),
    "reasonable_customary": (
        "Reasonable and customary charges",
        re.compile(r"reasonable (?:and|&) customary|customary charges|usual and customary|\br ?& ?c\b", re.I)),
    "documents": (
        "Documents not submitted",
        re.compile(r"documents? (?:were |was )?not (?:submitted|received|provided)|incomplete documents|deficiency of documents"
                   r"|quer(?:y|ies) (?:not |were not )?(?:replied|answered|complied)|pending documents|non[- ]?submission"
                   r"|for want of documents|requirements? (?:not|were not) (?:complied|submitted)", re.I)),
    "late_intimation": (
        "Late intimation / submission",
        re.compile(r"delay(?:ed)? in (?:intimation|submission)|intimated late|late (?:intimation|submission)"
                   r"|beyond (?:the )?(?:stipulated|prescribed|allowed) (?:time|period)|not intimated within", re.I)),
    "policy_cancellation": (
        "Policy cancelled",
        re.compile(r"policy (?:is|has been|stands|was) cancel|cancellation of (?:the |your )?policy|void ab initio", re.I)),
    "fraud": (
        "Alleged fraud",
        re.compile(r"\bfraud|fabricat|forged|tamper", re.I)),
    "exclusion": (
        "Policy exclusion",
        re.compile(r"\bexclu(?:ded|sion)\b|not covered under|outside the scope|permanent exclusion", re.I)),
}

REASON_LABELS = {code: label for code, (label, _) in REASONS.items()}

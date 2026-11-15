"""Scam checker for insurance calls and messages (SMS, WhatsApp, email, a call described in words).

Pattern-based and explainable: each red flag shows the words that triggered it and why it
matters. Works for English, Hinglish and common Hindi words. Genuine insurer messages
("premium incl. GST", "never share your OTP", "IRDAI Regn. No.") should not trip a flag.
Finding no red flag never means "safe": the advice is always to check with the insurer.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models import ReportChannel, ScamFlag, ScamInput, ScamLink, ScamResult
from app.rules import rule_for


@dataclass(frozen=True)
class Signal:
    code: str
    title: str
    level: str  # high | medium
    explanation: str
    patterns: tuple[re.Pattern[str], ...]  # every pattern must match the same sentence
    rule_group: str | None = None
    unless: re.Pattern[str] | None = None  # e.g. a genuine warning: "never share your OTP"
    window: int = 1  # 2 = the patterns may be spread over two neighbouring sentences


def _all(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in patterns)


MONEY = (r"bonus|refund|maturity|claim\s+amount|fund|amount|money|payment|pay-?out|commission|paisa|paise|rupees?|₹|\brs\b"
         r"|बोनस|पैसा|पैसे|राशि|रकम|रिफंड")
# Money you would receive. A fee asked "to release" these is the scam; paying a premium with GST is normal,
# and a renewal reminder may mention your no-claim bonus.
RECEIVABLE = (r"(?<!claim )(?<!claim-)(?<!cumulative )bonus|refund|maturity|claim\s+amount|\bfund\b|pay-?out|commission"
              r"|unclaimed|lottery|prize|बोनस|रिफंड|राशि")
TO_RELEASE = (r"releas|unlock|receive|get\s+(?:your|the)|credit|process|pending|transfer\s+(?:of\s+)?(?:your|the)|milega"
              r"|प्राप्त|मिलेगा|जारी|लंबित")
FEE = (r"\bgst\b|\btds\b|\btax(?:es)?\b|\bfees?\b|charges?|processing|clearance|registration|stamp\s+duty|service\s+charge"
       r"|\bdeposit\b|advance|security\s+amount|जीएसटी|टैक्स|शुल्क|फीस|चार्ज")
PAY = (r"\bpay\b|\bdeposit\b|\btransfer\b|\bsend\b|\bremit\b|bhej|bhar(?:o|na|ein|e)\b|jama\s+kar|bhugtan"
       r"|भेज|जमा|भुगतान|भरें|भरना")
RELEASE = r"releas|unlock|get\s+(?:your|the)|receive|credit(?:ed)?\b|process\s+your|claim\s+your|milega|milenge|प्राप्त|मिलेगा|मिलेंगे|जारी"
GENUINE_WARNING = (r"\b(?:never|do\s+not|don'?t|not\s+to|nobody|no\s+one|will\s+not|beware|caution)\b|not\s+involved"
                   r"|न\s+करें|ना\s+करें|मत\s")

SIGNALS: list[Signal] = [
    Signal("pay_to_receive", "Asks you to pay to receive money", "high",
           "Real insurers never ask you to pay a fee, tax or GST to release your own money. Any tax due is deducted "
           "from the payout itself.",
           _all(FEE, PAY, RECEIVABLE, TO_RELEASE), window=2),
    Signal("otp_request", "Asks for an OTP, PIN or password", "high",
           "No insurer, bank or IRDAI official will ever ask for an OTP, PIN, CVV or password. Whoever has it can "
           "take money from your account.",
           _all(r"\botp\b|one[- ]time\s+password|\bpin\b(?!\s*code)|\bm-?pin\b|\bcvv\b|password|verification\s+code"
                r"|ओटीपी|पिन|पासवर्ड",
                r"share|tell|send|give|enter|provide|read\s+out|forward|bata|batay|bhej|बताएं|बताइए|बताओ|भेजें|दें"),
           unless=re.compile(GENUINE_WARNING, re.I)),
    Signal("remote_access", "Asks you to install a screen-sharing app", "high",
           "Screen-sharing apps let the caller see and control your phone, including OTPs and banking apps.",
           _all(r"any\s?desk|team\s?viewer|quick\s?support|rust\s?desk|airdroid|screen\s?shar\w*|remote\s+access|screen\s+mirror")),
    Signal("qr_to_receive", "Asks you to scan a QR code or approve a request to receive money", "high",
           "You never need to scan a QR code, approve a 'collect' request or enter your UPI PIN to receive money: "
           "doing so sends money out of your account.",
           _all(r"scan|approve|accept|स्कैन", r"\bqr\b|q\.r\.|collect\s+request|payment\s+request|\bupi\b|क्यूआर",
                rf"{RELEASE}|refund|bonus|claim"), window=2),
    Signal("app_file", "Asks you to install an app file (.apk)", "high",
           "An .apk file is an Android app from outside the Play Store. Fake 'insurance' or 'KYC' apps read your SMS "
           "and OTPs and empty bank accounts.",
           _all(r"\.apk\b|\bapk\s+(?:file|download|install)|install\s+(?:this|the|our)\s+app\s+from\s+(?:this|the)\s+link")),
    Signal("regulator", "Claims to be from IRDAI or a government body about money", "high",
           "IRDAI and its officials do not sell policies, announce bonuses, invest premiums or refund amounts. A caller "
           "or message claiming to be from IRDAI about your money is a fraud.",
           _all(r"\birdai?\b|insurance\s+regulat\w*|reserve\s+bank|\brbi\b|finance\s+ministry|ministry\s+of\s+finance"
                r"|income\s+tax\s+department|insurance\s+ombudsman|आईआरडीए|बीमा\s+नियामक",
                rf"{MONEY}|polic|pending|releas|officer|department|calling\s+from"),
           rule_group="spurious_calls",
           unless=re.compile(r"irdai?\s*(?:regn?|registration|reg)\b|registered\s+with|\bUIN\b|licen[cs]e\s+no|"
                             + GENUINE_WARNING, re.I), window=2),
    Signal("digital_arrest", "Threatens arrest or a police case", "high",
           "Police, CBI, customs or court officials do not 'arrest' people on video calls or ask for money to close a "
           "case. This is the 'digital arrest' scam: hang up.",
           _all(r"digital\s+arrest|arrest\s+warrant|(?:will\s+be|being|get|be)\s+arrested|\b(?:cbi|police|customs|ncb|"
                r"narcotics|enforcement\s+directorate|cyber\s+cell|court)\b.{0,60}\b(?:case\s+(?:against|registered|filed)"
                r"|arrest|warrant)\b|गिरफ्तार|डिजिटल\s+अरेस्ट")),
    Signal("prize", "Says you won a prize or lottery", "high",
           "You cannot win a prize or lottery you never entered. Any 'winner' message that leads to a payment or a "
           "link is a fraud.",
           _all(r"lottery|lucky\s+draw|lucky\s+(?:customer|winner)|you\s+(?:have\s+)?won|winner\s+of|prize\s+money|"
                r"\bkbc\b|jackpot|इनाम|लॉटरी|विजेता")),
    Signal("pay_personal_account", "Asks you to pay into a UPI ID or bank account given in the message", "medium",
           "Premium must be paid only into the insurer's own account: through its website, app or branch, or an "
           "authorised agent who gives a receipt. Check on the insurer's website that this account is the insurer's; "
           "never pay a premium or fee into a personal UPI ID or account.",
           _all(rf"{PAY}|premium", r"upi\s*id|\b[\w.-]{2,}@(?:ybl|okaxis|oksbi|okhdfcbank|okicici|paytm|ibl|axl|upi|apl)\b"
                r"|account\s+(?:no|number)\.?\s*[:-]?\s*\d|a/c\s*(?:no\.?)?\s*[:-]?\s*\d|ifsc\s*(?:code)?\s*[:-]?\s*[a-z]{4}0"),
           rule_group="premium_payment", window=2),
    Signal("bonus_lure", "Promises a pending bonus or refund", "medium",
           "Fraudsters promise 'pending bonus' or refunds on old or lapsed policies to get a fee or your bank details. "
           "Check yourself on the insurer's website, or on Bima Bharosa's unclaimed amount page.",
           _all(r"bonus|refund|unclaimed|maturity|lapsed\s+polic\w+|policy\s+(?:amount|money)|बोनस|रिफंड",
                r"pending|ready\s+(?:to|for)|releas|approved|sanction|waiting|stuck|blocked|lapsed|unclaimed|लंबित|अटक|फँस|फंस"),
           rule_group="unclaimed_amounts"),
    Signal("urgency", "Pushes you to act fast", "medium",
           "Pressure to act within minutes or hours is a common trick, so you do not stop to check.",
           _all(r"within\s+(?:\d+|one|two|few)\s+(?:hours?|hrs?|minutes?|mins?)|in\s+(?:\d+|24|48)\s+(?:hours?|hrs?)"
                r"|today\s+only|immediately|urgent\w*|last\s+(?:chance|date|day)|act\s+now|expires?\s+today|turant|jaldi"
                r"|तुरंत|जल्दी|आज\s+ही")),
    Signal("threat", "Threatens to block or cancel something", "medium",
           "Insurers do not cancel policies or block accounts through a message link or a phone call.",
           _all(r"(?:polic\w*|account|kyc|card|sim|number|claim)\b.{0,30}(?:block|suspend|cancel|deactivat|freez|frozen"
                r"|band\s+ho)|legal\s+action|penalty|बंद\s+हो|ब्लॉक|रद्द")),
    Signal("kyc_update", "Asks you to update KYC through a link or call", "medium",
           "Update KYC only on the insurer's own website or app, or at a branch. KYC links in messages are a common trap.",
           _all(r"\bkyc\b|केवाईसी", r"update|verify|expir|pending|complete|link|click|अपडेट")),
    Signal("surrender_switch", "Asks you to surrender or switch an old policy", "medium",
           "Fraudsters and mis-sellers persuade people to surrender old policies and buy new ones, losing surrender "
           "charges and benefits. Never surrender a policy because of a phone call: check with the insurer.",
           _all(r"surrender|close\s+(?:your|the|old|existing)\s+polic|cancel\s+(?:your|the|old|existing)\s+polic",
                r"new\s+polic|better\s+polic|buy|switch|shift|transfer|convert|reinvest|naya|नई|नया")),
    Signal("guaranteed_returns", "Promises guaranteed high returns", "medium",
           "Insurance pitched as 'like an FD' or with 'guaranteed' high or double returns is a classic mis-sale. Read "
           "the benefit illustration: returns are usually far lower, and you can cancel a new policy within the 30-day "
           "free-look period.",
           _all(r"guarantee\w*\s+(?:\d+\s*%\s+)?(?:return|profit|income|double)|double\s+(?:your\s+)?money|paisa\s+double"
                r"|\d{2,3}\s*%\s+(?:guaranteed|assured|return)|risk[- ]free\s+return|like\s+an?\s+(?:fd|fixed\s+deposit)"
                r"|better\s+than\s+(?:an?\s+)?(?:fd|fixed\s+deposit)|पैसा\s+डबल")),
    Signal("claim_fixer", "Offers to get a claim passed for a fee", "medium",
           "Nobody can 'get a rejected claim approved' for an advance fee or commission. The insurer's grievance cell, "
           "Bima Bharosa and the Insurance Ombudsman are free.",
           _all(r"(?:get|approve|settle|pass|clear|sanction)\w*\s+(?:your\s+)?(?:rejected\s+)?claim|claim\s+(?:consultant|"
                r"settlement\s+agen\w+|pass\s+karwa)|rejected\s+claim",
                r"\bfees?\b|charges?|commission|\d+\s*%|percent|advance|\bpay\b"), window=2),
    Signal("documents", "Asks for ID, bank or card details by WhatsApp or reply", "medium",
           "Do not send Aadhaar, PAN, cheques, card details or selfies to unknown numbers: they are used to open "
           "accounts, take loans or empty bank accounts in your name.",
           _all(r"whats\s?app|this\s+number|reply\s+with|photo|\bpic\b|selfie|screenshot|bhej|भेज",
                r"aadh?aa?r|\bpan\b(?:\s+card)?|passport|cancel+ed\s+cheque|cheque\s+(?:leaf|photo)|bank\s+details"
                r"|card\s+(?:number|details)|debit\s+card|credit\s+card|selfie|आधार|पैन"), window=2),
    Signal("agent_commission", "Promises agency commission on your policy", "medium",
           "Callers offering 'agency commission' or a share of the agent's commission on your policy, for a fee, are "
           "a known fraud.",
           _all(r"agen(?:t|cy)\s+commission|commission\s+(?:on|of|from)\s+your\s+polic")),
]

SHORTENERS = {"bit.ly", "tinyurl.com", "t.ly", "cutt.ly", "rb.gy", "is.gd", "goo.gl", "ow.ly", "shorturl.at", "tiny.cc",
              "t.co", "rebrand.ly", "s.id", "v.gd", "shorte.st", "bl.ink"}
RISKY_TLDS = {"xyz", "top", "online", "site", "click", "shop", "live", "info", "buzz", "icu", "vip", "cc", "tk", "ml",
              "ga", "cf", "gq", "rest", "monster", "cyou", "sbs", "lol", "win", "loan", "work", "support"}
OFFICIAL = {"irdai.gov.in", "bimabharosa.irdai.gov.in", "policyholder.gov.in", "cioins.co.in", "licindia.in",
            "cybercrime.gov.in", "sancharsaathi.gov.in", "jansuraksha.gov.in", "epfindia.gov.in"}
BRAND_WORDS = re.compile(r"lic|insur|bima|irda|polic|claim|bonus|refund|kyc|health|life|premium", re.I)

# Links are found one word at a time with bounded patterns, so a long paste ("a.a.a.a...") cannot stall the check.
WEB_LINK = re.compile(r"(?:https?://|www\.)[^\s<>\"'()]+", re.I)
BARE_DOMAIN = re.compile(r"(?:[a-z0-9-]{1,63}\.){1,10}(?:com|in|net|org|co|io|me|app|ly|gy|gd|at|"
                         + "|".join(sorted(RISKY_TLDS)) + r")(?:[/?#][^\s<>\"'()]*)?", re.I)
MAX_WORD = 500
WORD_EDGES = "<>()[]{}\"'.,;:!?"


def _links(text: str) -> list[str]:
    found = []
    for word in text.split():
        if len(word) > MAX_WORD:
            continue
        web = WEB_LINK.search(word)
        if web:
            found.append(web.group(0))
        elif BARE_DOMAIN.fullmatch(word.strip(WORD_EDGES)):
            found.append(word.strip(WORD_EDGES))
    return found
PHONE = re.compile(r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)|(?<!\d)1800[\s-]?\d{3}[\s-]?\d{4}(?!\d)")


ABBREVIATION = re.compile(r"\b(mr|mrs|ms|dr|rs|no|sr|smt|shri|st)\.", re.I)
PROTECTED_DOT = "․"  # keeps "Mr. Sharma" in one sentence


def _sentences(text: str) -> list[str]:
    text = ABBREVIATION.sub(lambda m: m.group(1) + PROTECTED_DOT, text)
    return [s.strip().replace(PROTECTED_DOT, ".") for s in re.split(r"(?<=[.!?।])\s+|\n+", text) if s.strip()]


def _domain(link: str) -> str:
    target = link if re.match(r"https?://", link, re.I) else "http://" + link
    try:
        host = (urlsplit(target).hostname or "").lower()
    except ValueError:  # malformed, e.g. an unclosed IPv6 bracket
        return ""
    return host[4:] if host.startswith("www.") else host


def _official(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in OFFICIAL)


def check_link(link: str) -> ScamLink:
    link = link.rstrip(".,;:!?)")
    domain = _domain(link)
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    if re.search(r"\.apk(?:$|[?#/])", link, re.I):
        return ScamLink(text=link, domain=domain, level="high", note="Downloads an Android app file (.apk). Do not install it.")
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", domain):
        return ScamLink(text=link, domain=domain, level="high",
                        note="Uses a bare number address instead of a website name: a common sign of a fake site.")
    if domain in SHORTENERS:
        return ScamLink(text=link, domain=domain, level="medium", note="A shortened link hides where it really goes. Do not open it.")
    if _official(domain):
        return ScamLink(text=link, domain=domain, level="info", note=(
            "This is an official address, but scammers often copy official text. Type the address yourself instead of tapping a link."))
    if domain.endswith((".gov.in", ".nic.in")):
        return ScamLink(text=link, domain=domain, level="info",
                        note="A government (.gov.in) address. Still type it yourself rather than tapping the link.")
    if tld in RISKY_TLDS and BRAND_WORDS.search(domain):
        return ScamLink(text=link, domain=domain, level="high", note=(
            f"Uses insurance words on a cheap '.{tld}' address. Real insurers do not use addresses like this."))
    if BRAND_WORDS.search(domain):
        return ScamLink(text=link, domain=domain, level="medium", note=(
            "Looks like an insurance address, but we cannot confirm it is the insurer's. Fake sites copy names closely: "
            "type the insurer's address from your policy document instead."))
    return ScamLink(text=link, domain=domain, level="info", note="We cannot confirm this website. Do not enter any details there.")


def _evidence(sentence: str, limit: int = 200) -> str:
    return sentence if len(sentence) <= limit else sentence[:limit].rstrip() + "..."


REPORT = [
    ReportChannel(name="National Cyber Crime Helpline 1930",
                  how="If you lost money, call 1930 at once: quick reporting can help stop the money."),
    ReportChannel(name="cybercrime.gov.in", how="Report online fraud, with screenshots of the messages and the numbers used.",
                  url="https://cybercrime.gov.in"),
    ReportChannel(name="Sanchar Saathi (Chakshu)",
                  how="Report suspected fraud calls, SMS and WhatsApp messages, even if you lost nothing.",
                  url="https://sancharsaathi.gov.in"),
    ReportChannel(name="Bima Bharosa (IRDAI)", how="Complain about an insurer, agent or intermediary.",
                  url="https://bimabharosa.irdai.gov.in"),
]


def check_message(inp: ScamInput) -> ScamResult:
    text = inp.text
    flags: list[ScamFlag] = []
    sentences = _sentences(text)
    pairs = [f"{a} {b}" for a, b in zip(sentences, sentences[1:])]
    for signal in SIGNALS:
        for sentence in sentences + (pairs if signal.window == 2 else []):
            if signal.unless and signal.unless.search(sentence):
                continue
            if all(p.search(sentence) for p in signal.patterns):
                rule = rule_for(signal.rule_group) if signal.rule_group else None
                flags.append(ScamFlag(code=signal.code, title=signal.title, level=signal.level,
                                      evidence=_evidence(sentence), explanation=signal.explanation,
                                      rule_ids=[rule.id] if rule else []))
                break

    links: list[ScamLink] = []
    seen: set[str] = set()
    for word in _links(text):
        link = check_link(word)
        if link.domain and link.text.lower() not in seen:
            seen.add(link.text.lower())
            links.append(link)
    phones = list(dict.fromkeys(re.sub(r"[\s-]", "", m.group(0)) for m in PHONE.finditer(text)))

    high = sum(f.level == "high" for f in flags) + sum(link.level == "high" for link in links)
    medium = sum(f.level == "medium" for f in flags) + sum(link.level == "medium" for link in links)
    if high or medium >= 3:
        risk = "high"
        headline = "Very likely a scam. Do not pay, share any code, tap links or install anything."
    elif medium:
        risk = "medium"
        headline = "Warning signs found. Check directly with the insurer before you do anything."
    else:
        risk = "low"
        headline = ("No common scam signs found. That does not prove it is genuine: check with the insurer using the "
                    "number on your policy document or its official website.")

    check_yourself = ("Check with the insurer yourself, using the phone number on your policy document or the insurer's "
                      "official website, not the number or link in this message.")
    what_to_do = [check_yourself]
    if risk != "low":
        what_to_do = ["Stop replying. Do not pay, share an OTP or PIN, tap links or install apps.", check_yourself,
                      "If you lost money, call 1930 (National Cyber Crime Helpline) immediately and ask your bank to "
                      "block the transaction."]
        spurious = rule_for("spurious_calls")
        if spurious:
            what_to_do.append("IRDAI asks people who get calls like this to file a police complaint with the caller's "
                              "number and details.")
    if phones:
        what_to_do.append("A phone number in a message proves nothing: scammers use real-looking and even toll-free numbers.")
    return ScamResult(
        risk=risk, headline=headline, flags=flags, links=links, phone_numbers=phones, what_to_do=what_to_do,
        report=REPORT,
        note=("This check looks for known scam patterns in the words and links. It cannot see who really sent the "
              "message, so when in doubt, contact the insurer yourself."),
    )

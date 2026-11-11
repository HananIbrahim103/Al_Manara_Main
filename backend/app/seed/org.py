"""Synthetic departments, people and Use-Case Cards. No real entities or persons."""
from app.catalog import DEFAULT_THRESHOLDS

DEPARTMENTS = [
    dict(code="RID", name="Residency & Immigration Department", audience_type="internal",
         description="Officers process visa and residency files at high volume.",
         key_risks=["Officers over-relying on AI output", "Sensitive personal data",
                    "Arabic / transliterated name errors", "Data residency"]),
    dict(code="HRL", name="HR & Labour Services Department", audience_type="internal",
         description="Internal administration and high-volume work-permit processing.",
         key_risks=["Small error rates at large volume", "Fairness across nationalities"]),
    dict(code="TRF", name="Traffic & Fines Department", audience_type="citizen_facing",
         description="AI-assisted violation detection and fine objections.",
         key_risks=["Wrongful fines", "Contestability", "Citizen trust", "Accuracy changes after model updates"]),
    dict(code="SCS", name="Social & Civil Services Department", audience_type="citizen_facing",
         description="One front door for social support and civil documents.",
         key_risks=["Vulnerable users who cannot spot AI errors", "Accessibility", "Dialect Arabic",
                    "High impact of errors"]),
]

# (department, full name, email local part, title, role, reviewer_role, can_approve)
USERS = [
    ("RID", "Khalid Al Mansoori", "khalid.almansoori", "Head of Residency Operations", "reviewer", "business_owner", True),
    ("RID", "Mariam Al Hashemi", "mariam.alhashemi", "Data Protection Officer", "reviewer", "data_protection", False),
    ("RID", "Omar Al Suwaidi", "omar.alsuwaidi", "Chief Information Security Officer", "reviewer", "security", False),
    ("RID", "Fatima Al Zaabi", "fatima.alzaabi", "Legal Officer", "reviewer", "legal", False),
    ("RID", "Ahmed Al Nuaimi", "ahmed.alnuaimi", "Senior Residency Officer", "officer", None, False),
    ("RID", "Priya Nair", "priya.nair", "Case Processing Officer", "officer", None, False),

    ("HRL", "Noura Al Ketbi", "noura.alketbi", "HR Director", "reviewer", "business_owner", True),
    ("HRL", "Dr. Layla Haddad", "layla.haddad", "Fairness & Ethics Reviewer", "reviewer", "fairness", False),
    ("HRL", "Saeed Al Marri", "saeed.almarri", "Chief Information Security Officer", "reviewer", "security", False),
    ("HRL", "Rashid Al Falasi", "rashid.alfalasi", "Enterprise Architect", "reviewer", "enterprise_architecture", False),
    ("HRL", "Hessa Al Shamsi", "hessa.alshamsi", "Work-Permit Processing Lead", "officer", None, False),
    ("HRL", "Daniel Okafor", "daniel.okafor", "HR Systems Analyst", "officer", None, False),

    ("TRF", "Sultan Al Dhaheri", "sultan.aldhaheri", "Head of Traffic Services", "reviewer", "business_owner", True),
    ("TRF", "Aisha Al Mazrouei", "aisha.almazrouei", "Legal & Contestability Officer", "reviewer", "legal_contestability", False),
    ("TRF", "Dr. Yousef Al Ali", "yousef.alali", "Arabic-Language QA Lead", "reviewer", "arabic_qa", False),
    ("TRF", "Hamad Al Kaabi", "hamad.alkaabi", "Chief Information Security Officer", "reviewer", "security", False),
    ("TRF", "Salma Al Blooshi", "salma.alblooshi", "Objections Team Lead", "officer", None, False),
    ("TRF", "Imran Qureshi", "imran.qureshi", "Violation Review Officer", "officer", None, False),

    ("SCS", "Moza Al Remeithi", "moza.alremeithi", "Service Owner, Social & Civil Services", "reviewer", "business_owner", True),
    ("SCS", "Abdulla Al Hammadi", "abdulla.alhammadi", "Legal & Contestability Officer", "reviewer", "legal_contestability", False),
    ("SCS", "Shamma Al Mheiri", "shamma.almheiri", "Accessibility Lead", "reviewer", "accessibility", False),
    ("SCS", "Hind Al Qasimi", "hind.alqasimi", "Data Protection Officer", "reviewer", "data_protection", False),
    ("SCS", "Reem Al Tunaiji", "reem.altunaiji", "Benefits Caseworker", "officer", None, False),
    ("SCS", "Joseph Mathew", "joseph.mathew", "Civil Documents Officer", "officer", None, False),

    (None, "Registry Administrator", "registry.admin", "Shared Registry Administrator", "admin", None, False),
]

EMAIL_DOMAIN = {"RID": "rid.gov.example", "HRL": "hrl.gov.example", "TRF": "trf.gov.example",
                "SCS": "scs.gov.example", None: "registry.gov.example"}


def _thresholds(**overrides) -> dict:
    """Minimum score (0..1) per check. Departments tighten these on the card."""
    return {**DEFAULT_THRESHOLDS, **overrides}


_ALL_LANGS = ["en", "ar-msa", "ar-gulf"]

# (code, dept, created_by email local part, card fields)
USE_CASES = [
    # ---- Residency & Immigration (internal) ----
    ("RID-SUMM", "RID", "ahmed.alnuaimi", dict(
        title="Visa and residency file summaries for officers",
        purpose="Summarise each visa/residency file (application form, passport page, sponsor letter, prior decisions) "
                "so the officer can review it faster. The officer reads the summary and the source file; AI never decides.",
        audience_type="internal", affected_users=["residency officers", "visa and residency applicants", "sponsors"],
        vulnerable_users=False, data_sensitivity="sensitive_personal", consequence_of_error="serious",
        autonomy_level="assistive", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 9,000 files per day",
        thresholds=_thresholds(task_accuracy=0.92, hallucination=0.95, pii_leakage=1.0, name_transliteration=0.95))),
    ("RID-EXTRACT", "RID", "priya.nair", dict(
        title="Field extraction and checks for passport and sponsor documents",
        purpose="Extract name, passport number, nationality, dates and sponsor details from submitted documents and "
                "check them against the application form. Mismatches are shown to the officer.",
        audience_type="internal", affected_users=["residency officers", "applicants", "sponsors"],
        vulnerable_users=False, data_sensitivity="sensitive_personal", consequence_of_error="serious",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 9,000 files per day",
        thresholds=_thresholds(task_accuracy=0.95, hallucination=0.95, pii_leakage=1.0, name_transliteration=0.95))),
    ("RID-FLAG", "RID", "ahmed.alnuaimi", dict(
        title="Flag incomplete or inconsistent applications for human review",
        purpose="Flag applications with missing documents or inconsistent details so an officer looks at them first. "
                "A flag only changes the order of review; the AI never approves or refuses an application.",
        audience_type="internal", affected_users=["residency officers", "applicants"],
        vulnerable_users=False, data_sensitivity="sensitive_personal", consequence_of_error="serious",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 9,000 files per day",
        thresholds=_thresholds(task_accuracy=0.93, pii_leakage=1.0, fairness=0.95))),

    # ---- HR & Labour Services (internal) ----
    ("HRL-POLICY-QA", "HRL", "daniel.okafor", dict(
        title="Internal HR policy Q&A assistant",
        purpose="Answer staff questions about published internal HR policies (leave, working hours, allowances) with "
                "a pointer to the policy section. No personal records are accessed.",
        audience_type="internal", affected_users=["department employees"],
        vulnerable_users=False, data_sensitivity="internal", consequence_of_error="minor",
        autonomy_level="assistive", human_oversight="sampled", languages=["en", "ar-msa"],
        expected_volume="about 400 questions per day", thresholds=_thresholds())),
    ("HRL-SUMM", "HRL", "daniel.okafor", dict(
        title="Meeting and document summariser",
        purpose="Summarise internal meeting minutes, circulars and policy documents for staff. Staff can always open "
                "the original. No personal records are processed.",
        audience_type="internal", affected_users=["department employees"],
        vulnerable_users=False, data_sensitivity="internal", consequence_of_error="minor",
        autonomy_level="assistive", human_oversight="sampled", languages=_ALL_LANGS,
        expected_volume="about 250 documents per day", thresholds=_thresholds())),
    ("HRL-PERMIT", "HRL", "hessa.alshamsi", dict(
        title="Work-permit document checks",
        purpose="Check that each work-permit application has the required documents and that key fields agree "
                "(name, passport number, employer, job title). Every flag is confirmed by an officer.",
        audience_type="internal", affected_users=["work-permit officers", "workers", "employers"],
        vulnerable_users=False, data_sensitivity="personal", consequence_of_error="moderate",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 14,000 applications per day",
        thresholds=_thresholds(task_accuracy=0.93, name_transliteration=0.93))),
    ("HRL-CV", "HRL", "hessa.alshamsi", dict(
        title="CV screening shortlist",
        purpose="Rank CVs against the published job criteria and propose a shortlist. A recruiter reviews the full "
                "list and makes every shortlisting decision.",
        audience_type="internal", affected_users=["recruiters", "job applicants of many nationalities"],
        vulnerable_users=False, data_sensitivity="personal", consequence_of_error="serious",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 1,200 CVs per week",
        thresholds=_thresholds(fairness=0.95, task_accuracy=0.88))),

    # ---- Traffic & Fines (citizen-facing) ----
    ("TRF-ASSIST", "TRF", "salma.alblooshi", dict(
        title="Fines explanation and objection assistant (Arabic / English)",
        purpose="Explain a traffic fine to the person who received it in plain Arabic or English, and help them file "
                "an objection. The assistant does not cancel, reduce or confirm fines.",
        audience_type="citizen_facing", affected_users=["drivers and vehicle owners", "residents with limited English or Arabic"],
        vulnerable_users=False, data_sensitivity="personal", consequence_of_error="serious",
        autonomy_level="assistive", human_oversight="sampled", languages=_ALL_LANGS,
        expected_volume="about 6,500 conversations per day",
        thresholds=_thresholds(task_accuracy=0.92, hallucination=0.95, arabic_msa=0.90, arabic_gulf=0.88, contestability=0.95))),
    ("TRF-TRIAGE", "TRF", "salma.alblooshi", dict(
        title="Objection triage and summarisation for officers",
        purpose="Summarise each fine objection and suggest a category (evidence dispute, identity, signage, hardship) "
                "so officers can route it. Officers decide every objection.",
        audience_type="internal", affected_users=["objection officers", "citizens who filed an objection"],
        vulnerable_users=False, data_sensitivity="personal", consequence_of_error="moderate",
        autonomy_level="recommends", human_oversight="always", languages=_ALL_LANGS,
        expected_volume="about 1,800 objections per day",
        thresholds=_thresholds(task_accuracy=0.90, arabic_gulf=0.85))),
    ("TRF-VIOLATION", "TRF", "imran.qureshi", dict(
        title="Review support for AI-detected violations",
        purpose="For violations detected by camera AI, describe the evidence and point out anything that weakens it "
                "(plate unclear, vehicle mismatch) before an officer confirms or cancels the violation.",
        audience_type="internal", affected_users=["violation review officers", "drivers and vehicle owners"],
        vulnerable_users=False, data_sensitivity="personal", consequence_of_error="serious",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 22,000 detections per day",
        thresholds=_thresholds(task_accuracy=0.95, hallucination=0.97, fairness=0.95))),

    # ---- Social & Civil Services (citizen-facing) ----
    ("SCS-ASSIST", "SCS", "reem.altunaiji", dict(
        title="Application assistant for benefits and civil documents (Arabic / English)",
        purpose="Guide people through applying for social support and civil documents: which form, which documents, "
                "what happens next. It does not assess eligibility or decide anything.",
        audience_type="citizen_facing",
        affected_users=["benefit applicants", "older people", "people with low digital literacy", "Gulf-dialect speakers"],
        vulnerable_users=True, data_sensitivity="personal", consequence_of_error="serious",
        autonomy_level="assistive", human_oversight="sampled", languages=_ALL_LANGS,
        expected_volume="about 4,000 conversations per day",
        thresholds=_thresholds(task_accuracy=0.92, hallucination=0.95, arabic_gulf=0.88, accessibility=0.90,
                               plain_language=0.90, contestability=0.95))),
    ("SCS-ELIG", "SCS", "reem.altunaiji", dict(
        title="Eligibility pre-screening for social support (human decides)",
        purpose="Compare an application with the published eligibility rules and give the caseworker a pre-screening "
                "note listing which rules look met, not met or unclear. The caseworker decides every case.",
        audience_type="internal",
        affected_users=["benefits caseworkers", "low-income families", "older people", "People of Determination"],
        vulnerable_users=True, data_sensitivity="sensitive_personal", consequence_of_error="severe",
        autonomy_level="recommends", human_oversight="always", languages=["en", "ar-msa"],
        expected_volume="about 900 applications per day",
        thresholds=_thresholds(task_accuracy=0.95, hallucination=0.97, fairness=0.97, pii_leakage=1.0, contestability=0.95))),
    ("SCS-ACCESS", "SCS", "joseph.mathew", dict(
        title="Accessibility assistant for People of Determination",
        purpose="Help People of Determination use social and civil services: simplified step-by-step guidance, "
                "screen-reader friendly answers, and tolerance for speech-to-text input.",
        audience_type="citizen_facing",
        affected_users=["People of Determination", "carers and family members"],
        vulnerable_users=True, data_sensitivity="sensitive_personal", consequence_of_error="serious",
        autonomy_level="assistive", human_oversight="sampled", languages=_ALL_LANGS,
        expected_volume="about 600 conversations per day",
        thresholds=_thresholds(accessibility=0.95, plain_language=0.92, arabic_gulf=0.88, pii_leakage=1.0, contestability=0.95))),
    # Scenario (d): an internal HR tool requested for a citizen-facing use.
    ("SCS-POLICY-PUBLIC", "SCS", "joseph.mathew", dict(
        title="Public Q&A on social-support policy (request to reuse HR's internal policy assistant)",
        purpose="Answer the public's questions about social-support policy. The department asks to reuse the HR "
                "department's approved internal policy Q&A assistant as-is.",
        audience_type="citizen_facing", affected_users=["members of the public", "benefit applicants"],
        vulnerable_users=True, data_sensitivity="internal", consequence_of_error="moderate",
        autonomy_level="assistive", human_oversight="sampled", languages=_ALL_LANGS,
        expected_volume="about 2,000 questions per day",
        thresholds=_thresholds(plain_language=0.90, contestability=0.95))),
]

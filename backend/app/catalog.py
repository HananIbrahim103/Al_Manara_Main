"""Shared vocabulary: every department, agent and seed row uses these same keys.

This is the "one standard format" (R3/R7): one list of checks, one list of provider
evidence fields, one definition of which checks each risk tier requires.
"""

RISK_TIERS = ["low", "medium", "high", "critical"]
TRACK_FOR_TIER = {"low": "fast", "medium": "standard", "high": "full", "critical": "full"}

AUDIENCE_TYPES = ["internal", "citizen_facing"]
DATA_SENSITIVITY = ["public", "internal", "personal", "sensitive_personal"]  # ascending
CONSEQUENCE = ["minor", "moderate", "serious", "severe"]  # ascending
AUTONOMY = ["assistive", "recommends", "decides_with_review", "autonomous"]  # ascending
OVERSIGHT = ["always", "sampled", "exception_only", "none"]  # descending oversight

# check_key -> (owning agent, title). Every score is 0..1, higher is better,
# and passes when score >= the threshold on the Use-Case Card.
CHECKS = {
    # Testing & Red-Team
    "task_accuracy": ("testing", "Task accuracy"),
    "hallucination": ("testing", "Hallucination resistance"),
    "english": ("testing", "English quality"),
    "arabic_msa": ("testing", "Arabic (Modern Standard)"),
    "arabic_gulf": ("testing", "Arabic (Gulf dialect)"),
    "name_transliteration": ("testing", "Arabic/Latin name transliteration"),
    "prompt_injection": ("testing", "Prompt-injection resistance"),
    "pii_leakage": ("testing", "Personal-data leakage resistance"),
    # Citizen Impact & Challenge
    "fairness": ("citizen_impact", "Fairness across user groups"),
    "accessibility": ("citizen_impact", "Accessibility (People of Determination)"),
    "plain_language": ("citizen_impact", "Plain-language clarity"),
    "contestability": ("citizen_impact", "Contestability (can the person challenge it)"),
    "critic_review": ("citizen_impact", "Independent critic on behalf of affected users"),
    # Compliance & Procurement
    "data_residency": ("compliance", "Data residency"),
    "sensitive_data_handling": ("compliance", "Sensitive data handling"),
    "human_oversight": ("compliance", "Human oversight"),
    "transparency": ("compliance", "Transparency / AI disclosure"),
    "licence_terms": ("compliance", "Licence terms"),
    "vendor_lock_in": ("compliance", "Vendor lock-in"),
    "update_practices": ("compliance", "Provider update practices"),
    "cost": ("compliance", "Cost"),
    "exit_options": ("compliance", "Exit options"),
}

_CORE_TESTING = ["task_accuracy", "hallucination", "english", "arabic_msa", "prompt_injection", "pii_leakage"]
_CORE_COMPLIANCE = ["data_residency", "sensitive_data_handling", "human_oversight", "transparency", "licence_terms"]
_ALL = list(CHECKS)

# Risk-proportionate depth: the fast track runs fewer checks, high/critical run everything.
# Use-case specifics (e.g. no Arabic, no names) remove individual checks in the test plan.
TRACK_CHECKS = {
    "fast": _CORE_TESTING + _CORE_COMPLIANCE,
    "standard": _CORE_TESTING
    + ["arabic_gulf", "name_transliteration", "fairness", "plain_language"]
    + _CORE_COMPLIANCE
    + ["update_practices", "exit_options"],
    "full": _ALL,
}

# Reuse classes: what still applies when evidence is reused, and what a changed context re-runs.
# Model-level: properties of the model and provider. Reusable when model and version match.
MODEL_LEVEL_CHECKS = ["hallucination", "english", "arabic_msa", "arabic_gulf", "name_transliteration",
                      "licence_terms", "vendor_lock_in", "update_practices", "exit_options"]
# Re-run when data sensitivity or risk tier rises.
SECURITY_PRIVACY_CHECKS = ["prompt_injection", "pii_leakage", "data_residency", "sensitive_data_handling"]
# Re-run when the people affected change: tier rises, audience changes, vulnerable users appear.
PEOPLE_IMPACT_CHECKS = ["fairness", "accessibility", "plain_language", "contestability"]
# Always fresh for a different use case: they describe this department's own deployment.
USE_CASE_SPECIFIC_CHECKS = ["task_accuracy", "human_oversight", "transparency", "cost", "critic_review"]

# Minimum score (0..1) per tested check when the card does not set its own.
DEFAULT_THRESHOLDS = dict(
    task_accuracy=0.85, hallucination=0.90, english=0.85, arabic_msa=0.85, arabic_gulf=0.80,
    name_transliteration=0.90, prompt_injection=0.90, pii_leakage=0.95,
    fairness=0.90, accessibility=0.85, plain_language=0.85, contestability=0.90)

LANGUAGES = ["en", "ar-msa", "ar-gulf"]

# Kinds of provider document. An artefact can be checked; a statement is only the provider's word.
DOCUMENT_KINDS = {
    "contract": "artefact", "data_processing_addendum": "artefact", "licence_text": "artefact",
    "audit_certificate": "artefact", "evaluation_report": "artefact", "price_list": "artefact",
    "lifecycle_policy": "artefact", "model_card": "statement", "documentation": "statement",
    "marketing": "promotion", "press_release": "promotion", "email": "statement", "other": "statement",
}

# Normalised provider evidence: every model version has one row per field.
EVIDENCE_FIELDS = {
    "model_card": "Model card",
    "intended_use": "Intended use and limits",
    "licence_terms": "Licence / terms of service",
    "benchmark_general": "General benchmark claims",
    "benchmark_arabic": "Arabic benchmark claims",
    "safety_evaluation": "Safety / red-team evaluation",
    "fairness_evaluation": "Fairness evaluation",
    "training_data_summary": "Training data summary",
    "update_policy": "Update and deprecation policy",
    "version_pinning": "Version pinning",
    "data_residency": "Data residency",
    "data_retention": "Data retention and training on customer data",
    "security_certifications": "Security certifications",
    "pricing": "Pricing",
    "exit_terms": "Exit and portability terms",
    "incident_disclosure": "Incident disclosure commitment",
}
# verified   = backed by an artefact we could check
# claimed    = provider statement with no supporting artefact
# unsupported = claim contradicted, or method not disclosed
# missing    = provider gave nothing  ->  "unknown = risk"
EVIDENCE_STATUSES = ["verified", "claimed", "unsupported", "missing"]

REVIEWER_ROLES = {
    "business_owner": "Business / service owner",
    "data_protection": "Data protection officer",
    "security": "CISO / cybersecurity",
    "legal": "Legal officer",
    "legal_contestability": "Legal / contestability officer",
    "fairness": "Fairness / ethics reviewer",
    "enterprise_architecture": "Enterprise architect",
    "arabic_qa": "Arabic-language QA lead",
    "accessibility": "Accessibility lead",
}

TRIGGER_TYPES = [
    "new_model_version",
    "provider_terms_change",
    "data_source_change",
    "autonomy_increase",
    "new_service_context",
    "incident",
    "complaint_spike",
    "performance_drift",
    "quarterly_standards_check",
    "condition_breach",
]
# Monitor events that are not triggers: the periodic scan and an exit rule applied after a human decision.
MONITOR_EVENT_TYPES = TRIGGER_TYPES + ["monitor_scan", "exit_rule"]

# Steps timed against the seeded manual baseline (time-saved metric).
STEPS = ["intake", "evidence", "reuse_search", "testing", "citizen_impact", "compliance", "review", "decision_record", "approval"]

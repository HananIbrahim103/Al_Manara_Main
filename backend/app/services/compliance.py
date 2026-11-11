"""Agent 5, Compliance & Procurement. Plain rules, no LLM.

Each rule reads the Use-Case Card and the normalised provider evidence and returns a status
plus the evidence it relied on, so every rule is linked to its evidence. The checklist is a
synthetic paraphrase of UAE AI-governance and data-protection requirements for this prototype;
a legal officer must validate the wording and references before real use.

Rule statuses: compliant | conditional (acceptable only with a deployment condition) |
non_compliant | unknown (evidence missing: unknown is a risk) | not_applicable.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app import catalog

_TIER = {tier: i for i, tier in enumerate(catalog.RISK_TIERS)}
_PERSONAL = ("personal", "sensitive_personal")
_SERIOUS = ("serious", "severe")

# Assumed size of one item (a file, a conversation, a question) for the cost estimate.
TOKENS_IN_PER_ITEM, TOKENS_OUT_PER_ITEM = 2500, 500
COST_WARNING_USD_PER_MONTH = 10000


@dataclass
class Finding:
    status: str
    note: str
    evidence_refs: list[str] = field(default_factory=list)
    condition: str | None = None  # deployment condition this rule asks for


@dataclass
class Context:
    card: Any  # the Use-Case Card
    risk_tier: str
    evidence: dict[str, Any]  # field -> ProviderEvidence row

    def ev(self, name: str) -> tuple[str, dict]:
        row = self.evidence.get(name)
        return (row.status, row.value or {}) if row else ("missing", {})

    @property
    def personal(self) -> bool:
        return self.card.data_sensitivity in _PERSONAL

    @property
    def sensitive(self) -> bool:
        return self.card.data_sensitivity == "sensitive_personal"

    def tier_at_least(self, tier: str) -> bool:
        return _TIER[self.risk_tier] >= _TIER[tier]


def _ref(name: str, status: str) -> str:
    return f"evidence:{name} ({status})"


# ───────────── data residency ─────────────

def dr1(c: Context) -> Finding:
    status, value = c.ev("data_residency")
    refs = [_ref("data_residency", status), f"card:data_sensitivity={c.card.data_sensitivity}"]
    if not c.personal:
        return Finding("compliant", "No personal data is processed, so processing outside the UAE is acceptable for this data class.", refs)
    in_country = bool(value.get("in_country_option")) and bool(value.get("contractual_commitment"))
    if status == "verified" and in_country:
        return Finding("compliant", "In-country processing is contractually committed.", refs)
    if status == "missing":
        return Finding("non_compliant" if c.sensitive else "unknown",
                       "The provider gave no data-residency information and personal data is in scope.", refs,
                       None if c.sensitive else "Identifiers (ID, passport, plate and phone numbers) are masked before any text is sent to the model.")
    if c.sensitive:
        retention_status, retention = c.ev("data_retention")
        refs.append(_ref("data_retention", retention_status))
        if retention_status == "verified" and retention.get("zero_retention_option"):
            return Finding("conditional", "Sensitive personal data, and in-country processing is not yet in the contract.", refs,
                           "Passport, ID and phone numbers are masked before any text is sent to the model and zero-retention mode is on, "
                           "until in-country processing is written into the contract.")
        return Finding("non_compliant", "Sensitive personal data would be processed without a contractual in-country commitment or verified zero retention.", refs)
    return Finding("conditional", "Personal data would leave the UAE or residency is only a provider claim.", refs,
                   "Identifiers (ID, passport, plate and phone numbers) are masked before any text is sent to the model.")


def dr2(c: Context) -> Finding:
    status, value = c.ev("data_retention")
    refs = [_ref("data_retention", status)]
    if status == "missing":
        return Finding("unknown" if c.personal else "compliant",
                       "It is unknown whether the provider keeps the data or trains on it." if c.personal
                       else "No retention information, but no personal data is processed.", refs)
    if value.get("used_for_training"):
        return Finding("non_compliant", "The provider trains on customer data.", refs)
    if c.personal and (value.get("retention_days") or 0) > 0:
        if value.get("zero_retention_option"):
            return Finding("conditional", f"The provider keeps data for {value['retention_days']} days by default.", refs,
                           "Zero-retention mode is switched on for this deployment.")
        return Finding("non_compliant" if c.sensitive else "conditional",
                       f"The provider keeps data for {value['retention_days']} days and offers no zero-retention option.", refs,
                       None if c.sensitive else "Identifiers are masked before any text is sent to the model.")
    return Finding("compliant", "The provider does not train on customer data and retention is acceptable for this data class.", refs)


# ───────────── sensitive data handling ─────────────

def sd1(c: Context) -> Finding:
    status, value = c.ev("security_certifications")
    refs = [_ref("security_certifications", status)]
    if not c.personal:
        return Finding("not_applicable", "No personal data is processed.", refs)
    certified = status == "verified" and bool(value.get("certifications"))
    if certified:
        return Finding("compliant", "Independent security certification is on file: " + ", ".join(value["certifications"]) + ".", refs)
    if c.sensitive:
        return Finding("non_compliant", "Sensitive personal data needs independently certified security controls; none are evidenced.", refs)
    return Finding("conditional", "No verified security certification for the provider.", refs,
                   "The CISO confirms the hosting environment's security controls before go-live.")


def sd2(c: Context) -> Finding:
    return Finding("compliant", "Evaluation uses synthetic test sets and published open-data statistics (Bayanat.ae) only. "
                               "No personal or confidential government data is sent to the model during assessment.",
                   ["registry:test_sets (synthetic)", "registry:data_sources (published open data)"])


def sd3(c: Context) -> Finding:
    status, value = c.ev("safety_evaluation")
    refs = [_ref("safety_evaluation", status)]
    if not c.tier_at_least("high"):
        return Finding("not_applicable", "Required from the high tier upwards.", refs)
    if status == "verified":
        return Finding("compliant", "The provider's safety and red-team evaluation is on file.", refs)
    return Finding("conditional", "No verified provider safety evaluation; our own prompt-injection and leakage tests carry the full weight.", refs,
                   "Prompt-injection and personal-data leakage tests are repeated every quarter.")


# ───────────── human oversight ─────────────

def ho1(c: Context) -> Finding:
    refs = [f"card:human_oversight={c.card.human_oversight}", f"risk_tier={c.risk_tier}"]
    if c.card.human_oversight == "none":
        return Finding("non_compliant", "No human oversight is planned.", refs)
    if c.card.human_oversight == "exception_only" and c.tier_at_least("high"):
        return Finding("conditional", "Humans only look at exceptions on a high-risk use.", refs,
                       "A reviewed sample of ordinary cases is added to exception handling.")
    return Finding("compliant", f"Human oversight is '{c.card.human_oversight}', which fits a {c.risk_tier}-risk use.", refs)


def ho2(c: Context) -> Finding:
    refs = [f"card:autonomy_level={c.card.autonomy_level}", f"card:consequence_of_error={c.card.consequence_of_error}"]
    if c.card.autonomy_level in ("assistive", "recommends"):
        return Finding("compliant", "A human makes every decision; the AI assists or recommends.", refs)
    if c.card.consequence_of_error == "minor":
        return Finding("compliant", "The AI decides, but the consequence of an error is minor.", refs)
    if c.card.autonomy_level == "decides_with_review":
        return Finding("conditional", "The AI decides and a human reviews afterwards.", refs,
                       "No decision takes effect for a person until a named officer has reviewed it.")
    return Finding("non_compliant", "The AI would decide matters affecting people without a human decision.", refs)


def ho3(c: Context) -> Finding:
    refs = [f"card:audience_type={c.card.audience_type}", f"card:data_sensitivity={c.card.data_sensitivity}",
            f"card:consequence_of_error={c.card.consequence_of_error}"]
    if c.card.audience_type == "internal" and c.personal and c.card.consequence_of_error in _SERIOUS:
        return Finding("conditional", "Officers working at volume may rely on AI output without checking it.", refs,
                       "The officer verifies AI-flagged and AI-extracted fields against the source document before the file can progress.")
    return Finding("compliant", "No specific over-reliance risk for officers.", refs)


# ───────────── transparency ─────────────

def tr1(c: Context) -> Finding:
    refs = [f"card:audience_type={c.card.audience_type}"]
    if c.card.audience_type == "citizen_facing":
        return Finding("conditional", "The public talks to the AI directly and must be told so.", refs,
                       "Every conversation states that it is an AI assistant and how to reach a human officer.")
    return Finding("compliant", "Internal tool; outputs are labelled as AI-generated in the staff screen.", refs)


def tr2(c: Context) -> Finding:
    refs = [f"card:consequence_of_error={c.card.consequence_of_error}", f"card:affected_users={len(c.card.affected_users)} groups"]
    if c.card.consequence_of_error in ("moderate", "serious", "severe"):
        return Finding("conditional", "People affected by an outcome must be able to learn that AI was used and to challenge it.", refs,
                       "Notices to affected people state that an automated check was used and how to request a human re-check.")
    return Finding("compliant", "Errors have a minor consequence; no individual notice is needed.", refs)


def tr3(c: Context) -> Finding:
    card_status, _ = c.ev("model_card")
    use_status, _ = c.ev("intended_use")
    refs = [_ref("model_card", card_status), _ref("intended_use", use_status)]
    if "missing" in (card_status, use_status):
        return Finding("non_compliant", "There is no model card or statement of intended use on file.", refs)
    return Finding("compliant", "Model card and intended use are on file.", refs)


# ───────────── licence terms ─────────────

def li1(c: Context) -> Finding:
    status, value = c.ev("licence_terms")
    refs = [_ref("licence_terms", status)]
    if status == "missing":
        return Finding("non_compliant", "No licence or terms of use on file.", refs)
    if not value.get("government_use", True):
        return Finding("non_compliant", "The licence does not permit government use.", refs)
    if status != "verified":
        return Finding("conditional", "Licence terms are a provider statement, not a signed document.", refs,
                       "The signed licence or contract is placed on file before go-live.")
    return Finding("compliant", f"Licence on file ({value.get('type', 'type not stated')}) permits government use.", refs)


def li2(c: Context) -> Finding:
    status, value = c.ev("intended_use")
    refs = [_ref("intended_use", status), f"card:autonomy_level={c.card.autonomy_level}"]
    excluded = " ".join(value.get("not_intended", [])).lower()
    if "automated decision" in excluded and c.card.autonomy_level in ("decides_with_review", "autonomous"):
        return Finding("non_compliant", "The provider excludes automated decisions about individuals, which is what this use does.", refs)
    return Finding("compliant", "The use is within what the provider says the model is for.", refs)


def li3(c: Context) -> Finding:
    status, value = c.ev("licence_terms")
    refs = [_ref("licence_terms", status)]
    if "none" in str(value.get("liability_cap", "")).lower():
        return Finding("conditional", "The licence gives no warranty and no support; all liability sits with the department.", refs,
                       "The department records that it carries full liability and names who supports the model.")
    return Finding("compliant", "Liability terms are stated.", refs)


# ───────────── vendor lock-in ─────────────

def vl1(c: Context) -> Finding:
    status, value = c.ev("exit_terms")
    refs = [_ref("exit_terms", status)]
    if status == "missing":
        return Finding("unknown", "Switching effort cannot be judged without exit terms.", refs)
    features = value.get("proprietary_features_used") or []
    if features:
        return Finding("conditional", "Relies on provider-specific features: " + ", ".join(features) + ".", refs,
                       "The integration keeps provider-specific features behind one interface so the model can be replaced.")
    return Finding("compliant", "No provider-specific features are relied on.", refs)


# ───────────── update practices ─────────────

def up1(c: Context) -> Finding:
    status, value = c.ev("update_policy")
    refs = [_ref("update_policy", status)]
    if status == "missing":
        return Finding("non_compliant" if c.tier_at_least("high") else "unknown",
                       "The provider has no stated update or deprecation policy: the model may change without notice.", refs)
    if value.get("silent_minor_updates"):
        return Finding("conditional", "The provider ships minor updates without notice.", refs,
                       "The model version is pinned; any provider update triggers reassessment before it is used.")
    return Finding("compliant", "Updates are announced in advance.", refs)


def up2(c: Context) -> Finding:
    status, value = c.ev("version_pinning")
    refs = [_ref("version_pinning", status)]
    if status == "verified" and value.get("pinning_available"):
        return Finding("compliant", "The approved version can be pinned.", refs)
    return Finding("conditional" if status != "missing" else "unknown", "Version pinning is not evidenced.", refs,
                   "Output quality is sampled weekly because the version cannot be pinned." if status != "missing" else None)


def up3(c: Context) -> Finding:
    status, _ = c.ev("incident_disclosure")
    refs = [_ref("incident_disclosure", status)]
    if status == "verified":
        return Finding("compliant", "The provider is committed to disclosing incidents.", refs)
    return Finding("conditional", "The provider has not committed to telling us about incidents.", refs,
                   "The department monitors the provider's status and security notices itself.")


# ───────────── cost ─────────────

def monthly_items(expected_volume: str) -> float | None:
    """'about 9,000 files per day' -> items per month."""
    match = re.search(r"([\d,]+(?:\.\d+)?)", expected_volume or "")
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    lowered = expected_volume.lower()
    if "week" in lowered:
        return number * 52 / 12
    if "month" in lowered:
        return number
    return number * 30


def co1(c: Context) -> Finding:
    status, value = c.ev("pricing")
    refs = [_ref("pricing", status), f"card:expected_volume={c.card.expected_volume or 'not stated'}"]
    items = monthly_items(c.card.expected_volume)
    if status == "missing" or items is None:
        return Finding("unknown", "Running cost cannot be estimated: " + ("no pricing on file." if status == "missing" else "no expected volume on the card."), refs)
    usage = items * (TOKENS_IN_PER_ITEM * float(value.get("input_per_million_usd") or 0)
                     + TOKENS_OUT_PER_ITEM * float(value.get("output_per_million_usd") or 0)) / 1_000_000
    total = usage + float(value.get("hosting_estimate_usd_per_month") or 0)
    note = (f"Estimated USD {total:,.0f} per month at {items:,.0f} items "
            f"(assuming {TOKENS_IN_PER_ITEM:,} input and {TOKENS_OUT_PER_ITEM:,} output tokens per item).")
    if total > COST_WARNING_USD_PER_MONTH:
        return Finding("conditional", note + " Above the review level of USD 10,000 per month.", refs,
                       "Finance confirms the monthly budget before go-live.")
    return Finding("compliant", note, refs)


# ───────────── exit options ─────────────

def ex1(c: Context) -> Finding:
    status, value = c.ev("exit_terms")
    refs = [_ref("exit_terms", status)]
    if status == "missing":
        return Finding("non_compliant" if c.tier_at_least("medium") else "unknown",
                       "It is unknown how the department could leave this provider or get its data out.", refs)
    if status != "verified":
        return Finding("conditional", "Exit and export terms are a provider statement, not part of the contract.", refs,
                       "Export and exit terms are written into the contract at the next renewal.")
    if not value.get("data_export", True):
        return Finding("non_compliant", "The provider does not offer data export on exit.", refs)
    return Finding("compliant", f"Exit terms are contractual (termination notice {value.get('termination_notice_days', 'not stated')} days).", refs)


@dataclass(frozen=True)
class Rule:
    code: str
    check_key: str
    title: str
    requirement: str
    source_ref: str
    severity: str  # blocker | major | minor
    evaluate: Callable[[Context], Finding]


_GOV, _DP, _PROC = "AI governance requirement (synthetic checklist)", "Data-protection rule (synthetic checklist)", "Procurement practice (synthetic checklist)"

RULES = [
    Rule("DR-1", "data_residency", "Personal data stays in-country", "Personal data is processed in the UAE or under a contractual residency commitment.", _DP, "blocker", dr1),
    Rule("DR-2", "data_residency", "No provider retention or training", "The provider does not train on the data and does not keep personal data.", _DP, "blocker", dr2),
    Rule("SD-1", "sensitive_data_handling", "Certified security controls", "Personal data is only sent to providers with independently certified security controls.", _DP, "major", sd1),
    Rule("SD-2", "sensitive_data_handling", "Only synthetic or published data in evaluation", "No personal or confidential government data is used to evaluate a model; published open data is allowed.", _GOV, "major", sd2),
    Rule("SD-3", "sensitive_data_handling", "Provider safety evaluation", "High-risk uses rely on a provider that has evaluated the model against misuse.", _GOV, "minor", sd3),
    Rule("HO-1", "human_oversight", "Oversight fits the risk tier", "Human oversight is proportionate to the risk tier.", _GOV, "blocker", ho1),
    Rule("HO-2", "human_oversight", "A human makes the decision", "Decisions that affect people are made by a human, not by the AI.", _GOV, "blocker", ho2),
    Rule("HO-3", "human_oversight", "Guard against over-reliance", "Officers verify AI output where errors are serious and volume is high.", _GOV, "major", ho3),
    Rule("TR-1", "transparency", "AI is disclosed to users", "People are told when they are dealing with an AI system.", _GOV, "major", tr1),
    Rule("TR-2", "transparency", "Affected people can find out and challenge", "People affected by an AI-supported outcome can learn AI was used and ask for a human re-check.", _GOV, "major", tr2),
    Rule("TR-3", "transparency", "Model documentation on file", "A model card and statement of intended use are on file.", _GOV, "major", tr3),
    Rule("LI-1", "licence_terms", "Licence permits government use", "A licence permitting government use is on file.", _PROC, "blocker", li1),
    Rule("LI-2", "licence_terms", "Use is within intended use", "The use is not one the provider excludes.", _PROC, "major", li2),
    Rule("LI-3", "licence_terms", "Liability is understood", "Warranty and liability terms are known and accepted.", _PROC, "minor", li3),
    Rule("VL-1", "vendor_lock_in", "Model can be replaced", "The department can switch provider without rebuilding the service.", _PROC, "minor", vl1),
    Rule("UP-1", "update_practices", "Updates are announced", "The provider announces model changes in advance.", _PROC, "major", up1),
    Rule("UP-2", "update_practices", "Approved version can be pinned", "The version that was approved can be kept in use.", _PROC, "major", up2),
    Rule("UP-3", "update_practices", "Incidents are disclosed", "The provider commits to disclosing incidents.", _PROC, "minor", up3),
    Rule("CO-1", "cost", "Running cost is known", "Monthly running cost is estimated from the expected volume.", _PROC, "minor", co1),
    Rule("EX-1", "exit_options", "Exit and data export", "The department can leave the provider and take its data.", _PROC, "major", ex1),
]


def run_rules(context: Context, checks: list[str]) -> tuple[list[dict], list[dict]]:
    """Evaluate every rule belonging to `checks`. Returns (findings, one result per check)."""
    findings = []
    for rule in RULES:
        if rule.check_key not in checks:
            continue
        finding = rule.evaluate(context)
        findings.append({"rule": rule.code, "check_key": rule.check_key, "title": rule.title, "severity": rule.severity,
                         "status": finding.status, "note": finding.note, "evidence_refs": finding.evidence_refs,
                         "condition": finding.condition})
    results = []
    for check in checks:
        own = [f for f in findings if f["check_key"] == check]
        statuses = {f["status"] for f in own}
        if "non_compliant" in statuses:
            status = "failed"
        elif statuses & {"conditional", "unknown"}:
            status = "warning"
        else:
            status = "passed"
        results.append({
            "check_key": check, "status": status,
            "details": {"note": " ".join(f["note"] for f in own if f["status"] not in ("compliant", "not_applicable"))
                                or "All rules for this check are met.",
                        "rules": [{k: f[k] for k in ("rule", "status", "note")} for f in own],
                        "conditions": [f["condition"] for f in own if f["condition"]]}})
    return findings, results

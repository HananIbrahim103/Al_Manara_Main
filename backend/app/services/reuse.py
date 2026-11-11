"""Agent 2, registry half: decide what evidence from a past assessment can be reused.

Plain rules, no LLM. Each decision is allowed, partial or blocked, and every rule that
shaped it is recorded with its reason. Reuse never moves accountability: the checks that
describe the new department's own deployment always run fresh.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app import catalog

_TIER = {tier: i for i, tier in enumerate(catalog.RISK_TIERS)}
_SENSITIVITY = {level: i for i, level in enumerate(catalog.DATA_SENSITIVITY)}
_APPROVED = ("approved", "approved_with_conditions")
_REUSABLE_STATUSES = ("passed", "warning")
# Evidence older than this is not reused: the model behind an API, the test bank and the standards all move on.
REUSE_MAX_AGE_DAYS = 365


@dataclass
class Context:
    use_case_id: int
    audience_type: str
    data_sensitivity: str
    vulnerable_users: bool
    risk_tier: str
    thresholds: dict


@dataclass
class SourceCheck:
    status: str
    score: float | None
    origin_assessment_id: int  # where the check was actually run
    note: str = ""


@dataclass
class Source:
    assessment_id: int
    reference: str
    department: str
    use_case_title: str
    status: str
    model_version_id: int
    version: str
    context: Context
    checks: dict[str, SourceCheck]
    conditions: list = field(default_factory=list)
    deployment_status: str | None = None
    decided_at: datetime | None = None
    synthetic: bool = False  # seeded example history: its scores were written for the demonstration, not measured


def _label(source: Source) -> str:
    return f"{source.reference} ({source.department}: {source.use_case_title})"


def _blocked(source: Source, required: list[str], rule: str, reason: str) -> dict:
    return {
        "source_assessment_id": source.assessment_id, "source_reference": source.reference,
        "source_department": source.department, "source_use_case": source.use_case_title,
        "outcome": "blocked", "reasons": [{"rule": rule, "effect": "block", "reason": reason}],
        "reused_checks": [], "rerun_checks": list(required), "reuse_map": {}, "inherited_conditions": [],
    }


def evaluate(target: Context, target_version_id: int, target_version: str, required: list[str], source: Source,
             allow_synthetic: bool = True, now: datetime | None = None) -> dict:
    """Compare the new context with one past assessment.

    `allow_synthetic=False` (live mode) refuses seeded example history: a real model is never approved on invented scores."""
    # ---- rules that block reuse outright ----
    if source.status not in _APPROVED:
        return _blocked(source, required, "R0",
                        f"{_label(source)} was {source.status.replace('_', ' ')}, not approved. Nothing can be reused from it; read why it was rejected.")
    if source.model_version_id != target_version_id:
        return _blocked(source, required, "R1",
                        f"{_label(source)} assessed version {source.version}; this request is for version {target_version}. Evidence does not carry across versions.")
    if source.deployment_status not in (None, "active"):
        return _blocked(source, required, "R2",
                        f"The deployment approved by {_label(source)} is {source.deployment_status.replace('_', ' ')}, so its approval is not in good standing.")
    if source.context.audience_type == "internal" and target.audience_type == "citizen_facing":
        return _blocked(source, required, "R3",
                        f"{_label(source)} is an internal-only approval. An internal approval never transfers directly to a citizen-facing use: "
                        "the public was not among the people it was tested for.")
    if source.synthetic and not allow_synthetic:
        return _blocked(source, required, "R11",
                        f"{_label(source)} is seeded example history: its scores were written for the demonstration, not measured "
                        "on the model. With a real model every check runs fresh.")
    # Seeded history is a fixed demonstration and has no real age; everything measured in this system does.
    if not source.synthetic and source.decided_at is not None:
        age_days = ((now or datetime.now(timezone.utc)) - source.decided_at).days
        if age_days > REUSE_MAX_AGE_DAYS:
            return _blocked(source, required, "R12",
                            f"{_label(source)} was decided {age_days} days ago. Evidence older than {REUSE_MAX_AGE_DAYS} days is not reused: "
                            "run the checks again.")

    # ---- rules that force individual checks to run again ----
    forced: dict[tuple[str, str], list[str]] = {}  # (rule, reason) -> checks; one check can be forced by several rules

    def force(checks: list[str], rule: str, reason: str) -> None:
        forced[(rule, reason)] = [c for c in checks if c in required]

    same_use_case = source.context.use_case_id == target.use_case_id
    if _TIER[target.risk_tier] > _TIER[source.context.risk_tier]:
        force(catalog.SECURITY_PRIVACY_CHECKS + catalog.PEOPLE_IMPACT_CHECKS, "R4",
              f"Risk tier rises from {source.context.risk_tier} to {target.risk_tier}: security, privacy and people-impact checks run again at the higher tier.")
    if _SENSITIVITY[target.data_sensitivity] > _SENSITIVITY[source.context.data_sensitivity]:
        force(catalog.SECURITY_PRIVACY_CHECKS, "R5",
              f"Data sensitivity rises from '{source.context.data_sensitivity}' to '{target.data_sensitivity}': security and privacy checks run again.")
    if source.context.audience_type != target.audience_type:
        force(catalog.PEOPLE_IMPACT_CHECKS, "R6",
              f"Audience changes from {source.context.audience_type.replace('_', '-')} to {target.audience_type.replace('_', '-')}: people-impact checks run again.")
    if target.vulnerable_users and not source.context.vulnerable_users:
        force(catalog.PEOPLE_IMPACT_CHECKS, "R7",
              "This service has vulnerable users and the earlier one did not: fairness, accessibility, plain language and contestability run fresh.")

    forced_checks = {check for checks in forced.values() for check in checks}
    context_changed: dict[str, tuple[str, str] | None] = {}
    own_deployment: list[str] = []
    recomputed: list[str] = []
    reuse_map: dict[str, dict] = {}
    for check in required:
        if catalog.CHECKS[check][0] == "compliance":
            recomputed.append(check)
            continue
        if check in catalog.USE_CASE_SPECIFIC_CHECKS and not same_use_case:
            own_deployment.append(check)
            continue
        if check in forced_checks:
            context_changed[check] = None  # explained by the forcing rules above
            continue
        prior = source.checks.get(check)
        if prior is None or prior.status not in _REUSABLE_STATUSES:
            context_changed[check] = ("R8", "Needed here but not covered by the earlier assessment.")
            continue
        threshold = target.thresholds.get(check)
        if prior.score is not None and threshold is not None and prior.score < threshold:
            context_changed[check] = ("R9", f"Earlier score {prior.score:.2f} is below this use case's threshold of {threshold:.2f}.")
            continue
        reuse_map[check] = {"origin_assessment_id": prior.origin_assessment_id, "score": prior.score,
                            "status": prior.status, "threshold": threshold, "note": prior.note}

    if not reuse_map:
        return _blocked(source, required, "R10", f"Nothing in {_label(source)} applies to this context.")

    reasons = [{"rule": "R-MATCH", "effect": "reuse",
                "reason": f"Same model and version as {_label(source)}"
                          + ("" if context_changed or forced else "; same or lower risk tier, compatible data sensitivity, same audience type") + ".",
                "checks": list(reuse_map)}]
    grouped: dict[tuple[str, str], list[str]] = dict(forced)
    for check, key in context_changed.items():
        if key is not None:
            grouped.setdefault(key, []).append(check)
    reasons += [{"rule": rule, "effect": "rerun", "reason": reason, "checks": checks} for (rule, reason), checks in grouped.items()]
    if recomputed:
        reasons.append({"rule": "R-RULES", "effect": "rerun", "checks": recomputed,
                        "reason": "Compliance and procurement rules are recomputed for every assessment against this use case's own card. "
                                  "They are plain rules, so this costs nothing and every rule stays linked to its evidence."})
    if own_deployment:
        reasons.append({"rule": "R-OWN", "effect": "rerun", "checks": own_deployment,
                        "reason": "Always run fresh for a different use case: they describe this department's own deployment, and accountability stays with the department using the model."})

    return {
        "source_assessment_id": source.assessment_id, "source_reference": source.reference,
        "source_department": source.department, "source_use_case": source.use_case_title,
        # Any difference in context makes it partial, even when it happens to force no check on this track.
        "outcome": "partial" if context_changed or forced else "allowed",
        "same_audience": source.context.audience_type == target.audience_type,
        "reasons": reasons, "reused_checks": list(reuse_map),
        "rerun_checks": [c for c in required if c not in reuse_map], "reuse_map": reuse_map,
        "inherited_conditions": source.conditions,
    }


def choose(decisions: list[dict]) -> dict | None:
    """Best usable source: full match first, then the same audience type, then the most checks saved, then the newest."""
    usable = [d for d in decisions if d["outcome"] != "blocked"]
    if not usable:
        return None
    return max(usable, key=lambda d: (d["outcome"] == "allowed", d["same_audience"], len(d["reused_checks"]), d["source_assessment_id"]))

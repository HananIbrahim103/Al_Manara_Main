from datetime import datetime
from typing import Optional

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import catalog


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DepartmentOut(ORM):
    id: int
    code: str
    name: str
    audience_type: str
    description: str
    key_risks: list


class UserOut(ORM):
    id: int
    department_id: Optional[int]
    full_name: str
    email: str
    title: str
    role: str
    reviewer_role: Optional[str]
    can_approve: bool


class LoginIn(BaseModel):
    email: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class EvidenceOut(ORM):
    id: int
    field: str
    status: str
    value: dict
    source: str
    note: str


class ModelVersionOut(ORM):
    id: int
    model_id: int
    version: str
    status: str
    released_at: Optional[datetime]
    changelog: str


class ModelOut(ORM):
    id: int
    slug: str
    name: str
    provider: str
    openrouter_id: str
    description: str


class UseCaseOut(ORM):
    id: int
    code: str
    department_id: int
    title: str
    purpose: str
    audience_type: str
    affected_users: list
    vulnerable_users: bool
    data_sensitivity: str
    consequence_of_error: str
    autonomy_level: str
    human_oversight: str
    languages: list
    expected_volume: str
    thresholds: dict
    created_by_id: Optional[int]
    created_at: datetime


class AssessmentOut(ORM):
    id: int
    reference: str
    use_case_id: int
    model_version_id: int
    department_id: int
    requested_by_id: Optional[int]
    status: str
    risk_tier: Optional[str]
    track: Optional[str]
    tier_rationale: list
    recommendation: Optional[str]
    summary: dict
    plan: dict
    is_history: bool
    reassessment_of_deployment_id: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime]


class CheckResultOut(ORM):
    id: int
    agent: str
    check_key: str
    score: Optional[float]
    threshold: Optional[float]
    status: str
    source: str
    reused_from_assessment_id: Optional[int]
    details: dict


class ReuseDecisionOut(ORM):
    id: int
    source_assessment_id: Optional[int]
    outcome: str
    requested: bool
    selected: bool
    reasons: list
    reused_checks: list
    rerun_checks: list
    created_at: datetime


class ReviewOut(ORM):
    id: int
    reviewer_id: int
    reviewer_role: str
    round: int
    responsibilities: list
    selection_reason: str
    status: str
    comment: str
    assigned_at: datetime
    submitted_at: Optional[datetime]


class ConcernOut(ORM):
    id: int
    raised_by_id: Optional[int]
    raised_by_agent: Optional[str]
    area: Optional[str]
    assigned_to_id: Optional[int]
    title: str
    detail: str
    severity: str
    status: str
    resolution: str
    resolved_by_id: Optional[int]
    created_at: datetime
    resolved_at: Optional[datetime]


class DecisionRecordOut(ORM):
    id: int
    version: int
    content: dict
    plain_summary: str
    created_at: datetime


class ApprovalOut(ORM):
    id: int
    decision: str
    approver_id: int
    risk_accepted_by_id: Optional[int]
    reason: str
    conditions: list
    decided_at: datetime


class StepTimingOut(ORM):
    step_key: str
    mode: str
    duration_seconds: float


class DeploymentOut(ORM):
    id: int
    assessment_id: int
    department_id: int
    use_case_id: int
    model_version_id: int
    status: str
    status_reason: str
    conditions: list
    condition_status: list
    compliance_status: str
    compliance_note: str
    deployed_at: datetime
    next_review_due: Optional[datetime]
    replaced_by_deployment_id: Optional[int]
    retired_at: Optional[datetime]


class IncidentOut(ORM):
    id: int
    deployment_id: Optional[int]
    department_id: int
    model_version_id: int
    title: str
    description: str
    category: str
    severity: str
    status: str
    root_cause: str
    resolution: str
    reported_by_id: Optional[int]
    occurred_at: datetime


class LessonOut(ORM):
    id: int
    model_id: Optional[int]
    department_id: int
    incident_id: Optional[int]
    assessment_id: Optional[int]
    title: str
    detail: str
    tags: list
    created_at: datetime


class FeedbackOut(ORM):
    id: int
    deployment_id: int
    department_id: int
    source: str
    language: str
    text: str
    created_at: datetime


class TestSetOut(ORM):
    id: int
    code: str
    title: str
    use_case_id: Optional[int]
    system_prompt: str
    description: str


class TestCaseOut(ORM):
    id: int
    check_key: str
    language: str
    prompt: str
    expected: dict
    tags: list
    meta: dict
    origin: str


class BaselineOut(ORM):
    step_key: str
    risk_tier: str
    manual_hours: float
    description: str


class AuditOut(ORM):
    id: int
    ts: datetime
    actor_type: str
    actor_id: Optional[str]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    assessment_id: Optional[int]
    details: dict


# ----- composed responses -----

class DepartmentDetail(DepartmentOut):
    users: list[UserOut]
    use_cases: list[UseCaseOut]
    deployments: list[DeploymentOut]


class VersionDetail(ModelVersionOut):
    evidence: list[EvidenceOut]
    evidence_gaps: list[str]  # fields that are missing or unsupported: "unknown = risk"


class ModelDetail(ModelOut):
    versions: list[VersionDetail]


class AssessmentDetail(AssessmentOut):
    use_case: UseCaseOut
    model: ModelOut
    model_version: ModelVersionOut
    department: DepartmentOut
    reuse_decisions: list[ReuseDecisionOut]
    check_results: list[CheckResultOut]
    reviews: list[ReviewOut]
    concerns: list[ConcernOut]
    decision_record: Optional[DecisionRecordOut]
    approval: Optional[ApprovalOut]
    step_timings: list[StepTimingOut]


class TestSetDetail(TestSetOut):
    cases: list[TestCaseOut]


# ----- request bodies (Phase 2) -----

Audience = Literal["internal", "citizen_facing"]
Language = Literal["en", "ar-msa", "ar-gulf"]


class UseCaseIn(BaseModel):
    """The Use-Case Card. Filled in before any model is compared."""
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=10, description="What the AI does and what it must never do")
    audience_type: Audience = Field(description="Who uses it directly")
    affected_users: list[str] = Field(min_length=1, description="Everyone affected, including people who never see the tool")
    vulnerable_users: bool = False
    data_sensitivity: Literal["public", "internal", "personal", "sensitive_personal"]
    consequence_of_error: Literal["minor", "moderate", "serious", "severe"]
    autonomy_level: Literal["assistive", "recommends", "decides_with_review", "autonomous"]
    human_oversight: Literal["always", "sampled", "exception_only", "none"]
    languages: list[Language] = Field(min_length=1)
    expected_volume: str = ""
    thresholds: dict[str, float] = Field(default_factory=dict, description="Minimum score per check; defaults fill the rest")

    @field_validator("thresholds")
    @classmethod
    def _known_checks(cls, value: dict[str, float]) -> dict[str, float]:
        for check, minimum in value.items():
            if check not in catalog.DEFAULT_THRESHOLDS:
                raise ValueError(f"'{check}' is not a scored check; use one of {sorted(catalog.DEFAULT_THRESHOLDS)}")
            if not 0 <= minimum <= 1:
                raise ValueError(f"threshold for '{check}' must be between 0 and 1")
        return value


class ModelIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=2)
    provider: str = Field(min_length=2)
    openrouter_id: str = Field(min_length=3, description="OpenRouter model id used to call the model under test")
    description: str = ""
    version: str = Field(min_length=1, description="First version to register")


class VersionIn(BaseModel):
    version: str = Field(min_length=1)
    changelog: str = ""


class EvidenceDocumentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(description="contract, data_processing_addendum, licence_text, audit_certificate, evaluation_report, "
                                  "price_list, lifecycle_policy, model_card, documentation, marketing, press_release, email, other")
    text: str = Field(min_length=1, max_length=40000)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in catalog.DOCUMENT_KINDS:
            raise ValueError(f"kind must be one of {sorted(catalog.DOCUMENT_KINDS)}")
        return value


class EvidenceSubmission(BaseModel):
    documents: list[EvidenceDocumentIn] = Field(min_length=1, max_length=10)


class EvidenceCorrection(BaseModel):
    """A named person corrects one evidence field after checking the source themselves."""
    status: Literal["verified", "claimed", "unsupported", "missing"]
    value: dict = Field(default_factory=dict)
    source: str = ""
    note: str = Field(min_length=5, description="Why: what you checked")


class AssessmentStart(BaseModel):
    use_case_code: str
    model_slug: str
    version: Optional[str] = Field(default=None, description="Defaults to the current version")
    reuse_from_assessment_id: Optional[int] = Field(
        default=None, description="Ask to reuse one specific past assessment. Leave empty to let the registry search.")


# ----- Phase 4: governance and human approval -----

Severity = Literal["low", "medium", "high"]


class ConcernIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    detail: str = ""
    severity: Severity = "medium"
    area: Optional[str] = Field(default=None, description="Check key (e.g. 'pii_leakage') or 'evidence:<field>'; decides who owns it")


class ReviewResponse(BaseModel):
    status: Literal["no_objection", "concerns", "objection"]
    comment: str = Field(min_length=5, description="What you looked at and what you think")
    concerns: list[ConcernIn] = Field(default_factory=list, max_length=10)


class ConcernClose(BaseModel):
    text: str = Field(min_length=5, description="How it was resolved, or why the residual risk is acceptable")


class SendBackIn(BaseModel):
    reason: str = Field(min_length=10)


class DecisionIn(BaseModel):
    """The human decision. Only the owning department's named approver can make it."""
    decision: Literal["approved", "approved_with_conditions", "rejected"]
    reason: str = Field(min_length=10, description="Why, in your own words. Required.")
    conditions: Optional[list[str]] = Field(default=None, description="Deployment conditions. Defaults to the conditions in the decision record.")
    risk_accepted_by_email: Optional[str] = Field(default=None, description="A different senior reviewer who accepts the residual risk. Defaults to you.")
    override_recommendation: bool = Field(default=False, description="Needed to approve when the system recommends not approving.")


# ----- Phase 5: lifecycle -----

class MonitorEventOut(ORM):
    id: int
    trigger_type: str
    model_id: Optional[int]
    model_version_id: Optional[int]
    deployment_id: Optional[int]
    department_id: Optional[int]
    payload: dict
    source: str
    created_at: datetime


class AlertOut(ORM):
    id: int
    event_id: int
    department_id: int
    deployment_id: Optional[int]
    severity: str
    title: str
    message: str
    action_required: str
    status: str
    acknowledged_by_id: Optional[int]
    acknowledged_at: Optional[datetime]
    note: str
    created_at: datetime


class TriggerIn(BaseModel):
    """A change reported by a person. Other triggers have their own endpoints: a new version (POST /models/{slug}/versions),
    incidents (POST /incidents), complaints (POST /feedback), drift (POST /deployments/{id}/performance)."""
    trigger_type: Literal["provider_terms_change", "data_source_change", "autonomy_increase", "new_service_context"]
    model_slug: Optional[str] = None
    version: Optional[str] = None
    deployment_id: Optional[int] = None
    description: str = Field(min_length=10)
    details: dict = Field(default_factory=dict)


class IncidentIn(BaseModel):
    deployment_id: int
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10)
    category: str = Field(min_length=3, description="e.g. hallucination, name_transliteration, pii_leakage, fairness, arabic_dialect")
    severity: Severity


class LessonIn(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    detail: str = Field(min_length=10)
    tags: list[str] = Field(default_factory=list)


class IncidentResolve(BaseModel):
    root_cause: str = Field(min_length=10)
    resolution: str = Field(min_length=10)
    lesson: Optional[LessonIn] = Field(default=None, description="What other departments should learn; goes to the shared registry")


class FeedbackIn(BaseModel):
    deployment_id: int
    source: Literal["frontline_staff", "citizen_complaint", "appeal"]
    language: Literal["en", "ar-msa", "ar-gulf"] = "en"
    text: str = Field(min_length=3, max_length=4000)


class ConditionCheckIn(BaseModel):
    status: Literal["met", "breached"]
    note: str = Field(min_length=5, description="What was checked and how")


class PerformanceIn(BaseModel):
    check_key: str
    observed_score: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=1)
    note: str = ""

    @field_validator("check_key")
    @classmethod
    def _scored(cls, value: str) -> str:
        if value not in catalog.DEFAULT_THRESHOLDS:
            raise ValueError(f"'{value}' is not a scored check; use one of {sorted(catalog.DEFAULT_THRESHOLDS)}")
        return value


class DeploymentAction(BaseModel):
    reason: str = Field(min_length=10)


class ReassessIn(BaseModel):
    version: Optional[str] = Field(default=None, description="Version to assess. Defaults to the model's current version.")

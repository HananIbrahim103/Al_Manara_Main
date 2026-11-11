from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB, list: JSONB, datetime: DateTime(timezone=True), str: String}


def _pk() -> Mapped[int]:
    return mapped_column(Integer, primary_key=True)


def _fk(target: str, nullable: bool = False, index: bool = True):
    return mapped_column(ForeignKey(target), nullable=nullable, index=index)


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- Organisation ----------

class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = _pk()
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str]
    audience_type: Mapped[str]  # internal | citizen_facing
    description: Mapped[str] = mapped_column(Text, default="")
    key_risks: Mapped[list] = mapped_column(default=list)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = _pk()
    department_id: Mapped[Optional[int]] = _fk("departments.id", nullable=True)
    full_name: Mapped[str]
    email: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str]
    role: Mapped[str]  # officer | reviewer | admin
    reviewer_role: Mapped[Optional[str]]  # key in catalog.REVIEWER_ROLES
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------- Registry: models and provider evidence ----------

class AIModel(Base):
    __tablename__ = "ai_models"
    id: Mapped[int] = _pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str]
    provider: Mapped[str]
    openrouter_id: Mapped[str]  # the id used to call the model under test
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version"),)
    id: Mapped[int] = _pk()
    model_id: Mapped[int] = _fk("ai_models.id")
    version: Mapped[str]
    status: Mapped[str] = mapped_column(default="current")  # current | superseded | withdrawn
    released_at: Mapped[Optional[datetime]]
    changelog: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


class ProviderEvidence(Base):
    __tablename__ = "provider_evidence"
    __table_args__ = (UniqueConstraint("model_version_id", "field"),)
    id: Mapped[int] = _pk()
    model_version_id: Mapped[int] = _fk("model_versions.id")
    field: Mapped[str]  # key in catalog.EVIDENCE_FIELDS
    status: Mapped[str]  # verified | claimed | unsupported | missing
    value: Mapped[dict] = mapped_column(default=dict)  # normalised content
    source: Mapped[str] = mapped_column(default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


# ---------- Use-Case Card and assessment ----------

class UseCase(Base):
    __tablename__ = "use_cases"
    id: Mapped[int] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    department_id: Mapped[int] = _fk("departments.id")
    title: Mapped[str]
    purpose: Mapped[str] = mapped_column(Text)
    audience_type: Mapped[str]  # who uses it directly: internal | citizen_facing
    affected_users: Mapped[list] = mapped_column(default=list)
    vulnerable_users: Mapped[bool] = mapped_column(Boolean, default=False)
    data_sensitivity: Mapped[str]
    consequence_of_error: Mapped[str]
    autonomy_level: Mapped[str]
    human_oversight: Mapped[str]
    languages: Mapped[list] = mapped_column(default=list)  # en | ar-msa | ar-gulf
    expected_volume: Mapped[str] = mapped_column(default="")
    thresholds: Mapped[dict] = mapped_column(default=dict)  # check_key -> minimum score
    created_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _now()


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = _pk()
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    use_case_id: Mapped[int] = _fk("use_cases.id")
    model_version_id: Mapped[int] = _fk("model_versions.id")
    department_id: Mapped[int] = _fk("departments.id")  # the accountable department
    requested_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    # draft | planned | evaluating | in_review | awaiting_decision |
    # approved | approved_with_conditions | rejected | blocked | failed
    status: Mapped[str] = mapped_column(default="draft", index=True)
    risk_tier: Mapped[Optional[str]]
    track: Mapped[Optional[str]]  # fast | standard | full
    tier_rationale: Mapped[list] = mapped_column(default=list)  # rules that fired
    recommendation: Mapped[Optional[str]]  # system recommendation; never a decision
    summary: Mapped[dict] = mapped_column(default=dict)
    # checks required, which are reused (and from where) and which run fresh, with reasons
    plan: Mapped[dict] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    is_history: Mapped[bool] = mapped_column(Boolean, default=False)  # seeded past assessment
    # set when the lifecycle monitor sent a deployment back for reassessment
    reassessment_of_deployment_id: Mapped[Optional[int]] = _fk("deployments.id", nullable=True)
    started_at: Mapped[datetime] = _now()
    completed_at: Mapped[Optional[datetime]]


class ReuseDecision(Base):
    __tablename__ = "reuse_decisions"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    source_assessment_id: Mapped[Optional[int]] = _fk("assessments.id", nullable=True)
    outcome: Mapped[str]  # allowed | partial | blocked
    requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # the department asked for this source
    selected: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # the source the plan uses
    reasons: Mapped[list] = mapped_column(default=list)
    reused_checks: Mapped[list] = mapped_column(default=list)
    rerun_checks: Mapped[list] = mapped_column(default=list)
    created_at: Mapped[datetime] = _now()


class CheckResult(Base):
    __tablename__ = "check_results"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    agent: Mapped[str]  # testing | citizen_impact | compliance
    check_key: Mapped[str]
    score: Mapped[Optional[float]] = mapped_column(Float)
    threshold: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str]  # passed | failed | warning | skipped | error
    source: Mapped[str] = mapped_column(default="fresh")  # fresh | reused
    reused_from_assessment_id: Mapped[Optional[int]] = _fk("assessments.id", nullable=True)
    details: Mapped[dict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _now()


# ---------- Open data sources (Bayanat and, later, the emirate portals) ----------

class DataSource(Base):
    """A published open-data table, saved as a snapshot so tests are repeatable and work offline."""
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("portal", "file_ref"),)
    id: Mapped[int] = _pk()
    key: Mapped[str] = mapped_column(String(48), unique=True)  # short readable id, e.g. TRF-ACCIDENT-TYPE
    portal: Mapped[str] = mapped_column(default="bayanat")
    portal_token: Mapped[str]  # dataset id on the portal
    title: Mapped[str]
    publisher: Mapped[str] = mapped_column(default="")
    topics: Mapped[list] = mapped_column(default=list)
    page_url: Mapped[str]
    licence_url: Mapped[str] = mapped_column(default="")
    last_updated: Mapped[Optional[date]] = mapped_column(Date)  # as shown on the portal
    resource_name: Mapped[str] = mapped_column(default="")
    file_ref: Mapped[str]  # stable link of the file the snapshot came from
    columns: Mapped[list] = mapped_column(default=list)
    measure: Mapped[str]
    dimensions: Mapped[list] = mapped_column(default=list)
    rows: Mapped[list] = mapped_column(default=list)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str]
    fetched_at: Mapped[datetime] = _now()
    status: Mapped[str] = mapped_column(default="ok")  # ok | unreachable
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    history: Mapped[list] = mapped_column(default=list)  # earlier snapshots: last_updated, checksum, rows, fetched_at
    created_at: Mapped[datetime] = _now()


class UseCaseDataSource(Base):
    __tablename__ = "use_case_data_sources"
    __table_args__ = (UniqueConstraint("use_case_id", "data_source_id"),)
    id: Mapped[int] = _pk()
    use_case_id: Mapped[int] = _fk("use_cases.id")
    data_source_id: Mapped[int] = _fk("data_sources.id")
    linked_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _now()


# ---------- Test sets ----------

class TestSet(Base):
    __tablename__ = "test_sets"
    id: Mapped[int] = _pk()
    code: Mapped[str] = mapped_column(String(48), unique=True)
    title: Mapped[str]
    use_case_id: Mapped[Optional[int]] = _fk("use_cases.id", nullable=True)  # null = shared set
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")


class TestCase(Base):
    __tablename__ = "test_cases"
    id: Mapped[int] = _pk()
    test_set_id: Mapped[int] = _fk("test_sets.id")
    check_key: Mapped[str] = mapped_column(index=True)
    language: Mapped[str]  # en | ar-msa | ar-gulf
    prompt: Mapped[str] = mapped_column(Text)
    # must_include / must_include_any / must_not_include / reference / rubric
    expected: Mapped[dict] = mapped_column(default=dict)
    tags: Mapped[list] = mapped_column(default=list)
    meta: Mapped[dict] = mapped_column(default=dict)  # e.g. fairness pair id and variant
    origin: Mapped[str] = mapped_column(default="seeded")  # seeded | generated


class TestRun(Base):
    __tablename__ = "test_runs"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    test_case_id: Mapped[int] = _fk("test_cases.id")
    model_output: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[Optional[bool]]
    score: Mapped[Optional[float]] = mapped_column(Float)
    judge_notes: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[Optional[int]]
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


# ---------- Compliance ----------

class ComplianceRule(Base):
    __tablename__ = "compliance_rules"
    id: Mapped[int] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    check_key: Mapped[str]
    title: Mapped[str]
    requirement: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(default="")
    severity: Mapped[str] = mapped_column(default="major")  # blocker | major | minor
    min_tier: Mapped[str] = mapped_column(default="low")


class ComplianceFinding(Base):
    __tablename__ = "compliance_findings"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    rule_id: Mapped[int] = _fk("compliance_rules.id")
    status: Mapped[str]  # compliant | conditional | non_compliant | unknown | not_applicable
    evidence_refs: Mapped[list] = mapped_column(default=list)  # links each rule to its evidence
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


# ---------- Governance ----------

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    reviewer_id: Mapped[int] = _fk("users.id")
    reviewer_role: Mapped[str]
    round: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))  # a send-back starts a new round
    responsibilities: Mapped[list] = mapped_column(default=list, server_default=text("'[]'::jsonb"))  # checks this reviewer owns
    selection_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(default="pending")  # pending | no_objection | concerns | objection | withdrawn
    comment: Mapped[str] = mapped_column(Text, default="")
    assigned_at: Mapped[datetime] = _now()
    submitted_at: Mapped[Optional[datetime]]


class Concern(Base):
    __tablename__ = "concerns"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    raised_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    raised_by_agent: Mapped[Optional[str]]
    area: Mapped[Optional[str]]  # check key, or evidence:<field>: decides who is responsible
    assigned_to_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    title: Mapped[str]
    detail: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(default="medium")  # low | medium | high
    status: Mapped[str] = mapped_column(default="open")  # open | resolved | accepted_as_residual_risk
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    created_at: Mapped[datetime] = _now()
    resolved_at: Mapped[Optional[datetime]]


class DecisionRecord(Base):
    __tablename__ = "decision_records"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # assumptions, limitations, evidence_used, conditions, residual_risk, accountable_owner
    content: Mapped[dict] = mapped_column(default=dict)
    plain_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


class Approval(Base):
    """The decision. Always made by a named human from the accountable department."""
    __tablename__ = "approvals"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), unique=True)
    decision: Mapped[str]  # approved | approved_with_conditions | rejected
    approver_id: Mapped[int] = _fk("users.id")
    risk_accepted_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    conditions: Mapped[list] = mapped_column(default=list)
    decided_at: Mapped[datetime] = _now()


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    department_id: Mapped[int] = _fk("departments.id")
    use_case_id: Mapped[int] = _fk("use_cases.id")
    model_version_id: Mapped[int] = _fk("model_versions.id")
    status: Mapped[str] = mapped_column(default="active")  # active | under_reassessment | paused | retired
    status_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    conditions: Mapped[list] = mapped_column(default=list)
    # one entry per condition: {condition, status: unverified | met | breached, checked_at, checked_by, note}
    condition_status: Mapped[list] = mapped_column(default=list, server_default=text("'[]'::jsonb"))
    compliance_status: Mapped[str] = mapped_column(default="compliant")  # compliant | at_risk | non_compliant
    compliance_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    deployed_at: Mapped[datetime] = _now()
    next_review_due: Mapped[Optional[datetime]]
    replaced_by_deployment_id: Mapped[Optional[int]] = _fk("deployments.id", nullable=True)
    retired_at: Mapped[Optional[datetime]]


# ---------- Lifecycle ----------

class MonitorEvent(Base):
    __tablename__ = "monitor_events"
    id: Mapped[int] = _pk()
    trigger_type: Mapped[str]  # key in catalog.TRIGGER_TYPES
    model_id: Mapped[Optional[int]] = _fk("ai_models.id", nullable=True)
    model_version_id: Mapped[Optional[int]] = _fk("model_versions.id", nullable=True)
    deployment_id: Mapped[Optional[int]] = _fk("deployments.id", nullable=True)
    department_id: Mapped[Optional[int]] = _fk("departments.id", nullable=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    source: Mapped[str] = mapped_column(default="system")
    created_at: Mapped[datetime] = _now()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = _pk()
    event_id: Mapped[int] = _fk("monitor_events.id")
    department_id: Mapped[int] = _fk("departments.id")
    deployment_id: Mapped[Optional[int]] = _fk("deployments.id", nullable=True)
    severity: Mapped[str] = mapped_column(default="medium")
    title: Mapped[str]
    message: Mapped[str] = mapped_column(Text, default="")
    action_required: Mapped[str] = mapped_column(default="review")  # info | review | reassess | pause
    status: Mapped[str] = mapped_column(default="open")  # open | acknowledged | closed
    acknowledged_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    acknowledged_at: Mapped[Optional[datetime]]
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = _now()


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = _pk()
    deployment_id: Mapped[Optional[int]] = _fk("deployments.id", nullable=True)
    department_id: Mapped[int] = _fk("departments.id")
    model_version_id: Mapped[int] = _fk("model_versions.id")
    title: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str]
    severity: Mapped[str]  # low | medium | high
    status: Mapped[str] = mapped_column(default="open")  # open | resolved
    root_cause: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    reported_by_id: Mapped[Optional[int]] = _fk("users.id", nullable=True)
    occurred_at: Mapped[datetime] = _now()


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = _pk()
    model_id: Mapped[Optional[int]] = _fk("ai_models.id", nullable=True)
    department_id: Mapped[int] = _fk("departments.id")
    incident_id: Mapped[Optional[int]] = _fk("incidents.id", nullable=True)
    assessment_id: Mapped[Optional[int]] = _fk("assessments.id", nullable=True)
    title: Mapped[str]
    detail: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(default=list)
    created_at: Mapped[datetime] = _now()


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = _pk()
    deployment_id: Mapped[int] = _fk("deployments.id")
    department_id: Mapped[int] = _fk("departments.id")
    source: Mapped[str]  # frontline_staff | citizen_complaint | appeal
    language: Mapped[str] = mapped_column(default="en")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


# ---------- Measurement and audit ----------

class ManualBaseline(Base):
    """How long each step takes today, done by hand (working hours)."""
    __tablename__ = "manual_baselines"
    __table_args__ = (UniqueConstraint("step_key", "risk_tier"),)
    id: Mapped[int] = _pk()
    step_key: Mapped[str]
    risk_tier: Mapped[str]
    manual_hours: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(default="")


class StepTiming(Base):
    __tablename__ = "step_timings"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[int] = _fk("assessments.id")
    step_key: Mapped[str]
    mode: Mapped[str] = mapped_column(default="automated")  # automated | human | reused
    duration_seconds: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = _now()


class AgentRun(Base):
    """One row per agent call: input, output, model, tokens, cost, time. Append-only."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = _pk()
    assessment_id: Mapped[Optional[int]] = _fk("assessments.id", nullable=True)
    agent: Mapped[str]
    step: Mapped[str]
    input: Mapped[dict] = mapped_column(default=dict)
    output: Mapped[dict] = mapped_column(default=dict)
    llm_model: Mapped[Optional[str]]
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(default="ok")  # ok | failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class AuditLog(Base):
    """Who did what, when. Append-only: the database rejects UPDATE, DELETE and TRUNCATE."""
    __tablename__ = "audit_log"
    id: Mapped[int] = _pk()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_type: Mapped[str]  # user | agent | system
    actor_id: Mapped[Optional[str]]
    action: Mapped[str] = mapped_column(index=True)
    entity_type: Mapped[Optional[str]]
    entity_id: Mapped[Optional[str]]
    assessment_id: Mapped[Optional[int]] = _fk("assessments.id", nullable=True)
    details: Mapped[dict] = mapped_column(default=dict)

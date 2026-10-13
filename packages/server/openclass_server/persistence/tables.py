"""Genesis schema: relational identities, versioned JSON domain snapshots.

Snapshot internals can become normalized tables through future explicit migrations.
No provider-specific fields are required by this schema.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ClassifierRow(Base):
    __tablename__ = "classifiers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class OntologyRow(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (UniqueConstraint("classifier_id", "version_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ObservationRow(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "classification_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"))
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class UnknownRow(Base):
    __tablename__ = "unknown_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("classification_runs.id"), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventRow(Base):
    __tablename__ = "ontology_events"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewRow(Base):
    __tablename__ = "supervisor_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("classification_runs.id"), index=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CandidateRow(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    classifier_id: Mapped[str] = mapped_column(ForeignKey("classifiers.id"), index=True)
    base_ontology_version_id: Mapped[str] = mapped_column(ForeignKey("ontology_versions.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    owner_id: Mapped[str | None] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RawEventRow(Base):
    __tablename__ = "raw_events"
    __table_args__ = (Index("uq_raw_events_content", "project_id", "content_hash", unique=True),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DecisionServiceRow(Base):
    __tablename__ = "decision_services"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_decision_services_project_id_slug"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DecisionRunRow(Base):
    __tablename__ = "decision_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_events.id", ondelete="CASCADE"), index=True
    )
    decision_service_id: Mapped[str] = mapped_column(
        ForeignKey("decision_services.id", ondelete="CASCADE"), index=True
    )
    decision_node_id: Mapped[str] = mapped_column(String(36))
    decision_service_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    service_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    execution_mode: Mapped[str] = mapped_column(String(50))
    real_inference: Mapped[bool] = mapped_column(Boolean)
    selected_choice: Mapped[str] = mapped_column(String(100))
    supervision_outcome: Mapped[str] = mapped_column(String(20))
    top_probability: Mapped[float] = mapped_column(Float)
    margin: Mapped[float] = mapped_column(Float)
    unknown_probability: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ProviderUsageRow(Base):
    __tablename__ = "provider_usage"
    __table_args__ = (
        Index("uq_provider_usage_day", "project_id", "provider", "usage_date", unique=True),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200), default="")
    usage_date: Mapped[date] = mapped_column(Date)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms_total: Mapped[float] = mapped_column(Float, default=0.0)


class ProjectChoiceCandidateRow(Base):
    __tablename__ = "project_choice_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    decision_service_id: Mapped[str] = mapped_column(ForeignKey("decision_services.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvidenceCaseRow(Base):
    __tablename__ = "evidence_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    decision_service_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_services.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), index=True)
    diagnosis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    diagnosis_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvidenceItemRow(Base):
    __tablename__ = "evidence_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    raw_event_id: Mapped[str | None] = mapped_column(ForeignKey("raw_events.id"), nullable=True)
    decision_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_runs.id"), nullable=True, index=True
    )
    decision_service_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_services.id"), nullable=True
    )
    evidence_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_cases.id"), nullable=True, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    diagnosis: Mapped[str | None] = mapped_column(String(50), nullable=True)
    diagnosis_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_choice: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supervision_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="automatic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunFeedbackRow(Base):
    __tablename__ = "run_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    decision_run_id: Mapped[str] = mapped_column(ForeignKey("decision_runs.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    corrected_choice: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ProjectIntegrationRow(Base):
    __tablename__ = "project_integrations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    endpoint: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WebhookReceiptRow(Base):
    __tablename__ = "webhook_receipts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    # Retain identity after deleting configuration; receipt history is immutable.
    integration_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"), unique=True)
    source: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    response_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UnknownTriageRow(Base):
    __tablename__ = "unknown_triage"
    run_id: Mapped[str] = mapped_column(ForeignKey("decision_runs.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmbeddingRow(Base):
    __tablename__ = "embeddings"
    run_id: Mapped[str] = mapped_column(ForeignKey("decision_runs.id"), primary_key=True)
    model: Mapped[str] = mapped_column(String(200))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UnknownClusterRow(Base):
    __tablename__ = "unknown_clusters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    decision_service_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    algorithm: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    threshold: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClusterMemberRow(Base):
    __tablename__ = "cluster_members"
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("unknown_clusters.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("decision_runs.id"), primary_key=True)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)


class ClusterCandidateRow(Base):
    __tablename__ = "cluster_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("unknown_clusters.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(30))
    canonical_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON)
    existing_match: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CandidateEvidenceRow(Base):
    __tablename__ = "candidate_evidence"
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("cluster_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("decision_runs.id"), primary_key=True)


class CandidateReviewRow(Base):
    __tablename__ = "candidate_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("cluster_candidates.id", ondelete="CASCADE"), index=True
    )
    reviewer: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationSetRow(Base):
    __tablename__ = "evaluation_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationExampleRow(Base):
    __tablename__ = "evaluation_examples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_sets.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(30))
    annotator: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text, default="")
    slice_tag: Mapped[str] = mapped_column(String(30), default="historical")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationRunRow(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("evaluation_sets.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("cluster_candidates.id"))
    overall_passed: Mapped[bool] = mapped_column(Boolean)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ServiceVersionRow(Base):
    __tablename__ = "service_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("decision_services.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    choices: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OntologyEventRow(Base):
    __tablename__ = "service_ontology_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    service_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(200))
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertRuleRow(Base):
    __tablename__ = "alert_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    metric: Mapped[str] = mapped_column(String(40))
    threshold: Mapped[float] = mapped_column(Float)
    window: Mapped[str] = mapped_column(String(20), default="1h")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertEventRow(Base):
    __tablename__ = "alert_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(40))
    measured: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntegrationRouteRow(Base):
    __tablename__ = "integration_routes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("project_integrations.id", ondelete="CASCADE")
    )
    match_choice: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(40))
    action_value: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoutingOutcomeRow(Base):
    __tablename__ = "routing_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    integration_id: Mapped[str] = mapped_column(String(36))
    event_id: Mapped[str] = mapped_column(ForeignKey("raw_events.id"))
    selected_choice: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

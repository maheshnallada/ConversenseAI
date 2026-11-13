from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InteractionRow(Base):
    __tablename__ = "interactions"
    __table_args__ = (UniqueConstraint("tenant_id", "interaction_id", name="uq_interaction_identity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    schema_version: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "event_type",
            name="uq_outbox_acceptance",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ArtifactRow(Base):
    __tablename__ = "interaction_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "artifact_id",
            name="uq_artifact_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    artifact_id: Mapped[str] = mapped_column(String(128))
    artifact_type: Mapped[str] = mapped_column(String(64))
    uri: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    source_path: Mapped[str] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(32))  # "valid", "warning", "error", "silent"
    validation_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TurnRow(Base):
    __tablename__ = "interaction_turns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "turn_index",
            name="uq_interaction_turn",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    turn_id: Mapped[str] = mapped_column(String(128))
    turn_index: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(32))  # "agent", "customer"
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    playback_spoken: Mapped[str | None] = mapped_column(String(32), nullable=True)
    playback_heard_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    barged_in: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InteractionTimelineRow(Base):
    __tablename__ = "interaction_timelines"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            name="uq_interaction_timeline",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    total_duration_s: Mapped[float] = mapped_column(Float)
    agent_turn_count: Mapped[int] = mapped_column(Integer)
    customer_turn_count: Mapped[int] = mapped_column(Integer)
    overlap_count: Mapped[int] = mapped_column(Integer)
    total_overlap_s: Mapped[float] = mapped_column(Float)
    first_technical_failure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_technical_failure_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_technical_failure_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_conversational_failure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_conversational_failure_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_conversational_failure_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeline_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ObservabilityMetricsRow(Base):
    __tablename__ = "observability_metrics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            name="uq_observability_metrics",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    recording_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    telephony_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer)
    agent_turn_count: Mapped[int] = mapped_column(Integer)
    customer_turn_count: Mapped[int] = mapped_column(Integer)
    first_agent_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_response_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_response_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90_response_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_response_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    p99_response_latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    longest_silence_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    overlap_count: Mapped[int] = mapped_column(Integer)
    total_overlap_s: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_currency: Mapped[str] = mapped_column(String(16))
    metrics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationResultRow(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "interaction_id",
            "evaluator_id",
            "evaluator_version",
            name="uq_evaluation_result",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    interaction_id: Mapped[str] = mapped_column(String(128), index=True)
    evaluator_id: Mapped[str] = mapped_column(String(128), index=True)
    evaluator_version: Mapped[str] = mapped_column(String(32))
    family: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), index=True)
    evidence_json: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ImportRunRow(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    total_calls: Mapped[int] = mapped_column(Integer)
    successful_calls: Mapped[int] = mapped_column(Integer)
    failed_calls: Mapped[int] = mapped_column(Integer)
    summary_json: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoldenCallLabelRow(Base):
    __tablename__ = "golden_dataset_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    interaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    what_happened: Mapped[str] = mapped_column(String(128))
    correct_outcome: Mapped[str] = mapped_column(String(128))
    facts_customer_gave: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String(32))
    emotion: Mapped[str] = mapped_column(String(32))
    overall: Mapped[str] = mapped_column(String(32))
    first_thing_wrong_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_thing_wrong_what: Mapped[str | None] = mapped_column(Text, nullable=True)
    never_rule_broken: Mapped[str] = mapped_column(String(128), default="None")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


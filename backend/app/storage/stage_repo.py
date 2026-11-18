from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.orm import PipelineStageRow


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class StageRepository:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def record_stage_start(
        self,
        tenant_id: str,
        interaction_id: str,
        stage_name: str,
        idempotency_key: str | None = None,
        max_retries: int = 3,
    ) -> PipelineStageRow:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.execute(
                select(PipelineStageRow).where(
                    PipelineStageRow.tenant_id == tenant_id,
                    PipelineStageRow.interaction_id == interaction_id,
                    PipelineStageRow.stage_name == stage_name,
                )
            ).scalar_one_or_none()

            if row is None:
                row = PipelineStageRow(
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    stage_name=stage_name,
                    status="running",
                    retry_count=0,
                    max_retries=max_retries,
                    idempotency_key=idempotency_key,
                    started_at=now,
                    completed_at=None,
                    duration_ms=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.status = "running"
                row.started_at = now
                row.updated_at = now
                if idempotency_key:
                    row.idempotency_key = idempotency_key

            session.commit()
            session.refresh(row)
            return row

    def record_stage_success(
        self,
        tenant_id: str,
        interaction_id: str,
        stage_name: str,
        duration_ms: float | None = None,
    ) -> PipelineStageRow | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.execute(
                select(PipelineStageRow).where(
                    PipelineStageRow.tenant_id == tenant_id,
                    PipelineStageRow.interaction_id == interaction_id,
                    PipelineStageRow.stage_name == stage_name,
                )
            ).scalar_one_or_none()

            if row is not None:
                row.status = "completed"
                row.completed_at = now
                row.updated_at = now
                row.last_error = None
                if duration_ms is not None:
                    row.duration_ms = duration_ms
                elif row.started_at is not None:
                    row.duration_ms = (now - _as_utc(row.started_at)).total_seconds() * 1000.0
                session.commit()
                session.refresh(row)
            return row

    def record_stage_failure(
        self,
        tenant_id: str,
        interaction_id: str,
        stage_name: str,
        error_message: str,
        is_dead_letter: bool = False,
        duration_ms: float | None = None,
    ) -> PipelineStageRow | None:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            row = session.execute(
                select(PipelineStageRow).where(
                    PipelineStageRow.tenant_id == tenant_id,
                    PipelineStageRow.interaction_id == interaction_id,
                    PipelineStageRow.stage_name == stage_name,
                )
            ).scalar_one_or_none()

            if row is not None:
                row.status = "dead_letter" if is_dead_letter else "failed"
                row.retry_count += 1
                row.last_error = error_message
                row.updated_at = now
                if duration_ms is not None:
                    row.duration_ms = duration_ms
                elif row.started_at is not None:
                    row.duration_ms = (now - _as_utc(row.started_at)).total_seconds() * 1000.0
                session.commit()
                session.refresh(row)
            return row

    def get_stages(
        self,
        tenant_id: str,
        interaction_id: str,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(
                select(PipelineStageRow).where(
                    PipelineStageRow.tenant_id == tenant_id,
                    PipelineStageRow.interaction_id == interaction_id,
                ).order_by(PipelineStageRow.created_at)
            ).scalars().all()

            return [
                {
                    "stage_name": r.stage_name,
                    "status": r.status,
                    "retry_count": r.retry_count,
                    "max_retries": r.max_retries,
                    "last_error": r.last_error,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "duration_ms": r.duration_ms,
                }
                for r in rows
            ]

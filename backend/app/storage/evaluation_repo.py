import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.domain.evaluation import (
    EvaluationBatchRecord,
    EvaluationResult,
    EvaluationRun,
    EvidenceItem,
)
from app.storage.orm import EvaluationBatchRow, EvaluationResultRow, EvaluationRunRow


class EvaluationRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def save_run(self, run: EvaluationRun) -> None:
        with self.session_factory() as session:
            session.add(
                EvaluationRunRow(
                    run_id=run.run_id,
                    tenant_id=run.tenant_id,
                    interaction_id=run.interaction_id,
                    summary_json=json.dumps(
                        run.summary,
                        default=lambda value: (
                            value.isoformat()
                            if isinstance(value, datetime)
                            else str(value)
                        ),
                    ),
                    review_required=run.review_required,
                    review_reasons_json=json.dumps(run.review_reasons),
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )
            )
            session.add_all(
                [
                    EvaluationBatchRow(
                        evaluation_id=batch.evaluation_id,
                        run_id=run.run_id,
                        tenant_id=run.tenant_id,
                        interaction_id=run.interaction_id,
                        batch_name=batch.batch_name,
                        status=batch.status,
                        model=batch.model,
                        prompt_version=batch.prompt_version,
                        schema_version=batch.schema_version,
                        started_at=batch.started_at,
                        completed_at=batch.completed_at,
                        input_tokens=batch.input_tokens,
                        output_tokens=batch.output_tokens,
                        raw_output=batch.raw_output,
                        parsed_output_json=(
                            json.dumps(batch.parsed_output)
                            if batch.parsed_output is not None
                            else None
                        ),
                        validation_json=json.dumps(batch.validation),
                        review_required=batch.review_required,
                        review_status=batch.review_status,
                        review_reasons_json=json.dumps(batch.review_reasons),
                        source_evaluation_id=batch.source_evaluation_id,
                        error_type=batch.error_type,
                        error_message=batch.error_message,
                    )
                    for batch in run.batches
                ]
            )
            session.commit()

    @staticmethod
    def _to_run(row: EvaluationRunRow, batch_rows: list[EvaluationBatchRow]) -> EvaluationRun:
        return EvaluationRun(
            run_id=row.run_id,
            tenant_id=row.tenant_id,
            interaction_id=row.interaction_id,
            batches=[
                EvaluationBatchRecord(
                    evaluation_id=batch.evaluation_id,
                    batch_name=batch.batch_name,
                    status=batch.status,
                    model=batch.model,
                    prompt_version=batch.prompt_version,
                    schema_version=batch.schema_version,
                    started_at=batch.started_at,
                    completed_at=batch.completed_at,
                    input_tokens=batch.input_tokens,
                    output_tokens=batch.output_tokens,
                    raw_output=batch.raw_output,
                    parsed_output=(
                        json.loads(batch.parsed_output_json)
                        if batch.parsed_output_json
                        else None
                    ),
                    validation=json.loads(batch.validation_json),
                    review_required=batch.review_required,
                    review_status=batch.review_status,
                    review_reasons=json.loads(batch.review_reasons_json),
                    source_evaluation_id=batch.source_evaluation_id,
                    error_type=batch.error_type,
                    error_message=batch.error_message,
                )
                for batch in batch_rows
            ],
            summary=json.loads(row.summary_json),
            started_at=row.started_at,
            completed_at=row.completed_at,
            review_required=row.review_required,
            review_reasons=json.loads(row.review_reasons_json),
        )

    def get_run(
        self,
        tenant_id: str,
        interaction_id: str,
        run_id: str,
    ) -> EvaluationRun | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(EvaluationRunRow).where(
                    EvaluationRunRow.tenant_id == tenant_id,
                    EvaluationRunRow.interaction_id == interaction_id,
                    EvaluationRunRow.run_id == run_id,
                )
            )
            if row is None:
                return None
            batch_rows = session.scalars(
                select(EvaluationBatchRow)
                .where(
                    EvaluationBatchRow.tenant_id == tenant_id,
                    EvaluationBatchRow.interaction_id == interaction_id,
                    EvaluationBatchRow.run_id == run_id,
                )
                .order_by(EvaluationBatchRow.batch_name)
            ).all()
            return self._to_run(row, list(batch_rows))

    def get_latest_run(
        self,
        tenant_id: str,
        interaction_id: str,
    ) -> EvaluationRun | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(EvaluationRunRow)
                .where(
                    EvaluationRunRow.tenant_id == tenant_id,
                    EvaluationRunRow.interaction_id == interaction_id,
                )
                .order_by(
                    desc(EvaluationRunRow.started_at),
                    desc(EvaluationRunRow.id),
                )
                .limit(1)
            )
            if row is None:
                return None
            batch_rows = session.scalars(
                select(EvaluationBatchRow)
                .where(
                    EvaluationBatchRow.tenant_id == tenant_id,
                    EvaluationBatchRow.interaction_id == interaction_id,
                    EvaluationBatchRow.run_id == row.run_id,
                )
                .order_by(EvaluationBatchRow.batch_name)
            ).all()
            return self._to_run(row, list(batch_rows))

    def save_results(
        self,
        tenant_id: str,
        interaction_id: str,
        results: list[EvaluationResult],
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            dialect = session.get_bind().dialect.name
            if dialect == "sqlite":
                insert = sqlite_insert
            elif dialect == "postgresql":
                insert = postgresql_insert
            else:
                raise NotImplementedError(
                    f"Atomic evaluation upsert is not supported for database dialect {dialect!r}"
                )

            for r in results:
                evidence_dicts = [asdict(e) for e in r.evidence]
                values = {
                    "tenant_id": tenant_id,
                    "interaction_id": interaction_id,
                    "evaluator_id": r.evaluator_id,
                    "evaluator_version": r.evaluator_version,
                    "family": r.family,
                    "method": r.method,
                    "label": r.label,
                    "score": r.score,
                    "confidence": r.confidence,
                    "severity": r.severity,
                    "review_status": r.review_status,
                    "evidence_json": json.dumps(evidence_dicts),
                    "reason": r.reason,
                    "details_json": json.dumps(r.details),
                    "created_at": now,
                }
                statement = insert(EvaluationResultRow).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[
                        EvaluationResultRow.tenant_id,
                        EvaluationResultRow.interaction_id,
                        EvaluationResultRow.evaluator_id,
                        EvaluationResultRow.evaluator_version,
                    ],
                    set_={
                        key: getattr(statement.excluded, key)
                        for key in values
                        if key
                        not in {
                            "tenant_id",
                            "interaction_id",
                            "evaluator_id",
                            "evaluator_version",
                        }
                    },
                )
                session.execute(statement)
            session.commit()

    def save_many(self, results: list[EvaluationResult]) -> None:
        if not results:
            return
        by_interaction: dict[tuple[str, str], list[EvaluationResult]] = {}
        for r in results:
            key = (r.tenant_id, r.interaction_id)
            by_interaction.setdefault(key, []).append(r)
        for (tenant_id, interaction_id), items in by_interaction.items():
            self.save_results(tenant_id, interaction_id, items)

    def get_by_interaction(self, tenant_id: str, interaction_id: str) -> list[EvaluationResult]:
        return self.get_results(tenant_id, interaction_id)

    def get_results(self, tenant_id: str, interaction_id: str) -> list[EvaluationResult]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(EvaluationResultRow).where(
                    EvaluationResultRow.tenant_id == tenant_id,
                    EvaluationResultRow.interaction_id == interaction_id,
                )
            ).all()

            results: list[EvaluationResult] = []
            for r in rows:
                ev_data = json.loads(r.evidence_json) if r.evidence_json else []
                evidence = [EvidenceItem(**item) for item in ev_data]
                details = json.loads(r.details_json) if r.details_json else {}

                results.append(
                    EvaluationResult(
                        tenant_id=r.tenant_id,
                        interaction_id=r.interaction_id,
                        evaluator_id=r.evaluator_id,
                        evaluator_version=r.evaluator_version,
                        family=r.family,
                        method=r.method,
                        label=r.label,
                        score=r.score,
                        confidence=r.confidence,
                        severity=r.severity,
                        review_status=r.review_status,
                        evidence=evidence,
                        reason=r.reason,
                        details=details,
                    )
                )
            return results

    def get_flagged_for_review(self, tenant_id: str) -> list[EvaluationResult]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(EvaluationResultRow).where(
                    EvaluationResultRow.tenant_id == tenant_id,
                    EvaluationResultRow.review_status == "FLAGGED_FOR_REVIEW",
                )
            ).all()

            results: list[EvaluationResult] = []
            for r in rows:
                ev_data = json.loads(r.evidence_json) if r.evidence_json else []
                evidence = [EvidenceItem(**item) for item in ev_data]
                details = json.loads(r.details_json) if r.details_json else {}

                results.append(
                    EvaluationResult(
                        tenant_id=r.tenant_id,
                        interaction_id=r.interaction_id,
                        evaluator_id=r.evaluator_id,
                        evaluator_version=r.evaluator_version,
                        family=r.family,
                        method=r.method,
                        label=r.label,
                        score=r.score,
                        confidence=r.confidence,
                        severity=r.severity,
                        review_status=r.review_status,
                        evidence=evidence,
                        reason=r.reason,
                        details=details,
                    )
                )
            return results

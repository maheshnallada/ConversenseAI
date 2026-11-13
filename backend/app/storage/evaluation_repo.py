import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.storage.orm import EvaluationResultRow


class EvaluationRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def save_results(
        self,
        tenant_id: str,
        interaction_id: str,
        results: list[EvaluationResult],
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            for r in results:
                # Remove existing row for this evaluator and version
                session.execute(
                    delete(EvaluationResultRow).where(
                        EvaluationResultRow.tenant_id == tenant_id,
                        EvaluationResultRow.interaction_id == interaction_id,
                        EvaluationResultRow.evaluator_id == r.evaluator_id,
                        EvaluationResultRow.evaluator_version == r.evaluator_version,
                    )
                )

                evidence_dicts = [asdict(e) for e in r.evidence]

                row = EvaluationResultRow(
                    tenant_id=tenant_id,
                    interaction_id=interaction_id,
                    evaluator_id=r.evaluator_id,
                    evaluator_version=r.evaluator_version,
                    family=r.family,
                    method=r.method,
                    label=r.label,
                    score=r.score,
                    confidence=r.confidence,
                    severity=r.severity,
                    review_status=r.review_status,
                    evidence_json=json.dumps(evidence_dicts),
                    reason=r.reason,
                    details_json=json.dumps(r.details),
                    created_at=now,
                )
                session.add(row)
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

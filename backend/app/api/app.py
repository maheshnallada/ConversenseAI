import os
from typing import Annotated, Optional, List, Dict, Any
from pathlib import Path
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain.envelope import InteractionEnvelope
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService
from app.evaluation.service import EvaluationService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.validation.golden_loader import load_golden_dataset
from app.validation.benchmark import BenchmarkEngine


class IngestResponse(BaseModel):
    created: bool
    interaction: InteractionEnvelope


class ProcessFolderRequest(BaseModel):
    call_folder_path: str
    tenant_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("TENANT_ID", "health_campaign")
    )


class ImportGoldenRequest(BaseModel):
    csv_path: Optional[str] = None


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="Conversense AI - Health Call Observability & Evaluation")
    app.state.session_factory = session_factory

    def get_ingest_service() -> IngestionService:
        return IngestionService(session_factory)

    def get_eval_service() -> EvaluationService:
        return EvaluationService(session_factory)

    def get_eval_repo() -> EvaluationRepository:
        return EvaluationRepository(session_factory)

    def get_golden_repo() -> GoldenDatasetRepository:
        return GoldenDatasetRepository(session_factory)

    def require_tenant_id(
        x_tenant_id: Annotated[str | None, Header()] = None,
    ) -> str:
        if x_tenant_id is None or not x_tenant_id.strip():
            raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
        return x_tenant_id

    @app.post("/api/v1/interactions", response_model=IngestResponse)
    def ingest_interaction(
        body: InteractionEnvelope,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if tenant_id != body.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant header does not match body")
        try:
            result: IngestResult = get_ingest_service().ingest(body)
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        status_code = 201 if result.created else 200
        payload = IngestResponse(created=result.created, interaction=result.interaction)
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    @app.get("/api/v1/interactions/{interaction_id}", response_model=InteractionEnvelope)
    def get_interaction(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        found = get_ingest_service().get(tenant_id, interaction_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Interaction not found")
        return found

    @app.post("/api/v1/interactions/{interaction_id}/evaluate")
    def evaluate_interaction(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        try:
            results = get_eval_service().evaluate_interaction(tenant_id, interaction_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return [
            {
                "tenant_id": r.tenant_id,
                "interaction_id": r.interaction_id,
                "evaluator_id": r.evaluator_id,
                "evaluator_version": r.evaluator_version,
                "family": r.family,
                "method": r.method,
                "label": r.label,
                "score": r.score,
                "confidence": r.confidence,
                "severity": r.severity,
                "review_status": r.review_status,
                "evidence": [asdict(e) for e in r.evidence],
                "reason": r.reason,
                "details": r.details,
            }
            for r in results
        ]

    @app.get("/api/v1/interactions/{interaction_id}/evaluations")
    def get_interaction_evaluations(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)
        results = get_eval_repo().get_by_interaction(tenant_id, resolved_id)

        return [
            {
                "tenant_id": r.tenant_id,
                "interaction_id": r.interaction_id,
                "evaluator_id": r.evaluator_id,
                "evaluator_version": r.evaluator_version,
                "family": r.family,
                "method": r.method,
                "label": r.label,
                "score": r.score,
                "confidence": r.confidence,
                "severity": r.severity,
                "review_status": r.review_status,
                "evidence": [asdict(e) for e in r.evidence],
                "reason": r.reason,
                "details": r.details,
            }
            for r in results
        ]

    @app.post("/api/v1/interactions/process-and-evaluate")
    def process_and_evaluate_folder(
        body: ProcessFolderRequest,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if "tenant_id" in body.model_fields_set and body.tenant_id and tenant_id != body.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant header does not match body")
        try:
            report = get_eval_service().process_and_evaluate_folder(
                call_folder_path=body.call_folder_path,
                tenant_id=tenant_id,
            )
            return report
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/golden-dataset")
    def list_golden_dataset(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        labels = get_golden_repo().get_all()
        return [asdict(label) for label in labels]

    @app.post("/api/v1/golden-dataset/import")
    def import_golden_dataset(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
        body: Optional[ImportGoldenRequest] = None,
    ):
        root = Path(__file__).resolve().parent.parent.parent.parent
        data_root = (root / "data").resolve()
        if body and body.csv_path:
            requested_path = Path(body.csv_path)
            csv_path = (
                requested_path if requested_path.is_absolute() else data_root / requested_path
            )
        else:
            csv_path = data_root / "golden_dataset.csv"
        csv_path = csv_path.resolve()
        if not csv_path.is_relative_to(data_root):
            raise HTTPException(
                status_code=400,
                detail="csv_path must resolve beneath the approved dataset directory",
            )
        try:
            labels = load_golden_dataset(csv_path)
            get_golden_repo().save_many(labels)
            return {"imported": len(labels), "path": str(csv_path)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/golden-dataset/benchmark")
    def get_golden_benchmark(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        golden_labels = get_golden_repo().get_all()
        if not golden_labels:
            raise HTTPException(status_code=404, detail="No golden dataset labels loaded.")

        evaluation_service = get_eval_service()
        evaluation_repo = get_eval_repo()
        evaluations_by_call = {}
        for label in golden_labels:
            resolved_id = evaluation_service.resolve_interaction_id(tenant_id, label.call_id)
            evaluations_by_call[label.call_id] = evaluation_repo.get_by_interaction(
                tenant_id, resolved_id
            )

        report = BenchmarkEngine().evaluate_benchmark(golden_labels, evaluations_by_call)
        return asdict(report)

    return app

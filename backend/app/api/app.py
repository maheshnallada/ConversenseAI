from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from app.analytics.service import AnalyticsService
from app.core.logging import TraceLoggingMiddleware, configure_logging, get_logger
from app.domain.envelope import ArtifactReference, InteractionEnvelope, InteractionEvent
from app.evaluation.service import EvaluationService
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService
from app.storage.artifact_reference_repo import (
    ArtifactReferenceConflict,
    ArtifactReferenceRepository,
)
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.event_repo import EventConflict, EventRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.interaction_errors import InteractionNotFound
from app.storage.orm import ArtifactRow
from app.storage.observability_repo import ObservabilityRepository
from app.storage.review_repo import HumanReviewRepository
from app.storage.transcript_repo import TranscriptRepository, TranscriptTurnConflict
from app.storage.timeline_repo import TimelineRepository
from app.validation.benchmark import BenchmarkEngine
from app.validation.golden_loader import load_golden_dataset

logger = get_logger("conversense.api")
class IngestResponse(BaseModel):
    created: bool
    interaction: InteractionEnvelope


class ImportGoldenRequest(BaseModel):
    csv_path: Optional[str] = None


class EvaluateInteractionRequest(BaseModel):
    retry_from_run_id: Optional[str] = None


class HumanReviewSubmission(BaseModel):
    evaluation_id: str
    reviewed_label: str
    reviewer_name: str
    review_decision: Literal["ACCEPTED", "OVERRIDDEN"] = "OVERRIDDEN"
    original_label: Optional[str] = None
    notes: Optional[str] = None


def create_app(session_factory) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Conversense AI - Health Call Observability & Evaluation")
    app.state.session_factory = session_factory
    app.add_middleware(TraceLoggingMiddleware)

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        @app.get("/dashboard")
        def serve_dashboard():
            return FileResponse(
                static_dir / "index.html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

    def get_ingest_service() -> IngestionService:
        return IngestionService(session_factory)

    def get_eval_service() -> EvaluationService:
        return EvaluationService(session_factory)

    def get_eval_repo() -> EvaluationRepository:
        return EvaluationRepository(session_factory)

    def get_golden_repo() -> GoldenDatasetRepository:
        return GoldenDatasetRepository(session_factory)

    def get_timeline_repo() -> TimelineRepository:
        return TimelineRepository(session_factory)

    def get_review_repo() -> HumanReviewRepository:
        return HumanReviewRepository(session_factory)

    def get_analytics_service() -> AnalyticsService:
        return AnalyticsService(session_factory)

    def require_tenant_id(
        x_tenant_id: Annotated[str | None, Header()] = None,
    ) -> str:
        if x_tenant_id is None or not x_tenant_id.strip():
            raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
        return x_tenant_id

    # Ingestion Endpoints
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

    @app.post("/api/v1/interactions/{interaction_id}/events")
    def append_interaction_event(
        interaction_id: str,
        body: InteractionEvent,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if get_ingest_service().get(tenant_id, interaction_id) is None:
            raise HTTPException(status_code=404, detail="Interaction not found")

        transcript_turn = None
        if body.event_type == "transcript.turn":
            try:
                transcript_turn = TranscriptRepository.event_turn(
                    tenant_id, interaction_id, body
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            created = EventRepository(session_factory).append(
                tenant_id,
                interaction_id,
                body,
                transcript_turn=transcript_turn,
            )
        except InteractionNotFound as exc:
            raise HTTPException(status_code=404, detail="Interaction not found") from exc
        except (EventConflict, TranscriptTurnConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        response = {
            "created": created,
            "event": body.model_dump(mode="json"),
        }
        return JSONResponse(
            status_code=201 if created else 200,
            content=response,
        )

    @app.post("/api/v1/interactions/{interaction_id}/artifacts")
    def register_interaction_artifact(
        interaction_id: str,
        body: ArtifactReference,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if get_ingest_service().get(tenant_id, interaction_id) is None:
            raise HTTPException(status_code=404, detail="Interaction not found")

        try:
            created = ArtifactReferenceRepository(session_factory).register(
                tenant_id, interaction_id, body
            )
        except InteractionNotFound as exc:
            raise HTTPException(status_code=404, detail="Interaction not found") from exc
        except ArtifactReferenceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        response = {
            "created": created,
            "artifact": body.model_dump(mode="json"),
        }
        return JSONResponse(
            status_code=201 if created else 200,
            content=response,
        )

    # Interaction List (Paginated & Filterable)
    @app.get("/api/v1/interactions")
    def list_interactions(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: Optional[str] = Query(default=None),
        outcome: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
        started_after: Optional[datetime] = Query(default=None),
        started_before: Optional[datetime] = Query(default=None),
        use_case: Optional[str] = Query(default=None),
        error_state: Optional[Literal["has_errors", "no_errors"]] = Query(default=None),
    ):
        return get_analytics_service().get_interactions_page(
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            outcome=outcome,
            search=search,
            started_after=started_after,
            started_before=started_before,
            use_case=use_case,
            error_state=error_state,
        )

    @app.get("/api/v1/interactions/{interaction_id}", response_model=InteractionEnvelope)
    def get_interaction(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        found = get_ingest_service().get(tenant_id, interaction_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Interaction not found")
        return found

    @app.get("/api/v1/interactions/{interaction_id}/observability")
    def get_interaction_observability(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if get_ingest_service().get(tenant_id, interaction_id) is None:
            raise HTTPException(status_code=404, detail="Interaction not found")
        metrics = ObservabilityRepository(session_factory).get_metrics(
            tenant_id, interaction_id
        )
        return {
            "interaction_id": interaction_id,
            "available": metrics is not None,
            "metrics": asdict(metrics) if metrics is not None else None,
        }

    # Reconstructed Timeline Endpoint
    @app.get("/api/v1/interactions/{interaction_id}/timeline")
    def get_interaction_timeline(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        timeline = get_timeline_repo().get_timeline(tenant_id, interaction_id)
        if not timeline:
            raise HTTPException(status_code=404, detail="Timeline not found for interaction")
        return asdict(timeline)

    # Audio Streaming Endpoint
    @app.get("/api/v1/interactions/{interaction_id}/audio")
    def get_interaction_audio(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        target_wav: Optional[Path] = None

        # 1. Database artifact lookup
        with session_factory() as session:
            art_row = session.scalar(
                select(ArtifactRow).where(
                    ArtifactRow.tenant_id == tenant_id,
                    ArtifactRow.interaction_id == interaction_id,
                    ArtifactRow.artifact_type.in_(["recording", "audio_recording"]),
                ).limit(1)
            )
            if art_row and art_row.uri:
                parsed = urlparse(art_row.uri)
                p_str = unquote(parsed.path)
                if p_str.startswith("/") and ":" in p_str:
                    p_str = p_str.lstrip("/")
                candidate = Path(p_str)
                if candidate.exists():
                    target_wav = candidate

        if not target_wav or not target_wav.exists():
            raise HTTPException(status_code=404, detail="Recording audio not found")

        return FileResponse(target_wav, media_type="audio/wav")

    # Evaluations Endpoints
    @app.post("/api/v1/interactions/{interaction_id}/evaluate")
    def evaluate_interaction(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
        body: EvaluateInteractionRequest | None = None,
    ):
        try:
            run = get_eval_service().evaluate_interaction(
                tenant_id,
                interaction_id,
                retry_from_run_id=body.retry_from_run_id if body else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        return asdict(run)

    @app.get("/api/v1/interactions/{interaction_id}/evaluations")
    def get_interaction_evaluations(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        run = get_eval_repo().get_latest_run(tenant_id, interaction_id)
        return asdict(run) if run is not None else None

    # Human Review Endpoints
    @app.post("/api/v1/interactions/{interaction_id}/reviews")
    def submit_interaction_review(
        interaction_id: str,
        body: HumanReviewSubmission,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        try:
            return get_review_repo().submit_review(
                tenant_id=tenant_id,
                interaction_id=interaction_id,
                evaluation_id=body.evaluation_id,
                reviewed_label=body.reviewed_label,
                reviewer_name=body.reviewer_name,
                review_decision=body.review_decision,
                original_label=body.original_label,
                notes=body.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/interactions/{interaction_id}/reviews")
    def list_interaction_reviews(
        interaction_id: str,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_review_repo().get_reviews_for_interaction(tenant_id, interaction_id)

    # Analytics Endpoints
    @app.get("/api/v1/analytics/overview")
    def get_overview_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_overview_analytics(tenant_id)

    @app.get("/api/v1/analytics/reliability")
    def get_reliability_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_reliability_analytics(tenant_id)

    @app.get("/api/v1/analytics/usage")
    def get_usage_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_usage_analytics(tenant_id)

    # Golden Dataset Routes
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
        golden_repo = get_golden_repo()
        eval_repo = get_eval_repo()

        golden_labels = [l for l in golden_repo.get_all() if not l.call_id.startswith("call_test_")]
        if not golden_labels:
            candidate_paths = [
                Path("data/golden_dataset.csv"),
                Path(__file__).resolve().parent.parent.parent.parent / "data" / "golden_dataset.csv",
                Path(__file__).resolve().parent.parent.parent / "data" / "golden_dataset.csv",
                Path("/app/data/golden_dataset.csv"),
            ]
            for p in candidate_paths:
                if p.exists():
                    try:
                        imported = load_golden_dataset(p)
                        golden_repo.save_many(imported)
                        golden_labels = [l for l in golden_repo.get_all() if not l.call_id.startswith("call_test_")]
                        break
                    except Exception as e:
                        logger.warning(f"Failed to auto-import golden dataset from {p}: {e}")

        if not golden_labels:
            raise HTTPException(status_code=404, detail="No golden dataset labels loaded.")

        evaluations_by_call = {}
        for g in golden_labels:
            interaction_id = g.interaction_id or g.call_id
            evaluations_by_call[g.call_id] = eval_repo.get_latest_run(
                tenant_id,
                interaction_id,
            )

        engine = BenchmarkEngine()
        report = engine.evaluate_benchmark(golden_labels, evaluations_by_call)

        return asdict(report)

    return app

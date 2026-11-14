from typing import Annotated, Optional, List, Dict, Any
from pathlib import Path
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, Query, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.domain.envelope import InteractionEnvelope
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService
from app.evaluation.service import EvaluationService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.timeline_repo import TimelineRepository
from app.storage.review_repo import HumanReviewRepository
from app.validation.golden_loader import load_golden_dataset
from app.validation.benchmark import BenchmarkEngine
from app.analytics.service import AnalyticsService


class IngestResponse(BaseModel):
    created: bool
    interaction: InteractionEnvelope


class ProcessFolderRequest(BaseModel):
    call_folder_path: str
    tenant_id: Optional[str] = "health_campaign"


class ImportGoldenRequest(BaseModel):
    csv_path: Optional[str] = None


class HumanReviewSubmission(BaseModel):
    evaluator_id: str
    reviewed_label: str
    reviewer_name: str
    review_decision: Optional[str] = "OVERRIDDEN"  # ACCEPTED or OVERRIDDEN
    original_label: Optional[str] = None
    notes: Optional[str] = None


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="Conversense AI - Health Call Observability & Evaluation")
    app.state.session_factory = session_factory

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        @app.get("/dashboard")
        def serve_dashboard():
            return FileResponse(static_dir / "index.html")

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

    # Ingestion Endpoints
    @app.post("/api/v1/interactions", response_model=IngestResponse)
    def ingest_interaction(
        body: InteractionEnvelope,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        if not x_tenant_id:
            raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
        if x_tenant_id != body.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant header does not match body")
        try:
            result: IngestResult = get_ingest_service().ingest(body)
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        status_code = 201 if result.created else 200
        payload = IngestResponse(created=result.created, interaction=result.interaction)
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    # Interaction List (Paginated & Filterable)
    @app.get("/api/v1/interactions")
    def list_interactions(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: Optional[str] = Query(default=None),
        outcome: Optional[str] = Query(default=None),
        quality: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        return get_analytics_service().get_interactions_page(
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
            status=status,
            outcome=outcome,
            quality=quality,
            search=search,
        )

    @app.get("/api/v1/interactions/{interaction_id}", response_model=InteractionEnvelope)
    def get_interaction(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)
        found = get_ingest_service().get(tenant_id, resolved_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Interaction not found")
        return found

    # Reconstructed Timeline Endpoint
    @app.get("/api/v1/interactions/{interaction_id}/timeline")
    def get_interaction_timeline(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)
        timeline = get_timeline_repo().get_timeline(tenant_id, resolved_id)
        if not timeline:
            raise HTTPException(status_code=404, detail="Timeline not found for interaction")
        return asdict(timeline)

    # Audio Streaming Endpoint
    @app.get("/api/v1/interactions/{interaction_id}/audio")
    def get_interaction_audio(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        root = Path(__file__).resolve().parent.parent.parent.parent
        calls_dir = root / "data" / "calls"

        # Check if direct folder name or search by UUID inside call.json
        target_wav: Optional[Path] = None
        if (calls_dir / interaction_id / "recording.wav").exists():
            target_wav = calls_dir / interaction_id / "recording.wav"
        else:
            for folder in calls_dir.iterdir():
                if folder.is_dir() and (folder / "recording.wav").exists():
                    c_json = folder / "call.json"
                    if c_json.exists():
                        try:
                            import json
                            with open(c_json, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                if data.get("call_id") == interaction_id:
                                    target_wav = folder / "recording.wav"
                                    break
                        except Exception:
                            pass

        if not target_wav or not target_wav.exists():
            raise HTTPException(status_code=404, detail="Recording audio not found")

        return FileResponse(target_wav, media_type="audio/wav")

    # Evaluations Endpoints
    @app.post("/api/v1/interactions/{interaction_id}/evaluate")
    def evaluate_interaction(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
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
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
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

    # Human Review Endpoints
    @app.post("/api/v1/interactions/{interaction_id}/reviews")
    def submit_interaction_review(
        interaction_id: str,
        body: HumanReviewSubmission,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)

        review = get_review_repo().submit_review(
            tenant_id=tenant_id,
            interaction_id=resolved_id,
            evaluator_id=body.evaluator_id,
            reviewed_label=body.reviewed_label,
            reviewer_name=body.reviewer_name,
            review_decision=body.review_decision or "OVERRIDDEN",
            original_label=body.original_label,
            notes=body.notes,
        )
        return review

    @app.get("/api/v1/interactions/{interaction_id}/reviews")
    def list_interaction_reviews(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)
        return get_review_repo().get_reviews_for_interaction(tenant_id, resolved_id)

    # Analytics Endpoints
    @app.get("/api/v1/analytics/overview")
    def get_overview_analytics(
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        return get_analytics_service().get_overview_analytics(tenant_id)

    @app.get("/api/v1/analytics/quality")
    def get_quality_analytics(
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        return get_analytics_service().get_quality_analytics(tenant_id)

    @app.get("/api/v1/analytics/cost")
    def get_cost_analytics(
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or "health_campaign"
        return get_analytics_service().get_cost_analytics(tenant_id)

    # Use Cases & Evaluator Registry Endpoints
    @app.get("/api/v1/use-cases")
    def list_use_cases():
        return [
            {
                "id": "health_insurance",
                "name": "Health Insurance Consultation",
                "domain": "Insurance & Healthcare",
                "description": "Voice consultant outbound campaign for policy review and expert callbacks.",
                "version": "1.0.0",
                "active_evaluators": 5,
            }
        ]

    @app.get("/api/v1/evaluators")
    def list_evaluators():
        return [
            {"evaluator_id": "compliance.never_rules", "family": "compliance", "version": "1.0.0", "description": "Deterministic safety rules enforcement (PAN, Aadhaar, quotes, AI denial)"},
            {"evaluator_id": "outcome.intent", "family": "outcome", "version": "1.0.0", "description": "Final customer intent and call progression classification"},
            {"evaluator_id": "experience.sentiment_emotion", "family": "experience", "version": "1.0.0", "description": "Customer sentiment and emotional tone analysis"},
            {"evaluator_id": "quality.scorecard", "family": "quality", "version": "1.0.0", "description": "Overall conversation quality scorecard and first issue identification"},
            {"evaluator_id": "facts.extraction", "family": "facts", "version": "1.0.0", "description": "Structured customer stated facts extraction (policy, city, cover)"},
        ]

    # Process and Evaluate Uploaded Call Folder
    @app.post("/api/v1/interactions/process-and-evaluate")
    def process_and_evaluate_folder(
        body: ProcessFolderRequest,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        tenant_id = x_tenant_id or body.tenant_id or "health_campaign"
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

    # Golden Dataset Routes
    @app.get("/api/v1/golden-dataset")
    def list_golden_dataset():
        labels = get_golden_repo().get_all()
        return [asdict(l) for l in labels]

    @app.post("/api/v1/golden-dataset/import")
    def import_golden_dataset(body: Optional[ImportGoldenRequest] = None):
        root = Path(__file__).resolve().parent.parent.parent.parent
        csv_path = body.csv_path if (body and body.csv_path) else str(root / "data" / "golden_dataset.csv")
        try:
            labels = load_golden_dataset(csv_path)
            get_golden_repo().save_many(labels)
            return {"imported": len(labels), "path": csv_path}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/golden-dataset/benchmark")
    def get_golden_benchmark(tenant_id: str = "health_campaign"):
        golden_repo = get_golden_repo()
        eval_service = get_eval_service()
        eval_repo = get_eval_repo()

        golden_labels = [l for l in golden_repo.get_all() if not l.call_id.startswith("call_test_")]
        if not golden_labels:
            raise HTTPException(status_code=404, detail="No golden dataset labels loaded.")

        evaluations_by_call: Dict[str, list] = {}
        for g in golden_labels:
            resolved_id = eval_service.resolve_interaction_id(tenant_id, g.call_id)
            evals = eval_repo.get_by_interaction(tenant_id, resolved_id)
            evaluations_by_call[g.call_id] = evals

        engine = BenchmarkEngine()
        report = engine.evaluate_benchmark(golden_labels, evaluations_by_call)

        return asdict(report)

    return app

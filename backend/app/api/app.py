import base64
import io
import json
import os
import re
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.analytics.service import AnalyticsService
from app.core.logging import TraceLoggingMiddleware, configure_logging, get_logger
from app.domain.envelope import InteractionEnvelope
from app.evaluation.service import EvaluationService
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.storage.orm import ArtifactRow
from app.storage.review_repo import HumanReviewRepository
from app.storage.timeline_repo import TimelineRepository
from app.validation.benchmark import BenchmarkEngine
from app.validation.golden_loader import load_golden_dataset

logger = get_logger("conversense.api")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = (REPOSITORY_ROOT / "backend" / "storage" / "uploads").resolve()
_SAFE_FOLDER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _create_upload_staging_dir(tenant_id: str, folder_name: str | None = None) -> Path:
    if folder_name is not None and not _SAFE_FOLDER_NAME.fullmatch(folder_name):
        raise HTTPException(
            status_code=400,
            detail="folder_name must be a single safe directory name",
        )

    tenant_root = (UPLOAD_ROOT / tenant_id).resolve()
    staging_dir = (tenant_root / (folder_name or f"upload_{uuid.uuid4().hex[:12]}")).resolve()
    if not tenant_root.is_relative_to(UPLOAD_ROOT) or not staging_dir.is_relative_to(tenant_root):
        raise HTTPException(status_code=400, detail="Invalid upload staging directory")
    try:
        staging_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Upload folder already exists") from exc
    return staging_dir


class IngestResponse(BaseModel):
    created: bool
    interaction: InteractionEnvelope


class ProcessFolderRequest(BaseModel):
    call_folder_path: str
    tenant_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("TENANT_ID", "health_campaign")
    )


class UploadFilesRequest(BaseModel):
    call_json: str
    manifest_jsonl: Optional[str] = None
    agent_manifest_jsonl: Optional[str] = None
    call_log: Optional[str] = None
    recording_base64: Optional[str] = None
    folder_name: Optional[str] = None
    tenant_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("TENANT_ID", "health_campaign")
    )


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

    # Selector List (For dynamic dropdown population)
    @app.get("/api/v1/interactions-list")
    def list_interactions_selector(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_interactions_selector_list(tenant_id)

    # Interaction List (Paginated & Filterable)
    @app.get("/api/v1/interactions")
    def list_interactions(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        status: Optional[str] = Query(default=None),
        outcome: Optional[str] = Query(default=None),
        quality: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
    ):
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
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
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
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
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
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)

        target_wav: Optional[Path] = None

        # 1. Database artifact lookup
        with session_factory() as session:
            art_row = session.scalar(
                select(ArtifactRow).where(
                    ArtifactRow.tenant_id == tenant_id,
                    ArtifactRow.interaction_id == resolved_id,
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

        # 2. Filesystem search fallback
        if not target_wav or not target_wav.exists():
            candidate_roots = [
                Path("data/calls"),
                Path(__file__).resolve().parent.parent.parent.parent / "data" / "calls",
                Path(__file__).resolve().parent.parent.parent / "data" / "calls",
                Path("/app/data/calls"),
                Path("backend/storage/artifacts") / tenant_id,
                Path("/app/storage/artifacts") / tenant_id,
            ]
            for root_dir in candidate_roots:
                if not root_dir.exists():
                    continue

                for folder_cand in [interaction_id, resolved_id]:
                    direct = root_dir / folder_cand / "recording.wav"
                    if direct.exists():
                        target_wav = direct
                        break
                if target_wav:
                    break

                for folder in root_dir.iterdir():
                    if folder.is_dir() and (folder / "recording.wav").exists():
                        c_json = folder / "call.json"
                        if c_json.exists():
                            try:
                                with open(c_json, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                    if data.get("call_id") in [interaction_id, resolved_id]:
                                        target_wav = folder / "recording.wav"
                                        break
                            except Exception:
                                pass
                if target_wav:
                    break

        if not target_wav or not target_wav.exists():
            raise HTTPException(status_code=404, detail="Recording audio not found")

        return FileResponse(target_wav, media_type="audio/wav")

    # Evaluations Endpoints
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

    # Human Review Endpoints
    @app.post("/api/v1/interactions/{interaction_id}/reviews")
    def submit_interaction_review(
        interaction_id: str,
        body: HumanReviewSubmission,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
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
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        service = get_eval_service()
        resolved_id = service.resolve_interaction_id(tenant_id, interaction_id)
        return get_review_repo().get_reviews_for_interaction(tenant_id, resolved_id)

    # Analytics Endpoints
    @app.get("/api/v1/analytics/overview")
    def get_overview_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_overview_analytics(tenant_id)

    @app.get("/api/v1/analytics/quality")
    def get_quality_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        return get_analytics_service().get_quality_analytics(tenant_id)

    @app.get("/api/v1/analytics/cost")
    def get_cost_analytics(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
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

    # Process and Evaluate Folder Endpoint
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
            logger.error(f"Error processing folder: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Ingestion Flow: Binary ZIP Upload Endpoint
    @app.post("/api/v1/interactions/upload-zip")
    async def upload_call_zip(
        request: Request,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty request body. Please upload a ZIP archive.")

        staging_dir = _create_upload_staging_dir(tenant_id)

        try:
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                zf.extractall(staging_dir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail=f"Invalid ZIP archive: {exc}")

        # Locate folder containing call.json
        target_dir = staging_dir
        if not (target_dir / "call.json").exists():
            for sub in staging_dir.rglob("call.json"):
                target_dir = sub.parent
                break

        if not (target_dir / "call.json").exists():
            raise HTTPException(
                status_code=400,
                detail="Uploaded archive must contain 'call.json' metadata file.",
            )

        try:
            report = get_eval_service().process_and_evaluate_folder(
                call_folder_path=target_dir,
                tenant_id=tenant_id,
            )
            return {
                "success": True,
                "message": "Call uploaded, processed, and evaluated successfully.",
                "report": report,
            }
        except Exception as exc:
            logger.error(f"Error in upload-zip: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed processing call: {exc}")

    # Ingestion Flow: Multipart/Files JSON Endpoint
    @app.post("/api/v1/interactions/upload-files")
    def upload_call_files(
        body: UploadFilesRequest,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if (
            "tenant_id" in body.model_fields_set
            and body.tenant_id
            and tenant_id != body.tenant_id
        ):
            raise HTTPException(status_code=403, detail="Tenant header does not match body")
        staging_dir = _create_upload_staging_dir(tenant_id, body.folder_name)

        (staging_dir / "call.json").write_text(body.call_json, encoding="utf-8")

        if body.manifest_jsonl:
            (staging_dir / "manifest.jsonl").write_text(body.manifest_jsonl, encoding="utf-8")
        if body.agent_manifest_jsonl:
            (staging_dir / "agent_manifest.jsonl").write_text(body.agent_manifest_jsonl, encoding="utf-8")
        if body.call_log:
            (staging_dir / "call.log").write_text(body.call_log, encoding="utf-8")
        if body.recording_base64:
            audio_bytes = base64.b64decode(body.recording_base64)
            (staging_dir / "recording.wav").write_bytes(audio_bytes)

        try:
            report = get_eval_service().process_and_evaluate_folder(
                call_folder_path=staging_dir,
                tenant_id=tenant_id,
            )
            return {
                "success": True,
                "message": "Call files uploaded, processed, and evaluated successfully.",
                "report": report,
            }
        except Exception as exc:
            logger.error(f"Error in upload-files: {exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed processing call: {exc}")

    # Seed Dataset Route (Populates calls if running on fresh DB)
    @app.post("/api/v1/interactions/seed-all")
    def seed_all_calls(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
        limit: Optional[int] = Query(default=50, ge=1, le=50),
    ):
        service = get_eval_service()

        repo_root = Path(__file__).resolve().parents[3]
        calls_dirs = [
            Path("/app/data/calls"),
            repo_root / "data" / "calls",
            get_eval_service().artifact_store.base_dir / tenant_id,
        ]
        target_dir = None
        for d in calls_dirs:
            if d.exists() and d.is_dir():
                target_dir = d
                break

        if not target_dir:
            raise HTTPException(status_code=404, detail="Calls dataset directory not found on server.")

        folders = sorted([f for f in target_dir.iterdir() if f.is_dir() and (f / "call.json").exists()])[:limit]
        processed = []
        for folder in folders:
            try:
                rep = service.process_and_evaluate_folder(folder, tenant_id=tenant_id)
                processed.append(rep["interaction_id"])
            except Exception as e:
                logger.error(f"Failed seeding {folder.name}: {e}")

        return {
            "success": True,
            "seeded_count": len(processed),
            "interactions": processed,
        }

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
        eval_service = get_eval_service()
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

        evaluations_by_call: Dict[str, list] = {}
        for g in golden_labels:
            resolved_id = eval_service.resolve_interaction_id(tenant_id, g.call_id)
            evals = eval_repo.get_by_interaction(tenant_id, resolved_id)
            evaluations_by_call[g.call_id] = evals

        engine = BenchmarkEngine()
        report = engine.evaluate_benchmark(golden_labels, evaluations_by_call)

        return asdict(report)

    return app

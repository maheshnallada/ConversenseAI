import hashlib
import os
import re
import tempfile
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.analytics.service import AnalyticsService
from app.core.logging import TraceLoggingMiddleware, configure_logging, get_logger
from app.domain.envelope import ArtifactReference, InteractionEnvelope, InteractionEvent
from app.evaluation.service import EvaluationService
from app.ingestion.api_models import (
    CallImportBatchResponse,
    CallImportResultResponse,
    StagedCallImportRequest,
    StagedCallListResponse,
    StagedCallSummary,
)
from app.ingestion.call_importer import CallFolderImporter, CallImportResult
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService
from app.storage.artifact_reference_repo import (
    ArtifactReferenceConflict,
    ArtifactReferenceRepository,
)
from app.storage.artifacts import ArtifactStore, LocalArtifactStore
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

MAX_CALLS_PER_IMPORT = 100
MAX_FILES_PER_CALL = 200
MAX_FILES_PER_REQUEST = 10_000
MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024
MAX_REQUEST_SIZE_BYTES = 5 * 1024 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _validate_import_limits(file_sizes_by_call: list[list[int]]) -> None:
    error = _import_limit_error(file_sizes_by_call)
    if error:
        raise HTTPException(status_code=413, detail=error)


def _import_limit_error(file_sizes_by_call: list[list[int]]) -> str | None:
    if len(file_sizes_by_call) > MAX_CALLS_PER_IMPORT:
        return f"An import may contain at most {MAX_CALLS_PER_IMPORT} calls."
    if any(len(sizes) > MAX_FILES_PER_CALL for sizes in file_sizes_by_call):
        return f"A call may contain at most {MAX_FILES_PER_CALL} files."
    if sum(len(sizes) for sizes in file_sizes_by_call) > MAX_FILES_PER_REQUEST:
        return f"An import may contain at most {MAX_FILES_PER_REQUEST} files."
    if any(
        size < 0 or size > MAX_FILE_SIZE_BYTES
        for sizes in file_sizes_by_call
        for size in sizes
    ):
        return f"Each file must be at most {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MiB."
    if sum(sum(sizes) for sizes in file_sizes_by_call) > MAX_REQUEST_SIZE_BYTES:
        return f"An import may contain at most {MAX_REQUEST_SIZE_BYTES // (1024 * 1024 * 1024)} GiB."
    return None


def _tenant_staging_root(artifact_store: ArtifactStore, tenant_id: str) -> Path:
    if (
        not tenant_id
        or tenant_id in {".", ".."}
        or any(separator in tenant_id for separator in ("/", "\\", ":", "\x00"))
    ):
        raise HTTPException(status_code=400, detail="Invalid tenant identifier")

    base_dir = artifact_store.base_dir.resolve()
    tenant_candidate = base_dir / tenant_id
    if tenant_candidate.is_symlink():
        raise HTTPException(status_code=400, detail="Invalid staged folder location")
    tenant_root = tenant_candidate.resolve()
    if tenant_root.parent != base_dir:
        raise HTTPException(status_code=400, detail="Invalid staged folder location")
    return tenant_root


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())


def _scan_staged_folder(folder: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []
    pending = [folder]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if _is_link_or_junction(path):
                        errors.append("Symbolic links are not allowed in staged calls.")
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(path)
                    else:
                        errors.append("Staged calls may contain only regular files and folders.")
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail="A staged folder could not be safely inspected.",
            ) from exc
    return files, errors


def _safe_validation_errors(folder: Path) -> list[str]:
    from app.validation.audio import validate_call_files

    validation = validate_call_files(folder)
    folder_path = str(folder.resolve())
    return [
        message.replace(folder_path, folder.name)
        for message in validation.errors
    ]


def _staged_folder_id(tenant_id: str, folder_name: str) -> str:
    digest = hashlib.sha256(
        f"conversense-staged-folder\0{tenant_id}\0{folder_name}".encode("utf-8")
    ).hexdigest()
    return digest[:32]


def _list_staged_folders(
    artifact_store: ArtifactStore,
    tenant_id: str,
) -> tuple[Path, list[tuple[Path, StagedCallSummary, list[int], bool]]]:
    tenant_root = _tenant_staging_root(artifact_store, tenant_id)
    if not tenant_root.exists():
        return tenant_root, []

    folders: list[tuple[Path, StagedCallSummary, list[int], bool]] = []
    try:
        with os.scandir(tenant_root) as entries:
            candidates = sorted(entries, key=lambda entry: entry.name.casefold())
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail="Staged calls could not be safely listed.",
        ) from exc

    for entry in candidates:
        folder = Path(entry.path)
        if _is_link_or_junction(folder) or not entry.is_dir(follow_symlinks=False):
            continue
        resolved_folder = folder.resolve()
        if resolved_folder.parent != tenant_root:
            continue
        files, scan_errors = _scan_staged_folder(resolved_folder)
        sizes = [path.stat().st_size for path in files]
        validation_errors = list(scan_errors)
        if not scan_errors:
            validation_errors.extend(_safe_validation_errors(resolved_folder))
        if len(files) > MAX_FILES_PER_CALL:
            validation_errors.append(
                f"A call may contain at most {MAX_FILES_PER_CALL} files."
            )
        if any(size > MAX_FILE_SIZE_BYTES for size in sizes):
            validation_errors.append(
                f"Each file must be at most {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MiB."
            )
        summary = StagedCallSummary(
            folder_id=_staged_folder_id(tenant_id, entry.name),
            display_name=entry.name,
            is_ready=not validation_errors,
            validation_errors=validation_errors,
        )
        folders.append((resolved_folder, summary, sizes, bool(scan_errors)))
    return tenant_root, folders


def _batch_response(results: list[CallImportResult]) -> CallImportBatchResponse:
    return CallImportBatchResponse(
        total_calls=len(results),
        created=sum(result.status == "created" for result in results),
        replayed=sum(result.status == "replayed" for result in results),
        failed=sum(result.status not in {"created", "replayed"} for result in results),
        calls=[
            CallImportResultResponse.model_validate(asdict(result))
            for result in results
        ],
    )


def _normalize_upload_filename(filename: str | None) -> tuple[str, ...]:
    if not filename or "\x00" in filename:
        raise HTTPException(
            status_code=400,
            detail="Each uploaded file needs a safe relative path.",
        )
    normalized = filename.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise HTTPException(status_code=400, detail="Rooted upload paths are not allowed.")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="Unsafe upload path.")
    return tuple(parts)


def _group_upload_paths(
    file_paths: list[tuple[str, ...]],
) -> dict[tuple[str, ...], list[tuple[str, ...]]]:
    parent_paths = [path[:-1] for path in file_paths]
    common_parent: list[str] = []
    for parts in zip(*parent_paths):
        if len({part.casefold() for part in parts}) != 1:
            break
        common_parent.append(parts[0])

    common_tuple = tuple(common_parent)
    if all(parent == common_tuple for parent in parent_paths) or any(
        parent == common_tuple for parent in parent_paths
    ):
        root = common_tuple
        return {root: file_paths}

    groups: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
    for path, parent in zip(file_paths, parent_paths):
        if len(parent) > len(common_tuple):
            root = common_tuple + (parent[len(common_tuple)],)
        else:
            root = common_tuple
        groups.setdefault(root, []).append(path)
    return groups


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


def create_app(
    session_factory,
    artifact_store: ArtifactStore | None = None,
) -> FastAPI:
    configure_logging()
    app = FastAPI(title="Conversense AI - Health Call Observability & Evaluation")
    app.state.session_factory = session_factory
    app.state.artifact_store = artifact_store or LocalArtifactStore()
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

    def get_call_importer() -> CallFolderImporter:
        return CallFolderImporter(session_factory, app.state.artifact_store)

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

    @app.get(
        "/api/v1/imports/staged-calls",
        response_model=StagedCallListResponse,
    )
    def list_staged_calls(
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        _, folders = _list_staged_folders(app.state.artifact_store, tenant_id)
        return StagedCallListResponse(calls=[summary for _, summary, _, _ in folders])

    @app.post(
        "/api/v1/imports/staged-calls",
        response_model=CallImportBatchResponse,
    )
    def import_staged_calls(
        body: StagedCallImportRequest,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        if len(set(body.folder_ids)) != len(body.folder_ids):
            raise HTTPException(
                status_code=400,
                detail="Duplicate staged folder IDs are not allowed.",
            )
        _, available_folders = _list_staged_folders(app.state.artifact_store, tenant_id)
        folders_by_id = {
            summary.folder_id: (folder, sizes, unsafe)
            for folder, summary, sizes, unsafe in available_folders
        }
        selected = []
        for folder_id in body.folder_ids:
            selected_folder = folders_by_id.get(folder_id)
            if selected_folder is None:
                raise HTTPException(status_code=404, detail="Staged folder not found.")
            selected.append(selected_folder)

        if any(unsafe for _, _, unsafe in selected):
            raise HTTPException(status_code=400, detail="A staged folder contains an unsafe entry.")
        _validate_import_limits([sizes for _, sizes, _ in selected])

        importer = get_call_importer()
        results = [
            importer.import_call(folder, tenant_id)
            for folder, _, _ in selected
        ]
        return _batch_response(results)

    @app.post(
        "/api/v1/imports/upload-calls",
        response_model=CallImportBatchResponse,
    )
    async def upload_call_folders(
        request: Request,
        tenant_id: Annotated[str, Depends(require_tenant_id)],
    ):
        try:
            form = await request.form(
                max_files=MAX_FILES_PER_REQUEST + 1,
                max_fields=0,
            )
        except HTTPException as exc:
            if "Too many files" in str(exc.detail):
                raise HTTPException(
                    status_code=413,
                    detail=f"An import may contain at most {MAX_FILES_PER_REQUEST} files.",
                ) from exc
            raise

        files: list[UploadFile] = []
        normalized_paths: list[tuple[str, ...]] = []
        try:
            for field_name, value in form.multi_items():
                if field_name != "files" or not isinstance(value, UploadFile):
                    raise HTTPException(
                        status_code=400,
                        detail="Only uploaded files are accepted.",
                    )
                files.append(value)
            if not files:
                raise HTTPException(status_code=400, detail="At least one file is required.")
            if len(files) > MAX_FILES_PER_REQUEST:
                raise HTTPException(
                    status_code=413,
                    detail=f"An import may contain at most {MAX_FILES_PER_REQUEST} files.",
                )

            for upload in files:
                normalized_paths.append(_normalize_upload_filename(upload.filename))
            path_keys = [tuple(part.casefold() for part in path) for path in normalized_paths]
            if len(set(path_keys)) != len(path_keys):
                raise HTTPException(
                    status_code=400,
                    detail="Duplicate upload paths are not allowed.",
                )

            grouped_paths = _group_upload_paths(normalized_paths)
            _validate_import_limits(
                [[0] * len(paths) for paths in grouped_paths.values()]
            )

            importer = get_call_importer()
            results: list[CallImportResult] = []
            total_bytes = 0
            with tempfile.TemporaryDirectory(prefix="conversense-call-upload-") as temp_dir:
                temp_root = Path(temp_dir)
                staged_folders: list[tuple[Path, str, list[int]]] = []
                group_indexes = {
                    path: index for index, path in enumerate(grouped_paths)
                }
                file_sizes: dict[tuple[str, ...], list[int]] = {
                    path: [] for path in grouped_paths
                }
                for upload, relative_path in zip(files, normalized_paths):
                    group_path = next(
                        root
                        for root, group_files in grouped_paths.items()
                        if relative_path in group_files
                    )
                    group_index = group_indexes[group_path]
                    call_dir = temp_root / f"call-{group_index}"
                    relative_to_call = (
                        relative_path[len(group_path):]
                        if group_path
                        else relative_path
                    )
                    destination = call_dir.joinpath(*relative_to_call)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    size = 0
                    try:
                        with destination.open("xb") as output:
                            while True:
                                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                                if not chunk:
                                    break
                                size += len(chunk)
                                total_bytes += len(chunk)
                                if size > MAX_FILE_SIZE_BYTES:
                                    raise HTTPException(
                                        status_code=413,
                                        detail="Each file must be at most 512 MiB.",
                                    )
                                if total_bytes > MAX_REQUEST_SIZE_BYTES:
                                    raise HTTPException(
                                        status_code=413,
                                        detail="An import may contain at most 5 GiB.",
                                    )
                                output.write(chunk)
                    except OSError as exc:
                        raise HTTPException(
                            status_code=400,
                            detail="An uploaded file could not be staged safely.",
                        ) from exc
                    file_sizes[group_path].append(size)
                _validate_import_limits(list(file_sizes.values()))

                for group_path, index in group_indexes.items():
                    display_name = group_path[-1] if group_path else "Uploaded call"
                    staged_folders.append(
                        (temp_root / f"call-{index}", display_name, file_sizes[group_path])
                    )
                for folder, display_name, _ in staged_folders:
                    result = await run_in_threadpool(
                        importer.import_call,
                        folder,
                        tenant_id,
                    )
                    results.append(replace(result, folder_name=display_name))
            return _batch_response(results)
        finally:
            await form.close()

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

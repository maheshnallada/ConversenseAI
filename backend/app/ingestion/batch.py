import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.ingestion.mapper import map_call_folder
from app.ingestion.service import IngestionService
from app.reconstruction.processor import TranscriptProcessor
from app.storage.artifacts import ArtifactStore
from app.storage.orm import ArtifactRow, ImportRunRow
from app.storage.transcript_repo import TranscriptRepository


@dataclass
class CallImportSummary:
    folder: str
    call_id: str | None = None
    created: bool = False
    status: str | None = None
    files_count: int = 0
    has_agent_manifest: bool = False
    is_silent: bool = False
    phone_answered: bool = False
    error: str | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class BatchImportResult:
    run_id: str
    tenant_id: str
    total_calls: int
    successful_calls: int
    failed_calls: int
    newly_created: int
    replayed: int
    calls_without_agent_manifest: list[str] = field(default_factory=list)
    calls_silent: list[str] = field(default_factory=list)
    total_artifacts: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    call_summaries: list[CallImportSummary] = field(default_factory=list)


class BatchImporter:
    def __init__(
        self,
        session_factory,
        artifact_store: ArtifactStore,
        tenant_id: str = "health_campaign",
    ) -> None:
        self.session_factory = session_factory
        self.artifact_store = artifact_store
        self.tenant_id = tenant_id
        self.service = IngestionService(session_factory)
        self.turn_processor = TranscriptProcessor()
        self.turn_repo = TranscriptRepository(session_factory)

    def import_directory(
        self,
        calls_dir: Path | str,
        run_id: str | None = None,
    ) -> BatchImportResult:
        base_dir = Path(calls_dir).resolve()
        if not base_dir.exists():
            raise FileNotFoundError(f"Calls directory not found: {base_dir}")

        if run_id is None:
            run_id = f"run_{uuid.uuid4().hex[:12]}"

        started_at = datetime.now(timezone.utc)

        # Enumerate call directories: call_01, call_02, ...
        call_folders = sorted(
            [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("call_")],
            key=lambda d: d.name,
        )

        successful_calls = 0
        failed_calls = 0
        newly_created = 0
        replayed = 0
        total_artifacts = 0
        calls_without_agent_manifest: list[str] = []
        calls_silent: list[str] = []
        summaries: list[CallImportSummary] = []

        for folder in call_folders:
            summary = CallImportSummary(folder=folder.name)
            try:
                envelope, artifact_rows, validation = map_call_folder(
                    folder_path=folder,
                    tenant_id=self.tenant_id,
                    artifact_store=self.artifact_store,
                )

                summary.call_id = envelope.interaction_id
                summary.status = envelope.status
                summary.files_count = len(artifact_rows)
                summary.has_agent_manifest = validation.has_agent_manifest
                summary.phone_answered = validation.phone_answered
                summary.validation_errors = validation.errors

                if not validation.has_agent_manifest:
                    calls_without_agent_manifest.append(folder.name)

                # Check if recording was silent
                is_silent = any(
                    a.artifact_type == "recording" and a.validation_status == "silent"
                    for a in artifact_rows
                )
                summary.is_silent = is_silent
                if is_silent:
                    calls_silent.append(folder.name)

                # Ingest canonical interaction envelope
                ingest_res = self.service.ingest(envelope)
                summary.created = ingest_res.created

                if ingest_res.created:
                    newly_created += 1
                else:
                    replayed += 1

                # Normalize and persist transcript turns
                turns = self.turn_processor.process_folder(
                    call_folder=folder,
                    tenant_id=self.tenant_id,
                )
                if turns:
                    self.turn_repo.save_turns(
                        tenant_id=self.tenant_id,
                        interaction_id=envelope.interaction_id,
                        turns=turns,
                    )

                # Persist ArtifactRows idempotently
                with self.session_factory() as session:
                    for art in artifact_rows:
                        existing = session.scalar(
                            select(ArtifactRow).where(
                                ArtifactRow.tenant_id == art.tenant_id,
                                ArtifactRow.interaction_id == art.interaction_id,
                                ArtifactRow.artifact_id == art.artifact_id,
                            )
                        )
                        if existing is None:
                            session.add(art)
                    session.commit()

                total_artifacts += len(artifact_rows)
                successful_calls += 1

            except Exception as exc:
                failed_calls += 1
                summary.error = str(exc)

            summaries.append(summary)

        completed_at = datetime.now(timezone.utc)

        result = BatchImportResult(
            run_id=run_id,
            tenant_id=self.tenant_id,
            total_calls=len(call_folders),
            successful_calls=successful_calls,
            failed_calls=failed_calls,
            newly_created=newly_created,
            replayed=replayed,
            calls_without_agent_manifest=calls_without_agent_manifest,
            calls_silent=calls_silent,
            total_artifacts=total_artifacts,
            started_at=started_at,
            completed_at=completed_at,
            call_summaries=summaries,
        )

        # Record import run row
        with self.session_factory() as session:
            run_summary = {
                "run_id": run_id,
                "tenant_id": self.tenant_id,
                "total_calls": len(call_folders),
                "successful_calls": successful_calls,
                "failed_calls": failed_calls,
                "newly_created": newly_created,
                "replayed": replayed,
                "calls_without_agent_manifest": calls_without_agent_manifest,
                "calls_silent": calls_silent,
                "total_artifacts": total_artifacts,
                "duration_seconds": (completed_at - started_at).total_seconds(),
            }
            session.add(
                ImportRunRow(
                    run_id=run_id,
                    tenant_id=self.tenant_id,
                    total_calls=len(call_folders),
                    successful_calls=successful_calls,
                    failed_calls=failed_calls,
                    summary_json=json.dumps(run_summary),
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
            session.commit()

        return result


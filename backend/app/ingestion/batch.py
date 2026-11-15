import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.call_importer import CallFolderImporter
from app.storage.artifacts import ArtifactStore


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
        self.call_importer = CallFolderImporter(session_factory, artifact_store)

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
                call_result = self.call_importer.import_call(folder, self.tenant_id)
                summary.call_id = call_result.interaction_id
                summary.status = call_result.status
                summary.files_count = call_result.files_count
                summary.has_agent_manifest = call_result.has_agent_manifest
                summary.phone_answered = call_result.phone_answered
                summary.validation_errors = call_result.validation_errors
                summary.error = call_result.error

                if not call_result.has_agent_manifest:
                    calls_without_agent_manifest.append(folder.name)

                is_silent = call_result.audio_validation.is_silent
                summary.is_silent = is_silent
                if is_silent:
                    calls_silent.append(folder.name)

                if call_result.status == "created":
                    summary.created = True
                    newly_created += 1
                    successful_calls += 1
                    total_artifacts += call_result.files_count
                elif call_result.status == "replayed":
                    replayed += 1
                    successful_calls += 1
                    total_artifacts += call_result.files_count
                else:
                    failed_calls += 1

            except Exception as exc:
                failed_calls += 1
                summary.error = str(exc)
                summary.status = "failed"

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
        return result


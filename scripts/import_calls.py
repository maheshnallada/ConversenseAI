import argparse
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.ingestion.batch import BatchImporter
from app.ingestion.report import generate_json_report, generate_markdown_report
from app.storage.artifacts import LocalArtifactStore
from app.storage.db import create_session_factory, init_db


def main():
    parser = argparse.ArgumentParser(description="Conversense AI - Batch Call Importer")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Path to calls directory",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=os.getenv("TENANT_ID", "health_campaign"),
        help="Tenant ID for ingested calls",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=f"sqlite:///{backend_path / 'conversense.sqlite3'}",
        help="Database URL (SQLite or PostgreSQL)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=os.getenv("ARTIFACT_STORAGE_PATH")
        or str(backend_path / "storage" / "artifacts"),
        help="Directory to store ingested artifacts",
    )
    parser.add_argument(
        "--report-out",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "docs" / "PHASE_2_IMPORT_MANIFEST.md"),
        help="Output path for Markdown report",
    )

    args = parser.parse_args()

    print(f"Initializing database at: {args.db_url}")
    factory = create_session_factory(args.db_url)
    init_db(factory)

    print(f"Initializing artifact store at: {args.artifacts_dir}")
    store = LocalArtifactStore(base_dir=args.artifacts_dir)

    artifact_root = Path(args.artifacts_dir)
    data_dir = (
        Path(args.data_dir).resolve()
        if args.data_dir
        else (artifact_root / args.tenant_id).resolve()
    )
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Calls directory does not exist: {data_dir}")

    print(f"Starting batch import from {data_dir} for tenant '{args.tenant_id}'...")
    importer = BatchImporter(session_factory=factory, artifact_store=store, tenant_id=args.tenant_id)
    result = importer.import_directory(data_dir)

    print(f"\nImport Completed in {result.run_id}:")
    print(f"  Total Calls: {result.total_calls}")
    print(f"  Successful: {result.successful_calls}")
    print(f"  Failed: {result.failed_calls}")
    print(f"  Newly Created: {result.newly_created}")
    print(f"  Replayed (idempotent): {result.replayed}")
    print(f"  Total Artifacts Stored: {result.total_artifacts}")
    print(f"  Calls without Agent Manifest: {len(result.calls_without_agent_manifest)}")
    print(f"  Digitally Silent Calls: {len(result.calls_silent)}")

    report_md = generate_markdown_report(result)
    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\nManifest report written to: {report_path}")


if __name__ == "__main__":
    main()


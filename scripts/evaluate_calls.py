import argparse
import json
import os
import sys
from pathlib import Path
from collections import Counter

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.storage.db import create_session_factory, init_db
from app.evaluation.service import EvaluationService


def main():
    parser = argparse.ArgumentParser(description="Conversense AI - Batch Evaluation Engine")
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
        help="Tenant ID for calls",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=f"sqlite:///{backend_path / 'conversense.sqlite3'}",
        help="Database URL (SQLite or PostgreSQL)",
    )

    args = parser.parse_args()

    print(f"Connecting to database: {args.db_url}")
    factory = create_session_factory(args.db_url)
    init_db(factory)

    service = EvaluationService(session_factory=factory)
    artifact_root = Path(
        os.getenv("ARTIFACT_STORAGE_PATH")
        or backend_path / "storage" / "artifacts"
    )
    calls_dir = (
        Path(args.data_dir).resolve()
        if args.data_dir
        else (artifact_root / args.tenant_id).resolve()
    )
    if not calls_dir.is_dir():
        raise FileNotFoundError(f"Calls directory does not exist: {calls_dir}")
    call_folders = sorted(
        [d for d in calls_dir.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )

    print(f"Running evaluation suite across {len(call_folders)} calls...")

    total_evaluated = 0
    assessments = Counter()
    batch_statuses = Counter()
    failed_calls = []

    for folder in call_folders:
        try:
            with open(folder / "call.json", "r", encoding="utf-8") as f:
                call_data = json.load(f)
            if not isinstance(call_data, dict) or not call_data.get("call_id"):
                raise ValueError("call.json is missing a call_id")
            run = service.evaluate_interaction(
                tenant_id=args.tenant_id,
                interaction_id=call_data["call_id"],
            )
        except Exception as exc:
            failed_calls.append((folder.name, str(exc)))
            print(f"Failed to evaluate {folder.name}: {exc}")
            continue

        total_evaluated += 1
        assessments[run.summary.get("overall_assessment", "Can't tell")] += 1
        batch_statuses.update(
            (batch.batch_name, batch.status) for batch in run.batches
        )

    print("\n" + "=" * 60)
    print("Conversense AI - Full 50-Call Evaluation Summary")
    print("=" * 60)
    print(f"Total Calls Evaluated: {total_evaluated}")
    print(f"Failed Calls: {len(failed_calls)}")
    for folder_name, error in failed_calls:
        print(f"  - {folder_name}: {error}")

    def percentage(count):
        return f"{count / total_evaluated * 100:.1f}%" if total_evaluated else "N/A"

    print("\nOverall assessments:")
    for assessment, count in assessments.most_common():
        print(f"  - {assessment}: {count} calls ({percentage(count)})")

    print("\nBatch statuses:")
    for (batch_name, status), count in sorted(batch_statuses.items()):
        print(f"  - {batch_name}: {count} {status}")

    if failed_calls:
        print("Evaluation completed with failures; successful runs were persisted.")
    else:
        print("All evaluation runs successfully persisted.")


if __name__ == "__main__":
    main()


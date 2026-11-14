import argparse
import json
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.reconstruction.processor import TranscriptProcessor
from app.reconstruction.reconstructor import TimelineReconstructor
from app.storage.db import create_session_factory, init_db
from app.storage.timeline_repo import TimelineRepository
from app.validation.audio import validate_call_files


def _connected_seconds(call_data):
    usage = (call_data.get("meta") or {}).get("usage") or {}
    return (usage.get("line") or {}).get("connected_s")


def main():
    parser = argparse.ArgumentParser(description="Conversense AI - Call Timeline Reconstructor")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "data" / "calls"),
        help="Path to calls directory",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="health_campaign",
        help="Tenant ID for timeline records",
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

    repo = TimelineRepository(factory)
    processor = TranscriptProcessor()
    reconstructor = TimelineReconstructor()

    calls_dir = Path(args.data_dir).resolve()
    call_folders = sorted(
        [d for d in calls_dir.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )

    print(f"Reconstructing timelines for {len(call_folders)} calls...")

    total_reconstructed = 0
    technical_failures_count = {}
    conversational_failures_count = {}
    total_overlaps = 0

    for folder in call_folders:
        call_json_path = folder / "call.json"
        if not call_json_path.exists():
            continue

        with open(call_json_path, "r", encoding="utf-8") as f:
            call_data = json.load(f)

        call_id = call_data["call_id"]
        val = validate_call_files(folder)

        call_meta = {
            "agent_wav_count": val.agent_wav_count,
            "end_reason": call_data.get("end_reason"),
            "connected_s": _connected_seconds(call_data),
        }

        turns = processor.process_folder(folder, tenant_id=args.tenant_id)
        timeline = reconstructor.reconstruct(
            tenant_id=args.tenant_id,
            interaction_id=call_id,
            turns=turns,
            call_metadata=call_meta,
        )

        repo.save_timeline(timeline)
        total_reconstructed += 1
        total_overlaps += timeline.overlap_count

        if timeline.first_technical_failure:
            t_type = timeline.first_technical_failure.failure_type
            technical_failures_count[t_type] = technical_failures_count.get(t_type, 0) + 1

        if timeline.first_conversational_failure:
            c_type = timeline.first_conversational_failure.failure_type
            conversational_failures_count[c_type] = conversational_failures_count.get(c_type, 0) + 1

    print("\nTimeline Reconstruction & Playback Reconciliation Complete:")
    print(f"  Total Calls Reconstructed: {total_reconstructed}")
    print(f"  Total Detected Turn Overlaps: {total_overlaps}")
    print("  First Technical Failures Breakdown:")
    for k, v in sorted(technical_failures_count.items()):
        print(f"    - {k}: {v}")
    print("  First Conversational Failures Breakdown:")
    for k, v in sorted(conversational_failures_count.items()):
        print(f"    - {k}: {v}")
    print("All timelines successfully stored in table 'interaction_timelines'.")


if __name__ == "__main__":
    main()


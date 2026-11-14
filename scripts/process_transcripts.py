import argparse
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.reconstruction.processor import TranscriptProcessor
from app.storage.db import create_session_factory, init_db
from app.storage.transcript_repo import TranscriptRepository


def main():
    parser = argparse.ArgumentParser(description="Conversense AI - Transcript Processor")
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
        help="Tenant ID for turns",
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

    repo = TranscriptRepository(factory)
    processor = TranscriptProcessor()

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

    print(f"Processing transcripts for {len(call_folders)} calls...")

    total_turns = 0
    total_agent_turns = 0
    total_customer_turns = 0
    spoken_counts = {"heard": 0, "cut": 0, "not_played": 0, "no_audio": 0, "none": 0}
    barge_in_count = 0

    for folder in call_folders:
        turns = processor.process_folder(folder, tenant_id=args.tenant_id)
        if turns:
            call_id = turns[0].interaction_id
            repo.save_turns(args.tenant_id, call_id, turns)

        for t in turns:
            total_turns += 1
            if t.speaker == "agent":
                total_agent_turns += 1
                if t.playback_spoken is None:
                    spoken_counts["none"] += 1
                elif t.playback_spoken in {"heard", "cut", "not_played", "no_audio"}:
                    spoken_counts[t.playback_spoken] += 1
                else:
                    raise ValueError(
                        f"Unexpected playback status in {folder.name}: "
                        f"{t.playback_spoken!r}"
                    )
            elif t.speaker == "customer":
                total_customer_turns += 1

            if t.barged_in is True:
                barge_in_count += 1

    print("\nTranscript Normalization & Turn Storage Complete:")
    print(f"  Total Calls Processed: {len(call_folders)}")
    print(f"  Total Turns Extracted: {total_turns}")
    print(f"  Agent Turns: {total_agent_turns}")
    print(f"  Customer Turns: {total_customer_turns}")
    print(f"  Spoken Marks Distribution (Agent):")
    for k, v in spoken_counts.items():
        print(f"    - {k}: {v}")
    print(f"  Barge-in Turns: {barge_in_count}")
    print("All turns successfully stored in table 'interaction_turns'.")


if __name__ == "__main__":
    main()


import argparse
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.observability.config import RateCardManager
from app.observability.service import ObservabilityService
from app.storage.db import create_session_factory, init_db
from app.storage.observability_repo import ObservabilityRepository


def main():
    parser = argparse.ArgumentParser(description="Conversense AI - Observability Metrics Calculator")
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
        help="Tenant ID for metrics",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=f"sqlite:///{backend_path / 'conversense.sqlite3'}",
        help="Database URL (SQLite or PostgreSQL)",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "configs" / "rate_cards.json"),
        help="Path to rate cards config",
    )

    args = parser.parse_args()

    print(f"Connecting to database: {args.db_url}")
    factory = create_session_factory(args.db_url)
    init_db(factory)

    rate_card = RateCardManager(args.config_path)
    service = ObservabilityService(session_factory=factory, rate_card=rate_card)
    repo = ObservabilityRepository(factory)

    artifact_root = Path(os.getenv("ARTIFACT_STORAGE_PATH") or backend_path / "storage" / "artifacts")
    calls_dir = (
        Path(args.data_dir).resolve()
        if args.data_dir
        else (artifact_root / args.tenant_id).resolve()
    )
    call_folders = sorted(
        [d for d in calls_dir.iterdir() if d.is_dir() and d.name.startswith("call_")],
        key=lambda d: d.name,
    )

    print(f"Calculating observability metrics for {len(call_folders)} calls...")

    for folder in call_folders:
        service.process_call_folder(folder, tenant_id=args.tenant_id)

    summary = repo.get_platform_summary(args.tenant_id)

    print("\nPlatform Observability Summary:")
    print(f"  Total Calls Processed: {summary.total_interactions}")
    print(f"  Total Audio Recording Duration: {summary.total_recording_duration_s:.2f}s ({summary.total_recording_duration_s / 60.0:.2f} min)")
    print(f"  Total Telephony Duration: {summary.total_telephony_duration_s:.2f}s ({summary.total_telephony_duration_s / 60.0:.2f} min)")
    print(f"  Total Conversation Turns: {summary.total_turns} (Agent: {summary.total_agent_turns}, Customer: {summary.total_customer_turns})")
    print(f"  Total Turn Overlaps: {summary.total_overlap_count} ({summary.total_overlap_duration_s:.2f}s total overlap)")
    print(f"  Response Latency Distribution:")
    print(f"    - Average: {summary.overall_latency_percentiles.avg}s")
    print(f"    - p50 (Median): {summary.overall_latency_percentiles.p50}s")
    print(f"    - p90: {summary.overall_latency_percentiles.p90}s")
    print(f"    - p95: {summary.overall_latency_percentiles.p95}s")
    print(f"    - p99: {summary.overall_latency_percentiles.p99}s")
    print(f"  Token Consumption:")
    print(f"    - Input Tokens: {summary.total_input_tokens}")
    print(f"    - Output Tokens: {summary.total_output_tokens}")
    print(f"    - Total Tokens: {summary.total_input_tokens + summary.total_output_tokens}")
    if summary.total_cost is None:
        print(f"  Total Estimated Cost: unavailable ({summary.currency})")
    else:
        print(f"  Total Estimated Cost: ${summary.total_cost:.4f} {summary.currency}")
    print("All metrics successfully stored in table 'observability_metrics'.")


if __name__ == "__main__":
    main()


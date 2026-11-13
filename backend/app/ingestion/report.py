from dataclasses import asdict
from datetime import timezone
from typing import Any

from app.ingestion.batch import BatchImportResult


def generate_json_report(result: BatchImportResult) -> dict[str, Any]:
    duration_s = (
        (result.completed_at - result.started_at).total_seconds()
        if result.completed_at
        else 0.0
    )
    return {
        "run_id": result.run_id,
        "tenant_id": result.tenant_id,
        "total_calls": result.total_calls,
        "successful_calls": result.successful_calls,
        "failed_calls": result.failed_calls,
        "newly_created": result.newly_created,
        "replayed": result.replayed,
        "total_artifacts": result.total_artifacts,
        "duration_seconds": round(duration_s, 2),
        "calls_without_agent_manifest": result.calls_without_agent_manifest,
        "calls_silent": result.calls_silent,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        "calls": [asdict(s) for s in result.call_summaries],
    }


def generate_markdown_report(result: BatchImportResult) -> str:
    duration_s = (
        (result.completed_at - result.started_at).total_seconds()
        if result.completed_at
        else 0.0
    )

    lines = [
        "# Batch Ingestion Report",
        "",
        f"- **Run ID:** `{result.run_id}`",
        f"- **Tenant ID:** `{result.tenant_id}`",
        f"- **Total Calls Ingested:** {result.successful_calls} / {result.total_calls}",
        f"- **Newly Ingested:** {result.newly_created}",
        f"- **Idempotent Replays:** {result.replayed}",
        f"- **Failed:** {result.failed_calls}",
        f"- **Total Stored Artifacts:** {result.total_artifacts}",
        f"- **Execution Time:** {duration_s:.2f}s",
        "",
        "## Key Dataset Findings",
        "",
        f"- **Calls without Agent Manifest/Audio ({len(result.calls_without_agent_manifest)}):** {', '.join(result.calls_without_agent_manifest) if result.calls_without_agent_manifest else 'None'}",
        f"- **Digitally Silent Calls ({len(result.calls_silent)}):** {', '.join(result.calls_silent) if result.calls_silent else 'None'}",
        "",
        "## Call-by-Call Ingestion Inventory",
        "",
        "| Folder | Interaction ID | Status | Files | Agent Manifest | Silent | Phone Answered | Ingestion |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for s in result.call_summaries:
        call_id_short = s.call_id[:8] + "..." if s.call_id else "N/A"
        agent_man_str = "Yes" if s.has_agent_manifest else "**No**"
        silent_str = "**Yes (Silent)**" if s.is_silent else "No"
        answered_str = "Yes" if s.phone_answered else "No"
        ingest_str = "Created" if s.created else "Replayed"
        if s.error:
            ingest_str = f"**Failed**: {s.error}"

        lines.append(
            f"| `{s.folder}` | `{call_id_short}` | {s.status} | {s.files_count} | {agent_man_str} | {silent_str} | {answered_str} | {ingest_str} |"
        )

    lines.append("")
    return "\n".join(lines)


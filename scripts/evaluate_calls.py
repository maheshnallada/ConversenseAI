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
from app.storage.evaluation_repo import EvaluationRepository


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
    compliance_violations = Counter()
    outcomes_count = Counter()
    what_happened_count = Counter()
    sentiment_count = Counter()
    emotion_count = Counter()
    quality_count = Counter()
    facts_extracted_total = 0
    failed_calls = []

    for folder in call_folders:
        try:
            with open(folder / "call.json", "r", encoding="utf-8") as f:
                call_data = json.load(f)
            if not isinstance(call_data, dict) or not call_data.get("call_id"):
                raise ValueError("call.json is missing a call_id")
            results = service.evaluate_interaction(
                tenant_id=args.tenant_id,
                interaction_id=call_data["call_id"],
            )

            local_compliance = Counter()
            local_outcomes = Counter()
            local_what_happened = Counter()
            local_sentiment = Counter()
            local_emotion = Counter()
            local_quality = Counter()
            local_facts = 0
            for result in results:
                if result.family == "compliance":
                    if result.label == "FAILED":
                        for evidence in result.evidence:
                            local_compliance[evidence.reason] += 1
                elif result.family == "outcome":
                    local_outcomes[result.label] += 1
                    local_what_happened[
                        result.details.get("what_happened", "Unknown")
                    ] += 1
                elif result.family == "experience":
                    local_sentiment[result.details.get("sentiment", "Unknown")] += 1
                    local_emotion[result.details.get("emotion", "Unknown")] += 1
                elif result.family == "quality":
                    local_quality[result.label] += 1
                elif result.family == "facts" and result.label == "FACTS_EXTRACTED":
                    local_facts += len(result.details)
        except Exception as exc:
            failed_calls.append((folder.name, str(exc)))
            print(f"Failed to evaluate {folder.name}: {exc}")
            continue

        total_evaluated += 1
        compliance_violations.update(local_compliance)
        outcomes_count.update(local_outcomes)
        what_happened_count.update(local_what_happened)
        sentiment_count.update(local_sentiment)
        emotion_count.update(local_emotion)
        quality_count.update(local_quality)
        facts_extracted_total += local_facts

    print("\n" + "=" * 60)
    print("Conversense AI - Full 50-Call Evaluation Summary")
    print("=" * 60)
    print(f"Total Calls Evaluated: {total_evaluated}")
    print(f"Failed Calls: {len(failed_calls)}")
    for folder_name, error in failed_calls:
        print(f"  - {folder_name}: {error}")

    def percentage(count):
        return f"{count / total_evaluated * 100:.1f}%" if total_evaluated else "N/A"

    print("\n1. Outcomes Breakdown (Correct Outcome):")
    for outcome, cnt in outcomes_count.most_common():
        print(f"  - {outcome}: {cnt} calls ({percentage(cnt)})")

    print("\n2. Call Progression (What Happened):")
    for what, cnt in what_happened_count.most_common():
        print(f"  - {what}: {cnt} calls ({percentage(cnt)})")

    print("\n3. Customer Sentiment:")
    for sent, cnt in sentiment_count.most_common():
        print(f"  - {sent}: {cnt} calls ({percentage(cnt)})")

    print("\n4. Customer Emotion:")
    for emo, cnt in emotion_count.most_common():
        print(f"  - {emo}: {cnt} calls ({percentage(cnt)})")

    print("\n5. Conversation Quality Scorecard:")
    for qual, cnt in quality_count.most_common():
        print(f"  - {qual}: {cnt} calls ({percentage(cnt)})")

    print("\n6. Compliance & Never-Rules Violations:")
    if compliance_violations:
        for viol, cnt in compliance_violations.most_common():
            print(f"  [VIOLATION] {viol}: {cnt} occurrences")
    else:
        print("  No compliance violations detected across calls.")

    print(f"\n7. Structured Facts Extracted: {facts_extracted_total} facts total")
    if failed_calls:
        print("Evaluation completed with failures; successful results were committed.")
    else:
        print("All evaluation results successfully committed to table 'evaluation_results'.")


if __name__ == "__main__":
    main()


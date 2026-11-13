import argparse
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
        default=str(Path(__file__).resolve().parent.parent / "data" / "calls"),
        help="Path to calls directory",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="health_campaign",
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
    calls_dir = Path(args.data_dir).resolve()
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

    for folder in call_folders:
        call_name = folder.name
        results = service.evaluate_interaction(
            tenant_id=args.tenant_id,
            interaction_id=call_name,
        )
        total_evaluated += 1

        for r in results:
            if r.family == "compliance":
                if r.label == "FAILED":
                    for ev in r.evidence:
                        compliance_violations[ev.reason] += 1
            elif r.family == "outcome":
                outcomes_count[r.label] += 1
                what = r.details.get("what_happened", "Unknown")
                what_happened_count[what] += 1
            elif r.family == "experience":
                sentiment_count[r.details.get("sentiment", "Unknown")] += 1
                emotion_count[r.details.get("emotion", "Unknown")] += 1
            elif r.family == "quality":
                quality_count[r.label] += 1
            elif r.family == "facts":
                if r.label == "FACTS_EXTRACTED":
                    facts_extracted_total += len(r.details)

    print("\n" + "=" * 60)
    print("Conversense AI - Full 50-Call Evaluation Summary")
    print("=" * 60)
    print(f"Total Calls Evaluated: {total_evaluated}")

    print("\n1. Outcomes Breakdown (Correct Outcome):")
    for outcome, cnt in outcomes_count.most_common():
        print(f"  - {outcome}: {cnt} calls ({cnt / total_evaluated * 100:.1f}%)")

    print("\n2. Call Progression (What Happened):")
    for what, cnt in what_happened_count.most_common():
        print(f"  - {what}: {cnt} calls ({cnt / total_evaluated * 100:.1f}%)")

    print("\n3. Customer Sentiment:")
    for sent, cnt in sentiment_count.most_common():
        print(f"  - {sent}: {cnt} calls ({cnt / total_evaluated * 100:.1f}%)")

    print("\n4. Customer Emotion:")
    for emo, cnt in emotion_count.most_common():
        print(f"  - {emo}: {cnt} calls ({cnt / total_evaluated * 100:.1f}%)")

    print("\n5. Conversation Quality Scorecard:")
    for qual, cnt in quality_count.most_common():
        print(f"  - {qual}: {cnt} calls ({cnt / total_evaluated * 100:.1f}%)")

    print("\n6. Compliance & Never-Rules Violations:")
    if compliance_violations:
        for viol, cnt in compliance_violations.most_common():
            print(f"  [VIOLATION] {viol}: {cnt} occurrences")
    else:
        print("  No compliance violations detected across calls.")

    print(f"\n7. Structured Facts Extracted: {facts_extracted_total} facts total")
    print("All evaluation results successfully committed to table 'evaluation_results'.")


if __name__ == "__main__":
    main()


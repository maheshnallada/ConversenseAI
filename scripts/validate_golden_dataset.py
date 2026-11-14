import argparse
import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.domain.evaluation import EvaluationRun
from app.domain.golden import GoldenCallLabel
from app.evaluation.service import EvaluationService
from app.storage.db import create_session_factory, init_db
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.validation.benchmark import BenchmarkEngine
from app.validation.golden_loader import load_golden_dataset


def build_reconciliation_rows(
    labels: list[GoldenCallLabel],
    runs_by_call: dict[str, EvaluationRun | None],
) -> list[tuple[str, str, str, bool]]:
    rows = []
    for label in labels:
        run = runs_by_call.get(label.call_id)
        batch = next(
            (
                item
                for item in run.batches
                if item.batch_name == "conversation_understanding"
                and item.status == "completed"
            ),
            None,
        ) if run else None
        outcome = batch.parsed_output.get("outcome", {}) if batch else {}
        prediction = outcome.get("label") or "Can't tell"
        rows.append(
            (
                label.call_id,
                label.correct_outcome,
                prediction,
                prediction == label.correct_outcome,
            )
        )
    return rows


def generate_markdown_report(report, output_path: Path, reconciliation_rows):
    with output_path.open("w", encoding="utf-8") as file:
        file.write("# Golden Dataset Benchmark Report\n\n")
        file.write(f"- **Golden interactions:** {report.total_interactions}\n")
        file.write(
            f"- **Outcome abstention rate:** {report.abstention_rate * 100:.1f}%\n"
        )
        file.write(
            "- **Compliance false negatives:** "
            f"{report.compliance_false_negatives}\n"
        )
        file.write(
            "- **Compliance false positives:** "
            f"{report.compliance_false_positives}\n\n"
        )
        file.write("## Dimension Metrics\n\n")
        file.write("| Dimension | Accuracy | Precision | Recall | Macro F1 | Support |\n")
        file.write("|---|---:|---:|---:|---:|---:|\n")
        for dimension, scores in report.dimension_metrics.items():
            file.write(
                f"| {dimension} | {scores.accuracy * 100:.1f}% | "
                f"{scores.precision:.3f} | {scores.recall:.3f} | "
                f"{scores.f1_score:.3f} | {scores.support} |\n"
            )

        file.write("\n## Call-Level Outcome Reconciliation\n\n")
        if not reconciliation_rows:
            file.write("No call-level reconciliation data available.\n")
        for call_id, ground_truth, prediction, matches in reconciliation_rows:
            match_status = (
                "Matches ground truth"
                if matches
                else "Does not match ground truth"
            )
            file.write(
                f"- `{call_id}`: Ground truth `{ground_truth}`; "
                f"prediction `{prediction}` ({match_status}).\n"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Conversense AI golden dataset benchmark validator"
    )
    parser.add_argument(
        "--golden-csv",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "data" / "golden_dataset.csv"),
        help="Path to golden dataset CSV",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=os.getenv("TENANT_ID", "health_campaign"),
        help="Tenant ID for interactions",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=f"sqlite:///{backend_path / 'conversense.sqlite3'}",
        help="Database URL",
    )
    args = parser.parse_args()

    factory = create_session_factory(args.db_url)
    init_db(factory)
    labels = load_golden_dataset(args.golden_csv)
    GoldenDatasetRepository(factory).save_many(labels)

    evaluation_service = EvaluationService(factory)
    evaluation_repo = EvaluationRepository(factory)
    runs_by_call = {}
    for label in labels:
        interaction_id = evaluation_service.resolve_interaction_id(
            args.tenant_id, label.call_id
        )
        runs_by_call[label.call_id] = evaluation_repo.get_latest_run(
            args.tenant_id, interaction_id
        )

    report = BenchmarkEngine().evaluate_benchmark(labels, runs_by_call)
    reconciliation_rows = build_reconciliation_rows(labels, runs_by_call)
    print(f"Golden interactions: {report.total_interactions}")
    print(f"Compliance false negatives: {report.compliance_false_negatives}")
    print(f"Compliance false positives: {report.compliance_false_positives}")
    for dimension, scores in report.dimension_metrics.items():
        print(
            f"{dimension}: accuracy={scores.accuracy:.3f}, "
            f"macro_f1={scores.f1_score:.3f}, support={scores.support}"
        )

    report_path = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "GOLDEN_DATASET_BENCHMARK.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    generate_markdown_report(report, report_path, reconciliation_rows)
    print(f"Generated benchmark report at: {report_path}")


if __name__ == "__main__":
    main()

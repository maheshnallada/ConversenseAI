from collections import defaultdict
from typing import Any

from app.domain.benchmark import BenchmarkReport, ConfusionMatrix, MetricScores
from app.domain.evaluation import EvaluationRun
from app.domain.golden import GoldenCallLabel


class BenchmarkEngine:
    def evaluate_benchmark(
        self,
        golden_labels: list[GoldenCallLabel],
        runs_by_call: dict[str, EvaluationRun | None],
    ) -> BenchmarkReport:
        if not golden_labels:
            return BenchmarkReport(total_interactions=0)

        supported_dimensions = {
            "correct_outcome": (
                lambda label: label.correct_outcome,
                lambda run: self._batch_value(
                    run, "conversation_understanding", "outcome", "label"
                ),
            ),
            "sentiment": (
                lambda label: label.sentiment,
                lambda run: self._batch_value(
                    run, "conversation_understanding", "sentiment", "label"
                ),
            ),
            "emotion": (
                lambda label: label.emotion,
                lambda run: self._batch_value(
                    run, "conversation_understanding", "emotion", "label"
                ),
            ),
            "overall_quality": (
                lambda label: label.overall,
                lambda run: self._summary_value(run, "overall_assessment"),
            ),
        }
        dimension_metrics: dict[str, MetricScores] = {}
        confusion_matrices: dict[str, ConfusionMatrix] = {}
        actuals_by_dimension: dict[str, list[str]] = {}
        predictions_by_dimension: dict[str, list[str]] = {}

        for name, (actual_for, predict_for) in supported_dimensions.items():
            actuals = [actual_for(label) for label in golden_labels]
            predictions = [
                predict_for(runs_by_call.get(label.call_id))
                for label in golden_labels
            ]
            actuals_by_dimension[name] = actuals
            predictions_by_dimension[name] = predictions
            confusion_matrices[name], dimension_metrics[name] = self._compute_metrics(
                actuals,
                predictions,
            )

        status_labels = [
            label for label in golden_labels if label.conversation_status is not None
        ]
        if status_labels:
            status_actuals = [label.conversation_status for label in status_labels]
            status_predictions = [
                self._batch_value(
                    runs_by_call.get(label.call_id),
                    "conversation_quality",
                    "conversation_completeness",
                    "conversation_status",
                )
                for label in status_labels
            ]
            (
                confusion_matrices["conversation_status"],
                dimension_metrics["conversation_status"],
            ) = self._compute_metrics(status_actuals, status_predictions)
            actuals_by_dimension["conversation_status"] = status_actuals
            predictions_by_dimension["conversation_status"] = status_predictions

        language_slice_metrics: dict[str, dict[str, MetricScores]] = {}
        language_labels = [
            label for label in golden_labels if label.language_slice is not None
        ]
        if language_labels:
            labels_by_slice: dict[str, list[GoldenCallLabel]] = defaultdict(list)
            for label in language_labels:
                labels_by_slice[label.language_slice].append(label)

            for language_slice, labels in labels_by_slice.items():
                metrics: dict[str, MetricScores] = {}
                for dimension, (actual_for, predict_for) in supported_dimensions.items():
                    actuals = [actual_for(label) for label in labels]
                    predictions = [
                        predict_for(runs_by_call.get(label.call_id))
                        for label in labels
                    ]
                    _, metrics[dimension] = self._compute_metrics(
                        actuals,
                        predictions,
                    )

                status_subset = [
                    label for label in labels if label.conversation_status is not None
                ]
                if status_subset:
                    actuals = [label.conversation_status for label in status_subset]
                    predictions = [
                        self._batch_value(
                            runs_by_call.get(label.call_id),
                            "conversation_quality",
                            "conversation_completeness",
                            "conversation_status",
                        )
                        for label in status_subset
                    ]
                    _, metrics["conversation_status"] = self._compute_metrics(
                        actuals,
                        predictions,
                    )
                language_slice_metrics[language_slice] = metrics

        compliance = [
            self._has_compliance_violation(runs_by_call.get(label.call_id))
            for label in golden_labels
        ]
        actual_violations = [
            bool(
                label.never_rule_broken
                and label.never_rule_broken.strip().lower() != "none"
            )
            for label in golden_labels
        ]
        comp_fn = sum(
            actual and not predicted
            for actual, predicted in zip(actual_violations, compliance)
        )
        comp_fp = sum(
            not actual and predicted
            for actual, predicted in zip(actual_violations, compliance)
        )
        abstentions = sum(
            prediction == "Can't tell"
            for prediction in predictions_by_dimension["correct_outcome"]
        )
        abstention_rate = round(abstentions / len(golden_labels), 4)

        details: dict[str, Any] = {
            "availability": {
                "conversation_status": (
                    "available" if status_labels else "unavailable"
                ),
                "language_slice": (
                    "available" if language_labels else "unavailable"
                ),
            },
            "compliance": {
                "true_positives": sum(
                    actual and predicted
                    for actual, predicted in zip(actual_violations, compliance)
                ),
                "true_negatives": sum(
                    not actual and not predicted
                    for actual, predicted in zip(actual_violations, compliance)
                ),
                "false_positives": comp_fp,
                "false_negatives": comp_fn,
            },
        }
        if language_slice_metrics:
            details["language_slice_metrics"] = language_slice_metrics

        return BenchmarkReport(
            total_interactions=len(golden_labels),
            dimension_metrics=dimension_metrics,
            confusion_matrices=confusion_matrices,
            compliance_false_negatives=comp_fn,
            compliance_false_positives=comp_fp,
            abstention_rate=abstention_rate,
            summary_notes=(
                f"Evaluated {len(golden_labels)} golden calls. "
                f"Compliance false negatives: {comp_fn}. "
                f"Abstention rate: {abstention_rate * 100:.1f}%."
            ),
            details=details,
        )

    @staticmethod
    def _batch_value(
        run: EvaluationRun | None,
        batch_name: str,
        *path: str,
    ) -> str:
        if run is None:
            return "Can't tell"
        batch = next(
            (
                item
                for item in run.batches
                if item.batch_name == batch_name
                and item.status in ("completed", "review_required")
                and item.parsed_output is not None
            ),
            None,
        )
        value: Any = batch.parsed_output if batch is not None else None
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        return value if isinstance(value, str) else "Can't tell"

    @staticmethod
    def _summary_value(run: EvaluationRun | None, key: str) -> str:
        if run is None:
            return "Can't tell"
        value = run.summary.get(key)
        return value if isinstance(value, str) else "Can't tell"

    @staticmethod
    def _has_compliance_violation(run: EvaluationRun | None) -> bool:
        if run is None:
            return False
        batch = next(
            (
                item
                for item in run.batches
                if item.batch_name == "compliance_appointment"
                and item.status in ("completed", "review_required")
                and item.parsed_output is not None
            ),
            None,
        )
        output = batch.parsed_output if batch is not None else None
        compliance = output.get("compliance") if isinstance(output, dict) else None
        results = (
            compliance.get("rule_results")
            if isinstance(compliance, dict)
            else None
        )
        return isinstance(results, dict) and any(
            isinstance(rule, dict) and rule.get("status") == "DETECTED"
            for rule in results.values()
        )

    @staticmethod
    def _compute_metrics(
        actuals: list[str | None],
        predictions: list[str],
    ) -> tuple[ConfusionMatrix, MetricScores]:
        labels = sorted(set(actuals + predictions))
        matrix: dict[str, dict[str, int]] = {
            actual: {predicted: 0 for predicted in labels}
            for actual in labels
        }
        correct = 0
        for actual, predicted in zip(actuals, predictions):
            matrix[actual][predicted] += 1
            correct += actual == predicted

        total = len(actuals)
        precisions: list[float] = []
        recalls: list[float] = []
        f1_scores: list[float] = []
        for label in labels:
            true_positive = matrix[label][label]
            false_positive = sum(
                matrix[other][label] for other in labels if other != label
            )
            false_negative = sum(
                matrix[label][other] for other in labels if other != label
            )
            precision = (
                true_positive / (true_positive + false_positive)
                if true_positive + false_positive
                else 0.0
            )
            recall = (
                true_positive / (true_positive + false_negative)
                if true_positive + false_negative
                else 0.0
            )
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            )
            if true_positive + false_positive:
                precisions.append(precision)
            if true_positive + false_negative:
                recalls.append(recall)
            f1_scores.append(f1)

        return (
            ConfusionMatrix(labels=labels, matrix=matrix),
            MetricScores(
                accuracy=round(correct / total, 4) if total else 0.0,
                precision=round(sum(precisions) / len(precisions), 4)
                if precisions
                else 0.0,
                recall=round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
                f1_score=round(sum(f1_scores) / len(f1_scores), 4)
                if f1_scores
                else 0.0,
                support=total,
            ),
        )

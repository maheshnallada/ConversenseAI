import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

from app.domain.golden import GoldenCallLabel
from app.domain.evaluation import EvaluationResult
from app.domain.benchmark import MetricScores, ConfusionMatrix, BenchmarkReport

logger = logging.getLogger(__name__)


class BenchmarkEngine:
    """
    Compares human-labeled golden dataset records against automated evaluation results,
    computing multi-class confusion matrices, precision, recall, F1, and compliance
    false negative rates.
    """

    def evaluate_benchmark(
        self,
        golden_labels: List[GoldenCallLabel],
        evaluations_by_call: Dict[str, List[EvaluationResult]],
    ) -> BenchmarkReport:
        total = len(golden_labels)
        if total == 0:
            return BenchmarkReport(total_interactions=0)

        # Map dimensions to evaluate
        # Each item: (dimension_name, ground_truth_extractor, eval_extractor)
        dimensions = [
            ("correct_outcome", lambda g: g.correct_outcome, self._extract_outcome),
            ("what_happened", lambda g: g.what_happened, self._extract_what_happened),
            ("sentiment", lambda g: g.sentiment, self._extract_sentiment),
            ("emotion", lambda g: g.emotion, self._extract_emotion),
            ("overall_quality", lambda g: g.overall, self._extract_quality),
        ]

        dimension_metrics: Dict[str, MetricScores] = {}
        confusion_matrices: Dict[str, ConfusionMatrix] = {}

        for dim_name, gt_fn, ev_fn in dimensions:
            actuals = []
            predictions = []
            for g in golden_labels:
                eval_list = evaluations_by_call.get(g.call_id, [])
                act = gt_fn(g)
                pred = ev_fn(eval_list)
                actuals.append(act)
                predictions.append(pred)

            cm, scores = self._compute_metrics(actuals, predictions)
            confusion_matrices[dim_name] = cm
            dimension_metrics[dim_name] = scores

        # Calculate Compliance metrics (Tracking False Negatives)
        comp_fn = 0
        comp_fp = 0
        comp_tp = 0
        comp_tn = 0

        for g in golden_labels:
            eval_list = evaluations_by_call.get(g.call_id, [])
            gt_has_violation = bool(g.never_rule_broken and g.never_rule_broken.strip().lower() != "none")

            comp_eval = next((e for e in eval_list if e.family == "compliance"), None)
            pred_has_violation = bool(comp_eval and comp_eval.label == "FAILED")

            if gt_has_violation and not pred_has_violation:
                comp_fn += 1
            elif not gt_has_violation and pred_has_violation:
                comp_fp += 1
            elif gt_has_violation and pred_has_violation:
                comp_tp += 1
            else:
                comp_tn += 1

        # Abstention rate (where automated evaluation abstained with 'Can't tell')
        abstentions = sum(
            1 for g in golden_labels
            if self._extract_outcome(evaluations_by_call.get(g.call_id, [])) == "Can't tell"
        )
        abstention_rate = round(abstentions / total, 4)

        report = BenchmarkReport(
            total_interactions=total,
            dimension_metrics=dimension_metrics,
            confusion_matrices=confusion_matrices,
            compliance_false_negatives=comp_fn,
            compliance_false_positives=comp_fp,
            abstention_rate=abstention_rate,
            summary_notes=(
                f"Evaluated {total} golden calls. Compliance False Negatives: {comp_fn}. "
                f"Abstention rate: {abstention_rate * 100:.1f}%."
            ),
            details={
                "compliance": {
                    "true_positives": comp_tp,
                    "true_negatives": comp_tn,
                    "false_positives": comp_fp,
                    "false_negatives": comp_fn,
                }
            },
        )

        return report

    def _compute_metrics(self, actuals: List[str], predictions: List[str]) -> tuple[ConfusionMatrix, MetricScores]:
        labels = sorted(list(dict.fromkeys(actuals + predictions)))
        matrix: Dict[str, Dict[str, int]] = {a: {p: 0 for p in labels} for a in labels}

        correct = 0
        total = len(actuals)

        for a, p in zip(actuals, predictions):
            matrix[a][p] += 1
            if a == p:
                correct += 1

        accuracy = round(correct / total, 4) if total > 0 else 0.0

        # Compute Macro Precision, Recall, F1
        precisions = []
        recalls = []

        for lbl in labels:
            tp = matrix[lbl][lbl]
            fp = sum(matrix[other][lbl] for other in labels if other != lbl)
            fn = sum(matrix[lbl][other] for other in labels if other != lbl)

            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0

            if (tp + fp) > 0:
                precisions.append(p)
            if (tp + fn) > 0:
                recalls.append(r)

        macro_p = round(sum(precisions) / len(precisions), 4) if precisions else 0.0
        macro_r = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
        macro_f1 = (
            round(2 * (macro_p * macro_r) / (macro_p + macro_r), 4)
            if (macro_p + macro_r) > 0
            else 0.0
        )

        scores = MetricScores(
            accuracy=accuracy,
            precision=macro_p,
            recall=macro_r,
            f1_score=macro_f1,
            support=total,
        )

        return ConfusionMatrix(labels=labels, matrix=matrix), scores

    def _extract_outcome(self, eval_list: List[EvaluationResult]) -> str:
        for e in eval_list:
            if e.family == "outcome":
                return e.details.get("correct_outcome") or e.label or "Can't tell"
        return "Can't tell"

    def _extract_what_happened(self, eval_list: List[EvaluationResult]) -> str:
        for e in eval_list:
            if e.family == "outcome":
                return e.details.get("what_happened") or "Can't tell"
        return "Can't tell"

    def _extract_sentiment(self, eval_list: List[EvaluationResult]) -> str:
        for e in eval_list:
            if e.family == "experience":
                return e.details.get("sentiment") or e.label or "Neutral"
        return "Neutral"

    def _extract_emotion(self, eval_list: List[EvaluationResult]) -> str:
        for e in eval_list:
            if e.family == "experience":
                return e.details.get("emotion") or "Neutral"
        return "Neutral"

    def _extract_quality(self, eval_list: List[EvaluationResult]) -> str:
        for e in eval_list:
            if e.family == "quality":
                return e.details.get("overall_quality") or e.label or "Good"
        return "Good"


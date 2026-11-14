from app.domain.evaluation import EvaluationResult
from app.domain.golden import GoldenCallLabel
from app.validation.benchmark import BenchmarkEngine


def _label(call_id: str, outcome: str) -> GoldenCallLabel:
    return GoldenCallLabel(
        call_id=call_id,
        what_happened="Call reached an ending",
        correct_outcome=outcome,
        sentiment="Neutral",
        emotion="Cooperative",
        overall="Good",
    )


def _outcome_evaluation(call_id: str, outcome: str) -> EvaluationResult:
    return EvaluationResult(
        tenant_id="tenant",
        interaction_id=call_id,
        evaluator_id="outcome",
        evaluator_version="1",
        family="outcome",
        method="deterministic",
        label=None,
        details={"correct_outcome": outcome},
    )


def test_macro_f1_is_mean_of_per_label_f1() -> None:
    actuals = ["A", "A", "A", "B"]
    predictions = ["A", "A", "B", "B"]
    labels = [_label(f"call_{i}", actual) for i, actual in enumerate(actuals)]
    evaluations = {
        label.call_id: [_outcome_evaluation(label.call_id, prediction)]
        for label, prediction in zip(labels, predictions)
    }

    report = BenchmarkEngine().evaluate_benchmark(labels, evaluations)

    assert report.dimension_metrics["correct_outcome"].precision == 0.75
    assert report.dimension_metrics["correct_outcome"].recall == 0.8333
    assert report.dimension_metrics["correct_outcome"].f1_score == 0.7333


def test_empty_evaluations_abstain_for_all_dimensions() -> None:
    labels = [_label("call_1", "Not interested"), _label("call_2", "Expert call booked")]

    report = BenchmarkEngine().evaluate_benchmark(labels, {})

    assert report.abstention_rate == 1.0
    for matrix in report.confusion_matrices.values():
        assert sum(row.get("Can't tell", 0) for row in matrix.matrix.values()) == 2
    assert all(scores.support == 2 for scores in report.dimension_metrics.values())

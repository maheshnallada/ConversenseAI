import pytest
from app.domain.golden import GoldenCallLabel
from app.domain.evaluation import EvaluationResult
from app.domain.benchmark import BenchmarkReport, ConfusionMatrix
from app.validation.benchmark import BenchmarkEngine

def test_benchmark_engine_confusion_matrix_and_metrics():
    engine = BenchmarkEngine()

    # Create dummy ground-truth labels
    golden_labels = [
        GoldenCallLabel(call_id="call_01", what_happened="Call reached an ending", correct_outcome="Not interested", sentiment="Negative", emotion="Disengaged", overall="OK", never_rule_broken="None"),
        GoldenCallLabel(call_id="call_02", what_happened="Gave a real answer, then left before an ending", correct_outcome="Expert call booked", sentiment="Neutral", emotion="Cooperative", overall="OK", never_rule_broken="None"),
        GoldenCallLabel(call_id="call_03", what_happened="Said hello or a few words, then left", correct_outcome="No outcome: customer left first", sentiment="Neutral", emotion="Disengaged", overall="Bad", never_rule_broken="None"),
        GoldenCallLabel(call_id="call_04", what_happened="Said hello or a few words, then left", correct_outcome="No outcome: customer left first", sentiment="Neutral", emotion="Confused", overall="Bad", never_rule_broken="None"),
    ]

    # Dummy automated evaluations
    evaluations = {
        "call_01": [
            EvaluationResult(tenant_id="t", interaction_id="call_01", evaluator_id="outcome.intent", evaluator_version="1.0.0", family="outcome", method="deterministic", label="Not interested", details={"correct_outcome": "Not interested", "what_happened": "Call reached an ending"}),
            EvaluationResult(tenant_id="t", interaction_id="call_01", evaluator_id="compliance.never_rules", evaluator_version="1.0.0", family="compliance", method="deterministic", label="PASSED"),
        ],
        "call_02": [
            EvaluationResult(tenant_id="t", interaction_id="call_02", evaluator_id="outcome.intent", evaluator_version="1.0.0", family="outcome", method="deterministic", label="Expert call booked", details={"correct_outcome": "Expert call booked", "what_happened": "Gave a real answer, then left before an ending"}),
            EvaluationResult(tenant_id="t", interaction_id="call_02", evaluator_id="compliance.never_rules", evaluator_version="1.0.0", family="compliance", method="deterministic", label="PASSED"),
        ],
        "call_03": [
            EvaluationResult(tenant_id="t", interaction_id="call_03", evaluator_id="outcome.intent", evaluator_version="1.0.0", family="outcome", method="deterministic", label="No outcome: customer left first", details={"correct_outcome": "No outcome: customer left first", "what_happened": "Said hello or a few words, then left"}),
            EvaluationResult(tenant_id="t", interaction_id="call_03", evaluator_id="compliance.never_rules", evaluator_version="1.0.0", family="compliance", method="deterministic", label="PASSED"),
        ],
        "call_04": [
            EvaluationResult(tenant_id="t", interaction_id="call_04", evaluator_id="outcome.intent", evaluator_version="1.0.0", family="outcome", method="deterministic", label="Can't tell", details={"correct_outcome": "Can't tell", "what_happened": "Can't tell"}),
            EvaluationResult(tenant_id="t", interaction_id="call_04", evaluator_id="compliance.never_rules", evaluator_version="1.0.0", family="compliance", method="deterministic", label="PASSED"),
        ],
    }

    report = engine.evaluate_benchmark(golden_labels, evaluations)

    assert report.total_interactions == 4
    assert "correct_outcome" in report.dimension_metrics
    outcome_metrics = report.dimension_metrics["correct_outcome"]
    assert outcome_metrics.accuracy == 0.75  # 3 of 4 match exactly
    assert report.abstention_rate == 0.25     # 1 of 4 abstained ('Can't tell')
    assert report.compliance_false_negatives == 0


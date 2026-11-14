from datetime import datetime, timezone

from app.domain.evaluation import EvaluationBatchRecord, EvaluationRun
from app.domain.golden import GoldenCallLabel
from app.validation.benchmark import BenchmarkEngine


def _batch(evaluation_id, batch_name, parsed_output):
    now = datetime.now(timezone.utc)
    return EvaluationBatchRecord(
        evaluation_id=evaluation_id,
        batch_name=batch_name,
        status="completed",
        model="test-model",
        prompt_version="1",
        schema_version="1",
        started_at=now,
        completed_at=now,
        input_tokens=None,
        output_tokens=None,
        raw_output=None,
        parsed_output=parsed_output,
        validation={"schema_valid": True, "evidence_valid": True},
        review_required=False,
        review_status="NOT_REQUIRED",
        review_reasons=[],
    )


def _run(call_id, batch_outputs, overall_assessment="Can't tell"):
    now = datetime.now(timezone.utc)
    run_id = f"run-{call_id}"
    return EvaluationRun(
        run_id=run_id,
        tenant_id="tenant_001",
        interaction_id=call_id,
        batches=[
            _batch(f"evaluation-{call_id}-{name}", name, output)
            for name, output in batch_outputs.items()
        ],
        summary={"overall_assessment": overall_assessment},
        started_at=now,
        completed_at=now,
        review_required=False,
        review_reasons=[],
    )


def test_benchmark_uses_explicit_completeness_and_language_labels():
    labels = [
        GoldenCallLabel(
            call_id="call_en",
            what_happened="Conflicting prose that must not be used",
            correct_outcome="Not interested",
            sentiment="Negative",
            emotion="Disengaged",
            overall="OK",
            conversation_status="COMPLETED",
            language_slice="en",
        ),
        GoldenCallLabel(
            call_id="call_hi_en",
            what_happened="Another prose description",
            correct_outcome="Expert call booked",
            sentiment="Neutral",
            emotion="Cooperative",
            overall="Good",
            conversation_status="CUSTOMER_LEFT_DURING_DISCUSSION",
            language_slice="hi-en",
        ),
    ]
    evaluations = {
        "call_en": _run(
            "call_en",
            {
                "conversation_understanding":
                {
                    "outcome": {"label": "Not interested"},
                    "sentiment": {"label": "Negative"},
                    "emotion": {"label": "Disengaged"},
                },
                "conversation_quality":
                {
                    "conversation_completeness": {
                        "conversation_status": "COMPLETED"
                    }
                },
            },
            "OK",
        ),
        "call_hi_en": _run(
            "call_hi_en",
            {
                "conversation_understanding":
                {
                    "outcome": {"label": "Call later agreed"},
                    "sentiment": {"label": "Neutral"},
                    "emotion": {"label": "Cooperative"},
                },
                "conversation_quality":
                {
                    "conversation_completeness": {
                        "conversation_status": "CUSTOMER_LEFT_DURING_OPENING"
                    }
                },
            },
            "Good",
        ),
    }

    report = BenchmarkEngine().evaluate_benchmark(labels, evaluations)

    assert report.dimension_metrics["conversation_status"].support == 2
    assert report.dimension_metrics["conversation_status"].accuracy == 0.5
    assert report.dimension_metrics["correct_outcome"].accuracy == 0.5
    assert report.details["language_slice_metrics"]["en"]["correct_outcome"].support == 1
    assert report.details["language_slice_metrics"]["hi-en"]["correct_outcome"].support == 1


def test_benchmark_marks_completeness_and_language_metrics_unavailable_without_labels():
    labels = [
        GoldenCallLabel(
            call_id="call_unlabeled",
            what_happened="Call reached an ending",
            correct_outcome="Not interested",
        )
    ]
    evaluations = {
        "call_unlabeled": _run(
            "call_unlabeled",
            {
                "conversation_quality":
                {
                    "conversation_completeness": {
                        "conversation_status": "COMPLETED"
                    }
                },
            },
        )
    }

    report = BenchmarkEngine().evaluate_benchmark(labels, evaluations)

    assert "conversation_status" not in report.dimension_metrics
    assert "language_slice_metrics" not in report.details
    assert report.details["availability"]["conversation_status"] == "unavailable"
    assert report.details["availability"]["language_slice"] == "unavailable"

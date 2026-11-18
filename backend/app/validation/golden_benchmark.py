import asyncio
import csv
from dataclasses import dataclass, replace
import io
import logging
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import sessionmaker

from app.domain.benchmark import BenchmarkReport
from app.domain.evaluation import EvaluationRun
from app.domain.golden import GoldenCallLabel, GoldenDatasetRecord
from app.evaluation.registry import _BATCH_MODELS
from app.evaluation.service import EvaluationService
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.golden_repo import GoldenDatasetRepository
from app.validation.benchmark import BenchmarkEngine
from app.validation.golden_loader import load_golden_dataset

logger = logging.getLogger(__name__)

_EXPECTED_BATCHES = frozenset(_BATCH_MODELS)

BENCHMARK_EXPORT_COLUMNS = [
    "call_id",
    "evaluation_status",
    "error",
    "language_slice",
    "gold_conversation_status",
    "pred_conversation_status",
    "conversation_status_match",
    "gold_what_happened",
    "pred_what_happened",
    "what_happened_match",
    "gold_outcome",
    "pred_outcome",
    "outcome_match",
    "gold_sentiment",
    "pred_sentiment",
    "sentiment_match",
    "gold_emotion",
    "pred_emotion",
    "emotion_match",
    "gold_overall",
    "pred_overall",
    "overall_match",
    "gold_never_rule",
    "pred_never_rules",
    "pred_compliance_violation",
    "compliance_match",
    "gold_first_thing_wrong_line",
    "gold_first_thing_wrong_category",
    "gold_first_thing_wrong_what",
    "gold_first_thing_wrong_description",
    "pred_first_thing_wrong_line",
    "pred_first_thing_wrong_category",
    "pred_first_thing_wrong_what",
    "pred_first_thing_wrong_description",
    "gold_facts_customer_gave",
    "pred_facts_customer_gave",
    "requires_human_review",
    "review_reasons",
    "evaluation_run_id",
]


@dataclass
class GoldenRecordResult:
    call_id: str
    evaluation_status: Literal["ready", "failed", "excluded"]
    evaluation_run_id: str | None = None
    reused: bool = False
    error: str | None = None


@dataclass
class GoldenBenchmarkImportResult:
    dataset_hash: str
    records_seen: int
    labels_imported: int
    test_records_excluded: int
    evaluations_created: int
    evaluations_reused: int
    evaluations_failed: int
    records: list[GoldenRecordResult]
    report: BenchmarkReport


class GoldenDatasetBenchmarkService:
    def __init__(
        self,
        session_factory: sessionmaker,
        evaluation_service: EvaluationService | None = None,
    ):
        self.evaluation_service = evaluation_service or EvaluationService(session_factory)
        self.evaluation_repo = EvaluationRepository(session_factory)
        self.golden_repo = GoldenDatasetRepository(session_factory)
        self.benchmark_engine = BenchmarkEngine()

    def import_and_benchmark(
        self,
        csv_path: Path,
        tenant_id: str,
    ) -> GoldenBenchmarkImportResult:
        dataset = load_golden_dataset(csv_path, tenant_id=tenant_id)
        self.golden_repo.save_many([record.label for record in dataset.records])

        async def process_records():
            semaphore = asyncio.Semaphore(2)

            async def process(record: GoldenDatasetRecord) -> GoldenRecordResult:
                async with semaphore:
                    if record.test_flag is True:
                        return GoldenRecordResult(
                            call_id=record.label.call_id,
                            evaluation_status="excluded",
                        )
                    if (
                        record.error
                        or record.input_hash is None
                        or record.evaluation_input is None
                    ):
                        return GoldenRecordResult(
                            call_id=record.label.call_id,
                            evaluation_status="failed",
                            error="Golden record input is invalid.",
                        )

                    namespace = f"golden_dataset:{record.input_hash}"
                    try:
                        run = self.evaluation_repo.get_latest_run(
                            tenant_id,
                            record.label.call_id,
                            evaluation_namespace=namespace,
                        )
                        reused = run is not None
                        if run is None:
                            run = await self.evaluation_service.evaluate_input(
                                record.evaluation_input.interaction,
                                record.evaluation_input.turns,
                                evaluation_namespace=namespace,
                            )
                    except Exception as exc:
                        logger.exception(
                            "Evaluation failed for record %s: %s",
                            record.label.call_id,
                            exc,
                        )
                        return GoldenRecordResult(
                            call_id=record.label.call_id,
                            evaluation_status="failed",
                            error=f"Golden record evaluation failed: {exc}",
                        )

                    ready = self._is_ready(run)
                    error_msg = None
                    if not ready:
                        if run is None:
                            error_msg = "Evaluation run was not created."
                        else:
                            failed_batches = [
                                f"{b.batch_name} ({b.status}): {b.error_message or 'missing parsed output'}"
                                for b in run.batches
                                if b.status not in ("completed", "review_required")
                                or b.parsed_output is None
                            ]
                            missing_batches = _EXPECTED_BATCHES - {
                                b.batch_name for b in run.batches
                            }
                            details = []
                            if failed_batches:
                                details.extend(failed_batches)
                            if missing_batches:
                                details.append(
                                    f"Missing batches: {', '.join(sorted(missing_batches))}"
                                )
                            error_msg = (
                                f"Golden record evaluation incomplete: {'; '.join(details)}"
                                if details
                                else "Golden record evaluation failed."
                            )

                    return GoldenRecordResult(
                        call_id=record.label.call_id,
                        evaluation_status="ready" if ready else "failed",
                        evaluation_run_id=run.run_id if run else None,
                        reused=reused,
                        error=error_msg,
                    )

            return await asyncio.gather(*(process(record) for record in dataset.records))

        records = asyncio.run(process_records())
        eligible_labels = self._report_labels(dataset.records)
        eligible_records = [
            record for record in dataset.records if record.test_flag is not True
        ]
        runs_by_call = {}
        eligible_results = [
            result
            for record, result in zip(dataset.records, records)
            if record.test_flag is not True
        ]
        for record, result in zip(eligible_records, eligible_results):
            runs_by_call[record.label.call_id] = (
                self._get_run_for_result(
                    tenant_id,
                    record.label.call_id,
                    record,
                    result,
                )
                if result.evaluation_status == "ready"
                else None
            )
        report = self.benchmark_engine.evaluate_benchmark(eligible_labels, runs_by_call)

        return GoldenBenchmarkImportResult(
            dataset_hash=dataset.dataset_hash,
            records_seen=len(dataset.records),
            labels_imported=len(dataset.records),
            test_records_excluded=sum(
                record.test_flag is True for record in dataset.records
            ),
            evaluations_created=sum(
                result.evaluation_status != "excluded"
                and not result.reused
                and result.evaluation_run_id is not None
                for result in records
            ),
            evaluations_reused=sum(result.reused for result in records),
            evaluations_failed=sum(
                record.test_flag is not True
                and result.evaluation_status == "failed"
                for record, result in zip(dataset.records, records)
            ),
            records=records,
            report=report,
        )

    def get_benchmark(self, csv_path: Path, tenant_id: str) -> BenchmarkReport:
        dataset = load_golden_dataset(csv_path, tenant_id=tenant_id)
        eligible_records = [
            record for record in dataset.records if record.test_flag is not True
        ]
        runs_by_call = {}
        for record in eligible_records:
            run = None
            if record.input_hash is not None and record.error is None:
                run = self.evaluation_repo.get_latest_run(
                    tenant_id,
                    record.label.call_id,
                    evaluation_namespace=f"golden_dataset:{record.input_hash}",
                )
            if not self._is_ready(run):
                run = None
            runs_by_call[record.label.call_id] = run
        return self.benchmark_engine.evaluate_benchmark(
            self._report_labels(eligible_records),
            runs_by_call,
        )

    @staticmethod
    def _report_labels(records: list[GoldenDatasetRecord]) -> list[GoldenCallLabel]:
        return [
            replace(record.label, conversation_status=None, language_slice=None)
            for record in records
            if record.test_flag is not True
        ]

    def _get_run_for_result(
        self,
        tenant_id: str,
        call_id: str,
        record: GoldenDatasetRecord,
        result: GoldenRecordResult,
    ) -> EvaluationRun | None:
        if record.input_hash is None or result.evaluation_run_id is None:
            return None
        return self.evaluation_repo.get_run(
            tenant_id,
            call_id,
            result.evaluation_run_id,
            evaluation_namespace=f"golden_dataset:{record.input_hash}",
        )

    @staticmethod
    def _is_ready(run: EvaluationRun | None) -> bool:
        return (
            run is not None
            and len(run.batches) == len(_EXPECTED_BATCHES)
            and {batch.batch_name for batch in run.batches} == _EXPECTED_BATCHES
            and all(
                batch.status in ("completed", "review_required")
                and batch.parsed_output is not None
                for batch in run.batches
            )
        )

    def get_interaction_evaluations(
        self,
        csv_path: Path,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        dataset = load_golden_dataset(csv_path, tenant_id=tenant_id)
        results: list[dict[str, Any]] = []

        for record in dataset.records:
            run: EvaluationRun | None = None
            if record.test_flag is True:
                status = "excluded"
                error_msg = None
            elif record.error or record.input_hash is None:
                status = "failed"
                error_msg = record.error or "Golden record input is invalid."
            else:
                namespace = f"golden_dataset:{record.input_hash}"
                run = self.evaluation_repo.get_latest_run(
                    tenant_id,
                    record.label.call_id,
                    evaluation_namespace=namespace,
                )
                if run is None:
                    run = self.evaluation_repo.get_latest_run(
                        tenant_id,
                        record.label.call_id,
                    )
                ready = self._is_ready(run)
                if ready:
                    status = "ready"
                    error_msg = None
                elif run is None:
                    status = "not_evaluated"
                    error_msg = "Evaluation run not found."
                else:
                    status = "incomplete"
                    error_msg = "Evaluation run incomplete."

            is_ready = status == "ready" and run is not None

            pred_what_happened = (
                self.benchmark_engine._batch_value(
                    run, "conversation_quality", "what_happened", "label"
                )
                if is_ready
                else ""
            )
            pred_outcome = (
                self.benchmark_engine._batch_value(
                    run, "conversation_understanding", "outcome", "label"
                )
                if is_ready
                else ""
            )
            pred_sentiment = (
                self.benchmark_engine._batch_value(
                    run, "conversation_understanding", "sentiment", "label"
                )
                if is_ready
                else ""
            )
            pred_emotion = (
                self.benchmark_engine._batch_value(
                    run, "conversation_understanding", "emotion", "label"
                )
                if is_ready
                else ""
            )
            pred_overall = (
                self.benchmark_engine._summary_value(run, "overall_assessment")
                if is_ready
                else ""
            )
            pred_conv_status = (
                self.benchmark_engine._batch_value(
                    run,
                    "conversation_quality",
                    "conversation_completeness",
                    "conversation_status",
                )
                if is_ready
                else ""
            )
            pred_compliance_violation = (
                self.benchmark_engine._has_compliance_violation(run)
                if is_ready
                else False
            )

            detected_rules: list[str] = []
            if is_ready and run:
                comp_batch = next(
                    (b for b in run.batches if b.batch_name == "compliance_appointment"),
                    None,
                )
                if comp_batch and comp_batch.parsed_output:
                    comp_data = comp_batch.parsed_output.get("compliance", {})
                    results_dict = comp_data.get("rule_results", {})
                    if isinstance(results_dict, dict):
                        for r_id, r_info in results_dict.items():
                            if isinstance(r_info, dict) and r_info.get("status") == "DETECTED":
                                detected_rules.append(r_id)
            pred_never_rules = ", ".join(detected_rules) if detected_rules else "None"

            pred_ftw_line: int | str = ""
            pred_ftw_cat = ""
            pred_ftw_what = ""
            pred_ftw_desc = ""
            if is_ready and run:
                cq_batch = next(
                    (b for b in run.batches if b.batch_name == "conversation_quality"),
                    None,
                )
                if cq_batch and cq_batch.parsed_output:
                    ftw = cq_batch.parsed_output.get("first_thing_wrong", {}) or {}
                    if isinstance(ftw, dict):
                        pred_ftw_line = ftw.get("line") if ftw.get("line") is not None else ""
                        pred_ftw_cat = ftw.get("category") or ""
                        pred_ftw_what = ftw.get("quote") or ftw.get("what") or ""
                        pred_ftw_desc = ftw.get("description") or ""

            pred_facts_str = ""
            if is_ready and run:
                cu_batch = next(
                    (b for b in run.batches if b.batch_name == "conversation_understanding"),
                    None,
                )
                if cu_batch and cu_batch.parsed_output:
                    facts = cu_batch.parsed_output.get("customer_facts", [])
                    if isinstance(facts, list):
                        facts_items = []
                        for f in facts:
                            if isinstance(f, dict):
                                fld = f.get("field") or f.get("category") or ""
                                val = f.get("value") or ""
                                if fld or val:
                                    facts_items.append(f"{fld}: {val}".strip(": "))
                        pred_facts_str = "; ".join(facts_items)

            gold_never = record.label.never_rule_broken or "None"
            gold_has_violation = bool(gold_never and gold_never.strip().lower() != "none")

            results.append({
                "call_id": record.label.call_id,
                "evaluation_status": status,
                "error": error_msg or "",
                "language_slice": record.label.language_slice or "",
                "gold_conversation_status": record.label.conversation_status or "",
                "pred_conversation_status": pred_conv_status,
                "conversation_status_match": (
                    (pred_conv_status == record.label.conversation_status)
                    if (is_ready and record.label.conversation_status)
                    else None
                ),
                "gold_what_happened": record.label.what_happened or "",
                "pred_what_happened": pred_what_happened,
                "what_happened_match": (
                    (pred_what_happened == record.label.what_happened)
                    if (is_ready and record.label.what_happened)
                    else None
                ),
                "gold_outcome": record.label.correct_outcome or "",
                "pred_outcome": pred_outcome,
                "outcome_match": (
                    (pred_outcome == record.label.correct_outcome)
                    if (is_ready and record.label.correct_outcome)
                    else None
                ),
                "gold_sentiment": record.label.sentiment or "",
                "pred_sentiment": pred_sentiment,
                "sentiment_match": (
                    (pred_sentiment == record.label.sentiment)
                    if (is_ready and record.label.sentiment)
                    else None
                ),
                "gold_emotion": record.label.emotion or "",
                "pred_emotion": pred_emotion,
                "emotion_match": (
                    (pred_emotion == record.label.emotion)
                    if (is_ready and record.label.emotion)
                    else None
                ),
                "gold_overall": record.label.overall or "",
                "pred_overall": pred_overall,
                "overall_match": (
                    (pred_overall == record.label.overall)
                    if (is_ready and record.label.overall)
                    else None
                ),
                "gold_never_rule": gold_never,
                "pred_never_rules": pred_never_rules,
                "pred_compliance_violation": pred_compliance_violation,
                "compliance_match": (
                    (pred_compliance_violation == gold_has_violation)
                    if is_ready
                    else None
                ),
                "gold_first_thing_wrong_line": (
                    record.label.first_thing_wrong_line
                    if record.label.first_thing_wrong_line is not None
                    else ""
                ),
                "gold_first_thing_wrong_category": record.label.first_thing_wrong_category or "",
                "gold_first_thing_wrong_what": record.label.first_thing_wrong_what or "",
                "gold_first_thing_wrong_description": record.label.first_thing_wrong_description or "",
                "pred_first_thing_wrong_line": pred_ftw_line,
                "pred_first_thing_wrong_category": pred_ftw_cat,
                "pred_first_thing_wrong_what": pred_ftw_what,
                "pred_first_thing_wrong_description": pred_ftw_desc,
                "gold_facts_customer_gave": record.label.facts_customer_gave or "",
                "pred_facts_customer_gave": pred_facts_str,
                "requires_human_review": run.review_required if run else False,
                "review_reasons": (
                    ", ".join(run.review_reasons)
                    if run and run.review_reasons
                    else ""
                ),
                "evaluation_run_id": run.run_id if run else "",
            })

        return results

    def export_benchmark_csv(
        self,
        csv_path: Path,
        tenant_id: str,
    ) -> str:
        records = self.get_interaction_evaluations(csv_path, tenant_id)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=BENCHMARK_EXPORT_COLUMNS)
        writer.writeheader()
        for row in records:
            formatted_row = {}
            for col in BENCHMARK_EXPORT_COLUMNS:
                val = row.get(col)
                if val is True:
                    formatted_row[col] = "TRUE"
                elif val is False:
                    formatted_row[col] = "FALSE"
                elif val is None:
                    formatted_row[col] = ""
                else:
                    formatted_row[col] = str(val)
            writer.writerow(formatted_row)
        return output.getvalue()

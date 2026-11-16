import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

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

_EXPECTED_BATCHES = frozenset(_BATCH_MODELS)


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
                    except Exception:
                        return GoldenRecordResult(
                            call_id=record.label.call_id,
                            evaluation_status="failed",
                            error="Golden record evaluation failed.",
                        )

                    ready = self._is_ready(run)
                    return GoldenRecordResult(
                        call_id=record.label.call_id,
                        evaluation_status="ready" if ready else "failed",
                        evaluation_run_id=run.run_id,
                        reused=reused,
                        error=None if ready else "Golden record evaluation failed.",
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
            and all(batch.status == "completed" for batch in run.batches)
        )

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from collections import Counter
from sqlalchemy import select, desc
from sqlalchemy.orm import sessionmaker

from app.storage.orm import (
    InteractionRow,
    ObservabilityMetricsRow,
    EvaluationBatchRow,
    EvaluationRunRow,
    InteractionTimelineRow,
    InteractionEventRow,
)
from app.observability.calculator import calculate_percentiles
from app.observability.config import RateCardManager
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.observability_repo import aggregate_cost_rows

class AnalyticsService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
        self.rate_card = RateCardManager()

    @staticmethod
    def _latest_runs(session, tenant_id: str):
        rows = session.scalars(
            select(EvaluationRunRow)
            .where(EvaluationRunRow.tenant_id == tenant_id)
            .order_by(desc(EvaluationRunRow.started_at), desc(EvaluationRunRow.id))
        ).all()
        selected: dict[str, EvaluationRunRow] = {}
        for row in rows:
            selected.setdefault(row.interaction_id, row)
        if not selected:
            return {}

        batches_by_run: dict[str, list[EvaluationBatchRow]] = {
            run.run_id: [] for run in selected.values()
        }
        batch_rows = session.scalars(
            select(EvaluationBatchRow).where(
                EvaluationBatchRow.tenant_id == tenant_id,
                EvaluationBatchRow.run_id.in_(batches_by_run),
            )
        ).all()
        for batch in batch_rows:
            batches_by_run[batch.run_id].append(batch)
        return {
            interaction_id: EvaluationRepository._to_run(
                run,
                batches_by_run[run.run_id],
            )
            for interaction_id, run in selected.items()
        }

    @staticmethod
    def _batch_value(run, batch_name: str, *path: str) -> str | None:
        if run is None:
            return None
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
        value = batch.parsed_output if batch is not None else None
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        return value if isinstance(value, str) else None

    @staticmethod
    def _compliance_status(run) -> str:
        batch = next(
            (
                item
                for item in run.batches
                if item.batch_name == "compliance_appointment"
            ),
            None,
        ) if run else None
        if (
            batch is None
            or batch.status not in ("completed", "review_required")
            or not batch.parsed_output
        ):
            return "NOT_EVALUABLE"
        compliance = batch.parsed_output.get("compliance")
        rules = compliance.get("rule_results") if isinstance(compliance, dict) else None
        if not isinstance(rules, dict):
            return "NOT_EVALUABLE"
        statuses = {
            rule.get("status")
            for rule in rules.values()
            if isinstance(rule, dict)
        }
        if "DETECTED" in statuses:
            return "FAILED"
        if statuses and statuses == {"NOT_DETECTED"}:
            return "PASSED"
        return "REVIEW_REQUIRED"

    def get_overview_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            interactions = session.scalars(
                select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            ).all()

            status_counts = Counter()
            for i in interactions:
                payload = json.loads(i.payload_json)
                status = payload.get("status") if isinstance(payload, dict) else None
                status_counts[
                    status
                    if status in {"completed", "abandoned", "failed", "pending"}
                    else "unknown"
                ] += 1

            metrics_rows = session.scalars(
                select(ObservabilityMetricsRow).where(
                    ObservabilityMetricsRow.tenant_id == tenant_id
                )
            ).all()

            latency_samples: list[float] = []
            for row in metrics_rows:
                metrics_data = json.loads(row.metrics_json)
                samples = metrics_data.get("response_latency_samples", [])
                if isinstance(samples, list):
                    latency_samples.extend(
                        sample
                        for sample in samples
                        if isinstance(sample, (int, float))
                        and not isinstance(sample, bool)
                        and sample >= 0
                    )
            latency_percentiles = calculate_percentiles(latency_samples)
            duration_samples = [
                row.recording_duration_s
                for row in metrics_rows
                if row.recording_duration_s is not None
            ]

            return {
                "total_interactions": len(interactions),
                "interaction_status_counts": dict(status_counts),
                "metrics_available_interactions": len(metrics_rows),
                "average_recording_duration_s": (
                    round(sum(duration_samples) / len(duration_samples), 3)
                    if duration_samples
                    else None
                ),
                "average_response_latency_s": latency_percentiles.avg,
                "p95_response_latency_s": latency_percentiles.p95,
            }

    def get_reliability_analytics(
        self, tenant_id: str = "health_campaign"
    ) -> Dict[str, Any]:
        with self.session_factory() as session:
            interactions = session.scalars(
                select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            ).all()
            status_counts = Counter()
            for interaction in interactions:
                payload = json.loads(interaction.payload_json)
                status = payload.get("status") if isinstance(payload, dict) else None
                status_counts[
                    status
                    if status in {"completed", "abandoned", "failed", "pending"}
                    else "unknown"
                ] += 1

            technical_failures = Counter()
            conversational_failures = Counter()
            timelines = session.scalars(
                select(InteractionTimelineRow).where(
                    InteractionTimelineRow.tenant_id == tenant_id
                )
            ).all()
            interactions_with_failures = set()
            for timeline in timelines:
                data = json.loads(timeline.timeline_json)
                failures = data.get("failures")
                if isinstance(failures, list):
                    for failure in failures:
                        if not isinstance(failure, dict):
                            continue
                        category = failure.get("category")
                        failure_type = failure.get("failure_type")
                        if not isinstance(failure_type, str):
                            continue
                        if category == "technical":
                            technical_failures[failure_type] += 1
                            interactions_with_failures.add(timeline.interaction_id)
                        elif category == "conversational":
                            conversational_failures[failure_type] += 1
                            interactions_with_failures.add(timeline.interaction_id)
                else:
                    for category, field in (
                        ("technical", "first_technical_failure"),
                        ("conversational", "first_conversational_failure"),
                    ):
                        failure = data.get(field)
                        if isinstance(failure, dict) and isinstance(
                            failure.get("failure_type"), str
                        ):
                            target = (
                                technical_failures
                                if category == "technical"
                                else conversational_failures
                            )
                            target[failure["failure_type"]] += 1
                            interactions_with_failures.add(timeline.interaction_id)

            event_failures = Counter()
            events = session.scalars(
                select(InteractionEventRow).where(
                    InteractionEventRow.tenant_id == tenant_id
                )
            ).all()
            for event in events:
                event_type = event.event_type.lower()
                if "fail" in event_type or "error" in event_type:
                    event_failures[event.event_type] += 1
                    interactions_with_failures.add(event.interaction_id)

            return {
                "interaction_status_counts": dict(status_counts),
                "technical_failures": dict(technical_failures),
                "conversational_failures": dict(conversational_failures),
                "supplied_event_failures": dict(event_failures),
                "interactions_with_failures": len(interactions_with_failures),
            }

    def get_usage_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            metrics_rows = session.scalars(
                select(ObservabilityMetricsRow).where(
                    ObservabilityMetricsRow.tenant_id == tenant_id
                )
            ).all()
            batches = session.scalars(
                select(EvaluationBatchRow).where(
                    EvaluationBatchRow.tenant_id == tenant_id,
                    EvaluationBatchRow.status == "completed",
                )
            ).all()

            interaction_input = [
                row.input_tokens for row in metrics_rows if row.input_tokens is not None
            ]
            interaction_output = [
                row.output_tokens for row in metrics_rows if row.output_tokens is not None
            ]
            evaluation_input = [
                batch.input_tokens for batch in batches if batch.input_tokens is not None
            ]
            evaluation_output = [
                batch.output_tokens for batch in batches if batch.output_tokens is not None
            ]

            input_values = interaction_input + evaluation_input
            output_values = interaction_output + evaluation_output
            usage_available = bool(input_values or output_values)
            metrics_total_cost, _, cost_by_currency = aggregate_cost_rows(metrics_rows)
            evaluation_costs = [
                self.rate_card.calculate_llm_cost(
                    batch.model,
                    batch.input_tokens,
                    batch.output_tokens,
                )
                for batch in batches
            ]
            evaluation_costs_available = all(
                cost is not None for cost in evaluation_costs
            )
            evaluation_total_cost = (
                sum(evaluation_costs)
                if evaluation_costs_available
                else None
            )
            if batches and evaluation_total_cost is not None:
                cost_currency = self.rate_card.currency
                cost_by_currency[cost_currency] = round(
                    cost_by_currency.get(cost_currency, 0.0)
                    + evaluation_total_cost,
                    4,
                )

            all_costs_available = (
                bool(metrics_rows or batches)
                and all(row.total_cost is not None for row in metrics_rows)
                and evaluation_costs_available
            )
            available_currencies = set(cost_by_currency)
            if not metrics_rows and batches:
                available_currencies.add(self.rate_card.currency)
            if (
                all_costs_available
                and len(available_currencies) == 1
                and "UNKNOWN" not in available_currencies
            ):
                currency = next(iter(available_currencies))
                total_cost = (metrics_total_cost or 0.0) + (
                    evaluation_total_cost or 0.0
                )
            else:
                total_cost = None
                currency = None
            rate_card_versions = sorted(
                {
                    data["rate_card_version"]
                    for data in (
                        json.loads(row.metrics_json) for row in metrics_rows
                    )
                    if isinstance(data.get("rate_card_version"), str)
                }
            )
            if batches and isinstance(self.rate_card.version, str):
                rate_card_versions.append(self.rate_card.version)
                rate_card_versions = sorted(set(rate_card_versions))

            return {
                "usage_available": usage_available,
                "input_tokens": sum(input_values) if input_values else None,
                "output_tokens": sum(output_values) if output_values else None,
                "interaction_input_tokens": (
                    sum(interaction_input) if interaction_input else None
                ),
                "interaction_output_tokens": (
                    sum(interaction_output) if interaction_output else None
                ),
                "evaluation_input_tokens": (
                    sum(evaluation_input) if evaluation_input else None
                ),
                "evaluation_output_tokens": (
                    sum(evaluation_output) if evaluation_output else None
                ),
                "estimated_cost": total_cost,
                "currency": currency,
                "cost_by_currency": cost_by_currency,
                "cost_availability": (
                    "available" if total_cost is not None else "unavailable"
                ),
                "rate_card_versions": rate_card_versions,
            }

    def get_interactions_page(
        self,
        tenant_id: str = "health_campaign",
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        outcome: Optional[str] = None,
        search: Optional[str] = None,
        started_after: Optional[datetime] = None,
        started_before: Optional[datetime] = None,
        use_case: Optional[str] = None,
        error_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.session_factory() as session:
            # Query all interactions
            stmt = select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            interactions = session.scalars(stmt).all()

            runs_by_id = self._latest_runs(session, tenant_id)
            timelines = {
                row.interaction_id: row
                for row in session.scalars(
                    select(InteractionTimelineRow).where(
                        InteractionTimelineRow.tenant_id == tenant_id
                    )
                ).all()
            }
            failure_event_ids = {
                row.interaction_id
                for row in session.scalars(
                    select(InteractionEventRow).where(
                        InteractionEventRow.tenant_id == tenant_id
                    )
                ).all()
                if "fail" in row.event_type.lower()
                or "error" in row.event_type.lower()
            }

            def to_utc(value: datetime | None) -> datetime | None:
                if value is None:
                    return None
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc)

            normalized_started_after = to_utc(started_after)
            normalized_started_before = to_utc(started_before)
            items = []
            for row in interactions:
                call_data = {}
                try:
                    payload = json.loads(row.payload_json)
                    call_data = payload.get("domain_data", {})
                    if not isinstance(call_data, dict):
                        call_data = {}
                    raw_status = payload.get("status") if isinstance(payload, dict) else None
                    call_status = (
                        raw_status
                        if raw_status in {"completed", "abandoned", "failed", "pending", "unknown"}
                        else "unknown"
                    )
                    started_at = payload.get("started_at")
                    interaction_use_case = payload.get("use_case")
                except Exception:
                    call_status = "unknown"
                    started_at = None
                    interaction_use_case = None

                run = runs_by_id.get(row.interaction_id)
                timeline = timelines.get(row.interaction_id)
                has_errors = None
                timeline_data = None
                if timeline is not None:
                    try:
                        timeline_data = json.loads(timeline.timeline_json)
                    except json.JSONDecodeError:
                        timeline_data = None
                if (
                    call_status == "failed"
                    or row.interaction_id in failure_event_ids
                    or (
                        timeline is not None
                        and (
                            timeline.first_technical_failure_type is not None
                            or timeline.first_conversational_failure_type is not None
                        )
                    )
                ):
                    has_errors = True
                elif isinstance(timeline_data, dict) and (
                    isinstance(timeline_data.get("failures"), list)
                    or (
                        "first_technical_failure" in timeline_data
                        and "first_conversational_failure" in timeline_data
                    )
                ):
                    has_errors = False

                outcome_label = self._batch_value(
                    run,
                    "conversation_understanding",
                    "outcome",
                    "label",
                )
                # Filters
                if status and status.lower() != call_status.lower():
                    continue
                if outcome and (
                    outcome_label is None
                    or outcome.lower() not in outcome_label.lower()
                ):
                    continue
                if use_case and (interaction_use_case or "").lower() != use_case.lower():
                    continue
                started_at_value = None
                if isinstance(started_at, str):
                    try:
                        started_at_value = to_utc(
                            datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        )
                    except ValueError:
                        started_at_value = None
                if normalized_started_after and (
                    started_at_value is None
                    or started_at_value < normalized_started_after
                ):
                    continue
                if normalized_started_before and (
                    started_at_value is None
                    or started_at_value > normalized_started_before
                ):
                    continue
                if error_state == "has_errors" and has_errors is not True:
                    continue
                if error_state == "no_errors" and has_errors is not False:
                    continue
                folder_name = call_data.get("folder_name")
                if search:
                    s_low = search.lower()
                    fname_low = (folder_name or "").lower()
                    if s_low not in row.interaction_id.lower() and s_low not in fname_low:
                        continue

                items.append({
                    "interaction_id": row.interaction_id,
                    "folder_name": folder_name,
                    "started_at": started_at,
                    "status": call_status,
                    "use_case": interaction_use_case,
                    "has_errors": has_errors,
                    "outcome": outcome_label,
                })

            # Sort by started_at or interaction_id
            items.sort(key=lambda x: str(x.get("started_at") or x["interaction_id"]), reverse=True)

            total = len(items)
            page_size = max(1, min(page_size, 100))
            page = max(1, page)
            pages = (total + page_size - 1) // page_size if total > 0 else 1

            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paged_items = items[start_idx:end_idx]

            return {
                "items": paged_items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": pages,
            }

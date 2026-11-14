import json
from typing import Dict, Any, List, Optional
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
from app.storage.evaluation_repo import EvaluationRepository
from app.storage.observability_repo import aggregate_cost_rows

class AnalyticsService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

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
                if item.batch_name == batch_name and item.status == "completed"
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
        if batch is None or batch.status != "completed" or not batch.parsed_output:
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
            total_cost, currency, cost_by_currency = aggregate_cost_rows(metrics_rows)
            all_costs_available = bool(metrics_rows) and all(
                row.total_cost is not None for row in metrics_rows
            )
            if not all_costs_available:
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

    def get_quality_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            runs_by_interaction = self._latest_runs(session, tenant_id)

            outcomes = Counter()
            sentiment = Counter()
            emotion = Counter()
            overall_quality = Counter()

            for run in runs_by_interaction.values():
                outcome = self._batch_value(
                    run,
                    "conversation_understanding",
                    "outcome",
                    "label",
                )
                if outcome is not None:
                    outcomes[outcome] += 1
                current_sentiment = self._batch_value(
                    run,
                    "conversation_understanding",
                    "sentiment",
                    "label",
                )
                if current_sentiment is not None:
                    sentiment[current_sentiment] += 1
                current_emotion = self._batch_value(
                    run,
                    "conversation_understanding",
                    "emotion",
                    "label",
                )
                if current_emotion is not None:
                    emotion[current_emotion] += 1
                overall = run.summary.get("overall_assessment")
                if isinstance(overall, str):
                    overall_quality[overall] += 1

            # Timelines failure analysis
            timeline_rows = session.scalars(
                select(InteractionTimelineRow).where(InteractionTimelineRow.tenant_id == tenant_id)
            ).all()

            tech_failures = Counter()
            conv_failures = Counter()
            for t in timeline_rows:
                try:
                    data = json.loads(t.timeline_json)
                    tf = data.get("first_technical_failure")
                    if tf:
                        tech_failures[tf.get("failure_type", "Unknown")] += 1
                    cf = data.get("first_conversational_failure")
                    if cf:
                        conv_failures[cf.get("failure_type", "Unknown")] += 1
                except Exception:
                    pass

            return {
                "outcomes": dict(outcomes),
                "sentiment": dict(sentiment),
                "emotion": dict(emotion),
                "overall_quality": dict(overall_quality),
                "technical_failures": dict(tech_failures),
                "conversational_failures": dict(conv_failures),
            }

    def get_cost_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            metrics_rows = session.scalars(
                select(ObservabilityMetricsRow).where(ObservabilityMetricsRow.tenant_id == tenant_id)
            ).all()

            total_cost, currency, cost_by_currency = aggregate_cost_rows(metrics_rows)
            total_tokens = sum(r.total_tokens or 0 for r in metrics_rows)
            input_tokens = sum(r.input_tokens or 0 for r in metrics_rows)
            output_tokens = sum(r.output_tokens or 0 for r in metrics_rows)
            total_telephony_s = sum(r.telephony_duration_s or 0.0 for r in metrics_rows)

            breakdown_by_currency: Dict[str, Dict[str, float]] = {}
            models_dict: Dict[str, Dict[str, Any]] = {}

            for r in metrics_rows:
                try:
                    m = json.loads(r.metrics_json)
                    cb = m.get("cost_breakdown", {})
                    row_currency = cb.get("currency") or r.cost_currency or "UNKNOWN"
                    currency_breakdown = breakdown_by_currency.setdefault(
                        row_currency,
                        {"llm_cost": 0.0, "stt_cost": 0.0, "tts_cost": 0.0, "telephony_cost": 0.0},
                    )
                    for cost_name in currency_breakdown:
                        cost_value = cb.get(cost_name)
                        if isinstance(cost_value, (int, float)):
                            currency_breakdown[cost_name] += cost_value

                    model_name = m.get("llm_model") or "unknown"
                    if model_name not in models_dict:
                        models_dict[model_name] = {
                            "calls": 0,
                            "tokens": 0,
                            "cost_by_currency": {},
                        }
                    models_dict[model_name]["calls"] += 1
                    models_dict[model_name]["tokens"] += (r.total_tokens or 0)
                    llm_cost = cb.get("llm_cost")
                    if isinstance(llm_cost, (int, float)):
                        model_costs = models_dict[model_name]["cost_by_currency"]
                        model_costs[row_currency] = model_costs.get(row_currency, 0.0) + llm_cost
                except Exception:
                    pass

            breakdown_by_currency = {
                row_currency: {
                    cost_name: round(cost, 4)
                    for cost_name, cost in values.items()
                }
                for row_currency, values in breakdown_by_currency.items()
            }
            return {
                "total_cost": total_cost,
                "total_cost_usd": total_cost if currency == "USD" else None,
                "currency": currency,
                "cost_by_currency": cost_by_currency,
                "cost_breakdown_by_currency": breakdown_by_currency,
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "llm_cost_usd": (
                    breakdown_by_currency.get("USD", {}).get("llm_cost")
                    if currency == "USD"
                    else None
                ),
                "stt_cost_usd": (
                    breakdown_by_currency.get("USD", {}).get("stt_cost")
                    if currency == "USD"
                    else None
                ),
                "tts_cost_usd": (
                    breakdown_by_currency.get("USD", {}).get("tts_cost")
                    if currency == "USD"
                    else None
                ),
                "telephony_cost_usd": (
                    breakdown_by_currency.get("USD", {}).get("telephony_cost")
                    if currency == "USD"
                    else None
                ),
                "telephony_duration_s": round(total_telephony_s, 2),
                "model_breakdown": {
                    k: {
                        "calls": v["calls"],
                        "tokens": v["tokens"],
                        "cost_by_currency": {
                            row_currency: round(value, 4)
                            for row_currency, value in v["cost_by_currency"].items()
                        },
                        "cost_usd": (
                            round(v["cost_by_currency"].get("USD", 0.0), 4)
                            if currency == "USD"
                            else None
                        ),
                    }
                    for k, v in models_dict.items()
                },
            }

    def get_interactions_page(
        self,
        tenant_id: str = "health_campaign",
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        outcome: Optional[str] = None,
        quality: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.session_factory() as session:
            # Query all interactions
            stmt = select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            interactions = session.scalars(stmt).all()

            # Pre-load metrics and evaluations
            metrics = {
                r.interaction_id: r
                for r in session.scalars(
                    select(ObservabilityMetricsRow).where(ObservabilityMetricsRow.tenant_id == tenant_id)
                ).all()
            }

            runs_by_id = self._latest_runs(session, tenant_id)

            items = []
            for row in interactions:
                call_data = {}
                try:
                    payload = json.loads(row.payload_json)
                    call_data = payload.get("domain_data", {})
                    raw_status = payload.get("status") if isinstance(payload, dict) else None
                    call_status = (
                        raw_status
                        if raw_status in {"completed", "abandoned", "failed", "pending", "unknown"}
                        else "unknown"
                    )
                    started_at = payload.get("started_at")
                except Exception:
                    call_status = "unknown"
                    started_at = None

                m = metrics.get(row.interaction_id)
                run = runs_by_id.get(row.interaction_id)

                outcome_label = self._batch_value(
                    run,
                    "conversation_understanding",
                    "outcome",
                    "label",
                ) or "Can't tell"
                quality_label = (
                    run.summary.get("overall_assessment", "Can't tell")
                    if run
                    else "Can't tell"
                )
                sentiment_label = self._batch_value(
                    run,
                    "conversation_understanding",
                    "sentiment",
                    "label",
                ) or "Can't tell"
                compliance_label = self._compliance_status(run) if run else "NOT_EVALUABLE"

                # Filters
                if status and status.lower() != call_status.lower():
                    continue
                if outcome and outcome.lower() not in outcome_label.lower():
                    continue
                if quality and quality.lower() != quality_label.lower():
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
                    "duration_s": m.recording_duration_s if m else None,
                    "telephony_duration_s": m.telephony_duration_s if m else None,
                    "turns_count": m.turn_count if m else 0,
                    "outcome": outcome_label,
                    "quality": quality_label,
                    "sentiment": sentiment_label,
                    "compliance_status": compliance_label,
                    "cost": m.total_cost if m else None,
                    "currency": m.cost_currency if m else None,
                    "cost_usd": m.total_cost if m and m.cost_currency == "USD" else None,
                    "evaluations_count": len(run.batches) if run else 0,
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

    def get_interactions_selector_list(self, tenant_id: str = "health_campaign") -> List[Dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)).all()
            result = []
            for r in rows:
                folder_name = None
                try:
                    p = json.loads(r.payload_json)
                    folder_name = p.get("domain_data", {}).get("folder_name")
                except Exception:
                    pass
                display = f"{folder_name} ({r.interaction_id[:8]}...)" if folder_name else f"Call ({r.interaction_id[:8]}...)"
                result.append({
                    "interaction_id": r.interaction_id,
                    "folder_name": folder_name,
                    "display_name": display,
                })
            result.sort(key=lambda x: (x["folder_name"] or x["interaction_id"]))
            return result

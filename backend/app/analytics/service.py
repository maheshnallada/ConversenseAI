import json
import logging
from typing import Dict, Any, List, Optional
from collections import Counter
from sqlalchemy import select, func, desc
from sqlalchemy.orm import sessionmaker

from app.storage.orm import (
    InteractionRow,
    ObservabilityMetricsRow,
    EvaluationResultRow,
    InteractionTimelineRow,
)
from app.observability.calculator import calculate_percentiles
from app.storage.observability_repo import aggregate_cost_rows

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    @staticmethod
    def _latest_evaluations(session, tenant_id: str) -> list[EvaluationResultRow]:
        rows = session.scalars(
            select(EvaluationResultRow)
            .where(EvaluationResultRow.tenant_id == tenant_id)
            .order_by(desc(EvaluationResultRow.created_at), desc(EvaluationResultRow.id))
        ).all()
        selected: dict[tuple[str, str], EvaluationResultRow] = {}
        for row in rows:
            selected.setdefault((row.interaction_id, row.family), row)
        return list(selected.values())

    def get_overview_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            # Interactions count and status
            interactions = session.scalars(
                select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            ).all()

            total_interactions = len(interactions)
            completed = 0
            abandoned = 0
            failed = 0
            pending = 0
            unknown = 0
            for i in interactions:
                try:
                    payload = json.loads(i.payload_json)
                    status = payload.get("status") if isinstance(payload, dict) else None
                except Exception:
                    status = None

                if status == "completed":
                    completed += 1
                elif status == "abandoned":
                    abandoned += 1
                elif status == "failed":
                    failed += 1
                elif status == "pending":
                    pending += 1
                else:
                    unknown += 1

            # Observability metrics aggregations
            metrics_rows = session.scalars(
                select(ObservabilityMetricsRow).where(ObservabilityMetricsRow.tenant_id == tenant_id)
            ).all()

            total_cost, currency, cost_by_currency = aggregate_cost_rows(metrics_rows)
            avg_cost = (
                round(total_cost / total_interactions, 4)
                if total_cost is not None and total_interactions > 0
                else None
            )

            latency_samples: list[float] = []
            for row in metrics_rows:
                try:
                    metrics_data = json.loads(row.metrics_json)
                    samples = metrics_data.get("response_latency_samples", [])
                    if isinstance(samples, list):
                        latency_samples.extend(
                            sample
                            for sample in samples
                            if isinstance(sample, (int, float)) and sample >= 0
                        )
                except (TypeError, ValueError):
                    continue
            latency_percentiles = calculate_percentiles(latency_samples)
            legacy_averages = [
                row.avg_response_latency_s
                for row in metrics_rows
                if row.avg_response_latency_s is not None
            ]
            avg_lat = latency_percentiles.avg
            if avg_lat is None and legacy_averages:
                avg_lat = round(sum(legacy_averages) / len(legacy_averages), 3)
            p95_lat = latency_percentiles.p95

            # Evaluation results aggregations
            eval_rows = self._latest_evaluations(session, tenant_id)

            quality_counts = Counter()
            compliance_findings = {"PASSED": 0, "FAILED": 0}
            successful_outcomes = 0

            for ev in eval_rows:
                if ev.family == "quality":
                    quality_counts[ev.label or "Can't tell"] += 1
                elif ev.family == "compliance":
                    if ev.label == "FAILED":
                        compliance_findings["FAILED"] += 1
                    else:
                        compliance_findings["PASSED"] += 1
                elif ev.family == "outcome":
                    if ev.label in ["Expert call booked", "Call later agreed"]:
                        successful_outcomes += 1

            success_rate = round(successful_outcomes / total_interactions * 100, 1) if total_interactions > 0 else 0.0

            return {
                "total_interactions": total_interactions,
                "completed_interactions": completed,
                "abandoned_interactions": abandoned,
                "failed_interactions": failed,
                "pending_interactions": pending,
                "unknown_interactions": unknown,
                "successful_outcomes": successful_outcomes,
                "successful_outcomes_percentage": success_rate,
                "quality_distribution": dict(quality_counts),
                "compliance_findings": compliance_findings,
                "avg_latency_s": avg_lat,
                "p95_latency_s": p95_lat,
                "total_cost": total_cost,
                "currency": currency,
                "cost_by_currency": cost_by_currency,
                "total_cost_usd": total_cost if currency == "USD" else None,
                "avg_cost_per_interaction": avg_cost,
                "avg_cost_per_interaction_usd": avg_cost if currency == "USD" else None,
                "freshness_status": "UP_TO_DATE",
            }

    def get_quality_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            eval_rows = self._latest_evaluations(session, tenant_id)

            outcomes = Counter()
            sentiment = Counter()
            emotion = Counter()
            overall_quality = Counter()

            for ev in eval_rows:
                if ev.family == "outcome":
                    outcomes[ev.label or "Can't tell"] += 1
                elif ev.family == "experience":
                    sentiment[ev.label or "Neutral"] += 1
                    try:
                        details = json.loads(ev.details_json)
                        emotion[details.get("emotion", "Neutral")] += 1
                    except Exception:
                        emotion["Neutral"] += 1
                elif ev.family == "quality":
                    overall_quality[ev.label or "Good"] += 1

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

            eval_rows = self._latest_evaluations(session, tenant_id)

            evals_by_id: Dict[str, Dict[str, str]] = {}
            for ev in eval_rows:
                if ev.interaction_id not in evals_by_id:
                    evals_by_id[ev.interaction_id] = {}
                evals_by_id[ev.interaction_id][ev.family] = ev.label or ""

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
                e = evals_by_id.get(row.interaction_id, {})

                outcome_label = e.get("outcome", "Can't tell")
                quality_label = e.get("quality", "Good")
                sentiment_label = e.get("experience", "Neutral")
                compliance_label = e.get("compliance", "PASSED")

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
                    "evaluations_count": len(e),
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

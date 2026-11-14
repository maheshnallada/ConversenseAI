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

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def get_overview_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            # Interactions count and status
            interactions = session.scalars(
                select(InteractionRow).where(InteractionRow.tenant_id == tenant_id)
            ).all()

            total_interactions = len(interactions)
            completed = 0
            abandoned = 0
            for i in interactions:
                try:
                    payload = json.loads(i.payload_json)
                    status = payload.get("status", "completed")
                    if status == "completed":
                        completed += 1
                    else:
                        abandoned += 1
                except Exception:
                    completed += 1

            # Observability metrics aggregations
            metrics_rows = session.scalars(
                select(ObservabilityMetricsRow).where(ObservabilityMetricsRow.tenant_id == tenant_id)
            ).all()

            total_cost = sum(r.total_cost or 0.0 for r in metrics_rows)
            avg_cost = total_cost / total_interactions if total_interactions > 0 else 0.0

            latencies = [r.avg_response_latency_s for r in metrics_rows if r.avg_response_latency_s is not None]
            avg_lat = round(sum(latencies) / len(latencies), 3) if latencies else None

            p95_latencies = [r.p95_response_latency_s for r in metrics_rows if r.p95_response_latency_s is not None]
            p95_lat = round(sum(p95_latencies) / len(p95_latencies), 3) if p95_latencies else None

            # Evaluation results aggregations
            eval_rows = session.scalars(
                select(EvaluationResultRow).where(EvaluationResultRow.tenant_id == tenant_id)
            ).all()

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
                "successful_outcomes": successful_outcomes,
                "successful_outcomes_percentage": success_rate,
                "quality_distribution": dict(quality_counts),
                "compliance_findings": compliance_findings,
                "avg_latency_s": avg_lat,
                "p95_latency_s": p95_lat,
                "total_cost_usd": round(total_cost, 4),
                "avg_cost_per_interaction_usd": round(avg_cost, 4),
                "freshness_status": "UP_TO_DATE",
            }

    def get_quality_analytics(self, tenant_id: str = "health_campaign") -> Dict[str, Any]:
        with self.session_factory() as session:
            eval_rows = session.scalars(
                select(EvaluationResultRow).where(EvaluationResultRow.tenant_id == tenant_id)
            ).all()

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

            total_cost = sum(r.total_cost or 0.0 for r in metrics_rows)
            total_tokens = sum(r.total_tokens or 0 for r in metrics_rows)
            input_tokens = sum(r.input_tokens or 0 for r in metrics_rows)
            output_tokens = sum(r.output_tokens or 0 for r in metrics_rows)
            total_telephony_s = sum(r.telephony_duration_s or 0.0 for r in metrics_rows)

            llm_cost_total = 0.0
            stt_cost_total = 0.0
            tts_cost_total = 0.0
            telephony_cost_total = 0.0
            models_dict: Dict[str, Dict[str, Any]] = {}

            for r in metrics_rows:
                try:
                    m = json.loads(r.metrics_json)
                    cb = m.get("cost_breakdown", {})
                    llm_cost_total += cb.get("llm_cost", 0.0)
                    stt_cost_total += cb.get("stt_cost", 0.0)
                    tts_cost_total += cb.get("tts_cost", 0.0)
                    telephony_cost_total += cb.get("telephony_cost", 0.0)

                    model_name = m.get("llm_model") or "unknown"
                    if model_name not in models_dict:
                        models_dict[model_name] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
                    models_dict[model_name]["calls"] += 1
                    models_dict[model_name]["tokens"] += (r.total_tokens or 0)
                    models_dict[model_name]["cost_usd"] += cb.get("llm_cost", 0.0)
                except Exception:
                    pass

            return {
                "total_cost_usd": round(total_cost, 4),
                "currency": "USD",
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "llm_cost_usd": round(llm_cost_total, 4),
                "stt_cost_usd": round(stt_cost_total, 4),
                "tts_cost_usd": round(tts_cost_total, 4),
                "telephony_cost_usd": round(telephony_cost_total, 4),
                "telephony_duration_s": round(total_telephony_s, 2),
                "model_breakdown": {
                    k: {
                        "calls": v["calls"],
                        "tokens": v["tokens"],
                        "cost_usd": round(v["cost_usd"], 4),
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

            eval_rows = session.scalars(
                select(EvaluationResultRow).where(EvaluationResultRow.tenant_id == tenant_id)
            ).all()

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
                    call_status = payload.get("status", "completed")
                    started_at = payload.get("started_at")
                except Exception:
                    call_status = "completed"
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
                if search:
                    s_low = search.lower()
                    if s_low not in row.interaction_id.lower():
                        continue

                items.append({
                    "interaction_id": row.interaction_id,
                    "started_at": started_at,
                    "status": call_status,
                    "duration_s": m.recording_duration_s if m else None,
                    "telephony_duration_s": m.telephony_duration_s if m else None,
                    "turns_count": m.turn_count if m else 0,
                    "outcome": outcome_label,
                    "quality": quality_label,
                    "sentiment": sentiment_label,
                    "compliance_status": compliance_label,
                    "cost_usd": m.total_cost if m else 0.0,
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

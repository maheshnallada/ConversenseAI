import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from app.domain.observability import (
    InteractionMetrics,
    PercentilesResult,
    PlatformObservabilitySummary,
)
from app.observability.calculator import calculate_percentiles
from app.observability.config import CostBreakdown
from app.storage.orm import ObservabilityMetricsRow


class ObservabilityRepository:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def save_metrics(self, metrics: InteractionMetrics) -> None:
        now = datetime.now(timezone.utc)
        metrics_dict = {
            "tenant_id": metrics.tenant_id,
            "interaction_id": metrics.interaction_id,
            "recording_duration_s": metrics.recording_duration_s,
            "telephony_duration_s": metrics.telephony_duration_s,
            "turn_count": metrics.turn_count,
            "agent_turn_count": metrics.agent_turn_count,
            "customer_turn_count": metrics.customer_turn_count,
            "first_agent_latency_s": metrics.first_agent_latency_s,
            "response_latency_percentiles": asdict(metrics.response_latency_percentiles),
            "longest_silence_s": metrics.longest_silence_s,
            "overlap_count": metrics.overlap_count,
            "total_overlap_s": metrics.total_overlap_s,
            "audio_missing": metrics.audio_missing,
            "audio_silent": metrics.audio_silent,
            "llm_provider": metrics.llm_provider,
            "llm_model": metrics.llm_model,
            "input_tokens": metrics.input_tokens,
            "output_tokens": metrics.output_tokens,
            "total_tokens": metrics.total_tokens,
            "cost_breakdown": asdict(metrics.cost_breakdown),
        }

        with self.session_factory() as session:
            session.execute(
                delete(ObservabilityMetricsRow).where(
                    ObservabilityMetricsRow.tenant_id == metrics.tenant_id,
                    ObservabilityMetricsRow.interaction_id == metrics.interaction_id,
                )
            )

            pct = metrics.response_latency_percentiles
            row = ObservabilityMetricsRow(
                tenant_id=metrics.tenant_id,
                interaction_id=metrics.interaction_id,
                recording_duration_s=metrics.recording_duration_s,
                telephony_duration_s=metrics.telephony_duration_s,
                turn_count=metrics.turn_count,
                agent_turn_count=metrics.agent_turn_count,
                customer_turn_count=metrics.customer_turn_count,
                first_agent_latency_s=metrics.first_agent_latency_s,
                avg_response_latency_s=pct.avg,
                p50_response_latency_s=pct.p50,
                p90_response_latency_s=pct.p90,
                p95_response_latency_s=pct.p95,
                p99_response_latency_s=pct.p99,
                longest_silence_s=metrics.longest_silence_s,
                overlap_count=metrics.overlap_count,
                total_overlap_s=metrics.total_overlap_s,
                input_tokens=metrics.input_tokens,
                output_tokens=metrics.output_tokens,
                total_tokens=metrics.total_tokens,
                total_cost=metrics.cost_breakdown.total_cost,
                cost_currency=metrics.cost_breakdown.currency,
                metrics_json=json.dumps(metrics_dict),
                created_at=now,
            )
            session.add(row)
            session.commit()

    def get_metrics(self, tenant_id: str, interaction_id: str) -> InteractionMetrics | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(ObservabilityMetricsRow).where(
                    ObservabilityMetricsRow.tenant_id == tenant_id,
                    ObservabilityMetricsRow.interaction_id == interaction_id,
                )
            )
            if row is None:
                return None

            data = json.loads(row.metrics_json)
            pct_data = data.get("response_latency_percentiles") or {}
            cost_data = data.get("cost_breakdown") or {}

            return InteractionMetrics(
                tenant_id=data["tenant_id"],
                interaction_id=data["interaction_id"],
                recording_duration_s=data.get("recording_duration_s"),
                telephony_duration_s=data.get("telephony_duration_s"),
                turn_count=data.get("turn_count", 0),
                agent_turn_count=data.get("agent_turn_count", 0),
                customer_turn_count=data.get("customer_turn_count", 0),
                first_agent_latency_s=data.get("first_agent_latency_s"),
                response_latency_percentiles=PercentilesResult(**pct_data),
                longest_silence_s=data.get("longest_silence_s"),
                overlap_count=data.get("overlap_count", 0),
                total_overlap_s=data.get("total_overlap_s", 0.0),
                audio_missing=data.get("audio_missing", False),
                audio_silent=data.get("audio_silent", False),
                llm_provider=data.get("llm_provider"),
                llm_model=data.get("llm_model"),
                input_tokens=data.get("input_tokens"),
                output_tokens=data.get("output_tokens"),
                total_tokens=data.get("total_tokens"),
                cost_breakdown=CostBreakdown(**cost_data),
            )

    def get_platform_summary(self, tenant_id: str) -> PlatformObservabilitySummary:
        with self.session_factory() as session:
            rows = session.scalars(
                select(ObservabilityMetricsRow).where(
                    ObservabilityMetricsRow.tenant_id == tenant_id
                )
            ).all()

            total_interactions = len(rows)
            total_rec = sum(r.recording_duration_s or 0.0 for r in rows)
            total_tel = sum(r.telephony_duration_s or 0.0 for r in rows)
            total_turns = sum(r.turn_count for r in rows)
            total_agent = sum(r.agent_turn_count for r in rows)
            total_cust = sum(r.customer_turn_count for r in rows)
            total_overlap_cnt = sum(r.overlap_count for r in rows)
            total_overlap_dur = sum(r.total_overlap_s for r in rows)
            total_in_tok = sum(r.input_tokens or 0 for r in rows)
            total_out_tok = sum(r.output_tokens or 0 for r in rows)
            total_cost = sum(r.total_cost or 0.0 for r in rows)

            # Collect all measured p50s to compute overall distribution
            latencies = [r.p50_response_latency_s for r in rows if r.p50_response_latency_s is not None]
            overall_pct = calculate_percentiles(latencies)

            return PlatformObservabilitySummary(
                total_interactions=total_interactions,
                total_recording_duration_s=round(total_rec, 2),
                total_telephony_duration_s=round(total_tel, 2),
                total_turns=total_turns,
                total_agent_turns=total_agent,
                total_customer_turns=total_cust,
                overall_latency_percentiles=overall_pct,
                total_overlap_count=total_overlap_cnt,
                total_overlap_duration_s=round(total_overlap_dur, 2),
                total_input_tokens=total_in_tok,
                total_output_tokens=total_out_tok,
                total_cost=round(total_cost, 4),
                currency="USD",
            )


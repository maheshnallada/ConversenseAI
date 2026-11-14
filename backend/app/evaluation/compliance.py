import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.domain.timeline import ReconstructedTimeline
from app.domain.transcript import TranscriptTurn
from app.evaluation.base import BaseEvaluator


class ComplianceEvaluator(BaseEvaluator):
    evaluator_id = "compliance.never_rules"
    evaluator_version = "1.0.0"
    family = "compliance"
    method = "deterministic"

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            root = Path(__file__).resolve().parent.parent.parent.parent
            config_path = root / "configs" / "evaluators" / "health_insurance_rules.json"
        self.config_path = Path(config_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("never_rules", {})
            except Exception:
                pass
        return {
            "sensitive_data_keywords": ["aadhaar", "pan card", "pan number", "bank account", "cvv", "otp", "atm pin"],
            "premium_quote_patterns": [r"\b\d{3,6}\s*(?:rupees|rs|inr|per year|per month)\b", r"(?:rs\.?|rupees)\s*\d{3,6}"],
            "ai_denial_keywords": ["i am a human", "i am human", "i am not an ai", "i am not a robot", "main insaan hoon"],
            "appointment_rules": {
                "earliest_hour": 9,
                "latest_hour": 21,
                "allow_same_day": False,
            },
        }

    def evaluate(
        self,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
    ) -> EvaluationResult:
        evidence: list[EvidenceItem] = []

        agent_turns = [t for t in turns if t.speaker == "agent"]

        # 1. Never-Rule: Sensitive Data Request
        sens_keywords = self.rules.get("sensitive_data_keywords", [])
        for t in agent_turns:
            lower = t.normalized_text
            for kw in sens_keywords:
                if kw in lower:
                    evidence.append(
                        EvidenceItem(
                            source_type="transcript_turn",
                            reference_id=t.turn_id,
                            line_index=t.turn_index,
                            text_snippet=t.raw_text,
                            timestamp_s=t.start_s,
                            reason=f"Agent requested sensitive customer data ({kw.upper()})",
                        )
                    )

        # 2. Never-Rule: Premium Quotation
        prem_patterns = self.rules.get("premium_quote_patterns", [])
        for t in agent_turns:
            lower = t.normalized_text
            for pat in prem_patterns:
                if re.search(pat, lower):
                    evidence.append(
                        EvidenceItem(
                            source_type="transcript_turn",
                            reference_id=t.turn_id,
                            line_index=t.turn_index,
                            text_snippet=t.raw_text,
                            timestamp_s=t.start_s,
                            reason=f"Agent quoted a specific premium/price figure",
                        )
                    )

        # 3. Never-Rule: AI Identity Denial
        ai_denial_keywords = self.rules.get("ai_denial_keywords", [])
        ai_patterns = [r"\bi am (?:a |real )?human\b", r"\bnot an? (?:ai|robot)\b", r"\breal human\b"]
        for t in agent_turns:
            lower = t.normalized_text
            matched_denial = any(kw in lower for kw in ai_denial_keywords) or any(re.search(pat, lower) for pat in ai_patterns)
            if matched_denial:
                evidence.append(
                    EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=t.turn_id,
                        line_index=t.turn_index,
                        text_snippet=t.raw_text,
                        timestamp_s=t.start_s,
                        reason="Agent falsely denied being an AI / claimed to be human",
                    )
                )

        # 4. Never-Rule: Appointment Window (09:00 - 21:00)
        domain = interaction.domain_data
        domain = domain if isinstance(domain, Mapping) else {}
        meta = domain.get("meta")
        meta = meta if isinstance(meta, Mapping) else {}
        end_call = meta.get("end_call")
        end_call = end_call if isinstance(end_call, Mapping) else {}
        record = end_call.get("record")
        record = record if isinstance(record, Mapping) else {}

        appointment_rules = self.rules.get("appointment_rules")
        appointment_rules = appointment_rules if isinstance(appointment_rules, Mapping) else {}
        booking_time = record.get("time")
        time_match = (
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", booking_time)
            if isinstance(booking_time, str)
            else None
        )
        if "time" in record and time_match is None:
            evidence.append(
                EvidenceItem(
                    source_type="metadata",
                    reference_id="end_call.record.time",
                    line_index=None,
                    text_snippet=f"Booked time: {booking_time}",
                    timestamp_s=None,
                    reason="Invalid appointment time; expected HH:MM in 24-hour format",
                )
            )
        if time_match:
            hour = int(booking_time[:2])
            earliest = appointment_rules.get("earliest_hour", 9)
            latest = appointment_rules.get("latest_hour", 21)
            if hour < earliest or hour >= latest:
                evidence.append(
                    EvidenceItem(
                        source_type="metadata",
                        reference_id="end_call.record.time",
                        line_index=None,
                        text_snippet=f"Booked time: {booking_time}",
                        timestamp_s=None,
                        reason=f"Appointment booked at {booking_time}, outside permitted 9 AM–9 PM window",
                    )
                )

        appointment_date = record.get("date")
        parsed_appointment_date = None
        if isinstance(appointment_date, datetime):
            parsed_appointment_date = appointment_date.date()
        elif isinstance(appointment_date, date):
            parsed_appointment_date = appointment_date
        elif isinstance(appointment_date, str):
            try:
                parsed_appointment_date = date.fromisoformat(appointment_date.strip())
            except ValueError:
                pass

        if "date" in record and appointment_date is not None and parsed_appointment_date is None:
            evidence.append(
                EvidenceItem(
                    source_type="metadata",
                    reference_id="end_call.record.date",
                    line_index=None,
                    text_snippet=f"Booked date: {appointment_date}",
                    timestamp_s=None,
                    reason="Invalid appointment date; expected an ISO date",
                )
            )

        if appointment_rules.get("allow_same_day") is False and parsed_appointment_date:
            call_date = (
                interaction.started_at.date()
                if interaction.started_at is not None
                else datetime.now(timezone.utc).date()
            )
            if parsed_appointment_date == call_date:
                evidence.append(
                    EvidenceItem(
                        source_type="metadata",
                        reference_id="end_call.record.date",
                        line_index=None,
                        text_snippet=f"Booked date: {appointment_date}",
                        timestamp_s=None,
                        reason="Appointment booked on the call date, but same-day bookings are not permitted",
                    )
                )

        disallowed_insurers = self.rules.get("disallowed_insurers_pushing", [])
        if isinstance(disallowed_insurers, list):
            for turn in agent_turns:
                text = (turn.normalized_text or turn.raw_text or "").lower()
                for insurer in disallowed_insurers:
                    if isinstance(insurer, str) and insurer and re.search(
                        rf"\b{re.escape(insurer.lower())}\b", text
                    ):
                        evidence.append(
                            EvidenceItem(
                                source_type="transcript_turn",
                                reference_id=turn.turn_id,
                                line_index=turn.turn_index,
                                text_snippet=turn.raw_text,
                                timestamp_s=turn.start_s,
                                reason=f"Agent mentioned disallowed insurer: {insurer}",
                            )
                        )

        has_violations = len(evidence) > 0
        label = "FAILED" if has_violations else "PASSED"
        score = 0.0 if has_violations else 1.0
        review_status = "FLAGGED_FOR_REVIEW" if has_violations else "PASSED"
        severity = "high" if has_violations else "low"
        reason = (
            f"Detected {len(evidence)} compliance violation(s)"
            if has_violations
            else "No compliance violations detected"
        )

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method=self.method,
            label=label,
            score=score,
            confidence=1.0,
            severity=severity,
            review_status=review_status,
            evidence=evidence,
            reason=reason,
            details={"violation_count": len(evidence)},
        )

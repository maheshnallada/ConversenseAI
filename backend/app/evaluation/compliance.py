import json
import re
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
            "appointment_rules": {"earliest_hour": 9, "latest_hour": 21},
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
        domain = interaction.domain_data or {}
        end_call = domain.get("meta", {}).get("end_call") or {}
        record = end_call.get("record") or {}
        booking_time = record.get("time")

        if booking_time:
            try:
                # time format like "07:00" or "11:00"
                hour = int(booking_time.split(":")[0])
                earliest = self.rules.get("appointment_rules", {}).get("earliest_hour", 9)
                latest = self.rules.get("appointment_rules", {}).get("latest_hour", 21)
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
            except Exception:
                pass

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

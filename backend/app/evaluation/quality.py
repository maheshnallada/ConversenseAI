import logging
from typing import List, Optional, Dict, Any
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

logger = logging.getLogger(__name__)

OVERALL_QUALITY_VALUES = ["Good", "OK", "Bad", "Can't tell"]

class QualityEvaluator(BaseEvaluator):
    evaluator_id = "quality.scorecard"
    evaluator_version = "1.0.0"
    family = "quality"
    method = "hybrid"

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def evaluate(
        self,
        interaction: InteractionEnvelope,
        turns: List[TranscriptTurn],
        timeline: Optional[ReconstructedTimeline] = None,
        compliance_result: Optional[EvaluationResult] = None,
    ) -> EvaluationResult:
        first_wrong_line: Optional[int] = None
        first_wrong_what: Optional[str] = None
        label = "Good"
        evidence: List[EvidenceItem] = []

        # 1. Compliance Hard-Fail
        if compliance_result and compliance_result.label == "FAILED":
            label = "Bad"
            if compliance_result.evidence:
                first_wrong_line = compliance_result.evidence[0].line_index
                first_wrong_what = compliance_result.evidence[0].reason
                evidence.append(compliance_result.evidence[0])

        # 2. Latency / Opening check
        if label != "Bad" and timeline:
            if getattr(timeline, "first_agent_speech_s", 0) and timeline.first_agent_speech_s > 4.0:
                label = "OK"
                if not first_wrong_line:
                    first_wrong_line = 1
                    first_wrong_what = f"Agent initial greeting delayed ({timeline.first_agent_speech_s:.2f}s)"
                    evidence.append(EvidenceItem(
                        source_type="timeline",
                        reference_id="first_agent_speech_s",
                        line_index=1,
                        reason=first_wrong_what
                    ))

        # 3. Repetition check
        agent_turns = [t for t in turns if t.speaker == "agent"]
        if len(agent_turns) >= 2:
            texts = [(t.normalized_text or t.raw_text).strip().lower() for t in agent_turns]
            for i in range(1, len(texts)):
                if texts[i] == texts[i - 1] and len(texts[i]) > 10:
                    if label == "Good":
                        label = "OK"
                    if not first_wrong_line:
                        first_wrong_line = agent_turns[i].turn_index
                        first_wrong_what = "Repetitive agent turn verbatim"
                        evidence.append(EvidenceItem(
                            source_type="transcript_turn",
                            reference_id=agent_turns[i].turn_id,
                            line_index=first_wrong_line,
                            text_snippet=agent_turns[i].raw_text,
                            reason=first_wrong_what
                        ))

        if not turns:
            label = "Can't tell"

        score = 1.0 if label == "Good" else (0.7 if label == "OK" else 0.0)

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method=self.method,
            label=label,
            score=score,
            confidence=0.85,
            severity="high" if label == "Bad" else ("medium" if label == "OK" else "low"),
            review_status="FLAGGED_FOR_REVIEW" if label == "Bad" else "PASSED",
            evidence=evidence,
            reason=f"Overall quality: {label}." + (f" Issue: {first_wrong_what}" if first_wrong_what else ""),
            details={
                "overall_quality": label,
                "first_thing_wrong_line": first_wrong_line,
                "first_thing_wrong_what": first_wrong_what,
            },
        )

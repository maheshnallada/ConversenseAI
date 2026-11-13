import json
import logging
from typing import List, Optional, Dict, Any
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

logger = logging.getLogger(__name__)

CORRECT_OUTCOME_VALUES = [
    "Expert call booked",
    "Call later agreed",
    "Not interested",
    "Do not call",
    "Voicemail",
    "Call screener or machine",
    "No outcome: customer left first",
    "Can't tell",
]

WHAT_HAPPENED_VALUES = [
    "Machine or call screener answered",
    "Heard nothing from the agent",
    "Agent's first words came late (over 3 s)",
    "Left during the first line, said nothing",
    "Said hello or a few words, then left",
    "Gave a real answer, then left before an ending",
    "Call reached an ending",
    "Can't tell",
]

class OutcomeEvaluator(BaseEvaluator):
    evaluator_id = "outcome.intent"
    evaluator_version = "1.0.0"
    family = "outcome"
    method = "hybrid"

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def evaluate(
        self,
        interaction: InteractionEnvelope,
        turns: List[TranscriptTurn],
        timeline: Optional[ReconstructedTimeline] = None,
    ) -> EvaluationResult:
        customer_turns = [t for t in turns if t.speaker == "customer"]
        agent_turns = [t for t in turns if t.speaker == "agent"]

        # 1. Correct Outcome
        outcome_label, outcome_evidence, outcome_confidence, method = self._evaluate_correct_outcome(
            turns, customer_turns, agent_turns
        )

        # 2. What Happened
        what_label, what_evidence = self._evaluate_what_happened(
            turns, customer_turns, agent_turns, timeline
        )

        all_evidence = outcome_evidence + what_evidence

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method=method,
            label=outcome_label,
            score=1.0 if outcome_label in ["Expert call booked", "Call later agreed", "Not interested", "Do not call"] else 0.0,
            confidence=outcome_confidence,
            severity="low",
            review_status="PASSED" if outcome_label != "Can't tell" else "FLAGGED_FOR_REVIEW",
            evidence=all_evidence,
            reason=f"Outcome: {outcome_label}. Progression: {what_label}",
            details={
                "correct_outcome": outcome_label,
                "what_happened": what_label,
            },
        )

    def _evaluate_correct_outcome(
        self,
        all_turns: List[TranscriptTurn],
        customer_turns: List[TranscriptTurn],
        agent_turns: List[TranscriptTurn],
    ):
        if self.llm_client.is_live_configured:
            llm_res = self._llm_evaluate_outcome(all_turns)
            if llm_res:
                return llm_res

        # Heuristic fallback based on customer turns
        if not customer_turns:
            return "No outcome: customer left first", [], 0.95, "deterministic"

        # Check for voicemail / machine
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["beep", "leave a message", "voicemail", "call screen", "press 1"]):
                return (
                    "Voicemail",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Voicemail / automated message detected"
                    )],
                    0.95,
                    "deterministic",
                )

        # Check for Do Not Call
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["do not call", "don't call", "remove my number", "dnc", "stop calling"]):
                return (
                    "Do not call",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Explicit DNC request"
                    )],
                    0.95,
                    "deterministic",
                )

        # Check for Call Later
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["call later", "call me later", "call back later", "driving", "busy right now", "call in the evening", "after 5", "tomorrow evening"]):
                return (
                    "Call later agreed",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Customer requested callback later"
                    )],
                    0.9,
                    "deterministic",
                )

        # Check for Not Interested
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["not interested", "no need", "don't want", "already have", "nahi chahiye", "no thank you", "no thanks"]):
                return (
                    "Not interested",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Customer expressed lack of interest"
                    )],
                    0.9,
                    "deterministic",
                )

        # Check for Expert Call Booked (Customer confirmed appointment)
        for ct in reversed(customer_turns):
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["yes", "yeah", "sure", "book it", "that works", "okay tomorrow", "schedule it", "fine tomorrow", "call tomorrow"]):
                prior_agent = [at for at in agent_turns if at.turn_index < ct.turn_index]
                if prior_agent and any(w in (prior_agent[-1].normalized_text or prior_agent[-1].raw_text).lower() for w in ["expert", "consult", "call", "schedule", "tomorrow", "pm", "am"]):
                    return (
                        "Expert call booked",
                        [EvidenceItem(
                            source_type="transcript_turn",
                            reference_id=ct.turn_id,
                            line_index=ct.turn_index,
                            text_snippet=ct.raw_text,
                            reason="Customer confirmed appointment booking"
                        )],
                        0.9,
                        "deterministic",
                    )

        # If customer said minimal words (e.g. only 'hello')
        total_customer_words = sum(len(ct.raw_text.split()) for ct in customer_turns)
        if total_customer_words <= 3:
            return (
                "No outcome: customer left first",
                [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=customer_turns[0].turn_id,
                    line_index=customer_turns[0].turn_index,
                    text_snippet=customer_turns[0].raw_text,
                    reason="Customer disconnected after minimal response"
                )],
                0.8,
                "deterministic",
            )

        return "Can't tell", [], 0.5, "deterministic"

    def _evaluate_what_happened(
        self,
        all_turns: List[TranscriptTurn],
        customer_turns: List[TranscriptTurn],
        agent_turns: List[TranscriptTurn],
        timeline: Optional[ReconstructedTimeline],
    ):
        if not agent_turns:
            return "Heard nothing from the agent", []

        # If machine
        for ct in customer_turns:
            if any(k in ct.raw_text.lower() for k in ["beep", "leave a message", "voicemail", "press 1"]):
                return "Machine or call screener answered", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Machine greeting detected"
                )]

        # Check late agent opening (> 3.0s)
        if timeline and getattr(timeline, "first_agent_speech_s", 0) and timeline.first_agent_speech_s > 3.0:
            return "Agent's first words came late (over 3 s)", [EvidenceItem(
                source_type="timeline",
                reference_id="first_agent_speech_s",
                reason=f"First agent speech at {timeline.first_agent_speech_s:.2f}s"
            )]

        if not customer_turns:
            return "Left during the first line, said nothing", []

        total_customer_words = sum(len(ct.raw_text.split()) for ct in customer_turns)
        if total_customer_words <= 3 and len(customer_turns) <= 1:
            if any(w in customer_turns[0].raw_text.lower() for w in ["hello", "ha", "yes", "hi"]):
                return "Said hello or a few words, then left", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=customer_turns[0].turn_id,
                    line_index=customer_turns[0].turn_index,
                    text_snippet=customer_turns[0].raw_text,
                    reason="Minimal greeting before hangup"
                )]
            return "Left during the first line, said nothing", [EvidenceItem(
                source_type="transcript_turn",
                reference_id=customer_turns[0].turn_id,
                line_index=customer_turns[0].turn_index,
                text_snippet=customer_turns[0].raw_text,
                reason="Left during initial turn"
            )]

        # Check if reached ending
        last_turn = all_turns[-1] if all_turns else None
        last_text = last_turn.raw_text.lower() if last_turn else ""
        if any(w in last_text for w in ["thank you", "bye", "good day", "have a great day", "alright", "booked"]):
            return "Call reached an ending", [EvidenceItem(
                source_type="transcript_turn",
                reference_id=last_turn.turn_id if last_turn else "last",
                line_index=last_turn.turn_index if last_turn else None,
                text_snippet=last_turn.raw_text if last_turn else "",
                reason="Call concluded with closure"
            )]

        return "Gave a real answer, then left before an ending", [EvidenceItem(
            source_type="transcript_turn",
            reference_id=customer_turns[-1].turn_id,
            line_index=customer_turns[-1].turn_index,
            text_snippet=customer_turns[-1].raw_text,
            reason="Customer answered before disconnection"
        )]

    def _llm_evaluate_outcome(self, turns: List[TranscriptTurn]):
        transcript_str = "\n".join([f"{t.speaker.upper()} [Line {t.turn_index}]: {t.raw_text}" for t in turns])
        prompt = (
            f"Analyze this call transcript and classify the correct outcome.\n"
            f"Allowed values: {', '.join(CORRECT_OUTCOME_VALUES)}\n\n"
            f"Transcript:\n{transcript_str}\n\n"
            f"Return JSON: {{\"outcome\": \"<value>\", \"evidence_line\": <int>, \"quote\": \"<quote>\", \"reason\": \"<reason>\"}}"
        )
        res_str = self.llm_client.chat_completion([{"role": "user", "content": prompt}])
        if not res_str:
            return None
        try:
            data = json.loads(res_str)
            outcome = data.get("outcome")
            if outcome in CORRECT_OUTCOME_VALUES:
                evidence = []
                if "evidence_line" in data and "quote" in data:
                    line_idx = int(data["evidence_line"])
                    ref_id = f"turn_line_{line_idx}"
                    matching_turns = [t for t in turns if t.turn_index == line_idx]
                    if matching_turns:
                        ref_id = matching_turns[0].turn_id
                    evidence.append(EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ref_id,
                        line_index=line_idx,
                        text_snippet=data.get("quote"),
                        reason=data.get("reason", "LLM identified outcome evidence")
                    ))
                return outcome, evidence, 0.9, "llm"
        except Exception:
            pass
        return None

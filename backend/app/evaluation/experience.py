import logging
from typing import List, Optional, Dict, Any
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

logger = logging.getLogger(__name__)

SENTIMENT_VALUES = ["Positive", "Neutral", "Negative", "Can't tell"]
EMOTION_VALUES = ["Cooperative", "Confused", "Frustrated", "Disengaged", "Neutral", "Can't tell"]

class CustomerExperienceEvaluator(BaseEvaluator):
    evaluator_id = "experience.sentiment_emotion"
    evaluator_version = "1.0.0"
    family = "experience"
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

        sentiment_label, sent_evidence = self._evaluate_sentiment(customer_turns)
        emotion_label, emo_evidence = self._evaluate_emotion(customer_turns)

        all_evidence = sent_evidence + emo_evidence

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method="llm" if self.llm_client.is_live_configured else "deterministic",
            label=sentiment_label,
            score=1.0 if sentiment_label == "Positive" else (0.5 if sentiment_label == "Neutral" else 0.0),
            confidence=0.85 if sentiment_label != "Can't tell" else 0.5,
            severity="low",
            review_status="PASSED",
            evidence=all_evidence,
            reason=f"Customer sentiment: {sentiment_label}. Customer emotion: {emotion_label}.",
            details={
                "sentiment": sentiment_label,
                "emotion": emotion_label,
            },
        )

    def _evaluate_sentiment(self, customer_turns: List[TranscriptTurn]):
        if not customer_turns:
            return "Neutral", []

        frustrated_keywords = ["stop calling", "annoying", "don't call", "shut up", "idiot", "remove", "irritating", "hang up", "harass"]
        negative_keywords = ["not interested", "no need", "don't want", "already have", "nahi"]
        positive_keywords = ["yes sure", "interested", "please book", "great", "thank you", "sounds good", "sure, i am", "definitely"]

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in frustrated_keywords):
                return "Negative", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Strong negative / frustrated language"
                )]

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in positive_keywords):
                return "Positive", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Positive receptive customer language"
                )]

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in negative_keywords):
                return "Neutral", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Polite declination (neutral mood)"
                )]

        return "Neutral", []

    def _evaluate_emotion(self, customer_turns: List[TranscriptTurn]):
        if not customer_turns:
            return "Neutral", []

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["stop calling", "annoying", "told you", "harass", "angry", "why are you calling"]):
                return "Frustrated", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Frustration expressed by customer"
                )]

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["who is this", "what do you mean", "confused", "which policy", "what company"]):
                return "Confused", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Confusion or seeking clarity"
                )]

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(k in text for k in ["sure", "interested", "yes", "tell me", "options", "parents", "coverage"]):
                return "Cooperative", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Engaged and cooperative tone"
                )]

        total_words = sum(len(ct.raw_text.split()) for ct in customer_turns)
        if total_words <= 3:
            return "Disengaged", [EvidenceItem(
                source_type="transcript_turn",
                reference_id=customer_turns[0].turn_id,
                line_index=customer_turns[0].turn_index,
                text_snippet=customer_turns[0].raw_text,
                reason="Minimal disengaged interaction"
            )]

        return "Neutral", []

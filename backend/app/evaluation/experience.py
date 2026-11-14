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

        llm_result = (
            self._evaluate_with_llm(customer_turns)
            if customer_turns and self.llm_client.is_live_configured
            else None
        )
        if llm_result:
            sentiment_label, emotion_label, all_evidence = llm_result
            method = "llm"
        else:
            sentiment_label, sent_evidence = self._evaluate_sentiment(customer_turns)
            emotion_label, emo_evidence = self._evaluate_emotion(customer_turns)
            all_evidence = sent_evidence + emo_evidence
            method = "deterministic"

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method=method,
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

    def _evaluate_with_llm(self, customer_turns: List[TranscriptTurn]):
        transcript = "\n".join(
            f"[Line {turn.turn_index}] {turn.raw_text}" for turn in customer_turns
        )
        prompt = (
            "Classify the customer's overall sentiment and emotion from these customer turns only.\n"
            f"Allowed sentiment values: {', '.join(SENTIMENT_VALUES)}\n"
            f"Allowed emotion values: {', '.join(EMOTION_VALUES)}\n"
            "Return one JSON object with sentiment, emotion, sentiment_evidence_line, "
            "sentiment_quote, sentiment_reason, emotion_evidence_line, emotion_quote, "
            "and emotion_reason. Evidence line values must refer to the supplied line numbers; "
            "quotes must be exact text from that customer turn.\n\n"
            f"Customer turns:\n{transcript}"
        )
        response = self.llm_client.chat_completion([{"role": "user", "content": prompt}])
        if not response:
            return None

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Experience LLM response was not valid JSON; using deterministic classification")
            return None

        if not isinstance(data, dict):
            logger.warning("Experience LLM response was not a JSON object; using deterministic classification")
            return None

        sentiment = data.get("sentiment")
        emotion = data.get("emotion")
        if sentiment not in SENTIMENT_VALUES or emotion not in EMOTION_VALUES:
            logger.warning("Experience LLM response had invalid labels; using deterministic classification")
            return None

        evidence = []
        for prefix, label in (("sentiment", sentiment), ("emotion", emotion)):
            line_index = data.get(f"{prefix}_evidence_line")
            quote = data.get(f"{prefix}_quote")
            if type(line_index) is not int or not isinstance(quote, str) or not quote:
                continue
            matching_turn = next(
                (turn for turn in customer_turns if turn.turn_index == line_index),
                None,
            )
            if matching_turn is None or quote.casefold() not in matching_turn.raw_text.casefold():
                continue
            evidence.append(EvidenceItem(
                source_type="transcript_turn",
                reference_id=matching_turn.turn_id,
                line_index=line_index,
                text_snippet=quote,
                timestamp_s=matching_turn.start_s,
                reason=data.get(f"{prefix}_reason")
                or f"LLM identified {label.lower()} customer {prefix}",
            ))

        return sentiment, emotion, evidence

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

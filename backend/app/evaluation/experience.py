from typing import List, Literal, Optional
from pydantic import BaseModel
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

SENTIMENT_VALUES = ["Positive", "Neutral", "Negative", "Can't tell"]
EMOTION_VALUES = ["Cooperative", "Confused", "Frustrated", "Disengaged", "Neutral", "Can't tell"]

class SentimentEmotionLLMResponse(BaseModel):
    sentiment: Literal["Positive", "Neutral", "Negative", "Can't tell"]
    emotion: Literal["Cooperative", "Confused", "Frustrated", "Disengaged", "Neutral", "Can't tell"]
    sentiment_evidence_line: Optional[int]
    sentiment_quote: str
    sentiment_reason: str
    emotion_evidence_line: Optional[int]
    emotion_quote: str
    emotion_reason: str


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

    SENTIMENT_EMOTION_SYSTEM_PROMPT = """
    You are an expert customer-experience evaluator specializing in
    sentiment and emotion analysis of health-insurance voice calls.

    Your task is to independently classify the customer's overall
    sentiment and dominant emotional state using ONLY the customer's
    statements in the supplied transcript.

    Do not evaluate the agent's sentiment or emotion.

    GENERAL EVALUATION PRINCIPLES:

    1. Read all customer turns before assigning classifications.
    2. Consider the complete customer interaction, not just the
    first or last statement.
    3. Use the meaning and conversational context of customer
    statements rather than isolated keywords.
    4. Distinguish sentiment from emotion.
    5. Do not assume that declining an offer automatically means
    negative sentiment.
    6. Do not assume that agreeing automatically means positive sentiment.
    7. Do not infer emotions from punctuation or words alone.
    8. Do not invent emotional states that are not supported by
    the customer's statements.
    9. If there is insufficient evidence, return "Can't tell".

    SENTIMENT CLASSIFICATION:

    Use only these allowed values:

    - Positive:
    The customer expresses satisfaction, interest, appreciation,
    willingness, or a clearly favorable attitude.

    - Neutral:
    The customer communicates factually or responds without
    a clearly positive or negative attitude.

    - Negative:
    The customer expresses dissatisfaction, rejection,
    annoyance, disapproval, or an unfavorable attitude.

    - Can't tell:
    There is insufficient customer language to reliably
    determine sentiment.

    EMOTION CLASSIFICATION:

    Use only these allowed values:

    - Cooperative:
    The customer is willing to participate, answer questions,
    provide relevant information, or engage constructively.

    - Confused:
    The customer appears uncertain, does not understand the
    discussion, or repeatedly seeks clarification.

    - Frustrated:
    The customer expresses irritation, impatience, annoyance,
    or dissatisfaction with the interaction.

    - Disengaged:
    The customer shows little interest in continuing,
    gives minimal responses, or attempts to end the conversation.

    - Neutral:
    The customer shows no clearly identifiable emotional state.

    - Can't tell:
    There is insufficient evidence to identify the customer's emotion.

    SENTIMENT AND EMOTION MUST BE INDEPENDENT:

    Examples:

    Customer: "Thank you, but I already have insurance."
    Sentiment: Neutral
    Emotion: Cooperative

    Customer: "I don't understand why you keep asking me this."
    Sentiment: Negative
    Emotion: Confused or Frustrated, depending on context

    Customer: "Please don't call me again."
    Sentiment: Negative
    Emotion: Disengaged

    Customer: "Yes, please arrange the consultation."
    Sentiment: Positive
    Emotion: Cooperative

    OVERALL CLASSIFICATION:

    1. Consider the full sequence of customer turns.
    2. Identify the dominant sentiment across the interaction.
    3. Identify the dominant emotional state across the interaction.
    4. Do not allow one isolated statement to dominate the
    classification unless it is the only meaningful evidence.
    5. When customer behavior changes during the call, consider
    which state best represents the overall interaction.

    EVIDENCE REQUIREMENTS:

    For sentiment and emotion separately:

    1. Select the most representative customer statement.
    2. Return its exact transcript line number.
    3. Copy the exact customer statement as the quote.
    4. Explain why the statement supports the classification.
    5. Never cite an agent line as customer evidence.
    6. Never fabricate or paraphrase the evidence quote.
    7. If evidence is insufficient, return null for the line number
    and an empty string for the quote.

    """


    @staticmethod
    def build_sentiment_emotion_prompt(transcript, sentiment_values, emotion_values):
        return f"""
    Evaluate the customer's sentiment and emotion.

    ALLOWED SENTIMENT VALUES:
    {', '.join(sentiment_values)}

    ALLOWED EMOTION VALUES:
    {', '.join(emotion_values)}

    CUSTOMER TURNS:
    {transcript}
    """


    def _evaluate_with_llm(self, customer_turns: List[TranscriptTurn]):
        transcript = "\n".join(
            f"[Line {turn.turn_index}] {turn.raw_text}" for turn in customer_turns
        )
        response = self.llm_client.chat_completion(
            [
                {"role": "system", "content": self.SENTIMENT_EMOTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self.build_sentiment_emotion_prompt(
                        transcript,
                        SENTIMENT_VALUES,
                        EMOTION_VALUES,
                    ),
                },
            ],
            response_format=SentimentEmotionLLMResponse,
        )
        if not isinstance(response, SentimentEmotionLLMResponse):
            return None

        sentiment = response.sentiment
        emotion = response.emotion

        evidence = []
        for label, line_index, quote, reason in (
            (
                "sentiment",
                response.sentiment_evidence_line,
                response.sentiment_quote,
                response.sentiment_reason,
            ),
            (
                "emotion",
                response.emotion_evidence_line,
                response.emotion_quote,
                response.emotion_reason,
            ),
        ):
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
                reason=reason or f"LLM identified {label.lower()} customer experience",
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

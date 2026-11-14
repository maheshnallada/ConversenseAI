import re
from typing import List, Literal, Optional
from pydantic import BaseModel
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

class OutcomeLLMResponse(BaseModel):
    outcome: Literal[
        "Expert call booked",
        "Call later agreed",
        "Not interested",
        "Do not call",
        "Voicemail",
        "Call screener or machine",
        "No outcome: customer left first",
        "Can't tell",
    ]
    evidence_line: Optional[int]
    quote: str
    reason: str


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

        # Explicit voicemail language takes precedence over general machine indicators.
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(
                re.search(pattern, text)
                for pattern in (
                    r"\bvoicemail\b",
                    r"\bvoice mail\b",
                    r"\bleave (?:a|your) message\b",
                    r"\bafter (?:the )?(?:tone|beep)\b",
                )
            ):
                return (
                    "Voicemail",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Voicemail indicator detected"
                    )],
                    0.95,
                    "deterministic",
                )

        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(
                re.search(pattern, text)
                for pattern in (
                    r"\bcall (?:is )?(?:being )?screened\b",
                    r"\bcall[\s-]+screen(?:ing|ed)?\b",
                    r"\bscreening (?:call|system)\b",
                    r"\bpress 1\b",
                    r"\banswering machine\b",
                    r"\bautomated (?:recording|message|system|attendant)\b",
                    r"\brecorded (?:message|machine|system)\b",
                )
            ):
                return (
                    "Call screener or machine",
                    [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Call-screening or recorded-machine indicator detected"
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
            is_confirmation = bool(
                re.fullmatch(
                    r"\s*(?:yes|yeah|yep|sure|okay|ok|fine)(?:\s*,?\s*please)?[.! ]*",
                    text,
                )
                or re.search(
                    r"\b(?:that|it|today|tomorrow|this (?:morning|afternoon|evening)) works\b"
                    r"|\b(?:book|schedule) it\b"
                    r"|\b(?:i can|i will|i'll) do that\b",
                    text,
                )
            )
            if is_confirmation:
                prior_turns = [at for at in all_turns if at.turn_index < ct.turn_index]
                prior_turn = max(prior_turns, key=lambda at: at.turn_index) if prior_turns else None
                if prior_turn is None or prior_turn.speaker != "agent":
                    continue
                proposal_text = (prior_turn.normalized_text or prior_turn.raw_text).lower()
                explicit_appointment = re.search(
                    r"\b(?:schedule|book|arrange|set up|reserve)\b", proposal_text
                ) and re.search(
                    r"\b(?:expert|consult(?:ation)?|call|appointment|slot)\b", proposal_text
                )
                explicit_time = re.search(
                    r"\b(?:today|tomorrow|this (?:morning|afternoon|evening)|"
                    r"next (?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
                    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
                    r"|\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
                    proposal_text,
                )
                if explicit_appointment and explicit_time:
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
            text = (ct.normalized_text or ct.raw_text).lower()
            if any(
                re.search(pattern, text)
                for pattern in (
                    r"\bvoicemail\b",
                    r"\bvoice mail\b",
                    r"\bleave (?:a|your) message\b",
                    r"\bafter (?:the )?(?:tone|beep)\b",
                    r"\bcall (?:is )?(?:being )?screened\b",
                    r"\bcall[\s-]+screen(?:ing|ed)?\b",
                    r"\bscreening (?:call|system)\b",
                    r"\bpress 1\b",
                    r"\banswering machine\b",
                    r"\bautomated (?:recording|message|system|attendant)\b",
                    r"\brecorded (?:message|machine|system)\b",
                )
            ):
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

    OUTCOME_SYSTEM_PROMPT = """
            You are an expert conversation evaluator specializing in
            health-insurance customer calls.

            Your task is to determine the actual outcome of a customer call
            by carefully analyzing the supplied conversation transcript.

            You must classify what actually happened, not what the agent
            intended to happen or what the system expected to happen.

            EVALUATION PRINCIPLES:

            1. Read the entire transcript before making a decision.
            2. Consider both agent and customer statements.
            3. Prioritize the customer's explicit statements and decisions.
            4. Distinguish between customer interest, callback agreement,
            expert-call booking, rejection, and call abandonment.
            5. Do not assume that an appointment was booked merely because
            the agent said it would be booked.
            6. Do not interpret a polite acknowledgment such as "okay",
            "fine", or "hmm" as explicit consent without sufficient context.
            7. A callback request is not automatically an expert-call booking.
            8. If the customer leaves before a meaningful outcome is reached,
            classify it as customer left first.
            9. Do not infer an outcome from missing information.
            10. If the transcript does not provide sufficient evidence,
                return "Can't tell".

            OUTCOME CLASSIFICATION GUIDELINES:

            Use only the supplied allowed outcome values.

            Determine the outcome using these distinctions:

            - Expert call booked:
            The customer explicitly agrees to an expert consultation or
            appointment, and the conversation establishes that booking.

            - Call later agreed:
            The customer agrees to be contacted later, but an expert
            appointment is not established.

            - Not interested:
            The customer clearly declines the offer or expresses no interest.

            - Do not call:
            The customer explicitly requests that they not be contacted again.

            - Voicemail:
            The call reaches a voicemail system or voicemail greeting.

            - Call screener or machine:
            A machine, automated answering system, or call-screening
            service answers instead of the intended customer.

            - No outcome: customer left first:
            The customer disconnects or leaves before a meaningful outcome
            is established.

            - Can't tell:
            The available transcript is insufficient or ambiguous.

            EVIDENCE REQUIREMENTS:

            1. Provide the line number that most directly supports the outcome.
            2. The evidence quote must be copied exactly from that line.
            3. Do not combine multiple lines into a fabricated quote.
            4. If the outcome depends on multiple statements, choose the
            most decisive statement as primary evidence.
            5. If no reliable evidence exists, use null for evidence_line
            and an empty string for quote.
            6. Explain briefly why the evidence supports the classification.

            IMPORTANT:
            - Do not invent appointment dates, times, consent, or booking status.
            - Do not treat agent claims as proof of customer agreement.
            - Do not use external assumptions or information outside the transcript.
            """


    @staticmethod
    def build_outcome_prompt(transcript_str, allowed_values):
        return f"""
            Evaluate the following customer call transcript.

            ALLOWED OUTCOME VALUES:
            {', '.join(allowed_values)}

            TRANSCRIPT:
            {transcript_str}
            """


    def _llm_evaluate_outcome(self, turns: List[TranscriptTurn]):
        transcript_str = "\n".join([f"{t.speaker.upper()} [Line {t.turn_index}]: {t.raw_text}" for t in turns])
        response = self.llm_client.chat_completion(
            [
                {"role": "system", "content": self.OUTCOME_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self.build_outcome_prompt(transcript_str, CORRECT_OUTCOME_VALUES),
                },
            ],
            response_format=OutcomeLLMResponse,
        )
        if not isinstance(response, OutcomeLLMResponse):
            return None

        evidence = []
        if response.evidence_line is not None and response.quote:
            matching_turn = next(
                (turn for turn in turns if turn.turn_index == response.evidence_line),
                None,
            )
            if matching_turn and response.quote in matching_turn.raw_text:
                evidence.append(
                    EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=matching_turn.turn_id,
                        line_index=response.evidence_line,
                        text_snippet=response.quote,
                        reason=response.reason or "LLM identified outcome evidence",
                    )
                )
        return response.outcome, evidence, 0.9, "llm"

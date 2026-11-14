import re
import logging
from typing import List, Optional, Dict, Any
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult, EvidenceItem
from app.evaluation.base import BaseEvaluator
from app.evaluation.llm_client import LLMClient

logger = logging.getLogger(__name__)

class FactsExtractionEvaluator(BaseEvaluator):
    evaluator_id = "facts.extraction"
    evaluator_version = "1.0.0"
    family = "facts"
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
        evidence: List[EvidenceItem] = []
        details: Dict[str, Any] = {}

        # 1. Existing Policy
        policy_label, policy_ev = self._extract_policy(customer_turns)
        if policy_label:
            details["existing_policy"] = policy_label
            evidence.extend(policy_ev)

        # 2. Who Needs Cover
        family_label, family_ev = self._extract_who_needs_cover(customer_turns)
        if family_label:
            details["who_needs_cover"] = family_label
            evidence.extend(family_ev)

        # 3. City / Location
        city_label, city_ev = self._extract_city(customer_turns)
        if city_label:
            details["city"] = city_label
            evidence.extend(city_ev)

        # 4. Callback / Booking time
        time_label, time_ev = self._extract_callback_time(customer_turns)
        if time_label:
            details["callback_time"] = time_label
            evidence.extend(time_ev)

        has_facts = len(details) > 0

        return EvaluationResult(
            tenant_id=interaction.tenant_id,
            interaction_id=interaction.interaction_id,
            evaluator_id=self.evaluator_id,
            evaluator_version=self.evaluator_version,
            family=self.family,
            method=self.method,
            label="FACTS_EXTRACTED" if has_facts else "NO_FACTS",
            score=1.0 if has_facts else 0.0,
            confidence=0.9 if has_facts else 1.0,
            severity="low",
            review_status="PASSED",
            evidence=evidence,
            reason=f"Extracted {len(details)} facts from customer utterances" if has_facts else "No facts provided by customer",
            details=details,
        )

    def _extract_policy(self, customer_turns: List[TranscriptTurn]):
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            if "no policy" in text or "don't have" in text or "none" in text:
                return "None", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Customer stated no active policy"
                )]
            if "company" in text or "corporate" in text or "employer" in text:
                return "Company policy", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Customer mentioned company/corporate cover"
                )]
            if "own" in text or "individual" in text or "personal" in text or "private" in text:
                return "Own policy", [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason="Customer mentioned individual/own cover"
                )]
        return None, []

    def _extract_who_needs_cover(self, customer_turns: List[TranscriptTurn]):
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            mentions = []
            if "parent" in text or "mother" in text or "father" in text:
                mentions.append("Parents")
            if "wife" in text or "spouse" in text or "husband" in text:
                mentions.append("Spouse")
            if "kid" in text or "child" in text or "son" in text or "daughter" in text:
                mentions.append("Children")
            self_reference_patterns = (
                r"\bself\b",
                r"\bmyself\b",
                r"\bfor me\b",
                r"\bme personally\b",
                r"\bmy (?:own )?(?:health )?(?:insurance|policy|cover)\b",
                r"\bi (?:need|want|am looking for|would like)\b.{0,40}\b(?:health )?(?:insurance|policy|cover)\b",
            )
            if any(re.search(pattern, text) for pattern in self_reference_patterns):
                mentions.append("Self")
            if "family" in text:
                mentions.append("Family")
            if mentions:
                label = ", ".join(dict.fromkeys(mentions))
                return label, [EvidenceItem(
                    source_type="transcript_turn",
                    reference_id=ct.turn_id,
                    line_index=ct.turn_index,
                    text_snippet=ct.raw_text,
                    reason=f"Customer indicated cover for: {label}"
                )]
        return None, []

    def _extract_city(self, customer_turns: List[TranscriptTurn]):
        cities = ["mumbai", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "pune", "ahmedabad", "jaipur", "lucknow", "chandigarh", "noida", "gurgaon"]
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            for city in cities:
                if re.search(rf"\b{city}\b", text):
                    matched = city.capitalize()
                    return matched, [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason=f"Customer stated city: {matched}"
                    )]
        return None, []

    def _extract_callback_time(self, customer_turns: List[TranscriptTurn]):
        time_patterns = [
            r"\b(?:tomorrow|today|evening|morning|afternoon)\b",
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
            r"\bafter\s+\d{1,2}\b"
        ]
        for ct in customer_turns:
            text = (ct.normalized_text or ct.raw_text).lower()
            for pat in time_patterns:
                m = re.search(pat, text)
                if m:
                    return m.group(0).strip(), [EvidenceItem(
                        source_type="transcript_turn",
                        reference_id=ct.turn_id,
                        line_index=ct.turn_index,
                        text_snippet=ct.raw_text,
                        reason="Callback time requested by customer"
                    )]
        return None, []

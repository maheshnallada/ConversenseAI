import logging
from typing import List, Dict, Any, Optional
from app.domain.envelope import InteractionEnvelope
from app.domain.transcript import TranscriptTurn
from app.domain.timeline import ReconstructedTimeline
from app.domain.evaluation import EvaluationResult
from app.evaluation.compliance import ComplianceEvaluator
from app.evaluation.outcome import OutcomeEvaluator
from app.evaluation.experience import CustomerExperienceEvaluator
from app.evaluation.quality import QualityEvaluator
from app.evaluation.facts import FactsExtractionEvaluator
from app.evaluation.llm_client import LLMClient

logger = logging.getLogger(__name__)

class EvaluatorRegistry:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.compliance_evaluator = ComplianceEvaluator()
        self.outcome_evaluator = OutcomeEvaluator(llm_client=self.llm_client)
        self.experience_evaluator = CustomerExperienceEvaluator(llm_client=self.llm_client)
        self.quality_evaluator = QualityEvaluator(llm_client=self.llm_client)
        self.facts_evaluator = FactsExtractionEvaluator(llm_client=self.llm_client)

    def evaluate_all(
        self,
        interaction: InteractionEnvelope,
        turns: List[TranscriptTurn],
        timeline: Optional[ReconstructedTimeline] = None,
    ) -> List[EvaluationResult]:
        """
        Runs all evaluators across the interaction envelope, turns, and reconstructed timeline.
        """
        results: List[EvaluationResult] = []

        # 1. Compliance (Never-rules)
        comp_res = self.compliance_evaluator.evaluate(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
        )
        results.append(comp_res)

        # 2. Outcome & Progression
        outcome_res = self.outcome_evaluator.evaluate(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
        )
        results.append(outcome_res)

        # 3. Customer Experience (Sentiment & Emotion)
        exp_res = self.experience_evaluator.evaluate(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
        )
        results.append(exp_res)

        # 4. Conversation Quality (Overall score, first problem)
        qual_res = self.quality_evaluator.evaluate(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
            compliance_result=comp_res,
        )
        results.append(qual_res)

        # 5. Customer Facts Extraction
        facts_res = self.facts_evaluator.evaluate(
            interaction=interaction,
            turns=turns,
            timeline=timeline,
        )
        results.append(facts_res)

        return results

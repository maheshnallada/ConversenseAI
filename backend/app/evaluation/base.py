from abc import ABC, abstractmethod
from typing import Any

from app.domain.envelope import InteractionEnvelope
from app.domain.evaluation import EvaluationFamily, EvaluationMethod, EvaluationResult
from app.domain.timeline import ReconstructedTimeline
from app.domain.transcript import TranscriptTurn


class BaseEvaluator(ABC):
    evaluator_id: str
    evaluator_version: str = "1.0.0"
    family: EvaluationFamily
    method: EvaluationMethod

    @abstractmethod
    def evaluate(
        self,
        interaction: InteractionEnvelope,
        turns: list[TranscriptTurn],
        timeline: ReconstructedTimeline | None = None,
    ) -> EvaluationResult:
        pass


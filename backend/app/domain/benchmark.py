from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class MetricScores:
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    support: int

@dataclass
class ConfusionMatrix:
    labels: List[str]
    # matrix[actual][predicted] = count
    matrix: Dict[str, Dict[str, int]] = field(default_factory=dict)

@dataclass
class BenchmarkReport:
    total_interactions: int
    dimension_metrics: Dict[str, MetricScores] = field(default_factory=dict)
    confusion_matrices: Dict[str, ConfusionMatrix] = field(default_factory=dict)
    compliance_false_negatives: int = 0
    compliance_false_positives: int = 0
    abstention_rate: float = 0.0
    summary_notes: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


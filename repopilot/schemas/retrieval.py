from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RetrievalLevel(str, Enum):
    LIGHT = "LIGHT"
    LOCAL = "LOCAL"
    GLOBAL = "GLOBAL"


@dataclass
class RetrievalDecision:
    retrieval_level: RetrievalLevel
    search_targets: list[str] = field(default_factory=list)
    reason: str = ""
    decision_reasons: list[str] = field(default_factory=list)
    risk_level: str = "low"
    confidence: float = 0.0
    summary: str = ""
    source: str = "heuristic"
    fallback_used: bool = False

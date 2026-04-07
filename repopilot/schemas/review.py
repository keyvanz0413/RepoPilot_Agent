from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewReport:
    decision: str
    findings: list[str] = field(default_factory=list)
    summary: str = ""

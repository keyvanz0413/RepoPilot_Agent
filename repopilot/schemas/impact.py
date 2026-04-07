from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SymbolReference:
    path: str
    line: int
    text: str


@dataclass
class ImpactReport:
    target: str
    matched_symbol: str | None = None
    risk_level: str = "low"
    affected_files: list[str] = field(default_factory=list)
    references: list[SymbolReference] = field(default_factory=list)
    related_tests: list[str] = field(default_factory=list)
    impact_reasons: list[str] = field(default_factory=list)
    summary: str = ""

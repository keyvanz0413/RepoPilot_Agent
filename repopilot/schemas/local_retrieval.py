from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalSnippet:
    path: str
    line: int
    text: str


@dataclass
class LocalRetrievalReport:
    queries: list[str] = field(default_factory=list)
    matched_files: list[str] = field(default_factory=list)
    snippets: list[RetrievalSnippet] = field(default_factory=list)
    inspected_files: list[str] = field(default_factory=list)
    summary: str = ""

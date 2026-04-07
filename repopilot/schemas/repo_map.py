from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepoNode:
    path: str
    node_type: str
    summary: str
    symbols: list[str] = field(default_factory=list)


@dataclass
class RepoMap:
    root: str
    entrypoints: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    nodes: list[RepoNode] = field(default_factory=list)
    summary: str = ""

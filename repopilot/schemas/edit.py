from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EditResult:
    applied: bool
    changed_files: list[str] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    original_contents: dict[str, str] = field(default_factory=dict)

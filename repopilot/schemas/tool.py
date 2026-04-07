from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    summary: str
    data: dict = field(default_factory=dict)

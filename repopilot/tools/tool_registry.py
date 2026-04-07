from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from repopilot.schemas.tool import ToolResult
from repopilot.tools.safety_guard import SafetyError, SafetyGuard


@dataclass
class RegisteredTool:
    name: str
    handler: Callable[..., dict]
    read_only: bool = False


class ToolRegistry:
    def __init__(self, safety_guard: SafetyGuard) -> None:
        self.safety_guard = safety_guard
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, handler: Callable[..., dict], read_only: bool = False) -> None:
        self._tools[name] = RegisteredTool(name=name, handler=handler, read_only=read_only)

    def run(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools[name]
        try:
            if name == "run_test":
                self.safety_guard.ensure_command_allowed(kwargs["command"])
            if name == "read_file":
                self.safety_guard.ensure_path_allowed(kwargs["path"])
            result = tool.handler(**kwargs)
            return ToolResult(
                tool_name=name,
                ok=True,
                summary=f"{name} completed",
                data=result,
            )
        except (SafetyError, KeyError, OSError, RuntimeError, ValueError) as exc:
            return ToolResult(
                tool_name=name,
                ok=False,
                summary=str(exc),
                data={},
            )

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecoveryAction:
    action: str
    next_state: str
    reason: str
    rollback_files: list[str] = field(default_factory=list)
    replan_required: bool = False

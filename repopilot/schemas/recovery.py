from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecoveryAction:
    action: str
    next_state: str
    reason: str

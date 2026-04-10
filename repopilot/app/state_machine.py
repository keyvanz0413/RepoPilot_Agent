from __future__ import annotations

from repopilot.schemas.enums import RunState


TERMINAL_STATES = {RunState.DONE, RunState.FAILED}


def next_state(current: RunState) -> RunState:
    transitions = {
        RunState.INIT: RunState.TASK_INTAKE,
        RunState.TASK_INTAKE: RunState.RETRIEVE,
        RunState.RETRIEVE: RunState.PLAN,
        RunState.PLAN: RunState.ACT,
        RunState.ACT: RunState.VERIFY,
    }
    return transitions.get(current, RunState.FAILED)

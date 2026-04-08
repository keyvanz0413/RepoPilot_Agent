from __future__ import annotations

from repopilot.schemas.enums import RunState


TERMINAL_STATES = {RunState.DONE, RunState.FAILED}


def next_state(current: RunState) -> RunState:
    transitions = {
        RunState.INIT: RunState.ANALYZE_TASK,
        RunState.ANALYZE_TASK: RunState.DECIDE_RETRIEVAL,
        RunState.DECIDE_RETRIEVAL: RunState.LOCAL_RETRIEVE,
        RunState.LOCAL_RETRIEVE: RunState.VALIDATE_CONTRACT,
        RunState.ESCALATE_RETRIEVAL: RunState.MAP_REPO,
        RunState.MAP_REPO: RunState.VALIDATE_CONTRACT,
        RunState.VALIDATE_CONTRACT: RunState.ANALYZE_IMPACT,
        RunState.ANALYZE_IMPACT: RunState.PLAN,
        RunState.PLAN: RunState.EDIT,
        RunState.EDIT: RunState.TEST,
        RunState.TEST: RunState.REVIEW,
    }
    return transitions.get(current, RunState.FAILED)

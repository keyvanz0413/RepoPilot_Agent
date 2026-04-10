from enum import Enum


class RunState(str, Enum):
    INIT = "INIT"
    TASK_INTAKE = "TASK_INTAKE"
    RETRIEVE = "RETRIEVE"
    PLAN = "PLAN"
    ACT = "ACT"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"
    DONE = "DONE"
    FAILED = "FAILED"

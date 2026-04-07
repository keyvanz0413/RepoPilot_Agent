from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FunctionContract:
    path: str
    symbol: str
    parameters: list[str] = field(default_factory=list)
    return_type: str | None = None


@dataclass
class ContractReport:
    target: str
    matched_symbol: str | None = None
    matched_files: list[str] = field(default_factory=list)
    function_contracts: list[FunctionContract] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    summary: str = ""

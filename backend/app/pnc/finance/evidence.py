"""Typed evidence attached to every calculation so any number can be traced and re-computed."""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ENGINE_VERSION = "1.0.0"
_NAMESPACE = uuid.UUID("5d1c3f7e-0b52-4c7e-9a64-2a6f1d8b9e10")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class Evidence(BaseModel):
    """Evidence schema: ``{calculation_id, as_of_date, source_type, inputs, assumptions, formula_steps,
    intermediate_values, results, missing_inputs, limitations, engine_version}`` plus ``name`` and ``units``.

    Rate convention: all rates inside the engine are decimal fractions (0.07 = 7%); API boundaries use ``*_pct``.
    Money is ``Decimal`` serialised as a string; dates are ISO-8601; timestamps elsewhere are UTC.
    """

    model_config = ConfigDict(frozen=True)

    calculation_id: str
    name: str
    as_of_date: date
    source_type: str
    inputs: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list)
    formula_steps: list[str] = Field(default_factory=list)
    intermediate_values: dict[str, Any] = Field(default_factory=dict)
    results: dict[str, Any]
    units: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    engine_version: str = ENGINE_VERSION


def make_evidence(name: str, as_of: date, inputs: dict, results: dict, *, formula_steps=(), intermediates=None,
                  assumptions=(), missing=(), limitations=(), units=None, source_type: str = "caller_supplied") -> Evidence:
    ins = _jsonable(inputs)
    cid = uuid.uuid5(_NAMESPACE, json.dumps([name, as_of.isoformat(), ins, ENGINE_VERSION], sort_keys=True))
    return Evidence(
        calculation_id=str(cid), name=name, as_of_date=as_of, source_type=source_type, inputs=ins,
        assumptions=list(assumptions), formula_steps=list(formula_steps), intermediate_values=_jsonable(intermediates or {}),
        results=_jsonable(results), units=units or {}, missing_inputs=list(missing), limitations=list(limitations),
    )

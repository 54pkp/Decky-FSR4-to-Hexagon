#!/usr/bin/env python3
"""Replay a bounded, synthetic same-frame lifecycle on the CPU.

This host-only harness validates request/completion identity and delegates the
numerical operation to the H3 spatial reference.  It is not an FSR4, HTP,
device, or game validation.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Any


SCHEMA_VERSION = "host-synthetic-lifecycle-v1"
BACKEND = "cpu_reference"
MAX_SCENARIO_BYTES = 1 << 20
MAX_JSON_INTEGER_DIGITS = 1_000
MAX_ID_CHARACTERS = 128
MAX_DECIMAL_DIGITS = 20

_FIXED_ID_FIELDS = (
    "service_instance_id",
    "session_id",
    "context_id",
    "history_generation",
    "model_manifest_id",
)
_IDENTITY_FIELDS = (
    "service_instance_id",
    "session_id",
    "context_id",
    "frame_id",
    "history_generation",
    "model_manifest_id",
)
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "example_only",
        "production_ready",
        "validation_gate",
        "backend",
        "manifest_id",
        "context",
        "request",
        "history",
        "motion_vectors",
        "expected_output",
    }
)


class LifecycleInvalid(Exception):
    """The lifecycle contract or an identity transition is invalid."""


class LifecycleInputError(Exception):
    """The scenario input could not be read or decoded safely."""


def _load_model_dependency(module_name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "model" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"h4_{module_name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


model_manifest = _load_model_dependency("manifest")
spatial_reference = _load_model_dependency("spatial_reference")


def _fail(path: str, message: str) -> None:
    raise LifecycleInvalid(f"{path}: {message}")


def _object(value: Any, path: str, fields: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    unknown = sorted(set(value) - fields)
    if unknown:
        _fail(f"{path}.{unknown[0]}", "unknown field")
    missing = sorted(fields - set(value))
    if missing:
        _fail(f"{path}.{missing[0]}", "required field is missing")
    return value


def _nonempty_id(value: Any, path: str) -> str:
    if type(value) is not str or not value or not value.strip():
        _fail(path, "must be a non-empty string")
    if len(value) > MAX_ID_CHARACTERS:
        _fail(path, f"must contain at most {MAX_ID_CHARACTERS} characters")
    return value


def _decimal_id(value: Any, path: str) -> str:
    if type(value) is not str:
        _fail(path, "must be a canonical non-negative decimal string")
    if value != "0" and (not value or value[0] == "0"):
        _fail(path, "must be a canonical non-negative decimal string")
    if not value.isascii() or not value.isdecimal():
        _fail(path, "must be a canonical non-negative decimal string")
    if len(value) > MAX_DECIMAL_DIGITS:
        _fail(path, f"must contain at most {MAX_DECIMAL_DIGITS} digits")
    return value


def _identity(value: Any, path: str, *, fixed: bool = False) -> dict[str, str]:
    fields = _FIXED_ID_FIELDS if fixed else _IDENTITY_FIELDS
    result = _object(value, path, frozenset(fields))
    for field in fields:
        field_path = f"{path}.{field}"
        if field in ("frame_id", "history_generation"):
            _decimal_id(result[field], field_path)
        else:
            _nonempty_id(result[field], field_path)
    return dict(result)


class LifecycleContext:
    """One context with at most one submitted request awaiting completion."""

    def __init__(self, manifest: Any, identity: Any):
        try:
            model_manifest.validate_manifest(manifest)
        except model_manifest.ManifestInvalid as exc:
            raise LifecycleInvalid(f"manifest: {exc}") from exc
        self._identity = _identity(identity, "context", fixed=True)
        manifest_id = manifest["model_manifest_id"]
        if self._identity["model_manifest_id"] != manifest_id:
            _fail(
                "context.model_manifest_id",
                f"must equal validated manifest id {manifest_id!r}",
            )
        self._active_identity: dict[str, str] | None = None
        self._active_output: list[list[int | None]] | None = None
        self._last_completed_frame: int | None = None
        self._lock = threading.RLock()

    @property
    def active_identity(self) -> dict[str, str] | None:
        with self._lock:
            return None if self._active_identity is None else dict(self._active_identity)

    @property
    def last_completed_frame_id(self) -> str | None:
        with self._lock:
            if self._last_completed_frame is None:
                return None
            return str(self._last_completed_frame)

    def submit(self, request: Any, history: Any, motion_vectors: Any) -> None:
        checked = _identity(request, "request")
        with self._lock:
            if self._active_identity is not None:
                _fail("request", "context already has an active request")
            for field in _FIXED_ID_FIELDS:
                if checked[field] != self._identity[field]:
                    _fail(f"request.{field}", "does not match the bound context identity")
            frame_number = int(checked["frame_id"])
            if self._last_completed_frame is not None and frame_number <= self._last_completed_frame:
                _fail("request.frame_id", "must be strictly greater than last completed frame")
            try:
                history_snapshot = copy.deepcopy(history)
                motion_snapshot = copy.deepcopy(motion_vectors)
            except RecursionError as exc:
                raise LifecycleInvalid(
                    "request payload: nesting exceeds snapshot limit"
                ) from exc
            try:
                output = spatial_reference.reproject_backward(
                    history_snapshot, motion_snapshot
                )
            except spatial_reference.SpatialReferenceInvalid as exc:
                raise LifecycleInvalid(f"request payload: {exc}") from exc
            self._active_identity = checked
            self._active_output = output

    def complete(self, completion: Any) -> list[list[int | None]]:
        checked = _identity(completion, "completion")
        with self._lock:
            if self._active_identity is None:
                _fail("completion", "there is no active request")
            for field in _IDENTITY_FIELDS:
                if checked[field] != self._active_identity[field]:
                    _fail(f"completion.{field}", "does not match the active request identity")
            output = self._active_output
            assert output is not None
            self._last_completed_frame = int(checked["frame_id"])
            self._active_identity = None
            self._active_output = None
            return output


def _validate_expected_grid(value: Any, actual: list[list[int | None]]) -> None:
    if not isinstance(value, list) or len(value) != len(actual):
        _fail("$.expected_output", "dimensions must match the CPU output")
    for y, (row, actual_row) in enumerate(zip(value, actual)):
        if not isinstance(row, list) or len(row) != len(actual_row):
            _fail(f"$.expected_output[{y}]", "dimensions must match the CPU output")
        for x, item in enumerate(row):
            if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
                _fail(f"$.expected_output[{y}][{x}]", "must be an integer or null")


def validate_scenario(manifest: Any, value: Any) -> list[list[int | None]]:
    """Validate and execute one closed synthetic request/completion scenario."""

    scenario = _object(value, "$", _ROOT_FIELDS)
    fixed = {
        "schema_version": SCHEMA_VERSION,
        "example_only": True,
        "production_ready": False,
        "validation_gate": "not_run",
        "backend": BACKEND,
    }
    for field, expected in fixed.items():
        if scenario[field] != expected or type(scenario[field]) is not type(expected):
            _fail(f"$.{field}", f"must equal {expected!r}")

    try:
        model_manifest.validate_manifest(manifest)
    except model_manifest.ManifestInvalid as exc:
        raise LifecycleInvalid(f"manifest: {exc}") from exc
    manifest_id = _nonempty_id(scenario["manifest_id"], "$.manifest_id")
    if manifest_id != manifest["model_manifest_id"]:
        _fail("$.manifest_id", "must equal the validated model_manifest_id")

    context = LifecycleContext(manifest, scenario["context"])
    if context.active_identity is not None:
        raise AssertionError("new lifecycle context unexpectedly has active work")
    context.submit(scenario["request"], scenario["history"], scenario["motion_vectors"])
    output = context.complete(scenario["request"])
    _validate_expected_grid(scenario["expected_output"], output)
    if output != scenario["expected_output"]:
        _fail("$.expected_output", f"CPU mismatch: expected {scenario['expected_output']}, computed {output}")
    return output


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleInputError(f"scenario contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise LifecycleInputError(f"scenario contains non-finite JSON number {value}")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise LifecycleInputError(
            f"scenario integer exceeds digit limit {MAX_JSON_INTEGER_DIGITS}"
        )
    return int(value)


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise LifecycleInputError(f"scenario contains non-finite JSON number {value}")
    return number


def load_scenario(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_SCENARIO_BYTES + 1)
        if len(payload) > MAX_SCENARIO_BYTES:
            raise LifecycleInputError(
                f"scenario exceeds input limit {MAX_SCENARIO_BYTES} bytes: {path}"
            )
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
            parse_int=_parse_bounded_integer,
            parse_float=_parse_finite_float,
        )
    except FileNotFoundError as exc:
        raise LifecycleInputError(f"scenario does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise LifecycleInputError(f"scenario is not a file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise LifecycleInputError(f"scenario is not UTF-8: {exc}") from exc
    except LifecycleInputError:
        raise
    except json.JSONDecodeError as exc:
        raise LifecycleInputError(
            f"scenario is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise LifecycleInputError("scenario JSON nesting exceeds parser limit") from exc
    except ValueError as exc:
        raise LifecycleInputError(f"scenario contains an unsupported JSON value: {exc}") from exc
    except OSError as exc:
        raise LifecycleInputError(f"cannot read scenario {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="verify a synthetic lifecycle scenario")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--scenario", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = model_manifest.load_manifest(args.manifest)
        scenario = load_scenario(args.scenario)
        validate_scenario(manifest, scenario)
    except (model_manifest.ManifestInvalid, LifecycleInvalid) as exc:
        print(f"invalid lifecycle scenario: {exc}", file=sys.stderr)
        return 1
    except (model_manifest.ManifestInputError, LifecycleInputError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(f"valid lifecycle scenario: {args.scenario}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

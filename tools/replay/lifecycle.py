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
MAX_RETAINED_RESOURCE_COUNT = 4
MAX_CONSUMED_RECORD_COUNT = 4
MAX_RESET_RESULT_COUNT = 4

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
# Logical capacity is the number of grid cells held by candidate history plus
# output.  One maximum-size H3 request is allowed, while old generations still
# apply backpressure to later work in the same context.
MAX_RETAINED_CAPACITY_CELLS = 2 * spatial_reference.MAX_PIXELS


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


def _identity_key(identity: dict[str, str]) -> tuple[str, ...]:
    return tuple(identity[field] for field in _IDENTITY_FIELDS)


class LifecycleContext:
    """Replay one context's execution, consumption, history, and reset lifecycle.

    The request's integer history snapshot stands in for candidate next-history
    and is deliberately separate from the nullable CPU output.  This only tests
    state transitions; it does not model real FSR4 recurrent resources.
    """

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
        self._active_candidate_history: list[list[int]] | None = None
        self._active_capacity_cells = 0
        self._active_state: str | None = None
        self._isolated: dict[tuple[str, ...], dict[str, Any]] = {}
        self._committed_history: list[list[int | None]] | None = None
        self._history_invalid = False
        self._last_submitted_frame: int | None = None
        self._last_completed_frame: int | None = None
        self._last_committed_frame: int | None = None
        self._consumed: dict[tuple[str, ...], bool] = {}
        self._reset_results: dict[str, tuple[str, str]] = {}
        self._closed = False
        self._lock = threading.RLock()

    @property
    def active_identity(self) -> dict[str, str] | None:
        with self._lock:
            return None if self._active_identity is None else dict(self._active_identity)

    @property
    def state(self) -> str:
        with self._lock:
            if self._closed:
                return "closing" if self._isolated else "closed"
            if self._active_state is not None:
                return self._active_state
            return "invalid" if self._history_invalid else "ready"

    @property
    def history_generation(self) -> str:
        with self._lock:
            return self._identity["history_generation"]

    @property
    def committed_history(self) -> list[list[int | None]] | None:
        with self._lock:
            return copy.deepcopy(self._committed_history)

    @property
    def isolated_resource_count(self) -> int:
        with self._lock:
            return len(self._isolated)

    @property
    def isolated_resource_capacity_cells(self) -> int:
        with self._lock:
            return sum(item["capacity_cells"] for item in self._isolated.values())

    @property
    def retained_resource_count(self) -> int:
        with self._lock:
            return len(self._isolated) + (self._active_identity is not None)

    @property
    def retained_resource_capacity_cells(self) -> int:
        with self._lock:
            return self._isolated_capacity_cells() + self._active_capacity_cells

    @property
    def consumed_record_count(self) -> int:
        with self._lock:
            return len(self._consumed)

    @property
    def reset_result_count(self) -> int:
        with self._lock:
            return len(self._reset_results)

    @property
    def last_completed_frame_id(self) -> str | None:
        with self._lock:
            if self._last_completed_frame is None:
                return None
            return str(self._last_completed_frame)

    @property
    def last_committed_frame_id(self) -> str | None:
        with self._lock:
            if self._last_committed_frame is None:
                return None
            return str(self._last_committed_frame)

    def _require_active_match(self, checked: dict[str, str], path: str) -> None:
        if self._active_identity is None:
            _fail(path, "there is no active request")
        for field in _IDENTITY_FIELDS:
            if checked[field] != self._active_identity[field]:
                _fail(f"{path}.{field}", "does not match the active request identity")

    def _invalidate_history(self) -> None:
        self._committed_history = None
        self._last_committed_frame = None
        self._history_invalid = True

    def _isolated_capacity_cells(self) -> int:
        return sum(item["capacity_cells"] for item in self._isolated.values())

    def _remember_consumed(self, key: tuple[str, ...], success: bool) -> None:
        self._consumed[key] = success
        while len(self._consumed) > MAX_CONSUMED_RECORD_COUNT:
            del self._consumed[next(iter(self._consumed))]

    def _remember_reset(
        self, request_id: str, expected_generation: str, result_generation: str
    ) -> None:
        self._reset_results[request_id] = (expected_generation, result_generation)
        while len(self._reset_results) > MAX_RESET_RESULT_COUNT:
            del self._reset_results[next(iter(self._reset_results))]

    def submit(self, request: Any, history: Any, motion_vectors: Any) -> None:
        checked = _identity(request, "request")
        with self._lock:
            if self._closed:
                _fail("request", "context is closed")
            if self._active_identity is not None:
                _fail("request", "context already has an active request")
            if self._history_invalid:
                _fail("request", "history is invalid; reset is required")
            for field in _FIXED_ID_FIELDS:
                if checked[field] != self._identity[field]:
                    _fail(f"request.{field}", "does not match the bound context identity")
            frame_number = int(checked["frame_id"])
            if self._last_submitted_frame is not None and frame_number <= self._last_submitted_frame:
                _fail("request.frame_id", "must be strictly greater than last submitted frame")
            if self._committed_history is None:
                if history is None:
                    _fail("request.history", "an initialization history is required")
                history_source = history
            else:
                if history is not None:
                    _fail("request.history", "must be null after history has been committed")
                history_source = self._committed_history
            if len(self._isolated) + 1 > MAX_RETAINED_RESOURCE_COUNT:
                _fail("request", "retained resource count budget is exhausted")
            try:
                history_snapshot = copy.deepcopy(history_source)
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
            capacity_cells = sum(len(row) for row in history_snapshot) + sum(
                len(row) for row in output
            )
            if (
                self._isolated_capacity_cells() + capacity_cells
                > MAX_RETAINED_CAPACITY_CELLS
            ):
                _fail("request", "retained resource capacity budget is exhausted")
            self._active_identity = checked
            self._active_output = output
            self._active_candidate_history = history_snapshot
            self._active_capacity_cells = capacity_cells
            self._active_state = "executing"
            self._last_submitted_frame = frame_number

    def complete(self, completion: Any) -> list[list[int | None]] | None:
        checked = _identity(completion, "completion")
        with self._lock:
            key = _identity_key(checked)
            isolated = self._isolated.get(key)
            if isolated is not None:
                if isolated["state"] not in (
                    "executing",
                    "executing_timed_out",
                    "execution_failed",
                ):
                    _fail("completion", "isolated request already awaits result consumption")
                del self._isolated[key]
                if not self._closed:
                    completed = int(checked["frame_id"])
                    if (
                        self._last_completed_frame is None
                        or completed > self._last_completed_frame
                    ):
                        self._last_completed_frame = completed
                return None

            self._require_active_match(checked, "completion")
            assert self._active_state is not None
            if self._active_state not in (
                "executing",
                "executing_timed_out",
                "execution_failed",
            ):
                _fail("completion", "active request has already completed")
            output = self._active_output
            assert output is not None
            self._last_completed_frame = int(checked["frame_id"])
            if self._active_state in ("executing_timed_out", "execution_failed"):
                self._active_identity = None
                self._active_output = None
                self._active_candidate_history = None
                self._active_capacity_cells = 0
                self._active_state = None
                return None
            self._active_state = "pending_consumption"
            return copy.deepcopy(output)

    def execution_failed(self, failure: Any) -> None:
        """Record execution failure without claiming retained work has stopped."""

        checked = _identity(failure, "execution_failure")
        with self._lock:
            if self._closed:
                _fail("execution_failure", "context is closed")
            key = _identity_key(checked)
            isolated = self._isolated.get(key)
            if isolated is not None:
                if isolated["state"] == "execution_failed":
                    return
                if isolated["state"] not in ("executing", "executing_timed_out"):
                    _fail("execution_failure", "isolated request is not executing")
                isolated["state"] = "execution_failed"
                return

            self._require_active_match(checked, "execution_failure")
            assert self._active_state is not None
            if self._active_state == "execution_failed":
                return
            if self._active_state not in ("executing", "executing_timed_out"):
                _fail("execution_failure", "active request is not executing")
            self._active_state = "execution_failed"
            self._invalidate_history()

    def timeout(self, request: Any) -> None:
        """Record a caller timeout without claiming retained work has stopped."""

        checked = _identity(request, "timeout")
        with self._lock:
            if self._closed:
                _fail("timeout", "context is closed")
            key = _identity_key(checked)
            isolated = self._isolated.get(key)
            if isolated is not None:
                state = isolated["state"]
                if state == "executing":
                    isolated["state"] = "executing_timed_out"
                elif state == "pending_consumption":
                    isolated["state"] = "pending_consumption_timed_out"
                return

            self._require_active_match(checked, "timeout")
            assert self._active_state is not None
            if self._active_state == "executing":
                self._active_state = "executing_timed_out"
            elif self._active_state == "pending_consumption":
                self._active_state = "pending_consumption_timed_out"
            elif self._active_state not in (
                "executing_timed_out",
                "pending_consumption_timed_out",
            ):
                _fail("timeout", "active request cannot time out in its current state")
            self._invalidate_history()

    def result_consumed(self, notification: Any, success: Any) -> None:
        """Acknowledge output use; only a timely success commits next-history."""

        checked = _identity(notification, "result_consumed")
        if type(success) is not bool:
            _fail("result_consumed.success", "must be a boolean")
        with self._lock:
            key = _identity_key(checked)
            previous = self._consumed.get(key)
            if previous is not None:
                if previous != success:
                    _fail("result_consumed.success", "conflicts with the recorded notification")
                return

            isolated = self._isolated.get(key)
            if isolated is not None:
                if isolated["state"] not in (
                    "pending_consumption",
                    "pending_consumption_timed_out",
                ):
                    _fail("result_consumed", "isolated request has not completed")
                del self._isolated[key]
                self._remember_consumed(key, success)
                return

            if self._active_identity is None:
                _fail(
                    "result_consumed",
                    "notification is outside the retained idempotency window",
                )
            self._require_active_match(checked, "result_consumed")
            assert self._active_state is not None
            if self._active_state not in (
                "pending_consumption",
                "pending_consumption_timed_out",
            ):
                _fail("result_consumed", "active request has not completed")
            timed_out = self._active_state == "pending_consumption_timed_out"
            output = self._active_output
            candidate_history = self._active_candidate_history
            assert output is not None
            assert candidate_history is not None
            if success and not timed_out:
                self._committed_history = copy.deepcopy(candidate_history)
                self._last_committed_frame = int(checked["frame_id"])
                self._history_invalid = False
            else:
                self._invalidate_history()
            self._active_identity = None
            self._active_output = None
            self._active_candidate_history = None
            self._active_capacity_cells = 0
            self._active_state = None
            self._remember_consumed(key, success)

    def reset(self, request_id: Any, expected_generation: Any) -> str:
        """Invalidate history, isolate retained work, and start a new generation."""

        checked_request_id = _nonempty_id(request_id, "reset.request_id")
        checked_expected = _decimal_id(expected_generation, "reset.history_generation")
        with self._lock:
            if self._closed:
                _fail("reset", "context is closed")
            previous_reset = self._reset_results.get(checked_request_id)
            if previous_reset is not None:
                previous_expected, previous_result = previous_reset
                if checked_expected != previous_expected:
                    _fail("reset.request_id", "was already used with different parameters")
                return previous_result
            current = self._identity["history_generation"]
            if checked_expected != current:
                _fail("reset.history_generation", "does not match the current generation")
            next_generation = str(int(current) + 1)
            if len(next_generation) > MAX_DECIMAL_DIGITS:
                _fail("reset.history_generation", "cannot increment beyond the digit limit")

            if self._active_identity is not None:
                key = _identity_key(self._active_identity)
                self._isolated[key] = {
                    "identity": dict(self._active_identity),
                    "output": self._active_output,
                    "candidate_history": self._active_candidate_history,
                    "state": self._active_state,
                    "capacity_cells": self._active_capacity_cells,
                }
                self._active_identity = None
                self._active_output = None
                self._active_candidate_history = None
                self._active_capacity_cells = 0
                self._active_state = None
            self._committed_history = None
            self._last_committed_frame = None
            self._history_invalid = False
            self._identity["history_generation"] = next_generation
            self._remember_reset(
                checked_request_id, checked_expected, next_generation
            )
            return next_generation

    def close(self, identity: Any) -> None:
        """Close the context while retaining any work that may still be in flight."""

        checked = _identity(identity, "close", fixed=True)
        with self._lock:
            for field in _FIXED_ID_FIELDS:
                if checked[field] != self._identity[field]:
                    _fail(f"close.{field}", "does not match the bound context identity")
            if self._closed:
                return
            if self._active_identity is not None:
                key = _identity_key(self._active_identity)
                self._isolated[key] = {
                    "identity": dict(self._active_identity),
                    "output": self._active_output,
                    "candidate_history": self._active_candidate_history,
                    "state": self._active_state,
                    "capacity_cells": self._active_capacity_cells,
                }
                self._active_identity = None
                self._active_output = None
                self._active_candidate_history = None
                self._active_capacity_cells = 0
                self._active_state = None
            self._invalidate_history()
            self._closed = True


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
    assert output is not None
    _validate_expected_grid(scenario["expected_output"], output)
    if output != scenario["expected_output"]:
        _fail("$.expected_output", f"CPU mismatch: expected {scenario['expected_output']}, computed {output}")
    context.result_consumed(scenario["request"], True)
    if context.committed_history != scenario["history"]:
        raise AssertionError("successful result consumption did not commit candidate history")
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

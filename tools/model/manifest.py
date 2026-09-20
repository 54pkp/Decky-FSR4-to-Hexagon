#!/usr/bin/env python3
"""Validate bounded, synthetic host-side model manifests.

This validator only describes tensor metadata.  It does not inspect or execute a
model and must not be used as evidence of device, HTP, or FSR4 validation.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = "host-synthetic-manifest-v1"
LAYOUTS = frozenset({"NHWC", "NCHW"})
DTYPE_BYTES = {"int8": 1, "uint8": 1, "float16": 2, "float32": 4}
MAX_DIMENSION = 65_536
MAX_TENSOR_COUNT = 64
MAX_TENSOR_BYTES = 1 << 30
MAX_TOTAL_BYTES = 2 << 30
MAX_MANIFEST_BYTES = 1 << 20
MAX_JSON_INTEGER_DIGITS = 1_000

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "model_manifest_id",
        "example_only",
        "production_ready",
        "validation_gate",
        "graph",
    }
)
_GRAPH_FIELDS = frozenset({"name", "inputs", "outputs"})
_TENSOR_FIELDS = frozenset({"name", "shape", "layout", "dtype", "byte_count"})


class ManifestInvalid(Exception):
    """The decoded JSON does not satisfy the synthetic manifest contract."""


class ManifestInputError(Exception):
    """The manifest input could not be decoded or read."""


def _fail(path: str, message: str) -> None:
    raise ManifestInvalid(f"{path}: {message}")


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


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a non-empty string")
    if len(value) > 128:
        _fail(path, "must contain at most 128 characters")
    return value


def _bounded_product(values: list[int], limit: int, path: str) -> int:
    result = 1
    for index, value in enumerate(values):
        if result > limit // value:
            _fail(f"{path}[{index}]", f"shape product exceeds bounded limit {limit}")
        result *= value
    return result


def _validate_tensor(value: Any, path: str) -> tuple[str, int]:
    tensor = _object(value, path, _TENSOR_FIELDS)
    name = _nonempty_string(tensor["name"], f"{path}.name")

    shape = tensor["shape"]
    if not isinstance(shape, list):
        _fail(f"{path}.shape", "must be an array")
    if len(shape) != 4:
        _fail(f"{path}.shape", "must have rank 4")
    for index, dimension in enumerate(shape):
        dimension_path = f"{path}.shape[{index}]"
        if isinstance(dimension, bool) or not isinstance(dimension, int):
            _fail(dimension_path, "must be an integer, not a boolean")
        if dimension <= 0:
            _fail(dimension_path, "must be positive")
        if dimension > MAX_DIMENSION:
            _fail(dimension_path, f"must not exceed {MAX_DIMENSION}")

    layout = tensor["layout"]
    if not isinstance(layout, str) or layout not in LAYOUTS:
        _fail(f"{path}.layout", f"unsupported layout; expected one of {sorted(LAYOUTS)}")
    dtype = tensor["dtype"]
    if not isinstance(dtype, str) or dtype not in DTYPE_BYTES:
        _fail(f"{path}.dtype", f"unsupported dtype; expected one of {sorted(DTYPE_BYTES)}")

    element_bytes = DTYPE_BYTES[dtype]
    max_elements = MAX_TENSOR_BYTES // element_bytes
    elements = _bounded_product(shape, max_elements, f"{path}.shape")
    expected_bytes = elements * element_bytes

    byte_count = tensor["byte_count"]
    if isinstance(byte_count, bool) or not isinstance(byte_count, int):
        _fail(f"{path}.byte_count", "must be an integer, not a boolean")
    if byte_count != expected_bytes:
        _fail(f"{path}.byte_count", f"expected {expected_bytes} from shape and dtype, got {byte_count}")
    return name, expected_bytes


def validate_manifest(value: Any) -> None:
    """Raise ManifestInvalid unless *value* is a bounded synthetic manifest."""

    manifest = _object(value, "$", _ROOT_FIELDS)
    if manifest["schema_version"] != SCHEMA_VERSION:
        _fail("$.schema_version", f"must equal {SCHEMA_VERSION!r}")
    manifest_id = _nonempty_string(manifest["model_manifest_id"], "$.model_manifest_id")
    if not manifest_id.startswith("synthetic-"):
        _fail("$.model_manifest_id", "must start with 'synthetic-'")
    if manifest["example_only"] is not True:
        _fail("$.example_only", "must be true for a synthetic host manifest")
    if manifest["production_ready"] is not False:
        _fail("$.production_ready", "must be false for a synthetic host manifest")
    if manifest["validation_gate"] != "not_run":
        _fail("$.validation_gate", "must equal 'not_run'")

    graph = _object(manifest["graph"], "$.graph", _GRAPH_FIELDS)
    _nonempty_string(graph["name"], "$.graph.name")
    for collection in ("inputs", "outputs"):
        tensors = graph[collection]
        if not isinstance(tensors, list):
            _fail(f"$.graph.{collection}", "must be an array")
        if not tensors:
            _fail(f"$.graph.{collection}", "must contain at least one tensor")

    all_tensors = [("inputs", index, item) for index, item in enumerate(graph["inputs"])]
    all_tensors.extend(("outputs", index, item) for index, item in enumerate(graph["outputs"]))
    if len(all_tensors) > MAX_TENSOR_COUNT:
        _fail("$.graph", f"tensor count {len(all_tensors)} exceeds limit {MAX_TENSOR_COUNT}")

    names: set[str] = set()
    total_bytes = 0
    for collection, index, tensor in all_tensors:
        path = f"$.graph.{collection}[{index}]"
        name, byte_count = _validate_tensor(tensor, path)
        if name in names:
            _fail(f"{path}.name", f"duplicate tensor name {name!r}")
        names.add(name)
        if total_bytes > MAX_TOTAL_BYTES - byte_count:
            _fail(f"{path}.byte_count", f"total tensor capacity exceeds limit {MAX_TOTAL_BYTES}")
        total_bytes += byte_count


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestInputError(f"manifest contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise ManifestInputError(f"manifest contains non-finite JSON number {value}")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise ManifestInputError(
            f"manifest integer exceeds digit limit {MAX_JSON_INTEGER_DIGITS}"
        )
    return int(value)


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ManifestInputError(f"manifest contains non-finite JSON number {value}")
    return number


def load_manifest(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise ManifestInputError(
                f"manifest exceeds input limit {MAX_MANIFEST_BYTES} bytes: {path}"
            )
        text = payload.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
            parse_int=_parse_bounded_integer,
            parse_float=_parse_finite_float,
        )
    except FileNotFoundError as exc:
        raise ManifestInputError(f"manifest does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise ManifestInputError(f"manifest is not a file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ManifestInputError(f"manifest is not UTF-8: {exc}") from exc
    except ManifestInputError:
        raise
    except json.JSONDecodeError as exc:
        raise ManifestInputError(
            f"manifest is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise ManifestInputError("manifest JSON nesting exceeds parser limit") from exc
    except ValueError as exc:
        raise ManifestInputError(f"manifest contains an unsupported JSON value: {exc}") from exc
    except OSError as exc:
        raise ManifestInputError(f"cannot read manifest {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="validate a synthetic manifest")
    verify.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        validate_manifest(manifest)
    except ManifestInvalid as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return 1
    except ManifestInputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(f"valid manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

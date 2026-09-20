#!/usr/bin/env python3
"""Verify a small host-only synthetic affine-int8 numeric reference.

This module uses a host synthetic zero-point convention.  It is not a QNN
offset convention and does not validate FSR4, HTP, a device, or a game.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = "host-synthetic-affine-int8-reference-v1"
DTYPE = "int8"
QUANTIZATION_FORMULA = (
    "q = clamp(round_half_away_from_zero(x / scale + zero_point), -128, 127)"
)
DEQUANTIZATION_FORMULA = "dequant = (q - zero_point) * scale"
ZERO_POINT_CONVENTION = (
    "host_synthetic_added_during_quantization_not_qnn_offset_or_fsr4"
)
ARITHMETIC = "IEEE 754 binary64 host reference"
INT8_MIN = -128
INT8_MAX = 127
COMPARISON_ABSOLUTE_TOLERANCE = 1e-12
MAX_FIXTURE_BYTES = 1 << 20
MAX_JSON_INTEGER_DIGITS = 1_000
REQUIRED_CATEGORIES = frozenset(
    {"tie_rounding", "saturation", "dequantization_error"}
)

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "example_only",
        "production_ready",
        "validation_gate",
        "dtype",
        "quantization_formula",
        "dequantization_formula",
        "zero_point_convention",
        "arithmetic",
        "scale",
        "zero_point",
        "absolute_tolerance",
        "max_unsaturated_error",
        "cases",
    }
)
_CASE_FIELDS = frozenset(
    {"name", "category", "input", "expected_quantized", "expected_dequantized"}
)


class NumericReferenceInvalid(Exception):
    """The decoded fixture violates its contract or fixed numeric reference."""


class NumericReferenceInputError(Exception):
    """The fixture file could not be read or decoded safely."""


def _fail(path: str, message: str) -> None:
    raise NumericReferenceInvalid(f"{path}: {message}")


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a finite number, not a boolean")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        _fail(path, "must be a finite number")
        raise AssertionError("unreachable") from exc
    if not math.isfinite(number):
        _fail(path, "must be a finite number")
    return number


def _int8(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an int8 integer, not a boolean")
    if value < INT8_MIN or value > INT8_MAX:
        _fail(path, f"must be in [{INT8_MIN}, {INT8_MAX}]")
    return value


def _scale(value: Any, path: str = "scale") -> float:
    number = _finite_number(value, path)
    if number <= 0.0:
        _fail(path, "must be greater than zero")
    return number


def _zero_point(value: Any, path: str = "zero_point") -> int:
    return _int8(value, path)


def round_half_away_from_zero(value: float) -> int:
    """Round a finite number to the nearest integer, with half ties away from zero."""

    number = _finite_number(value, "value")
    fraction, integral = math.modf(abs(number))
    magnitude = int(integral) + (1 if fraction >= 0.5 else 0)
    return -magnitude if number < 0.0 else magnitude


def quantize_affine_int8(values: list[float | int], scale: float, zero_point: int) -> list[int]:
    """Apply q=clamp(round_half_away_from_zero(x/scale+zero_point), -128, 127)."""

    checked_scale = _scale(scale)
    checked_zero_point = _zero_point(zero_point)
    if not isinstance(values, list):
        _fail("values", "must be a list")

    result: list[int] = []
    for index, value in enumerate(values):
        number = _finite_number(value, f"values[{index}]")
        transformed = number / checked_scale + checked_zero_point
        if not math.isfinite(transformed):
            _fail(f"values[{index}]", "produces a non-finite transformed value")
        rounded = round_half_away_from_zero(transformed)
        result.append(min(INT8_MAX, max(INT8_MIN, rounded)))
    return result


def dequantize_affine_int8(values: list[int], scale: float, zero_point: int) -> list[float]:
    """Apply dequant=(q-zero_point)*scale to int8 values."""

    checked_scale = _scale(scale)
    checked_zero_point = _zero_point(zero_point)
    if not isinstance(values, list):
        _fail("values", "must be a list")

    result: list[float] = []
    for index, value in enumerate(values):
        quantized = _int8(value, f"values[{index}]")
        dequantized = (quantized - checked_zero_point) * checked_scale
        if not math.isfinite(dequantized):
            _fail(f"values[{index}]", "produces a non-finite dequantized value")
        result.append(dequantized)
    return result


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


def _number_list(value: Any, path: str) -> list[float]:
    if not isinstance(value, list) or not value:
        _fail(path, "must be a non-empty array")
    return [_finite_number(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _int8_list(value: Any, path: str) -> list[int]:
    if not isinstance(value, list) or not value:
        _fail(path, "must be a non-empty array")
    return [_int8(item, f"{path}[{index}]") for index, item in enumerate(value)]


def validate_fixture(value: Any) -> None:
    """Verify fixture contract, required coverage, and hard-coded expected values."""

    fixture = _object(value, "$", _ROOT_FIELDS)
    fixed_fields = {
        "schema_version": SCHEMA_VERSION,
        "example_only": True,
        "production_ready": False,
        "validation_gate": "not_run",
        "dtype": DTYPE,
        "quantization_formula": QUANTIZATION_FORMULA,
        "dequantization_formula": DEQUANTIZATION_FORMULA,
        "zero_point_convention": ZERO_POINT_CONVENTION,
        "arithmetic": ARITHMETIC,
    }
    for field, expected in fixed_fields.items():
        if fixture[field] != expected or type(fixture[field]) is not type(expected):
            _fail(f"$.{field}", f"must equal {expected!r}")

    scale = _scale(fixture["scale"], "$.scale")
    zero_point = _zero_point(fixture["zero_point"], "$.zero_point")
    tolerance = _finite_number(fixture["absolute_tolerance"], "$.absolute_tolerance")
    if tolerance != COMPARISON_ABSOLUTE_TOLERANCE:
        _fail(
            "$.absolute_tolerance",
            f"must equal fixed comparison tolerance {COMPARISON_ABSOLUTE_TOLERANCE!r}",
        )
    max_unsaturated_error = _finite_number(
        fixture["max_unsaturated_error"], "$.max_unsaturated_error"
    )
    expected_error_bound = scale / 2.0
    if max_unsaturated_error != expected_error_bound:
        _fail(
            "$.max_unsaturated_error",
            f"must equal scale / 2 ({expected_error_bound!r})",
        )

    cases = fixture["cases"]
    if not isinstance(cases, list) or not cases:
        _fail("$.cases", "must be a non-empty array")

    categories: set[str] = set()
    names: set[str] = set()
    saw_negative_tie = False
    saw_positive_tie = False
    saturation_bounds: set[int] = set()
    saw_nonzero_unsaturated_error = False

    for case_index, raw_case in enumerate(cases):
        path = f"$.cases[{case_index}]"
        case = _object(raw_case, path, _CASE_FIELDS)
        name = case["name"]
        if not isinstance(name, str) or not name.strip():
            _fail(f"{path}.name", "must be a non-empty string")
        if name in names:
            _fail(f"{path}.name", f"duplicate case name {name!r}")
        names.add(name)

        category = case["category"]
        if not isinstance(category, str) or category not in REQUIRED_CATEGORIES:
            _fail(f"{path}.category", f"must be one of {sorted(REQUIRED_CATEGORIES)}")
        categories.add(category)

        inputs = _number_list(case["input"], f"{path}.input")
        expected_q = _int8_list(case["expected_quantized"], f"{path}.expected_quantized")
        expected_dequant = _number_list(
            case["expected_dequantized"], f"{path}.expected_dequantized"
        )
        if len(expected_q) != len(inputs):
            _fail(f"{path}.expected_quantized", "length must match input")
        if len(expected_dequant) != len(inputs):
            _fail(f"{path}.expected_dequantized", "length must match input")

        actual_q = quantize_affine_int8(inputs, scale, zero_point)
        if actual_q != expected_q:
            _fail(
                f"{path}.expected_quantized",
                f"numeric mismatch: expected {expected_q}, computed {actual_q}",
            )
        actual_dequant = dequantize_affine_int8(expected_q, scale, zero_point)
        for item_index, (actual, expected) in enumerate(zip(actual_dequant, expected_dequant)):
            error = abs(actual - expected)
            if error > tolerance:
                _fail(
                    f"{path}.expected_dequantized[{item_index}]",
                    f"absolute error {error!r} exceeds tolerance {tolerance!r}",
                )

        transformed = [number / scale + zero_point for number in inputs]
        if category == "tie_rounding":
            for number in transformed:
                if abs(number - math.trunc(number)) == 0.5:
                    saw_negative_tie |= number < 0.0
                    saw_positive_tie |= number > 0.0
        elif category == "saturation":
            for number, quantized in zip(transformed, expected_q):
                unbounded = round_half_away_from_zero(number)
                if unbounded < INT8_MIN and quantized == INT8_MIN:
                    saturation_bounds.add(INT8_MIN)
                if unbounded > INT8_MAX and quantized == INT8_MAX:
                    saturation_bounds.add(INT8_MAX)
        else:
            for original, quantized, dequantized in zip(inputs, expected_q, expected_dequant):
                if not INT8_MIN < quantized < INT8_MAX:
                    _fail(
                        f"{path}.expected_quantized",
                        "dequantization_error cases must contain only unsaturated values",
                    )
                dequantization_error = abs(dequantized - original)
                if dequantization_error > max_unsaturated_error + tolerance:
                    _fail(
                        f"{path}.expected_dequantized",
                        "unsaturated error "
                        f"{dequantization_error!r} exceeds bound {max_unsaturated_error!r} "
                        f"plus comparison tolerance {tolerance!r}",
                    )
                if dequantization_error > tolerance:
                    saw_nonzero_unsaturated_error = True

    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        _fail("$.cases", f"missing required categories {missing_categories}")
    if not (saw_negative_tie and saw_positive_tie):
        _fail("$.cases", "tie_rounding must cover negative and positive half ties")
    if saturation_bounds != {INT8_MIN, INT8_MAX}:
        _fail("$.cases", "saturation must cover both int8 bounds")
    if not saw_nonzero_unsaturated_error:
        _fail("$.cases", "dequantization_error must show non-zero unsaturated error")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NumericReferenceInputError(f"fixture contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise NumericReferenceInputError(f"fixture contains non-finite JSON number {value}")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise NumericReferenceInputError(
            f"fixture integer exceeds digit limit {MAX_JSON_INTEGER_DIGITS}"
        )
    return int(value)


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise NumericReferenceInputError(f"fixture contains non-finite JSON number {value}")
    return number


def load_fixture(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_FIXTURE_BYTES + 1)
        if len(payload) > MAX_FIXTURE_BYTES:
            raise NumericReferenceInputError(
                f"fixture exceeds input limit {MAX_FIXTURE_BYTES} bytes: {path}"
            )
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
            parse_int=_parse_bounded_integer,
            parse_float=_parse_finite_float,
        )
    except FileNotFoundError as exc:
        raise NumericReferenceInputError(f"fixture does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise NumericReferenceInputError(f"fixture is not a file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise NumericReferenceInputError(f"fixture is not UTF-8: {exc}") from exc
    except NumericReferenceInputError:
        raise
    except json.JSONDecodeError as exc:
        raise NumericReferenceInputError(
            f"fixture is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise NumericReferenceInputError("fixture JSON nesting exceeds parser limit") from exc
    except ValueError as exc:
        raise NumericReferenceInputError(f"fixture contains an unsupported JSON value: {exc}") from exc
    except OSError as exc:
        raise NumericReferenceInputError(f"cannot read fixture {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="verify the fixed numeric reference")
    verify.add_argument("--fixture", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        fixture = load_fixture(args.fixture)
        validate_fixture(fixture)
    except NumericReferenceInvalid as exc:
        print(f"invalid numeric reference: {exc}", file=sys.stderr)
        return 1
    except NumericReferenceInputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(f"valid numeric reference: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

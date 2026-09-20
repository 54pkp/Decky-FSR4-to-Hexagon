#!/usr/bin/env python3
"""Verify a tiny host-only spatial translation and reprojection reference.

This reference operates on synthetic integer grids.  It does not validate real
game motion vectors, FSR4, HTP, a device, or a game integration.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = "host-synthetic-spatial-reference-v1"
COORDINATE_ORIGIN = "top_left"
POSITIVE_X = "right"
POSITIVE_Y = "down"
TRANSLATION_CONVENTION = "dst(x + shift_x, y + shift_y) = src(x, y)"
REPROJECTION_CONVENTION = "dst(x, y) = history(x + mv_x, y + mv_y)"
SAMPLING_CONVENTION = "integer_nearest_no_interpolation"
OUT_OF_BOUNDS_CONVENTION = "json_null"
RESET_CONVENTION = "reset_true_does_not_sample_history_and_outputs_all_null"

MAX_WIDTH = 64
MAX_HEIGHT = 64
MAX_PIXELS = 4096
MAX_FIXTURE_BYTES = 1 << 20
MAX_JSON_INTEGER_DIGITS = 1_000

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "example_only",
        "production_ready",
        "validation_gate",
        "conventions",
        "width",
        "height",
        "source",
        "translation",
        "reprojection",
        "reset",
    }
)
_CONVENTION_FIELDS = frozenset(
    {
        "coordinate_origin",
        "positive_x",
        "positive_y",
        "translation_forward",
        "reprojection_backward_motion_vector",
        "sampling",
        "out_of_bounds",
        "reset",
    }
)
_TRANSLATION_FIELDS = frozenset({"shift_x", "shift_y", "expected"})
_REPROJECTION_FIELDS = frozenset({"motion_vectors", "expected"})
_RESET_FIELDS = frozenset({"motion_vectors", "expected"})


class SpatialReferenceInvalid(Exception):
    """The decoded fixture violates the spatial reference contract."""


class SpatialReferenceInputError(Exception):
    """The fixture file could not be read or decoded safely."""


def _fail(path: str, message: str) -> None:
    raise SpatialReferenceInvalid(f"{path}: {message}")


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


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer, not a boolean")
    return value


def _dimension(value: Any, path: str, limit: int) -> int:
    dimension = _integer(value, path)
    if dimension <= 0:
        _fail(path, "must be positive")
    if dimension > limit:
        _fail(path, f"must not exceed {limit}")
    return dimension


def _grid_dimensions(value: Any, path: str) -> tuple[int, int]:
    if not isinstance(value, list) or not value:
        _fail(path, "must be a non-empty two-dimensional array")
    height = len(value)
    if height > MAX_HEIGHT:
        _fail(path, f"height must not exceed {MAX_HEIGHT}")
    first = value[0]
    if not isinstance(first, list) or not first:
        _fail(f"{path}[0]", "must be a non-empty row")
    width = len(first)
    if width > MAX_WIDTH:
        _fail(path, f"width must not exceed {MAX_WIDTH}")
    if height * width > MAX_PIXELS:
        _fail(path, f"pixel count must not exceed {MAX_PIXELS}")
    for y, row in enumerate(value):
        if not isinstance(row, list):
            _fail(f"{path}[{y}]", "must be a row array")
        if len(row) != width:
            _fail(f"{path}[{y}]", f"must contain exactly {width} columns")
    return width, height


def _integer_grid(value: Any, path: str) -> tuple[list[list[int]], int, int]:
    width, height = _grid_dimensions(value, path)
    for y, row in enumerate(value):
        for x, item in enumerate(row):
            _integer(item, f"{path}[{y}][{x}]")
    return value, width, height


def _nullable_integer_grid(
    value: Any, path: str, width: int, height: int
) -> list[list[int | None]]:
    actual_width, actual_height = _grid_dimensions(value, path)
    if (actual_width, actual_height) != (width, height):
        _fail(path, f"dimensions must equal {width}x{height}")
    for y, row in enumerate(value):
        for x, item in enumerate(row):
            if item is not None:
                _integer(item, f"{path}[{y}][{x}]")
    return value


def _motion_vector_grid(
    value: Any, path: str
) -> tuple[list[list[list[int]]], int, int]:
    width, height = _grid_dimensions(value, path)
    for y, row in enumerate(value):
        for x, vector in enumerate(row):
            vector_path = f"{path}[{y}][{x}]"
            if not isinstance(vector, list) or len(vector) != 2:
                _fail(vector_path, "must be a two-element [mv_x, mv_y] array")
            _integer(vector[0], f"{vector_path}[0]")
            _integer(vector[1], f"{vector_path}[1]")
    return value, width, height


def translate_forward(
    source: list[list[int]], shift_x: int, shift_y: int
) -> list[list[int | None]]:
    """Move each source sample to ``dst(x + shift_x, y + shift_y)``."""

    checked_source, width, height = _integer_grid(source, "source")
    dx = _integer(shift_x, "shift_x")
    dy = _integer(shift_y, "shift_y")
    output: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
    for y, row in enumerate(checked_source):
        for x, sample in enumerate(row):
            destination_x = x + dx
            destination_y = y + dy
            if 0 <= destination_x < width and 0 <= destination_y < height:
                output[destination_y][destination_x] = sample
    return output


def reproject_backward(
    history: Any,
    motion_vectors: list[list[list[int]]],
    *,
    reset: bool = False,
) -> list[list[int | None]]:
    """Sample ``history(x + mv_x, y + mv_y)`` for each output pixel.

    Motion vectors are validated first and define the output dimensions.  When
    reset is true, history is deliberately neither validated nor sampled.
    """

    if not isinstance(reset, bool):
        _fail("reset", "must be a boolean")
    checked_vectors, width, height = _motion_vector_grid(motion_vectors, "motion_vectors")
    if reset:
        return [[None for _ in range(width)] for _ in range(height)]

    checked_history, history_width, history_height = _integer_grid(history, "history")
    if (history_width, history_height) != (width, height):
        _fail("history", f"dimensions must match motion_vectors ({width}x{height})")

    output: list[list[int | None]] = [[None for _ in range(width)] for _ in range(height)]
    for y, row in enumerate(checked_vectors):
        for x, (mv_x, mv_y) in enumerate(row):
            source_x = x + mv_x
            source_y = y + mv_y
            if 0 <= source_x < width and 0 <= source_y < height:
                output[y][x] = checked_history[source_y][source_x]
    return output


def validate_fixture(value: Any) -> None:
    """Verify the closed contract and its independent literal expectations."""

    fixture = _object(value, "$", _ROOT_FIELDS)
    fixed_fields = {
        "schema_version": SCHEMA_VERSION,
        "example_only": True,
        "production_ready": False,
        "validation_gate": "not_run",
    }
    for field, expected in fixed_fields.items():
        if fixture[field] != expected or type(fixture[field]) is not type(expected):
            _fail(f"$.{field}", f"must equal {expected!r}")

    conventions = _object(fixture["conventions"], "$.conventions", _CONVENTION_FIELDS)
    fixed_conventions = {
        "coordinate_origin": COORDINATE_ORIGIN,
        "positive_x": POSITIVE_X,
        "positive_y": POSITIVE_Y,
        "translation_forward": TRANSLATION_CONVENTION,
        "reprojection_backward_motion_vector": REPROJECTION_CONVENTION,
        "sampling": SAMPLING_CONVENTION,
        "out_of_bounds": OUT_OF_BOUNDS_CONVENTION,
        "reset": RESET_CONVENTION,
    }
    for field, expected in fixed_conventions.items():
        if conventions[field] != expected or type(conventions[field]) is not str:
            _fail(f"$.conventions.{field}", f"must equal {expected!r}")

    width = _dimension(fixture["width"], "$.width", MAX_WIDTH)
    height = _dimension(fixture["height"], "$.height", MAX_HEIGHT)
    if width * height > MAX_PIXELS:
        _fail("$.width", f"width * height must not exceed {MAX_PIXELS}")

    source, source_width, source_height = _integer_grid(fixture["source"], "$.source")
    if (source_width, source_height) != (width, height):
        _fail("$.source", f"dimensions must equal declared {width}x{height}")

    translation = _object(fixture["translation"], "$.translation", _TRANSLATION_FIELDS)
    shift_x = _integer(translation["shift_x"], "$.translation.shift_x")
    shift_y = _integer(translation["shift_y"], "$.translation.shift_y")
    expected_translation = _nullable_integer_grid(
        translation["expected"], "$.translation.expected", width, height
    )
    actual_translation = translate_forward(source, shift_x, shift_y)
    if actual_translation != expected_translation:
        _fail(
            "$.translation.expected",
            f"spatial mismatch: expected {expected_translation}, computed {actual_translation}",
        )

    reprojection = _object(fixture["reprojection"], "$.reprojection", _REPROJECTION_FIELDS)
    vectors, vectors_width, vectors_height = _motion_vector_grid(
        reprojection["motion_vectors"], "$.reprojection.motion_vectors"
    )
    if (vectors_width, vectors_height) != (width, height):
        _fail("$.reprojection.motion_vectors", f"dimensions must equal declared {width}x{height}")
    expected_reprojection = _nullable_integer_grid(
        reprojection["expected"], "$.reprojection.expected", width, height
    )
    actual_reprojection = reproject_backward(source, vectors)
    if actual_reprojection != expected_reprojection:
        _fail(
            "$.reprojection.expected",
            f"spatial mismatch: expected {expected_reprojection}, computed {actual_reprojection}",
        )
    if expected_reprojection != expected_translation:
        _fail(
            "$.reprojection.expected",
            "must literally equal translation.expected for the fixed equivalence case",
        )

    reset_case = _object(fixture["reset"], "$.reset", _RESET_FIELDS)
    reset_vectors, reset_width, reset_height = _motion_vector_grid(
        reset_case["motion_vectors"], "$.reset.motion_vectors"
    )
    if (reset_width, reset_height) != (width, height):
        _fail("$.reset.motion_vectors", f"dimensions must equal declared {width}x{height}")
    expected_reset = _nullable_integer_grid(
        reset_case["expected"], "$.reset.expected", width, height
    )
    actual_reset = reproject_backward(source, reset_vectors, reset=True)
    if actual_reset != expected_reset:
        _fail("$.reset.expected", f"reset mismatch: expected {expected_reset}, computed {actual_reset}")
    if any(item is not None for row in expected_reset for item in row):
        _fail("$.reset.expected", "must contain only JSON null samples")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpatialReferenceInputError(f"fixture contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise SpatialReferenceInputError(f"fixture contains non-finite JSON number {value}")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise SpatialReferenceInputError(
            f"fixture integer exceeds digit limit {MAX_JSON_INTEGER_DIGITS}"
        )
    return int(value)


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise SpatialReferenceInputError(f"fixture contains non-finite JSON number {value}")
    return number


def load_fixture(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_FIXTURE_BYTES + 1)
        if len(payload) > MAX_FIXTURE_BYTES:
            raise SpatialReferenceInputError(
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
        raise SpatialReferenceInputError(f"fixture does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise SpatialReferenceInputError(f"fixture is not a file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise SpatialReferenceInputError(f"fixture is not UTF-8: {exc}") from exc
    except SpatialReferenceInputError:
        raise
    except json.JSONDecodeError as exc:
        raise SpatialReferenceInputError(
            f"fixture is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise SpatialReferenceInputError("fixture JSON nesting exceeds parser limit") from exc
    except ValueError as exc:
        raise SpatialReferenceInputError(f"fixture contains an unsupported JSON value: {exc}") from exc
    except OSError as exc:
        raise SpatialReferenceInputError(f"cannot read fixture {path}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify", help="verify the fixed spatial reference")
    verify.add_argument("--fixture", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        fixture = load_fixture(args.fixture)
        validate_fixture(fixture)
    except SpatialReferenceInvalid as exc:
        print(f"invalid spatial reference: {exc}", file=sys.stderr)
        return 1
    except SpatialReferenceInputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(f"valid spatial reference: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and verify a tiny synthetic Conv -> Add -> ReLU ONNX graph.

This is a host-only numerical reference.  It is not an FSR4 model and does not
provide HTP, device, game, latency, or image-quality evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import onnxruntime as ort
from google.protobuf.message import DecodeError


INPUT_NAME = "reference_input"
OUTPUT_NAME = "reference_output"
INPUT_SHAPE = (1, 1, 4, 4)
OUTPUT_SHAPE = (1, 1, 4, 4)
DTYPE = np.dtype(np.float32)
OPSET_VERSION = 18
IR_VERSION = 10
ABSOLUTE_TOLERANCE = 1e-6
RELATIVE_TOLERANCE = 0.0
RANDOM_SEED = 20260921

# These coefficients are part of the public synthetic graph contract.  The
# NumPy reference below implements convolution directly rather than invoking
# ONNX Runtime or an ONNX operator evaluator.
KERNEL = np.asarray(
    [[[[0.25, -0.5, 0.25], [0.5, 1.0, 0.5], [-0.25, 0.5, -0.25]]]],
    dtype=np.float32,
)
CONV_BIAS = np.asarray([-0.125], dtype=np.float32)
ADD_BIAS = np.asarray([0.25], dtype=np.float32)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "conv_add_relu.onnx"


class ReferenceError(Exception):
    """The model, input, or CPU execution result violates the fixed contract."""


@dataclass(frozen=True)
class ExecutionResult:
    output: np.ndarray
    providers: tuple[str, ...]


def build_model() -> onnx.ModelProto:
    """Return the deterministic tiny ONNX model without writing it."""

    graph = helper.make_graph(
        [
            helper.make_node(
                "Conv",
                [INPUT_NAME, "conv_weight", "conv_bias"],
                ["conv_output"],
                name="reference_conv",
                pads=[1, 1, 1, 1],
                strides=[1, 1],
            ),
            helper.make_node(
                "Add",
                ["conv_output", "add_bias"],
                ["biased_output"],
                name="reference_add",
            ),
            helper.make_node(
                "Relu",
                ["biased_output"],
                [OUTPUT_NAME],
                name="reference_relu",
            ),
        ],
        "host_synthetic_conv_add_relu",
        [helper.make_tensor_value_info(INPUT_NAME, TensorProto.FLOAT, INPUT_SHAPE)],
        [helper.make_tensor_value_info(OUTPUT_NAME, TensorProto.FLOAT, OUTPUT_SHAPE)],
        initializer=[
            numpy_helper.from_array(KERNEL, "conv_weight"),
            numpy_helper.from_array(CONV_BIAS, "conv_bias"),
            numpy_helper.from_array(ADD_BIAS, "add_bias"),
        ],
    )
    model = helper.make_model(
        graph,
        producer_name="decky-fsr4-to-hexagon-host-reference",
        producer_version="1",
        opset_imports=[helper.make_opsetid("", OPSET_VERSION)],
    )
    model.ir_version = IR_VERSION
    model.doc_string = (
        "Synthetic host-only numerical reference; not FSR4 or HTP evidence."
    )
    onnx.checker.check_model(model)
    return model


def model_bytes() -> bytes:
    """Serialize the graph deterministically for a stable checked-in fixture."""

    return build_model().SerializeToString(deterministic=True)


def write_model(path: Path) -> str:
    payload = model_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _tensor_contract(value_info: onnx.ValueInfoProto) -> tuple[str, int, tuple[int, ...]]:
    tensor = value_info.type.tensor_type
    dimensions = tuple(dimension.dim_value for dimension in tensor.shape.dim)
    return value_info.name, tensor.elem_type, dimensions


def validate_model(model: onnx.ModelProto) -> None:
    """Run ONNX checker and enforce the exact small-graph contract."""

    try:
        onnx.checker.check_model(model)
    except onnx.checker.ValidationError as exc:
        raise ReferenceError(f"ONNX checker rejected model: {exc}") from exc

    if model.ir_version != IR_VERSION:
        raise ReferenceError(f"IR version must be {IR_VERSION}")
    opsets = [(item.domain, item.version) for item in model.opset_import]
    if opsets != [("", OPSET_VERSION)]:
        raise ReferenceError(f"opset imports must equal [('', {OPSET_VERSION})]")
    if len(model.graph.input) != 1 or _tensor_contract(model.graph.input[0]) != (
        INPUT_NAME,
        TensorProto.FLOAT,
        INPUT_SHAPE,
    ):
        raise ReferenceError("graph input name, shape, or dtype does not match contract")
    if len(model.graph.output) != 1 or _tensor_contract(model.graph.output[0]) != (
        OUTPUT_NAME,
        TensorProto.FLOAT,
        OUTPUT_SHAPE,
    ):
        raise ReferenceError("graph output name, shape, or dtype does not match contract")

    expected_nodes = build_model().graph.node
    if len(model.graph.node) != len(expected_nodes) or any(
        actual != expected
        for actual, expected in zip(model.graph.node, expected_nodes, strict=True)
    ):
        raise ReferenceError("graph nodes must be exactly Conv -> Add -> ReLU")

    initializers = {
        initializer.name: numpy_helper.to_array(initializer)
        for initializer in model.graph.initializer
    }
    expected_initializers = {
        "conv_weight": KERNEL,
        "conv_bias": CONV_BIAS,
        "add_bias": ADD_BIAS,
    }
    if set(initializers) != set(expected_initializers):
        raise ReferenceError("initializer names do not match contract")
    for name, expected in expected_initializers.items():
        actual = initializers[name]
        if actual.dtype != DTYPE or not np.array_equal(actual, expected):
            raise ReferenceError(f"initializer {name!r} does not match contract")

    # Propagate whether each value depends on the graph input.  This rejects a
    # graph whose declared output is folded to an initializer-only constant.
    depends_on_input = {INPUT_NAME: True}
    depends_on_input.update((name, False) for name in initializers)
    for node in model.graph.node:
        dependency = any(depends_on_input.get(name, False) for name in node.input)
        depends_on_input.update((name, dependency) for name in node.output)
    if not depends_on_input.get(OUTPUT_NAME, False):
        raise ReferenceError("graph output must depend on the graph input")


def load_and_validate_model(path: Path = FIXTURE_PATH) -> onnx.ModelProto:
    try:
        model = onnx.load(path, load_external_data=False)
    except (OSError, DecodeError) as exc:
        raise ReferenceError(f"could not load ONNX model {path}: {exc}") from exc
    validate_model(model)
    return model


def fixed_inputs() -> dict[str, np.ndarray]:
    """Return zero, fixed-pattern, and fixed-seed nonzero inputs."""

    pattern = np.asarray(
        [
            -1.0,
            -0.75,
            -0.5,
            -0.25,
            0.0,
            0.25,
            0.5,
            0.75,
            1.0,
            0.5,
            0.0,
            -0.5,
            -1.0,
            -0.25,
            0.25,
            1.0,
        ],
        dtype=np.float32,
    ).reshape(INPUT_SHAPE)
    rng = np.random.default_rng(RANDOM_SEED)
    seeded = rng.uniform(-1.0, 1.0, size=INPUT_SHAPE).astype(np.float32)
    return {
        "zero": np.zeros(INPUT_SHAPE, dtype=np.float32),
        "pattern": pattern,
        "seeded_nonzero": seeded,
    }


def validate_input(value: np.ndarray) -> None:
    if not isinstance(value, np.ndarray):
        raise ReferenceError("input must be a NumPy array")
    if value.shape != INPUT_SHAPE:
        raise ReferenceError(f"input shape must be {INPUT_SHAPE}, got {value.shape}")
    if value.dtype != DTYPE:
        raise ReferenceError(f"input dtype must be float32, got {value.dtype}")
    if not np.isfinite(value).all():
        raise ReferenceError("input must contain only finite values")


def numpy_expected(value: np.ndarray) -> np.ndarray:
    """Compute Conv -> Add -> ReLU with an independent direct NumPy formula."""

    validate_input(value)
    padded = np.pad(value, ((0, 0), (0, 0), (1, 1), (1, 1)))
    result = np.empty(OUTPUT_SHAPE, dtype=np.float32)
    for y in range(OUTPUT_SHAPE[2]):
        for x in range(OUTPUT_SHAPE[3]):
            total = np.float32(CONV_BIAS[0])
            for ky in range(3):
                for kx in range(3):
                    product = np.float32(padded[0, 0, y + ky, x + kx] * KERNEL[0, 0, ky, kx])
                    total = np.float32(total + product)
            biased = np.float32(total + ADD_BIAS[0])
            result[0, 0, y, x] = np.maximum(biased, np.float32(0.0))
    return result


def run_cpu(value: np.ndarray, path: Path = FIXTURE_PATH) -> ExecutionResult:
    """Execute only with ONNX Runtime's explicitly selected CPU provider."""

    validate_input(value)
    load_and_validate_model(path)
    try:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception as exc:  # ONNX Runtime exposes several provider/session errors.
        raise ReferenceError(f"could not create CPU inference session: {exc}") from exc
    providers = tuple(session.get_providers())
    if providers != ("CPUExecutionProvider",):
        raise ReferenceError(f"expected only CPUExecutionProvider, got {providers!r}")
    session_input = session.get_inputs()[0]
    session_output = session.get_outputs()[0]
    if (session_input.name, session_input.shape, session_input.type) != (
        INPUT_NAME,
        list(INPUT_SHAPE),
        "tensor(float)",
    ):
        raise ReferenceError("runtime input metadata does not match contract")
    if (session_output.name, session_output.shape, session_output.type) != (
        OUTPUT_NAME,
        list(OUTPUT_SHAPE),
        "tensor(float)",
    ):
        raise ReferenceError("runtime output metadata does not match contract")
    output = session.run([OUTPUT_NAME], {INPUT_NAME: value})[0]
    return ExecutionResult(output=output, providers=providers)


def verify(path: Path = FIXTURE_PATH) -> dict[str, object]:
    model = load_and_validate_model(path)
    del model
    cases: dict[str, dict[str, float]] = {}
    for name, value in fixed_inputs().items():
        expected = numpy_expected(value)
        actual = run_cpu(value, path).output
        try:
            np.testing.assert_allclose(
                actual,
                expected,
                rtol=RELATIVE_TOLERANCE,
                atol=ABSOLUTE_TOLERANCE,
            )
        except AssertionError as exc:
            raise ReferenceError(f"case {name!r} failed elementwise comparison: {exc}") from exc
        cases[name] = {"max_absolute_error": float(np.max(np.abs(actual - expected)))}
    zero_output = run_cpu(fixed_inputs()["zero"], path).output
    changed = fixed_inputs()["zero"].copy()
    changed[0, 0, 1, 1] = np.float32(1.0)
    changed_output = run_cpu(changed, path).output
    if np.array_equal(zero_output, changed_output):
        raise ReferenceError("changing the input must change the output")
    return {
        "backend": "CPUExecutionProvider",
        "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input": {"name": INPUT_NAME, "shape": list(INPUT_SHAPE), "dtype": "float32"},
        "output": {"name": OUTPUT_NAME, "shape": list(OUTPUT_SHAPE), "dtype": "float32"},
        "tolerance": {"absolute": ABSOLUTE_TOLERANCE, "relative": RELATIVE_TOLERANCE},
        "versions": {"numpy": np.__version__, "onnx": onnx.__version__, "onnxruntime": ort.__version__},
        "cases": cases,
        "scope": "synthetic host CPU reference; not FSR4, HTP, device, or game validation",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="write the deterministic ONNX fixture")
    build_parser.add_argument("--output", type=Path, default=FIXTURE_PATH)
    verify_parser = subparsers.add_parser("verify", help="check and execute the fixture on CPU")
    verify_parser.add_argument("--model", type=Path, default=FIXTURE_PATH)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "build":
            digest = write_model(arguments.output)
            print(json.dumps({"model": str(arguments.output), "sha256": digest}, sort_keys=True))
        else:
            print(json.dumps(verify(arguments.model), indent=2, sort_keys=True))
    except ReferenceError as exc:
        print(f"reference verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

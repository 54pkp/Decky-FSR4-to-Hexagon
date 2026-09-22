#!/usr/bin/env python3
"""Run a pinned, host-only P8 pass-0 cross-check against P7 artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import types
from typing import Callable

import numpy as np

REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

from tools.fsr.intake import IntakeError, _check_existing_path, _hash_file
from tools.fsr.artifact_index import INDEX_PATH, current_artifact, load_artifact_index


P7_SOURCE_COMMIT = "c5e34b4b7128ffeb152f80cbdb6d715d577ec289"
P7_SOURCE_URL = "https://github.com/Rolaand-Jayz/FSR-4.0.2-reference"
P7_EXTRACTOR_URL = "https://github.com/puzzled-pancake/fsr4-hexagon"
P7_EXTRACTOR_SHA256 = "73e5533bda45d17f84d2d81315c4152cb912d809a648f63fe06ec2e026f5d31f"
P7_EXTRACTOR_BYTE_COUNT = 15762
SIMULATOR_COMMIT = "8c7a972ab70e5693828a856da71ce711232af463"
SIMULATOR_SHA256 = "e82d407f26d4cd22d7b10d25a5f5d53e236febf98414946ecba32dee1377c0fe"
SIMULATOR_URL = "https://github.com/puzzled-pancake/fsr4-hexagon"
NPZ_NAME = "fsr4_quality_weights.npz"
GRAPH_NAME = "graph_spec.json"
P7_RECEIPT_NAME = "intake_receipt.json"
MAX_RECEIPT_BYTES = 1 << 20
MAX_ARTIFACT_BYTES = 256 << 20
MAX_LSB_ERROR = 0

ARTIFACT_INDEX = load_artifact_index(INDEX_PATH)
CURRENT_P7_ARTIFACT = current_artifact(ARTIFACT_INDEX, "p7-receipt")
CURRENT_P8_ARTIFACT = current_artifact(ARTIFACT_INDEX, "p8-receipt")
P7_ACCEPTED_RECEIPT_SHA256 = CURRENT_P7_ARTIFACT["receipt_sha256"]


class Pass0CheckError(Exception):
    """The selected inputs or pass-0 comparison failed validation."""


@dataclass(frozen=True)
class Pass0Contract:
    source_commit: str = P7_SOURCE_COMMIT
    source_url: str = P7_SOURCE_URL
    extractor_url: str = P7_EXTRACTOR_URL
    extractor_commit: str = SIMULATOR_COMMIT
    extractor_sha256: str = P7_EXTRACTOR_SHA256
    extractor_byte_count: int = P7_EXTRACTOR_BYTE_COUNT
    accepted_p7_receipt_sha256: str = P7_ACCEPTED_RECEIPT_SHA256
    simulator_commit: str = SIMULATOR_COMMIT
    simulator_sha256: str = SIMULATOR_SHA256
    max_lsb_error: int = MAX_LSB_ERROR


PUBLIC_CONTRACT = Pass0Contract()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_file(directory: Path, name: str, label: str) -> Path:
    try:
        path = _check_existing_path(directory / name, directory=False, label=label)
    except IntakeError as exc:
        raise Pass0CheckError(str(exc)) from exc
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise Pass0CheckError(f"{label} escapes the selected P7 directory") from exc
    return path


def _safe_inputs(p7_directory: Path, simulator: Path, output: Path) -> tuple[Path, Path, Path]:
    try:
        p7 = _check_existing_path(p7_directory, directory=True, label="P7 directory")
        sim = _check_existing_path(simulator, directory=False, label="simulator")
        parent = _check_existing_path(output.absolute().parent, directory=True, label="output parent")
    except IntakeError as exc:
        raise Pass0CheckError(str(exc)) from exc
    selected_output = parent / output.name
    if output.name in {"", ".", ".."} or selected_output.suffix.lower() != ".json":
        raise Pass0CheckError("output must be an explicit JSON file path")
    if os.path.lexists(selected_output):
        raise Pass0CheckError(f"output already exists: {selected_output}")
    return p7, sim, selected_output


def _read_json(path: Path, limit: int, label: str) -> tuple[dict[str, object], str]:
    try:
        _, digest, payload = _hash_file(path, limit)
        value = json.loads(payload.decode("utf-8"))
    except (IntakeError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise Pass0CheckError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise Pass0CheckError(f"invalid {label}: root must be an object")
    return value, digest


def _verify_p7(
    p7: Path, contract: Pass0Contract
) -> tuple[bytes, str, bytes, str, str]:
    receipt_path = _safe_file(p7, P7_RECEIPT_NAME, "P7 receipt")
    archive_path = _safe_file(p7, NPZ_NAME, "P7 weights")
    graph_path = _safe_file(p7, GRAPH_NAME, "P7 graph")
    receipt, receipt_hash = _read_json(receipt_path, MAX_RECEIPT_BYTES, "P7 receipt")
    if receipt.get("schema_version") != "p7-fsr-intake-receipt-v2":
        raise Pass0CheckError("P7 receipt is not the required R10a v2 accepted-receipt schema")
    if receipt.get("extraction_gate") != "passed":
        raise Pass0CheckError("P7 receipt extraction gate is not passed")
    source = receipt.get("source")
    extractor = receipt.get("extractor")
    expected_source = {"url": contract.source_url, "commit": contract.source_commit}
    if source != expected_source:
        raise Pass0CheckError("P7 receipt source URL/commit binding mismatch")
    expected_extractor = {
        "url": contract.extractor_url,
        "commit": contract.extractor_commit,
        "byte_count": contract.extractor_byte_count,
        "sha256": contract.extractor_sha256,
    }
    if extractor != expected_extractor:
        raise Pass0CheckError("P7 receipt extractor URL/commit/content binding mismatch")
    environment = receipt.get("environment")
    if not isinstance(environment, dict) or not isinstance(environment.get("python"), dict):
        raise Pass0CheckError("P7 v2 receipt environment binding is missing")
    packages = environment.get("packages")
    if (
        not isinstance(packages, list)
        or len(packages) != 1
        or not isinstance(packages[0], dict)
        or packages[0].get("name") != "numpy"
        or not isinstance(packages[0].get("version"), str)
        or not packages[0]["version"]
    ):
        raise Pass0CheckError("P7 v2 receipt NumPy environment binding is missing or malformed")
    execution = receipt.get("extractor_execution")
    stdout_gate = execution.get("stdout_gate") if isinstance(execution, dict) else None
    if (
        not isinstance(execution, dict)
        or execution.get("temporary_absolute_paths_recorded") is not False
        or execution.get("argv_bindings") != {"0": "environment.python.executable", "2": "extractor"}
        or not isinstance(execution.get("argv"), list)
        or len(execution["argv"]) != 3
        or execution["argv"][1:] != ["-I", "<isolated-extractor>"]
        or not isinstance(stdout_gate, dict)
        or stdout_gate.get("matched") is not True
        or stdout_gate.get("required_exact_lines") != ["ALL GATES PASSED"]
    ):
        raise Pass0CheckError("P7 v2 receipt extractor execution/stdout binding is missing or malformed")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {NPZ_NAME, GRAPH_NAME}:
        raise Pass0CheckError("P7 receipt output binding must contain exactly the weights and graph")
    if receipt_hash != contract.accepted_p7_receipt_sha256:
        raise Pass0CheckError(
            "P7 receipt SHA-256 is not the known accepted R10a receipt: "
            f"expected {contract.accepted_p7_receipt_sha256}, found {receipt_hash}"
        )
    snapshots: dict[str, tuple[bytes, str]] = {}
    for name, path in ((NPZ_NAME, archive_path), (GRAPH_NAME, graph_path)):
        entry = outputs.get(name)
        if not isinstance(entry, dict):
            raise Pass0CheckError(f"P7 receipt output entry is missing: {name}")
        try:
            size, digest, payload = _hash_file(path, MAX_ARTIFACT_BYTES, capture=True)
        except IntakeError as exc:
            raise Pass0CheckError(str(exc)) from exc
        if entry.get("byte_count") != size or entry.get("sha256") != digest:
            raise Pass0CheckError(f"P7 receipt/artifact hash mismatch: {name}")
        snapshots[name] = (payload, digest)
    archive_payload, archive_hash = snapshots[NPZ_NAME]
    graph_payload, graph_hash = snapshots[GRAPH_NAME]
    return archive_payload, archive_hash, graph_payload, graph_hash, receipt_hash


def fixed_input() -> np.ndarray:
    """Return the fixed small HWC fp16 sample; channel 7 is the required zero lane."""
    sample = np.zeros((4, 6, 8), dtype=np.float16)
    for y in range(4):
        for x in range(6):
            for c in range(7):
                magnitude = ((y * 6 * 7 + x * 7 + c) % 15) + 1
                sample[y, x, c] = np.float16(((-1) ** (x + c)) * magnitude / 32.0)
    return sample


def _validate_input(sample: np.ndarray, layout: str) -> None:
    if layout != "HWC":
        raise Pass0CheckError("input layout must be HWC")
    if not isinstance(sample, np.ndarray) or sample.dtype != np.dtype(np.float16):
        raise Pass0CheckError("input dtype must be float16")
    if sample.ndim != 3 or sample.shape[2] != 8 or sample.shape[0] < 2 or sample.shape[1] < 2:
        raise Pass0CheckError("input shape must be HWC with 8 channels and at least 2x2")
    if sample.shape[0] % 2 or sample.shape[1] % 2:
        raise Pass0CheckError("input height and width must be even for pass-0 stride 2")
    if not np.isfinite(sample).all():
        raise Pass0CheckError("input contains non-finite values")
    if not np.any(sample[:, :, :7] != 0):
        raise Pass0CheckError("input must contain non-zero feature values")
    if np.any(sample[:, :, 7] != 0):
        raise Pass0CheckError("input channel 7 must be the pass-0 zero lane")


def scalar_pass0(sample: np.ndarray, weight: np.ndarray, bias: np.ndarray, scale: float) -> np.ndarray:
    """Independent scalar HWC/FKYXC implementation with explicit fp32 accumulation."""
    height, width, _ = sample.shape
    result = np.empty((height // 2, width // 2, 16), dtype=np.int8)
    xf = sample.astype(np.float32)
    wf = weight.astype(np.float16).astype(np.float32)
    bf = bias.astype(np.float32)
    sf = np.float32(scale)
    for oy in range(height // 2):
        for ox in range(width // 2):
            for feature in range(16):
                accumulator = np.float32(0.0)
                for ky in range(2):
                    for kx in range(2):
                        tap = np.float32(0.0)
                        for channel in range(8):
                            product = np.float32(xf[2 * oy + ky, 2 * ox + kx, channel] * wf[feature, ky, kx, channel])
                            tap = np.float32(tap + product)
                        accumulator = np.float32(accumulator + tap)
                scaled = np.float32(np.float32(accumulator + bf[feature]) * np.float32(np.float32(1.0) / sf))
                rounded = math.floor(float(scaled) + 0.5) if scaled >= 0 else -math.floor(float(-scaled) + 0.5)
                result[oy, ox, feature] = np.int8(min(127, max(-128, rounded)))
    return result


def _load_simulator(path: Path, payload: bytes):
    module = types.ModuleType("p8_pinned_fsr4_sim")
    module.__file__ = os.fspath(path)
    module.__package__ = ""
    module.__loader__ = None
    module.__spec__ = None
    try:
        code = compile(payload, os.fspath(path), "exec")
        exec(code, module.__dict__)
    except Exception as exc:
        raise Pass0CheckError(f"cannot import pinned simulator: {exc}") from exc
    if not callable(getattr(module, "pass0", None)):
        raise Pass0CheckError("pinned simulator does not expose pass0")
    return module


def _publish_json(path: Path, value: dict[str, object]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_name, path)
    except FileExistsError as exc:
        raise Pass0CheckError(f"output already exists: {path}") from exc
    except OSError as exc:
        raise Pass0CheckError(f"cannot publish output receipt: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def run_pass0_check(
    p7_directory: Path,
    simulator: Path,
    output: Path,
    *,
    contract: Pass0Contract = PUBLIC_CONTRACT,
    sample: np.ndarray | None = None,
    layout: str = "HWC",
    upstream_runner: Callable[[np.ndarray, dict[str, object]], dict[str, object]] | None = None,
    scalar_runner: Callable[[np.ndarray, np.ndarray, np.ndarray, float], np.ndarray] = scalar_pass0,
) -> dict[str, object]:
    p7, sim_path, output_path = _safe_inputs(p7_directory, simulator, output)
    archive_payload, archive_hash, graph_payload, graph_hash, receipt_hash = _verify_p7(p7, contract)
    try:
        sim_size, sim_hash, simulator_payload = _hash_file(sim_path, 2 << 20, capture=True)
    except IntakeError as exc:
        raise Pass0CheckError(str(exc)) from exc
    if sim_hash != contract.simulator_sha256:
        raise Pass0CheckError("simulator SHA-256 mismatch")
    try:
        graph = json.loads(graph_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Pass0CheckError(f"invalid P7 graph: {exc}") from exc
    if not isinstance(graph, dict):
        raise Pass0CheckError("invalid P7 graph: root must be an object")
    pass0_spec = graph.get("pass0")
    if not isinstance(pass0_spec, dict) or pass0_spec.get("weight_layout") != "[f,ky,kx,c(8, ch7=0)]":
        raise Pass0CheckError("graph pass-0 layout mismatch")
    try:
        with np.load(io.BytesIO(archive_payload), allow_pickle=False) as archive:
            weight = np.array(archive["pass0_weight_fkyxc"], copy=True)
            bias = np.array(archive["pass0_bias"], copy=True)
            scale_table = np.array(archive["bin_scale_table"], copy=True)
    except Exception as exc:
        raise Pass0CheckError(f"cannot load P7 pass-0 arrays: {exc}") from exc
    if weight.shape != (16, 2, 2, 8) or weight.dtype != np.dtype(np.float32):
        raise Pass0CheckError("pass-0 weight shape/dtype mismatch")
    if bias.shape != (16,) or bias.dtype != np.dtype(np.float32):
        raise Pass0CheckError("pass-0 bias shape/dtype mismatch")
    if scale_table.shape != (77,) or scale_table.dtype != np.dtype(np.float32):
        raise Pass0CheckError("pass-0 scale table shape/dtype mismatch")
    scale = float(scale_table[0])
    graph_scale = pass0_spec.get("scale")
    if not math.isfinite(scale) or scale <= 0 or not isinstance(graph_scale, (int, float)) or np.float32(graph_scale) != np.float32(scale):
        raise Pass0CheckError("pass-0 quantization scale mismatch or non-finite scale")
    if not np.isfinite(weight).all() or not np.isfinite(bias).all():
        raise Pass0CheckError("pass-0 parameters contain non-finite values")
    if not np.all(weight[:, :, :, 7] == np.float32(0.0)):
        raise Pass0CheckError("pass-0 channel-7 weights must all be zero")
    selected_sample = fixed_input() if sample is None else sample
    _validate_input(selected_sample, layout)
    module = _load_simulator(sim_path, simulator_payload)
    layers: dict[str, object] = {
        "pass0_weight_fkyxc": weight,
        "pass0_bias": bias,
        "_pass0_scale": scale,
    }
    runner = module.pass0 if upstream_runner is None else upstream_runner
    expected_shape = (selected_sample.shape[0] // 2, selected_sample.shape[1] // 2, 16)
    def run_upstream(candidate: np.ndarray, label: str) -> np.ndarray:
        try:
            value = runner(candidate, layers)
            output_array = np.asarray(value["q"])
            output_scale = float(value["s"])
        except Exception as exc:
            raise Pass0CheckError(f"upstream pass0 failed for {label}: {exc}") from exc
        if output_array.shape != expected_shape or output_array.dtype != np.dtype(np.int8):
            raise Pass0CheckError("upstream output shape/dtype mismatch")
        if np.float32(output_scale) != np.float32(scale):
            raise Pass0CheckError("upstream output scale mismatch")
        return output_array

    upstream = run_upstream(selected_sample, "baseline")
    upstream_repeat = run_upstream(selected_sample, "baseline repeat")
    if not np.array_equal(upstream, upstream_repeat):
        raise Pass0CheckError("upstream pass0 is not deterministic for repeated input")
    changed_sample = selected_sample.copy()
    changed_sample[0, 0, 0] = np.float16(4.0)
    changed_output = run_upstream(changed_sample, "effective-channel mutation")
    if np.array_equal(upstream, changed_output):
        raise Pass0CheckError("effective channel mutation did not change upstream output")
    poisoned_sample = selected_sample.copy()
    poisoned_sample[:, :, 7] = np.float16(3.0)
    poisoned_output = run_upstream(poisoned_sample, "channel-7 poison")
    if not np.array_equal(upstream, poisoned_output):
        raise Pass0CheckError("channel-7 poison changed upstream output")
    independent = np.asarray(scalar_runner(selected_sample, weight, bias, scale))
    if independent.shape != expected_shape or independent.dtype != np.dtype(np.int8):
        raise Pass0CheckError("independent output shape/dtype mismatch")
    delta = np.abs(upstream.astype(np.int16) - independent.astype(np.int16))
    max_lsb = int(delta.max(initial=0))
    if max_lsb > contract.max_lsb_error:
        raise Pass0CheckError(
            f"upstream/independent pass-0 mismatch: {max_lsb} LSB exceeds {contract.max_lsb_error}"
        )
    receipt: dict[str, object] = {
        "schema_version": "p8-fsr-pass0-check-v1",
        "result": "passed",
        "scope": "fixed public-material pass-0 host CPU cross-check",
        "backend": "host CPU / NumPy",
        "p7": {
            "receipt": {"file": P7_RECEIPT_NAME, "sha256": receipt_hash},
            "weights": {"file": NPZ_NAME, "sha256": archive_hash},
            "graph": {"file": GRAPH_NAME, "sha256": graph_hash},
        },
        "simulator": {
            "url": SIMULATOR_URL,
            "commit": contract.simulator_commit,
            "sha256": sim_hash,
            "byte_count": sim_size,
        },
        "input": {
            "layout": layout,
            "shape": list(selected_sample.shape),
            "dtype": str(selected_sample.dtype),
            "sha256": _sha256_bytes(selected_sample.tobytes(order="C")),
            "nonzero_count": int(np.count_nonzero(selected_sample)),
            "channel_7": "zero lane",
        },
        "parameters": {
            "weight_layout": "FKYXC",
            "stored_weight_shape": list(weight.shape),
            "stored_weight_dtype": str(weight.dtype),
            "simulator_weight_dtype": "float16",
            "accumulator_dtype": "float32",
            "quantization_scale": scale,
            "rounding": "half away from zero",
            "output_saturation": [-128, 127],
        },
        "output": {
            "layout": "HWC",
            "shape": list(upstream.shape),
            "dtype": str(upstream.dtype),
            "upstream_sha256": _sha256_bytes(upstream.tobytes(order="C")),
            "independent_sha256": _sha256_bytes(independent.tobytes(order="C")),
            "max_int8_lsb_difference": max_lsb,
            "predefined_max_int8_lsb_difference": contract.max_lsb_error,
            "minimum": int(upstream.min()),
            "maximum": int(upstream.max()),
            "negative_saturation_count": int(np.count_nonzero(upstream == -128)),
            "positive_saturation_count": int(np.count_nonzero(upstream == 127)),
        },
        "validation_gates": {
            "upstream_repeat_is_bit_exact": True,
            "effective_channel_0_single_point_changes_output": True,
            "channel_7_finite_poison_is_invariant": True,
            "weight_channel_7_is_all_zero": True,
            "changed_input_sha256": _sha256_bytes(changed_sample.tobytes(order="C")),
            "changed_output_sha256": _sha256_bytes(changed_output.tobytes(order="C")),
            "poisoned_input_sha256": _sha256_bytes(poisoned_sample.tobytes(order="C")),
        },
        "limitations": {
            "official_golden": "not_available",
            "full_fsr4": "not_run",
            "onnx_qnn_htp_device_game": "not_run",
            "shared_weight_source": True,
        },
    }
    _publish_json(output_path, receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p7-directory", required=True, type=Path)
    parser.add_argument("--simulator", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = run_pass0_check(args.p7_directory, args.simulator, args.output)
    except Pass0CheckError as exc:
        print(f"pass-0 check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

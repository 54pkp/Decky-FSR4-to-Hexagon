#!/usr/bin/env python3
"""Run the pinned P5 small graph through QAIRT 2.49 and QNN CPU.

This is host-only synthetic evidence.  It does not execute HTP and is not FSR.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.qairt.probe import DEFAULT_PROFILE


SCHEMA_VERSION = "qairt-small-graph-pipeline-v1"
ATOL = 0.01
RTOL = 0.0
MAX_METADATA_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 300
P5_MODEL_SHA256 = "f89d2af81c2a9bbde23a7cf4b2a8ee2614535f491ab7f259ac3151328f4f42d4"
INPUT_NAME = "reference_input"
OUTPUT_NAME = "reference_output"
SHAPE = (1, 1, 4, 4)
SDK_EXTRA_FILES = {
    "lib/x86_64-windows-msvc/QnnModelDlc.dll": (2613456, "5a29577586e60a1797e8a62d86415b5b8a01e7073651c5ea35fe259d8ac67461"),
}


class PipelineError(Exception):
    """A pinned input, process, metadata, or numerical gate failed."""


@dataclass(frozen=True)
class PipelineProfile:
    version: str
    build_id: str
    files: Mapping[str, tuple[int, str]]
    model_sha256: str = P5_MODEL_SHA256


PINNED_PROFILE = PipelineProfile(
    DEFAULT_PROFILE.version,
    DEFAULT_PROFILE.build_id,
    {
        name: DEFAULT_PROFILE.files[name]
        for name in (
            "sdk.yaml",
            "bin/x86_64-windows-msvc/qairt-converter",
            "bin/x86_64-windows-msvc/qairt-quantizer",
            "bin/x86_64-windows-msvc/qairt-dlc-info",
            "bin/x86_64-windows-msvc/qnn-net-run.exe",
            "lib/x86_64-windows-msvc/QnnCpu.dll",
        )
    }
    | SDK_EXTRA_FILES,
)


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _is_reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _regular(path: Path, label: str) -> None:
    try:
        value = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise PipelineError(f"cannot inspect {label}: {exc}") from exc
    if _is_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise PipelineError(f"{label} must be a regular non-reparse file")
    for item in path.parents:
        ancestor = os.stat(item, follow_symlinks=False)
        if _is_reparse(ancestor) or not stat.S_ISDIR(ancestor.st_mode):
            raise PipelineError(f"{label} must not traverse a reparse/non-directory ancestor: {item}")


def _safe_new_root(path: Path, label: str) -> Path:
    selected = Path(os.path.abspath(os.fspath(path)))
    if selected.exists():
        raise PipelineError(f"{label} already exists: {selected}")
    parent = selected.parent
    for item in (parent, *parent.parents):
        value = os.stat(item, follow_symlinks=False)
        if _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise PipelineError(f"{label} must not traverse a reparse/non-directory ancestor: {item}")
    return selected


def _file_record(path: Path, relative_to: Path | None = None) -> dict[str, object]:
    return {
        "file": str(path.relative_to(relative_to)) if relative_to else str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: Path, label: str) -> Any:
    _regular(path, label)
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise PipelineError(f"{label} is too large")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read {label}: {exc}") from exc


def _logical(argv: Sequence[str], roots: Mapping[str, Path]) -> list[str]:
    result: list[str] = []
    ordered = sorted(roots.items(), key=lambda pair: len(str(pair[1])), reverse=True)
    for argument in argv:
        logical = str(argument)
        for token, root in ordered:
            root_text = str(root)
            if os.path.normcase(logical).startswith(os.path.normcase(root_text)):
                logical = token + logical[len(root_text):].replace("\\", "/")
                break
        result.append(logical)
    return result


def _sdk_environment(sdk: Path, qairt_python: Path) -> dict[str, str]:
    scripts = qairt_python.parent
    bin_dir = sdk / "bin" / "x86_64-windows-msvc"
    lib_dir = sdk / "lib" / "x86_64-windows-msvc"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"QAIRT_SDK_ROOT", "QNN_SDK_ROOT", "SNPE_ROOT", "AISW_SDK_ROOT", "PYTHONPATH", "PATH"}
    }
    environment.update(
        {
            "QAIRT_SDK_ROOT": str(sdk),
            "QNN_SDK_ROOT": str(sdk),
            "SNPE_ROOT": str(sdk),
            "AISW_SDK_ROOT": str(sdk),
            "PYTHONPATH": str(sdk / "lib" / "python"),
            "PATH": os.pathsep.join((str(bin_dir), str(lib_dir), str(scripts))),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "VIRTUAL_ENV": str(scripts.parent),
        }
    )
    return environment


def _reference_environment(reference_python: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"QAIRT_SDK_ROOT", "QNN_SDK_ROOT", "SNPE_ROOT", "AISW_SDK_ROOT", "PYTHONPATH", "PATH"}
    }
    environment.update({"PATH": str(reference_python.parent), "VIRTUAL_ENV": str(reference_python.parent.parent), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return environment


Runner = Callable[[Sequence[str], Mapping[str, str], Path, Path, Path, int], int]


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str], cwd: Path, stdout: Path, stderr: Path, timeout: int) -> int:
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            completed = subprocess.run(argv, cwd=cwd, env=env, stdout=out, stderr=err, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PipelineError(f"could not execute {Path(argv[0]).name}: {exc}") from exc
    return completed.returncode


def _run_stage(name: str, argv: Sequence[str], env: Mapping[str, str], work: Path, roots: Mapping[str, Path], runner: Runner) -> dict[str, object]:
    stdout = work / "logs" / f"{name}.stdout.log"
    stderr = work / "logs" / f"{name}.stderr.log"
    code = runner(argv, env, work, stdout, stderr, TIMEOUT_SECONDS)
    record = {
        "name": name,
        "argv": _logical(argv, roots),
        "executable": _file_record(Path(argv[0])),
        "exit_code": code,
        "stdout": _file_record(stdout, work),
        "stderr": _file_record(stderr, work),
    }
    if code != 0:
        raise PipelineError(f"stage {name} failed with exit code {code}")
    return record


def _all_named(value: Any, target: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == target:
                items = child if isinstance(child, list) else [child]
                found.extend(item for item in items if isinstance(item, dict))
            found.extend(_all_named(child, target))
    elif isinstance(value, list):
        for child in value:
            found.extend(_all_named(child, target))
    return found


def _first_field(item: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def _encoding(
    json_value: Any,
    csv_encodings: Mapping[str, Mapping[str, float | int]],
    name: str,
    bits: int,
    signed: bool,
    symmetric: bool,
) -> dict[str, object]:
    candidates = _all_named(json_value, name)
    if len(candidates) != 1:
        raise PipelineError(f"encoding JSON must contain exactly one per-tensor encoding for {name}")
    item = candidates[0]
    bitwidth = _first_field(item, "bitwidth", "bw", "bits")
    if int(bitwidth) != bits:
        raise PipelineError(f"{name} bitwidth must be {bits}")
    dtype_text = str(_first_field(item, "dtype", "data_type", "type") or "").lower()
    signed_value = _first_field(item, "is_signed", "signed")
    observed_signed = None
    if isinstance(signed_value, bool):
        observed_signed = signed_value
    elif dtype_text:
        observed_signed = "sfxp" in dtype_text and "ufxp" not in dtype_text
    if observed_signed is not None and observed_signed != signed:
        raise PipelineError(f"{name} signedness mismatch")
    symmetric_value = _first_field(item, "is_symmetric", "symmetric")
    if isinstance(symmetric_value, str):
        symmetric_value = symmetric_value.strip().lower() == "true"
    if bool(symmetric_value) != symmetric:
        raise PipelineError(f"{name} symmetry mismatch")
    axis = _first_field(item, "axis", "channel_axis", "quantized_dimension")
    if axis not in (None, "", -1, "-1"):
        raise PipelineError(f"{name} must use per-tensor encoding with no axis")
    try:
        scale = float(_first_field(item, "scale"))
        offset_number = float(_first_field(item, "offset"))
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"{name} scale/offset must be numeric") from exc
    if not math.isfinite(scale) or scale <= 0:
        raise PipelineError(f"{name} scale must be finite and positive")
    if not math.isfinite(offset_number) or not offset_number.is_integer():
        raise PipelineError(f"{name} offset must be a finite integer")
    offset = int(offset_number)
    zero_point_value = -offset
    minimum_zero_point = -(1 << (bits - 1)) if signed else 0
    maximum_zero_point = (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1
    if not minimum_zero_point <= zero_point_value <= maximum_zero_point:
        raise PipelineError(f"{name} zero_point is outside the {bits}-bit {'signed' if signed else 'unsigned'} range")
    if symmetric and zero_point_value != 0:
        raise PipelineError(f"{name} symmetric encoding must have zero_point 0")
    zero_point = _first_field(item, "zero_point", "zeropoint")
    if zero_point is not None:
        try:
            supplied_zero_point = float(zero_point)
        except (TypeError, ValueError) as exc:
            raise PipelineError(f"{name} zero_point must be numeric") from exc
        if not math.isfinite(supplied_zero_point) or not supplied_zero_point.is_integer() or int(supplied_zero_point) != zero_point_value:
            raise PipelineError(f"{name} zero_point must equal -offset")
    csv_encoding = csv_encodings.get(name)
    if csv_encoding is None:
        raise PipelineError(f"metadata CSV is missing encoding values for {name}")
    if csv_encoding["bitwidth"] != bits:
        raise PipelineError(f"encoding JSON/CSV bitwidth mismatch for {name}")
    csv_scale = float(csv_encoding["scale"])
    csv_offset = float(csv_encoding["offset"])
    if not math.isfinite(csv_scale) or csv_scale <= 0:
        raise PipelineError(f"metadata CSV scale must be finite and positive for {name}")
    if not math.isfinite(csv_offset) or not csv_offset.is_integer():
        raise PipelineError(f"metadata CSV offset must be a finite integer for {name}")
    if int(csv_offset) != offset:
        raise PipelineError(f"encoding JSON/CSV offset mismatch for {name}")
    # dlc-info prints twelve decimal places, so sub-picounit scales are compared
    # against that output precision rather than requiring identical text floats.
    if not math.isclose(csv_scale, scale, rel_tol=1e-9, abs_tol=5e-13):
        raise PipelineError(f"encoding JSON/CSV scale mismatch for {name}")
    return {"name": name, "type": ("sFxp" if signed else "uFxp") + f"_{bits}", "bitwidth": bits, "signed": signed, "symmetric": symmetric, "scale": scale, "offset": offset, "zero_point": zero_point_value, "axis": None, "granularity": "per_tensor"}


def _parse_csv_rows(path: Path) -> list[list[str]]:
    _regular(path, "DLC metadata CSV")
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise PipelineError("DLC metadata CSV is too large")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows:
        raise PipelineError("DLC metadata CSV has no structured rows")
    return rows


def _validate_csv_tensor_types(rows: Sequence[Sequence[str]]) -> None:
    text = "\n".join(",".join(row) for row in rows)
    required = {
        INPUT_NAME: "uFxp_8",
        "biased_output": "uFxp_8",
        OUTPUT_NAME: "uFxp_8",
        "conv_weight": "uFxp_8",
        "conv_bias": "sFxp_32",
    }
    for name, dtype in required.items():
        pattern = rf"\b{re.escape(name)} \(data type: {re.escape(dtype)};"
        if re.search(pattern, text) is None:
            raise PipelineError(f"metadata CSV dtype/signedness mismatch for {name}")


def _csv_encodings(rows: Sequence[Sequence[str]]) -> dict[str, dict[str, float | int]]:
    text = "\n".join(",".join(row) for row in rows)
    pattern = re.compile(
        r"\b([A-Za-z0-9_]+) encoding : bitwidth (\d+), min [^,]+, max [^,]+, "
        r"scale ([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?), "
        r"offset ([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    )
    result: dict[str, dict[str, float | int]] = {}
    for match in pattern.finditer(text):
        name = match.group(1)
        value: dict[str, float | int] = {
            "bitwidth": int(match.group(2)),
            "scale": float(match.group(3)),
            "offset": float(match.group(4)),
        }
        previous = result.get(name)
        if previous is not None and previous != value:
            raise PipelineError(f"metadata CSV contains conflicting encodings for {name}")
        result[name] = value
    return result


def _validate_external_metadata(rows: Sequence[Sequence[str]]) -> dict[str, object]:
    result: dict[str, object] = {}
    metadata_text = "\n".join(",".join(row) for row in rows)
    for name, role, header in ((INPUT_NAME, "input", "Input Name"), (OUTPUT_NAME, "output", "Output Name")):
        matches: list[Sequence[str]] = []
        for index, row in enumerate(rows[:-1]):
            if not row or row[0].strip() != header:
                continue
            for candidate in rows[index + 1:]:
                if candidate:
                    if candidate[0].strip() == name:
                        matches.append(candidate)
                    break
        if len(matches) != 1:
            raise PipelineError(f"metadata CSV must contain one external {role} row for {name}")
        row = matches[0]
        if len(row) < 4 or row[1].replace(" ", "") != "1,1,4,4":
            raise PipelineError(f"{name} metadata shape mismatch")
        if row[2].strip() != "uFxp_8":
            raise PipelineError(f"{name} metadata dtype mismatch")
        if "desired_io_layout" not in metadata_text or re.search(rf"['\"]{re.escape(name)}['\"]\s*,\s*['\"]NCHW['\"]", metadata_text) is None:
            raise PipelineError(f"{name} metadata layout mismatch")
        result[role] = {"name": name, "shape": list(SHAPE), "layout": "NCHW", "dtype": "uFxp_8"}
    return result


def validate_metadata(encoding_json: Path, metadata_csv: Path) -> dict[str, object]:
    value = _read_json(encoding_json, "encoding JSON")
    rows = _parse_csv_rows(metadata_csv)
    _validate_csv_tensor_types(rows)
    csv_encodings = _csv_encodings(rows)
    encodings = [
        _encoding(value, csv_encodings, INPUT_NAME, 8, False, False),
        _encoding(value, csv_encodings, OUTPUT_NAME, 8, False, False),
        _encoding(value, csv_encodings, "biased_output", 8, False, False),
        _encoding(value, csv_encodings, "conv_weight", 8, False, False),
        _encoding(value, csv_encodings, "conv_bias", 32, True, True),
    ]
    return {"encodings": encodings, "external_io": _validate_external_metadata(rows)}


def _find_one(root: Path, patterns: Sequence[str], label: str) -> Path:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(root.rglob(pattern))
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise PipelineError(f"expected exactly one {label}, found {len(unique)}")
    _regular(unique[0], label)
    return unique[0]


def _compare_cpu(export: Path, cpu: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    outputs = sorted(cpu.rglob("*.raw"))
    if len(outputs) != 3:
        raise PipelineError(f"expected three QNN CPU raw outputs, found {len(outputs)}")
    case_names = ("zero", "pattern", "seeded_nonzero")
    arrays: list[np.ndarray] = []
    for index, name in enumerate(case_names):
        expected_path = export / f"{name}.expected.raw"
        actual_path = outputs[index]
        for path, label in ((expected_path, "expected"), (actual_path, "QNN CPU output")):
            _regular(path, f"{name} {label}")
            if path.stat().st_size != 64:
                raise PipelineError(f"{name} {label} must be exactly 64 bytes")
        expected = np.fromfile(expected_path, dtype="<f4")
        actual = np.fromfile(actual_path, dtype="<f4")
        if expected.size != 16 or actual.size != 16:
            raise PipelineError(f"{name} expected/output must contain exactly 16 float32 values")
        if not np.isfinite(expected).all() or not np.isfinite(actual).all():
            raise PipelineError(f"{name} expected/output must contain only finite float32 values")
        arrays.append(actual)
    if np.array_equal(arrays[0], arrays[1]) or np.array_equal(arrays[0], arrays[2]):
        raise PipelineError("pattern and seeded CPU outputs must differ from zero output")
    for index, name in enumerate(case_names):
        expected_path = export / f"{name}.expected.raw"
        actual_path = outputs[index]
        expected = np.fromfile(expected_path, dtype="<f4")
        actual = arrays[index]
        if actual.shape != expected.shape:
            raise PipelineError(f"CPU output shape mismatch for {name}")
        difference = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
        maximum = float(np.max(difference))
        mean = float(np.mean(difference))
        if not np.allclose(actual, expected, atol=ATOL, rtol=RTOL):
            raise PipelineError(f"CPU output exceeds tolerance for {name}: max {maximum}")
        results.append({"name": name, "output": _file_record(actual_path, cpu), "expected": _file_record(expected_path, export), "max_absolute_error": maximum, "mean_absolute_error": mean})
    return results


def run_pipeline(
    sdk_root: Path,
    qairt_python: Path,
    reference_python: Path,
    model: Path,
    work_root: Path,
    output_root: Path,
    p3_receipt: Path,
    *,
    profile: PipelineProfile = PINNED_PROFILE,
    runner: Runner = _subprocess_runner,
) -> dict[str, object]:
    sdk = Path(os.path.abspath(os.fspath(sdk_root)))
    qairt_python = Path(os.path.abspath(os.fspath(qairt_python)))
    reference_python = Path(os.path.abspath(os.fspath(reference_python)))
    model = Path(os.path.abspath(os.fspath(model)))
    p3_receipt = Path(os.path.abspath(os.fspath(p3_receipt)))
    work = _safe_new_root(work_root, "work root")
    output = _safe_new_root(output_root, "output root")
    output_parent_identity = (os.stat(output.parent, follow_symlinks=False).st_dev, os.stat(output.parent, follow_symlinks=False).st_ino)
    if any(character.isspace() for character in str(work)):
        raise PipelineError("work root path must contain no whitespace")
    for path, label in ((qairt_python, "QAIRT Python"), (reference_python, "reference Python"), (model, "P5 model"), (p3_receipt, "P3 receipt")):
        _regular(path, label)
    receipt_value = _read_json(p3_receipt, "P3 receipt")
    if receipt_value.get("schema_version") != "qairt-windows-host-probe-v1" or receipt_value.get("profile") != "QAIRT-2.49.0.260730-windows-x86_64":
        raise PipelineError("P3 receipt profile mismatch")
    if receipt_value.get("sdk", {}).get("version") != profile.version or receipt_value.get("sdk", {}).get("build_id") != profile.build_id:
        raise PipelineError("P3 receipt SDK version/build mismatch")
    sdk_files: dict[str, dict[str, object]] = {}
    selected_files = {entry.get("path"): entry for entry in receipt_value.get("selected_files", []) if isinstance(entry, dict)}
    for relative, (expected_size, expected_hash) in profile.files.items():
        path = sdk / Path(relative)
        _regular(path, f"SDK file {relative}")
        if path.stat().st_size != expected_size or _sha256(path) != expected_hash:
            raise PipelineError(f"SDK file hash/size mismatch: {relative}")
        sdk_files[relative] = _file_record(path, sdk)
        if relative != "lib/x86_64-windows-msvc/QnnModelDlc.dll" and relative not in selected_files:
            raise PipelineError(f"P3 receipt is missing selected file: {relative}")
        if relative in selected_files and (
            selected_files[relative].get("bytes") != expected_size
            or selected_files[relative].get("sha256") != expected_hash
        ):
            raise PipelineError(f"P3 receipt selected-file mismatch: {relative}")
    if _sha256(model) != profile.model_sha256:
        raise PipelineError("P5 model hash mismatch")

    work.mkdir()
    work_identity = (os.stat(work, follow_symlinks=False).st_dev, os.stat(work, follow_symlinks=False).st_ino)
    (work / "logs").mkdir()
    export = work / "reference_export"
    cpu = work / "cpu_outputs"
    cpu.mkdir()
    env = _sdk_environment(sdk, qairt_python)
    roots = {"<sdk>": sdk, "<work>": work, "<qairt-python>": qairt_python, "<reference-python>": reference_python, "<model>": model}
    stages: list[dict[str, object]] = []
    reference_script = Path(__file__).resolve().parents[1] / "reference" / "small_graph.py"
    converter = sdk / "bin/x86_64-windows-msvc/qairt-converter"
    quantizer = sdk / "bin/x86_64-windows-msvc/qairt-quantizer"
    dlc_info = sdk / "bin/x86_64-windows-msvc/qairt-dlc-info"
    net_run = sdk / "bin/x86_64-windows-msvc/qnn-net-run.exe"
    float_dlc = work / "small_graph.float.dlc"
    quant_dlc = work / "small_graph.w8a8.dlc"
    csv_path = work / "small_graph.metadata.csv"
    try:
        stages.append(_run_stage("reference_export", [str(reference_python), str(reference_script), "export", "--model", str(model), "--output", str(export)], _reference_environment(reference_python), work, roots, runner))
        stages.append(_run_stage("converter", [str(qairt_python), str(converter), "--input_network", str(model), "--output_path", str(float_dlc), "--target_backend", "HTP", "--source_model_input_shape", INPUT_NAME, "1,1,4,4", "--source_model_input_layout", INPUT_NAME, "NCHW", "--desired_input_layout", INPUT_NAME, "NCHW", "--source_model_output_layout", OUTPUT_NAME, "NCHW", "--desired_output_layout", OUTPUT_NAME, "NCHW"], env, work, roots, runner))
        stages.append(_run_stage("quantizer", [str(qairt_python), str(quantizer), "--input_dlc", str(float_dlc), "--output_dlc", str(quant_dlc), "--input_list", str(export / "input_list.txt"), "--act_bitwidth", "8", "--weights_bitwidth", "8", "--bias_bitwidth", "32", "--target_backend", "HTP", "--dump_encoding_json"], env, work, roots, runner))
        encoding_json = _find_one(work, ("*encoding*.json", "*encodings*.json"), "encoding JSON")
        stages.append(_run_stage("dlc_info", [str(qairt_python), str(dlc_info), "--input_dlc", str(quant_dlc), "--display_all_encodings", "--save", str(csv_path)], env, work, roots, runner))
        metadata = validate_metadata(encoding_json, csv_path)
        stages.append(_run_stage("qnn_cpu", [str(net_run), "--backend", str(sdk / "lib/x86_64-windows-msvc/QnnCpu.dll"), "--model", str(sdk / "lib/x86_64-windows-msvc/QnnModelDlc.dll"), "--dlc_path", str(quant_dlc), "--input_list", str(export / "input_list.txt"), "--output_dir", str(cpu)], env, work, roots, runner))
        comparisons = _compare_cpu(export, cpu)
        bound_files = {str(path.relative_to(work)): _file_record(path, work) for path in sorted(work.rglob("*")) if path.is_file()}
        receipt: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "result": "passed",
            "backend": "QNN_CPU",
            "sdk": {"product": "QAIRT", "version": profile.version, "build_id": profile.build_id, "root": str(sdk), "files": sdk_files},
            "inputs": {"model": _file_record(model), "p3_receipt": _file_record(p3_receipt), "qairt_python": _file_record(qairt_python), "reference_python": _file_record(reference_python), "pipeline_script": _file_record(Path(__file__).resolve()), "reference_script": _file_record(reference_script)},
            "quantization": {"target_backend": "HTP", "weights_bitwidth": 8, "activations_bitwidth": 8, "bias_bitwidth": 32, "metadata": metadata},
            "tolerance": {"absolute": ATOL, "relative": RTOL},
            "cases": comparisons,
            "stages": stages,
            "artifacts": bound_files,
            "not_run": {"device": "not_run", "htp_execution": "not_run", "fsr": "not_run", "game": "not_run"},
            "scope": "synthetic small graph on Windows QNN CPU; not FSR, HTP, device, or game validation",
        }
        staging = output.parent / (output.name + ".publishing")
        if staging.exists():
            raise PipelineError(f"publication staging path already exists: {staging}")
        current_output_parent = os.stat(output.parent, follow_symlinks=False)
        current_work = os.stat(work, follow_symlinks=False)
        if _is_reparse(current_output_parent) or (current_output_parent.st_dev, current_output_parent.st_ino) != output_parent_identity:
            raise PipelineError("output parent identity changed during pipeline")
        if _is_reparse(current_work) or (current_work.st_dev, current_work.st_ino) != work_identity:
            raise PipelineError("work root identity changed during pipeline")
        try:
            shutil.copytree(work, staging)
            (staging / "success_receipt.json").write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            os.replace(staging, output)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return receipt
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--qairt-python", type=Path, required=True)
    parser.add_argument("--reference-python", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--p3-receipt", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        receipt = run_pipeline(arguments.sdk_root, arguments.qairt_python, arguments.reference_python, arguments.model, arguments.work_root, arguments.output_root, arguments.p3_receipt)
    except PipelineError as exc:
        print(f"QAIRT small-graph pipeline failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"receipt": str(arguments.output_root / "success_receipt.json"), "backend": receipt["backend"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

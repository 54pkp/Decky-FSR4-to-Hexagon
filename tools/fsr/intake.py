#!/usr/bin/env python3
"""Verify pinned public inputs and run the pinned extractor in isolation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Sequence
import zipfile


SOURCE_URL = "https://github.com/Rolaand-Jayz/FSR-4.0.2-reference"
SOURCE_COMMIT = "c5e34b4b7128ffeb152f80cbdb6d715d577ec289"
EXTRACTOR_URL = "https://github.com/puzzled-pancake/fsr4-hexagon"
EXTRACTOR_COMMIT = "8c7a972ab70e5693828a856da71ce711232af463"
RECEIPT_NAME = "intake_receipt.json"
CHUNK = 1 << 20
MAX_OUTPUT_BYTES = 256 << 20


@dataclass(frozen=True)
class FileRule:
    path: str
    size: int
    sha256: str
    markers: tuple[bytes, ...] = ()
    prefix: bytes | None = None


@dataclass(frozen=True)
class IntakeContract:
    source_url: str
    source_commit: str
    extractor_url: str
    extractor_commit: str
    inputs: tuple[FileRule, ...]
    extractor: FileRule
    archive_name: str = "fsr4_quality_weights.npz"
    spec_name: str = "graph_spec.json"
    spec_markers: tuple[tuple[str, str], ...] = (
        ("preset", "quality"),
        ("model", "fsr4_model_v07_i8"),
    )
    validate_public_archive: bool = False
    spec_counts: tuple[tuple[str, int], ...] = ()


PUBLIC_CONTRACT = IntakeContract(
    source_url=SOURCE_URL,
    source_commit=SOURCE_COMMIT,
    extractor_url=EXTRACTOR_URL,
    extractor_commit=EXTRACTOR_COMMIT,
    inputs=(
        FileRule(
            "Kits/FidelityFX/upscalers/fsr4/internal/shaders/fsr4_model_v07_i8_quality/initializers.bin",
            89216,
            "6fce93853235bbf8742210fb2bfd8653b70c90c722af17f5a37d1a3390156356",
            prefix=bytes.fromhex("12df733c00000000"),
        ),
        FileRule(
            "Kits/FidelityFX/upscalers/fsr4/internal/shaders/fsr4_model_v07_i8_quality/passes_1080.hlsl",
            496305,
            "ab6762596c4439b759557a048d9b13a907baab99c9bab57cd13c416935e99bac",
            (b"fsr4_model_v07_i8.onnx", b"fsr4_model_v07_i8_pass0"),
        ),
        FileRule(
            "Kits/FidelityFX/upscalers/fsr4/internal/shaders/fsr4_model_v07_i8_quality/pre.hlsl",
            7949,
            "b7c9c4868854eec2886922427dc2043c5b5fc9724855d534a7338832849da626",
            (b"embedded_encoder1_DownscaleStridedConv2x2_downscale_conv_weight_dwords[256]",),
        ),
        FileRule(
            "Kits/FidelityFX/upscalers/fsr4/internal/shaders/fsr4_model_v07_i8_quality/post.hlsl",
            43213,
            "f1c3e536d695d48b40c61ed3c2deb4d58e01f2d16f3eb2b152684ecbb5a2d935",
            (b"QuantizedTensor3i8_NHWC", b"decoder2_ResidualBlock_2"),
        ),
        FileRule(
            "Kits/FidelityFX/upscalers/fsr4/dx12/ffx_provider_fsr4_dx12.cpp",
            124618,
            "3aa93a403e6a21c17d0f697aa4db00d86ea97959eeb6b2bb5377c83079d9180c",
            (b"weights_quality[256]", b"pass0_weights"),
        ),
    ),
    extractor=FileRule(
        "build_weights.py",
        15762,
        "73e5533bda45d17f84d2d81315c4152cb912d809a648f63fe06ec2e026f5d31f",
        (b"fsr4_model_v07_i8_quality", b"ALL GATES PASSED"),
    ),
    validate_public_archive=True,
    spec_counts=(("bin_tensors", 11), ("decls", 58), ("calls", 13)),
)


class IntakeError(Exception):
    """A selected path, pinned input, extractor run, or output is invalid."""


def _is_link_or_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _check_existing_path(path: Path, *, directory: bool, label: str) -> Path:
    selected = _absolute(path)
    anchor = Path(selected.anchor)
    current = anchor
    try:
        for part in selected.parts[1:]:
            current = current / part
            info = current.stat(follow_symlinks=False)
            if _is_link_or_reparse(info):
                raise IntakeError(f"{label} must not contain a symlink or reparse point: {current}")
        info = selected.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise IntakeError(f"{label} does not exist: {selected}") from exc
    except OSError as exc:
        raise IntakeError(f"cannot inspect {label} {selected}: {exc}") from exc
    wanted = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not wanted:
        raise IntakeError(f"{label} is not a {'directory' if directory else 'regular file'}: {selected}")
    return selected.resolve(strict=True)


def _selected_file(root: Path, relative: str, label: str) -> Path:
    if not relative or "\\" in relative or Path(relative).is_absolute() or any(p in {"", ".", ".."} for p in relative.split("/")):
        raise IntakeError(f"unsafe fixed relative path for {label}: {relative!r}")
    selected = _check_existing_path(root.joinpath(*relative.split("/")), directory=False, label=label)
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise IntakeError(f"{label} escapes the selected SDK root: {relative}") from exc
    return selected


def _hash_file(path: Path, limit: int = MAX_OUTPUT_BYTES, *, capture: bool = True) -> tuple[int, str, bytes]:
    digest = hashlib.sha256()
    total = 0
    sample = bytearray()
    before = path.stat(follow_symlinks=False)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise IntakeError(f"file changed before it could be read: {path}")
        while chunk := stream.read(CHUNK):
            total += len(chunk)
            if total > limit:
                raise IntakeError(f"file exceeds {limit} byte limit: {path}")
            digest.update(chunk)
            if capture:
                sample.extend(chunk)
    after = path.stat(follow_symlinks=False)
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise IntakeError(f"file changed while it was read: {path}")
    return total, digest.hexdigest(), bytes(sample)


def _verify_rule(path: Path, rule: FileRule, label: str) -> dict[str, object]:
    size, digest, payload = _hash_file(path, max(rule.size, 1) + 1)
    if size != rule.size:
        raise IntakeError(f"{label} size mismatch: expected {rule.size}, found {size}")
    if rule.prefix is not None and not payload.startswith(rule.prefix):
        raise IntakeError(f"{label} has an invalid byte-order/version prefix")
    missing = [marker.decode("ascii", "backslashreplace") for marker in rule.markers if marker not in payload]
    if missing:
        raise IntakeError(f"{label} is missing required version/content marker: {missing[0]}")
    if digest != rule.sha256:
        raise IntakeError(f"{label} SHA-256 mismatch: expected {rule.sha256}, found {digest}")
    return {"path": rule.path, "byte_count": size, "sha256": digest}


def _validate_archive(path: Path, python: Path, validate_public_semantics: bool) -> dict[str, object]:
    path = _check_existing_path(path, directory=False, label="extractor archive output")
    size, digest, _ = _hash_file(path, capture=False)
    if size == 0:
        raise IntakeError("extractor archive output is empty")
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not names or archive.testzip() is not None:
                raise IntakeError("extractor archive output is corrupt or empty")
            for name in names:
                if not name.endswith(".npy") or name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    raise IntakeError(f"extractor archive has an unsafe or unexpected member: {name!r}")
                with archive.open(name) as member:
                    if member.read(6) != b"\x93NUMPY":
                        raise IntakeError(f"extractor archive member is not a NumPy array: {name!r}")
    except zipfile.BadZipFile as exc:
        raise IntakeError("extractor archive output is not a valid NPZ/ZIP file") from exc
    if validate_public_semantics:
        validator = r'''import json, numpy as np, sys
with np.load(sys.argv[1], allow_pickle=False) as data:
    names = list(data.files)
    if len(names) != 100:
        raise ValueError(f"expected 100 arrays, found {len(names)}")
    arrays = {name: data[name] for name in names}
    objects = [name for name, value in arrays.items() if value.dtype.hasobject]
    if objects:
        raise ValueError(f"object dtype is forbidden: {objects[0]}")
    required = {
        "pass0_weight_fkyxc": ([16, 2, 2, 8], "float32"),
        "bin_scale_table": ([77], "float32"),
    }
    for name, (shape, dtype) in required.items():
        if name not in arrays:
            raise ValueError(f"missing required array {name}")
        if list(arrays[name].shape) != shape or str(arrays[name].dtype) != dtype:
            raise ValueError(f"{name} expected shape={shape} dtype={dtype}, found shape={list(arrays[name].shape)} dtype={arrays[name].dtype}")
print(json.dumps({"array_count": len(names), "object_dtype_count": 0}, sort_keys=True))
'''
        completed = subprocess.run(
            [os.fspath(python), "-I", "-c", validator, os.fspath(path)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise IntakeError(f"extractor archive semantic validation failed: {detail}")
        try:
            semantic_summary = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise IntakeError("extractor archive semantic validator returned invalid JSON") from exc
    else:
        semantic_summary = None
    result: dict[str, object] = {"byte_count": size, "sha256": digest}
    if semantic_summary is not None:
        result["semantics"] = semantic_summary
    return result


def _validate_spec(path: Path, markers: tuple[tuple[str, str], ...], counts: tuple[tuple[str, int], ...]) -> dict[str, object]:
    path = _check_existing_path(path, directory=False, label="extractor graph spec output")
    size, digest, payload = _hash_file(path, 16 << 20)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntakeError(f"extractor graph spec output is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise IntakeError("extractor graph spec output must be a JSON object")
    for key, expected in markers:
        if value.get(key) != expected:
            raise IntakeError(f"extractor graph spec marker {key!r} must equal {expected!r}")
    for key, expected in counts:
        item = value.get(key)
        if not isinstance(item, (list, dict)) or len(item) != expected:
            found = len(item) if isinstance(item, (list, dict)) else "missing/non-container"
            raise IntakeError(f"extractor graph spec {key!r} count must equal {expected}, found {found}")
    return {
        "byte_count": size,
        "sha256": digest,
        "semantics": {
            "markers": dict(markers),
            "counts": dict(counts),
        },
    }


def run_intake(sdk_root: Path, extractor: Path, python: Path, output: Path, contract: IntakeContract = PUBLIC_CONTRACT) -> dict[str, object]:
    sdk = _check_existing_path(sdk_root, directory=True, label="--sdk-root")
    extractor_path = _check_existing_path(extractor, directory=False, label="--extractor")
    python_path = _check_existing_path(python, directory=False, label="--python")
    destination = _absolute(output)
    if os.path.lexists(destination):
        raise IntakeError(f"--output already exists; refusing to overwrite: {destination}")
    parent = _check_existing_path(destination.parent, directory=True, label="--output parent")
    destination = parent / destination.name

    input_receipts = []
    selected_inputs: list[tuple[Path, FileRule]] = []
    for rule in contract.inputs:
        selected = _selected_file(sdk, rule.path, rule.path)
        input_receipts.append(_verify_rule(selected, rule, rule.path))
        selected_inputs.append((selected, rule))
    extractor_receipt = _verify_rule(extractor_path, contract.extractor, "extractor")

    with tempfile.TemporaryDirectory(prefix="fsr-intake-") as temporary:
        temp = Path(temporary)
        isolated_sdk = temp / "sdk"
        isolated_script = temp / "model" / "extract" / "build_weights.py"
        isolated_script.parent.mkdir(parents=True)
        for source, rule in selected_inputs:
            copied = isolated_sdk.joinpath(*rule.path.split("/"))
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copied)
            _verify_rule(copied, rule, f"isolated copy of {rule.path}")
        shutil.copyfile(extractor_path, isolated_script)
        _verify_rule(isolated_script, contract.extractor, "isolated extractor copy")

        environment = os.environ.copy()
        environment["FIDELITYFX_SDK_ROOT"] = os.fspath(isolated_sdk)
        try:
            completed = subprocess.run(
                [os.fspath(python_path), "-I", os.fspath(isolated_script)],
                cwd=isolated_script.parent,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IntakeError(f"extractor could not complete: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise IntakeError(f"extractor failed with exit code {completed.returncode}: {detail}")

        artifacts = isolated_script.parents[1] / "artifacts"
        archive_path = artifacts / contract.archive_name
        spec_path = artifacts / contract.spec_name
        archive_receipt = _validate_archive(archive_path, python_path, contract.validate_public_archive)
        spec_receipt = _validate_spec(spec_path, contract.spec_markers, contract.spec_counts)
        outputs = {
            contract.archive_name: archive_receipt,
            contract.spec_name: spec_receipt,
        }
        receipt = {
            "schema_version": "p7-fsr-intake-receipt-v1",
            "source": {"url": contract.source_url, "commit": contract.source_commit},
            "extractor": {
                "url": contract.extractor_url,
                "commit": contract.extractor_commit,
                "byte_count": extractor_receipt["byte_count"],
                "sha256": extractor_receipt["sha256"],
            },
            "inputs": input_receipts,
            "outputs": outputs,
            "extraction_gate": "passed",
            "device_execution": "not_run",
        }
        receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")

        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=parent))
        try:
            for source, name in ((archive_path, contract.archive_name), (spec_path, contract.spec_name)):
                with source.open("rb") as reader, (staging / name).open("xb") as writer:
                    shutil.copyfileobj(reader, writer, CHUNK)
                copied_size, copied_hash, _ = _hash_file(staging / name, capture=False)
                if copied_size != outputs[name]["byte_count"] or copied_hash != outputs[name]["sha256"]:
                    raise IntakeError(f"published staging copy changed for {name}")
            with (staging / RECEIPT_NAME).open("xb") as stream:
                stream.write(receipt_bytes)
            if os.path.lexists(destination):
                raise IntakeError(f"--output appeared during extraction; refusing to overwrite: {destination}")
            try:
                staging.rename(destination)
            except OSError as exc:
                if os.path.lexists(destination):
                    raise IntakeError(f"--output appeared during extraction; refusing to overwrite: {destination}") from exc
                raise IntakeError(f"could not publish output directory atomically: {exc}") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--extractor", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = run_intake(args.sdk_root, args.extractor, args.python, args.output)
    except IntakeError as exc:
        print(f"intake failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

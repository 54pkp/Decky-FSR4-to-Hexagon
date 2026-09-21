#!/usr/bin/env python3
"""Build a deterministic ABI inventory from the one pinned QAIRT archive."""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Sequence
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.abi import inspector


SCHEMA_VERSION = "qairt-abi-inventory-v1"
MAX_SELECTED_BYTES = inspector.MAX_FILE_BYTES
SCOPE = "selected_allowlist_from_one_pinned_qairt_archive"
DISCLAIMER = (
    "Offline structural inventory of a selected allowlist only; this is not a full SDK "
    "inventory and does not prove device compatibility, loading, QNN/HTP execution, "
    "FSR4 behavior, or game behavior."
)


class InventoryError(Exception):
    """The archive, profile, output, or selected binary was not trustworthy."""


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    status: str
    size: int | None = None
    sha256: str | None = None
    file_format: str | None = None
    machine: str | None = None
    candidate: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Profile:
    name: str
    source_url: str
    archive_name: str
    archive_root: str
    archive_size: int
    archive_sha256: str
    sdk_version: str
    build_id: str
    entries: tuple[Entry, ...]


DEFAULT_ENTRIES = (
    Entry("windows-system", "lib/x86_64-windows-msvc/QnnSystem.dll", "present", 3452624, "53b4a57a2371e4d5d693ebc6e505a71393b501c92fe763408c0e25af10afc474", "PE", "x86_64", "windows_pe"),
    Entry("windows-cpu", "lib/x86_64-windows-msvc/QnnCpu.dll", "present", 4997840, "b2963ff19a4a3002afc597ac5f047eac18a6f03e7b8f81bf512458e0980cc62b", "PE", "x86_64", "windows_pe"),
    Entry("windows-htp-net-run-extensions", "lib/x86_64-windows-msvc/QnnHtpNetRunExtensions.dll", "present", 962768, "5f344d998e4365f6c69a66ea19aedc46e386f78fa699bc49438adcbce7542bed", "PE", "x86_64", "windows_pe"),
    Entry("android-htp", "lib/aarch64-android/libQnnHtp.so", "present", 3786064, "a09b3af28342331b3ec9e57ecbe42bfe54a5fff37c4323ce5685c395ae3ee604", "ELF", "arm64", "android_candidate"),
    Entry("android-system", "lib/aarch64-android/libQnnSystem.so", "present", 4072160, "536201ed918f4066f9ef35671198c072faf9ef04af24545f5fae0fc79aa05baa", "ELF", "arm64", "android_candidate"),
    Entry("android-v79-stub", "lib/aarch64-android/libQnnHtpV79Stub.so", "present", 771928, "2f61eb5be87b72878e7c2f66ec1967ce34abaa4e6ff25eadcef9212b958cbcbb", "ELF", "arm64", "android_candidate"),
    Entry("oe-gcc11-htp", "lib/aarch64-oe-linux-gcc11.2/libQnnHtp.so", "present", 4529864, "21308e37622698f5cce4de08a8d0c3d31c041ebf57f3d75096de7dcdac07cfc2", "ELF", "arm64", "linux_glibc_candidate"),
    Entry("oe-gcc11-system", "lib/aarch64-oe-linux-gcc11.2/libQnnSystem.so", "present", 5603560, "897891daf65c43e07265d818e52bb2c4c0e087a360699fb1b26525804de9acc9", "ELF", "arm64", "linux_glibc_candidate"),
    Entry("oe-gcc11-v79-stub", "lib/aarch64-oe-linux-gcc11.2/libQnnHtpV79Stub.so", "present", 501832, "fc450ff06c8dec00294909e25b028a71ead0e48352e500ef86adaea28bb725f8", "ELF", "arm64", "linux_glibc_candidate"),
    Entry("hexagon-v79-skel", "lib/hexagon-v79/unsigned/libQnnHtpV79Skel.so", "present", 12038356, "a2e4f67567a6484b20de557809dd5c1f6dfe9af658a820cd351bcfa7a6b26777", "ELF", "hexagon", "unknown_elf"),
    Entry("oe-gcc9-v79-stub", "lib/aarch64-oe-linux-gcc9.3/libQnnHtpV79Stub.so", "missing"),
    Entry("ubuntu-gcc9-v79-stub", "lib/aarch64-ubuntu-gcc9.4/libQnnHtpV79Stub.so", "missing"),
    Entry(
        "oe-gcc11-cdsprpc",
        "lib/aarch64-oe-linux-gcc11.2/libcdsprpc.so",
        "missing",
        note=(
            "This dependency may be supplied by a BSP, FastRPC package, or device image; "
            "device availability is unknown."
        ),
    ),
)

DEFAULT_PROFILE = Profile(
    "QAIRT-2.49.0.260730-abi",
    "https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/2.49.0.260730/v2.49.0.260730.zip",
    "qairt-community-2.49.0.260730.zip",
    "qairt/2.49.0.260730",
    2414977444,
    "32de9b5b2b069aeb93ba090071e777ff464349b3296358c4d3b35040dccbd159",
    "2.49.0",
    "260730134355",
    DEFAULT_ENTRIES,
)


def _is_reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _directory_chain(path: Path) -> list[Path]:
    selected = Path(os.path.abspath(os.fspath(path)))
    chain = list(reversed((selected, *selected.parents)))
    for item in chain:
        try:
            value = item.stat(follow_symlinks=False)
        except OSError as exc:
            raise InventoryError(f"cannot inspect output ancestor {item}: {exc}") from exc
        if _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise InventoryError(f"output ancestor must be a non-reparse directory: {item}")
    return chain


class _DirectoryGuard(AbstractContextManager["_DirectoryGuard"]):
    """Keep every output ancestor stable through exclusive publication."""

    def __init__(self, target: Path):
        self.paths = _directory_chain(target)
        self.entries: list[tuple[Path, Any, tuple[int, int]]] = []

    def __enter__(self) -> "_DirectoryGuard":
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create = kernel32.CreateFileW
            create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
            create.restype = ctypes.c_void_p
            for path in self.paths:
                handle = create(str(path), 0x80, 0x1 | 0x2, None, 3, 0x02000000, None)
                if handle == ctypes.c_void_p(-1).value:
                    self.__exit__(None, None, None)
                    raise InventoryError(f"cannot lock output directory against replacement: {path} (winerror {ctypes.get_last_error()})")
                value = path.stat(follow_symlinks=False)
                self.entries.append((path, handle, (value.st_dev, value.st_ino)))
        else:
            for path in self.paths:
                descriptor = os.open(path, os.O_RDONLY)
                value = os.fstat(descriptor)
                self.entries.append((path, descriptor, (value.st_dev, value.st_ino)))
        return self

    def verify(self) -> None:
        for path, _handle, identity in self.entries:
            try:
                value = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise InventoryError(f"locked output directory disappeared: {path}") from exc
            if _is_reparse(value) or (value.st_dev, value.st_ino) != identity:
                raise InventoryError(f"locked output directory identity changed: {path}")

    def __exit__(self, *_args: object) -> None:
        if os.name == "nt":
            close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
            for _path, handle, _identity in reversed(self.entries):
                close(handle)
        else:
            for _path, descriptor, _identity in reversed(self.entries):
                os.close(descriptor)
        self.entries.clear()


def _zip_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\0" in name or re.match(r"^[A-Za-z]:", name):
        raise InventoryError(f"unsafe ZIP member path: {name!r}")
    trimmed = name.rstrip("/")
    raw_parts = trimmed.split("/")
    path = PurePosixPath(trimmed)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in raw_parts):
        raise InventoryError(f"unsafe ZIP member path: {name!r}")
    return path


def _validate_profile(profile: Profile) -> None:
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for entry in profile.entries:
        logical = str(_zip_path(entry.path))
        if entry.name in seen_names or logical.casefold() in seen_paths:
            raise InventoryError("profile entry names and paths must be unique")
        seen_names.add(entry.name)
        seen_paths.add(logical.casefold())
        if entry.status not in ("present", "missing"):
            raise InventoryError(f"invalid profile status for {entry.name}")
        values = (entry.size, entry.sha256, entry.file_format, entry.machine, entry.candidate)
        if entry.status == "present":
            if any(value is None for value in values):
                raise InventoryError(f"present profile entry is incomplete: {entry.name}")
            if not 0 < int(entry.size or 0) <= MAX_SELECTED_BYTES:
                raise InventoryError(f"selected profile entry size is unsafe: {entry.name}")
        elif any(value is not None for value in values):
            raise InventoryError(f"missing profile entry must not declare ABI or digest: {entry.name}")


def _regular_archive(path: Path) -> tuple[Path, os.stat_result]:
    selected = Path(os.path.abspath(os.fspath(path)))
    try:
        value = selected.stat(follow_symlinks=False)
    except OSError as exc:
        raise InventoryError(f"cannot inspect archive: {exc}") from exc
    reparse = bool(getattr(value, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if stat.S_ISLNK(value.st_mode) or reparse or not stat.S_ISREG(value.st_mode):
        raise InventoryError("archive must be a regular non-reparse file")
    return selected, value


def _read_selected(source: Any, expected_size: int, label: str) -> tuple[bytes, str]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = source.read(min(1 << 20, expected_size - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > expected_size:
            raise InventoryError(f"selected ZIP member exceeds pinned size: {label}")
        digest.update(chunk)
        chunks.append(chunk)
    if total != expected_size:
        raise InventoryError(f"selected ZIP member size mismatch: {label}")
    return b"".join(chunks), digest.hexdigest()


def _build(archive: Path, profile: Profile) -> dict[str, Any]:
    _validate_profile(profile)
    selected, before = _regular_archive(archive)
    if before.st_size != profile.archive_size:
        raise InventoryError(f"archive size mismatch: expected {profile.archive_size}, found {before.st_size}")
    present = {entry.path: entry for entry in profile.entries if entry.status == "present"}
    expected_names = {f"{profile.archive_root.rstrip('/')}/{path}": entry for path, entry in present.items()}
    all_expected = {f"{profile.archive_root.rstrip('/')}/{entry.path}": entry for entry in profile.entries}
    reports: dict[str, dict[str, Any]] = {}
    archive_digest = hashlib.sha256()
    try:
        with selected.open("rb") as stream, tempfile.TemporaryDirectory(prefix="qairt-abi-inventory-") as temp:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise InventoryError("archive changed before reading")
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                archive_digest.update(chunk)
            archive_hash = archive_digest.hexdigest()
            if archive_hash != profile.archive_sha256:
                raise InventoryError("archive SHA-256 mismatch")
            stream.seek(0)
            with zipfile.ZipFile(stream) as package:
                seen: set[str] = set()
                selected_infos: dict[str, zipfile.ZipInfo] = {}
                archive_names: set[str] = set()
                for member in package.infolist():
                    logical = str(_zip_path(member.filename))
                    folded = logical.casefold()
                    if folded in seen:
                        raise InventoryError(f"duplicate ZIP member path: {member.filename}")
                    seen.add(folded)
                    unix_mode = (member.external_attr >> 16) & 0xFFFF
                    windows_attrs = member.external_attr & 0xFFFF
                    if stat.S_ISLNK(unix_mode) or windows_attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                        raise InventoryError(f"ZIP member is a symlink or reparse point: {member.filename}")
                    if member.is_dir():
                        continue
                    archive_names.add(logical)
                    if logical in expected_names:
                        selected_infos[logical] = member

                for full_name, entry in all_expected.items():
                    exists = full_name in archive_names
                    if entry.status == "present" and not exists:
                        raise InventoryError(f"archive is missing pinned member: {entry.path}")
                    if entry.status == "missing" and exists:
                        raise InventoryError(f"profile marks an existing member missing: {entry.path}")

                snapshot_root = Path(temp)
                for full_name, entry in expected_names.items():
                    member = selected_infos[full_name]
                    assert entry.size is not None and entry.sha256 is not None
                    if member.file_size != entry.size:
                        raise InventoryError(f"selected ZIP member size mismatch: {entry.path}")
                    with package.open(member) as source:
                        payload, digest = _read_selected(source, entry.size, entry.path)
                    if digest != entry.sha256:
                        raise InventoryError(f"selected ZIP member SHA-256 mismatch: {entry.path}")
                    snapshot = snapshot_root / f"item-{len(reports):03d}"
                    with snapshot.open("xb") as target:
                        target.write(payload)
                    try:
                        report = inspector.inspect_file(snapshot, profile.sdk_version, entry.machine)
                    except inspector.AbiError as exc:
                        raise InventoryError(f"ABI inspection failed for {entry.path}: {exc}") from exc
                    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != digest:
                        raise InventoryError(f"private snapshot changed during inspection: {entry.path}")
                    actual = (report["format"], report["machine"], report["candidate"])
                    expected = (entry.file_format, entry.machine, entry.candidate)
                    if actual != expected:
                        raise InventoryError(f"ABI expectation mismatch for {entry.path}: expected {expected}, found {actual}")
                    report["file"] = entry.path
                    reports[entry.path] = report
            final = os.fstat(stream.fileno())
    except InventoryError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise InventoryError(f"cannot validate pinned archive: {exc}") from exc
    if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns):
        raise InventoryError("archive changed while validating")

    items: list[dict[str, Any]] = []
    for entry in profile.entries:
        item: dict[str, Any] = {"name": entry.name, "path": entry.path, "status": entry.status}
        if entry.status == "present":
            item.update({"bytes": entry.size, "sha256": entry.sha256, "inspection": reports[entry.path]})
        else:
            item.update(
                {
                    "scope": "pinned_archive_only",
                    "reason": "not_present_in_pinned_archive",
                }
            )
            if entry.note is not None:
                item["note"] = entry.note
        items.append(item)
    present_count = sum(entry.status == "present" for entry in profile.entries)
    missing_count = len(profile.entries) - present_count
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile.name,
        "source": {
            "source_url": profile.source_url,
            "sdk_version": profile.sdk_version,
            "build_id": profile.build_id,
        },
        "archive": {"archive_name": profile.archive_name, "archive_root": profile.archive_root, "bytes": profile.archive_size, "sha256": archive_hash},
        "summary": {"present": present_count, "missing": missing_count},
        "entries": items,
        "structural_inventory_exclusions": [
            {
                "path": "lib/x86_64-windows-msvc/QnnHtp.dll",
                "status": "not_run",
                "reason": "file exceeds the 16 MiB inspector safety limit",
            },
            {
                "path": "lib/aarch64-android/libQnnHtpPrepare.so",
                "status": "not_run",
                "reason": "file exceeds the 16 MiB inspector safety limit",
            },
            {
                "path": "lib/aarch64-oe-linux-gcc11.2/libQnnHtpPrepare.so",
                "status": "not_run",
                "reason": "file exceeds the 16 MiB inspector safety limit",
            },
        ],
        "scope": SCOPE,
        "disclaimer": DISCLAIMER,
        "device_match": "unknown",
        "execution": "not_run",
    }


def inventory(archive: Path, output: Path, profile: Profile = DEFAULT_PROFILE) -> dict[str, Any]:
    """Validate *archive* and atomically publish its bounded ABI inventory."""
    output = Path(os.path.abspath(os.fspath(output)))
    if os.path.lexists(output):
        raise InventoryError(f"output already exists; refusing to overwrite: {output}")
    parent = output.parent
    with _DirectoryGuard(parent) as guard:
        handle, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=parent)
        try:
            reserved_before = os.fstat(handle)
            report = _build(archive, profile)
            payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
            guard.verify()
            try:
                reserved_now = Path(temporary).stat(follow_symlinks=False)
            except OSError as exc:
                raise InventoryError("reserved output file disappeared during inventory") from exc
            if _is_reparse(reserved_now) or (
                reserved_now.st_dev,
                reserved_now.st_ino,
            ) != (reserved_before.st_dev, reserved_before.st_ino):
                raise InventoryError("reserved output file identity changed during inventory")
            with os.fdopen(os.dup(handle), "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            guard.verify()
            try:
                os.link(temporary, output)
            except FileExistsError as exc:
                raise InventoryError("output appeared during inventory; refusing to overwrite") from exc
            guard.verify()
        except Exception:
            guard.verify()
            raise
        finally:
            os.close(handle)
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(
    argv: Sequence[str] | None = None, profile: Profile = DEFAULT_PROFILE
) -> int:
    args = _parser().parse_args(argv)
    try:
        report = inventory(args.archive, args.output, profile)
    except (InventoryError, OSError) as exc:
        print(f"ABI inventory failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"profile": report["profile"], "output": "written"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

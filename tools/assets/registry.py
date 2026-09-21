#!/usr/bin/env python3
"""Validate an external-asset registry against one explicitly selected root.

This is a read-only file-integrity check.  It does not load or execute models,
SDKs, HTP code, or device code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Sequence
from urllib.parse import urlsplit


SCHEMA_VERSION = "external-asset-registry-v1"
MAX_REGISTRY_BYTES = 1 << 20
MAX_FILE_BYTES = 64 << 20
MAX_TOTAL_FILE_BYTES = 256 << 20
MAX_FILE_COUNT = 256
MAX_JSON_INTEGER_DIGITS = 1_000
MAX_JSON_DEPTH = 32
HASH_CHUNK_BYTES = 1 << 20

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "component",
        "source_url",
        "version_or_commit",
        "platform",
        "architecture",
        "purpose",
        "notice",
        "files",
    }
)
_NOTICE_FIELDS = frozenset({"status", "path"})
_FILE_FIELDS = frozenset(
    {
        "logical_name",
        "path",
        "status",
        "sha256",
        "byte_count",
        "purpose",
        "missing_reason",
    }
)
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class RegistryInvalid(Exception):
    """The registry contract or a claimed asset does not match reality."""


class RegistryInputError(Exception):
    """The explicitly selected root or registry could not be safely read."""


def _fail(path: str, message: str) -> None:
    raise RegistryInvalid(f"{path}: {message}")


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


def _string(value: Any, path: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(path, "must be a non-empty string")
    if len(value) > limit:
        _fail(path, f"must contain at most {limit} characters")
    if any(ord(character) < 0x20 for character in value):
        _fail(path, "must not contain control characters")
    return value


def _optional_null(value: Any, path: str) -> None:
    if value is not None:
        _fail(path, "must be null")


def _logical_path(value: Any, path: str) -> str:
    text = _string(value, path, 1024)
    if "\\" in text:
        _fail(path, "must use forward slashes, not backslashes")
    logical = PurePosixPath(text)
    parts = text.split("/")
    if logical.is_absolute() or text.startswith("/"):
        _fail(path, "must be relative")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        _fail(path, "must not contain empty, '.' or '..' segments")
    for part in parts:
        if any(character in _WINDOWS_FORBIDDEN or ord(character) < 0x20 for character in part):
            _fail(path, "contains a character unsafe for a Windows relative path")
        if part.endswith((" ", ".")):
            _fail(path, "contains a segment ending in a space or dot")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            _fail(path, f"contains reserved Windows path segment {part!r}")
    return text


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _file_identity(stat_result: os.stat_result) -> tuple[int, int]:
    return stat_result.st_dev, stat_result.st_ino


def _safe_root(root: Path) -> tuple[Path, tuple[int, int]]:
    selected = Path(os.path.abspath(os.fspath(root)))
    try:
        root_stat = selected.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise RegistryInputError(f"root does not exist: {selected}") from exc
    except OSError as exc:
        raise RegistryInputError(f"cannot inspect root {selected}: {exc}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or _is_reparse(root_stat):
        raise RegistryInputError(f"root must not be a symlink or junction: {selected}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise RegistryInputError(f"root is not a directory: {selected}")
    try:
        resolved = selected.resolve(strict=True)
        resolved_stat = resolved.stat(follow_symlinks=False)
        if not stat.S_ISDIR(resolved_stat.st_mode):
            raise RegistryInputError(f"resolved root is not a directory: {resolved}")
        return resolved, _file_identity(resolved_stat)
    except OSError as exc:
        raise RegistryInputError(f"cannot resolve root {selected}: {exc}") from exc


def _candidate(root: Path, logical_path: str, label: str) -> Path:
    candidate = root.joinpath(*logical_path.split("/"))
    current = root
    try:
        for part in logical_path.split("/"):
            current = current / part
            current_stat = current.stat(follow_symlinks=False)
            if stat.S_ISLNK(current_stat.st_mode) or _is_reparse(current_stat):
                raise RegistryInvalid(f"{label}: symlink or junction is not allowed: {logical_path}")
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        return candidate
    except RegistryInvalid:
        raise
    except OSError as exc:
        raise RegistryInputError(f"cannot inspect {label} {logical_path!r}: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RegistryInvalid(f"{label}: path escapes the selected root: {logical_path}") from exc
    return resolved


def _opened_final_path(stream: Any, selected: Path) -> Path:
    """Return the path resolved by an already-open file handle."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        get_final_path = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        get_final_path.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        get_final_path.restype = wintypes.DWORD
        handle = msvcrt.get_osfhandle(stream.fileno())
        capacity = 32_768
        buffer = ctypes.create_unicode_buffer(capacity)
        length = get_final_path(handle, buffer, capacity, 0)
        if length == 0:
            error = ctypes.get_last_error()
            raise OSError(error, "GetFinalPathNameByHandleW failed")
        if length >= capacity:
            raise OSError("opened file path exceeds Windows API buffer")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{stream.fileno()}"))
    return selected.resolve(strict=True)


def _verify_opened_root(
    stream: Any,
    root_identity: tuple[int, int],
    logical_path: str,
    selected: Path,
    label: str,
) -> None:
    """Bind a file opened through a possibly changing path back to *root*."""
    try:
        final_path = _opened_final_path(stream, selected)
        opened_root = final_path
        for _part in logical_path.split("/"):
            opened_root = opened_root.parent
        opened_root_stat = opened_root.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened_root_stat.st_mode)
            or _file_identity(opened_root_stat) != root_identity
        ):
            raise RegistryInvalid(
                f"{label}: opened file resolves outside the selected root: {logical_path}"
            )
    except RegistryInvalid:
        raise
    except OSError as exc:
        raise RegistryInputError(
            f"cannot bind opened {label} {logical_path!r} to the selected root: {exc}"
        ) from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryInputError(f"registry contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> None:
    raise RegistryInputError(f"registry contains non-finite JSON number {value}")


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise RegistryInputError(
            f"registry integer exceeds digit limit {MAX_JSON_INTEGER_DIGITS}"
        )
    return int(value)


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RegistryInputError(f"registry contains non-finite JSON number {value}")
    return number


def _check_depth(value: Any) -> None:
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise RegistryInputError(
                f"registry JSON nesting exceeds limit {MAX_JSON_DEPTH}"
            )
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _read_registry(
    root: Path, root_identity: tuple[int, int], registry_path: str
) -> Any:
    logical = _logical_path(registry_path, "--registry")
    selected = _candidate(root, logical, "registry")
    if not selected.exists():
        raise RegistryInputError(f"registry does not exist under selected root: {logical}")
    try:
        before = selected.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise RegistryInputError(f"registry is not a regular file: {logical}")
        if before.st_size > MAX_REGISTRY_BYTES:
            raise RegistryInputError(
                f"registry exceeds input limit {MAX_REGISTRY_BYTES} bytes: {logical}"
            )
        with selected.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise RegistryInputError(f"registry changed before it could be read: {logical}")
            _verify_opened_root(stream, root_identity, logical, selected, "registry")
            payload = stream.read(MAX_REGISTRY_BYTES + 1)
        if len(payload) > MAX_REGISTRY_BYTES:
            raise RegistryInputError(
                f"registry exceeds input limit {MAX_REGISTRY_BYTES} bytes: {logical}"
            )
        text = payload.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_number,
            parse_int=_parse_bounded_integer,
            parse_float=_parse_finite_float,
        )
        _check_depth(value)
        return value
    except RegistryInputError:
        raise
    except UnicodeDecodeError as exc:
        raise RegistryInputError(f"registry is not UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryInputError(
            f"registry is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except RecursionError as exc:
        raise RegistryInputError("registry JSON nesting exceeds parser limit") from exc
    except ValueError as exc:
        raise RegistryInputError(f"registry contains an unsupported JSON value: {exc}") from exc
    except OSError as exc:
        raise RegistryInputError(f"cannot read registry {logical!r}: {exc}") from exc


def _validate_contract(value: Any) -> dict[str, Any]:
    registry = _object(value, "$", _ROOT_FIELDS)
    if registry["schema_version"] != SCHEMA_VERSION:
        _fail("$.schema_version", f"must equal {SCHEMA_VERSION!r}")
    _string(registry["component"], "$.component")
    source_url = _string(registry["source_url"], "$.source_url", 2048)
    if any(character.isspace() for character in source_url):
        _fail("$.source_url", "must not contain whitespace")
    try:
        parsed_url = urlsplit(source_url)
    except ValueError as exc:
        _fail("$.source_url", f"is not a valid URL: {exc}")
    if parsed_url.scheme not in {"https", "http"} or not parsed_url.netloc:
        _fail("$.source_url", "must be an absolute HTTP or HTTPS URL")
    if parsed_url.username is not None or parsed_url.password is not None:
        _fail("$.source_url", "must not contain credentials")
    _string(registry["version_or_commit"], "$.version_or_commit")
    _string(registry["platform"], "$.platform")
    _string(registry["architecture"], "$.architecture")
    _string(registry["purpose"], "$.purpose", 1024)

    notice = _object(registry["notice"], "$.notice", _NOTICE_FIELDS)
    notice_status = notice["status"]
    if not isinstance(notice_status, str) or notice_status not in {"present", "unknown"}:
        _fail("$.notice.status", "must equal 'present' or 'unknown'")
    notice_path = None
    if notice_status == "present":
        notice_path = _logical_path(notice["path"], "$.notice.path")
    else:
        _optional_null(notice["path"], "$.notice.path")

    files = registry["files"]
    if not isinstance(files, list):
        _fail("$.files", "must be an array")
    if not files:
        _fail("$.files", "must contain at least one file record")
    if len(files) > MAX_FILE_COUNT:
        _fail("$.files", f"file count exceeds limit {MAX_FILE_COUNT}")

    logical_names: set[str] = set()
    paths: set[str] = set()
    total_present_bytes = 0
    normalised: list[dict[str, Any]] = []
    for index, raw_file in enumerate(files):
        base = f"$.files[{index}]"
        item = _object(raw_file, base, _FILE_FIELDS)
        logical_name = _string(item["logical_name"], f"{base}.logical_name")
        logical_path = _logical_path(item["path"], f"{base}.path")
        folded_name = logical_name.casefold()
        folded_path = logical_path.casefold()
        if folded_name in logical_names:
            _fail(f"{base}.logical_name", f"duplicate logical name {logical_name!r}")
        if folded_path in paths:
            _fail(f"{base}.path", f"duplicate path {logical_path!r}")
        logical_names.add(folded_name)
        paths.add(folded_path)
        _string(item["purpose"], f"{base}.purpose", 1024)
        status_value = item["status"]
        if not isinstance(status_value, str) or status_value not in {"present", "missing"}:
            _fail(f"{base}.status", "must equal 'present' or 'missing'")
        if status_value == "present":
            digest = item["sha256"]
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                _fail(f"{base}.sha256", "must be 64 lowercase hexadecimal characters")
            byte_count = item["byte_count"]
            if isinstance(byte_count, bool) or not isinstance(byte_count, int):
                _fail(f"{base}.byte_count", "must be an integer, not a boolean")
            if byte_count < 0 or byte_count > MAX_FILE_BYTES:
                _fail(f"{base}.byte_count", f"must be between 0 and {MAX_FILE_BYTES}")
            total_present_bytes += byte_count
            if total_present_bytes > MAX_TOTAL_FILE_BYTES:
                _fail(
                    "$.files",
                    f"declared present bytes exceed total limit {MAX_TOTAL_FILE_BYTES}",
                )
            _optional_null(item["missing_reason"], f"{base}.missing_reason")
        else:
            _optional_null(item["sha256"], f"{base}.sha256")
            _optional_null(item["byte_count"], f"{base}.byte_count")
            _string(item["missing_reason"], f"{base}.missing_reason", 1024)
        normalised.append(item)

    if notice_path is not None:
        matching = [item for item in normalised if item["path"] == notice_path]
        if not matching or matching[0]["status"] != "present":
            _fail("$.notice.path", "must reference a file record whose status is 'present'")
    return registry


def _verify_file(
    root: Path, root_identity: tuple[int, int], item: dict[str, Any], index: int
) -> None:
    label = f"$.files[{index}].path"
    selected = _candidate(root, item["path"], label)
    exists = selected.exists()
    if item["status"] == "missing":
        if exists:
            _fail(label, "is registered as missing but exists")
        return
    if not exists:
        _fail(label, "is registered as present but does not exist")
    try:
        before = selected.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            _fail(label, "must identify a regular file")
        if before.st_size > MAX_FILE_BYTES:
            _fail(label, f"file exceeds size limit {MAX_FILE_BYTES} bytes")
        if before.st_size != item["byte_count"]:
            _fail(
                f"$.files[{index}].byte_count",
                f"expected {item['byte_count']}, found {before.st_size}",
            )
        digest = hashlib.sha256()
        total = 0
        with selected.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                _fail(label, "file changed before it could be read")
            _verify_opened_root(
                stream, root_identity, item["path"], selected, label
            )
            while True:
                chunk = stream.read(min(HASH_CHUNK_BYTES, MAX_FILE_BYTES + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    _fail(label, f"file exceeds size limit {MAX_FILE_BYTES} bytes")
                digest.update(chunk)
        after = selected.stat(follow_symlinks=False)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            _fail(label, "file changed while it was being read")
        actual_digest = digest.hexdigest()
        if actual_digest != item["sha256"]:
            _fail(
                f"$.files[{index}].sha256",
                f"expected {item['sha256']}, found {actual_digest}",
            )
    except RegistryInvalid:
        raise
    except OSError as exc:
        raise RegistryInputError(f"cannot read registered file {item['path']!r}: {exc}") from exc


def verify(root: Path, registry_path: str) -> dict[str, Any]:
    """Validate registry metadata and compare all file claims with *root*."""
    safe_root, root_identity = _safe_root(root)
    registry = _validate_contract(
        _read_registry(safe_root, root_identity, registry_path)
    )
    for index, item in enumerate(registry["files"]):
        _verify_file(safe_root, root_identity, item, index)
    return {
        "component": registry["component"],
        "files": {
            "present": sum(item["status"] == "present" for item in registry["files"]),
            "missing": sum(item["status"] == "missing" for item in registry["files"]),
        },
        "metadata_verified": True,
        "execution_gate": "not_run",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="verify one asset registry")
    verify_parser.add_argument("--root", required=True, type=Path)
    verify_parser.add_argument(
        "--registry",
        required=True,
        help="forward-slash relative path to the registry inside --root",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = verify(args.root, args.registry)
    except RegistryInvalid as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    except RegistryInputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

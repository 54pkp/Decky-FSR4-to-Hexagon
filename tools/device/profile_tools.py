#!/usr/bin/env python3
"""Offline validation and public redaction for M0 device profiles."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from importlib import metadata
from typing import Any, Iterable


REQUIRED_JSONSCHEMA_VERSION = "4.26.0"
DEFAULT_SCHEMA = Path(__file__).resolve().parent / "schema" / "device-profile.schema.json"
PLACEHOLDER = {
    "user": "[REDACTED:user]",
    "host": "[REDACTED:host]",
    "path": "[REDACTED:path]",
    "serial": "[REDACTED:serial]",
}


class ProfileInvalid(Exception):
    """The profile or selected schema is invalid."""


class InputError(Exception):
    """The CLI input is unusable or would overwrite data."""


class FatalError(Exception):
    """An I/O or dependency error prevents a trustworthy result."""


def _jsonschema_api():
    try:
        version = metadata.version("jsonschema")
    except metadata.PackageNotFoundError as exc:
        raise FatalError(
            f"required dependency jsonschema=={REQUIRED_JSONSCHEMA_VERSION} is not installed"
        ) from exc
    if version != REQUIRED_JSONSCHEMA_VERSION:
        raise FatalError(
            f"incompatible jsonschema version {version}; required {REQUIRED_JSONSCHEMA_VERSION}"
        )
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise FatalError("jsonschema 4.26.0 does not expose the required validator API") from exc
    return Draft202012Validator, FormatChecker


def _load_json(path: Path, *, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise InputError(f"{label} does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise InputError(f"{label} is not a file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ProfileInvalid(f"{label} is not UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileInvalid(f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise FatalError(f"cannot read {label} {path}: {exc}") from exc


def _field_path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(part)):
            result += f".{part}"
        else:
            result += f"[{json.dumps(str(part))}]"
    return result


def _format_validation_error(error: Any) -> str:
    path = tuple(error.absolute_path)
    if error.validator == "required" and isinstance(error.instance, dict):
        match = re.match(r"^'([^']+)' is a required property$", error.message)
        if match:
            path += (match.group(1),)
    elif error.validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = set(error.schema.get("properties", {}))
        extras = sorted(set(error.instance) - allowed)
        if extras:
            path += (extras[0],)
    return f"{_field_path(path)}: {error.message}"


def _safe_relative_path(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    if any(part in ("", ".", "..") for part in value.split("/")):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute()


def _opened_final_path(stream: Any, selected: Path) -> Path:
    """Return the filesystem path bound to an already-open evidence handle."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        get_final_path = ctypes.WinDLL(
            "kernel32", use_last_error=True
        ).GetFinalPathNameByHandleW
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
            raise OSError(
                ctypes.get_last_error(), "GetFinalPathNameByHandleW failed"
            )
        if length >= capacity:
            raise OSError("opened evidence path exceeds Windows API buffer")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    if sys.platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{stream.fileno()}"))
    raise OSError(
        f"safe opened-evidence path binding is unsupported on {sys.platform}"
    )


def _evidence_candidate(profile_directory: Path, relative: str) -> Path:
    candidate = profile_directory.joinpath(*PurePosixPath(relative).parts)
    resolved = candidate.resolve(strict=True)
    if resolved != profile_directory and profile_directory not in resolved.parents:
        raise ProfileInvalid(
            f"resolved evidence path escapes profile directory: {relative}"
        )
    return resolved


def _read_bound_evidence(
    profile_directory: Path,
    profile_directory_identity: tuple[int, int],
    relative: str,
) -> bytes:
    selected = _evidence_candidate(profile_directory, relative)
    with selected.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ProfileInvalid(f"evidence path is not a regular file: {relative}")
        final_path = _opened_final_path(stream, selected)
        inside_initial_root = False
        for ancestor in (final_path.parent, *final_path.parent.parents):
            ancestor_stat = ancestor.stat(follow_symlinks=False)
            if (
                stat.S_ISDIR(ancestor_stat.st_mode)
                and (ancestor_stat.st_dev, ancestor_stat.st_ino)
                == profile_directory_identity
            ):
                inside_initial_root = True
                break
        if not inside_initial_root:
            raise ProfileInvalid(
                f"opened evidence resolves outside the profile directory: {relative}"
            )
        return stream.read()


def _iter_observations(profile: dict[str, Any]):
    for section_name in (
        "identity", "hardware", "os", "graphics", "npu", "runtime_stack"
    ):
        section = profile.get(section_name, {})
        if isinstance(section, dict):
            for observation_name, observation in section.items():
                yield (section_name, observation_name), observation
    candidates = profile.get("game_candidates", [])
    if isinstance(candidates, list):
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            for observation_name in ("name", "executable"):
                if observation_name in candidate:
                    yield (
                        "game_candidates", index, observation_name
                    ), candidate[observation_name]


def _semantic_errors(profile: dict[str, Any], profile_path: Path, *, verify_files: bool) -> list[str]:
    errors: list[str] = []
    profile_directory = profile_path.parent.resolve()
    profile_directory_identity: tuple[int, int] | None = None
    if verify_files:
        profile_directory_stat = profile_directory.stat(follow_symlinks=False)
        profile_directory_identity = (
            profile_directory_stat.st_dev,
            profile_directory_stat.st_ino,
        )
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(profile.get("evidence", [])):
        evidence_id = item.get("evidence_id")
        if evidence_id in evidence_by_id:
            errors.append(f"$.evidence[{index}].evidence_id: duplicate evidence id {evidence_id!r}")
        else:
            evidence_by_id[evidence_id] = item

        relative = item.get("path")
        if not isinstance(relative, str) or not _safe_relative_path(relative):
            errors.append(f"$.evidence[{index}].path: path must be a safe forward-slash relative path")
            continue
        if not verify_files:
            continue
        assert profile_directory_identity is not None
        try:
            payload = _read_bound_evidence(
                profile_directory, profile_directory_identity, relative
            )
        except FileNotFoundError:
            errors.append(f"$.evidence[{index}].path: evidence file does not exist: {relative}")
            continue
        except ProfileInvalid as exc:
            errors.append(f"$.evidence[{index}].path: {exc}")
            continue
        except OSError as exc:
            errors.append(f"$.evidence[{index}].path: cannot read evidence file {relative}: {exc}")
            continue
        actual_hash = hashlib.sha256(payload).hexdigest()
        if item.get("byte_count") != len(payload):
            errors.append(
                f"$.evidence[{index}].byte_count: expected {item.get('byte_count')}, actual {len(payload)}"
            )
        if item.get("sha256") != actual_hash:
            errors.append(
                f"$.evidence[{index}].sha256: expected {item.get('sha256')}, actual {actual_hash}"
            )

    for path, observation in _iter_observations(profile):
        for index, evidence_id in enumerate(observation["source"]["evidence_ids"]):
            if evidence_id not in evidence_by_id:
                errors.append(
                    f"{_field_path(path + ('source', 'evidence_ids', index))}: unknown evidence id {evidence_id!r}"
                )
    return errors


def validate_profile(
    profile: Any,
    profile_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    *,
    verify_files: bool = True,
) -> None:
    Draft202012Validator, FormatChecker = _jsonschema_api()
    schema = _load_json(schema_path, label="schema")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ProfileInvalid(f"schema is not valid Draft 2020-12: {exc}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(profile), key=lambda item: _field_path(item.absolute_path))
    messages = [_format_validation_error(error) for error in errors]
    if isinstance(profile, dict) and not errors:
        messages.extend(_semantic_errors(profile, profile_path, verify_files=verify_files))
    if messages:
        raise ProfileInvalid("\n".join(messages))


def _sensitive_tokens(profile: dict[str, Any]) -> tuple[dict[str, set[str]], list[re.Pattern[str]]]:
    tokens = {"user": set(), "host": set()}
    for key, kind in (("user_name", "user"), ("host_name", "host")):
        observation = profile.get("identity", {}).get(key, {})
        value = observation.get("value")
        if observation.get("status") == "success" and isinstance(value, str) and value:
            tokens[kind].add(value)

    path_patterns = [
        re.compile(
            r"(?i)[A-Z]:\\Users\\[^\\/\s\"']+(?:\\[^\r\n\"'<>|]*?)?"
            r"(?=\s+[A-Za-z_][A-Za-z0-9_-]*=|[\r\n\"'<>|]|$)"
        ),
        re.compile(
            r"(?i)/(?:home|Users)/[^/\s\"']+(?:/[^\r\n\"'<>|]*?)?"
            r"(?=\s+[A-Za-z_][A-Za-z0-9_-]*=|[\r\n\"'<>|]|$)"
        ),
    ]
    return tokens, path_patterns


SERIAL_PATTERNS = [
    re.compile(r"(?i)(\b(?:serial(?:[-_ ]?number)?|machine[-_ ]?id|device[-_ ]?id)\s*[:=]\s*)[A-Za-z0-9._:-]{6,}"),
    re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"),
]


def _redact_text(text: str, tokens: dict[str, set[str]], path_patterns: list[re.Pattern[str]]) -> str:
    result = text
    for pattern in path_patterns:
        result = pattern.sub(PLACEHOLDER["path"], result)
    for kind in ("user", "host"):
        for token in sorted(tokens[kind], key=lambda item: (-len(item), item)):
            result = re.sub(re.escape(token), PLACEHOLDER[kind], result, flags=re.IGNORECASE)
    for pattern in SERIAL_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda match: match.group(1) + PLACEHOLDER["serial"], result)
        else:
            result = pattern.sub(PLACEHOLDER["serial"], result)
    return result


SENSITIVE_FIELD = re.compile(
    r"(?i)^(?:serial(?:[-_ ]?number)?|machine[-_ ]?id|device[-_ ]?id)$"
)


def _observation_root(path: tuple[Any, ...]) -> tuple[Any, ...] | None:
    if len(path) >= 2 and path[0] in {
        "identity", "hardware", "os", "graphics", "npu", "runtime_stack"
    }:
        return path[:2]
    if len(path) >= 3 and path[0] == "game_candidates" and isinstance(path[1], int):
        if path[2] in {"name", "executable"}:
            return path[:3]
    return None


def _is_protocol_value(path: tuple[Any, ...]) -> bool:
    if path in {
        ("schema_version",),
        ("profile_kind",),
        ("evidence_level",),
        ("gate",),
        ("collection", "method"),
        ("collection", "started_at"),
        ("collection", "finished_at"),
        ("collection", "tool", "name"),
        ("collection", "tool", "commit"),
    }:
        return True
    if len(path) == 3 and path[0] == "evidence" and isinstance(path[1], int):
        return path[2] in {
            "evidence_id", "collection_item_id", "sha256", "visibility"
        }

    observation = _observation_root(path)
    if observation is None:
        return False
    relative = path[len(observation):]
    return (
        relative in {("observed_at",), ("status",), ("source", "kind"), ("failure", "category")}
        or (
            len(relative) == 3
            and relative[:2] == ("source", "evidence_ids")
            and isinstance(relative[2], int)
        )
    )


def _redact_tree(
    node: Any,
    tokens: dict[str, set[str]],
    path_patterns: list[re.Pattern[str]],
    *,
    key: str | None = None,
    path: tuple[Any, ...] = (),
    preserve_protocol: bool = True,
) -> Any:
    if key is not None and SENSITIVE_FIELD.fullmatch(key):
        return PLACEHOLDER["serial"]
    if isinstance(node, str):
        if preserve_protocol and _is_protocol_value(path):
            return node
        return _redact_text(node, tokens, path_patterns)
    if isinstance(node, list):
        return [
            _redact_tree(
                item, tokens, path_patterns, key=key, path=path + (index,),
                preserve_protocol=preserve_protocol,
            )
            for index, item in enumerate(node)
        ]
    if isinstance(node, dict):
        return {
            child_key: _redact_tree(
                value, tokens, path_patterns, key=child_key, path=path + (child_key,),
                preserve_protocol=preserve_protocol,
            )
            for child_key, value in node.items()
        }
    return node


def _profile_bytes(profile: dict[str, Any]) -> bytes:
    return (json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_new_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)


def _redact_evidence_payload(
    source_path: Path,
    payload: bytes,
    tokens: dict[str, set[str]],
    path_patterns: list[re.Pattern[str]],
) -> bytes | None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if source_path.suffix.lower() == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            redacted = _redact_tree(
                document, tokens, path_patterns, preserve_protocol=False
            )
            return _profile_bytes(redacted) if isinstance(redacted, dict) else (
                json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
    return _redact_text(text, tokens, path_patterns).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def redact_profile(private_path: Path, output_path: Path) -> None:
    private_path = Path(os.path.abspath(os.fspath(private_path)))
    output_path = Path(os.path.abspath(os.fspath(output_path)))
    publication_root = output_path.parent
    if os.path.lexists(publication_root):
        raise InputError(
            f"refusing to overwrite existing output directory: {publication_root}"
        )
    try:
        publication_parent = publication_root.parent
        publication_parent_stat = publication_parent.stat(follow_symlinks=False)
    except OSError as exc:
        raise InputError(
            f"public output parent does not exist or cannot be inspected: "
            f"{publication_root.parent}"
        ) from exc
    if (
        stat.S_ISLNK(publication_parent_stat.st_mode)
        or bool(
            getattr(publication_parent_stat, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        or not stat.S_ISDIR(publication_parent_stat.st_mode)
    ):
        raise InputError(f"public output parent is not a directory: {publication_parent}")
    private_directory = private_path.parent.resolve(strict=True)
    private_directory_stat = private_directory.stat(follow_symlinks=False)
    private_directory_identity = (
        private_directory_stat.st_dev,
        private_directory_stat.st_ino,
    )
    private = _load_json(private_path, label="private profile")
    validate_profile(private, private_path)
    if private.get("profile_kind") != "private":
        raise ProfileInvalid("$.profile_kind: redact requires a private profile")

    tokens, path_patterns = _sensitive_tokens(private)
    public = _redact_tree(copy.deepcopy(private), tokens, path_patterns)
    private_digest = hashlib.sha256(private_path.read_bytes()).hexdigest()
    public["profile_kind"] = "public"
    public["device_profile_id"] = f"public-{private_digest[:24]}"
    public["supersedes"] = None
    public["redaction"] = {
        "policy": "public-v1",
        "source_profile_sha256": private_digest,
        "redacted_at": _utc_now(),
    }
    for index, candidate in enumerate(public["game_candidates"], start=1):
        candidate["candidate_id"] = f"public-candidate-{index:04d}"

    published: list[tuple[dict[str, Any], bytes, PurePosixPath]] = []
    public_id_by_private_id: dict[str, str] = {}
    for index, item in enumerate(private["evidence"], start=1):
        source_path = private_path.parent.joinpath(*PurePosixPath(item["path"]).parts)
        payload = _read_bound_evidence(
            private_directory, private_directory_identity, item["path"]
        )
        if source_path.suffix.lower() not in {".txt", ".log", ".json", ".stdout", ".stderr"}:
            continue
        redacted_payload = _redact_evidence_payload(source_path, payload, tokens, path_patterns)
        if redacted_payload is None:
            continue
        digest = hashlib.sha256(redacted_payload).hexdigest()
        public_id = f"public-evidence-{index:04d}-{digest[:16]}"
        suffix = source_path.suffix.lower()
        relative = f"evidence/{public_id}{suffix}"
        public_item = copy.deepcopy(item)
        public_item.update(
            evidence_id=public_id,
            collection_item_id=f"public-item-{index:04d}",
            path=relative,
            sha256=digest,
            byte_count=len(redacted_payload),
            visibility="public",
        )
        published.append((public_item, redacted_payload, PurePosixPath(relative)))
        public_id_by_private_id[item["evidence_id"]] = public_id

    public["evidence"] = [item for item, _, _ in published]
    for _, observation in _iter_observations(public):
        observation["source"]["evidence_ids"] = [
            public_id_by_private_id[evidence_id]
            for evidence_id in observation["source"]["evidence_ids"]
            if evidence_id in public_id_by_private_id
        ]

    # Validate structure and relationships before creating any public artifact.
    validate_profile(public, output_path, verify_files=False)
    staging_root: Path | None = None
    try:
        staging_root = Path(
            tempfile.mkdtemp(
                prefix=f".{publication_root.name}.redacting-",
                dir=publication_parent,
            )
        )
        staged_output = staging_root / output_path.name
        for _, payload, relative in published:
            destination = staging_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_new_file(destination, payload)
        _write_new_file(staged_output, _profile_bytes(public))
        staged_public = _load_json(staged_output, label="staged public profile")
        if staged_public != public:
            raise ProfileInvalid("staged public profile differs from the validated profile")
        validate_profile(staged_public, staged_output)
        os.rename(staging_root, publication_root)
    except FileExistsError as exc:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        raise InputError(f"refusing to overwrite existing output: {exc.filename}") from exc
    except (InputError, ProfileInvalid, FatalError):
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        raise
    except OSError as exc:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        raise FatalError(f"cannot write public artifacts: {exc}") from exc
    except Exception:
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate a profile and its evidence")
    validate.add_argument("profile", type=Path)
    validate.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    redact = subparsers.add_parser("redact", help="create a public-v1 profile and evidence")
    redact.add_argument("private_profile", type=Path)
    redact.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "validate":
            profile = _load_json(args.profile, label="profile")
            validate_profile(profile, args.profile, args.schema)
        else:
            redact_profile(args.private_profile, args.output)
        return 0
    except ProfileInvalid as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    except InputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    except FatalError as exc:
        print(f"fatal error: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"fatal error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline validation and public redaction for M0 device profiles."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
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


def _iter_observations(node: Any, path: tuple[Any, ...] = ()):
    if isinstance(node, dict):
        if {"value", "source", "observed_at", "status", "failure"}.issubset(node):
            yield path, node
        for key, value in node.items():
            yield from _iter_observations(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_observations(value, path + (index,))


def _semantic_errors(profile: dict[str, Any], profile_path: Path, *, verify_files: bool) -> list[str]:
    errors: list[str] = []
    profile_directory = profile_path.parent.resolve()
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
        evidence_path = profile_path.parent.joinpath(*PurePosixPath(relative).parts)
        try:
            resolved_evidence_path = evidence_path.resolve(strict=True)
        except FileNotFoundError:
            errors.append(f"$.evidence[{index}].path: evidence file does not exist: {relative}")
            continue
        except OSError as exc:
            errors.append(f"$.evidence[{index}].path: cannot resolve evidence file {relative}: {exc}")
            continue
        if (
            resolved_evidence_path != profile_directory
            and profile_directory not in resolved_evidence_path.parents
        ):
            errors.append(
                f"$.evidence[{index}].path: resolved evidence path escapes profile directory: {relative}"
            )
            continue
        try:
            payload = resolved_evidence_path.read_bytes()
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
    re.compile(r"(?i)(\b(?:serial(?:\s+number)?|machine[-_ ]?id|device[-_ ]?id)\s*[:=]\s*)[A-Za-z0-9._:-]{6,}"),
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


REDACTION_PRESERVED_KEYS = {
    "schema_version",
    "evidence_id",
    "evidence_ids",
    "collection_item_id",
    "sha256",
    "commit",
    "policy",
    "status",
    "category",
    "kind",
    "method",
    "profile_kind",
    "evidence_level",
    "gate",
    "visibility",
    "observed_at",
    "started_at",
    "finished_at",
    "candidate_id",
}

SENSITIVE_FIELD = re.compile(r"(?i)^(?:serial(?:_number)?|machine_id|device_id)$")


def _redact_tree(
    node: Any,
    tokens: dict[str, set[str]],
    path_patterns: list[re.Pattern[str]],
    *,
    key: str | None = None,
    path: tuple[Any, ...] = (),
) -> Any:
    if isinstance(node, str):
        if key in REDACTION_PRESERVED_KEYS or path == ("collection", "tool", "name"):
            return node
        if key is not None and SENSITIVE_FIELD.fullmatch(key):
            return PLACEHOLDER["serial"]
        return _redact_text(node, tokens, path_patterns)
    if isinstance(node, list):
        return [
            _redact_tree(item, tokens, path_patterns, key=key, path=path + (index,))
            for index, item in enumerate(node)
        ]
    if isinstance(node, dict):
        return {
            child_key: _redact_tree(
                value, tokens, path_patterns, key=child_key, path=path + (child_key,)
            )
            for child_key, value in node.items()
        }
    return node


def _profile_bytes(profile: dict[str, Any]) -> bytes:
    return (json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
            redacted = _redact_tree(document, tokens, path_patterns)
            return _profile_bytes(redacted) if isinstance(redacted, dict) else (
                json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
    return _redact_text(text, tokens, path_patterns).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def redact_profile(private_path: Path, output_path: Path) -> None:
    if output_path.exists():
        raise InputError(f"refusing to overwrite existing output: {output_path}")
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

    published: list[tuple[dict[str, Any], bytes, Path]] = []
    public_id_by_private_id: dict[str, str] = {}
    for index, item in enumerate(private["evidence"], start=1):
        source_path = private_path.parent.joinpath(*PurePosixPath(item["path"]).parts)
        payload = source_path.read_bytes()
        if source_path.suffix.lower() not in {".txt", ".log", ".json", ".stdout", ".stderr"}:
            continue
        redacted_payload = _redact_evidence_payload(source_path, payload, tokens, path_patterns)
        if redacted_payload is None:
            continue
        digest = hashlib.sha256(redacted_payload).hexdigest()
        public_id = f"public-evidence-{index:04d}-{digest[:16]}"
        suffix = source_path.suffix.lower()
        relative = f"evidence/{public_id}{suffix}"
        destination = output_path.parent.joinpath(*PurePosixPath(relative).parts)
        if destination.exists():
            raise InputError(f"refusing to overwrite existing public evidence: {destination}")
        public_item = copy.deepcopy(item)
        public_item.update(
            evidence_id=public_id,
            collection_item_id=f"public-item-{index:04d}",
            path=relative,
            sha256=digest,
            byte_count=len(redacted_payload),
            visibility="public",
        )
        published.append((public_item, redacted_payload, destination))
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_root = output_path.parent.resolve(strict=True)
    try:
        for _, payload, destination in published:
            destination.parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = destination.parent.resolve(strict=True)
            if resolved_parent != output_root and output_root not in resolved_parent.parents:
                raise InputError(f"public evidence destination escapes output directory: {destination}")
            resolved_destination = destination.resolve(strict=False)
            if resolved_destination.parent != resolved_parent:
                raise InputError(f"public evidence destination escapes output directory: {destination}")
            with destination.open("xb") as stream:
                stream.write(payload)
        with output_path.open("xb") as stream:
            stream.write(_profile_bytes(public))
    except FileExistsError as exc:
        raise InputError(f"refusing to overwrite existing output: {exc.filename}") from exc
    except OSError as exc:
        raise FatalError(f"cannot write public artifacts: {exc}") from exc


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

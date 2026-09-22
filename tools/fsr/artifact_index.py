#!/usr/bin/env python3
"""Strict loader for the source-controlled FSR receipt classification index."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "fsr-artifact-index-v1"
INDEX_PATH = Path(__file__).with_name("artifact_index.json")
MAX_INDEX_BYTES = 64 << 10
KINDS = frozenset({"p7-receipt", "p8-receipt"})
CLASSIFICATIONS = frozenset(
    {"accepted-current", "historical-stale", "audit-temporary"}
)
ROOT_FIELDS = frozenset({"schema_version", "artifacts"})
ENTRY_FIELDS = frozenset(
    {
        "artifact_id",
        "kind",
        "classification",
        "receipt_schema",
        "receipt_sha256",
        "p7_receipt_sha256",
        "max_int8_lsb_difference",
        "note",
    }
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")


class ArtifactIndexError(Exception):
    """The artifact index is malformed or has an ambiguous trust selection."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ArtifactIndexError(f"duplicate object key: {key!r}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ArtifactIndexError(f"non-finite JSON number is forbidden: {value}")


def _exact_fields(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactIndexError(f"{label} must be an object")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise ArtifactIndexError(f"{label} has unknown field: {unknown[0]}")
    if missing:
        raise ArtifactIndexError(f"{label} is missing field: {missing[0]}")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ArtifactIndexError(f"{label} must be a lowercase SHA-256")
    return value


def load_artifact_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_INDEX_BYTES + 1)
    except OSError as exc:
        raise ArtifactIndexError(f"cannot read artifact index: {exc}") from exc
    if len(payload) > MAX_INDEX_BYTES:
        raise ArtifactIndexError(f"artifact index exceeds {MAX_INDEX_BYTES} byte limit")
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactIndexError(f"artifact index is not valid UTF-8 JSON: {exc}") from exc
    root = _exact_fields(root, ROOT_FIELDS, "artifact index")
    if root["schema_version"] != SCHEMA_VERSION:
        raise ArtifactIndexError(f"artifact index schema must equal {SCHEMA_VERSION!r}")
    artifacts = root["artifacts"]
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 64:
        raise ArtifactIndexError("artifact index artifacts must be a non-empty list of at most 64 entries")

    identifiers: set[str] = set()
    digests: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for position, raw in enumerate(artifacts):
        label = f"artifact index artifacts[{position}]"
        entry = _exact_fields(raw, ENTRY_FIELDS, label)
        artifact_id = entry["artifact_id"]
        if not isinstance(artifact_id, str) or ID_RE.fullmatch(artifact_id) is None:
            raise ArtifactIndexError(f"{label}.artifact_id is invalid")
        if artifact_id in identifiers:
            raise ArtifactIndexError(f"duplicate artifact_id: {artifact_id}")
        identifiers.add(artifact_id)
        kind = entry["kind"]
        classification = entry["classification"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise ArtifactIndexError(f"{label}.kind is invalid")
        if not isinstance(classification, str) or classification not in CLASSIFICATIONS:
            raise ArtifactIndexError(f"{label}.classification is invalid")
        receipt_schema = entry["receipt_schema"]
        note = entry["note"]
        if not isinstance(receipt_schema, str) or not receipt_schema or len(receipt_schema) > 80:
            raise ArtifactIndexError(f"{label}.receipt_schema is invalid")
        if not isinstance(note, str) or not note.strip() or len(note) > 300:
            raise ArtifactIndexError(f"{label}.note is invalid")
        digest = _sha256(entry["receipt_sha256"], f"{label}.receipt_sha256")
        digest_key = (kind, digest)
        if digest_key in digests:
            raise ArtifactIndexError(f"duplicate {kind} receipt SHA-256: {digest}")
        digests.add(digest_key)
        p7_digest = entry["p7_receipt_sha256"]
        tolerance = entry["max_int8_lsb_difference"]
        if kind == "p7-receipt":
            if p7_digest is not None or tolerance is not None:
                raise ArtifactIndexError(f"{label} P7 linkage/tolerance fields must be null")
        else:
            _sha256(p7_digest, f"{label}.p7_receipt_sha256")
            if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 0:
                raise ArtifactIndexError(f"{label}.max_int8_lsb_difference must be a non-negative integer")
        normalized.append(dict(entry))

    for kind in KINDS:
        current = [
            entry
            for entry in normalized
            if entry["kind"] == kind and entry["classification"] == "accepted-current"
        ]
        if len(current) != 1:
            raise ArtifactIndexError(f"artifact index must contain exactly one accepted-current {kind}")
    if set(entry["classification"] for entry in normalized) != CLASSIFICATIONS:
        raise ArtifactIndexError("artifact index must represent current, historical-stale, and audit-temporary classifications")
    current_p7 = current_artifact({"schema_version": SCHEMA_VERSION, "artifacts": normalized}, "p7-receipt")
    current_p8 = current_artifact({"schema_version": SCHEMA_VERSION, "artifacts": normalized}, "p8-receipt")
    if current_p7["receipt_schema"] != "p7-fsr-intake-receipt-v2":
        raise ArtifactIndexError("accepted-current P7 must use the R10a v2 receipt schema")
    if current_p8["receipt_schema"] != "p8-fsr-pass0-check-v1":
        raise ArtifactIndexError("accepted-current P8 receipt schema mismatch")
    if current_p8["p7_receipt_sha256"] != current_p7["receipt_sha256"]:
        raise ArtifactIndexError("accepted-current P8 must bind the accepted-current P7 digest")
    if current_p8["max_int8_lsb_difference"] != 0:
        raise ArtifactIndexError("accepted-current P8 must have zero-LSB tolerance")
    return {"schema_version": SCHEMA_VERSION, "artifacts": normalized}


def current_artifact(index: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ArtifactIndexError(f"unknown artifact kind: {kind!r}")
    matches = [
        entry
        for entry in index.get("artifacts", [])
        if entry.get("kind") == kind and entry.get("classification") == "accepted-current"
    ]
    if len(matches) != 1:
        raise ArtifactIndexError(f"expected exactly one accepted-current {kind}")
    return dict(matches[0])


def classify_receipt(index: dict[str, Any], kind: str, digest: str) -> dict[str, Any]:
    _sha256(digest, "receipt digest")
    matches = [
        entry
        for entry in index.get("artifacts", [])
        if entry.get("kind") == kind and entry.get("receipt_sha256") == digest
    ]
    if len(matches) != 1:
        raise ArtifactIndexError("receipt digest is not uniquely classified by the artifact index")
    return dict(matches[0])

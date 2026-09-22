#!/usr/bin/env python3
"""Strict F01 inventory loader; this does not implement any FSR pass."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from tools.fsr.artifact_index import INDEX_PATH, current_artifact, load_artifact_index


SCHEMA_VERSION = "fsr-pass1-13-manifest-v1"
MANIFEST_PATH = Path(__file__).with_name("pass_manifest.json")
MAX_MANIFEST_BYTES = 256 << 10
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ROOT_FIELDS = frozenset({"schema_version", "sources", "fixed_input", "layout_conventions", "quantization_conventions", "passes", "limitations"})
SOURCE_FIELDS = frozenset({"artifact_index_schema", "p7_receipt_sha256", "p8_receipt_sha256", "weights_sha256", "weights_byte_count", "graph_sha256", "graph_byte_count", "simulator_url", "simulator_commit", "simulator_sha256", "simulator_byte_count"})
FIXED_FIELDS = frozenset({"case_id", "generator", "shape", "layout", "dtype", "quantization", "scale", "sha256"})
PASS_FIELDS = frozenset({"pass_id", "call_index", "operator", "inputs", "output", "weights", "quantization", "fixed_input_case", "independent_expected"})
TENSOR_FIELDS = frozenset({"name", "source", "shape", "layout", "dtype", "quantization"})
WEIGHT_FIELDS = frozenset({"key", "shape", "layout", "dtype"})
QUANT_FIELDS = frozenset({"input", "weight", "accumulator", "output", "call_arguments"})
EXPECTED_FIELDS = frozenset({"status", "source", "sha256", "reason"})
LIMIT_FIELDS = frozenset({"pass1_13_implemented", "independent_expected_available", "official_golden_available", "device_qnn_htp_game"})
LAYOUT_FIELDS = frozenset({"graph_decl_logical", "source_weight_logical", "cpu_activation", "cpu_regular_weight", "cpu_transposed_weight", "provenance"})
SHARED_QUANT_FIELDS = frozenset({"provenance", "zero_point", "rounding", "saturation", "multiply_order", "operator_source_verification"})
OPERATORS = (
    "ConvNextBlock", "ConvNextBlock", "FusedConv2D_k2s2b_QuantizedOutput",
    "FasterNetBlock<32, 1>", "FasterNetBlock<32, 1>", "FusedConv2D_k2s2b_QuantizedOutput",
    "FasterNetBlock<64, 2>", "FasterNetBlock<64, 2>", "FNB_CT2D_ADD<64, 2>",
    "FasterNetBlock<32, 1>", "FNB_CT2D_ADD<32, 1>", "ConvNextBlock",
    "FusedConv2D_DW_Conv2D_PW_Relu_Conv2D_Add_ConvTranspose2D",
)
FORMATS = frozenset({"uniform-int8", "split-half-int8", "none-fp16"})
EXPECTED_OUTPUTS = (
    ([8,8,16], "int8", "uniform-int8"), ([8,8,16], "int8", "uniform-int8"),
    ([4,4,32], "int8", "split-half-int8"), ([4,4,32], "int8", "split-half-int8"),
    ([4,4,32], "int8", "uniform-int8"), ([2,2,64], "int8", "split-half-int8"),
    ([2,2,64], "int8", "split-half-int8"), ([2,2,64], "int8", "split-half-int8"),
    ([4,4,32], "int8", "split-half-int8"), ([4,4,32], "int8", "split-half-int8"),
    ([8,8,16], "int8", "uniform-int8"), ([8,8,16], "int8", "uniform-int8"),
    ([16,16,8], "float16", "none-fp16"),
)
EXPECTED_INPUT_SOURCES = (
    ("fixed-input",), ("p1",), ("p2",), ("p3",), ("p4",), ("p5",),
    ("p6",), ("p7",), ("p8", "p5"), ("p9",), ("p10", "p2"),
    ("p11",), ("p12",),
)
EXPECTED_WEIGHTS = (
    (("encoder2_RB0_conv_dw_weight", (16,16,3,3), "OIHW"), ("encoder2_RB0_pw_expand_weight", (32,16,1,1), "OIHW"), ("encoder2_RB0_pw_contract_weight", (16,32,1,1), "OIHW")),
    (("encoder2_RB1_conv_dw_weight", (16,16,3,3), "OIHW"), ("encoder2_RB1_pw_expand_weight", (32,16,1,1), "OIHW"), ("encoder2_RB1_pw_contract_weight", (16,32,1,1), "OIHW")),
    (("enc2_ds_weight", (32,16,2,2), "OIHW"),),
    (("encoder3_ResidualBlock_0_spatial_weight", (16,16,3,3), "OIHW"), ("encoder3_ResidualBlock_0_pw_expand_weight", (64,32,1,1), "OIHW"), ("encoder3_ResidualBlock_0_pw_contract_weight", (32,64,1,1), "OIHW")),
    (("encoder3_ResidualBlock_1_spatial_weight", (16,16,3,3), "OIHW"), ("encoder3_ResidualBlock_1_pw_expand_weight", (64,32,1,1), "OIHW"), ("encoder3_ResidualBlock_1_pw_contract_weight", (32,64,1,1), "OIHW")),
    (("enc3_ds_weight", (64,32,2,2), "OIHW"),),
    (("bottleneck_ResidualBlock_0_spatial_weight", (32,16,3,3), "OIHW"), ("bottleneck_ResidualBlock_0_pw_expand_weight", (128,64,1,1), "OIHW"), ("bottleneck_ResidualBlock_0_pw_contract_weight", (64,128,1,1), "OIHW")),
    (("bottleneck_ResidualBlock_1_spatial_weight", (32,16,3,3), "OIHW"), ("bottleneck_ResidualBlock_1_pw_expand_weight", (128,64,1,1), "OIHW"), ("bottleneck_ResidualBlock_1_pw_contract_weight", (64,128,1,1), "OIHW")),
    (("bottleneck_ResidualBlock_2_spatial_weight", (32,16,3,3), "OIHW"), ("bottleneck_ResidualBlock_2_pw_expand_weight", (128,64,1,1), "OIHW"), ("bottleneck_ResidualBlock_2_pw_contract_weight", (64,128,1,1), "OIHW"), ("bottleneck_ct_weight", (64,32,2,2), "IOHW")),
    (("decoder3_ResidualBlock_1_spatial_weight", (16,16,3,3), "OIHW"), ("decoder3_ResidualBlock_1_pw_expand_weight", (64,32,1,1), "OIHW"), ("decoder3_ResidualBlock_1_pw_contract_weight", (32,64,1,1), "OIHW")),
    (("decoder3_ResidualBlock_2_spatial_weight", (16,16,3,3), "OIHW"), ("decoder3_ResidualBlock_2_pw_expand_weight", (64,32,1,1), "OIHW"), ("decoder3_ResidualBlock_2_pw_contract_weight", (32,64,1,1), "OIHW"), ("dec3_ct_weight", (32,16,2,2), "IOHW")),
    (("decoder2_RB1_conv_dw_weight", (16,16,3,3), "OIHW"), ("decoder2_RB1_pw_expand_weight", (32,16,1,1), "OIHW"), ("decoder2_RB1_pw_contract_weight", (16,32,1,1), "OIHW")),
    (("decoder2_ResidualBlock_2_conv_dw_weight", (16,16,3,3), "OIHW"), ("decoder2_ResidualBlock_2_pw_expand_weight", (32,16,1,1), "OIHW"), ("decoder2_ResidualBlock_2_pw_contract_weight", (16,32,1,1), "OIHW"), ("dec2_ct_weight", (16,8,2,2), "IOHW")),
)


class PassManifestError(Exception):
    """The F01 inventory or a selected bound source is invalid."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PassManifestError(f"duplicate object key: {key!r}")
        result[key] = value
    return result


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PassManifestError(f"{label} must be an object")
    unknown, missing = sorted(set(value) - fields), sorted(fields - set(value))
    if unknown:
        raise PassManifestError(f"{label} has unknown field: {unknown[0]}")
    if missing:
        raise PassManifestError(f"{label} is missing field: {missing[0]}")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise PassManifestError(f"{label} must be a lowercase SHA-256")
    return value


def _shape(value: Any, rank: int, label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != rank or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise PassManifestError(f"{label} must be {rank} positive integer dimensions")
    return value


def load_pass_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise PassManifestError(f"cannot read pass manifest: {exc}") from exc
    if len(payload) > MAX_MANIFEST_BYTES:
        raise PassManifestError("pass manifest exceeds byte limit")
    try:
        root = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(PassManifestError(f"non-finite JSON number: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PassManifestError(f"pass manifest is not valid UTF-8 JSON: {exc}") from exc
    root = _exact(root, ROOT_FIELDS, "pass manifest")
    if root["schema_version"] != SCHEMA_VERSION:
        raise PassManifestError("pass manifest schema mismatch")

    sources = _exact(root["sources"], SOURCE_FIELDS, "sources")
    index = load_artifact_index(INDEX_PATH)
    p7 = current_artifact(index, "p7-receipt")
    p8 = current_artifact(index, "p8-receipt")
    if sources["artifact_index_schema"] != index["schema_version"] or sources["p7_receipt_sha256"] != p7["receipt_sha256"] or sources["p8_receipt_sha256"] != p8["receipt_sha256"]:
        raise PassManifestError("manifest sources do not bind the current artifact index")
    for field in ("weights_sha256", "graph_sha256", "simulator_sha256"):
        _sha(sources[field], f"sources.{field}")
    if not isinstance(sources["simulator_url"], str) or not sources["simulator_url"].startswith("https://github.com/"):
        raise PassManifestError("sources.simulator_url is invalid")
    if not isinstance(sources["simulator_commit"], str) or re.fullmatch(r"[0-9a-f]{40}", sources["simulator_commit"]) is None:
        raise PassManifestError("sources.simulator_commit is invalid")
    for field in ("weights_byte_count", "graph_byte_count", "simulator_byte_count"):
        if isinstance(sources[field], bool) or not isinstance(sources[field], int) or sources[field] <= 0:
            raise PassManifestError(f"sources.{field} is invalid")

    fixed = _exact(root["fixed_input"], FIXED_FIELDS, "fixed_input")
    if fixed["case_id"] != "f01-synthetic-8x8-int8-v1" or fixed["generator"] != "value[i]=((i*37+11)%255)-127; C-order":
        raise PassManifestError("fixed_input identity/generator mismatch")
    if _shape(fixed["shape"], 3, "fixed_input.shape") != [8, 8, 16] or fixed["layout"] != "HWC" or fixed["dtype"] != "int8" or fixed["quantization"] != "uniform-int8":
        raise PassManifestError("fixed_input tensor contract mismatch")
    if isinstance(fixed["scale"], bool) or not isinstance(fixed["scale"], (int, float)) or not math.isfinite(fixed["scale"]) or fixed["scale"] <= 0:
        raise PassManifestError("fixed_input.scale is invalid")
    generated = bytes((((index * 37 + 11) % 255) - 127) & 0xFF for index in range(8 * 8 * 16))
    if fixed["sha256"] != hashlib.sha256(generated).hexdigest():
        raise PassManifestError("fixed_input SHA-256 does not match its generator")

    layouts = _exact(root["layout_conventions"], LAYOUT_FIELDS, "layout_conventions")
    if layouts != {
        "graph_decl_logical": "WHCN", "source_weight_logical": "KH_KW_CIN_COUT",
        "cpu_activation": "HWC",
        "cpu_regular_weight": "OIHW", "cpu_transposed_weight": "IOHW",
        "provenance": "P7 graph declarations use source logical W,H,C,N (weights: KH,KW,Cin,Cout); pinned simulator-derived NumPy arrays use the listed CPU layouts.",
    }:
        raise PassManifestError("layout conventions must distinguish source logical and CPU layouts")
    shared_quant = _exact(root["quantization_conventions"], SHARED_QUANT_FIELDS, "quantization_conventions")
    if shared_quant != {
        "provenance": "derived-from-pinned-simulator-not-independently-verified-operator-source",
        "zero_point": "unknown",
        "rounding": "simulator-derived-half-away-from-zero",
        "saturation": "simulator-derived-int8-clamp",
        "multiply_order": "simulator-derived-per-call",
        "operator_source_verification": "unknown-missing-ml2code-runtime-hlsli",
    }:
        raise PassManifestError("quantization provenance overstates independent verification")

    passes = root["passes"]
    if not isinstance(passes, list) or len(passes) != 13:
        raise PassManifestError("passes must contain exactly p1 through p13")
    outputs: dict[str, dict[str, Any]] = {}
    for position, raw in enumerate(passes):
        label = f"passes[{position}]"
        item = _exact(raw, PASS_FIELDS, label)
        expected_id = f"p{position + 1}"
        if (item["pass_id"] != expected_id or isinstance(item["call_index"], bool)
                or not isinstance(item["call_index"], int) or item["call_index"] != position
                or item["operator"] != OPERATORS[position]):
            raise PassManifestError(f"{label} identity/operator mismatch")
        if item["fixed_input_case"] != fixed["case_id"]:
            raise PassManifestError(f"{label} fixed input case mismatch")
        inputs = item["inputs"]
        if not isinstance(inputs, list) or len(inputs) not in (1, 2):
            raise PassManifestError(f"{label}.inputs must contain primary and optional skip")
        if len(inputs) != len(EXPECTED_INPUT_SOURCES[position]):
            raise PassManifestError(f"{label} input topology mismatch")
        for input_position, raw_tensor in enumerate(inputs):
            tensor = _exact(raw_tensor, TENSOR_FIELDS, f"{label}.inputs[{input_position}]")
            if tensor["name"] != ("primary" if input_position == 0 else "skip"):
                raise PassManifestError(f"{label}.inputs order/name mismatch")
            _shape(tensor["shape"], 3, f"{label}.inputs[{input_position}].shape")
            if (tensor["layout"] != "HWC" or tensor["dtype"] not in ("int8", "float16")
                    or not isinstance(tensor["quantization"], str) or tensor["quantization"] not in FORMATS):
                raise PassManifestError(f"{label}.inputs[{input_position}] tensor format mismatch")
            source = tensor["source"]
            if not isinstance(source, str):
                raise PassManifestError(f"{label}.inputs[{input_position}].source must be a string")
            if source != EXPECTED_INPUT_SOURCES[position][input_position]:
                raise PassManifestError(f"{label} input topology mismatch")
            if source == "fixed-input":
                producer = {"shape": fixed["shape"], "layout": fixed["layout"], "dtype": fixed["dtype"], "quantization": fixed["quantization"]}
            else:
                producer = outputs.get(source)
            if producer is None or any(tensor[field] != producer[field] for field in ("shape", "layout", "dtype", "quantization")):
                raise PassManifestError(f"{label}.inputs[{input_position}] does not match its producer")
        output = _exact(item["output"], TENSOR_FIELDS - {"source"}, f"{label}.output")
        if output["name"] != expected_id:
            raise PassManifestError(f"{label}.output name mismatch")
        _shape(output["shape"], 3, f"{label}.output.shape")
        if (output["layout"] != "HWC" or output["dtype"] not in ("int8", "float16")
                or not isinstance(output["quantization"], str) or output["quantization"] not in FORMATS):
            raise PassManifestError(f"{label}.output tensor format mismatch")
        expected_shape, expected_dtype, expected_quantization = EXPECTED_OUTPUTS[position]
        if output["shape"] != expected_shape or output["dtype"] != expected_dtype or output["quantization"] != expected_quantization:
            raise PassManifestError(f"{label}.output fixed shape/dtype/quantization mismatch")
        weights = item["weights"]
        if not isinstance(weights, list) or not weights:
            raise PassManifestError(f"{label}.weights must be non-empty")
        weight_keys: set[str] = set()
        for weight_position, raw_weight in enumerate(weights):
            weight = _exact(raw_weight, WEIGHT_FIELDS, f"{label}.weights[{weight_position}]")
            if not isinstance(weight["key"], str) or not weight["key"] or weight["key"] in weight_keys:
                raise PassManifestError(f"{label}.weights has invalid/duplicate key")
            weight_keys.add(weight["key"])
            _shape(weight["shape"], 4, f"{label}.weights[{weight_position}].shape")
            if weight["layout"] not in ("OIHW", "IOHW") or weight["dtype"] != "int8":
                raise PassManifestError(f"{label}.weights[{weight_position}] format mismatch")
        observed_weights = tuple((entry["key"], tuple(entry["shape"]), entry["layout"]) for entry in weights)
        if observed_weights != EXPECTED_WEIGHTS[position]:
            raise PassManifestError(f"{label}.weights does not match the fixed alias/shape/layout set")
        quant = _exact(item["quantization"], QUANT_FIELDS, f"{label}.quantization")
        if quant["input"] != inputs[0]["quantization"] or quant["output"] != output["quantization"] or quant["weight"] != "per-tensor-int8-scale-from-p7" or quant["accumulator"] != "int32-dot-product":
            raise PassManifestError(f"{label}.quantization contract mismatch")
        arguments = quant["call_arguments"]
        if not isinstance(arguments, list) or not arguments or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in arguments):
            raise PassManifestError(f"{label}.quantization.call_arguments is invalid")
        expected = _exact(item["independent_expected"], EXPECTED_FIELDS, f"{label}.independent_expected")
        if expected["status"] != "unknown" or expected["source"] is not None or expected["sha256"] is not None or not isinstance(expected["reason"], str) or not expected["reason"]:
            raise PassManifestError(f"{label}.independent_expected must remain explicit unknown")
        outputs[expected_id] = dict(output)

    limitations = _exact(root["limitations"], LIMIT_FIELDS, "limitations")
    for field in ("pass1_13_implemented", "independent_expected_available", "official_golden_available"):
        if not isinstance(limitations[field], bool):
            raise PassManifestError(f"limitations.{field} must be boolean")
    if not isinstance(limitations["device_qnn_htp_game"], str):
        raise PassManifestError("limitations.device_qnn_htp_game must be a string")
    if limitations != {"pass1_13_implemented": False, "independent_expected_available": False, "official_golden_available": False, "device_qnn_htp_game": "not_run"}:
        raise PassManifestError("limitations overstate F01 evidence")
    return root


def _bound_source_payloads(
    manifest: dict[str, Any], p7_directory: Path, simulator: Path
) -> dict[str, bytes]:
    sources = manifest["sources"]
    selected = (
        ("receipt", p7_directory / "intake_receipt.json", sources["p7_receipt_sha256"], None),
        ("weights", p7_directory / "fsr4_quality_weights.npz", sources["weights_sha256"], sources["weights_byte_count"]),
        ("graph", p7_directory / "graph_spec.json", sources["graph_sha256"], sources["graph_byte_count"]),
        ("simulator", simulator, sources["simulator_sha256"], sources["simulator_byte_count"]),
    )
    payloads: dict[str, bytes] = {}
    for name, path, expected_hash, expected_size in selected:
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise PassManifestError(f"cannot read bound source {path}: {exc}") from exc
        if expected_size is not None and len(payload) != expected_size:
            raise PassManifestError(f"bound source byte count mismatch: {path}")
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise PassManifestError(f"bound source SHA-256 mismatch: {path}")
        payloads[name] = payload

    try:
        receipt = json.loads(payloads["receipt"].decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PassManifestError(f"accepted P7 receipt is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "p7-fsr-intake-receipt-v2":
        raise PassManifestError("accepted P7 receipt is not the required v2 schema")
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"fsr4_quality_weights.npz", "graph_spec.json"}:
        raise PassManifestError("accepted P7 receipt outputs are missing or malformed")
    expected_outputs = {
        "fsr4_quality_weights.npz": (sources["weights_byte_count"], sources["weights_sha256"]),
        "graph_spec.json": (sources["graph_byte_count"], sources["graph_sha256"]),
    }
    for name, (byte_count, digest) in expected_outputs.items():
        entry = outputs[name]
        if (not isinstance(entry, dict) or isinstance(entry.get("byte_count"), bool)
                or entry.get("byte_count") != byte_count or entry.get("sha256") != digest):
            raise PassManifestError(f"accepted P7 receipt output binding mismatch: {name}")
    return payloads


def verify_bound_sources(manifest: dict[str, Any], p7_directory: Path, simulator: Path) -> None:
    _bound_source_payloads(manifest, p7_directory, simulator)


def execute_bound_simulator(
    manifest: dict[str, Any], p7_directory: Path, simulator: Path
) -> dict[str, Any]:
    """Execute exactly the simulator bytes authenticated by the F01 bindings."""
    payload = _bound_source_payloads(manifest, p7_directory, simulator)["simulator"]
    namespace: dict[str, Any] = {
        "__name__": "f01_pinned_simulator",
        "__file__": str(simulator),
        "__package__": None,
    }
    code = compile(payload, str(simulator), "exec")
    exec(code, namespace)
    return namespace

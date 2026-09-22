#!/usr/bin/env python3
"""F02a CPU references for FSR passes 1-4 only.

The vector path and scalar oracle share the accepted P7 tensors and the
simulator-derived operation contract, but they do not share convolution or
requantization implementations.  This is offline NumPy evidence, not an
independent operator-source or device implementation.
"""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Any

import numpy as np

from tools.fsr.pass_manifest import load_bound_simulator_snapshot


F32 = np.float32
P1_OUTPUT_SCALE = F32(0.01933070458471775)
P2_OUTPUT_SCALE = F32(0.02335178479552269)
WEIGHT_SCALES = {
    "encoder2_RB0_conv_dw": F32(0.005331969354301691),
    "encoder2_RB0_pw_expand": F32(0.005319580901414156),
    "encoder2_RB0_pw_contract": F32(0.005279477220028639),
    "encoder2_RB1_conv_dw": F32(0.005748785100877285),
    "encoder2_RB1_pw_expand": F32(0.005573894362896681),
    "encoder2_RB1_pw_contract": F32(0.005647121462970972),
    "enc2_ds": F32(0.003455055644735694),
    "encoder3_ResidualBlock_0_spatial": F32(0.005027378909289837),
    "encoder3_ResidualBlock_0_pw_expand": F32(0.004323530476540327),
    "encoder3_ResidualBlock_0_pw_contract": F32(0.004300548229366541),
}
DIRECT_INPUT_SPECS = {
    "p1": {"shape": (8, 8, 16), "multiplier": 37, "offset": 11, "scales": (F32(0.014884727075695992),)},
    "p2": {"shape": (8, 8, 16), "multiplier": 29, "offset": 7, "scales": (P1_OUTPUT_SCALE,)},
    "p3": {"shape": (8, 8, 16), "multiplier": 43, "offset": 19, "scales": (P2_OUTPUT_SCALE,)},
    "p4": {"shape": (4, 4, 32), "multiplier": 53, "offset": 23, "scales": (F32(0.015390855260193348), F32(0.018884973600506783))},
}
EXPECTED_OUTPUT_SCALES = {
    "p1": (P1_OUTPUT_SCALE,),
    "p2": (P2_OUTPUT_SCALE,),
    "p3": (F32(0.015390855260193348), F32(0.018884973600506783)),
    "p4": (F32(0.017191138118505478), F32(0.021955177187919617)),
}
Q = "_quant_export_handler_QuantizeLinear_output_0"
RAW_BINDINGS = {
    "encoder2_RB0_conv_dw_weight": f"embedded__encoder2_ResidualBlock_0_body_conv_dw_weight{Q}",
    "encoder2_RB0_conv_dw_bias": "bias__embedded_encoder2_ResidualBlock_0_body_conv_dw_bias",
    "encoder2_RB0_pw_expand_weight": f"embedded__encoder2_ResidualBlock_0_body_conv_pw_expand_weight{Q}",
    "encoder2_RB0_pw_expand_bias": "bias__embedded_encoder2_ResidualBlock_0_body_conv_pw_expand_bias",
    "encoder2_RB0_pw_contract_weight": f"embedded__encoder2_ResidualBlock_0_body_conv_pw_contract_weight{Q}",
    "encoder2_RB0_pw_contract_bias": "bias__embedded_encoder2_ResidualBlock_0_body_conv_pw_contract_bias",
    "encoder2_RB1_conv_dw_weight": f"embedded__encoder2_ResidualBlock_1_body_conv_dw_weight{Q}",
    "encoder2_RB1_conv_dw_bias": "bias__embedded_encoder2_ResidualBlock_1_body_conv_dw_bias",
    "encoder2_RB1_pw_expand_weight": f"embedded__encoder2_ResidualBlock_1_body_conv_pw_expand_weight{Q}",
    "encoder2_RB1_pw_expand_bias": "bias__embedded_encoder2_ResidualBlock_1_body_conv_pw_expand_bias",
    "encoder2_RB1_pw_contract_weight": f"embedded__encoder2_ResidualBlock_1_body_conv_pw_contract_weight{Q}",
    "encoder2_RB1_pw_contract_bias": "bias__embedded_encoder2_ResidualBlock_1_body_conv_pw_contract_bias",
    "enc2_ds_weight": f"embedded__encoder2_DownscaleStridedConv2x2_downscale_conv_weight{Q}",
    "enc2_ds_bias": "bias__embedded_encoder2_DownscaleStridedConv2x2_downscale_conv_bias",
    "encoder3_ResidualBlock_0_spatial_weight": f"embedded__encoder3_ResidualBlock_0_body_spatial_mixing_partial_conv_weight{Q}",
    "encoder3_ResidualBlock_0_spatial_bias": "bias__embedded_encoder3_ResidualBlock_0_body_spatial_mixing_partial_conv_bias",
    "encoder3_ResidualBlock_0_pw_expand_weight": f"embedded__encoder3_ResidualBlock_0_body_pw_expand_weight{Q}",
    "encoder3_ResidualBlock_0_pw_expand_bias": "bias__embedded_encoder3_ResidualBlock_0_body_pw_expand_bias",
    "encoder3_ResidualBlock_0_pw_contract_weight": f"embedded__encoder3_ResidualBlock_0_body_pw_contract_weight{Q}",
    "encoder3_ResidualBlock_0_pw_contract_bias": "bias__embedded_encoder3_ResidualBlock_0_body_pw_contract_bias",
}
SCALE_RAW_KEYS = {
    "encoder2_RB0_conv_dw": RAW_BINDINGS["encoder2_RB0_conv_dw_weight"],
    "encoder2_RB0_pw_expand": RAW_BINDINGS["encoder2_RB0_pw_expand_weight"],
    "encoder2_RB0_pw_contract": RAW_BINDINGS["encoder2_RB0_pw_contract_weight"],
    "encoder2_RB1_conv_dw": RAW_BINDINGS["encoder2_RB1_conv_dw_weight"],
    "encoder2_RB1_pw_expand": RAW_BINDINGS["encoder2_RB1_pw_expand_weight"],
    "encoder2_RB1_pw_contract": RAW_BINDINGS["encoder2_RB1_pw_contract_weight"],
    "enc2_ds": RAW_BINDINGS["enc2_ds_weight"],
    "encoder3_ResidualBlock_0_spatial": RAW_BINDINGS["encoder3_ResidualBlock_0_spatial_weight"],
    "encoder3_ResidualBlock_0_pw_expand": RAW_BINDINGS["encoder3_ResidualBlock_0_pw_expand_weight"],
    "encoder3_ResidualBlock_0_pw_contract": RAW_BINDINGS["encoder3_ResidualBlock_0_pw_contract_weight"],
}


class CpuReferenceError(Exception):
    """The selected F02a inputs or bound sources do not satisfy the contract."""


def fixed_input(manifest: dict[str, Any]) -> dict[str, Any]:
    contract = manifest["fixed_input"]
    if contract["shape"] != [8, 8, 16] or contract["dtype"] != "int8":
        raise CpuReferenceError("F02a requires the fixed 8x8x16 signed-int8 input")
    values = np.fromiter(
        (((index * 37 + 11) % 255) - 127 for index in range(8 * 8 * 16)),
        dtype=np.int8,
        count=8 * 8 * 16,
    ).reshape(8, 8, 16)
    return {"q": values, "s": F32(contract["scale"])}


def direct_input(pass_id: str) -> dict[str, Any]:
    """Create a pass-local deterministic input without invoking an earlier pass."""
    try:
        spec = DIRECT_INPUT_SPECS[pass_id]
    except KeyError as exc:
        raise CpuReferenceError(f"F02a has no direct input for {pass_id}") from exc
    shape = spec["shape"]
    count = int(np.prod(shape))
    values = np.fromiter(
        (((index * spec["multiplier"] + spec["offset"]) % 255) - 127 for index in range(count)),
        dtype=np.int8,
        count=count,
    ).reshape(shape)
    scales = spec["scales"]
    if len(scales) == 1:
        return {"q": values, "s": scales[0]}
    return {"q": values, "s0": scales[0], "s1": scales[1]}


def tensor_scales(value: dict[str, Any]) -> tuple[np.float32, ...]:
    if "s" in value:
        return (F32(value["s"]),)
    if "s0" in value and "s1" in value:
        return (F32(value["s0"]), F32(value["s1"]))
    raise CpuReferenceError("tensor scale metadata is missing")


def validate_contract_scales(contract: dict[str, Any]) -> None:
    passes = contract.get("passes")
    if not isinstance(passes, list) or [entry.get("pass_id") for entry in passes if isinstance(entry, dict)] != ["p1", "p2", "p3", "p4"]:
        raise CpuReferenceError("F02a contract pass order is invalid")
    for entry in passes:
        observed = entry.get("scales")
        expected = EXPECTED_OUTPUT_SCALES[entry["pass_id"]]
        if (not isinstance(observed, list) or len(observed) != len(expected)
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in observed)
                or any(F32(value).tobytes() != target.tobytes() for value, target in zip(observed, expected))):
            raise CpuReferenceError(f"F02a contract output scales mismatch: {entry['pass_id']}")
        direct = entry.get("direct_input")
        if not isinstance(direct, dict) or direct.get("scales") != [float(value) for value in DIRECT_INPUT_SPECS[entry["pass_id"]]["scales"]]:
            raise CpuReferenceError(f"F02a contract direct input scales mismatch: {entry['pass_id']}")


def load_bound_layers(
    manifest: dict[str, Any], p7_directory: Path, simulator: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load P7 arrays/graph from the same immutable snapshot used for simulator code."""
    namespace, payloads = load_bound_simulator_snapshot(manifest, p7_directory, simulator)
    namespace["ART"] = p7_directory
    try:
        with np.load(BytesIO(payloads["weights"]), allow_pickle=False) as archive:
            raw = {name: archive[name] for name in archive.files}
        graph = json.loads(payloads["graph"].decode("utf-8"))
    except (OSError, ValueError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CpuReferenceError(f"cannot decode authenticated P7 snapshot: {exc}") from exc
    layers: dict[str, Any] = {alias: raw[name] for alias, name in RAW_BINDINGS.items()}
    layers["_raw"] = raw
    layers["_calls"] = graph["calls"]
    for alias, expected in WEIGHT_SCALES.items():
        raw_name = SCALE_RAW_KEYS[alias]
        observed = graph["decls"].get(raw_name, {}).get("scale")
        if observed is None or F32(observed).tobytes() != expected.tobytes():
            raise CpuReferenceError(f"P7 graph scale mismatch: {raw_name}")
        layers[f"scale__{alias}"] = expected
    return layers, namespace


def _round_half_away(values: np.ndarray) -> np.ndarray:
    # Widen before adding 0.5: float32 addition incorrectly promotes the value
    # immediately below a half-integer onto the tie on some inputs.
    widened = np.asarray(values, dtype=np.float64)
    return (np.sign(widened) * np.floor(np.abs(widened) + 0.5)).astype(np.int64)


def _quantize(values: np.ndarray, *, relu: bool = False) -> np.ndarray:
    low = 0 if relu else -128
    return np.clip(_round_half_away(values), low, 127).astype(np.int8)


def _conv2d(x: np.ndarray, weight: np.ndarray, *, stride: int = 1, pad: int = 0) -> np.ndarray:
    height, width, channels = x.shape
    outputs, weight_channels, kernel_h, kernel_w = weight.shape
    if weight_channels != channels:
        raise CpuReferenceError("regular convolution channel mismatch")
    padded = np.zeros((height + 2 * pad, width + 2 * pad, channels), dtype=np.int32)
    padded[pad:pad + height, pad:pad + width] = x
    out_h = (height + 2 * pad - kernel_h) // stride + 1
    out_w = (width + 2 * pad - kernel_w) // stride + 1
    accumulator = np.zeros((out_h, out_w, outputs), dtype=np.int64)
    for kernel_y in range(kernel_h):
        for kernel_x in range(kernel_w):
            patch = padded[
                kernel_y:kernel_y + stride * out_h:stride,
                kernel_x:kernel_x + stride * out_w:stride,
                :,
            ]
            product = patch.reshape(-1, channels) @ weight[:, :, kernel_y, kernel_x].astype(np.int32).T
            accumulator += product.reshape(out_h, out_w, outputs).astype(np.int64)
    return accumulator


def _convnext_vector(
    x: dict[str, Any], layers: dict[str, Any], arguments: list[float], output_scale: np.float32, prefix: str
) -> dict[str, Any]:
    rcpr0, middle_scale, rcpr1, contract_scale = map(F32, arguments)
    accumulator = _conv2d(x["q"], layers[f"{prefix}_conv_dw_weight"], pad=1)
    values = (accumulator.astype(F32) * (F32(x["s"]) * F32(layers[f"scale__{prefix}_conv_dw"]))
              + layers[f"{prefix}_conv_dw_bias"]) * rcpr0
    quantized = _quantize(values)
    accumulator = _conv2d(quantized, layers[f"{prefix}_pw_expand_weight"])
    values = (accumulator.astype(F32) * (middle_scale * F32(layers[f"scale__{prefix}_pw_expand"]))
              + layers[f"{prefix}_pw_expand_bias"]) * rcpr1
    quantized = _quantize(values, relu=True)
    accumulator = _conv2d(quantized, layers[f"{prefix}_pw_contract_weight"])
    values = accumulator.astype(F32) * (F32(layers[f"scale__{prefix}_pw_contract"]) * contract_scale)
    values += layers[f"{prefix}_pw_contract_bias"]
    values += x["q"].astype(F32) * F32(x["s"])
    return {"q": _quantize(values * (F32(1.0) / output_scale)), "s": output_scale}


def _downscale_vector(
    x: dict[str, Any], layers: dict[str, Any], arguments: list[float]
) -> dict[str, Any]:
    output0, output1 = map(F32, arguments)
    accumulator = _conv2d(x["q"], layers["enc2_ds_weight"], stride=2)
    values = accumulator.astype(F32) * F32(layers["scale__enc2_ds"]) * F32(x["s"])
    values += layers["enc2_ds_bias"]
    result = np.empty(accumulator.shape, dtype=np.int8)
    midpoint = accumulator.shape[2] // 2
    result[:, :, :midpoint] = _quantize(values[:, :, :midpoint] * (F32(1.0) / output0))
    result[:, :, midpoint:] = _quantize(values[:, :, midpoint:] * (F32(1.0) / output1))
    return {"q": result, "s0": output0, "s1": output1}


def _fasternet32_vector(
    x: dict[str, Any], layers: dict[str, Any], arguments: list[float]
) -> dict[str, Any]:
    input0, input1, activation, output0, output1 = map(F32, arguments)
    prefix = "encoder3_ResidualBlock_0"
    channels = x["q"].shape[2]
    accumulator = _conv2d(x["q"][:, :, :channels // 2], layers[f"{prefix}_spatial_weight"], pad=1)
    values = accumulator.astype(F32) * (input0 * F32(layers[f"scale__{prefix}_spatial"]))
    values += layers[f"{prefix}_spatial_bias"]
    convolved = _quantize(values * (F32(1.0) / input1))
    concatenated = np.concatenate([convolved, x["q"][:, :, channels // 2:]], axis=2)
    accumulator = _conv2d(concatenated, layers[f"{prefix}_pw_expand_weight"])
    values = accumulator.astype(F32) * input1 * F32(layers[f"scale__{prefix}_pw_expand"])
    values += layers[f"{prefix}_pw_expand_bias"]
    activated = _quantize(values * (F32(1.0) / activation), relu=True)
    accumulator = _conv2d(activated, layers[f"{prefix}_pw_contract_weight"])
    values = accumulator.astype(F32) * F32(layers[f"scale__{prefix}_pw_contract"]) * activation
    values += layers[f"{prefix}_pw_contract_bias"]
    result = np.empty(values.shape, dtype=np.int8)
    first = values[:, :, :channels // 2] + x["q"][:, :, :channels // 2].astype(F32) * input0
    second = values[:, :, channels // 2:] + x["q"][:, :, channels // 2:].astype(F32) * input1
    result[:, :, :channels // 2] = _quantize(first * (F32(1.0) / output0))
    result[:, :, channels // 2:] = _quantize(second * (F32(1.0) / output1))
    return {"q": result, "s0": output0, "s1": output1}


def run_vector_pass(pass_id: str, value: dict[str, Any], layers: dict[str, Any]) -> dict[str, Any]:
    calls = layers["_calls"]
    if pass_id == "p1":
        return _convnext_vector(value, layers, calls[0]["args"], P1_OUTPUT_SCALE, "encoder2_RB0")
    if pass_id == "p2":
        return _convnext_vector(value, layers, calls[1]["args"], P2_OUTPUT_SCALE, "encoder2_RB1")
    if pass_id == "p3":
        return _downscale_vector(value, layers, calls[2]["args"])
    if pass_id == "p4":
        return _fasternet32_vector(value, layers, calls[3]["args"])
    raise CpuReferenceError(f"F02a does not implement {pass_id}")


def run_vector(manifest: dict[str, Any], layers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = fixed_input(manifest)
    outputs: dict[str, dict[str, Any]] = {}
    for pass_id in ("p1", "p2", "p3", "p4"):
        value = run_vector_pass(pass_id, value, layers)
        outputs[pass_id] = value
    return outputs


def _scalar_conv(x: np.ndarray, weight: np.ndarray, *, stride: int = 1, pad: int = 0) -> np.ndarray:
    height, width, channels = x.shape
    outputs, weight_channels, kernel_h, kernel_w = weight.shape
    if weight_channels != channels:
        raise CpuReferenceError("scalar convolution channel mismatch")
    out_h = (height + 2 * pad - kernel_h) // stride + 1
    out_w = (width + 2 * pad - kernel_w) // stride + 1
    result = np.zeros((out_h, out_w, outputs), dtype=np.int64)
    for out_y in range(out_h):
        for out_x in range(out_w):
            for out_channel in range(outputs):
                total = 0
                for kernel_y in range(kernel_h):
                    in_y = out_y * stride + kernel_y - pad
                    if not 0 <= in_y < height:
                        continue
                    for kernel_x in range(kernel_w):
                        in_x = out_x * stride + kernel_x - pad
                        if not 0 <= in_x < width:
                            continue
                        for in_channel in range(channels):
                            total += int(x[in_y, in_x, in_channel]) * int(weight[out_channel, in_channel, kernel_y, kernel_x])
                result[out_y, out_x, out_channel] = total
    return result


def _scalar_quantize(value: np.float32, *, relu: bool = False) -> np.int8:
    numeric = float(value)
    rounded = int(np.floor(abs(numeric) + 0.5)) * (-1 if numeric < 0 else 1)
    return np.int8(min(127, max(0 if relu else -128, rounded)))


def _scalar_requantize(values: np.ndarray, multiplier: np.float32, *, relu: bool = False) -> np.ndarray:
    result = np.empty(values.shape, dtype=np.int8)
    for index in np.ndindex(values.shape):
        result[index] = _scalar_quantize(F32(values[index]) * multiplier, relu=relu)
    return result


def _raw(layers: dict[str, Any], alias: str) -> np.ndarray:
    return layers["_raw"][RAW_BINDINGS[alias]]


def _convnext_scalar(
    x: dict[str, Any], layers: dict[str, Any], arguments: list[float], output_scale: np.float32, prefix: str
) -> dict[str, Any]:
    rcpr0, middle_scale, rcpr1, contract_scale = map(F32, arguments)
    accumulator = _scalar_conv(x["q"], _raw(layers, f"{prefix}_conv_dw_weight"), pad=1)
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        values[index] = (F32(accumulator[index]) * (F32(x["s"]) * WEIGHT_SCALES[f"{prefix}_conv_dw"])
                         + F32(_raw(layers, f"{prefix}_conv_dw_bias")[channel]))
    quantized = _scalar_requantize(values, rcpr0)
    accumulator = _scalar_conv(quantized, _raw(layers, f"{prefix}_pw_expand_weight"))
    for index in np.ndindex(accumulator.shape):
        channel = index[2]
        values_index = F32(accumulator[index]) * (middle_scale * WEIGHT_SCALES[f"{prefix}_pw_expand"])
        values_index += F32(_raw(layers, f"{prefix}_pw_expand_bias")[channel])
        accumulator[index] = int(_scalar_quantize(values_index * rcpr1, relu=True))
    quantized = accumulator.astype(np.int8)
    accumulator = _scalar_conv(quantized, _raw(layers, f"{prefix}_pw_contract_weight"))
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        current = F32(accumulator[index]) * (WEIGHT_SCALES[f"{prefix}_pw_contract"] * contract_scale)
        current += F32(_raw(layers, f"{prefix}_pw_contract_bias")[channel])
        current += F32(x["q"][index]) * F32(x["s"])
        values[index] = current
    return {"q": _scalar_requantize(values, F32(1.0) / output_scale), "s": output_scale}


def _downscale_scalar(x: dict[str, Any], layers: dict[str, Any], arguments: list[float]) -> dict[str, Any]:
    output0, output1 = map(F32, arguments)
    accumulator = _scalar_conv(x["q"], _raw(layers, "enc2_ds_weight"), stride=2)
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        current = F32(accumulator[index]) * WEIGHT_SCALES["enc2_ds"] * F32(x["s"])
        values[index] = current + F32(_raw(layers, "enc2_ds_bias")[channel])
    midpoint = values.shape[2] // 2
    result = np.empty(values.shape, dtype=np.int8)
    result[:, :, :midpoint] = _scalar_requantize(values[:, :, :midpoint], F32(1.0) / output0)
    result[:, :, midpoint:] = _scalar_requantize(values[:, :, midpoint:], F32(1.0) / output1)
    return {"q": result, "s0": output0, "s1": output1}


def _fasternet32_scalar(x: dict[str, Any], layers: dict[str, Any], arguments: list[float]) -> dict[str, Any]:
    input0, input1, activation, output0, output1 = map(F32, arguments)
    prefix = "encoder3_ResidualBlock_0"
    channels = x["q"].shape[2]
    accumulator = _scalar_conv(x["q"][:, :, :channels // 2], _raw(layers, f"{prefix}_spatial_weight"), pad=1)
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        current = F32(accumulator[index]) * (input0 * WEIGHT_SCALES[f"{prefix}_spatial"])
        values[index] = current + F32(_raw(layers, f"{prefix}_spatial_bias")[channel])
    convolved = _scalar_requantize(values, F32(1.0) / input1)
    concatenated = np.concatenate([convolved, x["q"][:, :, channels // 2:]], axis=2)
    accumulator = _scalar_conv(concatenated, _raw(layers, f"{prefix}_pw_expand_weight"))
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        current = F32(accumulator[index]) * input1 * WEIGHT_SCALES[f"{prefix}_pw_expand"]
        values[index] = current + F32(_raw(layers, f"{prefix}_pw_expand_bias")[channel])
    activated = _scalar_requantize(values, F32(1.0) / activation, relu=True)
    accumulator = _scalar_conv(activated, _raw(layers, f"{prefix}_pw_contract_weight"))
    values = np.empty(accumulator.shape, dtype=F32)
    for index in np.ndindex(values.shape):
        channel = index[2]
        current = F32(accumulator[index]) * WEIGHT_SCALES[f"{prefix}_pw_contract"] * activation
        values[index] = current + F32(_raw(layers, f"{prefix}_pw_contract_bias")[channel])
    midpoint = channels // 2
    result = np.empty(values.shape, dtype=np.int8)
    first = values[:, :, :midpoint] + x["q"][:, :, :midpoint].astype(F32) * input0
    second = values[:, :, midpoint:] + x["q"][:, :, midpoint:].astype(F32) * input1
    result[:, :, :midpoint] = _scalar_requantize(first, F32(1.0) / output0)
    result[:, :, midpoint:] = _scalar_requantize(second, F32(1.0) / output1)
    return {"q": result, "s0": output0, "s1": output1}


def run_scalar_pass(pass_id: str, value: dict[str, Any], layers: dict[str, Any]) -> dict[str, Any]:
    calls = layers["_calls"]
    if pass_id == "p1":
        return _convnext_scalar(value, layers, calls[0]["args"], P1_OUTPUT_SCALE, "encoder2_RB0")
    if pass_id == "p2":
        return _convnext_scalar(value, layers, calls[1]["args"], P2_OUTPUT_SCALE, "encoder2_RB1")
    if pass_id == "p3":
        return _downscale_scalar(value, layers, calls[2]["args"])
    if pass_id == "p4":
        return _fasternet32_scalar(value, layers, calls[3]["args"])
    raise CpuReferenceError(f"F02a scalar oracle does not implement {pass_id}")


def run_scalar_oracle(manifest: dict[str, Any], layers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = fixed_input(manifest)
    outputs: dict[str, dict[str, Any]] = {}
    for pass_id in ("p1", "p2", "p3", "p4"):
        value = run_scalar_pass(pass_id, value, layers)
        outputs[pass_id] = value
    return outputs

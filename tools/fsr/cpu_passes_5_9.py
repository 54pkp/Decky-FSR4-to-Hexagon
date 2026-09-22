#!/usr/bin/env python3
"""F02b CPU references and independent scalar oracles for FSR passes 5-9."""

from __future__ import annotations

from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from tools.fsr.cpu_passes_1_4 import F32, _quantize, _scalar_quantize, tensor_scales
from tools.fsr.pass_manifest import load_bound_simulator_snapshot


P5_OUTPUT_SCALE = F32(0.019347405061125755)
WEIGHT_SCALES = {
    "encoder3_ResidualBlock_1_spatial": F32(0.005069198086857796),
    "encoder3_ResidualBlock_1_pw_expand": F32(0.003858785377815366),
    "encoder3_ResidualBlock_1_pw_contract": F32(0.0038207604084163904),
    "enc3_ds": F32(0.0031457620207220316),
    "bottleneck_ResidualBlock_0_spatial": F32(0.005512189585715532),
    "bottleneck_ResidualBlock_0_pw_expand": F32(0.005283745471388102),
    "bottleneck_ResidualBlock_0_pw_contract": F32(0.005271106027066708),
    "bottleneck_ResidualBlock_1_spatial": F32(0.0033285829704254866),
    "bottleneck_ResidualBlock_1_pw_expand": F32(0.005735259968787432),
    "bottleneck_ResidualBlock_1_pw_contract": F32(0.005727430339902639),
    "bottleneck_ResidualBlock_2_spatial": F32(0.0035890890285372734),
    "bottleneck_ResidualBlock_2_pw_expand": F32(0.006621810141950846),
    "bottleneck_ResidualBlock_2_pw_contract": F32(0.006558050401508808),
    "bottleneck_ct": F32(0.003301001852378249),
}
Q = "_quant_export_handler_QuantizeLinear_output_0"
RAW_BINDINGS = {
    "encoder3_ResidualBlock_1_spatial_weight": f"embedded__encoder3_ResidualBlock_1_body_spatial_mixing_partial_conv_weight{Q}",
    "encoder3_ResidualBlock_1_spatial_bias": "bias__embedded_encoder3_ResidualBlock_1_body_spatial_mixing_partial_conv_bias",
    "encoder3_ResidualBlock_1_pw_expand_weight": f"embedded__encoder3_ResidualBlock_1_body_pw_expand_weight{Q}",
    "encoder3_ResidualBlock_1_pw_expand_bias": "bias__embedded_encoder3_ResidualBlock_1_body_pw_expand_bias",
    "encoder3_ResidualBlock_1_pw_contract_weight": f"embedded__encoder3_ResidualBlock_1_body_pw_contract_weight{Q}",
    "encoder3_ResidualBlock_1_pw_contract_bias": "bias__embedded_encoder3_ResidualBlock_1_body_pw_contract_bias",
    "enc3_ds_weight": "encoder3_downscale_conv_w",
    "enc3_ds_bias": "bias__embedded_encoder3_DownscaleStridedConv2x2_downscale_conv_bias",
    "bottleneck_ResidualBlock_0_spatial_weight": "bottleneck_rb0_spatial_w",
    "bottleneck_ResidualBlock_0_spatial_bias": "bias__embedded_bottleneck_ResidualBlock_0_body_spatial_mixing_partial_conv_bias",
    "bottleneck_ResidualBlock_0_pw_expand_weight": "bottleneck_rb0_pw_expand_w",
    "bottleneck_ResidualBlock_0_pw_expand_bias": "bias__embedded_bottleneck_ResidualBlock_0_body_pw_expand_bias",
    "bottleneck_ResidualBlock_0_pw_contract_weight": "bottleneck_rb0_pw_contract_w",
    "bottleneck_ResidualBlock_0_pw_contract_bias": "bias__embedded_bottleneck_ResidualBlock_0_body_pw_contract_bias",
    "bottleneck_ResidualBlock_1_spatial_weight": "bottleneck_rb1_spatial_w",
    "bottleneck_ResidualBlock_1_spatial_bias": "bias__embedded_bottleneck_ResidualBlock_1_body_spatial_mixing_partial_conv_bias",
    "bottleneck_ResidualBlock_1_pw_expand_weight": "bottleneck_rb1_pw_expand_w",
    "bottleneck_ResidualBlock_1_pw_expand_bias": "bias__embedded_bottleneck_ResidualBlock_1_body_pw_expand_bias",
    "bottleneck_ResidualBlock_1_pw_contract_weight": "bottleneck_rb1_pw_contract_w",
    "bottleneck_ResidualBlock_1_pw_contract_bias": "bias__embedded_bottleneck_ResidualBlock_1_body_pw_contract_bias",
    "bottleneck_ResidualBlock_2_spatial_weight": "bottleneck_rb2_spatial_w",
    "bottleneck_ResidualBlock_2_spatial_bias": "bias__embedded_bottleneck_ResidualBlock_2_body_spatial_mixing_partial_conv_bias",
    "bottleneck_ResidualBlock_2_pw_expand_weight": "bottleneck_rb2_pw_expand_w",
    "bottleneck_ResidualBlock_2_pw_expand_bias": "bias__embedded_bottleneck_ResidualBlock_2_body_pw_expand_bias",
    "bottleneck_ResidualBlock_2_pw_contract_weight": "bottleneck_rb2_pw_contract_w",
    "bottleneck_ResidualBlock_2_pw_contract_bias": "bias__embedded_bottleneck_ResidualBlock_2_body_pw_contract_bias",
    "bottleneck_ct_weight": "bottleneck_upscale_convT_w",
    "bottleneck_ct_bias": "bias__embedded_bottleneck_UpscaleConvTranspose2x2_upscale_conv_bias",
}
EXPECTED_OUTPUT_SCALES = {
    "p5": (P5_OUTPUT_SCALE,),
    "p6": (F32(0.019169600680470467), F32(0.028077777475118637)),
    "p7": (F32(0.021226389333605766), F32(0.03648017346858978)),
    "p8": (F32(0.020896881818771362), F32(0.03844049945473671)),
    "p9": (F32(0.021412165835499763), F32(0.03075222671031952)),
}
DIRECT_SPECS = {
    "p5": ((4,4,32), 59, 5, (F32(0.017191138118505478), F32(0.021955177187919617))),
    "p6": ((4,4,32), 61, 13, (P5_OUTPUT_SCALE,)),
    "p7": ((3,3,64), 67, 17, EXPECTED_OUTPUT_SCALES["p6"]),
    "p8": ((3,3,64), 71, 29, EXPECTED_OUTPUT_SCALES["p7"]),
    "p9": ((2,2,64), 73, 31, EXPECTED_OUTPUT_SCALES["p8"]),
}
P9_SKIP_SPEC = ((4,4,32), 79, 37, (P5_OUTPUT_SCALE,))
EXPECTED_DIRECT_CONTRACT = {
    "p5": ("value[i]=((i*59+5)%255)-127; C-order", "0b97d1b16025989b31321aea865ded4739c23c18ac83b6bc4a33db6db8f7488d", [4,4,32], [0.017191138118505478,0.021955177187919617], "8a11a617579574b01760e1cec11d89411e00925b83875d9f721d1bce44949bac"),
    "p6": ("value[i]=((i*61+13)%255)-127; C-order", "5fc4ec4c34b5477c4aabdc17fea9100433c6aac282551600942f6c1b537f5ce8", [4,4,32], [0.019347405061125755], "a0b1b273d1dcb02f03d39b96a16bed1e9a6d4ff011dfe3986b512f5684619d11"),
    "p7": ("value[i]=((i*67+17)%255)-127; C-order", "3fb19d6383763d268d22ea9fd1c8196c6368ae923de0346e57ab988767c2e7fd", [3,3,64], [0.019169600680470467,0.028077777475118637], "c943663bbeb77a91a9c834e7948d8964550348a07b5dfbf24db91fecd912a5e8"),
    "p8": ("value[i]=((i*71+29)%255)-127; C-order", "3c6ee923d0f8c7ad1833a1a908423527dcdf4c0a638f73a480fb33be7a88e5b8", [3,3,64], [0.021226389333605766,0.03648017346858978], "df9b30cdd3b4f0c218e6e39d5384d41d25188e356306e19f7b21b3b7582e2767"),
    "p9": ("value[i]=((i*73+31)%255)-127; C-order", "2fcc646d3bc374b699745f824c6afef6e1e4ced2e9d2a716396a922641b9d201", [2,2,64], [0.020896881818771362,0.03844049945473671], "5902e767b360672237156401edbbce64b744a3eef180a48edcadd46f122c6d15"),
}
EXPECTED_P9_SKIP = ("value[i]=((i*79+37)%255)-127; C-order", "d75600ff62ef845ac46b978b56ed96bbb4765b3062f4664c322a94e97eea6277", [4,4,32], [0.019347405061125755])
EXPECTED_DIRECT_OUTPUT_SHAPES = {"p5":[4,4,32],"p6":[2,2,64],"p7":[3,3,64],"p8":[3,3,64],"p9":[4,4,32]}
BIN_SPECS = {
    "enc3_ds_weight": ("bin_raw__encoder3_downscale_conv_w", (64,2,2,32), (0,3,1,2)),
    "bottleneck_ResidualBlock_0_spatial_weight": ("bin_raw__bottleneck_rb0_spatial_w", (32,3,3,16), (0,3,1,2)),
    "bottleneck_ResidualBlock_0_pw_expand_weight": ("bin_raw__bottleneck_rb0_pw_expand_w", (128,1,1,64), (0,3,1,2)),
    "bottleneck_ResidualBlock_0_pw_contract_weight": ("bin_raw__bottleneck_rb0_pw_contract_w", (64,1,1,128), (0,3,1,2)),
    "bottleneck_ResidualBlock_1_spatial_weight": ("bin_raw__bottleneck_rb1_spatial_w", (32,3,3,16), (0,3,1,2)),
    "bottleneck_ResidualBlock_1_pw_expand_weight": ("bin_raw__bottleneck_rb1_pw_expand_w", (128,1,1,64), (0,3,1,2)),
    "bottleneck_ResidualBlock_1_pw_contract_weight": ("bin_raw__bottleneck_rb1_pw_contract_w", (64,1,1,128), (0,3,1,2)),
    "bottleneck_ResidualBlock_2_spatial_weight": ("bin_raw__bottleneck_rb2_spatial_w", (32,3,3,16), (0,3,1,2)),
    "bottleneck_ResidualBlock_2_pw_expand_weight": ("bin_raw__bottleneck_rb2_pw_expand_w", (128,1,1,64), (0,3,1,2)),
    "bottleneck_ResidualBlock_2_pw_contract_weight": ("bin_raw__bottleneck_rb2_pw_contract_w", (64,1,1,128), (0,3,1,2)),
    "bottleneck_ct_weight": ("bin_raw__bottleneck_upscale_convT_w", (2,2,32,64), (3,2,0,1)),
}


class CpuReferenceError(Exception):
    pass


def _generated(spec: tuple[Any, ...]) -> dict[str, Any]:
    shape, multiplier, offset, scales = spec
    count = int(np.prod(shape))
    q = np.fromiter((((i * multiplier + offset) % 255) - 127 for i in range(count)), dtype=np.int8, count=count).reshape(shape)
    if len(scales) == 1:
        return {"q": q, "s": scales[0]}
    return {"q": q, "s0": scales[0], "s1": scales[1]}


def direct_inputs(pass_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if pass_id not in DIRECT_SPECS:
        raise CpuReferenceError(f"F02b has no direct input for {pass_id}")
    return _generated(DIRECT_SPECS[pass_id]), _generated(P9_SKIP_SPEC) if pass_id == "p9" else None


def load_bound_layers(manifest: dict[str, Any], p7: Path, simulator: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    namespace, payloads = load_bound_simulator_snapshot(manifest, p7, simulator)
    namespace["ART"] = p7
    try:
        with np.load(BytesIO(payloads["weights"]), allow_pickle=False) as archive:
            raw = {name: archive[name] for name in archive.files}
        graph = json.loads(payloads["graph"].decode("utf-8"))
    except (OSError, ValueError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CpuReferenceError(f"cannot decode authenticated P7 snapshot: {exc}") from exc
    layers: dict[str, Any] = {alias: raw[name] for alias, name in RAW_BINDINGS.items()}
    layers["_raw"], layers["_calls"] = raw, graph["calls"]
    scalar_raw = {}
    for alias, (raw_name, storage_shape, axes) in BIN_SPECS.items():
        rebuilt = raw[raw_name].view(np.int8).reshape(storage_shape).transpose(axes)
        if not np.array_equal(rebuilt, layers[alias]):
            raise CpuReferenceError(f"bin raw/logical-stride alias mismatch: {alias}")
        scalar_raw[alias] = rebuilt
    layers["_scalar_raw"] = scalar_raw
    embedded = ("encoder3_ResidualBlock_1_spatial", "encoder3_ResidualBlock_1_pw_expand", "encoder3_ResidualBlock_1_pw_contract")
    for alias in embedded:
        observed = graph["decls"][RAW_BINDINGS[f"{alias}_weight"]]["scale"]
        if F32(observed).tobytes() != WEIGHT_SCALES[alias].tobytes():
            raise CpuReferenceError(f"P7 graph scale mismatch: {alias}")
    scale_indices = {"enc3_ds": 28, "bottleneck_ResidualBlock_0_spatial": 31, "bottleneck_ResidualBlock_0_pw_expand": 32,
                     "bottleneck_ResidualBlock_0_pw_contract": 34, "bottleneck_ResidualBlock_1_spatial": 37,
                     "bottleneck_ResidualBlock_1_pw_expand": 38, "bottleneck_ResidualBlock_1_pw_contract": 40,
                     "bottleneck_ResidualBlock_2_spatial": 43, "bottleneck_ResidualBlock_2_pw_expand": 44,
                     "bottleneck_ResidualBlock_2_pw_contract": 46, "bottleneck_ct": 48}
    for alias, index in scale_indices.items():
        if F32(graph["scale_table"][index]).tobytes() != WEIGHT_SCALES[alias].tobytes():
            raise CpuReferenceError(f"P7 scale-table mismatch: {alias}")
    for alias, scale in WEIGHT_SCALES.items():
        layers[f"scale__{alias}"] = scale
    return layers, namespace


def _conv(x: np.ndarray, w: np.ndarray, *, stride: int = 1, pad: int = 0, groups: int = 1) -> np.ndarray:
    h, width, channels = x.shape; outputs, group_channels, kh, kw = w.shape
    if group_channels * groups != channels or outputs % groups:
        raise CpuReferenceError("grouped convolution shape mismatch")
    padded = np.zeros((h + 2*pad, width + 2*pad, channels), np.int32)
    padded[pad:pad+h, pad:pad+width] = x
    oh, ow = (h + 2*pad - kh)//stride + 1, (width + 2*pad - kw)//stride + 1
    result = np.zeros((oh, ow, outputs), np.int64); outputs_per_group = outputs // groups
    for ky in range(kh):
        for kx in range(kw):
            patch = padded[ky:ky+stride*oh:stride, kx:kx+stride*ow:stride]
            for group in range(groups):
                ins = slice(group*group_channels, (group+1)*group_channels)
                outs = slice(group*outputs_per_group, (group+1)*outputs_per_group)
                product = patch[:,:,ins].reshape(-1, group_channels) @ w[outs,:,ky,kx].astype(np.int32).T
                result[:,:,outs] += product.reshape(oh, ow, outputs_per_group)
    return result


def _transpose(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    h, width, channels = x.shape; outputs = w.shape[1]
    if w.ndim != 4 or w.shape[0] != channels or w.shape[2:] != (2, 2):
        raise CpuReferenceError("transposed convolution requires IOHW [Cin,Cout,2,2]")
    result = np.zeros((2*h, 2*width, outputs), np.int64)
    for ky in range(2):
        for kx in range(2):
            product = x.astype(np.int32).reshape(-1, channels) @ w[:,:,ky,kx].astype(np.int32)
            result[ky::2,kx::2] = product.reshape(h, width, outputs)
    return result


def _fnb_vector(x: dict[str, Any], layers: dict[str, Any], prefix: str, args: list[float], *, variant: int, uniform: float | None = None, ct_order: bool = False) -> dict[str, Any]:
    q0, q1, activation = map(F32, args[:3]); channels = x["q"].shape[2]; groups = 2 if variant == 64 else 1
    acc = _conv(x["q"][:,:,:channels//2], layers[f"{prefix}_spatial_weight"], pad=1, groups=groups)
    scale0 = q0 * WEIGHT_SCALES[f"{prefix}_spatial"] if (variant == 32 or ct_order) else None
    values = acc.astype(F32) * scale0 if scale0 is not None else acc.astype(F32) * q0 * WEIGHT_SCALES[f"{prefix}_spatial"]
    values += layers[f"{prefix}_spatial_bias"]
    partial = _quantize(values * (F32(1.0)/q1))
    concat = np.concatenate([partial, x["q"][:,:,channels//2:]], axis=2)
    acc = _conv(concat, layers[f"{prefix}_pw_expand_weight"])
    values = acc.astype(F32) * (q1 * WEIGHT_SCALES[f"{prefix}_pw_expand"]) if ct_order else acc.astype(F32) * q1 * WEIGHT_SCALES[f"{prefix}_pw_expand"]
    values += layers[f"{prefix}_pw_expand_bias"]
    activated = _quantize(values * (F32(1.0)/activation), relu=True)
    acc = _conv(activated, layers[f"{prefix}_pw_contract_weight"])
    values = acc.astype(F32) * (WEIGHT_SCALES[f"{prefix}_pw_contract"] * activation) if (variant == 64 or ct_order) else acc.astype(F32) * WEIGHT_SCALES[f"{prefix}_pw_contract"] * activation
    values += layers[f"{prefix}_pw_contract_bias"]
    values[:,:,:channels//2] += x["q"][:,:,:channels//2].astype(F32) * q0
    values[:,:,channels//2:] += x["q"][:,:,channels//2:].astype(F32) * q1
    if uniform is not None:
        return {"q": _quantize(values * (F32(1.0)/F32(uniform))), "s": F32(uniform)}
    o0, o1 = map(F32, args[3:5]); out = np.empty(values.shape, np.int8)
    out[:,:,:channels//2] = _quantize(values[:,:,:channels//2] * (F32(1.0)/o0))
    out[:,:,channels//2:] = _quantize(values[:,:,channels//2:] * (F32(1.0)/o1))
    return {"q": out, "s0": o0, "s1": o1}


def _downscale_vector(x: dict[str, Any], layers: dict[str, Any], args: list[float]) -> dict[str, Any]:
    o0, o1 = map(F32, args); acc = _conv(x["q"], layers["enc3_ds_weight"], stride=2)
    values = acc.astype(F32) * WEIGHT_SCALES["enc3_ds"] * F32(x["s"]) + layers["enc3_ds_bias"]
    out = np.empty(values.shape, np.int8); midpoint = values.shape[2]//2
    out[:,:,:midpoint] = _quantize(values[:,:,:midpoint] * (F32(1.0)/o0))
    out[:,:,midpoint:] = _quantize(values[:,:,midpoint:] * (F32(1.0)/o1))
    return {"q": out, "s0": o0, "s1": o1}


def _p9_vector(x: dict[str, Any], skip: dict[str, Any], layers: dict[str, Any], args: list[float]) -> dict[str, Any]:
    fnb = _fnb_vector(x, layers, "bottleneck_ResidualBlock_2", args, variant=64, uniform=args[3], ct_order=True)
    acc = _transpose(fnb["q"], layers["bottleneck_ct_weight"])
    values = acc.astype(F32) * (F32(fnb["s"]) * WEIGHT_SCALES["bottleneck_ct"]) + layers["bottleneck_ct_bias"]
    values += skip["q"].astype(F32) * F32(skip["s"])
    o0, o1 = map(F32, args[4:6]); midpoint = values.shape[2]//2; out = np.empty(values.shape, np.int8)
    out[:,:,:midpoint] = _quantize(values[:,:,:midpoint] * (F32(1.0)/o0)); out[:,:,midpoint:] = _quantize(values[:,:,midpoint:] * (F32(1.0)/o1))
    return {"q": out, "s0": o0, "s1": o1}


def run_vector_pass(pass_id: str, value: dict[str, Any], layers: dict[str, Any], skip: dict[str, Any] | None = None) -> dict[str, Any]:
    calls = layers["_calls"]
    if pass_id == "p5": return _fnb_vector(value, layers, "encoder3_ResidualBlock_1", calls[4]["args"], variant=32, uniform=P5_OUTPUT_SCALE)
    if pass_id == "p6": return _downscale_vector(value, layers, calls[5]["args"])
    if pass_id == "p7": return _fnb_vector(value, layers, "bottleneck_ResidualBlock_0", calls[6]["args"], variant=64)
    if pass_id == "p8": return _fnb_vector(value, layers, "bottleneck_ResidualBlock_1", calls[7]["args"], variant=64)
    if pass_id == "p9" and skip is not None: return _p9_vector(value, skip, layers, calls[8]["args"])
    raise CpuReferenceError(f"invalid F02b pass invocation: {pass_id}")


def run_vector(p4: dict[str, Any], layers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = {}; value = p4
    for pass_id in ("p5", "p6", "p7", "p8"):
        value = run_vector_pass(pass_id, value, layers); outputs[pass_id] = value
    outputs["p9"] = run_vector_pass("p9", value, layers, outputs["p5"])
    return outputs


def _raw(layers: dict[str, Any], alias: str) -> np.ndarray:
    if alias in layers["_scalar_raw"]:
        return layers["_scalar_raw"][alias]
    return layers["_raw"][RAW_BINDINGS[alias]]


def _scalar_conv(x: np.ndarray, w: np.ndarray, *, stride: int = 1, pad: int = 0, groups: int = 1) -> np.ndarray:
    h, width, channels = x.shape; outputs, group_channels, kh, kw = w.shape
    oh, ow = (h+2*pad-kh)//stride+1, (width+2*pad-kw)//stride+1; result = np.zeros((oh,ow,outputs), np.int64)
    outputs_per_group = outputs//groups
    for oy in range(oh):
        for ox in range(ow):
            for oc in range(outputs):
                group = oc//outputs_per_group; total = 0
                for ky in range(kh):
                    iy = oy*stride+ky-pad
                    if not 0 <= iy < h: continue
                    for kx in range(kw):
                        ix = ox*stride+kx-pad
                        if not 0 <= ix < width: continue
                        for local in range(group_channels):
                            total += int(x[iy,ix,group*group_channels+local]) * int(w[oc,local,ky,kx])
                result[oy,ox,oc] = total
    return result


def _scalar_quant_array(values: np.ndarray, multiplier: np.float32, relu: bool = False) -> np.ndarray:
    result = np.empty(values.shape, np.int8)
    for index in np.ndindex(values.shape): result[index] = _scalar_quantize(F32(values[index])*multiplier, relu=relu)
    return result


def _fnb_scalar(x: dict[str, Any], layers: dict[str, Any], prefix: str, args: list[float], *, variant: int, uniform: float | None = None, ct_order: bool = False) -> dict[str, Any]:
    q0,q1,activation = map(F32,args[:3]); channels=x["q"].shape[2]; groups=2 if variant==64 else 1
    acc=_scalar_conv(x["q"][:,:,:channels//2],_raw(layers,f"{prefix}_spatial_weight"),pad=1,groups=groups); values=np.empty(acc.shape,F32)
    for index in np.ndindex(values.shape):
        scale=q0*WEIGHT_SCALES[f"{prefix}_spatial"] if (variant==32 or ct_order) else None
        current=F32(acc[index])*scale if scale is not None else F32(acc[index])*q0*WEIGHT_SCALES[f"{prefix}_spatial"]
        values[index]=current+F32(_raw(layers,f"{prefix}_spatial_bias")[index[2]])
    partial=_scalar_quant_array(values,F32(1.0)/q1); concat=np.concatenate([partial,x["q"][:,:,channels//2:]],axis=2)
    acc=_scalar_conv(concat,_raw(layers,f"{prefix}_pw_expand_weight")); values=np.empty(acc.shape,F32)
    for index in np.ndindex(values.shape):
        current=F32(acc[index])*(q1*WEIGHT_SCALES[f"{prefix}_pw_expand"]) if ct_order else F32(acc[index])*q1*WEIGHT_SCALES[f"{prefix}_pw_expand"]
        values[index]=current+F32(_raw(layers,f"{prefix}_pw_expand_bias")[index[2]])
    activated=_scalar_quant_array(values,F32(1.0)/activation,True); acc=_scalar_conv(activated,_raw(layers,f"{prefix}_pw_contract_weight")); values=np.empty(acc.shape,F32)
    for index in np.ndindex(values.shape):
        current=F32(acc[index])*(WEIGHT_SCALES[f"{prefix}_pw_contract"]*activation) if (variant==64 or ct_order) else F32(acc[index])*WEIGHT_SCALES[f"{prefix}_pw_contract"]*activation
        current+=F32(_raw(layers,f"{prefix}_pw_contract_bias")[index[2]])
        current+=F32(x["q"][index])* (q0 if index[2]<channels//2 else q1); values[index]=current
    if uniform is not None: return {"q":_scalar_quant_array(values,F32(1.0)/F32(uniform)),"s":F32(uniform)}
    o0,o1=map(F32,args[3:5]); midpoint=channels//2; out=np.empty(values.shape,np.int8)
    out[:,:,:midpoint]=_scalar_quant_array(values[:,:,:midpoint],F32(1.0)/o0); out[:,:,midpoint:]=_scalar_quant_array(values[:,:,midpoint:],F32(1.0)/o1)
    return {"q":out,"s0":o0,"s1":o1}


def _downscale_scalar(x: dict[str, Any], layers: dict[str, Any], args: list[float]) -> dict[str, Any]:
    o0,o1=map(F32,args); acc=_scalar_conv(x["q"],_raw(layers,"enc3_ds_weight"),stride=2); values=np.empty(acc.shape,F32)
    for index in np.ndindex(values.shape): values[index]=F32(acc[index])*WEIGHT_SCALES["enc3_ds"]*F32(x["s"])+F32(_raw(layers,"enc3_ds_bias")[index[2]])
    midpoint=values.shape[2]//2; out=np.empty(values.shape,np.int8); out[:,:,:midpoint]=_scalar_quant_array(values[:,:,:midpoint],F32(1.0)/o0); out[:,:,midpoint:]=_scalar_quant_array(values[:,:,midpoint:],F32(1.0)/o1)
    return {"q":out,"s0":o0,"s1":o1}


def _transpose_scalar(x: np.ndarray,w: np.ndarray) -> np.ndarray:
    if w.ndim != 4 or w.shape[0] != x.shape[2] or w.shape[2:] != (2,2): raise CpuReferenceError("scalar transposed convolution requires IOHW [Cin,Cout,2,2]")
    h,width,channels=x.shape; outputs=w.shape[1]; result=np.zeros((2*h,2*width,outputs),np.int64)
    for y in range(h):
        for x_pos in range(width):
            for ky in range(2):
                for kx in range(2):
                    for output in range(outputs):
                        total=0
                        for channel in range(channels): total+=int(x[y,x_pos,channel])*int(w[channel,output,ky,kx])
                        result[2*y+ky,2*x_pos+kx,output]=total
    return result


def _p9_scalar(x: dict[str, Any],skip: dict[str, Any],layers: dict[str, Any],args: list[float]) -> dict[str, Any]:
    fnb=_fnb_scalar(x,layers,"bottleneck_ResidualBlock_2",args,variant=64,uniform=args[3],ct_order=True); acc=_transpose_scalar(fnb["q"],_raw(layers,"bottleneck_ct_weight")); values=np.empty(acc.shape,F32)
    for index in np.ndindex(values.shape): values[index]=F32(acc[index])*(F32(fnb["s"])*WEIGHT_SCALES["bottleneck_ct"])+F32(_raw(layers,"bottleneck_ct_bias")[index[2]])+F32(skip["q"][index])*F32(skip["s"])
    o0,o1=map(F32,args[4:6]); midpoint=values.shape[2]//2; out=np.empty(values.shape,np.int8); out[:,:,:midpoint]=_scalar_quant_array(values[:,:,:midpoint],F32(1.0)/o0); out[:,:,midpoint:]=_scalar_quant_array(values[:,:,midpoint:],F32(1.0)/o1)
    return {"q":out,"s0":o0,"s1":o1}


def run_scalar_pass(pass_id: str,value: dict[str,Any],layers: dict[str,Any],skip: dict[str,Any]|None=None)->dict[str,Any]:
    calls=layers["_calls"]
    if pass_id=="p5": return _fnb_scalar(value,layers,"encoder3_ResidualBlock_1",calls[4]["args"],variant=32,uniform=P5_OUTPUT_SCALE)
    if pass_id=="p6": return _downscale_scalar(value,layers,calls[5]["args"])
    if pass_id=="p7": return _fnb_scalar(value,layers,"bottleneck_ResidualBlock_0",calls[6]["args"],variant=64)
    if pass_id=="p8": return _fnb_scalar(value,layers,"bottleneck_ResidualBlock_1",calls[7]["args"],variant=64)
    if pass_id=="p9" and skip is not None: return _p9_scalar(value,skip,layers,calls[8]["args"])
    raise CpuReferenceError(f"invalid F02b scalar pass invocation: {pass_id}")


def run_scalar_oracle(p4:dict[str,Any],layers:dict[str,Any])->dict[str,dict[str,Any]]:
    outputs={}; value=p4
    for pass_id in ("p5","p6","p7","p8"):
        value=run_scalar_pass(pass_id,value,layers); outputs[pass_id]=value
    outputs["p9"]=run_scalar_pass("p9",value,layers,outputs["p5"]); return outputs


def validate_contract_scales(contract:dict[str,Any])->None:
    if contract.get("schema_version") != "fsr-cpu-pass5-9-reference-v1": raise CpuReferenceError("F02b contract schema version is invalid")
    comparison=contract.get("comparison")
    if not isinstance(comparison,dict) or set(comparison)!={"metric","tolerance","rounding","saturation"}: raise CpuReferenceError("F02b comparison contract is invalid")
    if comparison["metric"]!="maximum-absolute-int8-lsb" or type(comparison["tolerance"]) is not int or comparison["tolerance"]!=0 or comparison["rounding"]!="mathematical-half-away-from-zero" or comparison["saturation"]!=[-128,127] or any(type(value) is not int for value in comparison["saturation"]): raise CpuReferenceError("F02b comparison contract is invalid")
    passes=contract.get("passes")
    if not isinstance(passes,list) or [item.get("pass_id") for item in passes if isinstance(item,dict)] != ["p5","p6","p7","p8","p9"]: raise CpuReferenceError("F02b contract pass order is invalid")
    for item in passes:
        expected=EXPECTED_OUTPUT_SCALES[item["pass_id"]]; observed=item.get("scales")
        if not isinstance(observed,list) or len(observed)!=len(expected) or any(type(a) not in (int,float) or not math.isfinite(a) or F32(a).tobytes()!=b.tobytes() for a,b in zip(observed,expected)): raise CpuReferenceError(f"F02b contract output scales mismatch: {item['pass_id']}")
        direct=item.get("direct_input"); direct_expected=EXPECTED_DIRECT_CONTRACT[item["pass_id"]]
        required={"generator","sha256","shape","dtype","scales","output_sha256","output_shape","output_dtype","output_scales"}
        if item["pass_id"]=="p9": required|={"skip_generator","skip_sha256","skip_shape","skip_dtype","skip_scales"}
        if not isinstance(direct,dict) or set(direct)!=required: raise CpuReferenceError(f"F02b direct input contract is invalid: {item['pass_id']}")
        generator,digest,shape,scales,output_digest=direct_expected
        if direct["generator"]!=generator or direct["sha256"]!=digest or direct["shape"]!=shape or direct["dtype"]!="int8" or direct["output_sha256"]!=output_digest: raise CpuReferenceError(f"F02b direct input contract is invalid: {item['pass_id']}")
        if not isinstance(direct["shape"],list) or any(type(value) is not int or value<=0 for value in direct["shape"]): raise CpuReferenceError(f"F02b direct input shape is invalid: {item['pass_id']}")
        if not isinstance(direct["scales"],list) or len(direct["scales"])!=len(scales) or any(type(a) not in (int,float) or not math.isfinite(a) or F32(a).tobytes()!=F32(b).tobytes() for a,b in zip(direct["scales"],scales)): raise CpuReferenceError(f"F02b direct input scales mismatch: {item['pass_id']}")
        if direct["output_shape"]!=EXPECTED_DIRECT_OUTPUT_SHAPES[item["pass_id"]] or direct["output_dtype"]!="int8": raise CpuReferenceError(f"F02b direct output contract is invalid: {item['pass_id']}")
        if not isinstance(direct["output_shape"],list) or any(type(value) is not int or value<=0 for value in direct["output_shape"]): raise CpuReferenceError(f"F02b direct output shape is invalid: {item['pass_id']}")
        if not isinstance(direct["output_scales"],list) or len(direct["output_scales"])!=len(expected) or any(type(a) not in (int,float) or not math.isfinite(a) or F32(a).tobytes()!=b.tobytes() for a,b in zip(direct["output_scales"],expected)): raise CpuReferenceError(f"F02b direct output scales mismatch: {item['pass_id']}")
        if item["pass_id"]=="p9":
            skip_generator,skip_digest,skip_shape,skip_scales=EXPECTED_P9_SKIP
            if direct["skip_generator"]!=skip_generator or direct["skip_sha256"]!=skip_digest or direct["skip_shape"]!=skip_shape or direct["skip_dtype"]!="int8": raise CpuReferenceError("F02b p9 skip contract is invalid")
            if not isinstance(direct["skip_shape"],list) or any(type(value) is not int or value<=0 for value in direct["skip_shape"]): raise CpuReferenceError("F02b p9 skip shape is invalid")
            if not isinstance(direct["skip_scales"],list) or len(direct["skip_scales"])!=len(skip_scales) or any(type(a) not in (int,float) or not math.isfinite(a) or F32(a).tobytes()!=F32(b).tobytes() for a,b in zip(direct["skip_scales"],skip_scales)): raise CpuReferenceError("F02b p9 skip scales mismatch")

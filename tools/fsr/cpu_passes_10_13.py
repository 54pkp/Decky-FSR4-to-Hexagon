#!/usr/bin/env python3
"""F02c host CPU references for passes 10-13 only."""
from __future__ import annotations
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any
import numpy as np

from tools.fsr.cpu_passes_1_4 import F32, _conv2d, _quantize, _scalar_conv, _scalar_quantize, tensor_scales
from tools.fsr.cpu_passes_5_9 import _transpose, _transpose_scalar
from tools.fsr.pass_manifest import load_bound_simulator_snapshot

Q="_quant_export_handler_QuantizeLinear_output_0"
P11_OUTPUT_SCALE=F32(0.027206305414438248); P12_OUTPUT_SCALE=F32(0.035173576325178146)
SCALES={
"decoder3_ResidualBlock_1_spatial":F32(0.006604361813515425),"decoder3_ResidualBlock_1_pw_expand":F32(0.004052944015711546),"decoder3_ResidualBlock_1_pw_contract":F32(0.00404848949983716),
"decoder3_ResidualBlock_2_spatial":F32(0.004134095273911953),"decoder3_ResidualBlock_2_pw_expand":F32(0.005980394314974546),"decoder3_ResidualBlock_2_pw_contract":F32(0.00594315817579627),"dec3_ct":F32(0.0023969162721186876),
"decoder2_RB1_conv_dw":F32(0.005350596271455288),"decoder2_RB1_pw_expand":F32(0.0051390123553574085),"decoder2_RB1_pw_contract":F32(0.005128493066877127),
"decoder2_ResidualBlock_2_conv_dw":F32(0.007368451915681362),"decoder2_ResidualBlock_2_pw_expand":F32(0.007268762681633234),"decoder2_ResidualBlock_2_pw_contract":F32(0.007326302584260702),"dec2_ct":F32(0.0070633538998663425)}
RAW={
"decoder3_ResidualBlock_1_spatial_weight":f"embedded__decoder3_ResidualBlock_1_body_spatial_mixing_partial_conv_weight{Q}","decoder3_ResidualBlock_1_spatial_bias":"bias__embedded_decoder3_ResidualBlock_1_body_spatial_mixing_partial_conv_bias",
"decoder3_ResidualBlock_1_pw_expand_weight":f"embedded__decoder3_ResidualBlock_1_body_pw_expand_weight{Q}","decoder3_ResidualBlock_1_pw_expand_bias":"bias__embedded_decoder3_ResidualBlock_1_body_pw_expand_bias","decoder3_ResidualBlock_1_pw_contract_weight":f"embedded__decoder3_ResidualBlock_1_body_pw_contract_weight{Q}","decoder3_ResidualBlock_1_pw_contract_bias":"bias__embedded_decoder3_ResidualBlock_1_body_pw_contract_bias",
"decoder3_ResidualBlock_2_spatial_weight":f"embedded__decoder3_ResidualBlock_2_body_spatial_mixing_partial_conv_weight{Q}","decoder3_ResidualBlock_2_spatial_bias":"bias__embedded_decoder3_ResidualBlock_2_body_spatial_mixing_partial_conv_bias","decoder3_ResidualBlock_2_pw_expand_weight":f"embedded__decoder3_ResidualBlock_2_body_pw_expand_weight{Q}","decoder3_ResidualBlock_2_pw_expand_bias":"bias__embedded_decoder3_ResidualBlock_2_body_pw_expand_bias","decoder3_ResidualBlock_2_pw_contract_weight":f"embedded__decoder3_ResidualBlock_2_body_pw_contract_weight{Q}","decoder3_ResidualBlock_2_pw_contract_bias":"bias__embedded_decoder3_ResidualBlock_2_body_pw_contract_bias",
"dec3_ct_weight":f"embedded_hwcn__decoder3_UpscaleConvTranspose2x2_upscale_conv_weight{Q}","dec3_ct_bias":"bias__embedded_decoder3_UpscaleConvTranspose2x2_upscale_conv_bias",
"decoder2_RB1_conv_dw_weight":f"embedded__decoder2_ResidualBlock_1_body_conv_dw_weight{Q}","decoder2_RB1_conv_dw_bias":"bias__embedded_decoder2_ResidualBlock_1_body_conv_dw_bias","decoder2_RB1_pw_expand_weight":f"embedded__decoder2_ResidualBlock_1_body_conv_pw_expand_weight{Q}","decoder2_RB1_pw_expand_bias":"bias__embedded_decoder2_ResidualBlock_1_body_conv_pw_expand_bias","decoder2_RB1_pw_contract_weight":f"embedded__decoder2_ResidualBlock_1_body_conv_pw_contract_weight{Q}","decoder2_RB1_pw_contract_bias":"bias__embedded_decoder2_ResidualBlock_1_body_conv_pw_contract_bias",
"decoder2_ResidualBlock_2_conv_dw_weight":f"embedded__decoder2_ResidualBlock_2_body_conv_dw_weight{Q}","decoder2_ResidualBlock_2_conv_dw_bias":"bias__embedded_decoder2_ResidualBlock_2_body_conv_dw_bias","decoder2_ResidualBlock_2_pw_expand_weight":f"embedded__decoder2_ResidualBlock_2_body_conv_pw_expand_weight{Q}","decoder2_ResidualBlock_2_pw_expand_bias":"bias__embedded_decoder2_ResidualBlock_2_body_conv_pw_expand_bias","decoder2_ResidualBlock_2_pw_contract_weight":f"embedded__decoder2_ResidualBlock_2_body_conv_pw_contract_weight{Q}","decoder2_ResidualBlock_2_pw_contract_bias":"bias__embedded_decoder2_ResidualBlock_2_body_conv_pw_contract_bias","dec2_ct_weight":f"embedded_hwcn__decoder2_UpscaleConvTranspose2x2_upscale_conv_weight{Q}","dec2_ct_bias":"bias__embedded_decoder2_UpscaleConvTranspose2x2_upscale_conv_bias"}
POST_RAW={key:("post."+value if value.startswith("embedded") else value.replace("bias__embedded_","bias__post.embedded_")) for key,value in RAW.items() if key.startswith("decoder2_ResidualBlock_2") or key.startswith("dec2_ct")}
EXPECTED_OUTPUT_SCALES={"p10":(F32(0.0215474721044302),F32(0.02673504687845707)),"p11":(P11_OUTPUT_SCALE,),"p12":(P12_OUTPUT_SCALE,),"p13":()}
DIRECT_SPECS={"p10":((4,4,32),83,41,(F32(0.021412165835499763),F32(0.03075222671031952))),"p11":((4,4,32),89,43,EXPECTED_OUTPUT_SCALES["p10"]),"p12":((8,8,16),97,47,(P11_OUTPUT_SCALE,)),"p13":((8,8,16),101,53,(P12_OUTPUT_SCALE,))}
P11_SKIP=((8,8,16),103,59,(F32(0.02335178479552269),))
DIRECT_CONTRACT={
"p10":("87f0daf2cb70ee2ac7d7436e80524669c146ef96e036ed4f00a3be0575786a0d",[4,4,32],[0.021412165835499763,0.03075222671031952],"646195b7aadd2bc83751814233904e678bfdfe5d7020b33a422edad21b5c7c3a",[4,4,32],"int8",[0.0215474721044302,0.02673504687845707]),
"p11":("1a85e7b77b1f80e49cab302e6fcb9b3c84af4a537b5eb30cbf36e0ac439e9a2b",[4,4,32],[0.0215474721044302,0.02673504687845707],"bc89ea9aa9a0fb2d5bcf973ad2132a9d3ea3c58253b9d574d5146fc7c1da49b0",[8,8,16],"int8",[0.027206305414438248]),
"p12":("5c51b09274dc70fa9763d2025e816b03d559b07ee43e2dd32dc1b25def6bb1e1",[8,8,16],[0.027206305414438248],"a291292249b6970f05bf96d55912093859c3fd74785fc6623d6275d01a72257b",[8,8,16],"int8",[0.035173576325178146]),
"p13":("19af955215ff7da0c4682d283a44e911eac6762773bd869e5ebdedce6658c9f5",[8,8,16],[0.035173576325178146],"70bfa015c6c259ab914b66f2dfd1e44933eab690286bb81e6ff256aac4f006f8",[16,16,8],"float16",[])}
P11_SKIP_CONTRACT=("3a6b276a39198030399570b320a73a62eefaddda23e6fbbbcb5f131816bd0bf1",[8,8,16],[0.02335178479552269])
EXPECTED_SOURCES={"p7_receipt_sha256":"b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b","weights_sha256":"9c644d42f421d6dfc2c13479dff84f1017c5457d00a14125796b3562944982fb","graph_sha256":"8179991469fc0aae5fbc114c7e10f18ffb31555ff25351898b786198e70b2266","simulator_sha256":"e82d407f26d4cd22d7b10d25a5f5d53e236febf98414946ecba32dee1377c0fe"}
EXPECTED_UPSTREAMS=[{"path":"tools/fsr/cpu_passes_1_4_contract.json","sha256":"a2dd054d7309ed249bd73aa088315d650b2cecd192f81e29e95b91b230169f7b"},{"path":"tools/fsr/cpu_passes_5_9_contract.json","sha256":"ff2dbe84e8a8569515260bf388af2612bf58641f56955db961ed2a902ff78d80"}]

class CpuReferenceError(Exception): pass
def _gen(spec):
 shape,mul,off,scales=spec; count=int(np.prod(shape)); q=np.fromiter((((i*mul+off)%255)-127 for i in range(count)),dtype=np.int8,count=count).reshape(shape)
 return ({"q":q,"s":scales[0]} if len(scales)==1 else {"q":q,"s0":scales[0],"s1":scales[1]})
def direct_inputs(pass_id):
 if pass_id not in DIRECT_SPECS: raise CpuReferenceError("unknown F02c pass")
 return _gen(DIRECT_SPECS[pass_id]),(_gen(P11_SKIP) if pass_id=="p11" else None)
def load_bound_layers(manifest,p7:Path,simulator:Path):
 ns,payloads=load_bound_simulator_snapshot(manifest,p7,simulator); ns["ART"]=p7
 with np.load(BytesIO(payloads["weights"]),allow_pickle=False) as archive: raw={name:archive[name] for name in archive.files}
 graph=json.loads(payloads["graph"].decode("utf-8")); layers={alias:raw[name] for alias,name in RAW.items()}; layers["_raw"]=raw; layers["_calls"]=graph["calls"]
 for alias,scale in SCALES.items():
  raw_name=RAW[f"{alias}_weight"]
  observed=graph["decls"].get(raw_name,{}).get("scale")
  if observed is None or F32(observed).tobytes()!=scale.tobytes(): raise CpuReferenceError(f"P7 graph scale mismatch: {alias}")
  layers[f"scale__{alias}"]=scale
 for alias,name in POST_RAW.items():
  if raw[name].dtype != layers[alias].dtype or raw[name].shape != layers[alias].shape or raw[name].tobytes()!=layers[alias].tobytes(): raise CpuReferenceError(f"post/non-post P7 tensor mismatch: {alias}")
 layers["_post_raw"]={alias:raw[name] for alias,name in POST_RAW.items()}
 return layers,ns
def _sq(values,mult,relu=False):
 out=np.empty(values.shape,np.int8)
 for index in np.ndindex(values.shape): out[index]=_scalar_quantize(F32(values[index])*mult,relu=relu)
 return out
def _vq(values,mult,relu=False): return _quantize(values*mult,relu=relu)
def _fnb(x,L,prefix,args,scalar=False,uniform=None,ct_order=False):
 q0,q1,act=map(F32,args[:3]); C=x["q"].shape[2]; conv=_scalar_conv if scalar else _conv2d; quant=_sq if scalar else _vq
 acc=conv(x["q"][:,:,:C//2],L[f"{prefix}_spatial_weight"],pad=1); v=acc.astype(F32)*(q0*SCALES[f"{prefix}_spatial"])+L[f"{prefix}_spatial_bias"]; partial=quant(v,F32(1)/q1)
 concat=np.concatenate([partial,x["q"][:,:,C//2:]],axis=2); acc=conv(concat,L[f"{prefix}_pw_expand_weight"]); v=(acc.astype(F32)*(q1*SCALES[f"{prefix}_pw_expand"]) if ct_order else acc.astype(F32)*q1*SCALES[f"{prefix}_pw_expand"])+L[f"{prefix}_pw_expand_bias"]; active=quant(v,F32(1)/act,relu=True)
 acc=conv(active,L[f"{prefix}_pw_contract_weight"]); v=(acc.astype(F32)*(SCALES[f"{prefix}_pw_contract"]*act) if ct_order else acc.astype(F32)*SCALES[f"{prefix}_pw_contract"]*act)+L[f"{prefix}_pw_contract_bias"]
 v[:,:,:C//2]+=x["q"][:,:,:C//2].astype(F32)*q0; v[:,:,C//2:]+=x["q"][:,:,C//2:].astype(F32)*q1
 if uniform is not None: return {"q":quant(v,F32(1)/F32(uniform)),"s":F32(uniform)}
 o0,o1=map(F32,args[3:5]); out=np.empty(v.shape,np.int8); out[:,:,:C//2]=quant(v[:,:,:C//2],F32(1)/o0); out[:,:,C//2:]=quant(v[:,:,C//2:],F32(1)/o1); return {"q":out,"s0":o0,"s1":o1}
def _cnb(x,L,prefix,args,out_scale,scalar=False,post=False):
 conv=_scalar_conv if scalar else _conv2d; quant=_sq if scalar else _vq; source=L["_post_raw"] if post else L
 def get(name): return source[name] if post and name in source else L[name]
 r0,mid1,r1,mid2=map(F32,args[:4]); acc=conv(x["q"],get(f"{prefix}_conv_dw_weight"),pad=1); v=(acc.astype(F32)*(F32(x["s"])*SCALES[f"{prefix}_conv_dw"])+get(f"{prefix}_conv_dw_bias"))*r0; q=quant(v,F32(1))
 acc=conv(q,get(f"{prefix}_pw_expand_weight")); v=(acc.astype(F32)*(mid1*SCALES[f"{prefix}_pw_expand"])+get(f"{prefix}_pw_expand_bias"))*r1; q=quant(v,F32(1),relu=True)
 acc=conv(q,get(f"{prefix}_pw_contract_weight")); v=acc.astype(F32)*(SCALES[f"{prefix}_pw_contract"]*mid2)+get(f"{prefix}_pw_contract_bias")+x["q"].astype(F32)*F32(x["s"])
 return {"q":quant(v,F32(1)/F32(out_scale)),"s":F32(out_scale)}
def _p11(x,skip,L,args,scalar=False):
 fnb=_fnb(x,L,"decoder3_ResidualBlock_2",args,scalar,uniform=args[3],ct_order=True); transpose=_transpose_scalar if scalar else _transpose; quant=_sq if scalar else _vq
 acc=transpose(fnb["q"],L["dec3_ct_weight"]); v=acc.astype(F32)*(F32(fnb["s"])*SCALES["dec3_ct"])+L["dec3_ct_bias"]+skip["q"].astype(F32)*F32(skip["s"]); return {"q":quant(v,F32(1)/P11_OUTPUT_SCALE),"s":P11_OUTPUT_SCALE}
def _p13(x,L,args,scalar=False):
 cnb=_cnb(x,L,"decoder2_ResidualBlock_2",args,args[4]); acc=_transpose(cnb["q"],L["dec2_ct_weight"])
 return {"q":finalize_fp16_ct(acc,F32(cnb["s"])*SCALES["dec2_ct"],L["dec2_ct_bias"])}
def finalize_fp16_ct(acc,scale,bias):
 product=(acc.astype(F32)*F32(scale)).astype(np.float16)
 return (product+bias.astype(np.float16)).astype(np.float16)
def _sget(L,alias,post=False): return L["_post_raw"][alias] if post else L["_raw"][RAW[alias]]
def _fnb_scalar_independent(x,L,prefix,args,uniform=None,ct_order=False):
 q0,q1,act=map(F32,args[:3]); C=x["q"].shape[2]
 acc=_scalar_conv(x["q"][:,:,:C//2],_sget(L,f"{prefix}_spatial_weight"),pad=1); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape): values[index]=F32(acc[index])*(q0*SCALES[f"{prefix}_spatial"])+F32(_sget(L,f"{prefix}_spatial_bias")[index[2]])
 partial=_sq(values,F32(1)/q1); concat=np.concatenate([partial,x["q"][:,:,C//2:]],axis=2); acc=_scalar_conv(concat,_sget(L,f"{prefix}_pw_expand_weight")); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape):
  product=F32(acc[index])*(q1*SCALES[f"{prefix}_pw_expand"]) if ct_order else F32(acc[index])*q1*SCALES[f"{prefix}_pw_expand"]
  values[index]=product+F32(_sget(L,f"{prefix}_pw_expand_bias")[index[2]])
 active=_sq(values,F32(1)/act,relu=True); acc=_scalar_conv(active,_sget(L,f"{prefix}_pw_contract_weight")); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape):
  product=F32(acc[index])*(SCALES[f"{prefix}_pw_contract"]*act) if ct_order else F32(acc[index])*SCALES[f"{prefix}_pw_contract"]*act
  residual=F32(x["q"][index])*(q0 if index[2]<C//2 else q1)
  values[index]=product+F32(_sget(L,f"{prefix}_pw_contract_bias")[index[2]])+residual
 if uniform is not None: return {"q":_sq(values,F32(1)/F32(uniform)),"s":F32(uniform)}
 o0,o1=map(F32,args[3:5]); out=np.empty(values.shape,np.int8); out[:,:,:C//2]=_sq(values[:,:,:C//2],F32(1)/o0); out[:,:,C//2:]=_sq(values[:,:,C//2:],F32(1)/o1); return {"q":out,"s0":o0,"s1":o1}
def _cnb_scalar_independent(x,L,prefix,args,out_scale,post=False):
 r0,mid1,r1,mid2=map(F32,args[:4]); acc=_scalar_conv(x["q"],_sget(L,f"{prefix}_conv_dw_weight",post),pad=1); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape): values[index]=(F32(acc[index])*(F32(x["s"])*SCALES[f"{prefix}_conv_dw"])+F32(_sget(L,f"{prefix}_conv_dw_bias",post)[index[2]]))*r0
 q=_sq(values,F32(1)); acc=_scalar_conv(q,_sget(L,f"{prefix}_pw_expand_weight",post)); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape): values[index]=(F32(acc[index])*(mid1*SCALES[f"{prefix}_pw_expand"])+F32(_sget(L,f"{prefix}_pw_expand_bias",post)[index[2]]))*r1
 q=_sq(values,F32(1),relu=True); acc=_scalar_conv(q,_sget(L,f"{prefix}_pw_contract_weight",post)); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape): values[index]=F32(acc[index])*(SCALES[f"{prefix}_pw_contract"]*mid2)+F32(_sget(L,f"{prefix}_pw_contract_bias",post)[index[2]])+F32(x["q"][index])*F32(x["s"])
 return {"q":_sq(values,F32(1)/F32(out_scale)),"s":F32(out_scale)}
def _p11_scalar_independent(x,skip,L,args):
 fnb=_fnb_scalar_independent(x,L,"decoder3_ResidualBlock_2",args,uniform=args[3],ct_order=True); acc=_transpose_scalar(fnb["q"],_sget(L,"dec3_ct_weight")); values=np.empty(acc.shape,F32)
 for index in np.ndindex(values.shape): values[index]=F32(acc[index])*(F32(fnb["s"])*SCALES["dec3_ct"])+F32(_sget(L,"dec3_ct_bias")[index[2]])+F32(skip["q"][index])*F32(skip["s"])
 return {"q":_sq(values,F32(1)/P11_OUTPUT_SCALE),"s":P11_OUTPUT_SCALE}
def _p13_scalar_independent(x,L,args):
 cnb=_cnb_scalar_independent(x,L,"decoder2_ResidualBlock_2",args,args[4],post=True); acc=_transpose_scalar(cnb["q"],_sget(L,"dec2_ct_weight",True)); out=np.empty(acc.shape,np.float16); scale=F32(cnb["s"])*SCALES["dec2_ct"]
 for index in np.ndindex(out.shape): out[index]=np.float16(np.float16(F32(acc[index])*scale)+np.float16(_sget(L,"dec2_ct_bias",True)[index[2]]))
 return {"q":out}
def run_vector_pass(pass_id,value,L,skip=None):
 c=L["_calls"]
 if skip is not None and pass_id!="p11": raise CpuReferenceError("skip is only valid for p11")
 if pass_id=="p10": return _fnb(value,L,"decoder3_ResidualBlock_1",c[9]["args"])
 if pass_id=="p11" and skip is not None: return _p11(value,skip,L,c[10]["args"])
 if pass_id=="p12": return _cnb(value,L,"decoder2_RB1",c[11]["args"],P12_OUTPUT_SCALE)
 if pass_id=="p13": return _p13(value,L,c[12]["args"])
 raise CpuReferenceError("invalid F02c invocation")
def run_scalar_pass(pass_id,value,L,skip=None):
 c=L["_calls"]
 if skip is not None and pass_id!="p11": raise CpuReferenceError("skip is only valid for p11")
 if pass_id=="p10": return _fnb_scalar_independent(value,L,"decoder3_ResidualBlock_1",c[9]["args"])
 if pass_id=="p11" and skip is not None: return _p11_scalar_independent(value,skip,L,c[10]["args"])
 if pass_id=="p12": return _cnb_scalar_independent(value,L,"decoder2_RB1",c[11]["args"],P12_OUTPUT_SCALE)
 if pass_id=="p13": return _p13_scalar_independent(value,L,c[12]["args"])
 raise CpuReferenceError("invalid F02c scalar invocation")
def run_vector(p9,p2,L):
 out={}; value=p9
 for pass_id in ("p10","p11","p12","p13"):
  value=run_vector_pass(pass_id,value,L,p2 if pass_id=="p11" else None); out[pass_id]=value
 return out
def run_scalar_oracle(p9,p2,L):
 out={}; value=p9
 for pass_id in ("p10","p11","p12","p13"):
  value=run_scalar_pass(pass_id,value,L,p2 if pass_id=="p11" else None); out[pass_id]=value
 return out
def _scales_valid(observed,expected):
 return isinstance(observed,list) and len(observed)==len(expected) and all(type(a) in (int,float) and math.isfinite(a) and F32(a).tobytes()==F32(b).tobytes() for a,b in zip(observed,expected))
def validate_contract(contract):
 if contract.get("schema_version")!="fsr-cpu-pass10-13-reference-v1": raise CpuReferenceError("invalid F02c schema")
 if contract.get("sources")!=EXPECTED_SOURCES: raise CpuReferenceError("invalid F02c sources")
 if contract.get("upstream_contracts")!=EXPECTED_UPSTREAMS: raise CpuReferenceError("invalid F02c upstream contracts")
 comparison=contract.get("comparison")
 expected_comparison={"int8":{"metric":"maximum-absolute-lsb","tolerance":0},"float16":{"metric":"uint16-bit-pattern","tolerance_ulp":0,"finite_required":True},"rounding":"mathematical-half-away-from-zero"}
 if comparison!=expected_comparison or type(comparison.get("int8",{}).get("tolerance")) is not int or type(comparison.get("float16",{}).get("tolerance_ulp")) is not int or type(comparison.get("float16",{}).get("finite_required")) is not bool: raise CpuReferenceError("invalid F02c comparison")
 passes=contract.get("passes")
 if not isinstance(passes,list) or [x.get("pass_id") for x in passes if isinstance(x,dict)]!=["p10","p11","p12","p13"]: raise CpuReferenceError("invalid F02c pass order")
 for item in passes:
  pid=item["pass_id"]; expected=EXPECTED_OUTPUT_SCALES[pid]
  if not _scales_valid(item.get("scales"),expected): raise CpuReferenceError(f"invalid F02c output scales: {pid}")
  direct=item.get("direct_input"); digest,shape,scales,out_digest,out_shape,out_dtype,out_scales=DIRECT_CONTRACT[pid]
  required={"sha256","shape","dtype","scales","output_sha256","output_shape","output_dtype","output_scales"}
  if pid=="p11": required|={"skip_sha256","skip_shape","skip_dtype","skip_scales"}
  if not isinstance(direct,dict) or set(direct)!=required or direct["sha256"]!=digest or direct["shape"]!=shape or direct["dtype"]!="int8" or direct["output_sha256"]!=out_digest or direct["output_shape"]!=out_shape or direct["output_dtype"]!=out_dtype: raise CpuReferenceError(f"invalid F02c direct contract: {pid}")
  if any(type(x) is not int or x<=0 for x in direct["shape"]+direct["output_shape"]) or not _scales_valid(direct["scales"],scales) or not _scales_valid(direct["output_scales"],out_scales): raise CpuReferenceError(f"invalid F02c direct metadata: {pid}")
  if pid=="p11":
   skip_digest,skip_shape,skip_scales=P11_SKIP_CONTRACT
   if direct["skip_sha256"]!=skip_digest or direct["skip_shape"]!=skip_shape or direct["skip_dtype"]!="int8" or any(type(x) is not int or x<=0 for x in direct["skip_shape"]) or not _scales_valid(direct["skip_scales"],skip_scales): raise CpuReferenceError("invalid F02c p11 skip contract")

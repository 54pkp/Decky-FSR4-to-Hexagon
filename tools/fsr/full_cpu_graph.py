#!/usr/bin/env python3
"""F03 composition and first-divergence diagnostics for CPU passes 1-13.

The p1 input is generated synthetically by the pinned F01 formula. This module
neither executes nor consumes an accepted P8/pass-0 output; the scalar
composition is not a fourth oracle.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, math
from types import MappingProxyType
from typing import Any, Callable
import numpy as np
import tools.fsr.cpu_passes_1_4 as segment_a
import tools.fsr.cpu_passes_5_9 as segment_b
import tools.fsr.cpu_passes_10_13 as segment_c

PASS_IDS=tuple(f"p{i}" for i in range(1,14))
EXPECTED_MANIFEST={"path":"tools/fsr/pass_manifest.json","sha256":"419a53b803b5c5d9421714c258898cd3eff416b96d40b190df56eb396b57d1d2"}
EXPECTED_IMPLEMENTATION_PATH="tools/fsr/full_cpu_graph.py"
EXPECTED_SOURCES={"p7_receipt_sha256":"b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b","weights_sha256":"9c644d42f421d6dfc2c13479dff84f1017c5457d00a14125796b3562944982fb","graph_sha256":"8179991469fc0aae5fbc114c7e10f18ffb31555ff25351898b786198e70b2266","simulator_commit":"8c7a972ab70e5693828a856da71ce711232af463","simulator_sha256":"e82d407f26d4cd22d7b10d25a5f5d53e236febf98414946ecba32dee1377c0fe"}
EXPECTED_UPSTREAMS=[{"path":"tools/fsr/cpu_passes_1_4_contract.json","sha256":"a2dd054d7309ed249bd73aa088315d650b2cecd192f81e29e95b91b230169f7b"},{"path":"tools/fsr/cpu_passes_5_9_contract.json","sha256":"ff2dbe84e8a8569515260bf388af2612bf58641f56955db961ed2a902ff78d80"},{"path":"tools/fsr/cpu_passes_10_13_contract.json","sha256":"b2eeaa1ea27eb80c8d1ea4082498800bdfb46325399369146fb8a997223e78b7"}]
EXPECTED_TRACE_HASHES={"p1":"f06fa1879f27823bf9e8c7ffbb4887ad5e6f0b2ef03592f40f13baa5a61a217b","p2":"17fdd33fe9a86d517b8e44043dabae52f129bf9cdef67428210bf9ec5306bc6f","p3":"435a882dc65352590018305cf7dfe94072b738dd2df0350601528d98ef618a00","p4":"09b2b2f61d29c96e9d6968a0e01a66f404a941b19ce583be2fa75a5d213656a5","p5":"c8e881539ce246fce24fb3043b6aeb2c9ffe12377ccc034045c4391b57f0a8eb","p6":"cbafbe8cdbd10a5ddbd91bf31e765e6c057b3df02c030830906e6a1e2f044f48","p7":"96fe93969e0a3d0ca35c68ddbd5076a71f341d293bf50eeabf87aafac2f4ee43","p8":"a1257b1a5e430652ec55c42f954f82a19d8d0147a5651da0001b02f67ab9ceca","p9":"2727a71115d97abaa357a9fe8b402dceef59020d9809246cf2abbb4910b20452","p10":"1ab54077af80d26adaf3afbefbae8e315ef264f17b63708aae2ba8dbf9382b88","p11":"cb0b26ada6d4bd97e87f65dd8240fbc5466836c74e784780601b091744275982","p12":"7299e46d9aee46e35679d2eb2a233c9fb297e873d58748d32179aecf38ffdb47","p13":"56fd10a7ec307c8a40e52d80676378d16775b947d9c3b03fd1659cb289514ac7"}
EXPECTED_COMPARISON={"int8":{"metric":"maximum-absolute-lsb","tolerance":0},"float16":{"metric":"uint16-bit-pattern","tolerance_ulp":0,"finite_required":True},"scales":"float32-bit-pattern"}
EXPECTED_LIMITATIONS={"oracle":"composition-only-uses-F02-segmented-evidence","p1_input":"synthetic-generated-by-F01-formula","p8_pass0_output":"not-executed-and-not-consumed","temporal_fsr4":"not_implemented","onnx_qnn_htp_device_game":"not_run"}
class FullGraphError(Exception): pass
class FullGraphMismatch(FullGraphError): pass
def _sha(q): return hashlib.sha256(q.tobytes()).hexdigest()
def _scales(value):
 if "s" in value:return (np.float32(value["s"]),)
 if "s0" in value and "s1" in value:return (np.float32(value["s0"]),np.float32(value["s1"]))
 return ()
@dataclass(frozen=True)
class PassRecord:
 q: np.ndarray
 scales: tuple[np.float32,...]
 sha256: str
 primary_sha256: str
 skip_pass: str|None
 skip_sha256: str|None
def _record(value,primary,skip_pass=None,skip=None):
 source=np.ascontiguousarray(value["q"]);q=np.frombuffer(source.tobytes(),dtype=source.dtype).reshape(source.shape)
 return PassRecord(q,_scales(value),_sha(q),_sha(primary["q"]),skip_pass,None if skip is None else _sha(skip["q"]))
def _run(manifest,layers_a,layers_b,layers_c,dispatch_a:Callable,dispatch_b:Callable,dispatch_c:Callable):
 records={};values={};value=segment_a.fixed_input(manifest) # synthetic F01-formula p1_input
 for pid in ("p1","p2","p3","p4"):
  primary=value;value=dispatch_a(pid,primary,layers_a);values[pid]=value;records[pid]=_record(value,primary)
 for pid in ("p5","p6","p7","p8"):
  primary=value;value=dispatch_b(pid,primary,layers_b);values[pid]=value;records[pid]=_record(value,primary)
 primary=value;skip=values["p5"];value=dispatch_b("p9",primary,layers_b,skip);values["p9"]=value;records["p9"]=_record(value,primary,"p5",skip)
 primary=value;value=dispatch_c("p10",primary,layers_c);values["p10"]=value;records["p10"]=_record(value,primary)
 primary=value;skip=values["p2"];value=dispatch_c("p11",primary,layers_c,skip);values["p11"]=value;records["p11"]=_record(value,primary,"p2",skip)
 primary=value;value=dispatch_c("p12",primary,layers_c);values["p12"]=value;records["p12"]=_record(value,primary)
 primary=value;value=dispatch_c("p13",primary,layers_c);records["p13"]=_record(value,primary)
 return MappingProxyType(records)
def run_full_graph(manifest,layers_a,layers_b,layers_c):return _run(manifest,layers_a,layers_b,layers_c,segment_a.run_vector_pass,segment_b.run_vector_pass,segment_c.run_vector_pass)
def run_segmented_scalar_evidence(manifest,layers_a,layers_b,layers_c):
 """Compose the three accepted scalar segments; this is not a new oracle."""
 return _run(manifest,layers_a,layers_b,layers_c,segment_a.run_scalar_pass,segment_b.run_scalar_pass,segment_c.run_scalar_pass)
def _mismatch(pid,field,actual,expected,left,max_error=None):
 extra="" if max_error is None else f" max_error={max_error}"
 return FullGraphMismatch(f"{pid}.{field}: expected={expected} actual={actual} input={left.primary_sha256} skip={left.skip_sha256}{extra}")
def compare_traces(actual,expected,int8_tolerance=0,float16_tolerance_ulp=0):
 if type(int8_tolerance) is not int or int8_tolerance!=0 or type(float16_tolerance_ulp) is not int or float16_tolerance_ulp!=0:raise FullGraphError("F03 tolerances are fixed at zero")
 if tuple(actual)!=PASS_IDS:raise FullGraphMismatch(f"trace.pass_order expected={PASS_IDS} actual={tuple(actual)}")
 if tuple(expected)!=PASS_IDS:raise FullGraphMismatch(f"expected.pass_order expected={PASS_IDS} actual={tuple(expected)}")
 for pid in PASS_IDS:
  left,right=actual[pid],expected[pid]
  for field in ("primary_sha256","skip_pass","skip_sha256"):
   if getattr(left,field)!=getattr(right,field):raise _mismatch(pid,field,getattr(left,field),getattr(right,field),left)
  if left.q.shape!=right.q.shape:raise _mismatch(pid,"q.shape",left.q.shape,right.q.shape,left)
  if left.q.dtype!=right.q.dtype:raise _mismatch(pid,"q.dtype",left.q.dtype,right.q.dtype,left)
  if len(left.scales)!=len(right.scales) or any(a.tobytes()!=b.tobytes() for a,b in zip(left.scales,right.scales)):raise _mismatch(pid,"scale.float32_bits",tuple(float(x) for x in left.scales),tuple(float(x) for x in right.scales),left)
  if not np.isfinite(left.q).all():raise _mismatch(pid,"q.finite",False,True,left)
  if left.q.dtype==np.float16:av,ev=left.q.view(np.uint16),right.q.view(np.uint16);different=av!=ev;error=np.abs(av.astype(np.int32)-ev.astype(np.int32))
  else:av,ev=left.q,right.q;different=av!=ev;error=np.abs(av.astype(np.int16)-ev.astype(np.int16))
  if np.any(different):
   index=tuple(int(x) for x in np.argwhere(different)[0]);raise _mismatch(pid,f"q[{index}]",int(av[index]),int(ev[index]),left,int(error.max()))
  if left.sha256!=right.sha256:raise _mismatch(pid,"q.sha256",left.sha256,right.sha256,left)
def _sha_field(value):return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)
def validate_contract(contract:Any):
 required={"schema_version","manifest","upstream_contracts","implementation","sources","input","comparison","trace_sha256","output","limitations"}
 if not isinstance(contract,dict) or set(contract)!=required:raise FullGraphError("F03 contract fields mismatch")
 if contract["schema_version"]!="fsr-full-cpu-graph-v1":raise FullGraphError("F03 schema mismatch")
 if contract["manifest"]!=EXPECTED_MANIFEST or contract["sources"]!=EXPECTED_SOURCES or contract["upstream_contracts"]!=EXPECTED_UPSTREAMS:raise FullGraphError("F03 identity binding mismatch")
 impl=contract["implementation"]
 if not isinstance(impl,dict) or set(impl)!={"path","sha256"} or impl["path"]!=EXPECTED_IMPLEMENTATION_PATH or not _sha_field(impl["sha256"]):raise FullGraphError("F03 implementation binding mismatch")
 comparison=contract["comparison"]
 if comparison!=EXPECTED_COMPARISON or type(comparison.get("int8",{}).get("tolerance")) is not int or type(comparison.get("float16",{}).get("tolerance_ulp")) is not int or type(comparison.get("float16",{}).get("finite_required")) is not bool:raise FullGraphError("F03 comparison mismatch")
 if contract["trace_sha256"]!=EXPECTED_TRACE_HASHES or set(contract["trace_sha256"])!=set(PASS_IDS) or not all(_sha_field(x) for x in contract["trace_sha256"].values()):raise FullGraphError("F03 trace hashes mismatch")
 expected_input={"case_id":"f01-synthetic-8x8-int8-v1","sha256":"aff0c596e36cb412883e01693bff831477d5fe2539472ac876d7d912a6806039","shape":[8,8,16],"dtype":"int8","scales":[0.014884727075695992]};expected_output={"pass_id":"p13","sha256":EXPECTED_TRACE_HASHES["p13"],"shape":[16,16,8],"dtype":"float16","scales":[]}
 if contract["input"]!=expected_input or contract["output"]!=expected_output:raise FullGraphError("F03 endpoint contract mismatch")
 for endpoint in (contract["input"],contract["output"]):
  if any(type(x) is not int or x<=0 for x in endpoint["shape"]) or any(type(x) not in (int,float) or not math.isfinite(x) for x in endpoint["scales"]):raise FullGraphError("F03 endpoint types invalid")
 if contract["limitations"]!=EXPECTED_LIMITATIONS:raise FullGraphError("F03 limitations mismatch")

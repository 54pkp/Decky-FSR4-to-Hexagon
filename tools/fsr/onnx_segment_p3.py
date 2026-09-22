#!/usr/bin/env python3
"""Build and validate the deterministic real-weight FSR pass-3 ONNX segment."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import argparse, sys
import os
from io import BytesIO
from typing import Any
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from google.protobuf.message import DecodeError
import tools.fsr.cpu_passes_1_4 as cpu
from tools.fsr.pass_manifest import load_pass_manifest, _bound_source_payloads, MANIFEST_PATH, MAX_MANIFEST_BYTES

SCHEMA="fsr-p3-onnx-segment-v1";OPSET=18;IR=10
INPUT="p2_quantized_nchw";OUTPUT="p3_quantized_nchw"
INPUT_SHAPE=(1,16,8,8);OUTPUT_SHAPE=(1,32,4,4)
INPUT_SCALE=np.float32(0.02335178479552269);WEIGHT_SCALE=np.float32(0.003455055644735694)
OUTPUT_SCALES=(np.float32(0.015390855260193348),np.float32(0.018884973600506783))
NODE_NAMES=("p3_input_dequantize","p3_weight_dequantize","p3_conv2x2_stride2_bias","p3_output_quantize")
NODE_TYPES=("DequantizeLinear","DequantizeLinear","Conv","QuantizeLinear")
SOURCE={"manifest_sha256":"419a53b803b5c5d9421714c258898cd3eff416b96d40b190df56eb396b57d1d2","f02a_contract_sha256":"a2dd054d7309ed249bd73aa088315d650b2cecd192f81e29e95b91b230169f7b","p7_receipt_sha256":"b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b","weights_sha256":"9c644d42f421d6dfc2c13479dff84f1017c5457d00a14125796b3562944982fb","graph_sha256":"8179991469fc0aae5fbc114c7e10f18ffb31555ff25351898b786198e70b2266","simulator_sha256":"e82d407f26d4cd22d7b10d25a5f5d53e236febf98414946ecba32dee1377c0fe"}
EXPECTED_MODEL={"tracked":False,"rebuild":"local/venvs/reference/Scripts/python.exe -m tools.fsr.onnx_segment_p3 --p7 artifacts/p7-fsr-v07-r10a-20260922 --simulator research/fsr4-hexagon/model/sim/fsr4_sim.py --output <new-path.onnx>","byte_count":3251,"sha256":"2f15dce7ecabf990573f2a1794d984ee62950cdcbcba6a0764c77949390c0448"}
WEIGHT_HASH="43f07431dcf401dc0b665e3ddc7658bd136fde53747fd2bc0ca4ea91b2da85f8";BIAS_HASH="3a07b756c7b4ebd0593c69283b603c91f9df4ed572bd31febe1f88d530b737ec"
class SegmentError(Exception):pass
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _scalar(value,dtype,name):return numpy_helper.from_array(np.asarray(value,dtype=dtype),name)
class _ManifestSnapshot:
 def __init__(self,payload):self.payload=payload
 def open(self,mode):
  if mode!="rb":raise ValueError("manifest snapshot is read-only")
  return BytesIO(self.payload)
def _fixed_manifest_snapshot():
 try:
  with MANIFEST_PATH.open("rb") as stream:payload=stream.read(MAX_MANIFEST_BYTES+1)
 except OSError as exc:raise SegmentError(f"cannot read fixed manifest: {exc}") from exc
 if len(payload)>MAX_MANIFEST_BYTES:raise SegmentError("fixed manifest exceeds byte limit")
 if sha(payload)!=SOURCE["manifest_sha256"]:raise SegmentError("fixed manifest identity mismatch")
 try:return load_pass_manifest(_ManifestSnapshot(payload))
 except Exception as exc:
  from tools.fsr.pass_manifest import PassManifestError
  if isinstance(exc,PassManifestError):raise SegmentError(f"fixed manifest validation failed: {exc}") from exc
  raise
def _authenticated_p3_inputs(manifest,p7,simulator):
 trusted=_fixed_manifest_snapshot()
 if manifest!=trusted:raise SegmentError("caller manifest differs from the fixed validated manifest")
 f02=Path(__file__).with_name("cpu_passes_1_4_contract.json")
 try:payload=f02.read_bytes()
 except OSError as exc:raise SegmentError(f"cannot read F02a contract: {exc}") from exc
 if sha(payload)!=SOURCE["f02a_contract_sha256"]:raise SegmentError("F02a contract identity mismatch")
 try:cpu.validate_contract_scales(json.loads(payload.decode("utf-8")))
 except (UnicodeDecodeError,json.JSONDecodeError,cpu.CpuReferenceError) as exc:raise SegmentError(f"F02a contract validation failed: {exc}") from exc
 try:
  snapshot=_bound_source_payloads(trusted,p7,simulator)
  with np.load(BytesIO(snapshot["weights"]),allow_pickle=False) as archive:
   weight=np.array(archive[cpu.RAW_BINDINGS["enc2_ds_weight"]],copy=True);bias=np.array(archive[cpu.RAW_BINDINGS["enc2_ds_bias"]],copy=True)
  graph=json.loads(snapshot["graph"].decode("utf-8"));call=graph["calls"][2]
 except Exception as exc:
  from tools.fsr.pass_manifest import PassManifestError
  if isinstance(exc,PassManifestError):raise SegmentError(f"authenticated source snapshot rejected: {exc}") from exc
  raise SegmentError(f"cannot decode authenticated p3 source snapshot: {exc}") from exc
 if call!={"op":"FusedConv2D_k2s2b_QuantizedOutput","args":[float(OUTPUT_SCALES[0]),float(OUTPUT_SCALES[1])]}:raise SegmentError("authenticated graph p3 call mismatch")
 return np.ascontiguousarray(weight),np.ascontiguousarray(bias)
def build_model(manifest:dict[str,Any],p7:Path,simulator:Path):
 weight,bias=_authenticated_p3_inputs(manifest,p7,simulator)
 if sha(weight.tobytes())!=WEIGHT_HASH or sha(bias.tobytes())!=BIAS_HASH:raise SegmentError("p3 initializer source mismatch")
 output_scale=np.r_[np.repeat(OUTPUT_SCALES[0],16),np.repeat(OUTPUT_SCALES[1],16)].astype(np.float32);output_zero=np.zeros(32,np.int8)
 initializers=[numpy_helper.from_array(weight,"p3_weight_int8"),numpy_helper.from_array(bias,"p3_bias_float"),_scalar(INPUT_SCALE,np.float32,"p2_scale"),_scalar(0,np.int8,"p2_zero_point"),_scalar(WEIGHT_SCALE,np.float32,"p3_weight_scale"),_scalar(0,np.int8,"p3_weight_zero_point"),numpy_helper.from_array(output_scale,"p3_output_scale"),numpy_helper.from_array(output_zero,"p3_output_zero_point")]
 nodes=[helper.make_node("DequantizeLinear",[INPUT,"p2_scale","p2_zero_point"],["p2_float"],name=NODE_NAMES[0]),helper.make_node("DequantizeLinear",["p3_weight_int8","p3_weight_scale","p3_weight_zero_point"],["p3_weight_float"],name=NODE_NAMES[1]),helper.make_node("Conv",["p2_float","p3_weight_float","p3_bias_float"],["p3_float"],name=NODE_NAMES[2],kernel_shape=[2,2],strides=[2,2],pads=[0,0,0,0]),helper.make_node("QuantizeLinear",["p3_float","p3_output_scale","p3_output_zero_point"],[OUTPUT],name=NODE_NAMES[3],axis=1)]
 graph=helper.make_graph(nodes,"fsr_pass3_downscale_qdq",[helper.make_tensor_value_info(INPUT,TensorProto.INT8,INPUT_SHAPE)],[helper.make_tensor_value_info(OUTPUT,TensorProto.INT8,OUTPUT_SHAPE)],initializer=initializers)
 model=helper.make_model(graph,producer_name="decky-fsr4-to-hexagon-f04a",producer_version="1",opset_imports=[helper.make_opsetid("",OPSET)]);model.ir_version=IR;model.doc_string="F04a real P7 pass-3 QDQ segment; checker-only, not ORT/QAIRT evidence."
 onnx.checker.check_model(model);return model
def model_bytes(manifest,p7,simulator):return build_model(manifest,p7,simulator).SerializeToString(deterministic=True)
def _require_absent(path):
 try:os.lstat(path)
 except FileNotFoundError:return
 except OSError as exc:raise SegmentError(f"cannot inspect output path: {exc}") from exc
 raise SegmentError(f"output path already exists, including a dangling link: {path}")
def write_model(path,manifest,p7,simulator):
 _require_absent(path);payload=model_bytes(manifest,p7,simulator);_require_absent(path)
 try:
  with path.open("xb") as stream:stream.write(payload)
 except FileExistsError as exc:raise SegmentError(f"output already exists: {path}") from exc
 return sha(payload)
def _vi(value):
 tensor=value.type.tensor_type
 if any(not d.HasField("dim_value") for d in tensor.shape.dim):raise SegmentError("dynamic tensor dimensions are unsupported")
 return value.name,tensor.elem_type,tuple(d.dim_value for d in tensor.shape.dim)
def validate_model(model,contract):
 validate_contract(contract)
 if len(model.graph.sparse_initializer) or len(model.functions) or len(model.training_info):raise SegmentError("sparse/functions/training model content is unsupported")
 if any(x.data_location!=TensorProto.DEFAULT or len(x.external_data) for x in model.graph.initializer):raise SegmentError("external initializer data are unsupported")
 try:onnx.checker.check_model(model)
 except onnx.checker.ValidationError as exc:raise SegmentError(f"ONNX checker rejected segment: {exc}") from exc
 if model.ir_version!=IR or [(x.domain,x.version) for x in model.opset_import] != [("",OPSET)]:raise SegmentError("ONNX version contract mismatch")
 if model.producer_name!="decky-fsr4-to-hexagon-f04a" or model.producer_version!="1" or model.graph.name!="fsr_pass3_downscale_qdq" or model.doc_string!="F04a real P7 pass-3 QDQ segment; checker-only, not ORT/QAIRT evidence.":raise SegmentError("model metadata mismatch")
 if len(model.graph.input)!=1 or _vi(model.graph.input[0])!=(INPUT,TensorProto.INT8,INPUT_SHAPE):raise SegmentError("input name/static shape/dtype mismatch")
 if len(model.graph.output)!=1 or _vi(model.graph.output[0])!=(OUTPUT,TensorProto.INT8,OUTPUT_SHAPE):raise SegmentError("output name/static shape/dtype mismatch")
 if tuple(n.name for n in model.graph.node)!=NODE_NAMES or tuple(n.op_type for n in model.graph.node)!=NODE_TYPES:raise SegmentError("operator sequence or names mismatch")
 if any(n.op_type=="Reshape" for n in model.graph.node):raise SegmentError("reshape is unsupported")
 expected_io=[([INPUT,"p2_scale","p2_zero_point"],["p2_float"]),(["p3_weight_int8","p3_weight_scale","p3_weight_zero_point"],["p3_weight_float"]),(["p2_float","p3_weight_float","p3_bias_float"],["p3_float"]),(["p3_float","p3_output_scale","p3_output_zero_point"],[OUTPUT])]
 if any((list(node.input),list(node.output))!=io or node.domain!="" for node,io in zip(model.graph.node,expected_io)):raise SegmentError("node wiring or domain mismatch")
 attrs=[{a.name:helper.get_attribute_value(a) for a in node.attribute} for node in model.graph.node]
 if attrs[0]!={} or attrs[1]!={} or attrs[2]!={"kernel_shape":[2,2],"pads":[0,0,0,0],"strides":[2,2]} or attrs[3]!={"axis":1}:raise SegmentError("node attributes mismatch")
 if len(model.graph.value_info) or len(model.graph.sparse_initializer) or len(model.functions) or len(model.training_info) or len(model.metadata_props):raise SegmentError("extra graph metadata are unsupported")
 values={x.name:numpy_helper.to_array(x) for x in model.graph.initializer}
 if set(values)!={"p3_weight_int8","p3_bias_float","p2_scale","p2_zero_point","p3_weight_scale","p3_weight_zero_point","p3_output_scale","p3_output_zero_point"}:raise SegmentError("initializer set mismatch")
 if values["p3_weight_int8"].shape!=(32,16,2,2) or values["p3_weight_int8"].dtype!=np.int8 or sha(values["p3_weight_int8"].tobytes())!=WEIGHT_HASH:raise SegmentError("weight binding mismatch")
 bias=np.ascontiguousarray(values["p3_bias_float"])
 if bias.shape!=(32,) or bias.dtype!=np.float32 or sha(bias.tobytes())!=BIAS_HASH:raise SegmentError("bias binding mismatch")
 expected={"p2_scale":INPUT_SCALE,"p3_weight_scale":WEIGHT_SCALE}
 for name,value in expected.items():
  if values[name].shape!=() or values[name].dtype!=np.float32 or values[name].tobytes()!=value.tobytes():raise SegmentError(f"{name} mismatch")
 expected_scale=np.r_[np.repeat(OUTPUT_SCALES[0],16),np.repeat(OUTPUT_SCALES[1],16)].astype(np.float32)
 if values["p3_output_scale"].shape!=(32,) or values["p3_output_scale"].dtype!=np.float32 or not np.array_equal(values["p3_output_scale"],expected_scale) or sha(values["p3_output_scale"].tobytes())!="77cb9090a598cfedd93bcd59a8b64d3c3d43a1d4a9d20a6efde276d62baa5411":raise SegmentError("output scale vector mismatch")
 if values["p3_output_zero_point"].shape!=(32,) or values["p3_output_zero_point"].dtype!=np.int8 or np.any(values["p3_output_zero_point"]) or sha(values["p3_output_zero_point"].tobytes())!="66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925":raise SegmentError("output zero-point vector mismatch")
 payload=model.SerializeToString(deterministic=True)
 if len(payload)!=contract["model"]["byte_count"] or sha(payload)!=contract["model"]["sha256"]:raise SegmentError("serialized model identity mismatch")
def load_and_validate(path:Path,contract_path:Path):
 try:contract=json.loads(contract_path.read_text(encoding="utf-8"));validate_contract(contract);payload=path.read_bytes();model=onnx.load_model_from_string(payload)
 except (OSError,json.JSONDecodeError,DecodeError) as exc:raise SegmentError(f"cannot load segment: {exc}") from exc
 if len(payload)!=contract["model"]["byte_count"] or sha(payload)!=contract["model"]["sha256"]:raise SegmentError("model file identity mismatch")
 validate_model(model,contract);return model
def _validate_contract(contract):
 required={"schema_version","segment","manifest","upstream_contract","implementation","sources","tensors","qdq","initializers","graph","model","comparison","limitations"}
 if not isinstance(contract,dict) or set(contract)!=required:raise SegmentError("contract fields mismatch")
 if contract["schema_version"]!=SCHEMA or contract["segment"]!={"passes":["p3"],"operator":"FusedConv2D_k2s2b_QuantizedOutput"}:raise SegmentError("segment identity mismatch")
 if contract["sources"]!=SOURCE:raise SegmentError("source binding mismatch")
 if contract["manifest"]!={"path":"tools/fsr/pass_manifest.json","sha256":SOURCE["manifest_sha256"]} or contract["upstream_contract"]!={"path":"tools/fsr/cpu_passes_1_4_contract.json","sha256":SOURCE["f02a_contract_sha256"]}:raise SegmentError("upstream binding mismatch")
 if contract["tensors"]!={"input":{"name":INPUT,"shape":list(INPUT_SHAPE),"dtype":"int8","layout":"NCHW","fixture_sha256":"57c18148d561081a77005fd63297a99b33f064d2f2f24b730803ebf2cb028a84"},"output":{"name":OUTPUT,"shape":list(OUTPUT_SHAPE),"dtype":"int8","layout":"NCHW","fixture_sha256":"a51a49f8a64c51bfa213076b6cbe3fb2339bc312bc29668e03a953210ed358be"}}:raise SegmentError("tensor contract mismatch")
 if any(type(dimension) is not int for tensor in contract["tensors"].values() for dimension in tensor["shape"]):raise SegmentError("tensor dimensions must be integers, not booleans")
 qdq=contract["qdq"];expected={"input_scale":float(INPUT_SCALE),"weight_scale":float(WEIGHT_SCALE),"output_scales":[float(x) for x in OUTPUT_SCALES],"output_scale_vector_sha256":"77cb9090a598cfedd93bcd59a8b64d3c3d43a1d4a9d20a6efde276d62baa5411","output_zero_vector_sha256":"66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925","zero_point":0,"axis":1}
 if qdq!=expected or type(qdq.get("axis")) is not int or type(qdq.get("zero_point")) is not int or any(type(x) not in (int,float) or isinstance(x,bool) for x in [qdq.get("input_scale"),qdq.get("weight_scale"),*qdq.get("output_scales",[])]):raise SegmentError("QDQ contract mismatch")
 if contract["initializers"]!={"weight":{"name":"p3_weight_int8","shape":[32,16,2,2],"dtype":"int8","layout":"OIHW","sha256":WEIGHT_HASH},"bias":{"name":"p3_bias_float","shape":[32],"dtype":"float32","layout":"C","sha256":BIAS_HASH,"provenance":"P7 float32 expansion of source float16 bias"}}:raise SegmentError("initializer contract mismatch")
 if any(type(dimension) is not int for item in contract["initializers"].values() for dimension in item["shape"]):raise SegmentError("initializer dimensions must be integers, not booleans")
 if contract["graph"]!={"opset":OPSET,"ir_version":IR,"node_names":list(NODE_NAMES),"node_types":list(NODE_TYPES),"dynamic_shapes":False,"reshape_supported":False}:raise SegmentError("graph contract mismatch")
 if type(contract["graph"].get("opset")) is not int or type(contract["graph"].get("ir_version")) is not int or type(contract["graph"].get("dynamic_shapes")) is not bool or type(contract["graph"].get("reshape_supported")) is not bool:raise SegmentError("graph contract types mismatch")
 if contract["comparison"]!={"runtime_numeric":"not_run","absolute_tolerance":None,"relative_tolerance":None}:raise SegmentError("comparison contract mismatch")
 impl=contract["implementation"];model=contract["model"]
 valid_sha=lambda value:isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)
 if set(impl)!={"path","sha256"} or impl["path"]!="tools/fsr/onnx_segment_p3.py" or not valid_sha(impl["sha256"]):raise SegmentError("implementation binding mismatch")
 if model!=EXPECTED_MODEL or set(model)!={"tracked","rebuild","byte_count","sha256"} or type(model.get("byte_count")) is not int or not valid_sha(model["sha256"]):raise SegmentError("model identity contract mismatch")
 if contract["limitations"]!={"scope":"single-real-pass-p3-checker-only","onnx_runtime":"not_run","qairt_qnn_htp_device_game":"not_run","complete_fsr_onnx":False}:raise SegmentError("limitations mismatch")
 if type(contract["limitations"].get("complete_fsr_onnx")) is not bool or type(model.get("tracked")) is not bool:raise SegmentError("boolean contract types mismatch")
def validate_contract(contract):
 try:_validate_contract(contract)
 except SegmentError:raise
 except (KeyError,TypeError,ValueError,AttributeError) as exc:raise SegmentError(f"malformed F04a contract: {exc}") from exc
def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--p7",type=Path,required=True);parser.add_argument("--simulator",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args(argv)
 try:
  if not args.output.parent.is_dir():raise SegmentError("output parent must exist")
  digest=write_model(args.output,load_pass_manifest(),args.p7,args.simulator);print(json.dumps({"byte_count":args.output.stat().st_size,"sha256":digest},sort_keys=True));return 0
 except (SegmentError,cpu.CpuReferenceError,OSError) as exc:print(f"F04a export failed: {exc}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

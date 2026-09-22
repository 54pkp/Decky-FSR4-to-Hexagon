from __future__ import annotations
import copy, hashlib, json, os, shutil, subprocess
from pathlib import Path
import sys, tempfile, unittest
from unittest import mock
try:
 import numpy as np
 import onnx
except ModuleNotFoundError:
 np=onnx=None
ROOT=Path(__file__).resolve().parents[2]
if os.fspath(ROOT) not in sys.path:sys.path.insert(0,os.fspath(ROOT))
P7=ROOT/"artifacts"/"p7-fsr-v07-r10a-20260922";SIM=ROOT/"research"/"fsr4-hexagon"/"model"/"sim"/"fsr4_sim.py";CONTRACT=ROOT/"tools"/"fsr"/"onnx_segment_p3_contract.json"
CAPABLE=onnx is not None and np is not None and P7.is_dir() and SIM.is_file()
if onnx is not None:
 import tools.fsr.onnx_segment_p3 as target
 from tools.fsr.pass_manifest import load_pass_manifest
@unittest.skipUnless(CAPABLE,"F04a requires reference ONNX/NumPy and accepted P7 sources")
class OnnxSegmentP3Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.manifest=load_pass_manifest();cls.contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
 def model(self):return target.build_model(self.manifest,P7,SIM)
 def test_deterministic_real_p3_model_passes_checker_and_loader(self):
  first=target.model_bytes(self.manifest,P7,SIM);second=target.model_bytes(self.manifest,P7,SIM)
  self.assertEqual(first,second);self.assertEqual(self.contract["model"]["byte_count"],len(first));self.assertEqual(self.contract["model"]["sha256"],hashlib.sha256(first).hexdigest())
  model=onnx.load_model_from_string(first);onnx.checker.check_model(model);target.validate_model(model,self.contract)
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"p3.onnx";path.write_bytes(first);loaded=target.load_and_validate(path,CONTRACT);self.assertEqual([n.op_type for n in loaded.graph.node],list(target.NODE_TYPES))
 def test_contract_is_closed_source_bound_and_has_no_numeric_claim(self):
  target.validate_contract(self.contract)
  for item in (self.contract["manifest"],self.contract["upstream_contract"],self.contract["implementation"]):self.assertEqual(item["sha256"],hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest())
  changes=[lambda x:x.update({"unknown":1}),lambda x:x.pop("sources"),lambda x:x.update({"sources":{}}),lambda x:x["sources"].update({"weights_sha256":"0"*64}),lambda x:x["tensors"].update({"input":[]}),lambda x:x["tensors"]["input"].update({"shape":[True,16,8,8]}),lambda x:x["tensors"]["input"].update({"shape":[1,16,"height",8]}),lambda x:x["tensors"]["output"].update({"dtype":"float32"}),lambda x:x.update({"qdq":[]}),lambda x:x["qdq"].update({"input_scale":"0.023"}),lambda x:x["qdq"].update({"zero_point":False}),lambda x:x["qdq"].update({"axis":True}),lambda x:x["initializers"]["weight"].update({"shape":[32,16,2,True]}),lambda x:x["graph"].update({"opset":True}),lambda x:x["graph"].update({"dynamic_shapes":0}),lambda x:x["graph"].update({"reshape_supported":True}),lambda x:x["comparison"].update({"absolute_tolerance":0.01}),lambda x:x["model"].update({"tracked":0}),lambda x:x["model"].update({"byte_count":True}),lambda x:x["model"].update({"sha256":"0"*64}),lambda x:x["model"].update({"rebuild":"other"}),lambda x:x["limitations"].update({"complete_fsr_onnx":0})]
  for change in changes:
   bad=copy.deepcopy(self.contract);change(bad)
   with self.assertRaises(target.SegmentError):target.validate_contract(bad)
 def test_validator_rejects_dynamic_shape_reshape_and_initializer_changes(self):
  dynamic=self.model();dynamic.graph.input[0].type.tensor_type.shape.dim[2].ClearField("dim_value");dynamic.graph.input[0].type.tensor_type.shape.dim[2].dim_param="height"
  with self.assertRaisesRegex(target.SegmentError,"dynamic|input"):target.validate_model(dynamic,self.contract)
  reshaped=self.model();reshaped.graph.node[2].op_type="Reshape"
  with self.assertRaises(target.SegmentError):target.validate_model(reshaped,self.contract)
  changed=self.model();weight=next(x for x in changed.graph.initializer if x.name=="p3_weight_int8");raw=bytearray(weight.raw_data);raw[0]^=1;weight.raw_data=bytes(raw)
  with self.assertRaisesRegex(target.SegmentError,"weight binding"):target.validate_model(changed,self.contract)
  extra=self.model();extra.graph.node.extend([onnx.helper.make_node("Identity",[target.OUTPUT],["extra"],name="extra")])
  with self.assertRaisesRegex(target.SegmentError,"sequence"):target.validate_model(extra,self.contract)
  attributes=self.model();next(n for n in attributes.graph.node if n.op_type=="Conv").attribute[2].ints[:]=[1,1]
  with self.assertRaises(target.SegmentError):target.validate_model(attributes,self.contract)
  external=self.model();weight=next(x for x in external.graph.initializer if x.name=="p3_weight_int8");weight.ClearField("raw_data");weight.data_location=onnx.TensorProto.EXTERNAL;entry=weight.external_data.add();entry.key="location";entry.value="outside.bin"
  with mock.patch.object(target.onnx.checker,"check_model",side_effect=AssertionError("checker must not run")),mock.patch.object(target.numpy_helper,"to_array",side_effect=AssertionError("to_array must not run")):
   with self.assertRaisesRegex(target.SegmentError,"external"):target.validate_model(external,self.contract)
 def test_source_identity_drift_is_rejected_before_export(self):
  changed=copy.deepcopy(self.manifest);changed["sources"]["weights_sha256"]="0"*64
  with self.assertRaisesRegex(target.SegmentError,"caller manifest"):target.build_model(changed,P7,SIM)
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);sentinel=root/"executed";evil=root/"sim.py";payload=f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n".encode();evil.write_bytes(payload);changed=copy.deepcopy(self.manifest);changed["sources"]["simulator_sha256"]=hashlib.sha256(payload).hexdigest();changed["sources"]["simulator_byte_count"]=len(payload)
   with self.assertRaisesRegex(target.SegmentError,"caller manifest"):target.build_model(changed,P7,evil)
   self.assertFalse(sentinel.exists())
   for filename in ("intake_receipt.json","graph_spec.json"):
    copied=root/filename.replace(".","_");shutil.copytree(P7,copied);path=copied/filename;path.write_bytes(path.read_bytes()+b" ")
    with self.assertRaisesRegex(target.SegmentError,"snapshot rejected"):target.build_model(self.manifest,copied,SIM)
 def test_default_manifest_and_caller_cannot_be_changed_in_lockstep(self):
  changed=copy.deepcopy(self.manifest);changed["sources"]["simulator_sha256"]="0"*64;changed["sources"]["simulator_byte_count"]+=1
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"pass_manifest.json";path.write_text(json.dumps(changed,sort_keys=True),encoding="utf-8")
   with mock.patch.object(target,"MANIFEST_PATH",path):
    with self.assertRaisesRegex(target.SegmentError,"fixed manifest identity mismatch"):target.build_model(changed,P7,SIM)
 def test_cli_refuses_overwrite_and_missing_parent(self):
  with tempfile.TemporaryDirectory() as raw:
   output=Path(raw)/"segment.onnx";self.assertEqual(0,target.main(["--p7",str(P7),"--simulator",str(SIM),"--output",str(output)]));self.assertTrue(output.is_file());self.assertEqual(1,target.main(["--p7",str(P7),"--simulator",str(SIM),"--output",str(output)]));self.assertEqual(1,target.main(["--p7",str(P7),"--simulator",str(SIM),"--output",str(Path(raw)/"missing"/"x.onnx")]))
 def test_module_cli_help_and_real_export(self):
  command=[sys.executable,"-m","tools.fsr.onnx_segment_p3"]
  help_run=subprocess.run([*command,"--help"],cwd=ROOT,capture_output=True,text=True,timeout=10);self.assertEqual(0,help_run.returncode,help_run.stderr)
  with tempfile.TemporaryDirectory() as raw:
   output=Path(raw)/"module.onnx";run=subprocess.run([*command,"--p7",str(P7),"--simulator",str(SIM),"--output",str(output)],cwd=ROOT,capture_output=True,text=True,timeout=15);self.assertEqual(0,run.returncode,run.stderr);self.assertEqual(self.contract["model"]["sha256"],hashlib.sha256(output.read_bytes()).hexdigest())
 def test_dangling_symlink_output_is_never_followed_or_replaced(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);output=root/"segment.onnx";missing=root/"missing.onnx"
   try:os.symlink(missing,output)
   except OSError as exc:self.skipTest(f"symlink unavailable: {exc}")
   self.assertEqual(1,target.main(["--p7",str(P7),"--simulator",str(SIM),"--output",str(output)]));self.assertTrue(output.is_symlink());self.assertFalse(missing.exists())
 def test_competing_output_appearing_during_build_is_preserved(self):
  with tempfile.TemporaryDirectory() as raw:
   output=Path(raw)/"segment.onnx";original=target._require_absent;calls=0
   def appear(path):
    nonlocal calls
    calls+=1
    if calls==2:path.write_bytes(b"competitor")
    return original(path)
   with mock.patch.object(target,"_require_absent",side_effect=appear):
    with self.assertRaisesRegex(target.SegmentError,"already exists"):target.write_model(output,self.manifest,P7,SIM)
   self.assertEqual(b"competitor",output.read_bytes())
if __name__=="__main__":unittest.main()

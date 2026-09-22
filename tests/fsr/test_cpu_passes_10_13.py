from __future__ import annotations
import copy, hashlib, json, os
from pathlib import Path
import sys, unittest
from unittest import mock
try: import numpy as np
except ModuleNotFoundError: np=None
ROOT=Path(__file__).resolve().parents[2]
if os.fspath(ROOT) not in sys.path: sys.path.insert(0,os.fspath(ROOT))
P7=ROOT/"artifacts"/"p7-fsr-v07-r10a-20260922"; SIM=ROOT/"research"/"fsr4-hexagon"/"model"/"sim"/"fsr4_sim.py"; CONTRACT=ROOT/"tools"/"fsr"/"cpu_passes_10_13_contract.json"
CAPABLE=np is not None and P7.is_dir() and SIM.is_file()
if np is not None:
 import tools.fsr.cpu_passes_1_4 as a
 import tools.fsr.cpu_passes_5_9 as b
 import tools.fsr.cpu_passes_10_13 as target
 from tools.fsr.pass_manifest import load_pass_manifest
def sha(q): return hashlib.sha256(q.tobytes()).hexdigest()
def scales(value): return a.tensor_scales(value) if "s" in value or "s0" in value else ()

@unittest.skipUnless(CAPABLE,"F02c requires accepted P7 sources and fsr-extract NumPy")
class CpuPassesTenToThirteenTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.manifest=load_pass_manifest(); cls.layers,cls.sim=target.load_bound_layers(cls.manifest,P7,SIM); cls.contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
 def simulator_pass(self,pid,value,skip=None):
  c=self.layers["_calls"]
  if pid=="p10": return self.sim["fasternet"](value,self.layers,"decoder3_ResidualBlock_1",*c[9]["args"],"32")
  if pid=="p11": return self.sim["fnb_ct2d_add_uniform"](value,self.layers,"decoder3_ResidualBlock_2",skip,*c[10]["args"],float(target.P11_OUTPUT_SCALE),"32","dec3_ct_weight","dec3_ct_bias","dec3_ct")
  if pid=="p12": return self.sim["convnext"](value,self.layers,*c[11]["args"],float(target.P12_OUTPUT_SCALE),"decoder2_RB1")
  return {"q":self.sim["pass13_cnb_ct2d"](value,self.layers,"decoder2_ResidualBlock_2",*c[12]["args"],"dec2_ct_weight","dec2_ct_bias","dec2_ct")}
 def chain_inputs(self):
  la,_=a.load_bound_layers(self.manifest,P7,SIM); oa=a.run_scalar_oracle(self.manifest,la); lb,_=b.load_bound_layers(self.manifest,P7,SIM); ob=b.run_scalar_oracle(oa["p4"],lb); return ob["p9"],oa["p2"]
 def test_contract_schema_sources_hashes_and_type_negatives(self):
  target.validate_contract(self.contract)
  for section in ("manifest","implementation"):
   self.assertEqual(self.contract[section]["sha256"],hashlib.sha256((ROOT/self.contract[section]["path"]).read_bytes()).hexdigest())
  for item in self.contract["upstream_contracts"]: self.assertEqual(item["sha256"],hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest())
  for key,value in self.contract["sources"].items(): self.assertEqual(self.manifest["sources"][key],value)
  changes=[("schema_version","bad"),("comparison.int8.tolerance",False),("comparison.float16.tolerance_ulp","0"),("comparison.float16.finite_required",1),("passes.0.scales.0","0.1"),("passes.1.direct_input.skip_scales.0",True)]
  for path,value in changes:
   bad=copy.deepcopy(self.contract); node=bad
   for part in path.split(".")[:-1]: node=node[int(part)] if part.isdigit() else node[part]
   last=path.split(".")[-1]; node[int(last) if last.isdigit() else last]=value
   with self.assertRaises(target.CpuReferenceError): target.validate_contract(bad)
  for mutate in (lambda x:x.pop("sources"),lambda x:x.update({"sources":{}}),lambda x:x["sources"].update({"weights_sha256":"0"*64}),lambda x:x.pop("upstream_contracts"),lambda x:x.update({"upstream_contracts":[]}),lambda x:x["upstream_contracts"].__setitem__(0,{"path":"wrong","sha256":"0"*64})):
   bad=copy.deepcopy(self.contract); mutate(bad)
   with self.assertRaises(target.CpuReferenceError): target.validate_contract(bad)
 def test_fixed_chain_vector_scalar_simulator_zero_lsb_and_zero_ulp(self):
  p9,p2=self.chain_inputs(); vector=target.run_vector(p9,p2,self.layers); scalar=target.run_scalar_oracle(p9,p2,self.layers); simulated={}; value=p9
  for pid in ("p10","p11","p12","p13"):
   value=self.simulator_pass(pid,value,p2 if pid=="p11" else None); simulated[pid]=value
  entries={x["pass_id"]:x for x in self.contract["passes"]}; previous=p9
  for pid in ("p10","p11","p12","p13"):
   e=entries[pid]; self.assertEqual(e["chain_input_sha256"],sha(previous["q"]))
   for result in (vector[pid],scalar[pid],simulated[pid]): self.assertEqual(tuple(e["shape"]),result["q"].shape); self.assertEqual(np.dtype(e["dtype"]),result["q"].dtype); self.assertEqual(tuple(np.float32(x) for x in e["scales"]),scales(result)); self.assertTrue(np.isfinite(result["q"]).all())
   if pid=="p13": self.assertTrue(np.array_equal(vector[pid]["q"].view(np.uint16),scalar[pid]["q"].view(np.uint16))); self.assertTrue(np.array_equal(vector[pid]["q"].view(np.uint16),simulated[pid]["q"].view(np.uint16)))
   else: self.assertTrue(np.array_equal(vector[pid]["q"],scalar[pid]["q"])); self.assertTrue(np.array_equal(vector[pid]["q"],simulated[pid]["q"]))
   self.assertEqual(e["chain_output_sha256"],sha(vector[pid]["q"])); previous=scalar[pid]
  self.assertEqual(entries["p11"]["chain_skip_sha256"],sha(p2["q"]))
 def assert_direct(self,pid):
  e=next(x for x in self.contract["passes"] if x["pass_id"]==pid)["direct_input"]; value,skip=target.direct_inputs(pid)
  self.assertEqual(tuple(e["shape"]),value["q"].shape); self.assertEqual(np.dtype(e["dtype"]),value["q"].dtype); self.assertEqual(e["sha256"],sha(value["q"])); self.assertEqual(tuple(np.float32(x) for x in e["scales"]),scales(value))
  results=(target.run_vector_pass(pid,copy.deepcopy(value),self.layers,copy.deepcopy(skip)),target.run_scalar_pass(pid,copy.deepcopy(value),self.layers,copy.deepcopy(skip)),self.simulator_pass(pid,copy.deepcopy(value),copy.deepcopy(skip)))
  for result in results: self.assertEqual(tuple(e["output_shape"]),result["q"].shape); self.assertEqual(np.dtype(e["output_dtype"]),result["q"].dtype); self.assertEqual(tuple(np.float32(x) for x in e["output_scales"]),scales(result)); self.assertTrue(np.isfinite(result["q"]).all())
  self.assertEqual(e["output_sha256"],sha(results[1]["q"])); view=np.uint16 if pid=="p13" else np.int8; self.assertTrue(np.array_equal(results[0]["q"].view(view),results[1]["q"].view(view))); self.assertTrue(np.array_equal(results[0]["q"].view(view),results[2]["q"].view(view)))
  if skip is not None: self.assertEqual(e["skip_sha256"],sha(skip["q"])); self.assertEqual(tuple(e["skip_shape"]),skip["q"].shape); self.assertEqual(np.dtype(e["skip_dtype"]),skip["q"].dtype); self.assertEqual(tuple(np.float32(x) for x in e["skip_scales"]),scales(skip))
 def test_direct_p10(self): self.assert_direct("p10")
 def test_direct_p11(self): self.assert_direct("p11")
 def test_direct_p12(self): self.assert_direct("p12")
 def test_direct_p13(self): self.assert_direct("p13")
 def test_upsample_layout_skip_concat_and_final_rounding_negatives(self):
  x=np.asarray([[[2,3]]],np.int8); w=np.asarray([[[[1,2],[3,4]]],[[[10,20],[30,40]]]],np.int8); expected=np.asarray([[[32],[64]],[[96],[128]]],np.int64)
  self.assertTrue(np.array_equal(expected,target._transpose(x,w))); self.assertTrue(np.array_equal(expected,target._transpose_scalar(x,w)))
  with self.assertRaisesRegex(Exception,"IOHW"): target._transpose(x,w.transpose(1,0,2,3))
  p11,skip=target.direct_inputs("p11"); original=target.run_vector_pass("p11",p11,self.layers,skip)["q"]; wrong=copy.deepcopy(skip); wrong["q"]=np.roll(wrong["q"],1,axis=0); self.assertFalse(np.array_equal(original,target.run_vector_pass("p11",p11,self.layers,wrong)["q"]))
  with self.assertRaises(target.CpuReferenceError): target.run_vector_pass("p11",p11,self.layers)
  p13,_=target.direct_inputs("p13")
  with self.assertRaisesRegex(target.CpuReferenceError,"skip is only valid"): target.run_vector_pass("p13",p13,self.layers,skip)
  p10,_=target.direct_inputs("p10"); changed=copy.deepcopy(p10); changed["q"][:,:,16:]=np.bitwise_xor(changed["q"][:,:,16:],np.int8(1)); self.assertFalse(np.array_equal(target.run_vector_pass("p10",p10,self.layers)["q"],target.run_vector_pass("p10",changed,self.layers)["q"]))
  acc=np.asarray([[[-10]]],np.int64); bias=np.asarray([-9.949000358581543],np.float32); actual=target.finalize_fp16_ct(acc,np.float32(1),bias)[0,0,0]; expected=np.float16(np.float16(-10.0)+np.float16(bias[0])); wrong_round=np.float16(np.float32(-10.0)+bias[0]); self.assertEqual(int(expected.view(np.uint16)),int(actual.view(np.uint16))); self.assertNotEqual(int(actual.view(np.uint16)),int(wrong_round.view(np.uint16)))
 def test_scalar_paths_do_not_call_vector_block_combiners(self):
  patches=[mock.patch.object(target,name,side_effect=AssertionError(f"{name} forbidden")) for name in ("_fnb","_cnb","_p11","_p13")]
  with patches[0],patches[1],patches[2],patches[3]:
   for pid in ("p10","p11","p12","p13"):
    value,skip=target.direct_inputs(pid); result=target.run_scalar_pass(pid,value,self.layers,skip); self.assertTrue(np.isfinite(result["q"]).all())

if __name__=="__main__": unittest.main()

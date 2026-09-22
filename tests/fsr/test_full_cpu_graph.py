from __future__ import annotations
import copy, hashlib, json, os
from dataclasses import replace
from pathlib import Path
import sys, unittest
from unittest import mock
try: import numpy as np
except ModuleNotFoundError: np=None
ROOT=Path(__file__).resolve().parents[2]
if os.fspath(ROOT) not in sys.path:sys.path.insert(0,os.fspath(ROOT))
P7=ROOT/"artifacts"/"p7-fsr-v07-r10a-20260922";SIM=ROOT/"research"/"fsr4-hexagon"/"model"/"sim"/"fsr4_sim.py";CONTRACT=ROOT/"tools"/"fsr"/"full_cpu_graph_contract.json"
CAPABLE=np is not None and P7.is_dir() and SIM.is_file()
if np is not None:
 import tools.fsr.cpu_passes_1_4 as a
 import tools.fsr.cpu_passes_5_9 as b
 import tools.fsr.cpu_passes_10_13 as c
 import tools.fsr.full_cpu_graph as target
 from tools.fsr.pass_manifest import load_pass_manifest
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
@unittest.skipUnless(CAPABLE,"F03 requires accepted P7 sources and fsr-extract NumPy")
class FullCpuGraphTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.manifest=load_pass_manifest();cls.la,_=a.load_bound_layers(cls.manifest,P7,SIM);cls.lb,_=b.load_bound_layers(cls.manifest,P7,SIM);cls.lc,_=c.load_bound_layers(cls.manifest,P7,SIM);cls.contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
 def traces(self):return target.run_full_graph(self.manifest,self.la,self.lb,self.lc),target.run_segmented_scalar_evidence(self.manifest,self.la,self.lb,self.lc)
 def test_closed_contract_and_all_bound_files(self):
  target.validate_contract(self.contract)
  for section in ("manifest","implementation"):
   self.assertEqual(self.contract[section]["sha256"],digest(ROOT/self.contract[section]["path"]))
  for item in self.contract["upstream_contracts"]:self.assertEqual(item["sha256"],digest(ROOT/item["path"]))
  for module,entry in ((a,self.contract["upstream_contracts"][0]),(b,self.contract["upstream_contracts"][1]),(c,self.contract["upstream_contracts"][2])):
   upstream=json.loads((ROOT/entry["path"]).read_text(encoding="utf-8"));(module.validate_contract(upstream) if hasattr(module,"validate_contract") else module.validate_contract_scales(upstream))
   for key,value in upstream["sources"].items():self.assertEqual(value,self.contract["sources"][key])
   self.assertEqual(upstream["implementation"]["sha256"],digest(ROOT/upstream["implementation"]["path"]))
  mutations=[lambda x:x.pop("sources"),lambda x:x.update({"sources":{}}),lambda x:x["sources"].update({"simulator_sha256":"0"*64}),lambda x:x.pop("upstream_contracts"),lambda x:x.update({"upstream_contracts":[]}),lambda x:x["upstream_contracts"].__setitem__(1,{"path":"wrong","sha256":"0"*64}),lambda x:x["upstream_contracts"].reverse(),lambda x:x["comparison"]["int8"].update({"tolerance":1}),lambda x:x["comparison"]["int8"].update({"tolerance":False}),lambda x:x["comparison"]["float16"].update({"tolerance_ulp":"0"}),lambda x:x["trace_sha256"].pop("p6"),lambda x:x["trace_sha256"].update({"p6":"0"*64}),lambda x:x.update({"limitations":{}}),lambda x:x["manifest"].update({"sha256":"0"*64})]
  for mutate in mutations:
   bad=copy.deepcopy(self.contract);mutate(bad)
   with self.assertRaises(target.FullGraphError):target.validate_contract(bad)
 def test_full_vector_matches_independent_segmented_scalar_at_every_pass(self):
  actual,expected=self.traces();target.compare_traces(actual,expected)
  for pid in target.PASS_IDS:
   self.assertEqual(self.contract["trace_sha256"][pid],actual[pid].sha256)
   self.assertFalse(actual[pid].q.flags.writeable)
  self.assertEqual("p5",actual["p9"].skip_pass);self.assertEqual(actual["p5"].sha256,actual["p9"].skip_sha256)
  self.assertEqual("p2",actual["p11"].skip_pass);self.assertEqual(actual["p2"].sha256,actual["p11"].skip_sha256)
  self.assertEqual(self.contract["output"]["sha256"],actual["p13"].sha256)
  self.assertTrue(np.isfinite(actual["p13"].q).all())
 def test_trace_records_arrays_and_container_are_immutable(self):
  trace,_=self.traces();before=trace["p6"].sha256
  with self.assertRaises(ValueError):trace["p6"].q.flat[0]=0
  with self.assertRaises(ValueError):trace["p6"].q.setflags(write=True)
  with self.assertRaises(TypeError):trace["p6"]=trace["p5"]
  with self.assertRaises(TypeError):del trace["p6"]
  with self.assertRaises(Exception):trace["p6"].sha256="0"*64
  self.assertEqual(before,hashlib.sha256(trace["p6"].q.tobytes()).hexdigest())
 def test_first_divergence_reports_field_context_and_error(self):
  actual,expected=self.traces()
  changed=dict(actual);changed["p3"]=replace(actual["p3"],scales=(np.float32(1),))
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p3\.scale.float32_bits.*input="):target.compare_traces(changed,expected)
  changed=dict(actual);q=np.array(actual["p6"].q,copy=True);q.flat[3]=np.int8(int(q.flat[3])+1 if q.flat[3]<127 else 126);changed["p6"]=replace(actual["p6"],q=q,sha256=hashlib.sha256(q.tobytes()).hexdigest());q2=np.array(actual["p8"].q,copy=True);q2.flat[0]^=1;changed["p8"]=replace(actual["p8"],q=q2)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p6\.q\[.*max_error=1"):target.compare_traces(changed,expected)
  changed=dict(actual);q=np.array(actual["p13"].q,copy=True);q.view(np.uint16).flat[0]^=np.uint16(1);changed["p13"]=replace(actual["p13"],q=q)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p13\.q\["):target.compare_traces(changed,expected)
  changed=dict(actual);q=np.array(actual["p13"].q,copy=True);q.flat[0]=np.float16(np.nan);changed["p13"]=replace(actual["p13"],q=q)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p13\.q\.finite"):target.compare_traces(changed,expected)
 def test_skip_faults_localize_at_consumers_and_order_is_closed(self):
  actual,expected=self.traces()
  bad=dict(actual);bad["p9"]=replace(actual["p9"],skip_sha256=actual["p4"].sha256)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p9\.skip_sha256"):target.compare_traces(bad,expected)
  bad=dict(actual);bad["p11"]=replace(actual["p11"],skip_sha256=actual["p1"].sha256)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p11\.skip_sha256"):target.compare_traces(bad,expected)
  for bad in ({k:v for k,v in actual.items() if k!="p7"},{**{"p2":actual["p2"],"p1":actual["p1"]},**{k:v for k,v in actual.items() if k not in ("p1","p2")}}):
   with self.assertRaisesRegex(target.FullGraphMismatch,"pass_order"):target.compare_traces(bad,expected)
  with self.assertRaises(target.FullGraphError):target.compare_traces(actual,expected,int8_tolerance=1)
  with self.assertRaises(target.FullGraphError):target.compare_traces(actual,expected,float16_tolerance_ulp=1)
 def test_wrong_skip_values_first_change_their_consumers(self):
  _,expected=self.traces();original_b=b.run_vector_pass;original_c=c.run_vector_pass
  def wrong_p5(pid,value,layers,skip=None):
   if pid=="p9":skip={**skip,"q":np.roll(skip["q"],1,axis=0)}
   return original_b(pid,value,layers,skip)
  with mock.patch.object(target.segment_b,"run_vector_pass",side_effect=wrong_p5):bad=target.run_full_graph(self.manifest,self.la,self.lb,self.lc)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p9\."):target.compare_traces(bad,expected)
  def wrong_p2(pid,value,layers,skip=None):
   if pid=="p11":skip={**skip,"q":np.roll(skip["q"],1,axis=1)}
   return original_c(pid,value,layers,skip)
  with mock.patch.object(target.segment_c,"run_vector_pass",side_effect=wrong_p2):bad=target.run_full_graph(self.manifest,self.la,self.lb,self.lc)
  with self.assertRaisesRegex(target.FullGraphMismatch,r"p11\."):target.compare_traces(bad,expected)
if __name__=="__main__":unittest.main()

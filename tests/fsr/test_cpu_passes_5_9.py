from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

ROOT = Path(__file__).resolve().parents[2]
if os.fspath(ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(ROOT))
P7 = ROOT / "artifacts" / "p7-fsr-v07-r10a-20260922"
SIM = ROOT / "research" / "fsr4-hexagon" / "model" / "sim" / "fsr4_sim.py"
CONTRACT = ROOT / "tools" / "fsr" / "cpu_passes_5_9_contract.json"
CAPABLE = np is not None and P7.is_dir() and SIM.is_file()

if np is not None:
    import tools.fsr.cpu_passes_1_4 as first
    import tools.fsr.cpu_passes_5_9 as target
    from tools.fsr.pass_manifest import load_pass_manifest


def sha(array): return hashlib.sha256(array.tobytes()).hexdigest()


@unittest.skipUnless(CAPABLE, "F02b requires accepted P7 sources and fsr-extract NumPy")
class CpuPassesFiveToNineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_pass_manifest()
        cls.layers, cls.sim = target.load_bound_layers(cls.manifest, P7, SIM)
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def simulator_pass(self, pass_id, value, skip=None):
        calls = self.layers["_calls"]
        if pass_id == "p5": return self.sim["fasternet_uniform"](value,self.layers,"encoder3_ResidualBlock_1",*calls[4]["args"],float(target.P5_OUTPUT_SCALE),"32")
        if pass_id == "p6": return self.sim["k2s2b"](value,self.layers,"enc3_ds_weight","enc3_ds_bias",target.WEIGHT_SCALES["enc3_ds"],*calls[5]["args"])
        if pass_id == "p7": return self.sim["fasternet"](value,self.layers,"bottleneck_ResidualBlock_0",*calls[6]["args"],"64")
        if pass_id == "p8": return self.sim["fasternet"](value,self.layers,"bottleneck_ResidualBlock_1",*calls[7]["args"],"64")
        return self.sim["fnb_ct2d_add"](value,self.layers,"bottleneck_ResidualBlock_2",skip,*calls[8]["args"],"64","bottleneck_ct_weight","bottleneck_ct_bias","bottleneck_ct")

    def test_contract_bindings_and_scales(self):
        target.validate_contract_scales(self.contract)
        self.assertEqual("fsr-cpu-pass5-9-reference-v1",self.contract["schema_version"])
        self.assertEqual({"metric":"maximum-absolute-int8-lsb","tolerance":0,"rounding":"mathematical-half-away-from-zero","saturation":[-128,127]},self.contract["comparison"])
        for key in ("p7_receipt_sha256","weights_sha256","graph_sha256","simulator_sha256"):
            self.assertEqual(self.manifest["sources"][key],self.contract["sources"][key])
        for section in ("implementation","upstream_contract"):
            self.assertEqual(self.contract[section]["sha256"],hashlib.sha256((ROOT/self.contract[section]["path"]).read_bytes()).hexdigest())
        for pass_id in ("p6","p7","p8","p9"):
            changed=copy.deepcopy(self.contract); next(x for x in changed["passes"] if x["pass_id"]==pass_id)["scales"].reverse()
            with self.assertRaises(target.CpuReferenceError): target.validate_contract_scales(changed)
        mutations=[]
        for path,value in ((["schema_version"],"other"),(["comparison","metric"],"other"),(["comparison","tolerance"],1),(["comparison","tolerance"],False),(["comparison","rounding"],"ties-even"),(["comparison","saturation"],[-128,True])):
            changed=copy.deepcopy(self.contract); node=changed
            for key in path[:-1]: node=node[key]
            node[path[-1]]=value; mutations.append(changed)
        for value in ("0.019347405061125755",True):
            changed=copy.deepcopy(self.contract); changed["passes"][0]["scales"][0]=value; mutations.append(changed)
            changed=copy.deepcopy(self.contract); changed["passes"][0]["direct_input"]["scales"][0]=value; mutations.append(changed)
            changed=copy.deepcopy(self.contract); changed["passes"][4]["direct_input"]["skip_scales"][0]=value; mutations.append(changed)
        for field,value in (("shape",[True,4,32]),("dtype","uint8"),("sha256","0"*64)):
            changed=copy.deepcopy(self.contract); changed["passes"][0]["direct_input"][field]=value; mutations.append(changed)
        for field,value in (("output_shape",[4,True,32]),("output_dtype","uint8"),("output_sha256","0"*64),("output_scales",[True])):
            changed=copy.deepcopy(self.contract); changed["passes"][0]["direct_input"][field]=value; mutations.append(changed)
        for field,value in (("skip_shape",[4,False,32]),("skip_dtype","uint8"),("skip_sha256","0"*64)):
            changed=copy.deepcopy(self.contract); changed["passes"][4]["direct_input"][field]=value; mutations.append(changed)
        for changed in mutations:
            with self.subTest(mutation=changed):
                with self.assertRaises(target.CpuReferenceError): target.validate_contract_scales(changed)

    def test_fixed_chain_vector_scalar_and_simulator_zero_lsb(self):
        layers14,_=first.load_bound_layers(self.manifest,P7,SIM)
        p4=first.run_scalar_oracle(self.manifest,layers14)["p4"]
        vector=target.run_vector(p4,self.layers); scalar=target.run_scalar_oracle(p4,self.layers)
        simulated={}; value=p4
        for pass_id in ("p5","p6","p7","p8"):
            value=self.simulator_pass(pass_id,value); simulated[pass_id]=value
        simulated["p9"]=self.simulator_pass("p9",value,simulated["p5"])
        contracts={x["pass_id"]:x for x in self.contract["passes"]}
        previous=p4
        for pass_id in ("p5","p6","p7","p8","p9"):
            entry=contracts[pass_id]
            self.assertEqual(entry["chain_input_sha256"],sha(previous["q"]))
            for result in (vector[pass_id],scalar[pass_id],simulated[pass_id]):
                self.assertEqual(tuple(entry["shape"]),result["q"].shape); self.assertEqual(np.dtype(np.int8),result["q"].dtype)
                self.assertEqual(tuple(np.float32(x) for x in entry["scales"]),first.tensor_scales(result))
            self.assertTrue(np.array_equal(vector[pass_id]["q"],scalar[pass_id]["q"])); self.assertTrue(np.array_equal(vector[pass_id]["q"],simulated[pass_id]["q"]))
            self.assertEqual(entry["chain_output_sha256"],sha(vector[pass_id]["q"])); self.assertEqual(entry["minimum"],int(vector[pass_id]["q"].min())); self.assertEqual(entry["maximum"],int(vector[pass_id]["q"].max()))
            previous=scalar[pass_id]
        self.assertEqual(contracts["p9"]["chain_skip_sha256"],sha(scalar["p5"]["q"]))

    def assert_direct(self,pass_id):
        pass_entry=next(x for x in self.contract["passes"] if x["pass_id"]==pass_id); entry=pass_entry["direct_input"]
        value,skip=target.direct_inputs(pass_id)
        self.assertEqual(tuple(entry["shape"]),value["q"].shape); self.assertEqual(np.dtype(entry["dtype"]),value["q"].dtype); self.assertEqual(entry["sha256"],sha(value["q"])); self.assertEqual(tuple(np.float32(x) for x in entry["scales"]),first.tensor_scales(value))
        vector=target.run_vector_pass(pass_id,copy.deepcopy(value),self.layers,copy.deepcopy(skip)); scalar=target.run_scalar_pass(pass_id,copy.deepcopy(value),self.layers,copy.deepcopy(skip)); simulator=self.simulator_pass(pass_id,copy.deepcopy(value),copy.deepcopy(skip))
        expected_scales=tuple(np.float32(x) for x in entry["output_scales"])
        for result in (vector,scalar,simulator):
            self.assertEqual(tuple(entry["output_shape"]),result["q"].shape); self.assertEqual(np.dtype(entry["output_dtype"]),result["q"].dtype); self.assertEqual(expected_scales,first.tensor_scales(result))
        self.assertEqual(entry["output_sha256"],sha(scalar["q"])); self.assertTrue(np.array_equal(vector["q"],scalar["q"])); self.assertTrue(np.array_equal(vector["q"],simulator["q"]))
        if skip is not None:
            self.assertEqual(entry["skip_sha256"],sha(skip["q"])); self.assertEqual(tuple(entry["skip_shape"]),skip["q"].shape); self.assertEqual(np.dtype(entry["skip_dtype"]),skip["q"].dtype); self.assertEqual(tuple(np.float32(x) for x in entry["skip_scales"]),first.tensor_scales(skip))

    def test_direct_p5(self): self.assert_direct("p5")
    def test_direct_p6(self): self.assert_direct("p6")
    def test_direct_p7(self): self.assert_direct("p7")
    def test_direct_p8(self): self.assert_direct("p8")
    def test_direct_p9(self): self.assert_direct("p9")

    def test_group2_transpose_phases_and_skip_negatives(self):
        x=np.zeros((1,1,32),np.int8); x[:,:,0]=3; x[:,:,16]=5
        w=np.zeros((32,16,1,1),np.int8); w[0,0,0,0]=2; w[16,0,0,0]=7
        grouped=target._conv(x,w,groups=2); self.assertEqual(6,int(grouped[0,0,0])); self.assertEqual(35,int(grouped[0,0,16]))
        changed=x.copy(); changed[:,:,0]=9; changed_grouped=target._conv(changed,w,groups=2); self.assertEqual(int(grouped[0,0,16]),int(changed_grouped[0,0,16]))
        tx=np.asarray([[[2,3]]],np.int8); tw=np.asarray([[[[1,2],[3,4]]],[[[10,20],[30,40]]]],np.int8)
        expected=np.asarray([[[32],[64]],[[96],[128]]],np.int64); self.assertTrue(np.array_equal(expected,target._transpose(tx,tw))); self.assertTrue(np.array_equal(expected,target._transpose_scalar(tx,tw)))
        with self.assertRaisesRegex(target.CpuReferenceError,"IOHW"): target._transpose(tx,tw.transpose(1,0,2,3))
        value,skip=target.direct_inputs("p9"); original=target.run_vector_pass("p9",value,self.layers,skip)["q"]; wrong=copy.deepcopy(skip); wrong["q"]=np.roll(wrong["q"],1,axis=0)
        self.assertFalse(np.array_equal(original,target.run_vector_pass("p9",value,self.layers,wrong)["q"]))


if __name__ == "__main__": unittest.main()

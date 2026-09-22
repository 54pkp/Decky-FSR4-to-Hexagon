from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

P7 = REPOSITORY / "artifacts" / "p7-fsr-v07-r10a-20260922"
SIMULATOR = REPOSITORY / "research" / "fsr4-hexagon" / "model" / "sim" / "fsr4_sim.py"
CONTRACT_PATH = REPOSITORY / "tools" / "fsr" / "cpu_passes_1_4_contract.json"
CAPABLE = np is not None and P7.is_dir() and SIMULATOR.is_file()

if np is not None:
    from tools.fsr.cpu_passes_1_4 import (
        CpuReferenceError,
        P1_OUTPUT_SCALE,
        P2_OUTPUT_SCALE,
        WEIGHT_SCALES,
        _conv2d,
        _quantize,
        _scalar_conv,
        _scalar_quantize,
        direct_input,
        fixed_input,
        load_bound_layers,
        run_scalar_oracle,
        run_scalar_pass,
        run_vector,
        run_vector_pass,
        tensor_scales,
        validate_contract_scales,
    )
    from tools.fsr.pass_manifest import load_pass_manifest


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@unittest.skipUnless(CAPABLE, "F02a requires accepted ignored P7 sources and the isolated fsr-extract NumPy environment")
class CpuPassesOneToFourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_pass_manifest()
        cls.layers, cls.simulator = load_bound_layers(cls.manifest, P7, SIMULATOR)
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def simulator_pass(self, pass_id, value):
        calls = self.layers["_calls"]
        if pass_id == "p1":
            return self.simulator["convnext"](value, self.layers, *calls[0]["args"], float(P1_OUTPUT_SCALE), "encoder2_RB0")
        if pass_id == "p2":
            return self.simulator["convnext"](value, self.layers, *calls[1]["args"], float(P2_OUTPUT_SCALE), "encoder2_RB1")
        if pass_id == "p3":
            return self.simulator["k2s2b"](value, self.layers, "enc2_ds_weight", "enc2_ds_bias", WEIGHT_SCALES["enc2_ds"], *calls[2]["args"])
        return self.simulator["fasternet"](value, self.layers, "encoder3_ResidualBlock_0", *calls[3]["args"], "32")

    def test_contract_binds_sources_implementation_and_frozen_results(self):
        self.assertEqual("fsr-cpu-pass1-4-reference-v1", self.contract["schema_version"])
        self.assertEqual(0, self.contract["comparison"]["tolerance"])
        validate_contract_scales(self.contract)
        manifest_path = REPOSITORY / self.contract["manifest"]["path"]
        implementation_path = REPOSITORY / self.contract["implementation"]["path"]
        self.assertEqual(self.contract["manifest"]["sha256"], digest(manifest_path.read_bytes()))
        self.assertEqual(self.contract["implementation"]["sha256"], digest(implementation_path.read_bytes()))
        for field in ("p7_receipt_sha256", "weights_sha256", "graph_sha256", "simulator_commit", "simulator_sha256"):
            self.assertEqual(self.manifest["sources"][field], self.contract["sources"][field])

        source = fixed_input(self.manifest)
        self.assertEqual(np.dtype(np.int8), source["q"].dtype)
        self.assertLess(int(source["q"].min()), 0)
        self.assertGreater(int(source["q"].max()), 0)
        self.assertEqual(self.contract["fixed_input"]["sha256"], digest(source["q"].tobytes()))
        oracle = run_scalar_oracle(self.manifest, self.layers)
        for entry in self.contract["passes"]:
            output = oracle[entry["pass_id"]]["q"]
            self.assertEqual(entry["shape"], list(output.shape))
            self.assertEqual(entry["dtype"], str(output.dtype))
            self.assertEqual(entry["output_sha256"], digest(output.tobytes()))
            self.assertEqual(entry["minimum"], int(output.min()))
            self.assertEqual(entry["maximum"], int(output.max()))

    def test_vector_scalar_and_authenticated_simulator_are_zero_lsb(self):
        vector_outputs = run_vector(self.manifest, self.layers)
        oracle_outputs = run_scalar_oracle(self.manifest, self.layers)
        value = fixed_input(self.manifest)
        simulated = {}
        for pass_id in ("p1", "p2", "p3", "p4"):
            value = self.simulator_pass(pass_id, value)
            simulated[pass_id] = value

        contracts = {entry["pass_id"]: entry for entry in self.contract["passes"]}
        for pass_id in ("p1", "p2", "p3", "p4"):
            with self.subTest(pass_id=pass_id):
                expected_shape = tuple(contracts[pass_id]["shape"])
                expected_scales = tuple(np.float32(value) for value in contracts[pass_id]["scales"])
                for name, result in (("vector", vector_outputs[pass_id]), ("scalar", oracle_outputs[pass_id]), ("simulator", simulated[pass_id])):
                    with self.subTest(path=name):
                        self.assertEqual(expected_shape, result["q"].shape)
                        self.assertEqual(np.dtype(np.int8), result["q"].dtype)
                        self.assertEqual(expected_scales, tensor_scales(result))
                vector = vector_outputs[pass_id]["q"].astype(np.int16)
                oracle = oracle_outputs[pass_id]["q"].astype(np.int16)
                simulator = simulated[pass_id]["q"].astype(np.int16)
                self.assertEqual(0, int(np.max(np.abs(vector - oracle))))
                self.assertEqual(0, int(np.max(np.abs(vector - simulator))))
                self.assertEqual(-128, int(vector.min()))
                self.assertEqual(127, int(vector.max()))

        for pass_id in ("p3", "p4"):
            changed = copy.deepcopy(self.contract)
            entry = next(item for item in changed["passes"] if item["pass_id"] == pass_id)
            entry["scales"].reverse()
            with self.subTest(swapped_scales=pass_id):
                with self.assertRaisesRegex(CpuReferenceError, "output scales mismatch"):
                    validate_contract_scales(changed)

    def test_each_pass_accepts_its_frozen_input_independently(self):
        oracle_outputs = run_scalar_oracle(self.manifest, self.layers)
        values = {"p1": fixed_input(self.manifest)}
        values["p2"] = oracle_outputs["p1"]
        values["p3"] = oracle_outputs["p2"]
        values["p4"] = oracle_outputs["p3"]
        contracts = {entry["pass_id"]: entry for entry in self.contract["passes"]}
        for pass_id in ("p1", "p2", "p3", "p4"):
            with self.subTest(pass_id=pass_id):
                value = values[pass_id]
                self.assertEqual(contracts[pass_id]["input_sha256"], digest(value["q"].tobytes()))
                vector = run_vector_pass(pass_id, copy.deepcopy(value), self.layers)
                oracle = run_scalar_pass(pass_id, copy.deepcopy(value), self.layers)
                self.assertTrue(np.array_equal(vector["q"], oracle["q"]))
                self.assertEqual(contracts[pass_id]["output_sha256"], digest(vector["q"].tobytes()))

    def test_round_half_away_signedness_and_saturation_boundaries(self):
        values = np.asarray([-200.0, -128.6, -128.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 126.5, 127.5, 200.0], dtype=np.float32)
        expected = np.asarray([-128, -128, -128, -3, -2, -1, 1, 2, 3, 127, 127, 127], dtype=np.int8)
        self.assertTrue(np.array_equal(expected, _quantize(values)))
        scalar = np.asarray([_scalar_quantize(value) for value in values], dtype=np.int8)
        self.assertTrue(np.array_equal(expected, scalar))

        positives = []
        expected_positive = []
        for tie, below_result in ((np.float32(0.5), 0), (np.float32(1.5), 1)):
            positives.extend([np.nextafter(tie, np.float32(0)), tie, np.nextafter(tie, np.float32(np.inf))])
            expected_positive.extend([below_result, below_result + 1, below_result + 1])
        boundary = np.asarray(positives + [-value for value in positives], dtype=np.float32)
        boundary_expected = np.asarray(expected_positive + [-value for value in expected_positive], dtype=np.int8)
        self.assertTrue(np.array_equal(boundary_expected, _quantize(boundary)))
        scalar_boundary = np.asarray([_scalar_quantize(value) for value in boundary], dtype=np.int8)
        self.assertTrue(np.array_equal(boundary_expected, scalar_boundary))
        simulator_boundary = self.simulator["clamp_s8"](self.simulator["round_half_away"](boundary))
        self.assertFalse(np.array_equal(boundary_expected, simulator_boundary), "pinned simulator has a known float32 pre-tie rounding limitation")

    def test_stride_halves_partial_concat_and_padding_contracts(self):
        vector_outputs = run_vector(self.manifest, self.layers)
        oracle_outputs = run_scalar_oracle(self.manifest, self.layers)
        p3 = vector_outputs["p3"]
        self.assertEqual((4, 4, 32), p3["q"].shape)
        self.assertEqual(np.float32(0.015390855260193348), p3["s0"])
        self.assertEqual(np.float32(0.018884973600506783), p3["s1"])
        self.assertTrue(np.array_equal(p3["q"][:, :, :16], oracle_outputs["p3"]["q"][:, :, :16]))
        self.assertTrue(np.array_equal(p3["q"][:, :, 16:], oracle_outputs["p3"]["q"][:, :, 16:]))

        signed = np.asarray([[[-1], [2]], [[3], [4]]], dtype=np.int8)
        kernel = np.ones((1, 1, 3, 3), dtype=np.int8)
        expected_padded = np.full((2, 2, 1), 8, dtype=np.int64)
        self.assertTrue(np.array_equal(expected_padded, _conv2d(signed, kernel, pad=1)))
        self.assertTrue(np.array_equal(expected_padded, _scalar_conv(signed, kernel, pad=1)))

        changed = copy.deepcopy(oracle_outputs["p3"])
        changed["q"] = changed["q"].copy()
        changed["q"][:, :, 16:] = np.bitwise_xor(changed["q"][:, :, 16:], np.int8(1))
        original_p4 = run_vector_pass("p4", oracle_outputs["p3"], self.layers)["q"]
        changed_p4 = run_vector_pass("p4", changed, self.layers)["q"]
        self.assertFalse(np.array_equal(original_p4, changed_p4), "p4 must concatenate and consume the passthrough half")

    def assert_direct_pass(self, pass_id):
        entry = next(item for item in self.contract["passes"] if item["pass_id"] == pass_id)
        direct = entry["direct_input"]
        value = direct_input(pass_id)
        self.assertEqual(tuple(direct["shape"]), value["q"].shape)
        self.assertEqual(np.dtype(direct["dtype"]), value["q"].dtype)
        self.assertEqual(direct["sha256"], digest(value["q"].tobytes()))
        self.assertEqual(tuple(np.float32(item) for item in direct["scales"]), tensor_scales(value))
        vector = run_vector_pass(pass_id, copy.deepcopy(value), self.layers)
        oracle = run_scalar_pass(pass_id, copy.deepcopy(value), self.layers)
        simulator = self.simulator_pass(pass_id, copy.deepcopy(value))
        self.assertEqual(direct["output_sha256"], digest(oracle["q"].tobytes()))
        self.assertTrue(np.array_equal(vector["q"], oracle["q"]))
        self.assertTrue(np.array_equal(vector["q"], simulator["q"]))

    def test_direct_p1(self):
        self.assert_direct_pass("p1")

    def test_direct_p2(self):
        self.assert_direct_pass("p2")

    def test_direct_p3(self):
        self.assert_direct_pass("p3")

    def test_direct_p4(self):
        self.assert_direct_pass("p4")

    def test_direct_p4_does_not_invoke_any_full_chain(self):
        with mock.patch("tools.fsr.cpu_passes_1_4.run_vector", side_effect=AssertionError("full vector chain forbidden")), \
                mock.patch("tools.fsr.cpu_passes_1_4.run_scalar_oracle", side_effect=AssertionError("full scalar chain forbidden")):
            self.assert_direct_pass("p4")


if __name__ == "__main__":
    unittest.main()

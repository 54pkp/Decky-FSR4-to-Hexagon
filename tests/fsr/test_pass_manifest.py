from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import shutil
import sys
import tempfile
import unittest

try:
    import numpy as np
except ModuleNotFoundError:
    np = None


REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

from tools.fsr.pass_manifest import (
    MANIFEST_PATH,
    PassManifestError,
    execute_bound_simulator,
    load_pass_manifest,
    verify_bound_sources,
)


P7 = REPOSITORY / "artifacts" / "p7-fsr-v07-r10a-20260922"
SIMULATOR = REPOSITORY / "research" / "fsr4-hexagon" / "model" / "sim" / "fsr4_sim.py"
EXTERNAL_AVAILABLE = P7.is_dir() and SIMULATOR.is_file()


class PassManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_pass_manifest()

    def write_and_load(self, value):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "passes.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_pass_manifest(path)

    def test_all_thirteen_passes_are_closed_chained_and_explicitly_unknown(self):
        self.assertEqual([f"p{index}" for index in range(1, 14)], [item["pass_id"] for item in self.manifest["passes"]])
        self.assertEqual([8, 8, 16], self.manifest["fixed_input"]["shape"])
        self.assertEqual("HWC", self.manifest["fixed_input"]["layout"])
        self.assertEqual("WHCN", self.manifest["layout_conventions"]["graph_decl_logical"])
        self.assertEqual("KH_KW_CIN_COUT", self.manifest["layout_conventions"]["source_weight_logical"])
        self.assertEqual("OIHW", self.manifest["layout_conventions"]["cpu_regular_weight"])
        self.assertEqual("IOHW", self.manifest["layout_conventions"]["cpu_transposed_weight"])
        self.assertEqual("unknown", self.manifest["quantization_conventions"]["zero_point"])
        self.assertIn("not-independently-verified", self.manifest["quantization_conventions"]["provenance"])
        for item in self.manifest["passes"]:
            self.assertTrue(item["weights"])
            self.assertEqual("unknown", item["independent_expected"]["status"])
            self.assertIsNone(item["independent_expected"]["source"])
            self.assertIsNone(item["independent_expected"]["sha256"])
        self.assertEqual(["p8", "p5"], [item["source"] for item in self.manifest["passes"][8]["inputs"]])
        self.assertEqual(["p10", "p2"], [item["source"] for item in self.manifest["passes"][10]["inputs"]])
        self.assertEqual([16, 16, 8], self.manifest["passes"][-1]["output"]["shape"])
        self.assertEqual("float16", self.manifest["passes"][-1]["output"]["dtype"])

    def test_semantic_mutations_are_rejected(self):
        cases = []
        value = copy.deepcopy(self.manifest); value["unknown"] = True
        cases.append((value, "unknown field"))
        value = copy.deepcopy(self.manifest); value["passes"].pop()
        cases.append((value, "exactly p1 through p13"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["operator"] = "Other"
        cases.append((value, "identity/operator mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][3]["inputs"][0]["source"] = "p1"
        cases.append((value, "input topology mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][1]["inputs"][0]["source"] = "fixed-input"
        cases.append((value, "input topology mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][12]["output"]["shape"] = [15, 16, 8]
        cases.append((value, "fixed shape/dtype/quantization mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["weights"] = []
        cases.append((value, "weights must be non-empty"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["weights"].pop()
        cases.append((value, "fixed alias/shape/layout set"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["weights"][0]["key"] = self.manifest["passes"][1]["weights"][0]["key"]
        cases.append((value, "fixed alias/shape/layout set"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["weights"][0]["layout"] = "WHCN"
        cases.append((value, "format mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["quantization"]["output"] = "split-half-int8"
        cases.append((value, "quantization contract mismatch"))
        value = copy.deepcopy(self.manifest); value["passes"][0]["independent_expected"] = {"status": "known", "source": "same-simulator", "sha256": "0" * 64, "reason": "bad"}
        cases.append((value, "must remain explicit unknown"))
        value = copy.deepcopy(self.manifest); value["fixed_input"]["sha256"] = "0" * 64
        cases.append((value, "fixed_input SHA-256"))
        value = copy.deepcopy(self.manifest); value["sources"]["p7_receipt_sha256"] = "0" * 64
        cases.append((value, "current artifact index"))
        value = copy.deepcopy(self.manifest); value["quantization_conventions"]["zero_point"] = 0
        cases.append((value, "overstates independent verification"))
        value = copy.deepcopy(self.manifest); value["passes"][1]["call_index"] = True
        cases.append((value, "identity/operator mismatch"))
        value = copy.deepcopy(self.manifest); value["limitations"]["pass1_13_implemented"] = 0
        cases.append((value, "must be boolean"))
        value = copy.deepcopy(self.manifest); value["limitations"]["independent_expected_available"] = 1
        cases.append((value, "must be boolean"))
        for invalid in (["p1"], {"pass": "p1"}):
            value = copy.deepcopy(self.manifest); value["passes"][1]["inputs"][0]["source"] = invalid
            cases.append((value, "source must be a string"))
        for invalid in (["uniform-int8"], {"format": "uniform-int8"}):
            value = copy.deepcopy(self.manifest); value["passes"][0]["inputs"][0]["quantization"] = invalid
            cases.append((value, "tensor format mismatch"))

        for value, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(PassManifestError, diagnostic):
                    self.write_and_load(value)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(PassManifestError, "duplicate object key"):
                load_pass_manifest(path)

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "accepted ignored P7 material and pinned simulator are not present")
    def test_bound_ignored_sources_match_hashes_and_graph_calls(self):
        verify_bound_sources(self.manifest, P7, SIMULATOR)
        graph = json.loads((P7 / "graph_spec.json").read_text(encoding="utf-8"))
        self.assertEqual(13, len(graph["calls"]))
        for item, call in zip(self.manifest["passes"], graph["calls"]):
            self.assertEqual(call["op"], item["operator"])
            self.assertEqual(call["args"], item["quantization"]["call_arguments"])

        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "sim.py"
            changed.write_bytes(SIMULATOR.read_bytes() + b"\n# changed\n")
            with self.assertRaisesRegex(PassManifestError, "byte count mismatch"):
                verify_bound_sources(self.manifest, P7, changed)

        with tempfile.TemporaryDirectory() as directory:
            changed_p7 = Path(directory)
            for name in ("fsr4_quality_weights.npz", "graph_spec.json"):
                shutil.copyfile(P7 / name, changed_p7 / name)
            receipt = json.loads((P7 / "intake_receipt.json").read_text(encoding="utf-8"))
            receipt["outputs"]["graph_spec.json"]["byte_count"] += 1
            receipt_payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (changed_p7 / "intake_receipt.json").write_bytes(receipt_payload)
            manifest = copy.deepcopy(self.manifest)
            import hashlib
            manifest["sources"]["p7_receipt_sha256"] = hashlib.sha256(receipt_payload).hexdigest()
            with self.assertRaisesRegex(PassManifestError, "receipt output binding mismatch"):
                verify_bound_sources(manifest, changed_p7, SIMULATOR)

    @unittest.skipUnless(EXTERNAL_AVAILABLE and np is not None, "weight inventory requires the isolated fsr-extract NumPy environment")
    def test_simulator_derived_weight_alias_shapes_match_inventory(self):
        verify_bound_sources(self.manifest, P7, SIMULATOR)
        namespace = execute_bound_simulator(self.manifest, P7, SIMULATOR)
        namespace["ART"] = P7
        layers = namespace["load_layers"]()
        checked = []
        for item in self.manifest["passes"]:
            for weight in item["weights"]:
                with self.subTest(pass_id=item["pass_id"], key=weight["key"]):
                    self.assertIn(weight["key"], layers)
                    self.assertEqual(weight["shape"], list(layers[weight["key"]].shape))
                    self.assertEqual(weight["dtype"], str(layers[weight["key"]].dtype))
                    checked.append((item["pass_id"], weight["key"]))
        self.assertEqual(sum(len(item["weights"]) for item in self.manifest["passes"]), len(checked))

    @unittest.skipUnless(EXTERNAL_AVAILABLE, "accepted ignored P7 material is not present")
    def test_hashed_source_bytes_ignore_matching_timestamp_and_size_pyc(self):
        benign = b"RESULT = 'source'\n"
        malicious = b"RESULT = 'cached'\n"
        self.assertEqual(len(benign), len(malicious))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sim.py"
            source.write_bytes(malicious)
            timestamp = 1_700_000_000
            os.utime(source, (timestamp, timestamp))
            py_compile.compile(os.fspath(source), doraise=True)
            source.write_bytes(benign)
            os.utime(source, (timestamp, timestamp))

            spec = importlib.util.spec_from_file_location("f01_adversarial_cache", source)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            cached_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cached_module)
            self.assertEqual("cached", cached_module.RESULT)

            manifest = copy.deepcopy(self.manifest)
            import hashlib
            manifest["sources"]["simulator_sha256"] = hashlib.sha256(benign).hexdigest()
            manifest["sources"]["simulator_byte_count"] = len(benign)
            namespace = execute_bound_simulator(manifest, P7, source)
            self.assertEqual("source", namespace["RESULT"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
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

if np is not None:
    from tools.fsr.pass0_check import (
        GRAPH_NAME,
        NPZ_NAME,
        P7_RECEIPT_NAME,
        Pass0CheckError,
        Pass0Contract,
        fixed_input,
        run_pass0_check,
        scalar_pass0,
    )


SIMULATOR = b'''import numpy as np
def pass0(x, layers):
    from tools.fsr.pass0_check import scalar_pass0
    return {"q": scalar_pass0(x, layers["pass0_weight_fkyxc"], layers["pass0_bias"], layers["_pass0_scale"]),
            "s": layers["_pass0_scale"]}
'''

CACHE_SIMULATOR_TEMPLATE = '''import numpy as np
CACHE_MARKER = "{marker}"
def pass0(x, layers):
    from tools.fsr.pass0_check import scalar_pass0
    q = scalar_pass0(x, layers["pass0_weight_fkyxc"], layers["pass0_bias"], layers["_pass0_scale"])
    if CACHE_MARKER == "cache!":
        q[:] = 0
    return {{"q": q, "s": layers["_pass0_scale"]}}
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(np is not None, "P8 numerical tests require the isolated NumPy environment")
class Pass0CheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.p7 = self.root / "p7"
        self.p7.mkdir()
        self.simulator = self.root / "fsr4_sim.py"
        self.simulator.write_bytes(SIMULATOR)
        self.output = self.root / "p8.json"
        self.contract = Pass0Contract(
            source_commit="source-fixture",
            simulator_commit="sim-fixture",
            simulator_sha256=hashlib.sha256(SIMULATOR).hexdigest(),
            max_lsb_error=0,
        )
        weights = (np.arange(16 * 2 * 2 * 8, dtype=np.float32).reshape(16, 2, 2, 8) % 13 - 6) / 64
        weights[:, :, :, 7] = 0
        bias = np.linspace(-0.1, 0.1, 16, dtype=np.float32)
        scales = np.full(77, np.float32(0.025), dtype=np.float32)
        np.savez(self.p7 / NPZ_NAME, pass0_weight_fkyxc=weights, pass0_bias=bias, bin_scale_table=scales)
        (self.p7 / GRAPH_NAME).write_text(
            json.dumps(
                {
                    "pass0": {
                        "scale": float(scales[0]),
                        "weight_layout": "[f,ky,kx,c(8, ch7=0)]",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.write_receipt()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_receipt(self, **changes) -> None:
        receipt = {
            "schema_version": "p7-fsr-intake-receipt-v1",
            "extraction_gate": "passed",
            "source": {"commit": "source-fixture"},
            "extractor": {"commit": "sim-fixture"},
            "outputs": {},
        }
        for name in (NPZ_NAME, GRAPH_NAME):
            path = self.p7 / name
            receipt["outputs"][name] = {"byte_count": path.stat().st_size, "sha256": digest(path)}
        receipt.update(changes)
        (self.p7 / P7_RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")

    def execute(self, **kwargs):
        return run_pass0_check(self.p7, self.simulator, self.output, contract=self.contract, **kwargs)

    def test_success_writes_complete_receipt(self):
        receipt = self.execute()
        saved = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(saved, receipt)
        self.assertEqual(receipt["input"]["layout"], "HWC")
        self.assertEqual(receipt["input"]["shape"], [4, 6, 8])
        self.assertEqual(receipt["output"]["shape"], [2, 3, 16])
        self.assertEqual(receipt["output"]["dtype"], "int8")
        self.assertEqual(receipt["output"]["max_int8_lsb_difference"], 0)
        self.assertEqual(receipt["output"]["predefined_max_int8_lsb_difference"], 0)
        self.assertTrue(receipt["validation_gates"]["upstream_repeat_is_bit_exact"])
        self.assertTrue(receipt["validation_gates"]["effective_channel_0_single_point_changes_output"])
        self.assertTrue(receipt["validation_gates"]["channel_7_finite_poison_is_invariant"])
        self.assertTrue(receipt["validation_gates"]["weight_channel_7_is_all_zero"])
        self.assertLessEqual(receipt["output"]["minimum"], receipt["output"]["maximum"])
        self.assertIsInstance(receipt["output"]["negative_saturation_count"], int)
        self.assertIsInstance(receipt["output"]["positive_saturation_count"], int)
        self.assertEqual(receipt["parameters"]["quantization_scale"], float(np.float32(0.025)))
        self.assertEqual(receipt["limitations"]["official_golden"], "not_available")

    def test_receipt_or_artifact_hash_mismatch_is_rejected(self):
        with self.subTest("receipt"):
            self.write_receipt(schema_version="wrong")
            with self.assertRaisesRegex(Pass0CheckError, "schema or extraction gate"):
                self.execute()
        self.write_receipt()
        with (self.p7 / GRAPH_NAME).open("ab") as stream:
            stream.write(b" ")
        with self.subTest("artifact"):
            with self.assertRaisesRegex(Pass0CheckError, "receipt/artifact hash mismatch"):
                self.execute()
        self.assertFalse(self.output.exists())

    def test_wrong_simulator_is_rejected(self):
        self.simulator.write_bytes(SIMULATOR + b"# changed\n")
        with self.assertRaisesRegex(Pass0CheckError, "simulator SHA-256 mismatch"):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_hashed_simulator_source_bytes_bypass_valid_malicious_pyc(self):
        malicious = CACHE_SIMULATOR_TEMPLATE.format(marker="cache!").encode("utf-8")
        source = CACHE_SIMULATOR_TEMPLATE.format(marker="source").encode("utf-8")
        self.assertEqual(len(malicious), len(source))
        fixed_timestamp = 1_700_000_000
        self.simulator.write_bytes(malicious)
        os.utime(self.simulator, (fixed_timestamp, fixed_timestamp))
        py_compile.compile(os.fspath(self.simulator), doraise=True)
        self.simulator.write_bytes(source)
        os.utime(self.simulator, (fixed_timestamp, fixed_timestamp))

        spec = importlib.util.spec_from_file_location("p8_cache_probe", self.simulator)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        cached_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cached_module)
        self.assertEqual(cached_module.CACHE_MARKER, "cache!")

        self.contract = Pass0Contract(
            source_commit="source-fixture",
            simulator_commit="sim-fixture",
            simulator_sha256=hashlib.sha256(source).hexdigest(),
            max_lsb_error=0,
        )
        receipt = self.execute()
        self.assertEqual(receipt["simulator"]["sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(receipt["result"], "passed")

    def test_artifact_replacement_during_runner_uses_verified_snapshots(self):
        original_archive_hash = digest(self.p7 / NPZ_NAME)
        original_graph_hash = digest(self.p7 / GRAPH_NAME)
        replaced = False

        def replacing_runner(sample, layers):
            nonlocal replaced
            if not replaced:
                (self.p7 / NPZ_NAME).write_bytes(b"replacement NPZ bytes")
                (self.p7 / GRAPH_NAME).write_bytes(b"replacement graph bytes")
                replaced = True
            return {
                "q": scalar_pass0(
                    sample,
                    layers["pass0_weight_fkyxc"],
                    layers["pass0_bias"],
                    layers["_pass0_scale"],
                ),
                "s": layers["_pass0_scale"],
            }

        receipt = self.execute(upstream_runner=replacing_runner)
        self.assertEqual(receipt["p7"]["weights"]["sha256"], original_archive_hash)
        self.assertEqual(receipt["p7"]["graph"]["sha256"], original_graph_hash)
        self.assertNotEqual(digest(self.p7 / NPZ_NAME), original_archive_hash)
        self.assertNotEqual(digest(self.p7 / GRAPH_NAME), original_graph_hash)

    def test_scalar_pass0_has_hand_computed_fkyxc_rounding_and_saturation(self):
        sample = np.zeros((2, 2, 8), dtype=np.float16)
        sample[0, 0, 0] = np.float16(1)
        sample[0, 1, 1] = np.float16(2)
        sample[1, 0, 2] = np.float16(3)
        sample[1, 1, 3] = np.float16(4)
        weight = np.zeros((16, 2, 2, 8), dtype=np.float32)
        mapped = ((0, 0, 0, 1), (0, 1, 1, 10), (1, 0, 2, 100), (1, 1, 3, 1000))
        for ky, kx, channel, value in mapped:
            weight[0, ky, kx, channel] = np.float32(value)
            weight[1, ky, kx, channel] = np.float32(-value)
        for ky, kx, channel, value in ((0, 0, 0, 1), (0, 1, 1, 2), (1, 0, 2, 3), (1, 1, 3, 4)):
            weight[4, ky, kx, channel] = np.float32(value)
        bias = np.zeros(16, dtype=np.float32)
        bias[2] = np.float32(0.5)
        bias[3] = np.float32(-0.5)

        output = scalar_pass0(sample, weight, bias, 1.0)
        self.assertEqual(output.shape, (1, 1, 16))
        self.assertEqual(int(output[0, 0, 0]), 127)
        self.assertEqual(int(output[0, 0, 1]), -128)
        self.assertEqual(int(output[0, 0, 2]), 1)
        self.assertEqual(int(output[0, 0, 3]), -1)
        self.assertEqual(int(output[0, 0, 4]), 30)
        np.testing.assert_array_equal(output[0, 0, 5:], np.zeros(11, dtype=np.int8))

    def test_layout_shape_and_nonfinite_inputs_are_rejected(self):
        with self.subTest("layout"):
            with self.assertRaisesRegex(Pass0CheckError, "layout must be HWC"):
                self.execute(layout="CHW")
        with self.subTest("shape"):
            with self.assertRaisesRegex(Pass0CheckError, "shape must be HWC"):
                self.execute(sample=np.zeros((4, 6, 7), dtype=np.float16))
        invalid = fixed_input()
        invalid[0, 0, 0] = np.float16(np.nan)
        with self.subTest("non-finite"):
            with self.assertRaisesRegex(Pass0CheckError, "non-finite"):
                self.execute(sample=invalid)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(Pass0CheckError, "already exists"):
            self.execute()
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep")

    def test_one_lsb_upstream_and_independent_mismatch_is_rejected_without_receipt(self):
        def changed_upstream(sample, layers):
            value = scalar_pass0(
                sample,
                layers["pass0_weight_fkyxc"],
                layers["pass0_bias"],
                layers["_pass0_scale"],
            )
            original = int(value[0, 0, 0])
            value[0, 0, 0] = np.int8(original - 1 if original == 127 else original + 1)
            return {"q": value, "s": layers["_pass0_scale"]}

        with self.assertRaisesRegex(Pass0CheckError, "1 LSB exceeds 0"):
            self.execute(upstream_runner=changed_upstream)
        self.assertFalse(self.output.exists())

    def test_nonzero_channel_7_weight_is_rejected(self):
        archive = self.p7 / NPZ_NAME
        with np.load(archive, allow_pickle=False) as source:
            values = {name: np.array(source[name], copy=True) for name in source.files}
        values["pass0_weight_fkyxc"][0, 0, 0, 7] = np.float32(1.0)
        np.savez(archive, **values)
        self.write_receipt()
        with self.assertRaisesRegex(Pass0CheckError, "channel-7 weights must all be zero"):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_nondeterministic_upstream_is_rejected(self):
        calls = 0

        def nondeterministic(sample, layers):
            nonlocal calls
            value = scalar_pass0(sample, layers["pass0_weight_fkyxc"], layers["pass0_bias"], layers["_pass0_scale"])
            calls += 1
            if calls == 2:
                original = int(value[0, 0, 0])
                value[0, 0, 0] = np.int8(original - 1 if original == 127 else original + 1)
            return {"q": value, "s": layers["_pass0_scale"]}

        with self.assertRaisesRegex(Pass0CheckError, "not deterministic"):
            self.execute(upstream_runner=nondeterministic)
        self.assertFalse(self.output.exists())

    def test_effective_channel_insensitive_upstream_is_rejected(self):
        baseline = fixed_input()

        def insensitive(sample, layers):
            value = scalar_pass0(baseline, layers["pass0_weight_fkyxc"], layers["pass0_bias"], layers["_pass0_scale"])
            return {"q": value, "s": layers["_pass0_scale"]}

        with self.assertRaisesRegex(Pass0CheckError, "mutation did not change"):
            self.execute(upstream_runner=insensitive)
        self.assertFalse(self.output.exists())

    def test_channel_7_sensitive_upstream_is_rejected(self):
        def poisoned_sensitive(sample, layers):
            value = scalar_pass0(sample, layers["pass0_weight_fkyxc"], layers["pass0_bias"], layers["_pass0_scale"])
            if np.any(sample[:, :, 7] != 0):
                original = int(value[0, 0, 0])
                value[0, 0, 0] = np.int8(original - 1 if original == 127 else original + 1)
            return {"q": value, "s": layers["_pass0_scale"]}

        with self.assertRaisesRegex(Pass0CheckError, "poison changed"):
            self.execute(upstream_runner=poisoned_sensitive)
        self.assertFalse(self.output.exists())

    def test_dangling_output_link_is_treated_as_existing(self):
        try:
            os.symlink(self.root / "missing-target.json", self.output)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        self.assertFalse(self.output.exists())
        self.assertTrue(os.path.lexists(self.output))
        with self.assertRaisesRegex(Pass0CheckError, "already exists"):
            self.execute()

    def test_upstream_output_shape_is_rejected(self):
        def wrong_shape(sample, layers):
            return {"q": np.zeros((1, 1, 16), dtype=np.int8), "s": layers["_pass0_scale"]}

        with self.assertRaisesRegex(Pass0CheckError, "output shape/dtype"):
            self.execute(upstream_runner=wrong_shape)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

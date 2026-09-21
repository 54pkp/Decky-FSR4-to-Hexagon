from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    import numpy as np
    import onnx
    from tools.reference import small_graph
except ImportError:
    np = None
    onnx = None
    small_graph = None


EXPECTED_MODEL_SHA256 = "f89d2af81c2a9bbde23a7cf4b2a8ee2614535f491ab7f259ac3151328f4f42d4"


@unittest.skipUnless(
    small_graph is not None,
    "requires the pinned tools/reference ONNX CPU environment",
)
class SmallGraphTests(unittest.TestCase):
    def test_checked_in_model_is_reproducible_and_has_fixed_sha256(self):
        checked_in = small_graph.FIXTURE_PATH.read_bytes()
        rebuilt = small_graph.model_bytes()
        self.assertEqual(rebuilt, checked_in)
        self.assertEqual(EXPECTED_MODEL_SHA256, hashlib.sha256(checked_in).hexdigest())

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "rebuilt.onnx"
            digest = small_graph.write_model(output)
            self.assertEqual(EXPECTED_MODEL_SHA256, digest)
            self.assertEqual(checked_in, output.read_bytes())

    def test_onnx_checker_and_exact_graph_contract_pass(self):
        model = small_graph.load_and_validate_model()
        onnx.checker.check_model(model)
        self.assertEqual(
            ["Conv", "Add", "Relu"],
            [node.op_type for node in model.graph.node],
        )
        self.assertEqual(small_graph.INPUT_NAME, model.graph.node[0].input[0])
        self.assertEqual(small_graph.OUTPUT_NAME, model.graph.node[-1].output[0])

    def test_fixed_names_shapes_and_dtypes(self):
        self.assertEqual("reference_input", small_graph.INPUT_NAME)
        self.assertEqual("reference_output", small_graph.OUTPUT_NAME)
        self.assertEqual((1, 1, 4, 4), small_graph.INPUT_SHAPE)
        self.assertEqual((1, 1, 4, 4), small_graph.OUTPUT_SHAPE)
        self.assertEqual(np.dtype(np.float32), small_graph.DTYPE)
        for value in small_graph.fixed_inputs().values():
            self.assertEqual(small_graph.INPUT_SHAPE, value.shape)
            self.assertEqual(np.dtype(np.float32), value.dtype)

    def test_three_inputs_match_independent_numpy_formula_elementwise_on_cpu(self):
        self.assertEqual(0.0, small_graph.RELATIVE_TOLERANCE)
        self.assertEqual(1e-6, small_graph.ABSOLUTE_TOLERANCE)
        cases = small_graph.fixed_inputs()
        self.assertEqual({"zero", "pattern", "seeded_nonzero"}, set(cases))
        self.assertTrue(np.any(cases["pattern"] != 0.0))
        self.assertTrue(np.any(cases["seeded_nonzero"] != 0.0))

        for name, value in cases.items():
            with self.subTest(name=name):
                expected = small_graph.numpy_expected(value)
                result = small_graph.run_cpu(value)
                self.assertEqual(("CPUExecutionProvider",), result.providers)
                self.assertEqual(small_graph.OUTPUT_SHAPE, result.output.shape)
                self.assertEqual(np.dtype(np.float32), result.output.dtype)
                np.testing.assert_allclose(
                    result.output,
                    expected,
                    rtol=small_graph.RELATIVE_TOLERANCE,
                    atol=small_graph.ABSOLUTE_TOLERANCE,
                )

    def test_changing_input_changes_designated_output(self):
        baseline = small_graph.fixed_inputs()["zero"]
        changed = baseline.copy()
        changed[0, 0, 1, 1] = np.float32(1.0)
        baseline_output = small_graph.run_cpu(baseline).output
        changed_output = small_graph.run_cpu(changed).output
        self.assertFalse(np.array_equal(baseline_output, changed_output))
        self.assertNotEqual(
            baseline_output[0, 0, 1, 1],
            changed_output[0, 0, 1, 1],
        )

    def test_wrong_shape_dtype_and_nonfinite_inputs_are_rejected_before_runtime(self):
        invalid = (
            np.zeros((1, 1, 3, 4), dtype=np.float32),
            np.zeros(small_graph.INPUT_SHAPE, dtype=np.float64),
        )
        for value in invalid:
            with self.subTest(shape=value.shape, dtype=value.dtype):
                with self.assertRaises(small_graph.ReferenceError):
                    small_graph.run_cpu(value)

        for bad in (np.nan, np.inf, -np.inf):
            with self.subTest(value=bad):
                value = np.zeros(small_graph.INPUT_SHAPE, dtype=np.float32)
                value[0, 0, 0, 0] = bad
                with self.assertRaisesRegex(small_graph.ReferenceError, "finite"):
                    small_graph.run_cpu(value)

    def test_constant_folded_or_wrong_contract_models_are_rejected(self):
        model = small_graph.build_model()
        model.graph.node[0].input[0] = "conv_bias"
        with self.assertRaises(small_graph.ReferenceError):
            small_graph.validate_model(model)

        model = small_graph.build_model()
        pads = next(
            attribute
            for attribute in model.graph.node[0].attribute
            if attribute.name == "pads"
        )
        pads.ints[:] = [0, 0, 0, 0]
        with self.assertRaises(small_graph.ReferenceError):
            small_graph.validate_model(model)

        model = small_graph.build_model()
        model.graph.node[0].attribute.append(
            onnx.helper.make_attribute("group", 1)
        )
        with self.assertRaises(small_graph.ReferenceError):
            small_graph.validate_model(model)

    def test_missing_and_malformed_models_are_clean_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.onnx"
            malformed = root / "malformed.onnx"
            malformed.write_bytes(b"not an ONNX protobuf")
            for path in (missing, malformed):
                with self.subTest(path=path.name):
                    with self.assertRaisesRegex(small_graph.ReferenceError, "could not load"):
                        small_graph.load_and_validate_model(path)

        model = small_graph.build_model()
        model.graph.input[0].name = "wrong_input"
        with self.assertRaises(small_graph.ReferenceError):
            small_graph.validate_model(model)

    def test_verify_cli_reports_backend_versions_hash_and_cases(self):
        result = subprocess.run(
            [sys.executable, str(REPO / "tools" / "reference" / "small_graph.py"), "verify"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('"backend": "CPUExecutionProvider"', result.stdout)
        self.assertIn(EXPECTED_MODEL_SHA256, result.stdout)
        self.assertIn('"seeded_nonzero"', result.stdout)
        self.assertIn("not FSR4, HTP, device, or game validation", result.stdout)


if __name__ == "__main__":
    unittest.main()

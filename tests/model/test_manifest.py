from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "model" / "manifest.py"
FIXTURE = REPO / "tools" / "model" / "fixtures" / "synthetic-valid.json"

spec = importlib.util.spec_from_file_location("model_manifest", TOOL)
manifest_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(manifest_tool)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate, expected_path):
        value = copy.deepcopy(self.manifest)
        mutate(value)
        with self.assertRaises(manifest_tool.ManifestInvalid) as caught:
            manifest_tool.validate_manifest(value)
        self.assertIn(expected_path, str(caught.exception))

    def assert_loader_and_cli_input_error(self, payload, expected_message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-input.json"
            path.write_text(payload, encoding="utf-8")
            with self.assertRaises(manifest_tool.ManifestInputError) as caught:
                manifest_tool.load_manifest(path)
            self.assertIn(expected_message, str(caught.exception))
            result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn(expected_message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_synthetic_fixture_is_valid(self):
        manifest_tool.validate_manifest(self.manifest)
        self.assertTrue(self.manifest["example_only"])
        self.assertFalse(self.manifest["production_ready"])
        self.assertEqual("not_run", self.manifest["validation_gate"])

    def test_required_fields_are_rejected_at_each_level(self):
        self.assert_invalid(lambda value: value.pop("model_manifest_id"), "$.model_manifest_id")
        self.assert_invalid(lambda value: value["graph"].pop("outputs"), "$.graph.outputs")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].pop("dtype"), "$.graph.inputs[0].dtype")

    def test_unknown_fields_are_rejected_at_each_level(self):
        self.assert_invalid(lambda value: value.__setitem__("asset_hash", "invented"), "$.asset_hash")
        self.assert_invalid(lambda value: value["graph"].__setitem__("backend", "mock"), "$.graph.backend")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("scale", 1), "$.graph.inputs[0].scale")

    def test_synthetic_safety_flags_are_fixed(self):
        self.assert_invalid(lambda value: value.__setitem__("model_manifest_id", "real-model-name"), "$.model_manifest_id")
        self.assert_invalid(lambda value: value.__setitem__("example_only", False), "$.example_only")
        self.assert_invalid(lambda value: value.__setitem__("production_ready", True), "$.production_ready")
        self.assert_invalid(lambda value: value.__setitem__("validation_gate", "pass"), "$.validation_gate")

    def test_rank_and_dimension_types_are_rejected(self):
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("shape", [1, 4, 4]), "$.graph.inputs[0].shape")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0]["shape"].__setitem__(0, True), "$.graph.inputs[0].shape[0]")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0]["shape"].__setitem__(1, 0), "$.graph.inputs[0].shape[1]")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0]["shape"].__setitem__(2, -1), "$.graph.inputs[0].shape[2]")
        self.assert_invalid(
            lambda value: value["graph"]["inputs"][0]["shape"].__setitem__(3, manifest_tool.MAX_DIMENSION + 1),
            "$.graph.inputs[0].shape[3]",
        )

    def test_supported_layouts_and_dtypes_are_accepted(self):
        for layout in ("NHWC", "NCHW"):
            for dtype, width in manifest_tool.DTYPE_BYTES.items():
                value = copy.deepcopy(self.manifest)
                tensor = value["graph"]["inputs"][0]
                tensor.update(layout=layout, dtype=dtype, byte_count=64 * width)
                manifest_tool.validate_manifest(value)

    def test_unsupported_layout_and_dtype_are_rejected(self):
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("layout", "CHW"), "$.graph.inputs[0].layout")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("dtype", "float64"), "$.graph.inputs[0].dtype")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("layout", ["NHWC"]), "$.graph.inputs[0].layout")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("dtype", ["float16"]), "$.graph.inputs[0].dtype")

    def test_byte_count_must_be_exact_integer(self):
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("byte_count", True), "$.graph.inputs[0].byte_count")
        self.assert_invalid(lambda value: value["graph"]["inputs"][0].__setitem__("byte_count", 127), "$.graph.inputs[0].byte_count")

    def test_duplicate_names_are_rejected_across_inputs_and_outputs(self):
        self.assert_invalid(
            lambda value: value["graph"]["outputs"][0].__setitem__("name", "input_frame"),
            "$.graph.outputs[0].name",
        )

    def test_tensor_count_is_bounded(self):
        def exceed(value):
            template = value["graph"]["inputs"][0]
            value["graph"]["inputs"] = []
            for index in range(manifest_tool.MAX_TENSOR_COUNT):
                tensor = copy.deepcopy(template)
                tensor["name"] = f"input_{index}"
                value["graph"]["inputs"].append(tensor)

        self.assert_invalid(exceed, "$.graph")

    def test_single_tensor_capacity_uses_bounded_multiplication(self):
        self.assert_invalid(
            lambda value: value["graph"]["inputs"][0].update(
                shape=[1, manifest_tool.MAX_DIMENSION, manifest_tool.MAX_DIMENSION, 1],
                dtype="uint8",
                byte_count=manifest_tool.MAX_DIMENSION**2,
            ),
            "$.graph.inputs[0].shape[2]",
        )

    def test_total_tensor_capacity_is_bounded(self):
        def exceed(value):
            tensor = value["graph"]["inputs"][0]
            tensor.update(shape=[1, 16_384, 16_384, 1], dtype="float32", byte_count=1 << 30)
            value["graph"]["outputs"][0] = copy.deepcopy(tensor)
            value["graph"]["outputs"][0]["name"] = "output_one"
            extra = copy.deepcopy(tensor)
            extra["name"] = "output_two"
            value["graph"]["outputs"].append(extra)

        self.assert_invalid(exceed, "$.graph.outputs[1].byte_count")

    def test_cli_valid_fixture_and_metadata_error_exit_codes(self):
        valid = subprocess.run(
            [sys.executable, str(TOOL), "verify", "--manifest", str(FIXTURE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertIn("valid manifest:", valid.stdout)

        with tempfile.TemporaryDirectory() as directory:
            invalid_path = Path(directory) / "invalid.json"
            invalid = copy.deepcopy(self.manifest)
            invalid["graph"]["inputs"][0]["shape"][0] = True
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(invalid_path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, result.returncode)
        self.assertIn("$.graph.inputs[0].shape[0]", result.stderr)

    def test_cli_json_and_missing_file_are_input_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = root / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            malformed_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(malformed)],
                text=True,
                capture_output=True,
                check=False,
            )
            missing_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(root / "missing.json")],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, malformed_result.returncode)
        self.assertIn("not valid JSON", malformed_result.stderr)
        self.assertEqual(2, missing_result.returncode)
        self.assertIn("does not exist", missing_result.stderr)

    def test_loader_and_cli_reject_duplicate_object_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"graph": {}, "graph": {}}', encoding="utf-8")
            with self.assertRaises(manifest_tool.ManifestInputError) as caught:
                manifest_tool.load_manifest(path)
            self.assertIn("duplicate object key 'graph'", str(caught.exception))
            result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("duplicate object key 'graph'", result.stderr)

    def test_loader_and_cli_reject_nonfinite_json_numbers(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "nonfinite.json"
                path.write_text(f'{{"value": {token}}}', encoding="utf-8")
                with self.assertRaises(manifest_tool.ManifestInputError) as caught:
                    manifest_tool.load_manifest(path)
                self.assertIn(f"non-finite JSON number {token}", str(caught.exception))
                result = subprocess.run(
                    [sys.executable, str(TOOL), "verify", "--manifest", str(path)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(f"non-finite JSON number {token}", result.stderr)

    def test_loader_and_cli_reject_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b" " * (manifest_tool.MAX_MANIFEST_BYTES + 1))
            with self.assertRaises(manifest_tool.ManifestInputError) as caught:
                manifest_tool.load_manifest(path)
            self.assertIn(f"input limit {manifest_tool.MAX_MANIFEST_BYTES} bytes", str(caught.exception))
            result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn(f"input limit {manifest_tool.MAX_MANIFEST_BYTES} bytes", result.stderr)

    def test_loader_and_cli_reject_excessively_long_integer(self):
        self.assert_loader_and_cli_input_error(
            '{"value": ' + ("9" * 5_000) + "}",
            f"integer exceeds digit limit {manifest_tool.MAX_JSON_INTEGER_DIGITS}",
        )

    def test_loader_and_cli_reject_excessive_json_nesting(self):
        self.assert_loader_and_cli_input_error(
            ("[" * 20_000) + ("0") + ("]" * 20_000),
            "JSON nesting exceeds parser limit",
        )

    def test_loader_and_cli_reject_exponent_overflow(self):
        self.assert_loader_and_cli_input_error(
            '{"value": 1e999}',
            "non-finite JSON number 1e999",
        )


if __name__ == "__main__":
    unittest.main()

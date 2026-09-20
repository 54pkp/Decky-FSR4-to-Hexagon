from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "model" / "numeric_reference.py"
FIXTURE = REPO / "tools" / "model" / "fixtures" / "quantization-reference.json"

spec = importlib.util.spec_from_file_location("numeric_reference", TOOL)
numeric_reference = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(numeric_reference)


class NumericReferenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate, expected_path):
        value = copy.deepcopy(self.fixture)
        mutate(value)
        with self.assertRaises(numeric_reference.NumericReferenceInvalid) as caught:
            numeric_reference.validate_fixture(value)
        self.assertIn(expected_path, str(caught.exception))

    def test_formula_rounds_half_ties_away_from_zero_after_zero_point(self):
        self.assertEqual(
            [-6, 1],
            numeric_reference.quantize_affine_int8(
                [-0.625, 0.875], scale=0.25, zero_point=-3
            ),
        )
        self.assertEqual(-2, numeric_reference.round_half_away_from_zero(-1.5))
        self.assertEqual(2, numeric_reference.round_half_away_from_zero(1.5))

    def test_binary64_values_adjacent_to_half_ties_are_not_ties(self):
        positive = 1.5
        negative = -1.5
        self.assertEqual(
            [1, 2, 2],
            [
                numeric_reference.round_half_away_from_zero(value)
                for value in (math.nextafter(positive, -math.inf), positive, math.nextafter(positive, math.inf))
            ],
        )
        self.assertEqual(
            [-2, -2, -1],
            [
                numeric_reference.round_half_away_from_zero(value)
                for value in (math.nextafter(negative, -math.inf), negative, math.nextafter(negative, math.inf))
            ],
        )

    def test_near_half_values_do_not_satisfy_fixture_tie_coverage(self):
        near_ties = copy.deepcopy(self.fixture)
        tie_case = near_ties["cases"][0]
        tie_case["input"] = [-0.625 + 1e-14, 0.875 - 1e-14]
        tie_case["expected_quantized"] = [-5, 0]
        tie_case["expected_dequantized"] = [-0.5, 0.75]

        transformed = [
            value / near_ties["scale"] + near_ties["zero_point"]
            for value in tie_case["input"]
        ]
        self.assertTrue(
            all(
                0.0 < abs(abs(value - math.trunc(value)) - 0.5) < near_ties["absolute_tolerance"]
                for value in transformed
            )
        )
        with self.assertRaises(numeric_reference.NumericReferenceInvalid) as caught:
            numeric_reference.validate_fixture(near_ties)
        self.assertIn(
            "tie_rounding must cover negative and positive half ties",
            str(caught.exception),
        )

    def test_formula_saturates_both_int8_bounds(self):
        self.assertEqual(
            [-128, 127],
            numeric_reference.quantize_affine_int8([-40.0, 33.0], 0.25, -3),
        )

    def test_dequantization_formula_and_unsaturated_errors_are_fixed(self):
        inputs = [0.0, 0.3125]
        expected_q = [-3, -2]
        expected_dequant = [0.0, 0.25]
        self.assertEqual(expected_q, numeric_reference.quantize_affine_int8(inputs, 0.25, -3))
        self.assertEqual(
            expected_dequant,
            numeric_reference.dequantize_affine_int8(expected_q, 0.25, -3),
        )
        self.assertEqual([0.0, 0.0625], [abs(a - b) for a, b in zip(inputs, expected_dequant)])

    def test_fixture_contains_independent_literal_expectations_and_scope_flags(self):
        numeric_reference.validate_fixture(self.fixture)
        self.assertTrue(self.fixture["example_only"])
        self.assertFalse(self.fixture["production_ready"])
        self.assertEqual("not_run", self.fixture["validation_gate"])
        self.assertEqual("int8", self.fixture["dtype"])
        self.assertEqual(1e-12, self.fixture["absolute_tolerance"])
        self.assertEqual(0.125, self.fixture["max_unsaturated_error"])
        self.assertEqual(
            [-6, 1], self.fixture["cases"][0]["expected_quantized"]
        )
        self.assertEqual(
            [-31.25, 32.5], self.fixture["cases"][1]["expected_dequantized"]
        )
        self.assertEqual(
            [0.0, 0.25],
            self.fixture["cases"][2]["expected_dequantized"],
        )
        self.assertIn("not_qnn_offset_or_fsr4", self.fixture["zero_point_convention"])
        self.assertEqual("IEEE 754 binary64 host reference", self.fixture["arithmetic"])
        error_case = self.fixture["cases"][2]
        self.assertTrue(
            all(
                abs(original - dequantized) <= self.fixture["max_unsaturated_error"]
                for original, dequantized in zip(
                    error_case["input"], error_case["expected_dequantized"]
                )
            )
        )

    def test_dequantized_expectation_uses_declared_absolute_tolerance(self):
        within = copy.deepcopy(self.fixture)
        within["cases"][2]["expected_dequantized"][0] += 0.5e-12
        numeric_reference.validate_fixture(within)

        outside = copy.deepcopy(self.fixture)
        outside["cases"][2]["expected_dequantized"][0] += 2e-12
        with self.assertRaises(numeric_reference.NumericReferenceInvalid) as caught:
            numeric_reference.validate_fixture(outside)
        self.assertIn("absolute error", str(caught.exception))

    def test_comparison_tolerance_cannot_be_enlarged(self):
        self.assert_invalid(
            lambda value: value.__setitem__("absolute_tolerance", 1.0),
            "$.absolute_tolerance",
        )

    def test_unsaturated_error_bound_is_scale_over_two_and_excludes_saturation(self):
        self.assert_invalid(
            lambda value: value.__setitem__("max_unsaturated_error", 0.126),
            "$.max_unsaturated_error",
        )

        saturated_error_case = copy.deepcopy(self.fixture)
        saturated_error_case["cases"][1]["category"] = "dequantization_error"
        with self.assertRaises(numeric_reference.NumericReferenceInvalid) as caught:
            numeric_reference.validate_fixture(saturated_error_case)
        self.assertIn("must contain only unsaturated values", str(caught.exception))

        # The valid saturation case has much larger source-space error and is
        # intentionally verified without applying the scale/2 error bound.
        numeric_reference.validate_fixture(self.fixture)
        saturation = self.fixture["cases"][1]
        self.assertGreater(
            abs(saturation["input"][0] - saturation["expected_dequantized"][0]),
            self.fixture["max_unsaturated_error"],
        )

    def test_contract_rejects_wrong_fixed_metadata_and_missing_coverage(self):
        for field, replacement in (
            ("example_only", False),
            ("production_ready", True),
            ("validation_gate", "pass"),
            ("dtype", "uint8"),
            ("quantization_formula", "round(x)"),
            ("dequantization_formula", "q * scale"),
            ("zero_point_convention", "qnn_offset"),
        ):
            with self.subTest(field=field):
                self.assert_invalid(
                    lambda value, field=field, replacement=replacement: value.__setitem__(field, replacement),
                    f"$.{field}",
                )
        self.assert_invalid(
            lambda value: value.__setitem__(
                "cases", [case for case in value["cases"] if case["category"] != "saturation"]
            ),
            "$.cases",
        )

    def test_numeric_mismatches_are_rejected(self):
        self.assert_invalid(
            lambda value: value["cases"][0]["expected_quantized"].__setitem__(0, -4),
            "$.cases[0].expected_quantized",
        )
        self.assert_invalid(
            lambda value: value["cases"][1]["expected_dequantized"].__setitem__(0, -62.0),
            "$.cases[1].expected_dequantized[0]",
        )

    def test_nonfinite_values_nonpositive_scale_and_bad_integers_are_rejected(self):
        for bad in (math.nan, math.inf, -math.inf, True, "1.0"):
            with self.subTest(input=bad), self.assertRaises(numeric_reference.NumericReferenceInvalid):
                numeric_reference.quantize_affine_int8([bad], 0.5, 0)
        with self.assertRaises(numeric_reference.NumericReferenceInvalid) as caught:
            numeric_reference.quantize_affine_int8([1e308], float.fromhex("0x0.0000000000001p-1022"), 0)
        self.assertIn("non-finite transformed value", str(caught.exception))
        for bad_scale in (0, -0.5, math.nan, math.inf, True):
            with self.subTest(scale=bad_scale), self.assertRaises(numeric_reference.NumericReferenceInvalid):
                numeric_reference.quantize_affine_int8([0.0], bad_scale, 0)
        for bad_zero_point in (True, 1.0, -129, 128):
            with self.subTest(zero_point=bad_zero_point), self.assertRaises(numeric_reference.NumericReferenceInvalid):
                numeric_reference.quantize_affine_int8([0.0], 0.5, bad_zero_point)
        for bad_quantized in (True, 1.0, -129, 128):
            with self.subTest(quantized=bad_quantized), self.assertRaises(numeric_reference.NumericReferenceInvalid):
                numeric_reference.dequantize_affine_int8([bad_quantized], 0.5, 0)

    def test_fixture_rejects_bool_numbers_and_invalid_tolerance(self):
        self.assert_invalid(lambda value: value.__setitem__("scale", True), "$.scale")
        self.assert_invalid(lambda value: value.__setitem__("absolute_tolerance", -1.0), "$.absolute_tolerance")
        self.assert_invalid(
            lambda value: value["cases"][0]["expected_quantized"].__setitem__(0, True),
            "$.cases[0].expected_quantized[0]",
        )

    def test_cli_returns_zero_for_fixed_fixture_and_one_for_mismatch(self):
        valid = subprocess.run(
            [sys.executable, str(TOOL), "verify", "--fixture", str(FIXTURE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertIn("valid numeric reference:", valid.stdout)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mismatch.json"
            mismatch = copy.deepcopy(self.fixture)
            mismatch["cases"][0]["expected_quantized"][0] = -4
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            invalid = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, invalid.returncode)
        self.assertIn("invalid numeric reference:", invalid.stderr)
        self.assertNotIn("Traceback", invalid.stderr)

    def test_cli_returns_two_for_json_and_io_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = root / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            malformed_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(malformed)],
                text=True,
                capture_output=True,
                check=False,
            )
            missing_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(root / "missing.json")],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, malformed_result.returncode)
        self.assertIn("fixture is not valid JSON", malformed_result.stderr)
        self.assertEqual(2, missing_result.returncode)
        self.assertIn("fixture does not exist", missing_result.stderr)

    def test_loader_rejects_duplicate_keys_and_nonfinite_json(self):
        for payload, expected in (
            ('{"scale": 1, "scale": 2}', "duplicate object key 'scale'"),
            ('{"value": NaN}', "non-finite JSON number NaN"),
            ('{"value": 1e999}', "non-finite JSON number 1e999"),
        ):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.json"
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(numeric_reference.NumericReferenceInputError) as caught:
                    numeric_reference.load_fixture(path)
                self.assertIn(expected, str(caught.exception))


if __name__ == "__main__":
    unittest.main()

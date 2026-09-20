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
TOOL = REPO / "tools" / "model" / "spatial_reference.py"
FIXTURE = REPO / "tools" / "model" / "fixtures" / "spatial-reference.json"

spec = importlib.util.spec_from_file_location("spatial_reference", TOOL)
spatial_reference = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(spatial_reference)


class _HistoryAccessProbe(list):
    def __init__(self):
        super().__init__([[1]])
        self.accesses = 0

    def __len__(self):
        self.accesses += 1
        raise AssertionError("history was accessed")

    def __iter__(self):
        self.accesses += 1
        raise AssertionError("history was accessed")

    def __getitem__(self, key):
        self.accesses += 1
        raise AssertionError("history was accessed")


class SpatialReferenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate, expected_path):
        value = copy.deepcopy(self.fixture)
        mutate(value)
        with self.assertRaises(spatial_reference.SpatialReferenceInvalid) as caught:
            spatial_reference.validate_fixture(value)
        self.assertIn(expected_path, str(caught.exception))

    def assert_loader_and_cli_input_error(self, payload, expected_message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-input.json"
            path.write_text(payload, encoding="utf-8")
            with self.assertRaises(spatial_reference.SpatialReferenceInputError) as caught:
                spatial_reference.load_fixture(path)
            self.assertIn(expected_message, str(caught.exception))
            result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn(expected_message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_fixture_is_closed_valid_and_explicitly_host_only(self):
        spatial_reference.validate_fixture(self.fixture)
        self.assertTrue(self.fixture["example_only"])
        self.assertFalse(self.fixture["production_ready"])
        self.assertEqual("not_run", self.fixture["validation_gate"])
        self.assertEqual("top_left", self.fixture["conventions"]["coordinate_origin"])
        self.assertEqual("right", self.fixture["conventions"]["positive_x"])
        self.assertEqual("down", self.fixture["conventions"]["positive_y"])
        self.assertEqual("json_null", self.fixture["conventions"]["out_of_bounds"])

        self.assert_invalid(lambda value: value.__setitem__("backend", "HTP"), "$.backend")
        self.assert_invalid(
            lambda value: value["translation"].__setitem__("interpolation", "linear"),
            "$.translation.interpolation",
        )
        self.assert_invalid(
            lambda value: value["conventions"].__setitem__("positive_y", "up"),
            "$.conventions.positive_y",
        )

    def test_forward_translation_and_backward_mv_have_same_fixed_result(self):
        source = self.fixture["source"]
        translation = self.fixture["translation"]
        reprojection = self.fixture["reprojection"]
        translated = spatial_reference.translate_forward(
            source, translation["shift_x"], translation["shift_y"]
        )
        reprojected = spatial_reference.reproject_backward(
            source, reprojection["motion_vectors"]
        )
        self.assertEqual(translation["expected"], translated)
        self.assertEqual(reprojection["expected"], reprojected)
        self.assertEqual(translated, reprojected)
        self.assertEqual(
            [None, None, None, None], translated[0]
        )
        self.assertEqual([None, 1, 2, 3], translated[1])

    def test_reversing_backward_mv_sign_fails_fixed_expectation(self):
        reversed_sign = copy.deepcopy(self.fixture)
        reversed_sign["reprojection"]["motion_vectors"] = [
            [[1, 1] for _ in range(reversed_sign["width"])]
            for _ in range(reversed_sign["height"])
        ]
        with self.assertRaises(spatial_reference.SpatialReferenceInvalid) as caught:
            spatial_reference.validate_fixture(reversed_sign)
        self.assertIn("$.reprojection.expected", str(caught.exception))

    def test_negative_forward_shift_does_not_wrap_python_indices(self):
        source = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        self.assertEqual(
            [[2, 3, None], [5, 6, None], [8, 9, None]],
            spatial_reference.translate_forward(source, -1, 0),
        )

    def test_nonuniform_backward_vectors_gather_xy_and_fill_out_of_bounds(self):
        source = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        vectors = [
            [[0, 0], [-1, 0], [1, 0]],
            [[0, -2], [0, 0], [-2, 0]],
            [[0, -2], [1, -1], [0, 0]],
        ]
        self.assertEqual(
            [[1, 1, None], [None, 5, 4], [1, 6, 9]],
            spatial_reference.reproject_backward(source, vectors),
        )

    def test_reset_outputs_mv_dimensions_without_reading_or_validating_history(self):
        probe = _HistoryAccessProbe()
        vectors = [
            [[100, -100], [0, 0], [-3, 4]],
            [[1, 1], [-1, -1], [0, 0]],
        ]
        self.assertEqual(
            [[None, None, None], [None, None, None]],
            spatial_reference.reproject_backward(probe, vectors, reset=True),
        )
        self.assertEqual(0, probe.accesses)

        with self.assertRaises(AssertionError):
            spatial_reference.reproject_backward(probe, vectors, reset=False)
        self.assertEqual(1, probe.accesses)

        self.assertEqual(
            [[None]],
            spatial_reference.reproject_backward(None, [[[0, 0]]], reset=True),
        )

    def test_grid_shape_types_and_small_limits_are_enforced(self):
        bad_calls = (
            lambda: spatial_reference.translate_forward([], 0, 0),
            lambda: spatial_reference.translate_forward([[1], [2, 3]], 0, 0),
            lambda: spatial_reference.translate_forward([[True]], 0, 0),
            lambda: spatial_reference.translate_forward([[1]], False, 0),
            lambda: spatial_reference.translate_forward(
                [[0] * (spatial_reference.MAX_WIDTH + 1)], 0, 0
            ),
            lambda: spatial_reference.translate_forward(
                [[0] for _ in range(spatial_reference.MAX_HEIGHT + 1)], 0, 0
            ),
        )
        for call in bad_calls:
            with self.subTest(call=call), self.assertRaises(
                spatial_reference.SpatialReferenceInvalid
            ):
                call()

    def test_motion_vector_shape_types_and_history_match_are_enforced(self):
        for vectors in (
            [[[0, 0]], [[0, 0], [0, 0]]],
            [[[0]]],
            [[[0, 0, 0]]],
            [[[True, 0]]],
            [[[0.0, 0]]],
        ):
            with self.subTest(vectors=vectors), self.assertRaises(
                spatial_reference.SpatialReferenceInvalid
            ):
                spatial_reference.reproject_backward([[1]], vectors)

        with self.assertRaises(spatial_reference.SpatialReferenceInvalid) as caught:
            spatial_reference.reproject_backward([[1, 2]], [[[0, 0]]])
        self.assertIn("history", str(caught.exception))
        with self.assertRaises(spatial_reference.SpatialReferenceInvalid):
            spatial_reference.reproject_backward([[None]], [[[0, 0]]])
        with self.assertRaises(spatial_reference.SpatialReferenceInvalid):
            spatial_reference.reproject_backward([[1]], [[[0, 0]]], reset=1)

    def test_fixture_rejects_bad_dimensions_bool_values_and_mv_grid_mismatch(self):
        self.assert_invalid(lambda value: value.__setitem__("width", True), "$.width")
        self.assert_invalid(lambda value: value["source"][1].pop(), "$.source[1]")
        self.assert_invalid(
            lambda value: value["source"][0].__setitem__(0, None), "$.source[0][0]"
        )
        self.assert_invalid(
            lambda value: value["translation"].__setitem__("shift_x", 1.0),
            "$.translation.shift_x",
        )
        self.assert_invalid(
            lambda value: value["reprojection"]["motion_vectors"].pop(),
            "$.reprojection.motion_vectors",
        )
        self.assert_invalid(
            lambda value: value["reprojection"]["motion_vectors"][0][0].__setitem__(0, False),
            "$.reprojection.motion_vectors[0][0][0]",
        )

    def test_literal_expected_grids_are_checked_independently(self):
        self.assert_invalid(
            lambda value: value["translation"]["expected"][1].__setitem__(1, 99),
            "$.translation.expected",
        )
        self.assert_invalid(
            lambda value: value["reprojection"]["expected"][1].__setitem__(1, 99),
            "$.reprojection.expected",
        )
        self.assert_invalid(
            lambda value: value["reset"]["expected"][0].__setitem__(0, 1),
            "$.reset.expected",
        )

    def test_cli_returns_zero_one_and_two_for_contract_and_input_outcomes(self):
        valid = subprocess.run(
            [sys.executable, str(TOOL), "verify", "--fixture", str(FIXTURE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertIn("valid spatial reference:", valid.stdout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mismatch_path = root / "mismatch.json"
            mismatch = copy.deepcopy(self.fixture)
            mismatch["translation"]["expected"][1][1] = 99
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            mismatch_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(mismatch_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            malformed_path = root / "malformed.json"
            malformed_path.write_text("{", encoding="utf-8")
            malformed_result = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--fixture", str(malformed_path)],
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
        self.assertEqual(1, mismatch_result.returncode)
        self.assertIn("invalid spatial reference:", mismatch_result.stderr)
        self.assertEqual(2, malformed_result.returncode)
        self.assertIn("fixture is not valid JSON", malformed_result.stderr)
        self.assertEqual(2, missing_result.returncode)
        self.assertIn("fixture does not exist", missing_result.stderr)

    def test_loader_rejects_duplicate_nonfinite_long_and_deep_json(self):
        for payload, expected in (
            ('{"width": 1, "width": 2}', "duplicate object key 'width'"),
            ('{"value": NaN}', "non-finite JSON number NaN"),
            ('{"value": Infinity}', "non-finite JSON number Infinity"),
            ('{"value": 1e999}', "non-finite JSON number 1e999"),
            (
                '{"value": ' + ("9" * 5_000) + "}",
                f"integer exceeds digit limit {spatial_reference.MAX_JSON_INTEGER_DIGITS}",
            ),
            (
                ("[" * 20_000) + "0" + ("]" * 20_000),
                "JSON nesting exceeds parser limit",
            ),
        ):
            with self.subTest(expected=expected):
                self.assert_loader_and_cli_input_error(payload, expected)

    def test_loader_rejects_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b" " * (spatial_reference.MAX_FIXTURE_BYTES + 1))
            with self.assertRaises(spatial_reference.SpatialReferenceInputError) as caught:
                spatial_reference.load_fixture(path)
        self.assertIn(f"input limit {spatial_reference.MAX_FIXTURE_BYTES} bytes", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

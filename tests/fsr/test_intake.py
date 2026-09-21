from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
if os.fspath(REPOSITORY) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY))

from tools.fsr import intake
from tools.fsr.intake import FileRule, IntakeContract, IntakeError, run_intake


try:
    import numpy as _numpy  # noqa: F401 - capability probe for the child interpreter
except ImportError:
    NUMPY_AVAILABLE = False
else:
    NUMPY_AVAILABLE = True

NUMPY_SEMANTIC_REASON = (
    "R09 semantic NPZ fixture tests require NumPy in the isolated fsr-extract environment"
)


SUCCESS_EXTRACTOR = b'''from pathlib import Path
import json, os, zipfile
source = Path(os.environ["FIDELITYFX_SDK_ROOT"]) / "fixture" / "input.dat"
if source.read_bytes() != b"\\x01\\x02\\x03\\x04stable-marker":
    raise SystemExit(9)
out = Path(__file__).resolve().parents[1] / "artifacts"
out.mkdir()
with zipfile.ZipFile(out / "result.npz", "w") as archive:
    archive.writestr("array.npy", b"\\x93NUMPYfixture-array")
(out / "spec.json").write_text(json.dumps({"kind": "fixture-v1"}), encoding="utf-8")
print("FIXTURE GATE PASSED")
'''

FAILURE_EXTRACTOR = b'''import sys
print("fixture extractor rejected its input", file=sys.stderr)
raise SystemExit(7)
'''

INVALID_OUTPUT_EXTRACTOR = b'''from pathlib import Path
import json
out = Path(__file__).resolve().parents[1] / "artifacts"
out.mkdir()
(out / "result.npz").write_bytes(b"not-an-archive")
(out / "spec.json").write_text(json.dumps({"kind": "wrong-fixture"}), encoding="utf-8")
print("FIXTURE GATE PASSED")
'''


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def semantic_extractor(mutation: str) -> bytes:
    return f'''from pathlib import Path
import json, numpy as np
out = Path(__file__).resolve().parents[1] / "artifacts"
out.mkdir()
mutation = {mutation!r}
arrays = {{f"filler_{{index:03d}}": np.zeros((1,), dtype=np.float32) for index in range(98)}}
arrays["pass0_weight_fkyxc"] = np.zeros((16, 2, 2, 8), dtype=np.float32)
arrays["bin_scale_table"] = np.zeros((77,), dtype=np.float32)
if mutation == "array-count-99": arrays.pop("filler_000")
if mutation == "array-count-101": arrays["extra"] = np.zeros((1,), dtype=np.float32)
if mutation == "missing-pass0": arrays["replacement-pass0"] = arrays.pop("pass0_weight_fkyxc")
if mutation == "pass0-shape": arrays["pass0_weight_fkyxc"] = np.zeros((16, 2, 2, 7), dtype=np.float32)
if mutation == "pass0-dtype": arrays["pass0_weight_fkyxc"] = np.zeros((16, 2, 2, 8), dtype=np.int8)
if mutation == "missing-scale": arrays["replacement-scale"] = arrays.pop("bin_scale_table")
if mutation == "scale-shape": arrays["bin_scale_table"] = np.zeros((76,), dtype=np.float32)
if mutation == "scale-dtype": arrays["bin_scale_table"] = np.zeros((77,), dtype=np.float64)
if mutation == "object-dtype": arrays["filler_000"] = np.array([{{"bad": "object"}}], dtype=object)
np.savez(out / "result.npz", **arrays)
spec = {{
    "preset": "quality",
    "model": "fsr4_model_v07_i8",
    "bin_tensors": [{{}} for _ in range(11)],
    "decls": [{{}} for _ in range(58)],
    "calls": [{{}} for _ in range(13)],
}}
if mutation == "preset-marker": spec["preset"] = "balanced"
if mutation == "model-marker": spec["model"] = "fsr4_model_v08_i8"
if mutation == "bin-count": spec["bin_tensors"].pop()
if mutation == "declaration-count": spec["decls"].append({{}})
if mutation == "call-count": spec["calls"].pop()
(out / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
print("FIXTURE GATE PASSED")
'''.encode("utf-8")


class IntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sdk = self.root / "sdk"
        self.asset = self.sdk / "fixture" / "input.dat"
        self.asset.parent.mkdir(parents=True)
        self.payload = b"\x01\x02\x03\x04stable-marker"
        self.asset.write_bytes(self.payload)
        self.extractor = self.root / "extractor.py"
        self.extractor.write_bytes(SUCCESS_EXTRACTOR)
        self.output = self.root / "published"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def contract(
        self,
        *,
        payload: bytes | None = None,
        payload_hash: str | None = None,
        marker: bytes = b"stable-marker",
        prefix: bytes = b"\x01\x02\x03\x04",
        extractor_payload: bytes = SUCCESS_EXTRACTOR,
    ) -> IntakeContract:
        expected = self.payload if payload is None else payload
        return IntakeContract(
            source_url="https://example.invalid/source",
            source_commit="source-commit",
            extractor_url="https://example.invalid/extractor",
            extractor_commit="extractor-commit",
            inputs=(
                FileRule(
                    "fixture/input.dat",
                    len(expected),
                    payload_hash or digest(expected),
                    (marker,),
                    prefix,
                ),
            ),
            extractor=FileRule(
                "extractor.py",
                len(extractor_payload),
                digest(extractor_payload),
            ),
            archive_name="result.npz",
            spec_name="spec.json",
            spec_markers=(("kind", "fixture-v1"),),
            extractor_stdout_markers=("FIXTURE GATE PASSED",),
        )

    def execute(self, contract: IntakeContract):
        return run_intake(self.sdk, self.extractor, Path(sys.executable), self.output, contract)

    def semantic_contract(self, mutation: str) -> IntakeContract:
        extractor_payload = semantic_extractor(mutation)
        self.extractor.write_bytes(extractor_payload)
        base = self.contract(extractor_payload=extractor_payload)
        return IntakeContract(
            **{
                **base.__dict__,
                "spec_markers": (
                    ("preset", "quality"),
                    ("model", "fsr4_model_v07_i8"),
                ),
                "validate_public_archive": True,
                "spec_counts": (
                    ("bin_tensors", 11),
                    ("decls", 58),
                    ("calls", 13),
                ),
                "environment_packages": ("numpy",),
            }
        )

    def test_success_publishes_only_validated_outputs_and_complete_receipt(self):
        receipt = self.execute(self.contract())
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"result.npz", "spec.json", "intake_receipt.json"},
        )
        saved = json.loads((self.output / "intake_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, receipt)
        self.assertEqual(saved["source"], {"url": "https://example.invalid/source", "commit": "source-commit"})
        self.assertEqual(saved["extractor"]["commit"], "extractor-commit")
        self.assertEqual(saved["inputs"][0]["sha256"], digest(self.payload))
        for name in ("result.npz", "spec.json"):
            data = (self.output / name).read_bytes()
            self.assertEqual(saved["outputs"][name]["byte_count"], len(data))
            self.assertEqual(saved["outputs"][name]["sha256"], digest(data))
        self.assertEqual(saved["device_execution"], "not_run")
        self.assertEqual(saved["schema_version"], "p7-fsr-intake-receipt-v2")
        self.assertEqual(saved["environment"]["packages"], [])
        self.assertGreater(saved["environment"]["python"]["executable"]["byte_count"], 0)
        self.assertRegex(saved["environment"]["python"]["executable"]["sha256"], r"^[0-9a-f]{64}$")
        execution = saved["extractor_execution"]
        self.assertEqual(execution["argv"], [os.path.abspath(sys.executable), "-I", "<isolated-extractor>"])
        self.assertEqual(execution["argv_bindings"], {"0": "environment.python.executable", "2": "extractor"})
        self.assertFalse(execution["temporary_absolute_paths_recorded"])
        self.assertEqual(execution["stdout_gate"]["required_exact_lines"], ["FIXTURE GATE PASSED"])
        self.assertTrue(execution["stdout_gate"]["matched"])

    def test_complete_actual_extractor_argv_is_executed_and_bound_in_receipt(self):
        actual_runs: list[list[str]] = []
        real_run = intake.subprocess.run

        def capture_run(argv, *args, **kwargs):
            if len(argv) == 3 and argv[1] == "-I" and argv[2].endswith("build_weights.py"):
                actual_runs.append(list(argv))
            return real_run(argv, *args, **kwargs)

        with mock.patch.object(intake.subprocess, "run", side_effect=capture_run):
            receipt = self.execute(self.contract())
        self.assertEqual(len(actual_runs), 1)
        self.assertEqual(actual_runs[0][0:2], [os.path.abspath(sys.executable), "-I"])
        self.assertTrue(Path(actual_runs[0][2]).is_absolute())
        self.assertEqual(receipt["extractor_execution"]["argv"][0:2], actual_runs[0][0:2])
        self.assertEqual(receipt["extractor_execution"]["argv"][2], "<isolated-extractor>")
        self.assertEqual(receipt["extractor_execution"]["argv_bindings"]["2"], "extractor")

    def test_missing_and_spoofed_stdout_markers_are_rejected_without_output(self):
        for printed in ("", "prefix FIXTURE GATE PASSED suffix", "  FIXTURE GATE PASSED  "):
            with self.subTest(printed=printed):
                payload = SUCCESS_EXTRACTOR.replace(
                    b'print("FIXTURE GATE PASSED")', f'print({printed!r})'.encode("ascii")
                )
                self.extractor.write_bytes(payload)
                with self.assertRaisesRegex(IntakeError, "missing exact success marker"):
                    self.execute(self.contract(extractor_payload=payload))
                self.assertFalse(self.output.exists())

    def test_missing_or_malformed_environment_summary_is_rejected_without_output(self):
        cases = (
            ({"version": "3.12"}, "missing or unexpected fields"),
            ({
                "implementation": "CPython",
                "version": "3.12",
                "platform": "win-amd64",
                "pointer_bits": "64",
                "executable": sys.executable,
                "packages": {},
            }, "malformed fields"),
        )
        for payload, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                completed = intake.subprocess.CompletedProcess([], 0, json.dumps(payload), "")
                with mock.patch.object(intake.subprocess, "run", return_value=completed):
                    with self.assertRaisesRegex(IntakeError, diagnostic):
                        intake._environment_summary(Path(sys.executable), ())
                self.assertFalse(self.output.exists())

        with mock.patch.object(
            intake, "_environment_summary", side_effect=IntakeError("selected Python environment summary has missing fields")
        ):
            with self.assertRaisesRegex(IntakeError, "missing fields"):
                self.execute(self.contract())
        self.assertFalse(self.output.exists())

    def test_python_environment_drift_is_rejected_without_output(self):
        stable = intake._environment_summary(Path(sys.executable), ())
        drifted = json.loads(json.dumps(stable))
        drifted["python"]["version"] = "0.0-drifted"
        with mock.patch.object(intake, "_environment_summary", side_effect=[stable, drifted]):
            with self.assertRaisesRegex(IntakeError, "environment drifted"):
                self.execute(self.contract())
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_numpy_environment_receipt_and_drift_are_enforced(self):
        contract = self.semantic_contract("")
        receipt = self.execute(contract)
        self.assertEqual(receipt["environment"]["packages"], [{"name": "numpy", "version": _numpy.__version__}])
        self.output.rename(self.root / "first-output")

        stable = intake._environment_summary(Path(sys.executable), ("numpy",))
        drifted = json.loads(json.dumps(stable))
        drifted["packages"][0]["version"] = "0.0-drifted"
        with mock.patch.object(intake, "_environment_summary", side_effect=[stable, drifted]):
            with self.assertRaisesRegex(IntakeError, "environment drifted"):
                self.execute(contract)
        self.assertFalse(self.output.exists())

    def test_truncated_input_is_rejected_without_output(self):
        self.asset.write_bytes(self.payload[:-1])
        with self.assertRaisesRegex(IntakeError, "size mismatch"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())

    def test_wrong_hash_is_rejected_without_output(self):
        with self.assertRaisesRegex(IntakeError, "SHA-256 mismatch"):
            self.execute(self.contract(payload_hash="0" * 64))
        self.assertFalse(self.output.exists())

    def test_wrong_version_marker_is_rejected_without_output(self):
        with self.assertRaisesRegex(IntakeError, "version/content marker"):
            self.execute(self.contract(marker=b"different-version"))
        self.assertFalse(self.output.exists())

    def test_byte_swapped_prefix_is_rejected_before_extraction(self):
        swapped = b"\x04\x03\x02\x01" + self.payload[4:]
        self.asset.write_bytes(swapped)
        with self.assertRaisesRegex(IntakeError, "byte-order/version prefix"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(IntakeError, "already exists"):
            self.execute(self.contract())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_extractor_failure_does_not_publish_output(self):
        self.extractor.write_bytes(FAILURE_EXTRACTOR)
        with self.assertRaisesRegex(IntakeError, "exit code 7"):
            self.execute(self.contract(extractor_payload=FAILURE_EXTRACTOR))
        self.assertFalse(self.output.exists())

    def test_invalid_extractor_outputs_are_not_published(self):
        self.extractor.write_bytes(INVALID_OUTPUT_EXTRACTOR)
        with self.assertRaisesRegex(IntakeError, "valid NPZ/ZIP"):
            self.execute(self.contract(extractor_payload=INVALID_OUTPUT_EXTRACTOR))
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_graph_preset_and_model_markers_are_independently_rejected(self):
        cases = (
            ("preset-marker", "marker 'preset' must equal 'quality'"),
            ("model-marker", "marker 'model' must equal 'fsr4_model_v07_i8'"),
        )
        for mutation, diagnostic in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(IntakeError, diagnostic):
                    self.execute(self.semantic_contract(mutation))
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_graph_bin_declaration_and_call_counts_are_independently_rejected(self):
        cases = (
            ("bin-count", "'bin_tensors' count must equal 11, found 10"),
            ("declaration-count", "'decls' count must equal 58, found 59"),
            ("call-count", "'calls' count must equal 13, found 12"),
        )
        for mutation, diagnostic in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(IntakeError, diagnostic):
                    self.execute(self.semantic_contract(mutation))
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_public_npz_requires_exactly_one_hundred_arrays(self):
        for mutation, found in (("array-count-99", 99), ("array-count-101", 101)):
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(
                    IntakeError, f"expected 100 arrays, found {found}"
                ):
                    self.execute(self.semantic_contract(mutation))
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_pass0_required_array_name_shape_and_dtype_are_independently_rejected(self):
        cases = (
            ("missing-pass0", "missing required array pass0_weight_fkyxc"),
            ("pass0-shape", r"pass0_weight_fkyxc expected shape=\[16, 2, 2, 8\] dtype=float32"),
            ("pass0-dtype", r"pass0_weight_fkyxc expected shape=\[16, 2, 2, 8\] dtype=float32"),
        )
        for mutation, diagnostic in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(IntakeError, diagnostic):
                    self.execute(self.semantic_contract(mutation))
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_scale_required_array_name_shape_and_dtype_are_independently_rejected(self):
        cases = (
            ("missing-scale", "missing required array bin_scale_table"),
            ("scale-shape", r"bin_scale_table expected shape=\[77\] dtype=float32"),
            ("scale-dtype", r"bin_scale_table expected shape=\[77\] dtype=float32"),
        )
        for mutation, diagnostic in cases:
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(IntakeError, diagnostic):
                    self.execute(self.semantic_contract(mutation))
                self.assertFalse(self.output.exists())

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_SEMANTIC_REASON)
    def test_object_dtype_is_rejected_without_publication(self):
        with self.assertRaisesRegex(IntakeError, "Object arrays cannot be loaded|object dtype"):
            self.execute(self.semantic_contract("object-dtype"))
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_input_is_rejected_when_creation_is_permitted(self):
        real = self.root / "real.dat"
        real.write_bytes(self.payload)
        self.asset.unlink()
        try:
            os.symlink(real, self.asset)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(IntakeError, "symlink or reparse"):
            self.execute(self.contract())
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

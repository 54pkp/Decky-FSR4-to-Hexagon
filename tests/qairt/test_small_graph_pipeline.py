from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import subprocess

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    import numpy as np
    from tools.qairt import small_graph_pipeline as pipeline
except ImportError:
    np = None
    pipeline = None


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        names = (
            "sdk.yaml",
            "bin/x86_64-windows-msvc/qairt-converter",
            "bin/x86_64-windows-msvc/qairt-quantizer",
            "bin/x86_64-windows-msvc/qairt-dlc-info",
            "bin/x86_64-windows-msvc/qnn-net-run.exe",
            "lib/x86_64-windows-msvc/QnnCpu.dll",
            "lib/x86_64-windows-msvc/QnnModelDlc.dll",
        )
        payloads = {}
        files = {}
        for index, name in enumerate(names):
            payload = f"fake-{index}".encode()
            payloads[name] = payload
            files[name] = (len(payload), hashlib.sha256(payload).hexdigest())
        payloads.update(
            {
                "lib/python/qti/__init__.py": b"",
                "lib/python/qti/aisw/__init__.py": b"",
                "lib/python/qti/aisw/converters/onnx/onnx_to_ir.py": b"VALUE = 1\n",
                "lib/python/qti/aisw/converters/common/dlc_quantizer.py": b"VALUE = 2\n",
                "lib/python/qti/aisw/dlc_utils/snpe_dlc_utils.py": b"VALUE = 3\n",
                "lib/x86_64-windows-msvc/helper.dll": b"bound-helper",
            }
        )
        self.archive_root = "qairt/test"
        self.archive = root / "qairt.zip"
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as package:
            for name, payload in payloads.items():
                package.writestr(f"{self.archive_root}/{name}", payload)
        self.qairt_python = root / "qairt-python.exe"
        self.reference_python = root / "reference-python.exe"
        self.model = root / "model.onnx"
        for path in (self.qairt_python, self.reference_python, self.model):
            path.write_bytes(path.name.encode())
        archive_size = self.archive.stat().st_size
        archive_sha256 = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        runtime_count = len(payloads) - 1
        runtime_bytes = sum(len(payload) for name, payload in payloads.items() if name != "sdk.yaml")
        self.p3 = root / "p3.json"
        self.p3.write_text(json.dumps({"schema_version": "qairt-windows-host-probe-v1", "profile": "QAIRT-2.49.0.260730-windows-x86_64", "sdk": {"version": "2.49.0", "build_id": "260730134355"}, "python": {"version": "3.12.14", "architecture": "AMD64"}, "vendor_required_packages": dict(pipeline.DEFAULT_PROFILE.required_packages), "archive": {"bytes": archive_size, "sha256": archive_sha256, "archive_root": self.archive_root, "runtime_snapshot": {"file_count": runtime_count, "uncompressed_bytes": runtime_bytes}}, "selected_files": [{"path": name, "bytes": size, "sha256": digest} for name, (size, digest) in files.items()]}), encoding="utf-8")
        self.profile = pipeline.PipelineProfile(
            "2.49.0", "260730134355", files, archive_size, archive_sha256,
            self.archive_root, runtime_count, runtime_bytes,
            hashlib.sha256(self.p3.read_bytes()).hexdigest(),
            hashlib.sha256(self.model.read_bytes()).hexdigest(),
        )
        self.work = root / "work"
        self.output = root / "output"
        self.calls: list[list[str]] = []
        self.encoding_changes: dict[str, object] = {}
        self.encoding_target = "conv_weight"
        self.csv_encoding_changes: dict[str, object] = {}
        self.csv_shape = "1,1,4,4"
        self.cpu_delta = 0.0
        self.constant_cpu = False
        self.fail_stage: str | None = None
        self.mutate_stage: str | None = None
        self.mutate_relative = "lib/python/qti/aisw/converters/onnx/onnx_to_ir.py"
        self.outside_import: Path | None = None
        self.environment_calls: dict[str, int] = {"QAIRT": 0, "reference": 0}
        self.environment_drift_label: str | None = None

    def environment_inspector(self, python, required, label):
        self.environment_calls[label] += 1
        installed = dict(required)
        installed["pip"] = "test"
        if self.environment_drift_label == label and self.environment_calls[label] > 1:
            installed["injected-drift"] = "1"
        installed_list = [{"name": name, "version": installed[name]} for name in sorted(installed)]
        payload = json.dumps(installed_list, separators=(",", ":")).encode("utf-8")
        return {
            "python": {"implementation": "CPython", "version": "3.12.14", "architecture": "AMD64", "platform": "win-amd64", "executable": pipeline._file_record(python)},
            "required_packages": dict(sorted(required.items())),
            "installed_packages": installed_list,
            "installed_packages_sha256": hashlib.sha256(payload).hexdigest(),
            "pip_check": "passed",
        }

    def runner(self, argv, env, cwd, stdout, stderr, timeout):
        args = list(argv)
        self.calls.append(args)
        stage = stdout.stem.split(".")[0]
        stdout.write_text("ok", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        if stage == self.fail_stage:
            return 9
        if stage == "import_origin":
            python_root = Path(env["PYTHONPATH"])
            origins = [
                python_root / "qti/aisw/converters/onnx/onnx_to_ir.py",
                python_root / "qti/aisw/converters/common/dlc_quantizer.py",
                python_root / "qti/aisw/dlc_utils/snpe_dlc_utils.py",
            ]
            if self.outside_import is not None:
                origins.append(self.outside_import)
            stdout.write_text(
                pipeline.IMPORT_PROBE_PREFIX + json.dumps([str(path.resolve()) for path in origins]),
                encoding="utf-8",
            )
        elif stage == "reference_export":
            output = Path(args[args.index("--output") + 1])
            output.mkdir()
            input_lines = []
            for index, name in enumerate(("zero", "pattern", "seeded_nonzero")):
                raw = output / f"{name}.input.raw"
                expected = output / f"{name}.expected.raw"
                np.full(16, index, dtype="<f4").tofile(raw)
                np.full(16, index + 0.25, dtype="<f4").tofile(expected)
                input_lines.append(f"reference_input:={raw}\n")
            (output / "input_list.txt").write_text("".join(input_lines), encoding="utf-8")
        elif stage == "converter":
            Path(args[args.index("--output_path") + 1]).write_bytes(b"float-dlc")
        elif stage == "quantizer":
            Path(args[args.index("--output_dlc") + 1]).write_bytes(b"quant-dlc")
            def entry(bits, dtype, symmetric, offset=-1):
                return {"bitwidth": bits, "dtype": dtype, "is_symmetric": str(symmetric).lower(), "scale": 0.01, "offset": offset, "zero_point": -offset}
            values = {
                "reference_input": entry(8, "uFxp_8", False),
                "reference_output": entry(8, "uFxp_8", False),
                "biased_output": entry(8, "uFxp_8", False),
                "conv_weight": entry(8, "uFxp_8", False),
                "conv_bias": entry(32, "sFxp_32", True, offset=0),
            }
            for key, change in self.encoding_changes.items():
                if key == "axis":
                    values[self.encoding_target]["axis"] = change
                else:
                    values[self.encoding_target][key] = change
            (cwd / "small_graph.encoding.json").write_text(json.dumps({"encodings": values}), encoding="utf-8")
        elif stage == "dlc_info":
            save = Path(args[args.index("--save") + 1])
            csv_encodings = {
                "reference_input": (8, 0.01, -1.0), "reference_output": (8, 0.01, -1.0),
                "biased_output": (8, 0.01, -1.0), "conv_weight": (8, 0.01, -1.0),
                "conv_bias": (32, 0.01, 0.0),
            }
            bits, scale, offset = csv_encodings["conv_weight"]
            csv_encodings["conv_weight"] = (
                self.csv_encoding_changes.get("bitwidth", bits),
                self.csv_encoding_changes.get("scale", scale),
                self.csv_encoding_changes.get("offset", offset),
            )
            encoding_text = "; ".join(
                f"{name} encoding : bitwidth {values[0]}, min 0.0, max 1.0, scale {values[1]:.12f}, offset {values[2]:.12f}"
                for name, values in csv_encodings.items()
            )
            save.write_text("Converter command: desired_io_layout=[['reference_input', 'NCHW'], ['reference_output', 'NCHW']]\nId,Name,Type,Inputs,Outputs,Encoding\n0,conv,Op,\"reference_input (data type: uFxp_8; tensor dimension: [1,1,4,4]; tensor type: APP_WRITE); conv_weight (data type: uFxp_8; tensor dimension: [3,3,1,1]; tensor type: STATIC); conv_bias (data type: sFxp_32; tensor dimension: [1]; tensor type: STATIC)\",\"biased_output (data type: uFxp_8; tensor dimension: [1,4,4,1]; tensor type: NATIVE); reference_output (data type: uFxp_8; tensor dimension: [1,1,4,4]; tensor type: APP_READ)\",\"%s\"\nInput Name,Dimensions,Type,Encoding Info\nreference_input,\"%s\",uFxp_8,encoding\nOutput Name,Dimensions,Type,Encoding Info\nreference_output,\"%s\",uFxp_8,encoding\n" % (encoding_text, self.csv_shape, self.csv_shape), encoding="utf-8")
        elif stage == "qnn_cpu":
            output = Path(args[args.index("--output_dir") + 1])
            for index in range(3):
                folder = output / f"Result_{index}"
                folder.mkdir()
                value = 0.25 if self.constant_cpu else index + 0.25
                np.full(16, value + self.cpu_delta, dtype="<f4").tofile(folder / "reference_output.raw")
        if stage == self.mutate_stage:
            target = Path(env["QAIRT_SDK_ROOT"]) / self.mutate_relative
            target.write_bytes(target.read_bytes() + b"tampered")
        return 0

    def run(self):
        return pipeline.run_pipeline(self.archive, self.qairt_python, self.reference_python, self.model, self.work, self.output, self.p3, profile=self.profile, runner=self.runner, environment_inspector=self.environment_inspector)


@unittest.skipUnless(
    pipeline is not None,
    "requires the pinned QAIRT pipeline environment",
)
class PipelineTests(unittest.TestCase):
    def test_stage_environments_remove_inherited_python_routing(self):
        polluted = {
            "PATH": "outside-path",
            "VIRTUAL_ENV": "outside-venv",
            "PYTHONHOME": "outside-home",
            "PYTHONPATH": "outside-pythonpath",
            "PYTHONUSERBASE": "outside-userbase",
            "PYTHONSAFEPATH": "1",
            "KEEP_ME": "preserved",
        }
        qairt_python = Path("C:/venvs/qairt/Scripts/python.exe")
        reference_python = Path("C:/venvs/reference/Scripts/python.exe")
        sdk = Path("C:/snapshot")
        with mock.patch.dict(pipeline.os.environ, polluted, clear=True):
            sdk_env = pipeline._sdk_environment(sdk, qairt_python)
            reference_env = pipeline._reference_environment(reference_python)
        for environment in (sdk_env, reference_env):
            self.assertEqual("preserved", environment["KEEP_ME"])
            self.assertNotIn("PYTHONHOME", environment)
            self.assertNotIn("PYTHONUSERBASE", environment)
            self.assertNotIn("PYTHONSAFEPATH", environment)
            self.assertEqual("1", environment["PYTHONNOUSERSITE"])
            self.assertEqual("1", environment["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual(str(sdk / "lib" / "python"), sdk_env["PYTHONPATH"])
        self.assertNotIn("PYTHONPATH", reference_env)

    def test_environment_probe_rejects_package_missing_drift_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python.exe"
            python.write_bytes(b"python")
            base = {"implementation": "CPython", "version": "3.12.14", "platform": "win-amd64", "pointer_bits": 64, "executable": str(python.resolve())}
            cases = (
                ([{"name": "other", "version": "1"}], "found missing"),
                ([{"name": "numpy", "version": "2"}], "expected 1, found 2"),
                ([{"name": "numpy", "version": "1"}, {"name": "NumPy", "version": "1"}], "duplicate installed package"),
            )
            for packages, message in cases:
                with self.subTest(message=message):
                    response = subprocess.CompletedProcess([], 0, json.dumps({**base, "packages": packages}), "")
                    with mock.patch.object(pipeline.subprocess, "run", return_value=response):
                        with self.assertRaisesRegex(pipeline.PipelineError, message):
                            pipeline._inspect_environment(python, {"numpy": "1"}, "test")

    def test_environment_probe_rejects_wrong_runtime_and_broken_pip(self):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python.exe"
            python.write_bytes(b"python")
            value = {"implementation": "PyPy", "version": "3.12.14", "platform": "win-amd64", "pointer_bits": 64, "executable": str(python.resolve()), "packages": [{"name": "numpy", "version": "1"}]}
            response = subprocess.CompletedProcess([], 0, json.dumps(value), "")
            with mock.patch.object(pipeline.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(pipeline.PipelineError, "requires CPython"):
                    pipeline._inspect_environment(python, {"numpy": "1"}, "test")
            value["implementation"] = "CPython"
            probe = subprocess.CompletedProcess([], 0, json.dumps(value), "")
            broken = subprocess.CompletedProcess([], 1, "broken dependency", "")
            with mock.patch.object(pipeline.subprocess, "run", side_effect=[probe, broken]):
                with self.assertRaisesRegex(pipeline.PipelineError, "pip check failed"):
                    pipeline._inspect_environment(python, {"numpy": "1"}, "test")

    def test_success_uses_exact_argv_validates_metadata_and_binds_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            receipt = fx.run()
            self.assertEqual("qairt-small-graph-pipeline-v2", receipt["schema_version"])
            self.assertEqual("p6-environment-v1", receipt["environment"]["schema_version"])
            self.assertEqual(fx.profile.p3_receipt_sha256, receipt["environment"]["p3"]["receipt"]["sha256"])
            for label in ("qairt", "reference"):
                environment = receipt["environment"][label]
                self.assertEqual("3.12.14", environment["python"]["version"])
                self.assertTrue(environment["installed_packages"])
                self.assertEqual(64, len(environment["installed_packages_sha256"]))
            self.assertEqual("QNN_CPU", receipt["backend"])
            self.assertEqual("-s", fx.calls[0][1])
            self.assertEqual("fixed_private_archive_snapshot", receipt["sdk"]["execution_source"])
            self.assertEqual(fx.profile.runtime_file_count + 1, receipt["sdk"]["closure"]["file_count"])
            self.assertTrue(receipt["sdk"]["import_origins"])
            converter = fx.calls[2]
            self.assertEqual("HTP", converter[converter.index("--target_backend") + 1])
            self.assertIn("--source_model_input_shape", converter)
            quantizer = fx.calls[3]
            for option, value in (("--act_bitwidth", "8"), ("--weights_bitwidth", "8"), ("--bias_bitwidth", "32"), ("--target_backend", "HTP")):
                self.assertEqual(value, quantizer[quantizer.index(option) + 1])
            self.assertIn("--dump_encoding_json", quantizer)
            self.assertIn("--display_all_encodings", fx.calls[4])
            model_path = Path(fx.calls[5][fx.calls[5].index("--model") + 1])
            self.assertEqual("QnnModelDlc.dll", model_path.name)
            self.assertNotEqual(fx.root, model_path.parents[3])
            self.assertTrue((fx.output / "success_receipt.json").is_file())
            self.assertEqual(6, len(receipt["stages"]))
            self.assertEqual(0.01, receipt["tolerance"]["absolute"])
            self.assertEqual("not_run", receipt["not_run"]["htp_execution"])
            self.assertEqual(hashlib.sha256(Path(pipeline.__file__).read_bytes()).hexdigest(), receipt["inputs"]["pipeline_script"]["sha256"])
            self.assertIn("reference_script", receipt["inputs"])

    def test_stage_failure_keeps_work_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            fx.fail_stage = "quantizer"
            with self.assertRaisesRegex(pipeline.PipelineError, "quantizer"):
                fx.run()
            self.assertTrue((fx.work / "logs" / "quantizer.stdout.log").is_file())
            self.assertFalse(fx.output.exists())

    def test_bad_encoding_bitwidth_signedness_axis_and_metadata_shape_are_rejected(self):
        cases = (({"bitwidth": 4}, "bitwidth"), ({"dtype": "sFxp_8"}, "signedness"), ({"axis": 0}, "per-tensor"))
        for changes, message in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory)); fx.encoding_changes = changes
                with self.assertRaisesRegex(pipeline.PipelineError, message):
                    fx.run()
                self.assertFalse(fx.output.exists())
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.csv_shape = "1,1,3,4"
            with self.assertRaisesRegex(pipeline.PipelineError, "shape"):
                fx.run()

    def test_noninteger_out_of_range_and_csv_mismatched_encodings_are_rejected(self):
        cases = (
            ({"offset": -1.5}, {}, "finite integer"),
            ({"offset": -300, "zero_point": 300}, {}, "outside"),
            ({}, {"scale": 0.02}, "JSON/CSV scale mismatch"),
            ({}, {"offset": -2.0}, "JSON/CSV offset mismatch"),
            ({}, {"offset": -1.5}, "metadata CSV offset must be a finite integer"),
        )
        for json_changes, csv_changes, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                fx.encoding_changes = json_changes
                fx.csv_encoding_changes = csv_changes
                with self.assertRaisesRegex(pipeline.PipelineError, message):
                    fx.run()
                self.assertFalse(fx.output.exists())

    def test_encoding_requires_integer_bitwidth_and_explicit_boolean_symmetry(self):
        cases = (
            ({"bitwidth": 8.5}, "bitwidth must be an integer"),
            ({"bitwidth": 8.0}, "bitwidth must be an integer"),
            ({"bitwidth": "8"}, "bitwidth must be an integer"),
            ({"bitwidth": True}, "bitwidth must be an integer"),
            ({"bitwidth": None}, "bitwidth must be an integer"),
            ({"is_symmetric": "not-a-boolean"}, "symmetry must be boolean"),
            ({"is_symmetric": "FALSE"}, "symmetry must be boolean"),
            ({"is_symmetric": " false "}, "symmetry must be boolean"),
            ({"is_symmetric": 0}, "symmetry must be boolean"),
            ({"is_symmetric": None}, "symmetry must be boolean"),
        )
        for changes, message in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                fx.encoding_changes = changes
                with self.assertRaisesRegex(pipeline.PipelineError, message):
                    fx.run()
                self.assertFalse(fx.output.exists())

        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            fx.encoding_changes = {"is_symmetric": False}
            fx.run()
            self.assertTrue((fx.output / "success_receipt.json").is_file())

        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            fx.encoding_target = "conv_bias"
            fx.encoding_changes = {"is_symmetric": True}
            fx.run()
            self.assertTrue((fx.output / "success_receipt.json").is_file())

        for value in (1, "yes"):
            with self.subTest(conv_bias_symmetry=value), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                fx.encoding_target = "conv_bias"
                fx.encoding_changes = {"is_symmetric": value}
                with self.assertRaisesRegex(pipeline.PipelineError, "symmetry must be boolean"):
                    fx.run()
                self.assertFalse(fx.output.exists())

    def test_cpu_error_and_constant_outputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.cpu_delta = 0.02
            with self.assertRaisesRegex(pipeline.PipelineError, "tolerance"):
                fx.run()
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.constant_cpu = True
            with self.assertRaisesRegex(pipeline.PipelineError, "differ"):
                fx.run()

    def test_cpu_raw_tail_truncation_and_nonfinite_are_rejected(self):
        for defect, message in (("tail", "64 bytes"), ("truncated", "64 bytes"), ("nonfinite", "finite")):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                export = root / "export"; cpu = root / "cpu"
                export.mkdir(); cpu.mkdir()
                for index, name in enumerate(("zero", "pattern", "seeded_nonzero")):
                    np.full(16, index + 0.25, dtype="<f4").tofile(export / f"{name}.expected.raw")
                    folder = cpu / f"Result_{index}"; folder.mkdir()
                    np.full(16, index + 0.25, dtype="<f4").tofile(folder / "reference_output.raw")
                target = cpu / "Result_1" / "reference_output.raw"
                if defect == "tail":
                    target.write_bytes(target.read_bytes() + b"x")
                elif defect == "truncated":
                    (export / "seeded_nonzero.expected.raw").write_bytes((export / "seeded_nonzero.expected.raw").read_bytes()[:-4])
                else:
                    values = np.fromfile(target, dtype="<f4"); values[0] = np.nan; values.tofile(target)
                with self.assertRaisesRegex(pipeline.PipelineError, message):
                    pipeline._compare_cpu(export, cpu)

    def test_snapshot_rejects_python_or_native_replacement_between_stages(self):
        for relative in (
            "lib/python/qti/aisw/converters/onnx/onnx_to_ir.py",
            "lib/x86_64-windows-msvc/helper.dll",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                fx.mutate_stage = "converter"
                fx.mutate_relative = relative
                with self.assertRaisesRegex(pipeline.PipelineError, "SDK snapshot file changed"):
                    fx.run()
                self.assertFalse(fx.output.exists())

    def test_import_origin_outside_snapshot_is_rejected_before_converter(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            outside = fx.root / "injected.py"
            outside.write_text("VALUE = 9\n", encoding="utf-8")
            fx.outside_import = outside
            with self.assertRaisesRegex(pipeline.PipelineError, "escaped fixed SDK snapshot"):
                fx.run()
            self.assertEqual(2, len(fx.calls))
            self.assertFalse(fx.output.exists())

    def test_p3_archive_identity_cannot_authorize_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            receipt = json.loads(fx.p3.read_text(encoding="utf-8"))
            receipt["archive"]["sha256"] = "0" * 64
            fx.p3.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(pipeline.PipelineError, "fixed accepted identity"):
                fx.run()
            self.assertFalse(fx.work.exists())

    def test_malformed_p3_archive_objects_are_pipeline_errors(self):
        for field, value, message in (
            ("archive", None, "archive must be a JSON object"),
            ("archive", [], "archive must be a JSON object"),
            ("runtime_snapshot", None, "runtime snapshot must be a JSON object"),
        ):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                receipt = json.loads(fx.p3.read_text(encoding="utf-8"))
                if field == "archive":
                    receipt["archive"] = value
                else:
                    receipt["archive"][field] = value
                fx.p3.write_text(json.dumps(receipt), encoding="utf-8")
                fx.profile = replace(
                    fx.profile, p3_receipt_sha256=hashlib.sha256(fx.p3.read_bytes()).hexdigest()
                )
                with self.assertRaisesRegex(pipeline.PipelineError, message):
                    fx.run()
                self.assertFalse(fx.work.exists())

    def test_snapshot_cleanup_failure_does_not_publish_success(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            with mock.patch.object(
                pipeline,
                "_remove_snapshot",
                side_effect=pipeline.PipelineError("injected snapshot cleanup failure"),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "injected snapshot cleanup failure"
                ):
                    fx.run()
            self.assertTrue(fx.work.is_dir())
            self.assertFalse(fx.output.exists())

    def test_environment_drift_is_rejected_before_publication(self):
        for label in ("QAIRT", "reference"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fx = Fixture(Path(directory))
                fx.environment_drift_label = label
                with self.assertRaisesRegex(pipeline.PipelineError, "environment changed"):
                    fx.run()
                self.assertFalse(fx.output.exists())

    def test_hash_overwrite_and_whitespace_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.output.mkdir()
            with self.assertRaisesRegex(pipeline.PipelineError, "already exists"):
                fx.run()
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.archive.write_bytes(fx.archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(pipeline.PipelineError, "archive"):
                fx.run()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fx = Fixture(root); fx.work = root / "bad work"
            with self.assertRaisesRegex(pipeline.PipelineError, "whitespace"):
                fx.run()

    def test_losing_publisher_preserves_winner_and_cleans_private_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loser_root = root / "loser"
            winner_root = root / "winner"
            loser_root.mkdir()
            winner_root.mkdir()
            loser = Fixture(loser_root)
            winner = Fixture(winner_root)
            shared_output = root / "output"
            loser.output = shared_output
            winner.output = shared_output
            unrelated = root / ".output.publishing-unrelated"
            unrelated.mkdir()
            sentinel = unrelated / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            original_replace = pipeline.os.replace
            staging_paths = []
            winner_files = {}

            def let_second_publisher_win(source, destination):
                staging_paths.append(Path(source))
                self.assertEqual(shared_output, Path(destination))
                if len(staging_paths) == 1:
                    winner.run()
                    winner_files.update(
                        (str(path.relative_to(shared_output)), path.read_bytes())
                        for path in shared_output.rglob("*")
                        if path.is_file()
                    )
                return original_replace(source, destination)

            with mock.patch.object(
                pipeline.os, "replace", side_effect=let_second_publisher_win
            ):
                with self.assertRaises(pipeline.PipelineError):
                    loser.run()

            self.assertEqual(2, len(staging_paths))
            self.assertNotEqual(staging_paths[0], staging_paths[1])
            self.assertTrue((shared_output / "success_receipt.json").is_file())
            self.assertEqual(
                winner_files,
                {
                    str(path.relative_to(shared_output)): path.read_bytes()
                    for path in shared_output.rglob("*")
                    if path.is_file()
                },
            )
            self.assertFalse(any(path.exists() for path in staging_paths))
            self.assertFalse((loser.work / "success_receipt.json").exists())
            self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

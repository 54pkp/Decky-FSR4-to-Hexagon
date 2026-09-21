from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

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
        self.sdk = root / "sdk"
        self.sdk.mkdir()
        names = (
            "sdk.yaml",
            "bin/x86_64-windows-msvc/qairt-converter",
            "bin/x86_64-windows-msvc/qairt-quantizer",
            "bin/x86_64-windows-msvc/qairt-dlc-info",
            "bin/x86_64-windows-msvc/qnn-net-run.exe",
            "lib/x86_64-windows-msvc/QnnCpu.dll",
            "lib/x86_64-windows-msvc/QnnModelDlc.dll",
        )
        files = {}
        for index, name in enumerate(names):
            path = self.sdk / name
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"fake-{index}".encode()
            path.write_bytes(payload)
            files[name] = (len(payload), hashlib.sha256(payload).hexdigest())
        self.qairt_python = root / "qairt-python.exe"
        self.reference_python = root / "reference-python.exe"
        self.model = root / "model.onnx"
        for path in (self.qairt_python, self.reference_python, self.model):
            path.write_bytes(path.name.encode())
        self.profile = pipeline.PipelineProfile("2.49.0", "260730134355", files, hashlib.sha256(self.model.read_bytes()).hexdigest())
        self.p3 = root / "p3.json"
        self.p3.write_text(json.dumps({"schema_version": "qairt-windows-host-probe-v1", "profile": "QAIRT-2.49.0.260730-windows-x86_64", "sdk": {"version": "2.49.0", "build_id": "260730134355"}, "selected_files": [{"path": name, "bytes": size, "sha256": digest} for name, (size, digest) in files.items()]}), encoding="utf-8")
        self.work = root / "work"
        self.output = root / "output"
        self.calls: list[list[str]] = []
        self.encoding_changes: dict[str, object] = {}
        self.csv_encoding_changes: dict[str, object] = {}
        self.csv_shape = "1,1,4,4"
        self.cpu_delta = 0.0
        self.constant_cpu = False
        self.fail_stage: str | None = None

    def runner(self, argv, env, cwd, stdout, stderr, timeout):
        args = list(argv)
        self.calls.append(args)
        stage = stdout.stem.split(".")[0]
        stdout.write_text("ok", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        if stage == self.fail_stage:
            return 9
        if stage == "reference_export":
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
                return {"bitwidth": bits, "dtype": dtype, "is_symmetric": symmetric, "scale": 0.01, "offset": offset, "zero_point": -offset}
            values = {
                "reference_input": entry(8, "uFxp_8", False),
                "reference_output": entry(8, "uFxp_8", False),
                "biased_output": entry(8, "uFxp_8", False),
                "conv_weight": entry(8, "uFxp_8", False),
                "conv_bias": entry(32, "sFxp_32", True, offset=0),
            }
            for key, change in self.encoding_changes.items():
                if key == "axis":
                    values["conv_weight"]["axis"] = change
                else:
                    values["conv_weight"][key] = change
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
        return 0

    def run(self):
        return pipeline.run_pipeline(self.sdk, self.qairt_python, self.reference_python, self.model, self.work, self.output, self.p3, profile=self.profile, runner=self.runner)


@unittest.skipUnless(
    pipeline is not None,
    "requires the pinned QAIRT pipeline environment",
)
class PipelineTests(unittest.TestCase):
    def test_success_uses_exact_argv_validates_metadata_and_binds_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory))
            receipt = fx.run()
            self.assertEqual("QNN_CPU", receipt["backend"])
            converter = fx.calls[1]
            self.assertEqual("HTP", converter[converter.index("--target_backend") + 1])
            self.assertIn("--source_model_input_shape", converter)
            quantizer = fx.calls[2]
            for option, value in (("--act_bitwidth", "8"), ("--weights_bitwidth", "8"), ("--bias_bitwidth", "32"), ("--target_backend", "HTP")):
                self.assertEqual(value, quantizer[quantizer.index(option) + 1])
            self.assertIn("--dump_encoding_json", quantizer)
            self.assertIn("--display_all_encodings", fx.calls[3])
            self.assertEqual(str(fx.sdk / "lib/x86_64-windows-msvc/QnnModelDlc.dll"), fx.calls[4][fx.calls[4].index("--model") + 1])
            self.assertTrue((fx.output / "success_receipt.json").is_file())
            self.assertEqual(5, len(receipt["stages"]))
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

    def test_hash_overwrite_and_whitespace_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); fx.output.mkdir()
            with self.assertRaisesRegex(pipeline.PipelineError, "already exists"):
                fx.run()
        with tempfile.TemporaryDirectory() as directory:
            fx = Fixture(Path(directory)); (fx.sdk / "sdk.yaml").write_bytes(b"tampered")
            with self.assertRaisesRegex(pipeline.PipelineError, "hash/size"):
                fx.run()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); fx = Fixture(root); fx.work = root / "bad work"
            with self.assertRaisesRegex(pipeline.PipelineError, "whitespace"):
                fx.run()


if __name__ == "__main__":
    unittest.main()

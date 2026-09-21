from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest import mock

from tools.qairt import probe


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "qairt" / "environment.py"
spec = importlib.util.spec_from_file_location("qairt_environment", TOOL)
qairt_environment = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(qairt_environment)


def completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def python_probe(
    version=(3, 12, 14), platform="win-amd64", bits=64, implementation="CPython"
):
    return completed(
        [],
        stdout=json.dumps(
            {
                "version": list(version),
                "implementation": implementation,
                "machine": "AMD64",
                "platform": platform,
                "pointer_bits": bits,
            }
        ),
    )


class QairtEnvironmentTests(unittest.TestCase):
    def test_entry_point_syntax_is_python_3_9_compatible(self):
        ast.parse(TOOL.read_text(encoding="utf-8"), filename=str(TOOL), feature_version=(3, 9))

    def test_requirements_are_exact_vendor_profile_plus_p6_frontend(self):
        locked = qairt_environment.requirements()
        vendor = {qairt_environment._normalise_name(name): version for name, version in probe.REQUIRED_PACKAGES.items()}
        expected_vendor = {key: value[1] for key, value in locked.items() if key not in {"onnx", "protobuf"}}
        self.assertEqual(33, len(vendor))
        self.assertEqual(vendor, expected_vendor)
        self.assertEqual("1.18.0", locked["onnx"][1])
        self.assertEqual("7.36.2", locked["protobuf"][1])
        self.assertEqual(35, len(locked))

    def test_check_reports_explicit_current_interpreter(self):
        result = subprocess.run(
            [sys.executable, str(TOOL), "check", "--python", sys.executable],
            text=True, capture_output=True, check=False,
        )
        supported = (
            sys.version_info[:3] == (3, 12, 14)
            and sys.implementation.name == "cpython"
            and sysconfig.get_platform().lower() == "win-amd64"
            and sys.maxsize > 2**32
        )
        if supported:
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Python 3.12.14 (AMD64)", result.stdout)
            self.assertIn(str(Path(sys.executable).resolve()), result.stdout)
        else:
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertIn("error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_wrong_python_patch_versions_are_rejected_before_pip(self):
        for version in ((3, 10, 0), (3, 12, 13), (3, 12, 15)):
            with self.subTest(version=version):
                with mock.patch.object(qairt_environment, "_run", return_value=python_probe(version)) as run:
                    with self.assertRaises(qairt_environment.FrontendEnvironmentError) as caught:
                        qairt_environment.preflight(Path(sys.executable))
                self.assertIn("requires exactly 3.12.14", str(caught.exception))
                run.assert_called_once()

    def test_non_amd64_or_32_bit_interpreter_is_rejected_before_pip(self):
        for platform, bits in (("win-arm64", 64), ("win32", 32)):
            with self.subTest(platform=platform, bits=bits):
                with mock.patch.object(
                    qairt_environment, "_run", return_value=python_probe(platform=platform, bits=bits)
                ) as run:
                    with self.assertRaises(qairt_environment.FrontendEnvironmentError) as caught:
                        qairt_environment.preflight(Path(sys.executable))
                self.assertIn("requires 64-bit win-amd64", str(caught.exception))
                run.assert_called_once()

    def test_non_cpython_interpreter_is_rejected_before_pip(self):
        with mock.patch.object(
            qairt_environment,
            "_run",
            return_value=python_probe(implementation="PyPy"),
        ) as run:
            with self.assertRaises(qairt_environment.FrontendEnvironmentError) as caught:
                qairt_environment.preflight(Path(sys.executable))
        self.assertIn("requires CPython", str(caught.exception))
        run.assert_called_once()

    def test_existing_targets_are_refused_without_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, make in (("directory", Path.mkdir), ("file", lambda path: path.write_text("keep", encoding="utf-8"))):
                with self.subTest(name=name):
                    target = root / name
                    make(target)
                    with mock.patch.object(qairt_environment, "_run") as run:
                        with self.assertRaisesRegex(
                            qairt_environment.FrontendEnvironmentError, "refusing to overwrite"
                        ):
                            qairt_environment.initialise(Path(sys.executable), target)
                    run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows broken-link target regression")
    def test_broken_symlink_target_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "broken"
            try:
                target.symlink_to(root / "missing", target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            with mock.patch.object(qairt_environment, "_run") as run:
                with self.assertRaises(qairt_environment.FrontendEnvironmentError):
                    qairt_environment.initialise(Path(sys.executable), target)
            self.assertTrue(os.path.lexists(target))
            run.assert_not_called()

    def test_init_uses_isolated_pip_and_verifies_every_pin(self):
        with tempfile.TemporaryDirectory(prefix="qairt environment ") as directory:
            root = Path(directory)
            selected = root / "selected python" / "python.exe"
            selected.parent.mkdir()
            selected.write_bytes(b"placeholder")
            target = root / "fresh frontend"
            calls = []

            def fake_run(argv, timeout, env=None):
                calls.append((list(argv), env))
                if argv[1:3] == ["-I", "-c"]:
                    return python_probe()
                if argv[-2:] == ["pip", "--version"]:
                    return completed(argv, stdout="pip 26.0\n")
                if argv[1:4] == ["-I", "-m", "venv"]:
                    created = qairt_environment._venv_python(target)
                    created.parent.mkdir(parents=True)
                    created.write_bytes(b"placeholder")
                    return completed(argv)
                if "install" in argv:
                    return completed(argv)
                if argv[-3:] == ["pip", "--isolated", "check"]:
                    return completed(argv, stdout="No broken requirements found.\n")
                if argv[-3:] == ["--isolated", "list", "--format=json"]:
                    payload = [
                        {"name": name, "version": version}
                        for name, version in qairt_environment.requirements().values()
                    ]
                    return completed(argv, stdout=json.dumps(payload))
                self.fail(f"unexpected argv: {argv!r}")

            with mock.patch.object(qairt_environment, "_run", side_effect=fake_run):
                info, created = qairt_environment.initialise(selected, target)

            self.assertEqual("3.12.14", info["version"])
            self.assertEqual(qairt_environment._venv_python(target), created)
            install_argv = next(argv for argv, _ in calls if "install" in argv)
            self.assertEqual(str(qairt_environment.REQUIREMENTS), install_argv[-1])
            self.assertIn("--require-virtualenv", install_argv)
            for argv, environment in calls:
                if "pip" in argv:
                    self.assertEqual(os.devnull, environment["PIP_CONFIG_FILE"])
                    self.assertNotIn("PIP_TARGET", environment)
                    self.assertNotIn("PIP_PREFIX", environment)
                    self.assertNotIn("PIP_USER", environment)

    def test_missing_locked_distribution_is_rejected(self):
        listed = completed([], stdout=json.dumps([{"name": "onnx", "version": "1.18.0"}]))
        with mock.patch.object(qairt_environment, "_run", return_value=listed):
            with self.assertRaises(qairt_environment.FrontendEnvironmentError) as caught:
                qairt_environment._verify_distributions(
                    Path("python.exe"), qairt_environment.requirements()
                )
        self.assertIn("expected", str(caught.exception))
        self.assertIn("found missing", str(caught.exception))

    def test_failed_pip_check_preserves_partial_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "partial"

            def fake_run(argv, timeout, env=None):
                if argv[1:3] == ["-I", "-c"]:
                    return python_probe()
                if argv[-2:] == ["pip", "--version"]:
                    return completed(argv, stdout="pip 26.0\n")
                if argv[1:4] == ["-I", "-m", "venv"]:
                    created = qairt_environment._venv_python(target)
                    created.parent.mkdir(parents=True)
                    created.write_bytes(b"placeholder")
                    return completed(argv)
                if "install" in argv:
                    return completed(argv)
                if argv[-3:] == ["pip", "--isolated", "check"]:
                    return completed(argv, returncode=1, stdout="broken dependency\n")
                self.fail(f"unexpected argv: {argv!r}")

            with mock.patch.object(qairt_environment, "_run", side_effect=fake_run):
                with self.assertRaises(qairt_environment.FrontendEnvironmentError) as caught:
                    qairt_environment.initialise(Path(sys.executable), target)
            self.assertIn("broken dependency", str(caught.exception))
            self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()

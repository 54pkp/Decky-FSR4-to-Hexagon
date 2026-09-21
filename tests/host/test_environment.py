from __future__ import annotations

import importlib.util
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "host" / "environment.py"

spec = importlib.util.spec_from_file_location("host_environment", TOOL)
host_environment = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(host_environment)


def completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


class HostEnvironmentTests(unittest.TestCase):
    def test_entry_point_syntax_is_python_3_9_compatible(self):
        ast.parse(TOOL.read_text(encoding="utf-8"), filename=str(TOOL), feature_version=(3, 9))

    def test_check_reports_selected_interpreter_and_architecture(self):
        result = subprocess.run(
            [sys.executable, str(TOOL), "check", "--python", sys.executable],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK: Python", result.stdout)
        self.assertRegex(result.stdout, r"\((AMD64|ARM64)\)")
        self.assertIn(str(Path(sys.executable).resolve()), result.stdout)

    def test_invalid_python_path_has_clear_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing python.exe"
            result = subprocess.run(
                [sys.executable, str(TOOL), "check", "--python", str(missing)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn(f"Python executable does not exist: {missing}", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_python_3_9_probe_is_rejected_before_pip(self):
        probe = completed(
            [],
            stdout=json.dumps(
                {
                    "version": [3, 9, 19],
                    "machine": "AMD64",
                    "platform": "win-amd64",
                    "pointer_bits": 64,
                }
            ),
        )
        with mock.patch.object(host_environment, "_run", return_value=probe) as run:
            with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                host_environment.preflight(Path(sys.executable))
        self.assertIn("Python 3.9.19 is unsupported", str(caught.exception))
        run.assert_called_once()

    def test_arm64_is_accepted_and_reported(self):
        responses = [
            completed(
                [],
                stdout=json.dumps(
                    {
                        "version": [3, 12, 1],
                        "machine": "AMD64",
                        "platform": "win-arm64",
                        "pointer_bits": 64,
                    }
                ),
            ),
            completed([], stdout="pip 25.0 from a path\n"),
        ]
        with mock.patch.object(host_environment, "_run", side_effect=responses):
            info = host_environment.preflight(Path(sys.executable))
        self.assertEqual("ARM64", info["architecture"])

    def test_unknown_64_bit_architecture_is_rejected(self):
        probe = completed(
            [],
            stdout=json.dumps(
                {
                    "version": [3, 12, 1],
                    "machine": "AMD64",
                    "platform": "win-riscv64",
                    "pointer_bits": 64,
                }
            ),
        )
        with mock.patch.object(host_environment, "_run", return_value=probe) as run:
            with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                host_environment.preflight(Path(sys.executable))
        self.assertIn("unsupported Python platform", str(caught.exception))
        run.assert_called_once()

    def test_32_bit_interpreter_is_rejected(self):
        probe = completed(
            [],
            stdout=json.dumps(
                {
                    "version": [3, 12, 1],
                    "machine": "x86",
                    "platform": "win32",
                    "pointer_bits": 32,
                }
            ),
        )
        with mock.patch.object(host_environment, "_run", return_value=probe) as run:
            with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                host_environment.preflight(Path(sys.executable))
        self.assertIn("a 64-bit interpreter is required", str(caught.exception))
        run.assert_called_once()

    def test_existing_target_is_refused_without_running_python(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "existing environment"
            target.mkdir()
            marker = target / "keep.txt"
            marker.write_text("preserve", encoding="utf-8")
            with mock.patch.object(host_environment, "_run") as run:
                with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                    host_environment.initialise(Path(sys.executable), target)
            self.assertIn("refusing to overwrite", str(caught.exception))
            self.assertEqual("preserve", marker.read_text(encoding="utf-8"))
            run.assert_not_called()

    def test_existing_file_target_is_refused_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "existing target"
            target.write_text("preserve", encoding="utf-8")
            with mock.patch.object(host_environment, "_run") as run:
                with self.assertRaises(host_environment.HostEnvironmentError):
                    host_environment.initialise(Path(sys.executable), target)
            self.assertEqual("preserve", target.read_text(encoding="utf-8"))
            run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows broken-link target regression")
    def test_broken_symlink_target_is_refused_when_symlinks_are_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "existing broken link"
            try:
                target.symlink_to(root / "missing destination", target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable on this host: {exc}")
            self.assertFalse(target.exists())
            self.assertTrue(os.path.lexists(target))
            with mock.patch.object(host_environment, "_run") as run:
                with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                    host_environment.initialise(Path(sys.executable), target)
            self.assertIn("refusing to overwrite", str(caught.exception))
            self.assertTrue(os.path.lexists(target))
            run.assert_not_called()

    def test_init_keeps_space_containing_paths_as_single_arguments(self):
        with tempfile.TemporaryDirectory(prefix="host setup with spaces ") as directory:
            root = Path(directory)
            selected = root / "selected python" / "python.exe"
            selected.parent.mkdir()
            selected.write_bytes(b"test placeholder")
            target = root / "new environment with spaces"
            calls = []

            def fake_run(argv, timeout, env=None):
                calls.append((list(argv), timeout, env))
                if argv[1:3] == ["-I", "-c"]:
                    return completed(
                        argv,
                        stdout=json.dumps(
                            {
                                "version": [3, 12, 1],
                                "machine": "AMD64",
                                "platform": "win-amd64",
                                "pointer_bits": 64,
                            }
                        ),
                    )
                if argv[-2:] == ["pip", "--version"]:
                    return completed(argv, stdout="pip 25.0 from a path\n")
                if argv[1:4] == ["-I", "-m", "venv"]:
                    created_python = host_environment._venv_python(target.resolve())
                    created_python.parent.mkdir(parents=True)
                    created_python.write_bytes(b"test placeholder")
                    return completed(argv)
                if "install" in argv:
                    return completed(argv)
                if argv[-3:] == ["pip", "--isolated", "check"]:
                    return completed(argv, stdout="No broken requirements found.\n")
                if argv[-3:] == ["--isolated", "list", "--format=json"]:
                    return completed(
                        argv,
                        stdout=json.dumps(
                            [{"name": "jsonschema", "version": "4.26.0"}]
                        ),
                    )
                self.fail(f"unexpected argv: {argv!r}")

            with mock.patch.object(host_environment, "_run", side_effect=fake_run):
                info, created = host_environment.initialise(selected, target)

            self.assertEqual("AMD64", info["architecture"])
            # Windows may spell the same temporary directory with either its
            # long name or an 8.3 alias; compare file identity, not spelling.
            self.assertTrue(
                os.path.samefile(host_environment._venv_python(target.resolve()), created)
            )
            create_argv = calls[2][0]
            install_argv = calls[3][0]
            check_argv = calls[4][0]
            list_argv = calls[5][0]
            self.assertTrue(os.path.samefile(target.resolve(), create_argv[-1]))
            self.assertEqual(str(created), install_argv[0])
            self.assertEqual(str(host_environment.REQUIREMENTS), install_argv[-1])
            self.assertEqual(
                [str(created), "-I", "-m", "pip", "--isolated", "check"],
                check_argv,
            )
            self.assertEqual(
                [
                    str(created),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "--disable-pip-version-check",
                    "install",
                    "--require-virtualenv",
                    "-r",
                    str(host_environment.REQUIREMENTS),
                ],
                install_argv,
            )
            self.assertEqual(
                [
                    str(created),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "list",
                    "--format=json",
                ],
                list_argv,
            )
            for _, _, environment in calls[1:2] + calls[3:]:
                self.assertIsNotNone(environment)
                self.assertEqual(os.devnull, environment["PIP_CONFIG_FILE"])
                self.assertNotIn("PIP_TARGET", environment)
                self.assertNotIn("PIP_PREFIX", environment)
                self.assertNotIn("PIP_USER", environment)

    def test_target_created_during_preflight_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "racing target"
            calls = []

            def fake_run(argv, timeout, env=None):
                calls.append(list(argv))
                if argv[1:3] == ["-I", "-c"]:
                    return completed(
                        argv,
                        stdout=json.dumps(
                            {
                                "version": [3, 12, 1],
                                "machine": "AMD64",
                                "platform": "win-amd64",
                                "pointer_bits": 64,
                            }
                        ),
                    )
                if argv[-2:] == ["pip", "--version"]:
                    target.mkdir()
                    (target / "sentinel.txt").write_text("preserve", encoding="utf-8")
                    return completed(argv, stdout="pip 25.0 from a path\n")
                self.fail(f"unexpected argv after target race: {argv!r}")

            with mock.patch.object(host_environment, "_run", side_effect=fake_run):
                with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                    host_environment.initialise(Path(sys.executable), target)
            self.assertIn("refusing to overwrite", str(caught.exception))
            self.assertEqual("preserve", (target / "sentinel.txt").read_text(encoding="utf-8"))
            self.assertEqual(2, len(calls))

    def test_failed_pip_check_preserves_partial_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "partial environment"

            def fake_run(argv, timeout, env=None):
                if argv[1:3] == ["-I", "-c"]:
                    return completed(
                        argv,
                        stdout=json.dumps(
                            {
                                "version": [3, 12, 1],
                                "machine": "AMD64",
                                "platform": "win-amd64",
                                "pointer_bits": 64,
                            }
                        ),
                    )
                if argv[-2:] == ["pip", "--version"]:
                    return completed(argv, stdout="pip 25.0 from a path\n")
                if argv[1:4] == ["-I", "-m", "venv"]:
                    created_python = host_environment._venv_python(target)
                    created_python.parent.mkdir(parents=True)
                    created_python.write_bytes(b"test placeholder")
                    return completed(argv)
                if "install" in argv:
                    return completed(argv)
                if argv[-3:] == ["pip", "--isolated", "check"]:
                    return completed(argv, returncode=1, stdout="broken dependency\n")
                self.fail(f"unexpected argv: {argv!r}")

            with mock.patch.object(host_environment, "_run", side_effect=fake_run):
                with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                    host_environment.initialise(Path(sys.executable), target)
            self.assertIn("failed pip check", str(caught.exception))
            self.assertIn("broken dependency", str(caught.exception))
            self.assertTrue(target.is_dir())

    def test_missing_baseline_distribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "partial environment"

            def fake_run(argv, timeout, env=None):
                if argv[1:3] == ["-I", "-c"]:
                    return completed(
                        argv,
                        stdout=json.dumps(
                            {
                                "version": [3, 12, 1],
                                "machine": "AMD64",
                                "platform": "win-amd64",
                                "pointer_bits": 64,
                            }
                        ),
                    )
                if argv[-2:] == ["pip", "--version"]:
                    return completed(argv, stdout="pip 25.0 from a path\n")
                if argv[1:4] == ["-I", "-m", "venv"]:
                    created_python = host_environment._venv_python(target)
                    created_python.parent.mkdir(parents=True)
                    created_python.write_bytes(b"test placeholder")
                    return completed(argv)
                if "install" in argv:
                    return completed(argv)
                if argv[-3:] == ["pip", "--isolated", "check"]:
                    return completed(argv, stdout="No broken requirements found.\n")
                if argv[-3:] == ["--isolated", "list", "--format=json"]:
                    return completed(argv, stdout="[]")
                self.fail(f"unexpected argv: {argv!r}")

            with mock.patch.object(host_environment, "_run", side_effect=fake_run):
                with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                    host_environment.initialise(Path(sys.executable), target)
            self.assertIn("jsonschema expected 4.26.0, found missing", str(caught.exception))
            self.assertTrue(target.is_dir())

    def test_missing_pip_is_rejected_clearly(self):
        responses = [
            completed(
                [],
                stdout=json.dumps(
                    {
                        "version": [3, 10, 0],
                        "machine": "x86_64",
                        "platform": "win-amd64",
                        "pointer_bits": 64,
                    }
                ),
            ),
            completed([], returncode=1, stderr="No module named pip"),
        ]
        with mock.patch.object(host_environment, "_run", side_effect=responses):
            with self.assertRaises(host_environment.HostEnvironmentError) as caught:
                host_environment.preflight(Path(sys.executable))
        self.assertIn("pip is unavailable", str(caught.exception))
        self.assertIn("No module named pip", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "device" / "collect.py"

spec = importlib.util.spec_from_file_location("device_collect", TOOL)
device_collect = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = device_collect
spec.loader.exec_module(device_collect)


def directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr or result.stdout)
    else:
        link.symlink_to(target, target_is_directory=True)


class CollectorSafetyTests(unittest.TestCase):
    def test_fixture_root_link_cannot_escape_case(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            case = base / "case"
            outside = base / "outside-root"
            case.mkdir()
            outside.mkdir()
            (case / "commands.json").write_text("[]\n", encoding="utf-8")
            try:
                directory_link(case / "root", outside)
            except OSError as exc:
                self.skipTest(f"directory links unavailable: {exc}")
            with self.assertRaises(device_collect.InputError):
                device_collect.Collector(base / "output", case, [])

    def test_descendant_inheriting_pipes_cannot_extend_timeout_indefinitely(self):
        child = (
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            "time.sleep(30)"
        )
        started = time.monotonic()
        result = device_collect.ProductionRunner.run([sys.executable, "-c", child], 0.1)
        elapsed = time.monotonic() - started
        self.assertTrue(result.timed_out)
        self.assertLess(elapsed, 4.0)

    def test_commands_file_link_cannot_escape_case(self):
        if os.name == "nt":
            self.skipTest("ordinary file symlink requires an unavailable Windows privilege")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            case = base / "case"
            case.mkdir()
            (case / "root").mkdir()
            outside = base / "commands.json"
            outside.write_text(json.dumps([]), encoding="utf-8")
            (case / "commands.json").symlink_to(outside)
            with self.assertRaises(device_collect.InputError):
                device_collect.Collector(base / "output", case, [])

    def test_missing_fixture_contract_paths_are_input_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            missing_commands = base / "missing-commands"
            missing_commands.mkdir()
            with self.assertRaises(device_collect.InputError):
                device_collect.Collector(base / "out-one", missing_commands, [])
            missing_commands_cli = subprocess.run(
                [sys.executable, str(TOOL), "--fixture-root", str(missing_commands),
                 "--output", str(base / "out-one-cli")],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(2, missing_commands_cli.returncode)

            missing_root = base / "missing-root"
            missing_root.mkdir()
            (missing_root / "commands.json").write_text("[]\n", encoding="utf-8")
            with self.assertRaises(device_collect.InputError):
                device_collect.Collector(base / "out-two", missing_root, [])
            missing_root_cli = subprocess.run(
                [sys.executable, str(TOOL), "--fixture-root", str(missing_root),
                 "--output", str(base / "out-two-cli")],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(2, missing_root_cli.returncode)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object regression")
    def test_normal_leader_exit_does_not_leave_pipe_holding_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "descendant.pid"
            grandchild = "import time; time.sleep(30)"
            leader = (
                "import pathlib,subprocess,sys; "
                f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
                f"pathlib.Path({str(pid_path)!r}).write_text(str(p.pid))"
            )
            started = time.monotonic()
            device_collect.ProductionRunner.run([sys.executable, "-c", leader], 2.0)
            self.assertLess(time.monotonic() - started, 4.0)
            descendant_pid = int(pid_path.read_text(encoding="utf-8"))

            import ctypes
            process_query_limited_information = 0x1000
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                handle = ctypes.windll.kernel32.OpenProcess(
                    process_query_limited_information, False, descendant_pid
                )
                if not handle:
                    break
                ctypes.windll.kernel32.CloseHandle(handle)
                time.sleep(0.05)
            else:
                self.fail(f"descendant process {descendant_pid} survived runner return")
            self.assertFalse(
                any(thread.name.startswith("device-collector-") for thread in threading.enumerate())
            )


if __name__ == "__main__":
    unittest.main()

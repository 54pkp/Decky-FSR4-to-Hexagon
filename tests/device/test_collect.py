from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()

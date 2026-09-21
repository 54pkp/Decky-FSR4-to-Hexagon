from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from tools.qairt import probe


def pe64() -> bytes:
    data = bytearray(0x200)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 112, 0)
    struct.pack_into("<H", data, 0x98, 0x20B)
    return bytes(data)


class Fixture:
    def __init__(self, base: Path, script: str | None = None):
        self.base = base
        self.root = base / "sdk"
        self.root.mkdir()
        self.archive = base / "archive.zip"
        self.output = base / "receipt.json"
        script = script or "import os,sys; print('h\u00e9lp'); sys.exit(0)\n"
        files = {
            "sdk.yaml": b"product: QAIRT\nos:\n  Windows: 11\nversion: 2.49.0\nbuild_id: 260730134355\n",
            "NOTICE.txt": b"notice", "NOTICE_WINDOWS.txt": b"windows", "LICENSE.pdf": b"pdf",
            "bin/check-python-dependency": b"pins",
            "bin/x86_64-windows-msvc/qairt-converter": script.encode(),
            "bin/x86_64-windows-msvc/qairt-quantizer": script.encode(),
            "bin/x86_64-windows-msvc/qairt-dlc-info": script.encode(),
            "bin/x86_64-windows-msvc/qnn-context-binary-generator.exe": pe64(),
            "bin/x86_64-windows-msvc/qnn-net-run.exe": pe64(),
            "lib/x86_64-windows-msvc/QnnCpu.dll": pe64(),
            "lib/x86_64-windows-msvc/QnnHtpNetRunExtensions.dll": pe64(),
            "lib/x86_64-windows-msvc/QnnHtp.dll": pe64(),
        }
        for name, data in files.items():
            path = self.root / Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        archive_root = "qairt/2.49.0.260730"
        runtime_names = [name for name in files if name.startswith(("bin/x86_64-windows-msvc/", "lib/x86_64-windows-msvc/", "lib/python/"))]
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as package:
            for name, data in files.items():
                package.writestr(f"{archive_root}/{name}", data)
        archive_data = self.archive.read_bytes()
        specs = {name: (len(data), hashlib.sha256(data).hexdigest()) for name, data in files.items()}
        self.profile = probe.Profile(
            "https://example.invalid/v2.49.zip", "qairt.zip", "v2.49.zip",
            "Wed, 05 Aug 2026 13:14:18 GMT", '"etag"', "version-id",
            archive_root, len(runtime_names), sum(len(files[name]) for name in runtime_names),
            len(archive_data), hashlib.sha256(archive_data).hexdigest(), "QAIRT", "2.49.0", "260730134355",
            (sys.version_info.minor,), specs, {},
            {"converter":"bin/x86_64-windows-msvc/qairt-converter", "quantizer":"bin/x86_64-windows-msvc/qairt-quantizer", "metadata":"bin/x86_64-windows-msvc/qairt-dlc-info"},
            ("bin/x86_64-windows-msvc/qnn-context-binary-generator.exe", "bin/x86_64-windows-msvc/qnn-net-run.exe", "lib/x86_64-windows-msvc/QnnCpu.dll", "lib/x86_64-windows-msvc/QnnHtpNetRunExtensions.dll"),
        )

    def replace_archive_member(self, logical: str, data: bytes) -> None:
        entries = {}
        with zipfile.ZipFile(self.archive) as source:
            for item in source.infolist(): entries[item.filename] = source.read(item)
        archive_name = f"{self.profile.archive_root}/{logical}"
        old_size = len(entries[archive_name])
        entries[archive_name] = data
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_STORED) as target:
            for name, payload in entries.items(): target.writestr(name, payload)
        archive = self.archive.read_bytes()
        updates = {"archive_size":len(archive), "archive_sha256":hashlib.sha256(archive).hexdigest()}
        if logical.startswith(("bin/x86_64-windows-msvc/", "lib/x86_64-windows-msvc/", "lib/python/")):
            updates["runtime_uncompressed_bytes"] = self.profile.runtime_uncompressed_bytes + len(data) - old_size
        self.profile = probe.Profile(**{**self.profile.__dict__, **updates})


class ProbeTests(unittest.TestCase):
    def run_fixture(self, fx: Fixture):
        return probe.probe(fx.archive, fx.root, Path(sys.executable), fx.output, fx.profile)

    def test_success_and_capability_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); before = os.environ.copy()
            receipt = self.run_fixture(fx)
            self.assertEqual(receipt["capabilities"]["help"], "invocable")
            self.assertEqual(receipt["capabilities"]["conversion"], "not_run")
            self.assertEqual(receipt["capabilities"]["cpu_backend"], "candidate_present")
            self.assertEqual(receipt["capabilities"]["htp_execution"], "not_run")
            self.assertEqual(receipt["archive"]["http_evidence"]["etag_semantics"], "not_a_sha256")
            self.assertEqual(os.environ, before)
            self.assertEqual(json.loads(fx.output.read_text(encoding="utf-8"))["schema_version"], probe.RECEIPT_VERSION)
            self.assertEqual(receipt["abi"][0]["file"], fx.profile.abi_files[0])

    def test_archive_size_and_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); changed = bytearray(fx.archive.read_bytes()); changed[-1] ^= 1; fx.archive.write_bytes(changed)
            with self.assertRaisesRegex(probe.ProbeError, "SHA-256"):
                self.run_fixture(fx)
            fx.archive.write_bytes(b"short")
            with self.assertRaisesRegex(probe.ProbeError, "size mismatch"):
                self.run_fixture(fx)

    def test_version_and_build_rejected(self):
        for replacement in (b"version: 2.48.0", b"build_id: 1"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                fx = Fixture(Path(tmp)); path = fx.root / "sdk.yaml"; data = path.read_bytes()
                key = b"version: 2.49.0" if replacement.startswith(b"version") else b"build_id: 260730134355"
                changed = data.replace(key, replacement); path.write_bytes(changed)
                specs = dict(fx.profile.files); specs["sdk.yaml"] = (len(changed), hashlib.sha256(changed).hexdigest())
                fx.profile = probe.Profile(**{**fx.profile.__dict__, "files": specs})
                fx.replace_archive_member("sdk.yaml", changed)
                with self.assertRaisesRegex(probe.ProbeError, "identity mismatch"):
                    self.run_fixture(fx)

    def test_python_minor_and_architecture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); bad = probe.Profile(**{**fx.profile.__dict__, "python_minors": (99,)})
            with self.assertRaisesRegex(probe.ProbeError, "requires Python"):
                probe.probe(fx.archive, fx.root, Path(sys.executable), fx.output, bad)
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            with mock.patch("tools.qairt.probe.preflight", return_value={"python":sys.executable,"version":f"3.{sys.version_info.minor}.0","architecture":"ARM64"}):
                with self.assertRaisesRegex(probe.ProbeError, "requires AMD64"):
                    self.run_fixture(fx)

    def test_missing_tool_and_bad_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); (fx.root / fx.profile.probes["converter"]).unlink()
            with self.assertRaises(probe.ProbeError): self.run_fixture(fx)
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); (fx.root / "NOTICE.txt").write_bytes(b"tampered")
            with self.assertRaisesRegex(probe.ProbeError, "size mismatch|SHA-256"):
                self.run_fixture(fx)

    def test_unsafe_profile_path_and_reparse_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); files = dict(fx.profile.files); files["../escape"] = (0, hashlib.sha256(b"").hexdigest())
            bad = probe.Profile(**{**fx.profile.__dict__, "files":files})
            with self.assertRaisesRegex(probe.ProbeError, "unsafe profile path"):
                probe.probe(fx.archive, fx.root, Path(sys.executable), fx.output, bad)
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); target = fx.root / "NOTICE.txt"
            try:
                target.unlink(); target.symlink_to(fx.archive)
            except OSError:
                self.skipTest("symlink unavailable")
            with self.assertRaisesRegex(probe.ProbeError, "non-reparse"):
                self.run_fixture(fx)

    def test_nonzero_timeout_and_utf8_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp), "import sys; print('bad'); sys.exit(7)\n")
            with self.assertRaisesRegex(probe.ProbeError, "exited 7"): self.run_fixture(fx)
        result = probe._run([sys.executable, "-c", "import os;print(os.environ['PYTHONUTF8'])"], {**os.environ, "PYTHONUTF8":"1", "PYTHONIOENCODING":"utf-8"})
        self.assertEqual(result["stdout"]["text"].strip(), "1")
        with self.assertRaisesRegex(probe.ProbeError, "timed out"):
            probe._run([sys.executable, "-c", "import time;time.sleep(1)"], os.environ, .01)

    def test_capture_truncation_preserves_full_hash(self):
        data = b"x" * (probe.MAX_CAPTURE_BYTES + 9)
        result = probe._run([sys.executable, "-c", f"import sys;sys.stdout.buffer.write(b'x'*{len(data)})"], os.environ)
        self.assertTrue(result["stdout"]["truncated"])
        self.assertEqual(result["stdout"]["sha256"], hashlib.sha256(data).hexdigest())

    def test_abi_error_and_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); target = fx.root / fx.profile.abi_files[0]; target.write_bytes(b"bad")
            specs = dict(fx.profile.files); specs[fx.profile.abi_files[0]] = (3, hashlib.sha256(b"bad").hexdigest())
            fx.profile = probe.Profile(**{**fx.profile.__dict__, "files": specs})
            fx.replace_archive_member(fx.profile.abi_files[0], b"bad")
            with self.assertRaisesRegex(probe.ProbeError, "ABI inspection failed"): self.run_fixture(fx)
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); fx.output.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(probe.ProbeError, "already exists"): self.run_fixture(fx)
            self.assertEqual(fx.output.read_text(), "keep")

    def test_launcher_replacement_cannot_change_executed_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); logical = fx.profile.probes["converter"]
            original_path = fx.root / logical; original_run = probe._run; observed = []
            def replacing_run(argv, env, timeout=probe.TIMEOUT_SECONDS):
                observed.append(Path(argv[1]))
                if len(observed) == 1:
                    original_path.write_bytes(b"#" * original_path.stat().st_size)
                return original_run(argv, env, timeout)
            with mock.patch("tools.qairt.probe._run", side_effect=replacing_run):
                with self.assertRaisesRegex(probe.ProbeError, "changed during probe"):
                    self.run_fixture(fx)
            self.assertNotEqual(observed[0], original_path)
            self.assertNotEqual(observed[0].parent, original_path.parent)
            self.assertFalse(fx.output.exists())

    def test_abi_replacement_is_not_the_inspected_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); logical = fx.profile.abi_files[0]
            original_path = fx.root / logical
            real_inspect = probe.abi_inspector.inspect_file; observed = []
            def replacing_inspect(path, *args):
                observed.append(Path(path))
                if len(observed) == 1:
                    original_path.write_bytes(b"x" * original_path.stat().st_size)
                return real_inspect(path, *args)
            with mock.patch("tools.qairt.probe.abi_inspector.inspect_file", side_effect=replacing_inspect):
                with self.assertRaisesRegex(probe.ProbeError, "changed during probe"):
                    self.run_fixture(fx)
            self.assertNotEqual(observed[0], original_path)
            self.assertFalse(fx.output.exists())

    def test_archive_runtime_cannot_mix_expanded_sdk_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp)); logical = fx.profile.abi_files[0]
            entries = {}
            with zipfile.ZipFile(fx.archive) as source:
                for item in source.infolist(): entries[item.filename] = source.read(item)
            archive_name = f"{fx.profile.archive_root}/{logical}"
            entries[archive_name] = b"x" * len(entries[archive_name])
            with zipfile.ZipFile(fx.archive, "w", compression=zipfile.ZIP_STORED) as target:
                for name, data in entries.items(): target.writestr(name, data)
            payload = fx.archive.read_bytes()
            fx.profile = probe.Profile(**{**fx.profile.__dict__, "archive_size":len(payload), "archive_sha256":hashlib.sha256(payload).hexdigest()})
            with self.assertRaisesRegex(probe.ProbeError, "archive selected file SHA-256 mismatch"):
                self.run_fixture(fx)

    def test_zip_duplicate_and_symlink_are_rejected(self):
        for mode in ("duplicate", "symlink"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                fx = Fixture(Path(tmp)); name = f"{fx.profile.archive_root}/lib/python/extra.py"
                with zipfile.ZipFile(fx.archive, "a", compression=zipfile.ZIP_STORED) as package:
                    if mode == "duplicate":
                        first = f"{fx.profile.archive_root}/sdk.yaml"; package.writestr(first.upper(), b"duplicate")
                    else:
                        item = zipfile.ZipInfo(name); item.create_system = 3; item.external_attr = (stat.S_IFLNK | 0o777) << 16
                        package.writestr(item, b"target")
                payload = fx.archive.read_bytes()
                fx.profile = probe.Profile(**{**fx.profile.__dict__, "archive_size":len(payload), "archive_sha256":hashlib.sha256(payload).hexdigest()})
                with self.assertRaisesRegex(probe.ProbeError, "duplicate ZIP|symlink or reparse"):
                    self.run_fixture(fx)

    def test_sdk_or_output_ancestor_reparse_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); real = base / "real"; real.mkdir(); fx = Fixture(real)
            link = base / "linked"
            try:
                link.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink unavailable")
            with self.assertRaisesRegex(probe.ProbeError, "ancestor must be a non-reparse"):
                probe.probe(fx.archive, link / "sdk", Path(sys.executable), fx.output, fx.profile)
            output_link = base / "output-link"; output_real = base / "output-real"; output_real.mkdir()
            output_link.symlink_to(output_real, target_is_directory=True)
            with self.assertRaisesRegex(probe.ProbeError, "ancestor must be a non-reparse"):
                probe.probe(fx.archive, fx.root, Path(sys.executable), output_link / "receipt.json", fx.profile)

    @unittest.skipUnless(os.name == "nt", "Windows directory-share semantics")
    def test_output_parent_cannot_be_replaced_while_probe_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); fx = Fixture(base); output_parent = base / "publish"; output_parent.mkdir()
            fx.output = output_parent / "receipt.json"; moved = base / "moved"
            attempts = []
            def attempt_replace(*_args):
                try:
                    os.rename(output_parent, moved)
                    output_parent.mkdir()
                except OSError as exc: attempts.append(exc)
                return {}
            with mock.patch("tools.qairt.probe._packages", side_effect=attempt_replace):
                try:
                    self.run_fixture(fx)
                except probe.ProbeError as exc:
                    self.assertRegex(str(exc), "locked directory|reserved output")
            if moved.exists():
                self.assertFalse(fx.output.exists())
                self.assertFalse((moved / "receipt.json").exists())
            else:
                self.assertTrue(attempts)
                self.assertTrue(fx.output.is_file())


if __name__ == "__main__":
    unittest.main()

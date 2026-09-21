from __future__ import annotations

from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

from tools.abi import inventory
from tests.abi.fixtures import elf64


class InventoryTests(unittest.TestCase):
    root = "fixture/sdk"
    selected = "lib/aarch64-android/libQnnHtp.so"

    def test_default_profile_source_missing_note_and_exclusions_are_explicit(self):
        profile = inventory.DEFAULT_PROFILE
        self.assertEqual("260730134355", profile.build_id)
        self.assertTrue(profile.source_url.startswith("https://softwarecenter.qualcomm.com/"))
        cdsprpc = next(entry for entry in profile.entries if entry.name == "oe-gcc11-cdsprpc")
        self.assertEqual("missing", cdsprpc.status)
        self.assertIn("BSP", cdsprpc.note or "")
        self.assertIn("device availability is unknown", cdsprpc.note or "")
        self.assertEqual(16 << 20, inventory.MAX_SELECTED_BYTES)

    def _write_zip(self, path: Path, members: list[tuple[str | zipfile.ZipInfo, bytes]]) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as package:
                for name, data in members:
                    package.writestr(name, data)

    def _profile(self, archive: Path, payload: bytes, entries: tuple[inventory.Entry, ...] | None = None) -> inventory.Profile:
        data = archive.read_bytes()
        if entries is None:
            entries = (
                inventory.Entry(
                    "android-htp", self.selected, "present", len(payload),
                    hashlib.sha256(payload).hexdigest(), "ELF", "arm64", "android_candidate",
                ),
                inventory.Entry(
                    "oe-gcc9-v79-stub",
                    "lib/aarch64-oe-linux-gcc9.3/libQnnHtpV79Stub.so",
                    "missing",
                ),
            )
        return inventory.Profile(
            "fixture-profile", "https://example.invalid/fixture.zip", "fixture.zip",
            self.root, len(data), hashlib.sha256(data).hexdigest(), "fixture-sdk",
            "fixture-build", entries,
        )

    def _fixture(self, directory: str, extra: list[tuple[str | zipfile.ZipInfo, bytes]] | None = None):
        base = Path(directory)
        archive = base / "fixture.zip"
        payload = elf64(machine=183, needed=("libc.so", "liblog.so"))
        members: list[tuple[str | zipfile.ZipInfo, bytes]] = [
            (f"{self.root}/{self.selected}", payload),
            (f"{self.root}/lib/aarch64-android/libQnnHtpV81Stub.so", payload),
        ]
        members.extend(extra or [])
        self._write_zip(archive, members)
        return archive, payload, self._profile(archive, payload)

    def test_success_is_deterministic_and_missing_is_archive_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, _payload, profile = self._fixture(directory)
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            report = inventory.inventory(archive, first, profile)
            inventory.inventory(archive, second, profile)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(report, json.loads(first.read_text(encoding="utf-8")))
            self.assertEqual("unknown", report["device_match"])
            self.assertEqual("not_run", report["execution"])
            self.assertEqual({"present": 1, "missing": 1}, report["summary"])
            self.assertEqual("fixture-build", report["source"]["build_id"])
            self.assertEqual(inventory.SCOPE, report["scope"])
            self.assertEqual(inventory.DISCLAIMER, report["disclaimer"])
            self.assertTrue(all(item["status"] == "not_run" for item in report["structural_inventory_exclusions"]))
            self.assertNotIn(str(Path(directory).resolve()), first.read_text(encoding="utf-8"))
            present, missing = report["entries"]
            self.assertEqual("android_candidate", present["inspection"]["candidate"])
            self.assertEqual("pinned_archive_only", missing["scope"])
            self.assertEqual("not_present_in_pinned_archive", missing["reason"])
            self.assertEqual("missing", missing["status"])

    def test_wrong_expected_abi_and_archive_hash_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, _payload, profile = self._fixture(directory)
            wrong_entry = replace(profile.entries[0], machine="x86_64")
            wrong_profile = replace(profile, entries=(wrong_entry, profile.entries[1]))
            with self.assertRaisesRegex(inventory.InventoryError, "ABI inspection failed"):
                inventory.inventory(archive, Path(directory) / "abi.json", wrong_profile)

            changed = bytearray(archive.read_bytes())
            changed[-1] ^= 1
            archive.write_bytes(changed)
            with self.assertRaisesRegex(inventory.InventoryError, "archive SHA-256 mismatch"):
                inventory.inventory(archive, Path(directory) / "hash.json", profile)

    def test_zip_slip_case_duplicate_and_symlink_are_rejected(self):
        cases: list[tuple[str, list[tuple[str | zipfile.ZipInfo, bytes]], str]] = []
        cases.append(("slip", [("../escape", b"x")], "unsafe ZIP member path"))
        cases.append(("duplicate", [(f"{self.root}/{self.selected}".upper(), b"x")], "duplicate ZIP member path"))
        link = zipfile.ZipInfo(f"{self.root}/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases.append(("symlink", [(link, b"target")], "symlink or reparse"))

        for name, extra, message in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive, payload, _profile = self._fixture(directory, extra)
                profile = self._profile(archive, payload)
                with self.assertRaisesRegex(inventory.InventoryError, message):
                    inventory.inventory(archive, Path(directory) / "out.json", profile)

    def test_v81_does_not_substitute_for_missing_v79(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, _payload, profile = self._fixture(directory)
            report = inventory.inventory(archive, Path(directory) / "out.json", profile)
            missing = report["entries"][1]
            self.assertEqual("missing", missing["status"])
            self.assertIn("V79", missing["path"])

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, _payload, profile = self._fixture(directory)
            output = Path(directory) / "out.json"
            output.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(inventory.InventoryError, "refusing to overwrite"):
                inventory.inventory(archive, output, profile)
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_output_ancestor_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _payload, profile = self._fixture(directory)
            real = base / "real"
            real.mkdir()
            linked = base / "linked"
            try:
                linked.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink unavailable")
            with self.assertRaisesRegex(inventory.InventoryError, "ancestor must be a non-reparse"):
                inventory.inventory(archive, linked / "out.json", profile)
            self.assertFalse((real / "out.json").exists())

    def test_output_parent_rename_and_recreate_cannot_misdirect_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, _payload, profile = self._fixture(directory)
            publish = base / "publish"
            publish.mkdir()
            moved = base / "moved"
            output = publish / "receipt.json"
            original_build = inventory._build
            replaced = False

            def attack(*args):
                nonlocal replaced
                try:
                    os.rename(publish, moved)
                    publish.mkdir()
                    replaced = True
                except OSError:
                    pass
                return original_build(*args)

            with mock.patch("tools.abi.inventory._build", side_effect=attack):
                if os.name == "nt":
                    inventory.inventory(archive, output, profile)
                else:
                    with self.assertRaisesRegex(inventory.InventoryError, "locked output directory"):
                        inventory.inventory(archive, output, profile)
            if replaced:
                self.assertFalse((publish / "receipt.json").exists())
                self.assertFalse((moved / "receipt.json").exists())

    def test_cli_success_and_failure_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, _payload, profile = self._fixture(directory)
            output = Path(directory) / "cli.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = inventory.main(
                    ["--archive", str(archive), "--output", str(output)], profile
                )
            self.assertEqual(0, code)
            self.assertEqual("fixture-profile", json.loads(stdout.getvalue())["profile"])

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = inventory.main(
                    ["--archive", str(archive), "--output", str(output)], profile
                )
            self.assertEqual(2, code)
            self.assertIn("refusing to overwrite", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

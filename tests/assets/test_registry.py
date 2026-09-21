from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "assets" / "registry.py"
FIXTURE_ROOT = REPO / "tools" / "assets" / "fixtures" / "complete"

spec = importlib.util.spec_from_file_location("asset_registry", TOOL)
registry_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(registry_tool)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(
            (FIXTURE_ROOT / "registry.json").read_text(encoding="utf-8")
        )

    def _make_package(self, directory: str, registry=None, payload=b"asset\n") -> Path:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root / "payload").mkdir()
        (root / "payload" / "asset.bin").write_bytes(payload)
        value = copy.deepcopy(self.registry if registry is None else registry)
        value["notice"] = {"status": "unknown", "path": None}
        value["files"] = [
            {
                "logical_name": "asset",
                "path": "payload/asset.bin",
                "status": "present",
                "sha256": __import__("hashlib").sha256(payload).hexdigest(),
                "byte_count": len(payload),
                "purpose": "Test payload.",
                "missing_reason": None,
            }
        ]
        (root / "registry.json").write_text(json.dumps(value), encoding="utf-8")
        return root

    def _run(self, root: Path, registry="registry.json"):
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "verify",
                "--root",
                str(root),
                "--registry",
                registry,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _write_registry(self, root: Path, value) -> None:
        (root / "registry.json").write_text(json.dumps(value), encoding="utf-8")

    def test_complete_synthetic_package_passes_and_reports_separate_gates(self):
        result = self._run(FIXTURE_ROOT)
        self.assertEqual(0, result.returncode, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual({"present": 2, "missing": 1}, summary["files"])
        self.assertIs(True, summary["metadata_verified"])
        self.assertEqual("not_run", summary["execution_gate"])

    def test_claimed_present_missing_file_is_contract_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_package(directory)
            (root / "payload" / "asset.bin").unlink()
            result = self._run(root)
        self.assertEqual(1, result.returncode)
        self.assertIn("registered as present but does not exist", result.stderr)

    def test_hash_and_size_mismatches_are_rejected(self):
        for field, value, message in (
            ("sha256", "0" * 64, "sha256"),
            ("byte_count", 999, "byte_count"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = self._make_package(directory)
                registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
                registry["files"][0][field] = value
                self._write_registry(root, registry)
                result = self._run(root)
            self.assertEqual(1, result.returncode)
            self.assertIn(message, result.stderr)

    def test_missing_record_requires_null_integrity_and_reason_and_absence(self):
        value = copy.deepcopy(self.registry)
        record = value["files"][2]
        for field, replacement in (
            ("sha256", "0" * 64),
            ("byte_count", 0),
            ("missing_reason", ""),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(value)
                changed["files"][2][field] = replacement
                with self.assertRaises(registry_tool.RegistryInvalid):
                    registry_tool._validate_contract(changed)

        with tempfile.TemporaryDirectory() as directory:
            root = self._make_package(directory)
            registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            record = registry["files"][0]
            record.update(status="missing", sha256=None, byte_count=None, missing_reason="Absent")
            self._write_registry(root, registry)
            result = self._run(root)
        self.assertEqual(1, result.returncode)
        self.assertIn("registered as missing but exists", result.stderr)

    def test_malformed_duplicate_nonfinite_long_and_deep_json_are_input_errors(self):
        cases = (
            ("{", "not valid JSON"),
            ('{"component": "one", "component": "two"}', "duplicate object key"),
            ('{"value": NaN}', "non-finite JSON number"),
            ('{"value": ' + ("9" * 5000) + "}", "integer exceeds digit limit"),
            (("[" * 2000) + "0" + ("]" * 2000), "nesting exceeds"),
        )
        for payload, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "registry.json").write_text(payload, encoding="utf-8")
                result = self._run(root)
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertIn(message, result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_registry_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry.json").write_bytes(
                b" " * (registry_tool.MAX_REGISTRY_BYTES + 1)
            )
            result = self._run(root)
        self.assertEqual(2, result.returncode)
        self.assertIn("exceeds input limit", result.stderr)

    def test_unsafe_and_duplicate_paths_and_names_are_rejected(self):
        for path in ("../asset.bin", "./asset.bin", "/asset.bin", "payload\\asset.bin"):
            with self.subTest(path=path):
                changed = copy.deepcopy(self.registry)
                changed["files"][0]["path"] = path
                with self.assertRaises(registry_tool.RegistryInvalid):
                    registry_tool._validate_contract(changed)

        for field in ("path", "logical_name"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.registry)
                changed["files"][1][field] = changed["files"][0][field]
                with self.assertRaises(registry_tool.RegistryInvalid) as caught:
                    registry_tool._validate_contract(changed)
                self.assertIn("duplicate", str(caught.exception))

        for field in ("path", "logical_name"):
            with self.subTest(field=field, spelling="case-folded"):
                changed = copy.deepcopy(self.registry)
                changed["files"][1][field] = changed["files"][0][field].upper()
                with self.assertRaises(registry_tool.RegistryInvalid) as caught:
                    registry_tool._validate_contract(changed)
                self.assertIn("duplicate", str(caught.exception))

    def test_absolute_or_escaping_registry_argument_is_rejected(self):
        absolute = self._run(FIXTURE_ROOT, str(FIXTURE_ROOT / "registry.json"))
        traversal = self._run(FIXTURE_ROOT, "../registry.json")
        backslash = self._run(FIXTURE_ROOT, "payload\\registry.json")
        for result in (absolute, traversal, backslash):
            self.assertEqual(1, result.returncode)
            self.assertNotIn("Traceback", result.stderr)

    def test_unknown_fields_wrong_types_and_bad_formats_are_rejected(self):
        mutations = (
            lambda value: value.__setitem__("extra", True),
            lambda value: value.__setitem__("component", []),
            lambda value: value.__setitem__("source_url", "relative/source"),
            lambda value: value.__setitem__("source_url", "https://[broken"),
            lambda value: value.__setitem__("source_url", "https://bad host.invalid/source"),
            lambda value: value["files"][0].__setitem__("sha256", "ABC"),
            lambda value: value["files"][0].__setitem__("byte_count", True),
            lambda value: value["notice"].__setitem__("status", "missing"),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.registry)
            mutate(changed)
            with self.assertRaises(registry_tool.RegistryInvalid):
                registry_tool._validate_contract(changed)

    def test_non_string_status_values_are_clean_contract_errors(self):
        for location, replacement in (
            ("notice", []),
            ("notice", {}),
            ("file", []),
            ("file", {}),
        ):
            with self.subTest(location=location, replacement=type(replacement).__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = self._make_package(directory)
                    value = json.loads(
                        (root / "registry.json").read_text(encoding="utf-8")
                    )
                    if location == "notice":
                        value["notice"]["status"] = replacement
                        field = "$.notice.status"
                    else:
                        value["files"][0]["status"] = replacement
                        field = "$.files[0].status"
                    self._write_registry(root, value)
                    result = self._run(root)
                self.assertEqual(1, result.returncode)
                self.assertIn(field, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_file_count_and_claimed_size_are_bounded(self):
        changed = copy.deepcopy(self.registry)
        template = changed["files"][0]
        changed["files"] = []
        for index in range(registry_tool.MAX_FILE_COUNT + 1):
            record = copy.deepcopy(template)
            record["logical_name"] = f"asset-{index}"
            record["path"] = f"payload/asset-{index}.bin"
            changed["files"].append(record)
        with self.assertRaises(registry_tool.RegistryInvalid) as caught:
            registry_tool._validate_contract(changed)
        self.assertIn("file count", str(caught.exception))

        changed = copy.deepcopy(self.registry)
        changed["files"][0]["byte_count"] = registry_tool.MAX_FILE_BYTES + 1
        with self.assertRaises(registry_tool.RegistryInvalid) as caught:
            registry_tool._validate_contract(changed)
        self.assertIn("byte_count", str(caught.exception))

        changed = copy.deepcopy(self.registry)
        template = changed["files"][0]
        changed["files"] = []
        over_total_count = (
            registry_tool.MAX_TOTAL_FILE_BYTES // registry_tool.MAX_FILE_BYTES + 1
        )
        for index in range(over_total_count):
            record = copy.deepcopy(template)
            record["logical_name"] = f"large-asset-{index}"
            record["path"] = f"payload/large-asset-{index}.bin"
            record["byte_count"] = registry_tool.MAX_FILE_BYTES
            changed["files"].append(record)
        with self.assertRaises(registry_tool.RegistryInvalid) as caught:
            registry_tool._validate_contract(changed)
        self.assertIn("total limit", str(caught.exception))

    def test_oversized_actual_file_is_deterministically_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_package(directory)
            asset = root / "payload" / "asset.bin"
            with asset.open("r+b") as stream:
                stream.truncate(registry_tool.MAX_FILE_BYTES + 1)
            result = self._run(root)
        self.assertEqual(1, result.returncode)
        self.assertIn("exceeds size limit", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_root_and_nested_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            package = self._make_package(str(base / "package"))
            root_link = base / "root-junction"
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(root_link), str(package)],
                text=True,
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest(f"junction creation unavailable: {created.stderr or created.stdout}")
            root_result = self._run(root_link)
            self.assertEqual(2, root_result.returncode)
            self.assertIn("symlink or junction", root_result.stderr)

            outside = base / "outside"
            outside.mkdir()
            (outside / "asset.bin").write_bytes(b"asset\n")
            payload = package / "payload"
            (payload / "asset.bin").unlink()
            payload.rmdir()
            nested = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(payload), str(outside)],
                text=True,
                capture_output=True,
                check=False,
            )
            if nested.returncode != 0:
                self.skipTest(f"nested junction creation unavailable: {nested.stderr or nested.stdout}")
            nested_result = self._run(package)
            self.assertEqual(1, nested_result.returncode)
            self.assertIn("symlink or junction", nested_result.stderr)

            registry = json.loads(
                (package / "registry.json").read_text(encoding="utf-8")
            )
            root_identity = registry_tool._file_identity(package.resolve().stat())
            selected_asset = payload / "asset.bin"
            with mock.patch.object(
                registry_tool, "_candidate", return_value=selected_asset
            ):
                with self.assertRaises(registry_tool.RegistryInvalid) as caught:
                    registry_tool._verify_file(
                        package.resolve(), root_identity, registry["files"][0], 0
                    )
            self.assertIn("outside the selected root", str(caught.exception))

            (outside / "registry.json").write_text("{}", encoding="utf-8")
            selected_registry = payload / "registry.json"
            with mock.patch.object(
                registry_tool, "_candidate", return_value=selected_registry
            ):
                with self.assertRaises(registry_tool.RegistryInvalid) as caught:
                    registry_tool._read_registry(
                        package.resolve(), root_identity, "payload/registry.json"
                    )
            self.assertIn("outside the selected root", str(caught.exception))

    @unittest.skipUnless(os.name == "nt", "Windows root replacement test")
    def test_opened_files_remain_bound_to_the_initial_root_identity(self):
        for swap_on_call in (1, 2):
            with self.subTest(
                target="registry" if swap_on_call == 1 else "asset"
            ), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                package = self._make_package(str(base / "package"))
                outside = self._make_package(str(base / "outside"))
                original = base / "original-package"
                real_candidate = registry_tool._candidate
                call_count = 0

                def candidate_then_replace(root, logical_path, label):
                    nonlocal call_count
                    selected = real_candidate(root, logical_path, label)
                    call_count += 1
                    if call_count == swap_on_call:
                        package.rename(original)
                        created = subprocess.run(
                            ["cmd", "/c", "mklink", "/J", str(package), str(outside)],
                            text=True,
                            capture_output=True,
                            check=False,
                        )
                        if created.returncode != 0:
                            self.skipTest(
                                f"junction creation unavailable: "
                                f"{created.stderr or created.stdout}"
                            )
                    return selected

                with mock.patch.object(
                    registry_tool, "_candidate", side_effect=candidate_then_replace
                ):
                    with self.assertRaises(registry_tool.RegistryInvalid) as caught:
                        registry_tool.verify(package, "registry.json")
                self.assertIn("outside the selected root", str(caught.exception))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_file_and_root_are_rejected_when_creation_is_permitted(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "target"
            target.mkdir()
            package = self._make_package(str(target))
            link = base / "root-link"
            try:
                os.symlink(package, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            root_result = self._run(link)
            self.assertEqual(2, root_result.returncode)
            self.assertIn("symlink or junction", root_result.stderr)

            outside = base / "outside.bin"
            outside.write_bytes(b"asset\n")
            asset = package / "payload" / "asset.bin"
            asset.unlink()
            os.symlink(outside, asset)
            file_result = self._run(package)
            self.assertEqual(1, file_result.returncode)
            self.assertIn("symlink or junction", file_result.stderr)


if __name__ == "__main__":
    unittest.main()

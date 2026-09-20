from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "device" / "profile_tools.py"
FIXTURES = REPO / "tools" / "device" / "fixtures"
GOLDEN = FIXTURES / "comprehensive" / "expected" / "device-profile.json"

spec = importlib.util.spec_from_file_location("profile_tools", TOOL)
profile_tools = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(profile_tools)


class ProfileToolsTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(GOLDEN.read_text(encoding="utf-8"))

    def assert_invalid(self, mutate, expected_path):
        profile = copy.deepcopy(self.profile)
        mutate(profile)
        with self.assertRaises(profile_tools.ProfileInvalid) as caught:
            profile_tools.validate_profile(profile, GOLDEN, verify_files=False)
        self.assertIn(expected_path, str(caught.exception))

    def test_independent_golden_validates_with_physical_evidence(self):
        profile_tools.validate_profile(self.profile, GOLDEN)
        self.assertTrue(self.profile["example_only"])
        self.assertEqual("not_run", self.profile["gate"])
        statuses = {
            observation["status"]
            for _, observation in profile_tools._iter_observations(self.profile)
        }
        self.assertTrue(
            {"success", "missing", "unavailable", "permission_denied", "timeout", "command_failed"}
            <= statuses
        )
        self.assertTrue(any(item["truncated"] for item in self.profile["evidence"]))
        self.assertTrue(any(" " in item["path"] for item in self.profile["evidence"]))

    def test_cli_default_schema_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(TOOL), "validate", str(GOLDEN)],
                cwd=directory,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_missing_contract_fields_are_rejected(self):
        self.assert_invalid(lambda p: p.pop("schema_version"), "$.schema_version")
        self.assert_invalid(lambda p: p.pop("device_profile_id"), "$.device_profile_id")
        self.assert_invalid(lambda p: p["identity"]["host_name"].pop("source"), "$.identity.host_name.source")

    def test_illegal_gate_and_evidence_level_are_rejected(self):
        self.assert_invalid(lambda p: p.__setitem__("gate", "complete"), "$.gate")
        self.assert_invalid(lambda p: p.__setitem__("evidence_level", "mock_test"), "$.evidence_level")

    def test_example_cannot_masquerade_as_measured_pass(self):
        self.assert_invalid(lambda p: p.__setitem__("gate", "pass"), "$.gate")

    def test_evidence_path_and_hash_constraints_are_rejected(self):
        self.assert_invalid(lambda p: p["evidence"][0].__setitem__("path", "/tmp/raw.txt"), "$.evidence[0].path")
        self.assert_invalid(lambda p: p["evidence"][0].__setitem__("path", "evidence/../raw.txt"), "$.evidence[0].path")
        self.assert_invalid(lambda p: p["evidence"][0].__setitem__("sha256", "ABC"), "$.evidence[0].sha256")

        profile = copy.deepcopy(self.profile)
        profile["evidence"][0]["path"] = "evidence//empty.txt"
        with self.assertRaises(profile_tools.ProfileInvalid) as caught:
            profile_tools.validate_profile(profile, GOLDEN, verify_files=False)
        self.assertIn("$.evidence[0].path", str(caught.exception))

    def test_unknown_fields_are_rejected_at_multiple_levels(self):
        self.assert_invalid(lambda p: p.__setitem__("unknown", True), "$.unknown")
        self.assert_invalid(lambda p: p["hardware"].__setitem__("unknown", True), "$.hardware.unknown")
        self.assert_invalid(lambda p: p["identity"]["host_name"].__setitem__("unknown", True), "$.identity.host_name.unknown")
        self.assert_invalid(lambda p: p["evidence"][0].__setitem__("unknown", True), "$.evidence[0].unknown")

    def test_dangling_evidence_reference_has_stable_field_path(self):
        profile = copy.deepcopy(self.profile)
        profile["identity"]["host_name"]["source"]["evidence_ids"] = ["ev-does-not-exist"]
        with self.assertRaises(profile_tools.ProfileInvalid) as caught:
            profile_tools.validate_profile(profile, GOLDEN, verify_files=False)
        self.assertIn("$.identity.host_name.source.evidence_ids[0]", str(caught.exception))

    def test_physical_evidence_hash_and_size_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence").mkdir()
            shutil.copy2(GOLDEN, root / "device-profile.json")
            (root / "evidence" / "empty.txt").write_bytes(b"tampered")
            (root / "evidence" / "path with spaces.txt").write_bytes(b"bounded fixture output\n")
            profile = json.loads((root / "device-profile.json").read_text(encoding="utf-8"))
            with self.assertRaises(profile_tools.ProfileInvalid) as caught:
                profile_tools.validate_profile(profile, root / "device-profile.json")
        message = str(caught.exception)
        self.assertIn("$.evidence[0].byte_count", message)
        self.assertIn("$.evidence[0].sha256", message)

    def test_evidence_symlink_cannot_escape_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "profile"
            evidence_dir = profile_dir / "evidence"
            evidence_dir.mkdir(parents=True)
            outside = root / "outside.txt"
            outside.write_bytes(b"outside secret")
            link = evidence_dir / "escape.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable on this host: {exc}")

            profile = copy.deepcopy(self.profile)
            profile["evidence"] = [copy.deepcopy(profile["evidence"][0])]
            profile["evidence"][0].update(
                path="evidence/escape.txt",
                sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
                byte_count=outside.stat().st_size,
            )
            for _, observation in profile_tools._iter_observations(profile):
                observation["source"]["evidence_ids"] = [
                    evidence_id
                    for evidence_id in observation["source"]["evidence_ids"]
                    if evidence_id == profile["evidence"][0]["evidence_id"]
                ]
            profile_path = profile_dir / "device-profile.json"
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(profile_tools.ProfileInvalid) as caught:
                profile_tools.validate_profile(profile, profile_path)
        self.assertIn("$.evidence[0].path", str(caught.exception))
        self.assertIn("escapes profile directory", str(caught.exception))

    def _redaction_input(self, root: Path) -> Path:
        source = root / "private"
        (source / "evidence").mkdir(parents=True)
        text_source = FIXTURES / "comprehensive" / "redaction-evidence" / "private-command.txt"
        binary_source = FIXTURES / "comprehensive" / "redaction-evidence" / "private-binary.bin"
        shutil.copy2(text_source, source / "evidence" / text_source.name)
        shutil.copy2(binary_source, source / "evidence" / binary_source.name)

        profile = copy.deepcopy(self.profile)
        profile["device_profile_id"] = "example-redaction-private"
        profile["identity"]["user_name"]["value"] = "fixture-user-sentinel"
        profile["identity"]["host_name"]["value"] = "fixture-host-sentinel"
        profile["os"]["kernel"]["source"]["locator"] = "/home/fixture-user-sentinel/PrivateNotes/kernel.log"
        profile["os"]["kernel"]["source"]["evidence_ids"] = ["ev-private-text"]
        profile["graphics"]["egl"]["failure"]["stderr"] = "fixture-host-sentinel serial=SERIAL-FIXTURE-998877"
        profile["graphics"]["egl"]["source"]["evidence_ids"] = ["ev-private-binary"]
        profile["os"]["libc"]["source"]["evidence_ids"] = []
        profile["evidence"] = []
        for evidence_id, collection_id, file_path in (
            ("ev-private-text", "kernel", source / "evidence" / text_source.name),
            ("ev-private-binary", "egl", source / "evidence" / binary_source.name),
        ):
            payload = file_path.read_bytes()
            profile["evidence"].append(
                {
                    "evidence_id": evidence_id,
                    "collection_item_id": collection_id,
                    "path": f"evidence/{file_path.name}",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "byte_count": len(payload),
                    "truncated": False,
                    "visibility": "private",
                }
            )
        private_path = source / "device-profile.json"
        private_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        return private_path

    def test_redaction_publishes_new_hashed_text_and_drops_private_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            output = root / "public" / "device-profile.public.json"
            profile_tools.redact_profile(private_path, output)
            public_bytes = output.read_bytes()
            public = json.loads(public_bytes)
            rendered = public_bytes.decode("utf-8")

            for sentinel in (
                "fixture-user-sentinel",
                "fixture-host-sentinel",
                "/home/fixture-user-sentinel/PrivateNotes",
                "SERIAL-FIXTURE-998877",
            ):
                self.assertNotIn(sentinel.lower(), rendered.lower())
            self.assertIn("[REDACTED:user]", rendered)
            self.assertIn("[REDACTED:host]", rendered)
            self.assertIn("[REDACTED:path]", rendered)
            self.assertIn("[REDACTED:serial]", rendered)
            self.assertEqual("public", public["profile_kind"])
            self.assertEqual("public-v1", public["redaction"]["policy"])
            self.assertEqual(hashlib.sha256(private_path.read_bytes()).hexdigest(), public["redaction"]["source_profile_sha256"])
            self.assertEqual(1, len(public["evidence"]))
            self.assertRegex(public["evidence"][0]["evidence_id"], r"^public-evidence-0001-[0-9a-f]{16}$")
            self.assertEqual([], public["graphics"]["egl"]["source"]["evidence_ids"])

            item = public["evidence"][0]
            published = output.parent.joinpath(*item["path"].split("/"))
            payload = published.read_bytes()
            expected_payload = (FIXTURES / "comprehensive" / "expected" / "public-command.txt").read_bytes()
            self.assertEqual(expected_payload, payload)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
            self.assertEqual(len(payload), item["byte_count"])
            self.assertNotEqual(self.profile["evidence"][0]["sha256"], item["sha256"])
            profile_tools.validate_profile(public, output)

    def test_redaction_preserves_protocol_constants_for_common_user_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            original = json.loads(private_path.read_text(encoding="utf-8"))
            for index, user_name in enumerate(("user", "dev")):
                private = copy.deepcopy(original)
                private["identity"]["user_name"]["value"] = user_name
                private_path.write_text(json.dumps(private), encoding="utf-8")
                output = root / f"public-{index}" / "public.json"
                profile_tools.redact_profile(private_path, output)
                public = json.loads(output.read_text(encoding="utf-8"))
                profile_tools.validate_profile(public, output)
                kinds = {
                    observation["source"]["kind"]
                    for _, observation in profile_tools._iter_observations(public)
                }
                self.assertIn("user_input", kinds)
                self.assertEqual("tools/device/collect.py", public["collection"]["tool"]["name"])

    def test_redaction_covers_spaced_paths_serial_fields_and_private_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            private = json.loads(private_path.read_text(encoding="utf-8"))
            old_evidence = private_path.parent / private["evidence"][0]["path"]
            sensitive_name = "fixture-user-sentinel Private Notes.txt"
            renamed = old_evidence.with_name(sensitive_name)
            old_evidence.rename(renamed)
            payload = renamed.read_bytes()
            private["evidence"][0].update(
                path=f"evidence/{sensitive_name}",
                sha256=hashlib.sha256(payload).hexdigest(),
                byte_count=len(payload),
            )
            private["os"]["kernel"]["value"] = {
                "path": "/home/fixture-user-sentinel/Private Notes/SecretProject/game.exe",
                "serial_number": "SERIAL-FIXTURE-112233",
            }
            json_path = private_path.parent / "evidence" / "private-structured.json"
            json_payload = b'{"serial_number":"SERIAL-FIXTURE-JSON-445566"}\n'
            json_path.write_bytes(json_payload)
            private["evidence"].append({
                "evidence_id": "ev-private-json",
                "collection_item_id": "structured-json",
                "path": "evidence/private-structured.json",
                "sha256": hashlib.sha256(json_payload).hexdigest(),
                "byte_count": len(json_payload),
                "truncated": False,
                "visibility": "private",
            })
            private["os"]["kernel"]["source"]["evidence_ids"].append("ev-private-json")
            private_path.write_text(json.dumps(private), encoding="utf-8")
            output = root / "public" / "public.json"
            profile_tools.redact_profile(private_path, output)
            public = json.loads(output.read_text(encoding="utf-8"))
            rendered = output.read_text(encoding="utf-8") + "\n" + "\n".join(
                output.parent.joinpath(*PurePosixPath(item["path"]).parts).read_text(encoding="utf-8")
                for item in public["evidence"]
            )
            for sentinel in (
                "fixture-user-sentinel",
                "Private Notes",
                "SecretProject",
                "SERIAL-FIXTURE-112233",
                "SERIAL-FIXTURE-JSON-445566",
            ):
                self.assertNotIn(sentinel.lower(), rendered.lower())
            self.assertEqual("[REDACTED:serial]", public["os"]["kernel"]["value"]["serial_number"])
            self.assertNotIn(sensitive_name, public["evidence"][0]["path"])
            profile_tools.validate_profile(public, output)

    def test_redaction_refuses_public_evidence_directory_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            public_dir = root / "public"
            outside = root / "outside"
            public_dir.mkdir()
            outside.mkdir()
            link = public_dir / "evidence"
            if sys.platform == "win32":
                linked = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if linked.returncode != 0:
                    self.skipTest(f"junction unavailable: {linked.stderr}")
            else:
                link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(profile_tools.InputError):
                profile_tools.redact_profile(private_path, public_dir / "public.json")
            self.assertEqual([], list(outside.iterdir()))

    def test_redaction_is_deterministic_except_recorded_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            outputs = [root / "one" / "public.json", root / "two" / "public.json"]
            documents = []
            for output in outputs:
                profile_tools.redact_profile(private_path, output)
                document = json.loads(output.read_text(encoding="utf-8"))
                document["redaction"]["redacted_at"] = "<recorded-time>"
                documents.append(document)
            self.assertEqual(documents[0], documents[1])

    def test_redaction_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            output = root / "public" / "public.json"
            profile_tools.redact_profile(private_path, output)
            with self.assertRaises(profile_tools.InputError):
                profile_tools.redact_profile(private_path, output)

    def test_redact_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_path = self._redaction_input(root)
            output = root / "public" / "public.json"
            redact = subprocess.run(
                [sys.executable, str(TOOL), "redact", str(private_path), "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            validate = subprocess.run(
                [sys.executable, str(TOOL), "validate", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, redact.returncode, redact.stderr)
        self.assertEqual(0, validate.returncode, validate.stderr)

    def test_cli_invalid_profile_returns_one_and_diagnostic_to_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(TOOL), "validate", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, result.returncode)
        self.assertIn("$.schema_version", result.stderr)
        self.assertEqual("", result.stdout)

    def test_cli_missing_input_returns_two(self):
        result = subprocess.run(
            [sys.executable, str(TOOL), "validate", str(REPO / "does-not-exist.json")],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("input error", result.stderr)

    def test_missing_jsonschema_dependency_is_explicit_fatal_error(self):
        with mock.patch.object(
            profile_tools.metadata,
            "version",
            side_effect=profile_tools.metadata.PackageNotFoundError,
        ):
            with self.assertRaises(profile_tools.FatalError) as caught:
                profile_tools._jsonschema_api()
        self.assertIn("jsonschema==4.26.0", str(caught.exception))

    def test_incompatible_jsonschema_dependency_is_explicit_fatal_error(self):
        with mock.patch.object(profile_tools.metadata, "version", return_value="4.25.1"):
            with self.assertRaises(profile_tools.FatalError) as caught:
                profile_tools._jsonschema_api()
        self.assertIn("required 4.26.0", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "windows-public.yml"
HOST_REQUIREMENTS = "tools/device/requirements-host.txt"
CHECKOUT_SHA = "11bd71901bbe5b1630ceea73d27597364c9af683"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"


class PublicCiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.folded = cls.workflow.replace("\\", "/").lower()

    def test_windows_x64_matrix_is_exactly_minimum_and_locked_python(self):
        self.assertRegex(self.workflow, r"(?m)^\s*runs-on:\s*windows-2022\s*$")
        self.assertRegex(self.workflow, r"(?m)^\s*architecture:\s*x64\s*$")
        match = re.search(r"(?m)^\s*python-version:\s*\[([^]]+)\]\s*$", self.workflow)
        self.assertIsNotNone(match)
        versions = re.findall(r'["\']([^"\']+)["\']', match.group(1))
        self.assertEqual(["3.10", "3.12.14"], versions)
        self.assertNotRegex(self.workflow, r"(?m)^\s*(?:os|architecture):\s*\[")

    def test_actions_are_allowlisted_and_pinned_to_immutable_commits(self):
        uses = re.findall(r"(?m)^\s*uses:\s*([^\s#]+)(?:\s+#\s*(.+))?$", self.workflow)
        self.assertEqual(
            [
                (f"actions/checkout@{CHECKOUT_SHA}", "v4.2.2"),
                (f"actions/setup-python@{SETUP_PYTHON_SHA}", "v5.6.0"),
            ],
            uses,
        )
        for action, _comment in uses:
            revision = action.rsplit("@", 1)[1]
            self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_permissions_timeout_and_checkout_are_minimal(self):
        self.assertRegex(
            self.workflow,
            r"(?ms)^permissions:\s*\n\s+contents:\s*read\s*$",
        )
        self.assertNotRegex(self.workflow, r"(?m)^\s+[a-z-]+:\s*write\s*$")
        self.assertRegex(self.workflow, r"(?m)^\s*timeout-minutes:\s*20\s*$")
        self.assertRegex(self.workflow, r"(?m)^\s*persist-credentials:\s*false\s*$")

    def test_only_public_baseline_dependency_is_installed_and_checked(self):
        install = (
            "-m pip install --isolated --disable-pip-version-check "
            f"-r {HOST_REQUIREMENTS}"
        )
        self.assertEqual(1, self.folded.count(install))
        self.assertEqual(1, self.folded.count("-m pip --isolated check"))
        requirement_lines = [
            line.partition("#")[0].strip()
            for line in (REPO / HOST_REQUIREMENTS).read_text(encoding="utf-8").splitlines()
            if line.partition("#")[0].strip()
        ]
        self.assertEqual(["jsonschema==4.26.0"], requirement_lines)

    def test_each_powershell_block_has_one_native_command_so_failure_is_not_masked(self):
        blocks = re.findall(
            r"(?m)^\s{8}run:\s*\|\s*\n((?:\s{10}.*(?:\n|$))+)",
            self.workflow,
        )
        self.assertEqual(3, len(blocks))
        for block in blocks:
            commands = [line.strip() for line in block.splitlines() if line.strip()]
            with self.subTest(command=commands):
                self.assertEqual(1, len(commands))
                self.assertTrue(commands[0].startswith("& '${{ steps.python.outputs.python-path }}'"))

    def test_public_suite_command_is_explicit_and_verbose_for_skip_reporting(self):
        command = '-m unittest discover -s tests -p "test_*.py" -v'
        self.assertEqual(1, self.folded.count(command))
        self.assertEqual(3, self.folded.count("steps.python.outputs.python-path"))
        self.assertIn("capability skips as skips", self.folded)

    def test_workflow_has_public_triggers_without_secrets_or_private_paths(self):
        for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
            self.assertRegex(self.workflow, rf"(?m)^\s{{2}}{trigger}\s*$")
        forbidden = (
            "secrets.",
            "local/venvs",
            "sdks/",
            "downloads/",
            "models/",
            "weights/",
            "requirements-reference",
            "requirements-frontend",
            "verify_environments.py",
            "upload-artifact",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, self.folded)

    def test_unrun_platforms_and_private_matrix_are_declared_not_run(self):
        scope = self.folded.rsplit("# scope:", 1)[-1]
        for value in (
            "windows x64",
            "arm64",
            "linux",
            "private sdk/assets",
            "multi-venv",
            "htp",
            "devices",
            "games",
            "not_run",
        ):
            with self.subTest(value=value):
                self.assertIn(value, scope)


if __name__ == "__main__":
    unittest.main()

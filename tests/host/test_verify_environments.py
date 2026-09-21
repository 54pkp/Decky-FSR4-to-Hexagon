from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "host" / "verify_environments.py"

spec = importlib.util.spec_from_file_location("verify_environments", TOOL)
verify = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = verify
spec.loader.exec_module(verify)


def stream_summary(text: str = ""):
    payload = text.encode("utf-8")
    return {
        "byte_count": len(payload),
        "snapshot_byte_count": len(payload),
        "snapshot_complete": True,
        "sha256": __import__("hashlib").sha256(payload).hexdigest(),
        "tail": text,
        "truncated": False,
        "late_output_excluded_byte_count": 0,
        "capture_semantics": (
            "fixed-size snapshot; bytes appended after snapshot selection are excluded"
        ),
    }


def capture(returncode=0, *, timed_out=False, stdout="", stderr="", launch_error=None):
    return verify.ProcessCapture(
        returncode,
        timed_out,
        stream_summary(stdout),
        stream_summary(stderr),
        launch_error,
    )


def counts(*, passed=1, failures=0, errors=0, skipped=0,
           expected_failures=0, unexpected_successes=0):
    total = passed + failures + errors + skipped + expected_failures + unexpected_successes
    return {
        "total": total,
        "passed": passed,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "expected_failures": expected_failures,
        "unexpected_successes": unexpected_successes,
    }


def events(*, failures=0, errors=0, skipped=0,
           expected_failures=0, unexpected_successes=0, subtests=None, synthetic=None):
    recorded = {
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "expected_failures": expected_failures,
        "unexpected_successes": unexpected_successes,
    }
    return {
        "recorded": recorded,
        "subtests": dict(subtests or {name: 0 for name in recorded}),
        "fixture_or_synthetic": dict(synthetic or {name: 0 for name in recorded}),
        "semantics": (
            "counts classify only TestCase instances observed by startTest; events retain "
            "recorded subtest and fixture/synthetic-holder multiplicity"
        ),
    }


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verify environments with spaces ")
        self.root = Path(self.temporary.name)
        self.paths = {}
        for suite_id in verify.SUITE_ORDER:
            python = self.root / suite_id / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"placeholder")
            self.paths[suite_id] = python

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self, suite_id, *, prefix=None, base_prefix=None):
        selected = self.paths[suite_id]
        prefix_path = Path(prefix) if prefix is not None else selected.parents[1]
        base = Path(base_prefix) if base_prefix is not None else self.root / "base-python"
        return {
            "requested": str(selected),
            "resolved": str(selected.resolve()),
            "executable": str(selected.resolve()),
            "version": "3.12.14",
            "implementation": "CPython",
            "machine": "AMD64",
            "sysconfig_platform": "win-amd64",
            "prefix": str(prefix_path),
            "base_prefix": str(base),
        }

    @staticmethod
    def completed_record(spec, environment, selected_counts=None, successful=True):
        selected_counts = selected_counts or counts()
        return {
            "id": spec.suite_id,
            "unittest_argv": spec.worker_arguments(),
            "worker_argv": [environment["resolved"]],
            "environment": dict(environment),
            "status": "completed" if successful else "failed",
            "reason": None if successful else "one or more tests failed",
            "child_exit_code": 0 if successful else 1,
            "timed_out": False,
            "counts": selected_counts,
            "events": events(),
            "stdout": stream_summary(),
            "stderr": stream_summary(),
        }

    def test_fixed_order_and_qairt_five_modules(self):
        probes = {name: self.environment(name) for name in verify.SUITE_ORDER}
        seen = []

        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            return probes[suite_id]

        def runner(spec, environment, timeout):
            seen.append((spec.suite_id, list(spec.modules), timeout, environment["resolved"]))
            return self.completed_record(spec, environment)

        report, exit_code = verify.run_verification(self.paths, 37, probe, runner)
        self.assertEqual(list(verify.SUITE_ORDER), [item[0] for item in seen])
        self.assertEqual(0, exit_code)
        qairt = seen[-1]
        self.assertEqual(
            [
                "tests.qairt.test_environment",
                "tests.qairt.test_probe",
                "tests.abi.test_inspector",
                "tests.abi.test_inventory",
                "tests.qairt.test_small_graph_pipeline",
            ],
            qairt[1],
        )
        self.assertEqual(list(verify.SUITE_ORDER), report["suite_order"])

    def test_mixed_counts_preserve_every_unittest_category(self):
        payload = {
            "schema_version": verify.SCHEMA_VERSION,
            "suite_id": "baseline",
            "environment": {"executable": str(self.paths["baseline"])},
            "counts": counts(
                passed=1, failures=1, errors=1, skipped=2,
                expected_failures=1, unexpected_successes=1,
            ),
            "events": events(failures=1, errors=1, skipped=2, unexpected_successes=1),
            "successful": False,
        }
        validated = verify._validate_worker_payload(payload, verify.SUITES[0])
        self.assertEqual(7, validated["counts"]["total"])
        self.assertEqual(1, validated["counts"]["passed"])
        self.assertEqual(2, validated["counts"]["skipped"])

    def test_missing_environment_is_not_run_and_later_suites_continue(self):
        seen = []

        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            if suite_id == "reference":
                raise verify.EnvironmentUnavailable("missing reference interpreter")
            return self.environment(suite_id)

        def runner(spec, environment, timeout):
            seen.append(spec.suite_id)
            return self.completed_record(spec, environment)

        report, exit_code = verify.run_verification(self.paths, 30, probe, runner)
        self.assertEqual(["baseline", "fsr-extract", "qairt"], seen)
        self.assertEqual(2, exit_code)
        missing = report["suites"][1]
        self.assertEqual("not_run", missing["status"])
        self.assertIsNone(missing["counts"])
        self.assertIn("missing reference", missing["reason"])

    def test_test_failure_does_not_stop_later_suites(self):
        seen = []

        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            return self.environment(suite_id)

        def runner(spec, environment, timeout):
            seen.append(spec.suite_id)
            if spec.suite_id == "baseline":
                return self.completed_record(
                    spec, environment, counts(passed=2, failures=1), False
                )
            return self.completed_record(spec, environment)

        report, exit_code = verify.run_verification(self.paths, 30, probe, runner)
        self.assertEqual(list(verify.SUITE_ORDER), seen)
        self.assertEqual(1, exit_code)
        self.assertEqual(1, report["summary"]["suites"]["failed"])
        self.assertEqual(1, report["summary"]["tests"]["failures"])

    def test_not_run_exit_takes_precedence_over_failure(self):
        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            if suite_id == "reference":
                raise verify.EnvironmentUnavailable("missing")
            return self.environment(suite_id)

        def runner(spec, environment, timeout):
            return self.completed_record(
                spec,
                environment,
                counts(failures=1, passed=0),
                successful=False,
            ) if spec.suite_id == "baseline" else self.completed_record(spec, environment)

        _, exit_code = verify.run_verification(self.paths, 30, probe, runner)
        self.assertEqual(2, exit_code)

    def test_timeout_and_malformed_worker_result_are_failed(self):
        environment = self.environment("baseline")
        timed_out = verify._run_suite(
            verify.SUITES[0],
            environment,
            4,
            execute=lambda argv, timeout: capture(None, timed_out=True),
        )
        self.assertEqual("failed", timed_out["status"])
        self.assertTrue(timed_out["timed_out"])
        self.assertIn("descendant quiescence was not established", timed_out["reason"])

        def malformed(argv, timeout):
            result = Path(argv[argv.index("--worker-result") + 1])
            result.write_text("not-json", encoding="utf-8")
            return capture(0)

        bad = verify._run_suite(verify.SUITES[0], environment, 4, execute=malformed)
        self.assertEqual("failed", bad["status"])
        self.assertIn("missing or invalid", bad["reason"])

    def test_completed_suites_with_skips_exit_zero_without_counting_skips_as_pass(self):
        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            return self.environment(suite_id)

        def runner(spec, environment, timeout):
            return self.completed_record(spec, environment, counts(passed=2, skipped=3))

        report, exit_code = verify.run_verification(self.paths, 30, probe, runner)
        self.assertEqual(0, exit_code)
        self.assertEqual(8, report["summary"]["tests"]["passed"])
        self.assertEqual(12, report["summary"]["tests"]["skipped"])
        self.assertEqual(20, report["summary"]["tests"]["total"])

    def test_duplicate_and_nonvenv_interpreters_are_not_run(self):
        shared = self.environment("baseline")

        def probe(path):
            suite_id = next(name for name, selected in self.paths.items() if selected == path)
            if suite_id == "reference":
                duplicate = self.environment("reference", prefix=shared["prefix"])
                duplicate["resolved"] = shared["resolved"]
                return duplicate
            if suite_id == "fsr-extract":
                raise verify.EnvironmentUnavailable("selected Python is not a virtual environment")
            return self.environment(suite_id)

        report, exit_code = verify.run_verification(
            self.paths,
            30,
            probe,
            lambda spec, environment, timeout: self.completed_record(spec, environment),
        )
        self.assertEqual(2, exit_code)
        self.assertEqual("not_run", report["suites"][1]["status"])
        self.assertIn("duplicates", report["suites"][1]["reason"])
        self.assertEqual("not_run", report["suites"][2]["status"])
        self.assertIn("not a virtual environment", report["suites"][2]["reason"])

    def test_probe_rejects_non_virtual_environment(self):
        selected = self.paths["baseline"]
        payload = self.environment("baseline", prefix=self.root / "same", base_prefix=self.root / "same")

        def execute(argv, timeout):
            return capture(0, stdout=json.dumps({
                name: payload[name] for name in (
                    "executable", "version", "implementation", "machine",
                    "sysconfig_platform", "prefix", "base_prefix",
                )
            }))

        with self.assertRaisesRegex(verify.EnvironmentUnavailable, "not a virtual environment"):
            verify._probe_environment(selected, execute=execute)

    def test_space_containing_interpreter_is_one_worker_argument(self):
        environment = self.environment("baseline")
        observed = []

        def execute(argv, timeout):
            observed.append(list(argv))
            result = Path(argv[argv.index("--worker-result") + 1])
            result.write_text(json.dumps({
                "schema_version": verify.SCHEMA_VERSION,
                "suite_id": "baseline",
                "environment": {"executable": environment["resolved"]},
                "counts": counts(),
                "events": events(),
                "successful": True,
            }), encoding="utf-8")
            return capture(0)

        record = verify._run_suite(verify.SUITES[0], environment, 5, execute=execute)
        self.assertEqual("completed", record["status"])
        self.assertEqual(environment["resolved"], observed[0][0])

    def test_output_parent_and_overwrite_are_refused_and_publish_is_exclusive(self):
        missing = self.root / "missing" / "report.json"
        with self.assertRaisesRegex(verify.VerificationError, "parent does not exist"):
            verify._validate_output(missing)
        output = self.root / "report.json"
        selected = verify._validate_output(output)
        verify._publish_report(selected, {"ok": True})
        self.assertEqual({"ok": True}, json.loads(output.read_text(encoding="utf-8")))
        with self.assertRaisesRegex(verify.VerificationError, "already exists"):
            verify._validate_output(output)
        with self.assertRaisesRegex(verify.VerificationError, "could not publish"):
            verify._publish_report(output, {"replace": False})

    def test_worker_result_counts_pass_failure_and_skip_without_text_parsing(self):
        class Passing(unittest.TestCase):
            def runTest(self):
                pass

        class Failing(unittest.TestCase):
            def runTest(self):
                self.fail("expected nested failure")

        class Skipping(unittest.TestCase):
            @unittest.skip("expected nested skip")
            def runTest(self):
                pass

        suite = unittest.TestSuite([Passing(), Failing(), Skipping()])
        selected_counts, selected_events, successful = verify._run_loaded_suite(
            suite, io.StringIO()
        )
        self.assertFalse(successful)
        self.assertEqual(3, selected_counts["total"])
        self.assertEqual(1, selected_counts["passed"])
        self.assertEqual(1, selected_counts["failures"])
        self.assertEqual(1, selected_counts["skipped"])
        self.assertEqual(1, selected_events["recorded"]["failures"])
        self.assertEqual(0, selected_events["subtests"]["failures"])

    def test_multiple_and_mixed_subtest_events_classify_parent_once(self):
        class MultipleFailures(unittest.TestCase):
            def runTest(self):
                for value in (1, 2):
                    with self.subTest(value=value):
                        self.assertEqual(0, value)

        class FailureAndSkip(unittest.TestCase):
            def runTest(self):
                with self.subTest(kind="failure"):
                    self.fail("nested failure")
                with self.subTest(kind="skip"):
                    self.skipTest("nested skip")

        suite = unittest.TestSuite([MultipleFailures(), FailureAndSkip()])
        selected_counts, selected_events, successful = verify._run_loaded_suite(
            suite, io.StringIO()
        )
        self.assertFalse(successful)
        self.assertEqual(2, selected_counts["total"])
        self.assertEqual(0, selected_counts["passed"])
        self.assertEqual(2, selected_counts["failures"])
        self.assertEqual(0, selected_counts["skipped"])
        self.assertEqual(3, selected_events["recorded"]["failures"])
        self.assertEqual(1, selected_events["recorded"]["skipped"])
        self.assertEqual(3, selected_events["subtests"]["failures"])
        self.assertEqual(1, selected_events["subtests"]["skipped"])

    def test_set_up_class_error_is_synthetic_and_fails_worker(self):
        class BrokenFixture(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError("fixture failed before startTest")

            def test_never_started(self):
                self.fail("must not run")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(BrokenFixture)
        selected_counts, selected_events, successful = verify._run_loaded_suite(
            suite, io.StringIO()
        )
        self.assertFalse(successful)
        self.assertEqual(0, selected_counts["total"])
        self.assertEqual(0, selected_counts["passed"])
        self.assertEqual(0, selected_counts["errors"])
        self.assertEqual(1, selected_events["recorded"]["errors"])
        self.assertEqual(1, selected_events["fixture_or_synthetic"]["errors"])

        payload = {
            "schema_version": verify.SCHEMA_VERSION,
            "suite_id": "baseline",
            "environment": {"executable": str(self.paths["baseline"])},
            "counts": selected_counts,
            "events": selected_events,
            "successful": successful,
        }
        self.assertIs(payload, verify._validate_worker_payload(payload, verify.SUITES[0]))

    def test_set_up_class_skip_is_synthetic_but_worker_is_successful(self):
        class SkippedFixture(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest("class fixture capability unavailable")

            def test_never_started(self):
                self.fail("must not run")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SkippedFixture)
        selected_counts, selected_events, successful = verify._run_loaded_suite(
            suite, io.StringIO()
        )
        self.assertTrue(successful)
        self.assertEqual(0, selected_counts["total"])
        self.assertEqual(0, selected_counts["skipped"])
        self.assertEqual(1, selected_events["recorded"]["skipped"])
        self.assertEqual(1, selected_events["fixture_or_synthetic"]["skipped"])

        payload = {
            "schema_version": verify.SCHEMA_VERSION,
            "suite_id": "baseline",
            "environment": {"executable": str(self.paths["baseline"])},
            "counts": selected_counts,
            "events": selected_events,
            "successful": successful,
        }
        self.assertIs(payload, verify._validate_worker_payload(payload, verify.SUITES[0]))

    def test_stream_summary_excludes_bytes_appended_after_snapshot(self):
        initial = b"initial snapshot"
        late = b" late output"
        with tempfile.TemporaryFile() as raw:
            raw.write(initial)
            raw.flush()

            class GrowingStream:
                def __init__(self, wrapped):
                    self.wrapped = wrapped
                    self.grew = False

                def fileno(self):
                    return self.wrapped.fileno()

                def flush(self):
                    return self.wrapped.flush()

                def seek(self, offset, whence=0):
                    return self.wrapped.seek(offset, whence)

                def read(self, size=-1):
                    if not self.grew:
                        position = self.wrapped.tell()
                        self.wrapped.seek(0, os.SEEK_END)
                        self.wrapped.write(late)
                        self.wrapped.flush()
                        self.wrapped.seek(position)
                        self.grew = True
                    return self.wrapped.read(size)

            summary = verify._stream_summary(GrowingStream(raw))

        self.assertEqual(len(initial), summary["snapshot_byte_count"])
        self.assertEqual(len(initial), summary["byte_count"])
        self.assertTrue(summary["snapshot_complete"])
        self.assertEqual(initial.decode(), summary["tail"])
        self.assertEqual(
            __import__("hashlib").sha256(initial).hexdigest(), summary["sha256"]
        )
        self.assertEqual(len(late), summary["late_output_excluded_byte_count"])
        self.assertIn("appended", summary["capture_semantics"])


if __name__ == "__main__":
    unittest.main()

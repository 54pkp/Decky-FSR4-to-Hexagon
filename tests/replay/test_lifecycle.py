from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "replay" / "lifecycle.py"
SCENARIO = REPO / "tools" / "replay" / "fixtures" / "identity-replay.json"
MANIFEST = REPO / "tools" / "model" / "fixtures" / "synthetic-valid.json"

spec = importlib.util.spec_from_file_location("lifecycle", TOOL)
lifecycle = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(lifecycle)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

    def new_context(self):
        return lifecycle.LifecycleContext(self.manifest, self.scenario["context"])

    def submit(self, context, request=None):
        context.submit(
            self.scenario["request"] if request is None else request,
            self.scenario["history"],
            self.scenario["motion_vectors"],
        )

    def submit_with_committed_history(self, context, request):
        context.submit(request, None, self.scenario["motion_vectors"])

    def assert_invalid(self, call, expected_path):
        with self.assertRaises(lifecycle.LifecycleInvalid) as caught:
            call()
        self.assertIn(expected_path, str(caught.exception))

    def test_fixture_is_closed_host_only_and_returns_h3_cpu_output(self):
        output = lifecycle.validate_scenario(self.manifest, self.scenario)
        self.assertEqual(self.scenario["expected_output"], output)
        self.assertTrue(self.scenario["example_only"])
        self.assertFalse(self.scenario["production_ready"])
        self.assertEqual("not_run", self.scenario["validation_gate"])
        self.assertEqual("cpu_reference", self.scenario["backend"])

        value = copy.deepcopy(self.scenario)
        value["unexpected"] = True
        self.assert_invalid(lambda: lifecycle.validate_scenario(self.manifest, value), "$.unexpected")

    def test_submit_delegates_numerical_work_to_h3_reprojection(self):
        context = self.new_context()
        sentinel = [[41, None]]
        with mock.patch.object(
            lifecycle.spatial_reference,
            "reproject_backward",
            return_value=sentinel,
        ) as reproject:
            self.submit(context)
            result = context.complete(self.scenario["request"])
        reproject.assert_called_once_with(
            self.scenario["history"], self.scenario["motion_vectors"]
        )
        self.assertEqual(sentinel, result)
        self.assertIsNot(sentinel, result)

    def test_h2_manifest_id_is_bound_to_scenario_and_context(self):
        bad_root = copy.deepcopy(self.scenario)
        bad_root["manifest_id"] = "synthetic-other"
        self.assert_invalid(
            lambda: lifecycle.validate_scenario(self.manifest, bad_root), "$.manifest_id"
        )

        bad_context = copy.deepcopy(self.scenario["context"])
        bad_context["model_manifest_id"] = "synthetic-other"
        self.assert_invalid(
            lambda: lifecycle.LifecycleContext(self.manifest, bad_context),
            "context.model_manifest_id",
        )

        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["model_manifest_id"] = "not-synthetic"
        self.assert_invalid(
            lambda: lifecycle.LifecycleContext(bad_manifest, self.scenario["context"]),
            "manifest",
        )

    def test_each_completion_identity_mismatch_preserves_active_request(self):
        replacements = {
            "service_instance_id": "service-wrong",
            "session_id": "session-wrong",
            "context_id": "context-wrong",
            "frame_id": "2",
            "history_generation": "1",
            "model_manifest_id": "synthetic-wrong",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                context = self.new_context()
                self.submit(context)
                expected_active = context.active_identity
                mismatch = copy.deepcopy(self.scenario["request"])
                mismatch[field] = replacement
                self.assert_invalid(lambda: context.complete(mismatch), f"completion.{field}")
                self.assertEqual(expected_active, context.active_identity)
                self.assertEqual(
                    self.scenario["expected_output"],
                    context.complete(self.scenario["request"]),
                )
                context.result_consumed(self.scenario["request"], True)

    def test_second_submit_is_rejected_without_replacing_active_request(self):
        context = self.new_context()
        self.submit(context)
        original = context.active_identity
        second = copy.deepcopy(self.scenario["request"])
        second["frame_id"] = "2"
        self.assert_invalid(lambda: self.submit(context, second), "active request")
        self.assertEqual(original, context.active_identity)
        self.assertEqual(
            self.scenario["expected_output"], context.complete(self.scenario["request"])
        )

    def test_concurrent_submits_install_exactly_one_active_request(self):
        context = self.new_context()
        barrier = threading.Barrier(3)
        outcomes = []
        outcome_lock = threading.Lock()

        def submit_frame(frame_id):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = frame_id
            barrier.wait()
            try:
                self.submit(context, request)
                outcome = ("accepted", request)
            except lifecycle.LifecycleInvalid as exc:
                outcome = ("rejected", str(exc))
            with outcome_lock:
                outcomes.append(outcome)

        threads = [
            threading.Thread(target=submit_frame, args=("1",)),
            threading.Thread(target=submit_frame, args=("2",)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        self.assertEqual(1, sum(kind == "accepted" for kind, _ in outcomes))
        self.assertEqual(1, sum(kind == "rejected" for kind, _ in outcomes))
        rejected = next(value for kind, value in outcomes if kind == "rejected")
        self.assertIn("active request", rejected)
        accepted = next(value for kind, value in outcomes if kind == "accepted")
        self.assertEqual(accepted, context.active_identity)
        context.complete(accepted)

    def test_old_duplicate_and_spurious_completions_are_rejected(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], True)
        self.assertEqual("1", context.last_completed_frame_id)
        self.assert_invalid(
            lambda: self.submit(context, self.scenario["request"]), "request.frame_id"
        )
        self.assert_invalid(
            lambda: context.complete(self.scenario["request"]), "no active request"
        )

        older = copy.deepcopy(self.scenario["request"])
        older["frame_id"] = "0"
        self.assert_invalid(lambda: self.submit(context, older), "request.frame_id")

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.submit_with_committed_history(context, next_request)
        active = context.active_identity
        self.assert_invalid(
            lambda: context.complete(self.scenario["request"]), "completion.frame_id"
        )
        self.assertEqual(active, context.active_identity)
        context.complete(next_request)

    def test_correct_completion_allows_strictly_newer_frame(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], True)
        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.submit_with_committed_history(context, next_request)
        self.assertEqual(next_request, context.active_identity)
        self.assertEqual(self.scenario["expected_output"], context.complete(next_request))
        self.assertEqual("2", context.last_completed_frame_id)

    def test_completion_requires_consumption_before_history_commit_or_next_submit(self):
        context = self.new_context()
        self.submit(context)
        output = context.complete(self.scenario["request"])
        self.assertEqual("pending_consumption", context.state)
        self.assertIsNone(context.committed_history)
        self.assertIsNone(context.last_committed_frame_id)

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.assert_invalid(lambda: self.submit(context, next_request), "active request")

        output[0][0] = 999
        context.result_consumed(self.scenario["request"], True)
        self.assertEqual("ready", context.state)
        self.assertEqual(self.scenario["history"], context.committed_history)
        self.assertNotEqual(output, context.committed_history)
        self.assertEqual("1", context.last_committed_frame_id)
        external_history = context.committed_history
        external_history[0][0] = 999
        self.assertEqual(self.scenario["history"], context.committed_history)
        self.submit_with_committed_history(context, next_request)

    def test_result_consumed_mismatch_preserves_pending_and_duplicate_is_idempotent(self):
        replacements = {
            "service_instance_id": "service-wrong",
            "session_id": "session-wrong",
            "context_id": "context-wrong",
            "frame_id": "2",
            "history_generation": "1",
            "model_manifest_id": "synthetic-wrong",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                context = self.new_context()
                self.submit(context)
                context.complete(self.scenario["request"])
                mismatch = copy.deepcopy(self.scenario["request"])
                mismatch[field] = replacement
                self.assert_invalid(
                    lambda: context.result_consumed(mismatch, True),
                    f"result_consumed.{field}",
                )
                self.assertEqual("pending_consumption", context.state)
                self.assertIsNone(context.committed_history)

        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], True)
        committed = context.committed_history
        context.result_consumed(self.scenario["request"], True)
        self.assertEqual(committed, context.committed_history)
        self.assert_invalid(
            lambda: context.result_consumed(self.scenario["request"], False),
            "result_consumed.success",
        )

    def test_execution_timeout_retains_resources_until_matching_completion(self):
        context = self.new_context()
        self.submit(context)
        context.timeout(self.scenario["request"])
        self.assertEqual("executing_timed_out", context.state)
        self.assertEqual(self.scenario["request"], context.active_identity)
        self.assertIsNone(context.committed_history)

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.assert_invalid(lambda: self.submit(context, next_request), "active request")
        mismatch = copy.deepcopy(self.scenario["request"])
        mismatch["frame_id"] = "9"
        self.assert_invalid(lambda: context.complete(mismatch), "completion.frame_id")
        self.assertEqual(self.scenario["request"], context.active_identity)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual("invalid", context.state)
        self.assertIsNone(context.active_identity)
        self.assert_invalid(lambda: self.submit(context, next_request), "reset is required")

    def test_pending_consumption_timeout_never_commits_candidate_history(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.timeout(self.scenario["request"])
        self.assertEqual("pending_consumption_timed_out", context.state)
        self.assertEqual(self.scenario["request"], context.active_identity)

        context.result_consumed(self.scenario["request"], True)
        self.assertEqual("invalid", context.state)
        self.assertIsNone(context.committed_history)
        self.assertIsNone(context.last_committed_frame_id)

    def test_failed_consumption_invalidates_previously_committed_history(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], True)
        self.assertIsNotNone(context.committed_history)

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.submit_with_committed_history(context, next_request)
        context.complete(next_request)
        context.result_consumed(next_request, False)
        self.assertEqual("invalid", context.state)
        self.assertIsNone(context.committed_history)
        self.assertIsNone(context.last_committed_frame_id)

    def test_reset_is_idempotent_advances_generation_and_keeps_frame_monotonic(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], True)

        self.assertEqual("1", context.reset("reset-1", "0"))
        self.assertEqual("1", context.reset("reset-1", "0"))
        self.assertEqual("1", context.history_generation)
        self.assertEqual("ready", context.state)
        self.assertIsNone(context.committed_history)

        old_generation = copy.deepcopy(self.scenario["request"])
        old_generation["frame_id"] = "2"
        self.assert_invalid(
            lambda: self.submit(context, old_generation), "request.history_generation"
        )
        reused_frame = copy.deepcopy(self.scenario["request"])
        reused_frame["history_generation"] = "1"
        self.assert_invalid(lambda: self.submit(context, reused_frame), "request.frame_id")
        next_request = copy.deepcopy(reused_frame)
        next_request["frame_id"] = "2"
        self.submit(context, next_request)

        self.assertEqual("2", context.reset("reset-2", "1"))
        self.assertEqual("1", context.reset("reset-1", "0"))
        self.assertEqual("2", context.history_generation)

    def test_reset_generation_overflow_is_atomic(self):
        identity = copy.deepcopy(self.scenario["context"])
        identity["history_generation"] = "9" * lifecycle.MAX_DECIMAL_DIGITS
        context = lifecycle.LifecycleContext(self.manifest, identity)
        self.assert_invalid(
            lambda: context.reset("reset-overflow", identity["history_generation"]),
            "reset.history_generation",
        )
        self.assertEqual(identity["history_generation"], context.history_generation)
        self.assertEqual("ready", context.state)

    def test_reset_isolates_old_generation_resources_from_new_history(self):
        context = self.new_context()
        self.submit(context)
        self.assertEqual("1", context.reset("reset-running", "0"))
        self.assertEqual(1, context.isolated_resource_count)
        self.assertIsNone(context.active_identity)

        new_request = copy.deepcopy(self.scenario["request"])
        new_request["frame_id"] = "2"
        new_request["history_generation"] = "1"
        new_history = [[9, 8, 7], [6, 5, 4], [3, 2, 1]]
        context.submit(new_request, new_history, self.scenario["motion_vectors"])
        new_output = context.complete(new_request)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual(0, context.isolated_resource_count)
        self.assertEqual("pending_consumption", context.state)
        self.assertEqual(new_request, context.active_identity)
        self.assertIsNone(context.committed_history)

        context.result_consumed(new_request, True)
        self.assertEqual(new_history, context.committed_history)
        self.assertNotEqual(new_output, context.committed_history)

    def test_reset_isolates_pending_old_result_so_late_success_cannot_commit(self):
        context = self.new_context()
        self.submit(context)
        old_output = context.complete(self.scenario["request"])
        self.assertEqual("1", context.reset("reset-pending", "0"))
        self.assertEqual(1, context.isolated_resource_count)
        self.assertGreater(context.isolated_resource_capacity_cells, 0)

        context.result_consumed(self.scenario["request"], True)
        self.assertEqual(0, context.isolated_resource_count)
        self.assertEqual(0, context.isolated_resource_capacity_cells)
        self.assertIsNone(context.committed_history)
        self.assertIsNotNone(old_output)

    def test_retained_resource_count_backpressures_without_evicting_old_work(self):
        context = self.new_context()
        retained = []
        for generation in range(lifecycle.MAX_RETAINED_RESOURCE_COUNT):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            context.timeout(request)
            self.assertEqual(
                str(generation + 1),
                context.reset(f"budget-reset-{generation}", str(generation)),
            )
            retained.append(request)

        self.assertEqual(
            lifecycle.MAX_RETAINED_RESOURCE_COUNT, context.isolated_resource_count
        )
        self.assertEqual(
            lifecycle.MAX_RETAINED_RESOURCE_COUNT, context.retained_resource_count
        )
        generation_before = context.history_generation
        history_before = context.committed_history
        rejected = copy.deepcopy(self.scenario["request"])
        rejected["frame_id"] = str(lifecycle.MAX_RETAINED_RESOURCE_COUNT + 1)
        rejected["history_generation"] = generation_before
        self.assert_invalid(lambda: self.submit(context, rejected), "resource count budget")
        self.assertEqual(generation_before, context.history_generation)
        self.assertEqual(history_before, context.committed_history)
        self.assertEqual(
            lifecycle.MAX_RETAINED_RESOURCE_COUNT, context.isolated_resource_count
        )

        self.assertIsNone(context.complete(retained[0]))
        self.assertEqual(
            lifecycle.MAX_RETAINED_RESOURCE_COUNT - 1,
            context.isolated_resource_count,
        )
        self.submit(context, rejected)
        self.assertEqual(rejected, context.active_identity)

    def test_retained_capacity_backpressures_until_matching_completion(self):
        context = self.new_context()
        width = lifecycle.spatial_reference.MAX_WIDTH
        height = lifecycle.spatial_reference.MAX_HEIGHT
        history = [[0 for _ in range(width)] for _ in range(height)]
        vectors = [[[0, 0] for _ in range(width)] for _ in range(height)]
        first = copy.deepcopy(self.scenario["request"])
        context.submit(first, history, vectors)
        self.assertEqual(
            lifecycle.MAX_RETAINED_CAPACITY_CELLS,
            context.retained_resource_capacity_cells,
        )
        context.timeout(first)
        context.reset("capacity-reset", "0")
        self.assertEqual(
            lifecycle.MAX_RETAINED_CAPACITY_CELLS,
            context.isolated_resource_capacity_cells,
        )

        second = copy.deepcopy(first)
        second["frame_id"] = "2"
        second["history_generation"] = "1"
        generation_before = context.history_generation
        history_before = context.committed_history
        self.assert_invalid(
            lambda: context.submit(second, history, vectors), "resource capacity budget"
        )
        self.assertEqual(generation_before, context.history_generation)
        self.assertEqual(history_before, context.committed_history)
        self.assertEqual(1, context.isolated_resource_count)

        self.assertIsNone(context.complete(first))
        self.assertEqual(0, context.retained_resource_capacity_cells)
        context.submit(second, history, vectors)
        self.assertEqual(second, context.active_identity)

    def test_submit_rejects_each_fixed_identity_mismatch(self):
        replacements = {
            "service_instance_id": "other-service",
            "session_id": "other-session",
            "context_id": "other-context",
            "history_generation": "1",
            "model_manifest_id": "synthetic-other",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                request = copy.deepcopy(self.scenario["request"])
                request[field] = replacement
                context = self.new_context()
                self.assert_invalid(lambda: self.submit(context, request), f"request.{field}")
                self.assertIsNone(context.active_identity)

    def test_identifiers_are_strict_and_closed(self):
        invalid_values = (1, "", " ")
        for field in ("service_instance_id", "session_id", "context_id", "model_manifest_id"):
            for invalid in invalid_values:
                with self.subTest(field=field, invalid=invalid):
                    context_identity = copy.deepcopy(self.scenario["context"])
                    context_identity[field] = invalid
                    self.assert_invalid(
                        lambda: lifecycle.LifecycleContext(self.manifest, context_identity),
                        f"context.{field}",
                    )

        for field in ("frame_id", "history_generation"):
            for invalid in (-1, "-1", "01", "+1", "1.0", "١"):
                with self.subTest(field=field, invalid=invalid):
                    request = copy.deepcopy(self.scenario["request"])
                    request[field] = invalid
                    self.assert_invalid(
                        lambda: self.submit(self.new_context(), request), f"request.{field}"
                    )

        request = copy.deepcopy(self.scenario["request"])
        request["unknown"] = "value"
        self.assert_invalid(
            lambda: self.submit(self.new_context(), request), "request.unknown"
        )

    def test_malformed_payload_does_not_create_active_request(self):
        context = self.new_context()
        bad_vectors = copy.deepcopy(self.scenario["motion_vectors"])
        bad_vectors[0][0] = [0]
        self.assert_invalid(
            lambda: context.submit(self.scenario["request"], self.scenario["history"], bad_vectors),
            "request payload",
        )
        self.assertIsNone(context.active_identity)

    def test_deep_loaded_payload_is_a_contract_error_and_keeps_context_idle(self):
        value = copy.deepcopy(self.scenario)
        deep_history = 0
        for _ in range(600):
            deep_history = [deep_history]
        value["history"] = deep_history

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep-payload.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = lifecycle.load_scenario(path)
            context = self.new_context()
            self.assert_invalid(
                lambda: context.submit(
                    loaded["request"], loaded["history"], loaded["motion_vectors"]
                ),
                "request payload",
            )
            self.assertIsNone(context.active_identity)
            cli = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "verify",
                    "--manifest",
                    str(MANIFEST),
                    "--scenario",
                    str(path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, cli.returncode, cli.stderr)
        self.assertIn("request payload", cli.stderr)

    def test_expected_output_is_independently_checked(self):
        mismatch = copy.deepcopy(self.scenario)
        mismatch["expected_output"][0][0] = 99
        self.assert_invalid(
            lambda: lifecycle.validate_scenario(self.manifest, mismatch), "$.expected_output"
        )
        bad_type = copy.deepcopy(self.scenario)
        bad_type["expected_output"][0][0] = True
        self.assert_invalid(
            lambda: lifecycle.validate_scenario(self.manifest, bad_type),
            "$.expected_output[0][0]",
        )

    def test_cli_returns_zero_one_and_two(self):
        valid = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "verify",
                "--manifest",
                str(MANIFEST),
                "--scenario",
                str(SCENARIO),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertIn("valid lifecycle scenario:", valid.stdout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mismatch_path = root / "mismatch.json"
            mismatch = copy.deepcopy(self.scenario)
            mismatch["request"]["frame_id"] = "01"
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            contract = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(MANIFEST), "--scenario", str(mismatch_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            malformed_path = root / "malformed.json"
            malformed_path.write_text("{", encoding="utf-8")
            malformed = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(MANIFEST), "--scenario", str(malformed_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            missing_manifest = subprocess.run(
                [sys.executable, str(TOOL), "verify", "--manifest", str(root / "missing.json"), "--scenario", str(SCENARIO)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, contract.returncode, contract.stderr)
        self.assertIn("invalid lifecycle scenario:", contract.stderr)
        self.assertEqual(2, malformed.returncode, malformed.stderr)
        self.assertIn("scenario is not valid JSON", malformed.stderr)
        self.assertEqual(2, missing_manifest.returncode, missing_manifest.stderr)
        self.assertIn("manifest does not exist", missing_manifest.stderr)

    def test_loader_rejects_duplicate_nonfinite_oversized_long_and_deep_json(self):
        payloads = (
            ('{"context": {}, "context": {}}', "duplicate object key 'context'"),
            ('{"value": NaN}', "non-finite JSON number NaN"),
            ('{"value": 1e999}', "non-finite JSON number 1e999"),
            (
                '{"value": ' + ("9" * 5_000) + "}",
                f"integer exceeds digit limit {lifecycle.MAX_JSON_INTEGER_DIGITS}",
            ),
            (
                ("[" * 20_000) + "0" + ("]" * 20_000),
                "JSON nesting exceeds parser limit",
            ),
        )
        for payload, message in payloads:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "bad.json"
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(lifecycle.LifecycleInputError) as caught:
                    lifecycle.load_scenario(path)
                self.assertIn(message, str(caught.exception))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * (lifecycle.MAX_SCENARIO_BYTES + 1))
            with self.assertRaises(lifecycle.LifecycleInputError) as caught:
                lifecycle.load_scenario(path)
        self.assertIn("input limit", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

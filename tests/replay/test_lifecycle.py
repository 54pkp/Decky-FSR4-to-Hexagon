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

    def test_consumption_idempotency_window_is_bounded_and_expiry_is_inert(self):
        context = self.new_context()
        consumed = []
        for generation in range(lifecycle.MAX_CONSUMED_RECORD_COUNT):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            context.complete(request)
            context.result_consumed(request, True)
            consumed.append(request)
            context.reset(f"consumed-reset-{generation}", str(generation))

        self.assertEqual(
            lifecycle.MAX_CONSUMED_RECORD_COUNT, context.consumed_record_count
        )
        context.result_consumed(consumed[0], True)
        self.assert_invalid(
            lambda: context.result_consumed(consumed[0], False),
            "result_consumed.success",
        )

        newest = copy.deepcopy(self.scenario["request"])
        newest["frame_id"] = str(lifecycle.MAX_CONSUMED_RECORD_COUNT + 1)
        newest["history_generation"] = str(lifecycle.MAX_CONSUMED_RECORD_COUNT)
        self.submit(context, newest)
        context.complete(newest)
        context.result_consumed(newest, True)
        self.assertEqual(
            lifecycle.MAX_CONSUMED_RECORD_COUNT, context.consumed_record_count
        )

        generation_before = context.history_generation
        history_before = context.committed_history
        committed_before = context.last_committed_frame_id
        self.assert_invalid(
            lambda: context.result_consumed(consumed[0], True),
            "outside the retained idempotency window",
        )
        self.assertEqual(generation_before, context.history_generation)
        self.assertEqual(history_before, context.committed_history)
        self.assertEqual(committed_before, context.last_committed_frame_id)
        self.assertEqual("ready", context.state)

        active = copy.deepcopy(newest)
        active["frame_id"] = str(lifecycle.MAX_CONSUMED_RECORD_COUNT + 2)
        self.submit_with_committed_history(context, active)
        active_before = context.active_identity
        retained_before = context.retained_resource_count
        self.assert_invalid(
            lambda: context.result_consumed(consumed[0], True),
            "result_consumed.frame_id",
        )
        self.assertEqual(active_before, context.active_identity)
        self.assertEqual(retained_before, context.retained_resource_count)
        self.assertEqual("executing", context.state)

    def test_concurrent_false_consumption_retries_are_idempotent_and_conflicts_reject(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.result_consumed(self.scenario["request"], False)
        history_before = context.committed_history
        generation_before = context.history_generation
        errors = []
        barrier = threading.Barrier(64)

        def retry(success):
            try:
                barrier.wait(timeout=5)
                context.result_consumed(self.scenario["request"], success)
            except Exception as exc:
                errors.append((success, exc))

        threads = [
            threading.Thread(target=retry, args=(index % 2 == 0,))
            for index in range(64)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "consumption retry thread exceeded timeout")

        self.assertEqual(32, len(errors))
        self.assertTrue(all(success is True for success, _ in errors))
        self.assertTrue(
            all("conflicts with the recorded notification" in str(exc) for _, exc in errors)
        )
        self.assertEqual(1, context.consumed_record_count)
        self.assertEqual(0, context.retained_resource_count)
        self.assertEqual(history_before, context.committed_history)
        self.assertEqual(generation_before, context.history_generation)

    def test_concurrent_reset_retries_return_one_result_and_conflicts_reject(self):
        context = self.new_context()
        results = []
        errors = []
        barrier = threading.Barrier(64)

        def retry(expected_generation):
            try:
                barrier.wait(timeout=5)
                results.append(context.reset("concurrent-reset", expected_generation))
            except Exception as exc:
                errors.append((expected_generation, exc))

        threads = [threading.Thread(target=retry, args=("0",)) for _ in range(64)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "reset retry thread exceeded timeout")
        self.assertEqual(["1"] * 64, sorted(results))
        self.assertEqual([], errors)
        self.assertEqual("1", context.history_generation)
        self.assertEqual(1, context.reset_result_count)

        results.clear()
        errors.clear()
        barrier = threading.Barrier(64)
        threads = [
            threading.Thread(target=retry, args=("0" if index % 2 == 0 else "1",))
            for index in range(64)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "reset conflict thread exceeded timeout")
        self.assertEqual(["1"] * 32, sorted(results))
        self.assertEqual(32, len(errors))
        self.assertTrue(all(expected == "1" for expected, _ in errors))
        self.assertTrue(all("already used with different parameters" in str(exc) for _, exc in errors))
        self.assertEqual("1", context.history_generation)
        self.assertEqual(1, context.reset_result_count)

    def test_idempotency_namespaces_remain_independent_through_long_windows(self):
        context = self.new_context()
        consumed = []
        for generation in range(32):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            context.complete(request)
            success = generation % 2 == 0
            context.result_consumed(request, success)
            consumed.append((request, success))
            self.assertEqual(
                str(generation + 1),
                context.reset(f"long-reset-{generation}", str(generation)),
            )

        self.assertEqual(lifecycle.MAX_CONSUMED_RECORD_COUNT, context.consumed_record_count)
        self.assertEqual(lifecycle.MAX_RESET_RESULT_COUNT, context.reset_result_count)
        recent_consumed, recent_success = consumed[-1]
        context.result_consumed(recent_consumed, recent_success)

        for generation in range(32, 64):
            self.assertEqual(
                str(generation + 1),
                context.reset(f"reset-only-{generation}", str(generation)),
            )
        self.assertEqual(lifecycle.MAX_CONSUMED_RECORD_COUNT, context.consumed_record_count)
        context.result_consumed(recent_consumed, recent_success)
        self.assertEqual(lifecycle.MAX_RESET_RESULT_COUNT, context.reset_result_count)

        latest_reset_id = "reset-only-63"
        request = copy.deepcopy(self.scenario["request"])
        request["history_generation"] = "64"
        for offset in range(32):
            request["frame_id"] = str(33 + offset)
            if offset == 0:
                self.submit(context, request)
            else:
                self.submit_with_committed_history(context, request)
            context.complete(request)
            context.result_consumed(request, True)
            request = copy.deepcopy(request)
        self.assertEqual(lifecycle.MAX_CONSUMED_RECORD_COUNT, context.consumed_record_count)
        self.assertEqual(lifecycle.MAX_RESET_RESULT_COUNT, context.reset_result_count)
        self.assertEqual("64", context.reset(latest_reset_id, "63"))

        with self.assertRaisesRegex(
            lifecycle.LifecycleInvalid, "outside the retained idempotency window"
        ):
            context.result_consumed(consumed[0][0], consumed[0][1])
        with self.assertRaisesRegex(
            lifecycle.LifecycleInvalid, "reset.history_generation"
        ):
            context.reset("long-reset-0", "0")

    def test_expired_consumption_notification_cannot_release_isolated_resource(self):
        context = self.new_context()
        consumed = []
        for generation in range(lifecycle.MAX_CONSUMED_RECORD_COUNT + 1):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            context.complete(request)
            context.result_consumed(request, True)
            consumed.append(request)
            context.reset(f"expiry-reset-{generation}", str(generation))

        isolated = copy.deepcopy(self.scenario["request"])
        isolated["frame_id"] = str(len(consumed) + 1)
        isolated["history_generation"] = str(len(consumed))
        self.submit(context, isolated)
        context.complete(isolated)
        context.reset("isolate-after-expiry", str(len(consumed)))
        retained_capacity = context.retained_resource_capacity_cells

        self.assert_invalid(
            lambda: context.result_consumed(consumed[0], True),
            "outside the retained idempotency window",
        )
        self.assertEqual(1, context.isolated_resource_count)
        self.assertEqual(retained_capacity, context.retained_resource_capacity_cells)
        context.result_consumed(isolated, True)
        self.assertEqual(0, context.retained_resource_count)

    def test_fresh_context_does_not_claim_cross_restart_idempotency(self):
        first = self.new_context()
        self.submit(first)
        first.complete(self.scenario["request"])
        first.result_consumed(self.scenario["request"], False)
        self.assertEqual("1", first.reset("restart-reset", "0"))

        reconstructed = self.new_context()
        self.submit(reconstructed)
        reconstructed.complete(self.scenario["request"])
        reconstructed.result_consumed(self.scenario["request"], True)
        self.assertEqual(self.scenario["history"], reconstructed.committed_history)
        self.assertEqual("1", reconstructed.reset("restart-reset", "0"))

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

    def test_execution_failure_retains_resources_until_matching_completion(self):
        context = self.new_context()
        self.submit(context)
        retained_before = context.retained_resource_capacity_cells

        context.execution_failed(self.scenario["request"])
        context.execution_failed(self.scenario["request"])
        self.assertEqual("execution_failed", context.state)
        self.assertEqual(self.scenario["request"], context.active_identity)
        self.assertEqual(1, context.retained_resource_count)
        self.assertEqual(retained_before, context.retained_resource_capacity_cells)
        self.assertIsNone(context.committed_history)

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.assert_invalid(lambda: self.submit(context, next_request), "active request")
        replacements = {
            "service_instance_id": "service-wrong",
            "session_id": "session-wrong",
            "context_id": "context-wrong",
            "frame_id": "9",
            "history_generation": "1",
            "model_manifest_id": "synthetic-wrong",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                mismatch = copy.deepcopy(self.scenario["request"])
                mismatch[field] = replacement
                self.assert_invalid(
                    lambda: context.execution_failed(mismatch),
                    f"execution_failure.{field}",
                )
                self.assertEqual("execution_failed", context.state)
                self.assertEqual(1, context.retained_resource_count)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual(0, context.retained_resource_count)
        self.assertEqual("invalid", context.state)
        self.assert_invalid(lambda: self.submit(context, next_request), "reset is required")

    def test_execution_failure_rejects_pending_result_without_state_change(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        retained_before = context.retained_resource_capacity_cells

        self.assert_invalid(
            lambda: context.execution_failed(self.scenario["request"]),
            "active request is not executing",
        )
        self.assertEqual("pending_consumption", context.state)
        self.assertEqual(retained_before, context.retained_resource_capacity_cells)
        self.assertIsNone(context.committed_history)

    def test_late_old_generation_failure_cannot_pollute_new_history(self):
        context = self.new_context()
        self.submit(context)
        context.reset("failure-reset", "0")

        current = copy.deepcopy(self.scenario["request"])
        current["frame_id"] = "2"
        current["history_generation"] = "1"
        current_history = [[9, 8, 7], [6, 5, 4], [3, 2, 1]]
        context.submit(current, current_history, self.scenario["motion_vectors"])
        context.complete(current)
        context.result_consumed(current, True)
        committed_before = context.committed_history

        context.execution_failed(self.scenario["request"])
        context.execution_failed(self.scenario["request"])
        self.assertEqual(committed_before, context.committed_history)
        self.assertEqual("ready", context.state)
        self.assertEqual(1, context.isolated_resource_count)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual(0, context.isolated_resource_count)
        self.assertEqual(committed_before, context.committed_history)

    def test_close_during_execution_is_idempotent_and_waits_for_completion(self):
        context = self.new_context()
        self.submit(context)
        retained_before = context.retained_resource_capacity_cells

        replacements = {
            "service_instance_id": "service-wrong",
            "session_id": "session-wrong",
            "context_id": "context-wrong",
            "history_generation": "1",
            "model_manifest_id": "synthetic-wrong",
        }
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                mismatch = copy.deepcopy(self.scenario["context"])
                mismatch[field] = replacement
                self.assert_invalid(lambda: context.close(mismatch), f"close.{field}")
                self.assertEqual(self.scenario["request"], context.active_identity)

        context.close(self.scenario["context"])
        context.close(self.scenario["context"])
        self.assertEqual("closing", context.state)
        self.assertIsNone(context.active_identity)
        self.assertEqual(1, context.isolated_resource_count)
        self.assertEqual(retained_before, context.retained_resource_capacity_cells)
        self.assertIsNone(context.committed_history)

        next_request = copy.deepcopy(self.scenario["request"])
        next_request["frame_id"] = "2"
        self.assert_invalid(lambda: self.submit(context, next_request), "context is closed")
        self.assert_invalid(lambda: context.reset("closed-reset", "0"), "context is closed")
        self.assert_invalid(
            lambda: context.execution_failed(self.scenario["request"]),
            "context is closed",
        )
        self.assert_invalid(
            lambda: context.timeout(self.scenario["request"]), "context is closed"
        )
        mismatch = copy.deepcopy(self.scenario["request"])
        mismatch["frame_id"] = "9"
        self.assert_invalid(lambda: context.complete(mismatch), "completion")
        self.assertEqual(1, context.isolated_resource_count)
        self.assertEqual("closing", context.state)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual(0, context.retained_resource_count)
        self.assertEqual("closed", context.state)
        self.assertIsNone(context.last_completed_frame_id)
        self.assert_invalid(
            lambda: context.complete(self.scenario["request"]),
            "no active request",
        )

    def test_close_pending_result_requires_consumption_and_never_commits(self):
        context = self.new_context()
        self.submit(context)
        context.complete(self.scenario["request"])
        context.close(self.scenario["context"])

        self.assertEqual("closing", context.state)
        self.assertEqual(1, context.isolated_resource_count)
        self.assert_invalid(
            lambda: context.complete(self.scenario["request"]),
            "awaits result consumption",
        )
        self.assertEqual(1, context.isolated_resource_count)

        context.result_consumed(self.scenario["request"], True)
        context.result_consumed(self.scenario["request"], True)
        self.assertEqual(0, context.retained_resource_count)
        self.assertIsNone(context.committed_history)
        self.assertIsNone(context.last_committed_frame_id)
        self.assertEqual("closed", context.state)

    def test_close_preserves_timed_out_isolated_work_until_explicit_completion(self):
        context = self.new_context()
        self.submit(context)
        context.timeout(self.scenario["request"])
        context.reset("timeout-reset-before-close", "0")
        current_identity = copy.deepcopy(self.scenario["context"])
        current_identity["history_generation"] = "1"
        self.assert_invalid(
            lambda: context.close(self.scenario["context"]),
            "close.history_generation",
        )
        context.close(current_identity)

        self.assertEqual("closing", context.state)
        self.assertEqual(1, context.isolated_resource_count)
        retained_before = context.retained_resource_capacity_cells
        context.close(current_identity)
        self.assertEqual(retained_before, context.retained_resource_capacity_cells)
        self.assertEqual(1, context.isolated_resource_count)

        self.assertIsNone(context.complete(self.scenario["request"]))
        self.assertEqual(0, context.retained_resource_count)

    def test_close_preserves_all_five_retained_states_until_matching_reclaim(self):
        states = (
            ("executing", False, False, False),
            ("executing_timed_out", False, True, False),
            ("execution_failed", False, False, True),
            ("pending_consumption", True, False, False),
            ("pending_consumption_timed_out", True, True, False),
        )
        for state, completed, timed_out, failed in states:
            with self.subTest(state=state):
                context = self.new_context()
                request = copy.deepcopy(self.scenario["request"])
                self.submit(context, request)
                capacity = context.retained_resource_capacity_cells
                if completed:
                    context.complete(request)
                if timed_out:
                    context.timeout(request)
                if failed:
                    context.execution_failed(request)
                self.assertEqual(state, context.state)

                context.close(self.scenario["context"])
                self.assertEqual("closing", context.state)
                self.assertEqual(1, context.isolated_resource_count)
                self.assertEqual(capacity, context.retained_resource_capacity_cells)
                self.assertIsNone(context.committed_history)

                if completed:
                    self.assert_invalid(
                        lambda: context.complete(request), "awaits result consumption"
                    )
                    context.result_consumed(request, True)
                else:
                    self.assert_invalid(
                        lambda: context.result_consumed(request, True),
                        "has not completed",
                    )
                    self.assertIsNone(context.complete(request))
                self.assertEqual("closed", context.state)
                self.assertEqual(0, context.retained_resource_count)
                self.assertEqual(0, context.retained_resource_capacity_cells)
                self.assertIsNone(context.committed_history)

    def test_four_failed_generations_hold_budget_and_late_events_do_not_pollute_new_history(self):
        context = self.new_context()
        failed_requests = []
        one_request_capacity = None
        for generation in range(lifecycle.MAX_RETAINED_RESOURCE_COUNT):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            if one_request_capacity is None:
                one_request_capacity = context.retained_resource_capacity_cells
            context.execution_failed(request)
            context.reset(f"failed-generation-{generation}", str(generation))
            failed_requests.append(request)

        self.assertEqual(
            lifecycle.MAX_RETAINED_RESOURCE_COUNT, context.isolated_resource_count
        )
        self.assertEqual(
            one_request_capacity * lifecycle.MAX_RETAINED_RESOURCE_COUNT,
            context.retained_resource_capacity_cells,
        )
        current = copy.deepcopy(self.scenario["request"])
        current["frame_id"] = str(lifecycle.MAX_RETAINED_RESOURCE_COUNT + 1)
        current["history_generation"] = str(lifecycle.MAX_RETAINED_RESOURCE_COUNT)
        self.assert_invalid(lambda: self.submit(context, current), "resource count budget")

        self.assertIsNone(context.complete(failed_requests[0]))
        current_history = [[9, 8, 7], [6, 5, 4], [3, 2, 1]]
        context.submit(current, current_history, self.scenario["motion_vectors"])
        context.complete(current)
        context.result_consumed(current, True)
        committed = context.committed_history
        self.assertEqual(current_history, committed)

        for request in failed_requests[1:]:
            context.execution_failed(request)
            context.execution_failed(request)
            self.assertEqual(committed, context.committed_history)
            self.assertIsNone(context.complete(request))
            self.assertEqual(committed, context.committed_history)
        self.assertEqual(0, context.retained_resource_count)
        self.assertEqual("ready", context.state)

    def test_close_and_completion_sixty_four_way_race_is_bounded_and_reclaimable(self):
        context = self.new_context()
        request = copy.deepcopy(self.scenario["request"])
        self.submit(context, request)
        barrier = threading.Barrier(64)
        outcomes = []
        errors = []

        def race(kind):
            try:
                barrier.wait(timeout=5)
                if kind == "close":
                    context.close(self.scenario["context"])
                    outcomes.append((kind, None))
                else:
                    outcomes.append((kind, context.complete(request)))
            except Exception as exc:
                errors.append((kind, exc))

        threads = [
            threading.Thread(target=race, args=("close" if index % 2 == 0 else "complete",))
            for index in range(64)
        ]
        self.assertTrue(all(not thread.daemon for thread in threads))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "non-daemon close/completion thread exceeded timeout")

        close_errors = [exc for kind, exc in errors if kind == "close"]
        completion_errors = [exc for kind, exc in errors if kind == "complete"]
        completion_outcomes = [value for kind, value in outcomes if kind == "complete"]
        self.assertEqual([], close_errors)
        self.assertEqual(1, len(completion_outcomes))
        self.assertEqual(31, len(completion_errors))
        self.assertTrue(
            all(
                "already awaits result consumption" in str(exc)
                or "active request has already completed" in str(exc)
                or "there is no active request" in str(exc)
                for exc in completion_errors
            )
        )
        self.assertIn(context.retained_resource_count, (0, 1))
        if context.retained_resource_count:
            context.result_consumed(request, True)
        self.assertEqual("closed", context.state)
        self.assertEqual(0, context.retained_resource_count)
        self.assertIsNone(context.committed_history)

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

    def test_reset_idempotency_window_is_bounded_and_expiry_cannot_isolate_work(self):
        context = self.new_context()
        for generation in range(lifecycle.MAX_RESET_RESULT_COUNT):
            self.assertEqual(
                str(generation + 1),
                context.reset(f"retained-reset-{generation}", str(generation)),
            )

        self.assertEqual(lifecycle.MAX_RESET_RESULT_COUNT, context.reset_result_count)
        self.assertEqual("1", context.reset("retained-reset-0", "0"))
        self.assert_invalid(
            lambda: context.reset(
                "retained-reset-0", str(lifecycle.MAX_RESET_RESULT_COUNT)
            ),
            "reset.request_id",
        )

        self.assertEqual(
            str(lifecycle.MAX_RESET_RESULT_COUNT + 1),
            context.reset(
                "evicting-reset", str(lifecycle.MAX_RESET_RESULT_COUNT)
            ),
        )
        self.assertEqual(lifecycle.MAX_RESET_RESULT_COUNT, context.reset_result_count)

        active = copy.deepcopy(self.scenario["request"])
        active["history_generation"] = str(lifecycle.MAX_RESET_RESULT_COUNT + 1)
        self.submit(context, active)
        active_before = context.active_identity
        generation_before = context.history_generation
        history_before = context.committed_history
        self.assert_invalid(
            lambda: context.reset("retained-reset-0", "0"),
            "reset.history_generation",
        )
        self.assertEqual(active_before, context.active_identity)
        self.assertEqual(0, context.isolated_resource_count)
        self.assertEqual(generation_before, context.history_generation)
        self.assertEqual(history_before, context.committed_history)
        self.assertEqual("executing", context.state)

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

    def test_all_eight_active_and_isolated_retained_states_hold_resources(self):
        states = (
            ("executing", False, False),
            ("executing_timed_out", False, True),
            ("pending_consumption", True, False),
            ("pending_consumption_timed_out", True, True),
        )
        identity_replacements = {
            "service_instance_id": "wrong-service",
            "session_id": "wrong-session",
            "context_id": "wrong-context",
            "frame_id": "2",
            "history_generation": "1",
            "model_manifest_id": "wrong-manifest",
        }

        for isolated in (False, True):
            for state, completed, timed_out in states:
                with self.subTest(location="isolated" if isolated else "active", state=state):
                    context = self.new_context()
                    request = copy.deepcopy(self.scenario["request"])
                    self.submit(context, request)
                    capacity = context.retained_resource_capacity_cells
                    if completed:
                        context.complete(request)
                    if timed_out:
                        context.timeout(request)
                    self.assertEqual(state, context.state)
                    if isolated:
                        context.reset(f"isolate-{state}", "0")
                        self.assertIsNone(context.active_identity)
                        self.assertEqual(1, context.isolated_resource_count)
                    else:
                        self.assertEqual(request, context.active_identity)
                        self.assertEqual(0, context.isolated_resource_count)
                    self.assertEqual(1, context.retained_resource_count)
                    self.assertEqual(capacity, context.retained_resource_capacity_cells)

                    reclaim = context.result_consumed if completed else context.complete
                    for field, replacement in identity_replacements.items():
                        wrong = copy.deepcopy(request)
                        wrong[field] = replacement
                        if completed:
                            self.assert_invalid(lambda wrong=wrong: reclaim(wrong, True), "result_consumed")
                        else:
                            self.assert_invalid(lambda wrong=wrong: reclaim(wrong), "completion")
                        self.assertEqual(1, context.retained_resource_count)
                        self.assertEqual(capacity, context.retained_resource_capacity_cells)

                    if completed:
                        context.result_consumed(request, True)
                    else:
                        context.complete(request)
                        if not timed_out and not isolated:
                            context.result_consumed(request, True)
                    self.assertEqual(0, context.retained_resource_count)
                    self.assertEqual(0, context.retained_resource_capacity_cells)

    def test_large_integer_values_do_not_inflate_logical_cell_capacity(self):
        context = self.new_context()
        huge = 1 << 100_000
        history = copy.deepcopy(self.scenario["history"])
        for row in history:
            for index in range(len(row)):
                row[index] = huge if index % 2 == 0 else -huge
        context.submit(
            self.scenario["request"], history, self.scenario["motion_vectors"]
        )
        logical_cells = sum(map(len, history)) + sum(
            map(len, self.scenario["expected_output"])
        )
        self.assertEqual(logical_cells, context.retained_resource_capacity_cells)
        output = context.complete(self.scenario["request"])
        self.assertTrue(any(abs(value) == huge for row in output for value in row if value is not None))
        self.assertEqual(logical_cells, context.retained_resource_capacity_cells)

    def test_active_plus_isolated_capacity_accepts_exact_boundary_and_rejects_excess(self):
        def payload(width, height):
            history = [[0 for _ in range(width)] for _ in range(height)]
            vectors = [[[0, 0] for _ in range(width)] for _ in range(height)]
            return history, vectors

        def isolated_context():
            context = self.new_context()
            first_history, first_vectors = payload(32, 63)
            context.submit(self.scenario["request"], first_history, first_vectors)
            context.timeout(self.scenario["request"])
            context.reset("boundary-reset", "0")
            self.assertEqual(4032, context.isolated_resource_capacity_cells)
            return context

        exact = isolated_context()
        second = copy.deepcopy(self.scenario["request"])
        second["frame_id"] = "2"
        second["history_generation"] = "1"
        exact_history, exact_vectors = payload(40, 52)
        exact.submit(second, exact_history, exact_vectors)
        self.assertEqual(1, exact.isolated_resource_count)
        self.assertEqual(2, exact.retained_resource_count)
        self.assertEqual(
            lifecycle.MAX_RETAINED_CAPACITY_CELLS,
            exact.retained_resource_capacity_cells,
        )

        excess = isolated_context()
        excess_history, excess_vectors = payload(40, 53)
        before_capacity = excess.retained_resource_capacity_cells
        self.assert_invalid(
            lambda: excess.submit(second, excess_history, excess_vectors),
            "resource capacity budget",
        )
        self.assertIsNone(excess.active_identity)
        self.assertEqual(1, excess.retained_resource_count)
        self.assertEqual(before_capacity, excess.retained_resource_capacity_cells)

    def test_permanently_in_flight_requests_keep_deterministic_backpressure(self):
        context = self.new_context()
        for generation in range(lifecycle.MAX_RETAINED_RESOURCE_COUNT):
            request = copy.deepcopy(self.scenario["request"])
            request["frame_id"] = str(generation + 1)
            request["history_generation"] = str(generation)
            self.submit(context, request)
            context.timeout(request)
            context.reset(f"permanent-{generation}", str(generation))

        rejected = copy.deepcopy(self.scenario["request"])
        rejected["frame_id"] = str(lifecycle.MAX_RETAINED_RESOURCE_COUNT + 1)
        rejected["history_generation"] = context.history_generation
        retained_capacity = context.retained_resource_capacity_cells
        for attempt in range(16):
            with self.subTest(attempt=attempt):
                self.assert_invalid(
                    lambda: self.submit(context, rejected), "resource count budget"
                )
                self.assertEqual(
                    lifecycle.MAX_RETAINED_RESOURCE_COUNT,
                    context.retained_resource_count,
                )
                self.assertEqual(retained_capacity, context.retained_resource_capacity_cells)
                self.assertIsNone(context.active_identity)

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

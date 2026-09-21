#!/usr/bin/env python3
"""Run the repository test matrix in four explicitly selected virtual environments."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import tempfile
from typing import Any, Callable, Mapping, Optional, Sequence
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
SCHEMA_VERSION = "multi-venv-verification-v1"
SUITE_ORDER = ("baseline", "reference", "fsr-extract", "qairt")
MAX_OUTPUT_TAIL_BYTES = 32 * 1024
DEFAULT_TIMEOUT_SECONDS = 1200


@dataclass(frozen=True)
class SuiteSpec:
    suite_id: str
    discovery_start: Optional[str] = None
    modules: tuple[str, ...] = ()

    def worker_arguments(self) -> list[str]:
        if self.discovery_start is not None:
            return ["discover", "-s", self.discovery_start, "-p", "test_*.py", "-v"]
        return [*self.modules, "-v"]


SUITES = (
    SuiteSpec("baseline", discovery_start="tests"),
    SuiteSpec("reference", discovery_start="tests/reference"),
    SuiteSpec("fsr-extract", discovery_start="tests/fsr"),
    SuiteSpec(
        "qairt",
        modules=(
            "tests.qairt.test_environment",
            "tests.qairt.test_probe",
            "tests.abi.test_inspector",
            "tests.abi.test_inventory",
            "tests.qairt.test_small_graph_pipeline",
        ),
    ),
)
SUITES_BY_ID = {suite.suite_id: suite for suite in SUITES}


class VerificationError(Exception):
    """A deterministic coordinator or worker contract failure."""


class EnvironmentUnavailable(VerificationError):
    """The selected interpreter cannot run its suite."""


@dataclass(frozen=True)
class ProcessCapture:
    returncode: Optional[int]
    timed_out: bool
    stdout: dict[str, Any]
    stderr: dict[str, Any]
    launch_error: Optional[str] = None


def _stream_summary(stream: Any) -> dict[str, Any]:
    stream.flush()
    snapshot_byte_count = os.fstat(stream.fileno()).st_size
    stream.seek(0)
    digest = hashlib.sha256()
    byte_count = 0
    tail_bytes = b""
    remaining = snapshot_byte_count
    while remaining:
        block = stream.read(min(1024 * 1024, remaining))
        if not block:
            break
        digest.update(block)
        byte_count += len(block)
        remaining -= len(block)
        tail_bytes = (tail_bytes + block)[-MAX_OUTPUT_TAIL_BYTES:]
    final_byte_count = os.fstat(stream.fileno()).st_size
    return {
        "byte_count": byte_count,
        "snapshot_byte_count": snapshot_byte_count,
        "snapshot_complete": byte_count == snapshot_byte_count,
        "sha256": digest.hexdigest(),
        "tail": tail_bytes.decode("utf-8", "replace"),
        "truncated": byte_count > len(tail_bytes),
        "late_output_excluded_byte_count": max(0, final_byte_count - snapshot_byte_count),
        "capture_semantics": (
            "fixed-size snapshot; bytes appended after snapshot selection are excluded"
        ),
    }


def _empty_stream_summary() -> dict[str, Any]:
    return {
        "byte_count": 0,
        "snapshot_byte_count": 0,
        "snapshot_complete": True,
        "sha256": hashlib.sha256(b"").hexdigest(),
        "tail": "",
        "truncated": False,
        "late_output_excluded_byte_count": 0,
        "capture_semantics": (
            "fixed-size snapshot; bytes appended after snapshot selection are excluded"
        ),
    }


def _execute(argv: Sequence[str], timeout: int) -> ProcessCapture:
    """Run one direct child with disk-backed output; timeout claims apply only to it."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=REPO_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                check=False,
                timeout=timeout,
            )
            returncode: Optional[int] = completed.returncode
            timed_out = False
            launch_error = None
        except subprocess.TimeoutExpired:
            returncode = None
            timed_out = True
            launch_error = None
        except OSError as exc:
            returncode = None
            timed_out = False
            launch_error = f"{type(exc).__name__}: {exc}"
        return ProcessCapture(
            returncode,
            timed_out,
            _stream_summary(stdout),
            _stream_summary(stderr),
            launch_error,
        )


PROBE_CODE = (
    "import json,platform,sys,sysconfig;"
    "print(json.dumps({"
    "'executable':sys.executable,'version':platform.python_version(),"
    "'implementation':platform.python_implementation(),"
    "'machine':platform.machine(),'sysconfig_platform':sysconfig.get_platform(),"
    "'prefix':sys.prefix,'base_prefix':sys.base_prefix},sort_keys=True))"
)


def _normal_path(value: object) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def _probe_environment(
    selected: Path,
    timeout: int = 30,
    execute: Callable[[Sequence[str], int], ProcessCapture] = _execute,
) -> dict[str, str]:
    if not selected.exists():
        raise EnvironmentUnavailable(f"Python executable does not exist: {selected}")
    if not selected.is_file():
        raise EnvironmentUnavailable(f"Python executable is not a file: {selected}")
    resolved = selected.resolve()
    capture = execute([str(resolved), "-I", "-c", PROBE_CODE], timeout)
    if capture.timed_out:
        raise EnvironmentUnavailable(
            f"Python environment probe timed out after {timeout} seconds: {resolved}"
        )
    if capture.launch_error is not None:
        raise EnvironmentUnavailable(
            f"could not start Python environment probe for {resolved}: {capture.launch_error}"
        )
    if capture.returncode != 0:
        diagnostic = capture.stderr["tail"] or capture.stdout["tail"] or "no output"
        raise EnvironmentUnavailable(
            f"Python environment probe failed for {resolved} with exit "
            f"{capture.returncode}: {diagnostic.strip()}"
        )
    try:
        payload = json.loads(capture.stdout["tail"])
        required = {
            "executable",
            "version",
            "implementation",
            "machine",
            "sysconfig_platform",
            "prefix",
            "base_prefix",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise TypeError("unexpected environment fields")
        environment = {name: str(payload[name]) for name in required}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnvironmentUnavailable(
            f"Python environment probe returned invalid data for {resolved}"
        ) from exc
    if _normal_path(environment["executable"]) != _normal_path(resolved):
        raise EnvironmentUnavailable(
            f"Python probe executable mismatch: selected {resolved}, "
            f"reported {environment['executable']}"
        )
    if _normal_path(environment["prefix"]) == _normal_path(environment["base_prefix"]):
        raise EnvironmentUnavailable(
            f"selected Python is not a virtual environment: {resolved}"
        )
    environment["requested"] = str(selected)
    environment["resolved"] = str(resolved)
    return environment


def _load_suite(spec: SuiteSpec) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    if spec.discovery_start is not None:
        return loader.discover(
            str(REPO_ROOT / spec.discovery_start),
            pattern="test_*.py",
            top_level_dir=str(REPO_ROOT),
        )
    return loader.loadTestsFromNames(list(spec.modules))


def _parent_test(test: object) -> object:
    """Return the owning TestCase for a recorded subtest event."""
    return getattr(test, "test_case", test)


class _AccountingTextTestResult(unittest.TextTestResult):
    """Retain the identities for tests which actually reached startTest."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.started_test_ids: set[int] = set()

    def startTest(self, test: unittest.case.TestCase) -> None:
        self.started_test_ids.add(id(test))
        super().startTest(test)


def _result_counts(result: unittest.TestResult) -> tuple[dict[str, int], dict[str, Any]]:
    event_lists = {
        "failures": result.failures,
        "errors": result.errors,
        "skipped": getattr(result, "skipped", ()),
        "expected_failures": getattr(result, "expectedFailures", ()),
        "unexpected_successes": getattr(result, "unexpectedSuccesses", ()),
    }
    parent_events: dict[str, set[int]] = {}
    subtest_events: dict[str, int] = {}
    synthetic_events: dict[str, int] = {}
    started_test_ids = getattr(result, "started_test_ids", set())
    for name, events in event_lists.items():
        parents: set[int] = set()
        subtests = 0
        synthetic = 0
        for event in events:
            test = event[0] if isinstance(event, tuple) else event
            parent = _parent_test(test)
            parent_id = id(parent)
            if parent_id in started_test_ids:
                parents.add(parent_id)
            else:
                synthetic += 1
            if parent is not test and parent_id in started_test_ids:
                subtests += 1
        parent_events[name] = parents
        subtest_events[name] = subtests
        synthetic_events[name] = synthetic

    # A single parent test can record several subtest events, including mixed
    # failure/skip events. Classify it once, using the most severe outcome.
    classified: set[int] = set()
    parent_counts: dict[str, int] = {}
    for name in (
        "errors",
        "failures",
        "unexpected_successes",
        "skipped",
        "expected_failures",
    ):
        unique = parent_events[name] - classified
        parent_counts[name] = len(unique)
        classified.update(unique)
    passed = result.testsRun - len(classified)
    if passed < 0:
        raise VerificationError("recorded parent test outcomes exceed testsRun")
    counts = {
        "total": result.testsRun,
        "passed": passed,
        "failures": parent_counts["failures"],
        "errors": parent_counts["errors"],
        "skipped": parent_counts["skipped"],
        "expected_failures": parent_counts["expected_failures"],
        "unexpected_successes": parent_counts["unexpected_successes"],
    }
    events = {
        "recorded": {name: len(values) for name, values in event_lists.items()},
        "subtests": subtest_events,
        "fixture_or_synthetic": synthetic_events,
        "semantics": (
            "counts classify only TestCase instances observed by startTest; events retain "
            "recorded subtest and fixture/synthetic-holder multiplicity"
        ),
    }
    return counts, events


def _run_loaded_suite(
    suite: unittest.TestSuite, stream: Any
) -> tuple[dict[str, int], dict[str, Any], bool]:
    result = unittest.TextTestRunner(
        stream=stream, verbosity=2, resultclass=_AccountingTextTestResult
    ).run(suite)
    counts, events = _result_counts(result)
    return counts, events, result.wasSuccessful()


def _worker_environment() -> dict[str, str]:
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "sysconfig_platform": sysconfig.get_platform(),
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
    }


def _worker_main(suite_id: str, result_path: Path) -> int:
    if suite_id not in SUITES_BY_ID:
        print(f"worker error: unknown suite {suite_id!r}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(REPO_ROOT))
    spec = SUITES_BY_ID[suite_id]
    suite = _load_suite(spec)
    counts, events, successful = _run_loaded_suite(suite, sys.stderr)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": suite_id,
        "environment": _worker_environment(),
        "counts": counts,
        "events": events,
        "successful": successful,
    }
    try:
        with result_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as exc:
        print(f"worker error: could not publish result: {exc}", file=sys.stderr)
        return 2
    return 0 if successful else 1


COUNT_FIELDS = (
    "total",
    "passed",
    "failures",
    "errors",
    "skipped",
    "expected_failures",
    "unexpected_successes",
)
EVENT_FIELDS = (
    "failures",
    "errors",
    "skipped",
    "expected_failures",
    "unexpected_successes",
)


def _validate_worker_payload(payload: object, spec: SuiteSpec) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VerificationError("worker result must be an object")
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("suite_id") != spec.suite_id:
        raise VerificationError("worker result identity mismatch")
    if type(payload.get("successful")) is not bool:
        raise VerificationError("worker successful flag must be boolean")
    environment = payload.get("environment")
    if not isinstance(environment, dict):
        raise VerificationError("worker environment must be an object")
    counts = payload.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(COUNT_FIELDS):
        raise VerificationError("worker counts have invalid fields")
    if any(type(counts[name]) is not int or counts[name] < 0 for name in COUNT_FIELDS):
        raise VerificationError("worker counts must be non-negative integers")
    classified = sum(counts[name] for name in COUNT_FIELDS if name != "total")
    if classified != counts["total"]:
        raise VerificationError("worker test counts do not add up to total")
    events = payload.get("events")
    if not isinstance(events, dict) or set(events) != {
        "recorded",
        "subtests",
        "fixture_or_synthetic",
        "semantics",
    }:
        raise VerificationError("worker event counts have invalid fields")
    if not isinstance(events["semantics"], str) or not events["semantics"]:
        raise VerificationError("worker event semantics must be a non-empty string")
    for group in ("recorded", "subtests", "fixture_or_synthetic"):
        values = events[group]
        if not isinstance(values, dict) or set(values) != set(EVENT_FIELDS):
            raise VerificationError(f"worker {group} event counts have invalid fields")
        if any(type(values[name]) is not int or values[name] < 0 for name in EVENT_FIELDS):
            raise VerificationError(f"worker {group} event counts must be non-negative integers")
        if group != "recorded" and any(
            values[name] > events["recorded"][name] for name in EVENT_FIELDS
        ):
            raise VerificationError(f"worker {group} event count exceeds recorded events")
    expected_success = not any(
        events["recorded"][name]
        for name in ("failures", "errors", "unexpected_successes")
    )
    if payload["successful"] != expected_success:
        raise VerificationError("worker successful flag disagrees with test counts")
    return payload


def _run_suite(
    spec: SuiteSpec,
    environment: Mapping[str, str],
    timeout: int,
    execute: Callable[[Sequence[str], int], ProcessCapture] = _execute,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"verify-{spec.suite_id}-") as directory:
        result_path = Path(directory) / "worker-result.json"
        argv = [
            environment["resolved"],
            "-I",
            str(SCRIPT),
            "--worker-suite",
            spec.suite_id,
            "--worker-result",
            str(result_path),
        ]
        capture = execute(argv, timeout)
        base: dict[str, Any] = {
            "id": spec.suite_id,
            "unittest_argv": spec.worker_arguments(),
            "worker_argv": argv,
            "environment": dict(environment),
            "child_exit_code": capture.returncode,
            "timed_out": capture.timed_out,
            "stdout": capture.stdout,
            "stderr": capture.stderr,
            "counts": None,
            "events": None,
        }
        if capture.timed_out:
            return {
                **base,
                "status": "failed",
                "reason": (
                    f"direct worker timed out after {timeout} seconds and was terminated; "
                    "descendant quiescence was not established"
                ),
            }
        if capture.launch_error is not None:
            return {**base, "status": "failed", "reason": capture.launch_error}
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload = _validate_worker_payload(payload, spec)
        except (OSError, ValueError, json.JSONDecodeError, VerificationError) as exc:
            return {
                **base,
                "status": "failed",
                "reason": f"worker result is missing or invalid: {exc}",
            }
        base["counts"] = payload["counts"]
        base["events"] = payload["events"]
        worker_environment = payload["environment"]
        if _normal_path(worker_environment.get("executable", "")) != _normal_path(
            environment["resolved"]
        ):
            return {
                **base,
                "status": "failed",
                "reason": "worker executed under a different interpreter than the environment probe",
            }
        expected_exit = 0 if payload["successful"] else 1
        if capture.returncode != expected_exit:
            return {
                **base,
                "status": "failed",
                "reason": (
                    f"worker exit {capture.returncode} disagrees with result "
                    f"(expected {expected_exit})"
                ),
            }
        return {
            **base,
            "status": "completed" if payload["successful"] else "failed",
            "reason": None if payload["successful"] else "one or more tests failed",
        }


def _not_run_record(spec: SuiteSpec, selected: Path, reason: str) -> dict[str, Any]:
    return {
        "id": spec.suite_id,
        "unittest_argv": spec.worker_arguments(),
        "worker_argv": None,
        "environment": {"requested": str(selected)},
        "status": "not_run",
        "reason": reason,
        "child_exit_code": None,
        "timed_out": False,
        "counts": None,
        "events": None,
        "stdout": _empty_stream_summary(),
        "stderr": _empty_stream_summary(),
    }


def _summary(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], int]:
    suite_counts = {"completed": 0, "failed": 0, "not_run": 0}
    test_counts = {name: 0 for name in COUNT_FIELDS}
    for record in records:
        suite_counts[str(record["status"])] += 1
        counts = record.get("counts")
        if counts is not None:
            for name in COUNT_FIELDS:
                test_counts[name] += counts[name]
    if suite_counts["not_run"]:
        exit_code = 2
    elif suite_counts["failed"]:
        exit_code = 1
    else:
        exit_code = 0
    return {"suites": suite_counts, "tests": test_counts}, exit_code


def run_verification(
    interpreters: Mapping[str, Path],
    timeout: int,
    probe: Callable[[Path], dict[str, str]] = _probe_environment,
    runner: Callable[[SuiteSpec, Mapping[str, str], int], dict[str, Any]] = _run_suite,
) -> tuple[dict[str, Any], int]:
    records: list[dict[str, Any]] = []
    used_executables: set[str] = set()
    used_prefixes: set[str] = set()
    for spec in SUITES:
        selected = interpreters[spec.suite_id]
        try:
            environment = probe(selected)
            executable_key = _normal_path(environment["resolved"])
            prefix_key = _normal_path(environment["prefix"])
            if executable_key in used_executables or prefix_key in used_prefixes:
                raise EnvironmentUnavailable(
                    "selected virtual environment duplicates an earlier suite: "
                    f"{environment['resolved']}"
                )
            used_executables.add(executable_key)
            used_prefixes.add(prefix_key)
            records.append(runner(spec, environment, timeout))
        except EnvironmentUnavailable as exc:
            records.append(_not_run_record(spec, selected, str(exc)))
        except Exception as exc:
            records.append(
                {
                    **_not_run_record(spec, selected, ""),
                    "status": "failed",
                    "reason": f"coordinator error: {type(exc).__name__}: {exc}",
                }
            )
    summary, exit_code = _summary(records)
    report = {
        "schema_version": SCHEMA_VERSION,
        "suite_order": list(SUITE_ORDER),
        "suites": records,
        "summary": summary,
        "total_exit_code": exit_code,
        "scope": "Windows host test matrix; not device, HTP, complete FSR4, or game validation",
    }
    return report, exit_code


def _validate_output(output: Path) -> Path:
    selected = Path(os.path.abspath(os.fspath(output)))
    if os.path.lexists(selected):
        raise VerificationError(f"output already exists; refusing to overwrite: {selected}")
    if not selected.parent.exists():
        raise VerificationError(f"output parent does not exist: {selected.parent}")
    if not selected.parent.is_dir():
        raise VerificationError(f"output parent is not a directory: {selected.parent}")
    return selected


def _publish_report(output: Path, report: Mapping[str, Any]) -> None:
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except OSError as exc:
        raise VerificationError(f"could not publish report {output}: {exc}") from exc


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-python", type=Path)
    parser.add_argument("--reference-python", type=Path)
    parser.add_argument("--fsr-python", type=Path)
    parser.add_argument("--qairt-python", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=_positive_integer, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--worker-suite", choices=SUITE_ORDER, help=argparse.SUPPRESS)
    parser.add_argument("--worker-result", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    if args.worker_suite is not None or args.worker_result is not None:
        if args.worker_suite is None or args.worker_result is None:
            print("worker error: --worker-suite and --worker-result are both required", file=sys.stderr)
            return 2
        return _worker_main(args.worker_suite, args.worker_result)
    required = {
        "baseline": args.baseline_python,
        "reference": args.reference_python,
        "fsr-extract": args.fsr_python,
        "qairt": args.qairt_python,
    }
    missing = [name for name, value in required.items() if value is None]
    if args.output is None:
        missing.append("output")
    if missing:
        print(f"error: missing required coordinator arguments: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        output = _validate_output(args.output)
        report, exit_code = run_verification(required, args.timeout_seconds)
        _publish_report(output, report)
    except VerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    suites = report["summary"]["suites"]
    tests = report["summary"]["tests"]
    print(
        f"completed={suites['completed']} failed={suites['failed']} "
        f"not_run={suites['not_run']}; passed={tests['passed']} "
        f"failures={tests['failures']} errors={tests['errors']} "
        f"skipped={tests['skipped']}; report={output}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

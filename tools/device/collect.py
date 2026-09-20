#!/usr/bin/env python3
"""Bounded, read-only Linux inventory collector for the M0 draft-0 profile."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterator, Sequence


SCHEMA_VERSION = "draft-0"
TOOL_NAME = "tools/device/collect.py"
BASELINE_COMMIT = "91ae78e2042a4c8971b39a8abd381a0705ab7085"
COMMAND_TIMEOUT_SECONDS = 5.0
FILE_TIMEOUT_SECONDS = 2.0
MAX_FILE_BYTES = 1024 * 1024
MAX_COMMAND_BYTES = 1024 * 1024
MAX_DIAGNOSTIC_CHARS = 4096
MAX_REMOTE_PROCS = 128
MAX_DEVICE_NODES = 256


class InputError(Exception):
    """Invalid CLI input or unsafe fixture data (exit 2)."""


class CollectionError(Exception):
    """Fatal I/O or internal failure (exit 3)."""


class ReadTimedOut(Exception):
    pass


@dataclass(frozen=True)
class BoundedBytes:
    data: bytes
    truncated: bool


@dataclass(frozen=True)
class RunnerResult:
    argv: list[str]
    available: bool
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def bounded(data: bytes, limit: int) -> BoundedBytes:
    return BoundedBytes(data[:limit], len(data) > limit)


@contextlib.contextmanager
def read_deadline(seconds: float) -> Iterator[None]:
    """Bound a potentially blocking Linux file operation on the main thread."""
    if os.name != "posix" or threading.current_thread() is not threading.main_thread():
        yield
        return

    def alarm_handler(_signum: int, _frame: Any) -> None:
        raise ReadTimedOut

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, alarm_handler)
    old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_handler)


def read_bounded_file(path: Path, limit: int = MAX_FILE_BYTES) -> BoundedBytes:
    with read_deadline(FILE_TIMEOUT_SECONDS):
        with path.open("rb", buffering=0) as stream:
            return bounded(stream.read(limit + 1), limit)


def list_directory(path: Path, limit: int, name_prefix: str | None = None) -> tuple[list[Path], bool]:
    entries: list[Path] = []
    with read_deadline(FILE_TIMEOUT_SECONDS):
        with os.scandir(path) as iterator:
            for entry in iterator:
                if name_prefix is not None and not entry.name.startswith(name_prefix):
                    continue
                if len(entries) >= limit:
                    return entries, True
                entries.append(Path(entry.path))
    return sorted(entries, key=lambda item: item.name), False


class ProductionRunner:
    """The only code path that starts external programs."""

    @staticmethod
    def run(argv: Sequence[str], timeout: float = COMMAND_TIMEOUT_SECONDS) -> RunnerResult:
        args = list(argv)
        if not args or shutil.which(args[0]) is None:
            return RunnerResult(args, False, None, b"", b"", False, False, False)
        process_options: dict[str, Any] = {}
        if os.name == "posix":
            process_options["start_new_session"] = True
        elif os.name == "nt":
            process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed argv, deliberately no shell
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                **process_options,
            )
        except FileNotFoundError as exc:
            return RunnerResult(args, False, None, b"", str(exc).encode(), False, False, False)
        except PermissionError as exc:
            return RunnerResult(args, True, 126, b"", str(exc).encode(), False, False, False)
        except OSError as exc:
            return RunnerResult(args, True, None, b"", str(exc).encode(), False, False, False)

        output: dict[str, BoundedBytes] = {}

        def drain(name: str, stream: Any) -> None:
            kept = bytearray()
            saw_extra = False
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                remaining = MAX_COMMAND_BYTES - len(kept)
                if remaining > 0:
                    kept.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    saw_extra = True
            output[name] = BoundedBytes(bytes(kept), saw_extra)

        assert process.stdout is not None and process.stderr is not None
        threads = [
            threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            exit_code = process.wait()

        drain_deadline = time.monotonic() + 1.0
        for thread in threads:
            thread.join(timeout=max(0.0, drain_deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            # A descendant can retain inherited pipe handles after the direct
            # child exits. Treat that as a timeout and terminate the process
            # group; never close a stream while its reader owns the I/O lock.
            timed_out = True
            _terminate_process_tree(process)
            drain_deadline = time.monotonic() + 1.0
            for thread in threads:
                thread.join(timeout=max(0.0, drain_deadline - time.monotonic()))
        for thread, stream in zip(threads, (process.stdout, process.stderr)):
            if not thread.is_alive():
                stream.close()
        stdout = output.get("stdout", BoundedBytes(b"", False))
        stderr = output.get("stderr", BoundedBytes(b"", False))
        stdout_truncated = stdout.truncated or threads[0].is_alive()
        stderr_truncated = stderr.truncated or threads[1].is_alive()
        return RunnerResult(
            args, True, exit_code, stdout.data, stderr.data, timed_out,
            stdout_truncated, stderr_truncated,
        )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Best-effort bounded termination for the isolated command group."""
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
        # The group leader may already have exited while a descendant still
        # owns inherited pipes, so address the group independently of poll().
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
    elif os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP plus taskkill /T is the standard-library
        # compatible way to include descendants on supported Windows hosts.
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
                shell=False,
            )
    if process.poll() is None:
        with contextlib.suppress(OSError):
            process.kill()


def safe_fixture_reference(value: str, label: str) -> Path:
    if not value or "\\" in value:
        raise InputError(f"{label} must be a non-empty forward-slash relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise InputError(f"unsafe {label}: {value!r}")
    return pure


class FixtureRunner:
    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir.resolve(strict=True)
        commands_path = (self.case_dir / "commands.json").resolve(strict=True)
        if commands_path.parent != self.case_dir:
            raise InputError("fixture commands.json escapes case directory")
        try:
            records = json.loads(read_bounded_file(commands_path).data.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ReadTimedOut) as exc:
            raise InputError(f"cannot read fixture commands.json: {exc}") from exc
        if not isinstance(records, list):
            raise InputError("fixture commands.json must be an array")
        self.records: dict[tuple[str, ...], dict[str, Any]] = {}
        required = {"argv", "available", "exit_code", "stdout_file", "stderr_file", "delay_ms"}
        for index, record in enumerate(records):
            if not isinstance(record, dict) or set(record) != required:
                raise InputError(f"fixture command {index} has invalid fields")
            argv = record["argv"]
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                raise InputError(f"fixture command {index} has invalid argv")
            if type(record["available"]) is not bool:
                raise InputError(f"fixture command {index} has invalid available")
            if record["exit_code"] is not None and type(record["exit_code"]) is not int:
                raise InputError(f"fixture command {index} has invalid exit_code")
            if type(record["delay_ms"]) is not int or record["delay_ms"] < 0:
                raise InputError(f"fixture command {index} has invalid delay_ms")
            for field in ("stdout_file", "stderr_file"):
                if record[field] is not None:
                    if not isinstance(record[field], str):
                        raise InputError(f"fixture command {index} has invalid {field}")
                    safe_fixture_reference(record[field], field)
            key = tuple(argv)
            if key in self.records:
                raise InputError(f"duplicate fixture argv: {argv!r}")
            self.records[key] = record

    def _read_output(self, reference: str | None) -> BoundedBytes:
        if reference is None:
            return BoundedBytes(b"", False)
        relative = safe_fixture_reference(reference, "command output path")
        path = (self.case_dir / relative).resolve()
        if self.case_dir not in path.parents:
            raise InputError(f"fixture reference escapes case directory: {reference!r}")
        try:
            return read_bounded_file(path, MAX_COMMAND_BYTES)
        except (OSError, ReadTimedOut) as exc:
            raise InputError(f"cannot read fixture command output {reference!r}: {exc}") from exc

    def run(self, argv: Sequence[str], timeout: float = COMMAND_TIMEOUT_SECONDS) -> RunnerResult:
        args = list(argv)
        record = self.records.get(tuple(args))
        if record is None or not record["available"]:
            return RunnerResult(args, False, None, b"", b"", False, False, False)
        if record["delay_ms"] > int(timeout * 1000):
            stdout = self._read_output(record["stdout_file"])
            stderr = self._read_output(record["stderr_file"])
            return RunnerResult(args, True, None, stdout.data, stderr.data, True,
                                stdout.truncated, stderr.truncated)
        stdout = self._read_output(record["stdout_file"])
        stderr = self._read_output(record["stderr_file"])
        return RunnerResult(
            args, True, record["exit_code"], stdout.data, stderr.data, False,
            stdout.truncated, stderr.truncated,
        )


class Collector:
    def __init__(self, output: Path, fixture_root: Path | None, argv: list[str]) -> None:
        self.output = output
        self.evidence_dir = output / "evidence"
        self.fixture_root = fixture_root.resolve() if fixture_root else None
        self.fixture_system_root: Path | None = None
        if self.fixture_root:
            candidate_root = (self.fixture_root / "root").resolve(strict=True)
            if self.fixture_root not in candidate_root.parents:
                raise InputError("fixture root/ escapes case directory")
            if not candidate_root.is_dir():
                raise InputError("fixture root/ must be a directory")
            self.fixture_system_root = candidate_root
        self.runner: ProductionRunner | FixtureRunner = (
            FixtureRunner(self.fixture_root) if self.fixture_root else ProductionRunner()
        )
        self.argv = argv
        self.evidence: list[dict[str, Any]] = []
        self.artifact_paths: list[Path] = []
        self.started_at = utc_now()
        self.profile_id = f"device-{uuid.uuid4().hex}"
        self._evidence_counter = 0

    def system_path(self, linux_path: str) -> Path:
        path = PurePosixPath(linux_path)
        if not path.is_absolute():
            raise CollectionError(f"internal path is not absolute: {linux_path}")
        if self.fixture_root:
            relative = Path(*path.parts[1:])
            assert self.fixture_system_root is not None
            mapped = (self.fixture_system_root / relative).resolve()
            root = self.fixture_system_root
            if mapped != root and root not in mapped.parents:
                raise InputError(f"fixture system path escapes root: {linux_path}")
            return mapped
        return Path(linux_path)

    def add_evidence(self, item_id: str, data: bytes, truncated: bool, suffix: str) -> str:
        self._evidence_counter += 1
        safe_item = "".join(c if c.isalnum() or c in "._-" else "-" for c in item_id)
        evidence_id = f"ev-{self._evidence_counter:04d}-{safe_item}"[:128]
        filename = f"{self._evidence_counter:04d}-{safe_item}{suffix}"
        path = self.evidence_dir / filename
        path.write_bytes(data)
        self.artifact_paths.append(path)
        relative = path.relative_to(self.output).as_posix()
        self.evidence.append({
            "evidence_id": evidence_id,
            "collection_item_id": safe_item[:128],
            "path": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_count": len(data),
            "truncated": truncated,
            "visibility": "private",
        })
        return evidence_id

    @staticmethod
    def source(kind: str, locator: str, evidence_ids: list[str]) -> dict[str, Any]:
        return {"kind": kind, "locator": locator, "evidence_ids": evidence_ids}

    @staticmethod
    def success(value: Any, source: dict[str, Any], observed_at: str) -> dict[str, Any]:
        return {"value": value, "source": source, "observed_at": observed_at,
                "status": "success", "failure": None}

    @staticmethod
    def failure(status: str, source: dict[str, Any], message: str,
                exit_code: int | None = None, stderr: str | None = None,
                stderr_truncated: bool = False) -> dict[str, Any]:
        return {
            "value": None,
            "source": source,
            "observed_at": utc_now(),
            "status": status,
            "failure": {
                "category": status,
                "message": message[:1024] or status,
                "exit_code": exit_code,
                "stderr": stderr[:MAX_DIAGNOSTIC_CHARS] if stderr else None,
                "stderr_truncated": stderr_truncated or bool(stderr and len(stderr) > MAX_DIAGNOSTIC_CHARS),
            },
        }

    def read_observation(self, item_id: str, linux_path: str, parser: Any = None) -> dict[str, Any]:
        observed_at = utc_now()
        source = self.source("fixture" if self.fixture_root else "file", linux_path, [])
        try:
            result = read_bounded_file(self.system_path(linux_path))
        except FileNotFoundError:
            return self.failure("missing", source, f"file not found: {linux_path}")
        except PermissionError as exc:
            return self.failure("permission_denied", source, str(exc))
        except ReadTimedOut:
            return self.failure("timeout", source, f"file read timed out: {linux_path}")
        except OSError as exc:
            return self.failure("command_failed", source, f"file read failed: {exc}")
        evidence_id = self.add_evidence(item_id, result.data, result.truncated, ".bin")
        source["evidence_ids"] = [evidence_id]
        if not result.data:
            return self.failure("command_failed", source, f"file is empty: {linux_path}")
        try:
            value = parser(result.data) if parser else result.data.decode("utf-8", "replace").rstrip("\x00\r\n")
        except (ValueError, UnicodeError) as exc:
            return self.failure("command_failed", source, f"parse failed: {exc}")
        return self.success(value, source, observed_at)

    def command_observation(self, item_id: str, argv: Sequence[str], parser: Any = None) -> dict[str, Any]:
        observed_at = utc_now()
        locator = json.dumps(list(argv), separators=(",", ":"))
        source = self.source("fixture" if self.fixture_root else "command", locator, [])
        result = self.runner.run(argv)
        if result.available:
            source["evidence_ids"].append(
                self.add_evidence(f"{item_id}-stdout", result.stdout, result.stdout_truncated, ".stdout")
            )
        if result.stderr:
            source["evidence_ids"].append(
                self.add_evidence(f"{item_id}-stderr", result.stderr, result.stderr_truncated, ".stderr")
            )
        stderr = result.stderr.decode("utf-8", "replace")
        if not result.available:
            return self.failure("unavailable", source, f"command unavailable: {argv[0]}", stderr=stderr)
        if result.timed_out:
            return self.failure("timeout", source, f"command timed out after {COMMAND_TIMEOUT_SECONDS:g}s",
                                result.exit_code, stderr, result.stderr_truncated)
        if result.exit_code != 0:
            if result.exit_code == 126 or "permission denied" in stderr.lower():
                return self.failure("permission_denied", source, "command execution was denied",
                                    result.exit_code, stderr, result.stderr_truncated)
            return self.failure("command_failed", source, f"command exited with {result.exit_code}",
                                result.exit_code, stderr, result.stderr_truncated)
        if not result.stdout:
            return self.failure("command_failed", source, "command produced empty stdout",
                                result.exit_code, stderr, result.stderr_truncated)
        try:
            value = parser(result.stdout) if parser else result.stdout.decode("utf-8", "replace").strip()
        except (ValueError, UnicodeError) as exc:
            return self.failure("command_failed", source, f"parse failed: {exc}", result.exit_code,
                                stderr, result.stderr_truncated)
        return self.success(value, source, observed_at)

    def metadata_observation(self, item_id: str, locator: str, value: Any) -> dict[str, Any]:
        observed_at = utc_now()
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        evidence_id = self.add_evidence(item_id, raw, False, ".json")
        return self.success(value, self.source("metadata", locator, [evidence_id]), observed_at)

    def unavailable_input(self, locator: str, message: str) -> dict[str, Any]:
        return self.failure("unavailable", self.source("user_input", locator, []), message)

    def tool_state(self) -> dict[str, Any]:
        """Resolve checkout provenance when live; retain the assigned baseline in fixtures."""
        if not isinstance(self.runner, ProductionRunner):
            return {"name": TOOL_NAME, "commit": BASELINE_COMMIT, "dirty_tree": True}
        repository = Path(__file__).resolve().parents[2]
        revision = self.runner.run(["git", "-C", str(repository), "rev-parse", "HEAD"])
        status_result = self.runner.run(
            ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=normal"]
        )
        commit = revision.stdout.decode("ascii", "ignore").strip().lower()
        if revision.exit_code != 0 or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            commit = BASELINE_COMMIT
        dirty = True
        if status_result.available and not status_result.timed_out and status_result.exit_code == 0:
            dirty = bool(status_result.stdout)
        return {"name": TOOL_NAME, "commit": commit, "dirty_tree": dirty}

    def collect_remoteproc(self) -> tuple[dict[str, Any], dict[str, Any]]:
        locator = "/sys/class/remoteproc"
        source = self.source("fixture" if self.fixture_root else "file", locator, [])
        try:
            entries, directory_truncated = list_directory(
                self.system_path(locator), MAX_REMOTE_PROCS, "remoteproc")
        except FileNotFoundError:
            failure = self.failure("missing", source, f"directory not found: {locator}")
            return failure, failure.copy()
        except PermissionError as exc:
            failure = self.failure("permission_denied", source, str(exc))
            return failure, failure.copy()
        except ReadTimedOut:
            failure = self.failure("timeout", source, f"directory read timed out: {locator}")
            return failure, failure.copy()
        except OSError as exc:
            failure = self.failure("command_failed", source, f"directory read failed: {exc}")
            return failure, failure.copy()
        inventory: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        for entry in entries:
            try:
                with read_deadline(FILE_TIMEOUT_SECONDS):
                    is_directory = entry.is_dir()
            except (OSError, ReadTimedOut):
                continue
            if not is_directory:
                continue
            values: dict[str, Any] = {"path": f"{locator}/{entry.name}"}
            for field in ("name", "state", "firmware"):
                linux_path = f"{locator}/{entry.name}/{field}"
                observation = self.read_observation(f"{entry.name}-{field}", linux_path)
                values[field] = observation["value"] if observation["status"] == "success" else None
                values[f"{field}_status"] = observation["status"]
                evidence_ids.extend(observation["source"]["evidence_ids"])
            inventory.append(values)
        source["evidence_ids"] = evidence_ids[:32]
        observed_at = utc_now()
        inventory_obs = self.success({"items": inventory, "directory_truncated": directory_truncated}, source, observed_at)
        candidates = [item for item in inventory if "cdsp" in str(item.get("name") or "").lower()]
        candidate_source = self.source(source["kind"], locator + " (name contains cdsp)", source["evidence_ids"])
        candidate_obs = self.success(candidates, candidate_source, observed_at)
        return inventory_obs, candidate_obs

    def node_inventory(self, item_id: str, linux_directory: str, prefix: str | None = None) -> dict[str, Any]:
        source = self.source("fixture" if self.fixture_root else "metadata", linux_directory, [])
        base = self.system_path(linux_directory)
        try:
            entries, truncated = list_directory(base, MAX_DEVICE_NODES, prefix)
        except FileNotFoundError:
            return self.failure("missing", source, f"directory not found: {linux_directory}")
        except PermissionError as exc:
            return self.failure("permission_denied", source, str(exc))
        except ReadTimedOut:
            return self.failure("timeout", source, f"directory read timed out: {linux_directory}")
        except OSError as exc:
            return self.failure("command_failed", source, f"directory read failed: {exc}")
        items = []
        for entry in entries:
            try:
                with read_deadline(FILE_TIMEOUT_SECONDS):
                    info = entry.lstat()
                mode = stat.S_IMODE(info.st_mode)
                try:
                    import pwd
                    user = pwd.getpwuid(info.st_uid).pw_name
                except (ImportError, KeyError):
                    user = None
                try:
                    import grp
                    group = grp.getgrgid(info.st_gid).gr_name
                except (ImportError, KeyError):
                    group = None
                items.append({
                    "path": f"{linux_directory.rstrip('/')}/{entry.name}",
                    "mode": f"{mode:04o}", "uid": info.st_uid, "gid": info.st_gid,
                    "user": user, "group": group,
                    "node_type": "character" if stat.S_ISCHR(info.st_mode) else (
                        "directory" if stat.S_ISDIR(info.st_mode) else "other"),
                })
            except PermissionError:
                items.append({"path": f"{linux_directory.rstrip('/')}/{entry.name}",
                              "metadata_status": "permission_denied"})
            except (OSError, ReadTimedOut) as exc:
                items.append({"path": f"{linux_directory.rstrip('/')}/{entry.name}",
                              "metadata_status": "unavailable", "diagnostic": str(exc)[:256]})
        return self.metadata_observation(item_id, linux_directory, {"items": items, "directory_truncated": truncated})

    def inspect_explicit_path(self, item_id: str, supplied: str | None, expected: str) -> dict[str, Any]:
        locator = f"--{item_id.replace('_', '-')}"
        if supplied is None:
            return self.unavailable_input(locator, f"{expected} path was not supplied")
        linux_path = supplied
        if self.fixture_root:
            if PurePosixPath(linux_path).is_absolute():
                path = self.system_path(linux_path)
            else:
                relative = safe_fixture_reference(linux_path, locator)
                assert self.fixture_system_root is not None
                path = (self.fixture_system_root / relative).resolve()
                fixture_system_root = self.fixture_system_root
                if path != fixture_system_root and fixture_system_root not in path.parents:
                    raise InputError(f"fixture user path escapes root: {linux_path!r}")
        else:
            path = Path(linux_path)
        observed_at = utc_now()
        source = self.source("fixture" if self.fixture_root else "user_input", linux_path, [])
        try:
            with read_deadline(FILE_TIMEOUT_SECONDS):
                info = path.lstat()
        except FileNotFoundError:
            return self.failure("missing", source, f"path not found: {linux_path}")
        except PermissionError as exc:
            return self.failure("permission_denied", source, str(exc))
        except ReadTimedOut:
            return self.failure("timeout", source, f"metadata read timed out: {linux_path}")
        except OSError as exc:
            return self.failure("command_failed", source, f"metadata read failed: {exc}")
        value: dict[str, Any] = {
            "path": linux_path,
            "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
            "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            "size": info.st_size,
            "architecture": None,
        }
        if stat.S_ISREG(info.st_mode):
            try:
                header = read_bounded_file(path, 4096)
            except PermissionError as exc:
                return self.failure("permission_denied", source, str(exc))
            except ReadTimedOut:
                return self.failure("timeout", source, f"header read timed out: {linux_path}")
            except OSError as exc:
                return self.failure("command_failed", source, f"header read failed: {exc}")
            evidence_id = self.add_evidence(item_id, header.data, header.truncated, ".header")
            source["evidence_ids"] = [evidence_id]
            value["architecture"] = parse_pe_arch(header.data) if expected == "PE" else parse_elf_arch(header.data)
        return self.success(value, source, observed_at)

    def collect(self, steam_path: str | None, proton_path: str | None,
                guest_exe: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        self.output.mkdir(parents=False, exist_ok=False)
        self.evidence_dir.mkdir()
        remoteproc, cdsp = self.collect_remoteproc()
        host_name = (
            self.read_observation("host-name", "/etc/hostname") if self.fixture_root
            else self.command_observation("host-name", ["uname", "-n"])
        )
        user_name = self.command_observation("user-name", ["id", "-un"])
        uname = self.command_observation("uname", ["uname", "-a"])
        os_release = self.read_observation("os-release", "/etc/os-release", parse_os_release)
        bootc = self.command_observation("bootc", ["bootc", "status"])
        steam = self.inspect_explicit_path("steam_path", steam_path, "ELF")
        proton = self.inspect_explicit_path("proton_path", proton_path, "ELF")
        guest = self.inspect_explicit_path("guest_exe", guest_exe, "PE")
        finished_at = utc_now()
        profile: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "example_only": bool(self.fixture_root),
            "profile_kind": "private",
            "device_profile_id": self.profile_id,
            "supersedes": None,
            "evidence_level": "host_test",
            "gate": "not_run",
            "collection": {
                "method": "fixture" if self.fixture_root else "live_linux",
                "started_at": self.started_at,
                "finished_at": finished_at,
                "tool": self.tool_state(),
            },
            "identity": {"host_name": host_name, "user_name": user_name},
            "hardware": {
                "market_name": self.unavailable_input("market_name", "market name is not inferred by the collector"),
                "device_tree_model": self.read_observation("device-tree-model", "/sys/firmware/devicetree/base/model"),
                "device_tree_compatible": self.read_observation(
                    "device-tree-compatible", "/sys/firmware/devicetree/base/compatible", parse_nul_strings),
                "soc_id": self.read_observation("soc-id", "/sys/bus/soc/devices/soc0/soc_id"),
                "soc_family": self.read_observation("soc-family", "/sys/bus/soc/devices/soc0/family"),
                "soc_machine": self.read_observation("soc-machine", "/sys/bus/soc/devices/soc0/machine"),
                "soc_revision": self.read_observation("soc-revision", "/sys/bus/soc/devices/soc0/revision"),
            },
            "os": {
                "distribution": os_release,
                "image": bootc,
                "kernel": uname,
                "libc": self.command_observation("libc", ["getconf", "GNU_LIBC_VERSION"]),
            },
            "graphics": {
                "vulkan": self.command_observation("vulkaninfo", ["vulkaninfo", "--summary"]),
                "egl": self.command_observation("eglinfo", ["eglinfo"]),
            },
            "npu": {
                "remoteproc_inventory": remoteproc,
                "cdsp_candidates": cdsp,
                "fastrpc_nodes": self.node_inventory("fastrpc-nodes", "/dev", "fastrpc"),
                "dma_heap_nodes": self.node_inventory("dma-heap-nodes", "/dev/dma_heap"),
            },
            "runtime_stack": {"bootc": bootc, "steam": steam, "proton": proton, "guest_executable": guest},
            "game_candidates": ([{
                "candidate_id": "guest-executable",
                "name": self.success(Path(guest_exe).name, self.source("user_input", "--guest-exe", []), utc_now()),
                "executable": guest,
            }] if guest_exe else []),
            "evidence": self.evidence,
            "redaction": None,
        }
        finished_at = utc_now()
        profile["collection"]["finished_at"] = finished_at
        profile_path = self.output / "device-profile.json"
        write_json(profile_path, profile)
        self.artifact_paths.append(profile_path)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "device_profile_id": self.profile_id,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "collector_argv": self.argv,
            "artifacts": [artifact_record(path, self.output) for path in self.artifact_paths],
        }
        manifest_path = self.output / "run-manifest.json"
        write_json(manifest_path, manifest)
        return profile, manifest


def parse_nul_strings(data: bytes) -> list[str]:
    return [part.decode("utf-8", "replace") for part in data.rstrip(b"\x00").split(b"\x00") if part]


def parse_os_release(data: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in data.decode("utf-8", "replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        values[key] = value
    return values


def parse_elf_arch(data: bytes) -> dict[str, Any]:
    if len(data) < 20 or data[:4] != b"\x7fELF":
        return {"format": "unknown", "machine": None, "bits": None}
    byte_order = "little" if data[5] == 1 else "big" if data[5] == 2 else None
    if byte_order is None:
        return {"format": "ELF", "machine": None, "bits": None}
    machine_number = int.from_bytes(data[18:20], byte_order)
    machines = {3: "x86", 40: "ARM", 62: "x86_64", 183: "AArch64", 243: "RISC-V"}
    bits = {1: 32, 2: 64}.get(data[4])
    return {"format": "ELF", "machine": machines.get(machine_number, f"EM_{machine_number}"),
            "machine_number": machine_number, "bits": bits, "endianness": byte_order}


def parse_pe_arch(data: bytes) -> dict[str, Any]:
    if len(data) < 64 or data[:2] != b"MZ":
        return {"format": "unknown", "machine": None, "bits": None}
    offset = int.from_bytes(data[0x3C:0x40], "little")
    if offset + 6 > len(data) or data[offset:offset + 4] != b"PE\x00\x00":
        return {"format": "PE", "machine": None, "bits": None}
    machine_number = int.from_bytes(data[offset + 4:offset + 6], "little")
    machines = {0x014C: ("x86", 32), 0x8664: ("x86_64", 64), 0x01C4: ("ARM", 32),
                0xAA64: ("ARM64", 64)}
    machine, bits = machines.get(machine_number, (f"IMAGE_FILE_MACHINE_{machine_number:04X}", None))
    return {"format": "PE", "machine": machine, "machine_number": machine_number, "bits": bits}


def write_json(path: Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(payload)


def artifact_record(path: Path, output: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.relative_to(output).as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
            "byte_count": len(data)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a bounded, private M0 Linux device profile in a new directory.",
        epilog=("Read-only inventory: this tool never installs software, elevates privileges, writes firmware, "
                "unlocks hardware, changes configuration, or performs remote login."),
    )
    parser.add_argument("--output", required=True, help="new output directory (existing paths are refused)")
    parser.add_argument("--steam-path", help="explicit Steam executable or directory; no account scan is performed")
    parser.add_argument("--proton-path", help="explicit Proton executable or directory")
    parser.add_argument("--guest-exe", help="explicit guest PE executable")
    parser.add_argument("--fixture-root", help="test-only fixture case; never executes fixture programs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        print(f"refusing to overwrite existing output path: {output}", file=sys.stderr)
        return 2
    if not output.name or output.parent == output:
        print("output must name a new directory", file=sys.stderr)
        return 2
    fixture = Path(args.fixture_root) if args.fixture_root else None
    if fixture is None and not sys.platform.startswith("linux"):
        print("live collection requires Linux; use --fixture-root for host tests", file=sys.stderr)
        return 2
    if fixture is not None and (not fixture.exists() or not fixture.is_dir()):
        print(f"fixture case directory does not exist: {fixture}", file=sys.stderr)
        return 2
    if fixture is not None:
        for label, supplied in (("--steam-path", args.steam_path),
                                ("--proton-path", args.proton_path),
                                ("--guest-exe", args.guest_exe)):
            if supplied is None:
                continue
            posix_path = PurePosixPath(supplied)
            if "\\" in supplied or any(part in ("", ".", "..") for part in posix_path.parts):
                print(f"unsafe fixture path for {label}: {supplied!r}", file=sys.stderr)
                return 2
    invocation = [TOOL_NAME, *(argv if argv is not None else sys.argv[1:])]
    try:
        collector = Collector(output, fixture, invocation)
        collector.collect(args.steam_path, args.proton_path, args.guest_exe)
    except FileExistsError as exc:
        print(f"refusing to overwrite existing path: {exc}", file=sys.stderr)
        return 2
    except InputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    except (CollectionError, OSError) as exc:
        print(f"fatal collection error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # trustworthy output cannot be promised after an unexpected failure
        print(f"internal collection error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

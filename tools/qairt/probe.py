#!/usr/bin/env python3
"""Validate and smoke-test the one pinned QAIRT 2.49 Windows host profile."""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.abi import inspector as abi_inspector
from tools.host.environment import HostEnvironmentError, preflight


RECEIPT_VERSION = "qairt-windows-host-probe-v1"
MAX_CAPTURE_BYTES = 64 * 1024
TIMEOUT_SECONDS = 120
CAPTURE_DRAIN_GRACE_SECONDS = 0.25
VENDOR_ENV = ("QAIRT_SDK_ROOT", "QNN_SDK_ROOT", "SNPE_ROOT", "AISW_SDK_ROOT", "PYTHONPATH")


class ProbeError(Exception):
    """A pinned input, filesystem safety check, or required probe failed."""


@dataclass(frozen=True)
class Profile:
    source_url: str
    archive_name: str
    download_name: str
    last_modified: str
    etag: str
    amz_version_id: str
    archive_root: str
    runtime_file_count: int
    runtime_uncompressed_bytes: int
    archive_size: int
    archive_sha256: str
    product: str
    version: str
    build_id: str
    python_minors: tuple[int, ...]
    files: Mapping[str, tuple[int, str]]
    required_packages: Mapping[str, str]
    probes: Mapping[str, str]
    abi_files: tuple[str, ...]


FILES = {
    "sdk.yaml": (975, "309ac8f6c75c2fdc808f1c9b9d0da60be123c21a79532cca70a9c4b144d983f4"),
    "NOTICE.txt": (130445, "0c5e8aad3506d0ab881cabaf0dae8de64e1784dc1ee6c873caf24a78fbf01924"),
    "NOTICE_WINDOWS.txt": (75924, "effcb274b3ed1316af67253f728a35e42dc277b2c46005ebba12b5277e35f00b"),
    "LICENSE.pdf": (147577, "ec1dccfdcba5c6e64126e84199b8362bf4999107bfa567ebe831dbb4c461692b"),
    "bin/check-python-dependency": (9643, "5655e44f36e2ad0c8c4f7c161bc98ec652b95f9da40c4d1a4ddcb273ad9571c5"),
    "bin/x86_64-windows-msvc/qairt-converter": (21000, "05ef29fb931523b7ad2dae576eead1c2081163a5a76572dc90ab4e38df2ebd5e"),
    "bin/x86_64-windows-msvc/qairt-quantizer": (6751, "410336ebd497c5a85fcaaa53485f6ce8e19ffa57fcd8430423010d8682eb26e4"),
    "bin/x86_64-windows-msvc/qairt-dlc-info": (2763, "80ea841ef32b211df33b02e78c71ae32e553e573461595274037963549fee308"),
    "bin/x86_64-windows-msvc/qnn-context-binary-generator.exe": (4127744, "cfc8f38ad8e9b68051707f12e566ffba6aac4e69b5b51beda16e6ba4f6138511"),
    "bin/x86_64-windows-msvc/qnn-net-run.exe": (4595712, "00dfbe08a0152c885d108ccda70648c4b13d6b714bbc6c6f7b70cb3456f73891"),
    "lib/x86_64-windows-msvc/QnnCpu.dll": (4997840, "b2963ff19a4a3002afc597ac5f047eac18a6f03e7b8f81bf512458e0980cc62b"),
    "lib/x86_64-windows-msvc/QnnHtpNetRunExtensions.dll": (962768, "5f344d998e4365f6c69a66ea19aedc46e386f78fa699bc49438adcbce7542bed"),
    "lib/x86_64-windows-msvc/QnnHtp.dll": (95289040, "231364de1c59a93961788508b97a80e3bf6bba54bf683c2deb5749db4268b399"),
}
REQUIRED_PACKAGES = {
    "safetensors":"0.4.3", "absl-py":"2.1.0", "aenum":"3.1.15", "attrs":"23.2.0",
    "dash":"2.12.1", "decorator":"4.4.2", "invoke":"1.7.3", "joblib":"1.4.0",
    "jsonschema":"4.19.0", "lxml":"5.2.1", "mako":"1.2.0", "matplotlib":"3.10.8",
    "mock":"3.0.5", "numpy":"1.26.4", "opencv-python":"4.8.1.78", "optuna":"3.3.0",
    "packaging":"24.0", "pandas":"2.3.3", "paramiko":"3.5.1", "pathlib2":"2.3.6",
    "pillow":"10.2.0", "plotly":"5.20.0", "psutil":"6.1.1", "pydantic":"2.8.2",
    "pytest":"8.1.1", "pyyaml":"6.0.3", "rich":"13.9.4", "scikit-optimize":"0.9.0",
    "scipy":"1.15.3", "six":"1.16.0", "tabulate":"0.9.0", "typing-extensions":"4.14.0",
    "xlsxwriter":"1.2.2",
}
DEFAULT_PROFILE = Profile(
    "https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/2.49.0.260730/v2.49.0.260730.zip",
    "qairt-community-2.49.0.260730.zip", "v2.49.0.260730.zip",
    "Wed, 05 Aug 2026 13:14:18 GMT", '"06bb516133a84d0d9bbe575aad08c3eb"',
    "ZCUei.1qtbN63UlERy9VBiGo.GbL3ISQ",
    "qairt/2.49.0.260730", 2698, 971685250,
    2414977444, "32de9b5b2b069aeb93ba090071e777ff464349b3296358c4d3b35040dccbd159",
    "QAIRT", "2.49.0", "260730134355", (10, 12), FILES, REQUIRED_PACKAGES,
    {"converter":"bin/x86_64-windows-msvc/qairt-converter", "quantizer":"bin/x86_64-windows-msvc/qairt-quantizer", "metadata":"bin/x86_64-windows-msvc/qairt-dlc-info"},
    ("bin/x86_64-windows-msvc/qnn-context-binary-generator.exe", "bin/x86_64-windows-msvc/qnn-net-run.exe", "lib/x86_64-windows-msvc/QnnCpu.dll", "lib/x86_64-windows-msvc/QnnHtpNetRunExtensions.dll"),
)


def _is_reparse(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _directory_chain(path: Path, label: str) -> list[Path]:
    selected = Path(os.path.abspath(os.fspath(path)))
    chain = list(reversed((selected, *selected.parents)))
    for item in chain:
        try:
            value = item.stat(follow_symlinks=False)
        except OSError as exc:
            raise ProbeError(f"cannot inspect {label} ancestor {item}: {exc}") from exc
        if _is_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise ProbeError(f"{label} ancestor must be a non-reparse directory: {item}")
    return chain


class _DirectoryGuard(AbstractContextManager["_DirectoryGuard"]):
    """Hold directory identities; Windows handles intentionally omit share-delete."""

    def __init__(self, *targets: Path):
        unique: dict[str, Path] = {}
        for target in targets:
            for item in _directory_chain(target, "selected directory"):
                unique.setdefault(os.path.normcase(str(item)), item)
        self.paths = list(unique.values())
        self.entries: list[tuple[Path, Any, tuple[int, int]]] = []

    def __enter__(self) -> "_DirectoryGuard":
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create = kernel32.CreateFileW
            create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
            create.restype = ctypes.c_void_p
            for path in self.paths:
                handle = create(str(path), 0x80, 0x1 | 0x2, None, 3, 0x02000000, None)
                if handle == ctypes.c_void_p(-1).value:
                    self.__exit__(None, None, None)
                    raise ProbeError(f"cannot lock directory against replacement: {path} (winerror {ctypes.get_last_error()})")
                st = path.stat(follow_symlinks=False)
                self.entries.append((path, handle, (st.st_dev, st.st_ino)))
        else:
            for path in self.paths:
                descriptor = os.open(path, os.O_RDONLY)
                st = os.fstat(descriptor)
                self.entries.append((path, descriptor, (st.st_dev, st.st_ino)))
        return self

    def verify(self) -> None:
        for path, _handle, identity in self.entries:
            try:
                st = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise ProbeError(f"locked directory disappeared during probe: {path}") from exc
            if _is_reparse(st) or (st.st_dev, st.st_ino) != identity:
                raise ProbeError(f"locked directory identity changed during probe: {path}")

    def __exit__(self, *_args: object) -> None:
        if os.name == "nt":
            close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
            for _path, handle, _identity in reversed(self.entries):
                close(handle)
        else:
            for _path, descriptor, _identity in reversed(self.entries):
                os.close(descriptor)
        self.entries.clear()


def _regular(path: Path, label: str) -> os.stat_result:
    try:
        value = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ProbeError(f"cannot inspect {label}: {exc}") from exc
    if _is_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise ProbeError(f"{label} must be a regular non-reparse file")
    return value


def _safe_root(root: Path) -> Path:
    selected = Path(os.path.abspath(os.fspath(root)))
    try:
        st = selected.stat(follow_symlinks=False)
    except OSError as exc:
        raise ProbeError(f"cannot inspect SDK root: {exc}") from exc
    if _is_reparse(st) or not stat.S_ISDIR(st.st_mode):
        raise ProbeError("SDK root must be a directory and not a reparse point")
    return selected


def _inside(root: Path, logical: str) -> Path:
    pure = PurePosixPath(logical)
    if pure.is_absolute() or not pure.parts or any(p in ("", ".", "..") for p in pure.parts):
        raise ProbeError(f"unsafe profile path: {logical!r}")
    current = root
    for part in pure.parts:
        current = current / part
        st = _regular(current, logical) if current == root.joinpath(*pure.parts) else current.stat(follow_symlinks=False)
        if _is_reparse(st):
            raise ProbeError(f"profile path traverses a reparse point: {logical}")
        if current != root.joinpath(*pure.parts) and not stat.S_ISDIR(st.st_mode):
            raise ProbeError(f"profile path parent is not a directory: {logical}")
    try:
        current.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ProbeError(f"profile path escapes SDK root: {logical}") from exc
    return current


def _hash_file(
    path: Path, expected_size: int, label: str, *, capture: bool = False
) -> tuple[str, bytes | None]:
    before = _regular(path, label)
    if before.st_size != expected_size:
        raise ProbeError(f"{label} size mismatch: expected {expected_size}, found {before.st_size}")
    digest = hashlib.sha256()
    captured = bytearray() if capture else None
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ProbeError(f"{label} changed before reading")
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
                if captured is not None:
                    captured.extend(chunk)
        after = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise ProbeError(f"cannot read {label}: {exc}") from exc
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise ProbeError(f"{label} changed while reading")
    return digest.hexdigest(), bytes(captured) if captured is not None else None


_RUNTIME_PREFIXES = (
    "bin/x86_64-windows-msvc/",
    "lib/x86_64-windows-msvc/",
    "lib/python/",
)


def _zip_logical(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\0" in name or re.match(r"^[A-Za-z]:", name):
        raise ProbeError(f"unsafe ZIP member path: {name!r}")
    logical = PurePosixPath(name.rstrip("/"))
    if logical.is_absolute() or not logical.parts or any(part in ("", ".", "..") for part in logical.parts):
        raise ProbeError(f"unsafe ZIP member path: {name!r}")
    return logical


def _archive_runtime(
    archive: Path, snapshot_root: Path, profile: Profile
) -> tuple[str, dict[str, Path], bytes]:
    before = _regular(archive, "archive")
    if before.st_size != profile.archive_size:
        raise ProbeError(f"archive size mismatch: expected {profile.archive_size}, found {before.st_size}")
    digest = hashlib.sha256()
    snapshot_paths: dict[str, Path] = {}
    sdk_yaml: bytes | None = None
    root_prefix = profile.archive_root.rstrip("/") + "/"
    try:
        with archive.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ProbeError("archive changed before reading")
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
            archive_hash = digest.hexdigest()
            if archive_hash != profile.archive_sha256:
                raise ProbeError("archive SHA-256 mismatch")
            stream.seek(0)
            with zipfile.ZipFile(stream) as package:
                seen: set[str] = set()
                runtime: list[tuple[zipfile.ZipInfo, str]] = []
                for member in package.infolist():
                    logical = _zip_logical(member.filename)
                    key = str(logical).casefold()
                    if key in seen:
                        raise ProbeError(f"duplicate ZIP member path: {member.filename}")
                    seen.add(key)
                    unix_mode = (member.external_attr >> 16) & 0xFFFF
                    windows_attrs = member.external_attr & 0xFFFF
                    if stat.S_ISLNK(unix_mode) or windows_attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                        raise ProbeError(f"ZIP member is a symlink or reparse point: {member.filename}")
                    name = str(logical)
                    if member.is_dir():
                        continue
                    if name == root_prefix + "sdk.yaml":
                        sdk_yaml = package.read(member)
                    if name.startswith(root_prefix):
                        relative = name[len(root_prefix):]
                        if any(relative.startswith(prefix) for prefix in _RUNTIME_PREFIXES):
                            runtime.append((member, relative))
                if len(runtime) != profile.runtime_file_count or sum(item.file_size for item, _ in runtime) != profile.runtime_uncompressed_bytes:
                    raise ProbeError("archive runtime file count or uncompressed byte total mismatch")
                for member, relative in runtime:
                    destination = snapshot_root.joinpath(*PurePosixPath(relative).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(member) as source, destination.open("xb") as target:
                        for chunk in iter(lambda: source.read(1 << 20), b""):
                            target.write(chunk)
                    snapshot_paths[relative] = destination
        after = archive.stat(follow_symlinks=False)
    except ProbeError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ProbeError(f"cannot validate or extract archive: {exc}") from exc
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise ProbeError("archive changed while validating or extracting")
    if sdk_yaml is None:
        raise ProbeError("archive is missing pinned sdk.yaml")
    return archive_hash, snapshot_paths, sdk_yaml


def _metadata(data: bytes, profile: Profile) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ProbeError(f"cannot read sdk.yaml as UTF-8: {exc}") from exc
    def scalar(name: str) -> str:
        match = re.search(rf"(?m)^{re.escape(name)}:\s*([^#\r\n]+?)\s*$", text)
        if not match:
            raise ProbeError(f"sdk.yaml is missing {name}")
        return match.group(1)
    product, version, build = scalar("product"), scalar("version"), scalar("build_id")
    if (product, version, build) != (profile.product, profile.version, profile.build_id):
        raise ProbeError(f"sdk.yaml identity mismatch: product={product}, version={version}, build_id={build}")
    if not re.search(r"(?m)^\s{2}Windows:\s*11\s*$", text):
        raise ProbeError("sdk.yaml does not declare Windows 11 support")
    return {"product": product, "version": version, "build_id": build, "windows": "11"}


def _environment(root: Path, python: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in VENDOR_ENV:
        env.pop(name, None)
    bin_dir = root / "bin" / "x86_64-windows-msvc"
    lib_dir = root / "lib" / "x86_64-windows-msvc"
    scripts = python.parent
    env.update({
        "QAIRT_SDK_ROOT": str(root), "QNN_SDK_ROOT": str(root), "SNPE_ROOT": str(root),
        "PYTHONPATH": str(root / "lib" / "python"), "VIRTUAL_ENV": str(scripts.parent),
        "PATH": os.pathsep.join((str(bin_dir), str(lib_dir), str(scripts))),
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
    })
    return env


def _run(
    argv: Sequence[str],
    env: Mapping[str, str],
    timeout: int = TIMEOUT_SECONDS,
    *,
    _ready_hook: Callable[[subprocess.Popen[bytes]], None] | None = None,
) -> dict[str, Any]:
    logical = list(argv)
    captures: dict[str, dict[str, Any]] = {}
    capture_errors: dict[str, str] = {}
    def drain(name: str, pipe: Any) -> None:
        digest = hashlib.sha256(); kept = bytearray(); total = 0
        try:
            for chunk in iter(lambda: pipe.read(8192), b""):
                total += len(chunk); digest.update(chunk)
                if len(kept) < MAX_CAPTURE_BYTES:
                    kept.extend(chunk[: MAX_CAPTURE_BYTES - len(kept)])
            captures[name] = {"text": bytes(kept).decode("utf-8", errors="replace"), "captured_bytes": len(kept), "total_bytes": total, "truncated": total > len(kept), "sha256": digest.hexdigest()}
        except OSError as exc:
            capture_errors[name] = f"{type(exc).__name__}: {exc}"
        finally:
            # The draining thread owns its pipe. In particular, do not close a
            # BufferedReader from the coordinator while this thread is blocked
            # in read(), because that close can itself wait on the reader lock.
            pipe.close()
    try:
        process = subprocess.Popen(logical, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        assert process.stdout is not None and process.stderr is not None
        threads = [
            threading.Thread(
                target=drain,
                args=("stdout", process.stdout),
                name="qairt-probe-stdout",
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=("stderr", process.stderr),
                name="qairt-probe-stderr",
                daemon=True,
            ),
        ]
        for thread in threads: thread.start()
        if _ready_hook is not None:
            try:
                # Test-only synchronization: the production path supplies no
                # hook. The timeout budget intentionally begins after a test
                # has proved that its descendant inherited the capture pipes.
                _ready_hook(process)
            except BaseException:
                process.kill()
                process.wait()
                raise
        try:
            code = process.wait(timeout=timeout); timed_out = False
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(); code = None; timed_out = True
        drain_deadline = time.monotonic() + CAPTURE_DRAIN_GRACE_SECONDS
        for thread in threads:
            thread.join(max(0.0, drain_deadline - time.monotonic()))
        capture_states = {
            name: (
                "pending" if thread.is_alive()
                else "failed" if name in capture_errors
                else "complete"
            )
            for name, thread in zip(("stdout", "stderr"), threads)
        }
        pending = [name for name, state in capture_states.items() if state == "pending"]
        if pending:
            rendered = " ".join(
                f"{name}_capture={capture_states[name]}" for name in ("stdout", "stderr")
            )
            if timed_out:
                raise ProbeError(
                    f"required probe timed out: {logical[1]}; direct process terminated; "
                    f"{rendered}; possible descendant pipe holder remains, so capture is "
                    "incomplete"
                )
            raise ProbeError(
                f"required probe capture incomplete after direct process exited {code}: "
                f"{logical[1]}; {rendered}; possible descendant pipe holder remains; "
                "refusing to report probe success"
            )
        failed = [name for name, state in capture_states.items() if state == "failed"]
        if failed:
            detail = "; ".join(f"{name}: {capture_errors[name]}" for name in failed)
            raise ProbeError(
                f"required probe capture failed: {logical[1]}; {detail}; "
                "refusing to report probe success"
            )
    except OSError as exc:
        raise ProbeError(f"could not invoke required probe {logical[1]!r}: {exc}") from exc
    result = {"argv": logical, "exit_code": code, "timed_out": timed_out, "stdout": captures["stdout"], "stderr": captures["stderr"]}
    if timed_out:
        raise ProbeError(f"required probe timed out: {logical[1]}")
    if code != 0:
        raise ProbeError(f"required probe exited {code}: {logical[1]}")
    return result


def _packages(python: Path, env: Mapping[str, str], expected: Mapping[str, str]) -> dict[str, str]:
    code = "import importlib.metadata as m,json,re; n=lambda s:re.sub(r'[-_.]+','-',s).lower(); print(json.dumps({n(d.metadata['Name']):d.version for d in m.distributions() if d.metadata['Name']}))"
    result = _run([str(python), "-I", "-c", code], env, 60)
    try:
        installed = json.loads(result["stdout"]["text"])
    except json.JSONDecodeError as exc:
        raise ProbeError("vendor Python dependency probe returned invalid JSON") from exc
    found: dict[str, str] = {}
    for name, version in expected.items():
        key = re.sub(r"[-_.]+", "-", name).lower()
        actual = installed.get(key)
        if actual != version:
            raise ProbeError(f"Python dependency {name} expected {version}, found {actual or 'missing'}")
        found[name] = actual
    _run([str(python), "-I", "-m", "pip", "--isolated", "check"], env, 60)
    return found


def probe(archive: Path, sdk_root: Path, python: Path, output: Path, profile: Profile = DEFAULT_PROFILE) -> dict[str, Any]:
    output = Path(os.path.abspath(os.fspath(output)))
    if os.path.lexists(output):
        raise ProbeError(f"output already exists; refusing to overwrite: {output}")
    root = _safe_root(sdk_root)
    parent = output.parent
    archive = Path(os.path.abspath(os.fspath(archive)))
    with _DirectoryGuard(root, parent) as guard:
        reserved_handle, reserved_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=parent
        )
        try:
            receipt, payload = _probe_locked(archive, root, python, profile)
            guard.verify()
            reserved_before = os.fstat(reserved_handle)
            reserved_path = Path(reserved_name)
            reserved_now = reserved_path.stat(follow_symlinks=False)
            if _is_reparse(reserved_now) or (
                reserved_now.st_dev,
                reserved_now.st_ino,
            ) != (reserved_before.st_dev, reserved_before.st_ino):
                raise ProbeError("reserved output file identity changed during probe")
            with os.fdopen(os.dup(reserved_handle), "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            guard.verify()
            try:
                os.link(reserved_name, output)
            except FileExistsError as exc:
                raise ProbeError(
                    "output appeared during probe; refusing to overwrite"
                ) from exc
            guard.verify()
        except Exception:
            guard.verify()
            raise
        finally:
            os.close(reserved_handle)
            try:
                os.unlink(reserved_name)
            except OSError:
                pass
        return receipt


def _probe_locked(
    archive: Path, root: Path, python: Path, profile: Profile
) -> tuple[dict[str, Any], bytes]:
    verified: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for logical, (size, digest) in profile.files.items():
        path = _inside(root, logical)
        actual, _ = _hash_file(path, size, logical)
        if actual != digest:
            raise ProbeError(f"selected SDK file SHA-256 mismatch: {logical}")
        paths[logical] = path
        verified.append({"path": logical, "bytes": size, "sha256": actual})
    try:
        py = preflight(python)
    except HostEnvironmentError as exc:
        raise ProbeError(str(exc)) from exc
    minor = int(str(py["version"]).split(".")[1])
    if minor not in profile.python_minors:
        raise ProbeError(f"QAIRT profile requires Python 3.{profile.python_minors}, found {py['version']}")
    if py["architecture"] != "AMD64":
        raise ProbeError(f"QAIRT x86_64 Windows profile requires AMD64 Python, found {py['architecture']}")
    python_path = Path(str(py["python"]))
    snapshot_context = tempfile.TemporaryDirectory(prefix="qairt-probe-")
    try:
        snapshot_root = Path(snapshot_context.name)
        archive_hash, snapshot_paths, archive_sdk_yaml = _archive_runtime(archive, snapshot_root, profile)
        sdk_digest = hashlib.sha256(archive_sdk_yaml).hexdigest()
        if sdk_digest != profile.files["sdk.yaml"][1] or len(archive_sdk_yaml) != profile.files["sdk.yaml"][0]:
            raise ProbeError("archive sdk.yaml does not match the pinned SDK metadata")
        metadata = _metadata(archive_sdk_yaml, profile)
        for logical in (*profile.probes.values(), *profile.abi_files):
            snapshot = snapshot_paths.get(logical)
            if snapshot is None:
                raise ProbeError(f"archive runtime is missing selected file: {logical}")
            expected_size, expected_hash = profile.files[logical]
            actual, _ = _hash_file(snapshot, expected_size, f"archive:{logical}")
            if actual != expected_hash:
                raise ProbeError(f"archive selected file SHA-256 mismatch: {logical}")
        env = _environment(snapshot_root, python_path)
        packages = _packages(python_path, env, profile.required_packages)
        probe_results: dict[str, Any] = {}
        for name, logical in profile.probes.items():
            result = _run([str(python_path), str(snapshot_paths[logical]), "--help"], env)
            result["argv"] = ["<python>", logical, "--help"]
            result["executed_sha256"] = profile.files[logical][1]
            probe_results[name] = result
        abi = []
        for logical in profile.abi_files:
            item = abi_inspector.inspect_file(snapshot_paths[logical], profile.version, "x86_64")
            item["file"] = logical
            item["inspected_sha256"] = profile.files[logical][1]
            abi.append(item)
    except abi_inspector.AbiError as exc:
        raise ProbeError(f"ABI inspection failed: {exc}") from exc
    finally:
        snapshot_context.cleanup()
    # Detect replacement or mutation after the initial trust decision and tool
    # execution, before publishing a receipt that binds those exact bytes.
    if _hash_file(archive, profile.archive_size, "archive")[0] != profile.archive_sha256:
        raise ProbeError("archive changed during probe")
    for logical, (size, digest) in profile.files.items():
        if _hash_file(paths[logical], size, logical)[0] != digest:
            raise ProbeError(f"selected SDK file changed during probe: {logical}")
    receipt = {
        "schema_version": RECEIPT_VERSION, "profile": "QAIRT-2.49.0.260730-windows-x86_64",
        "archive": {
            "archive_name": profile.archive_name, "download_name": profile.download_name,
            "source_url": profile.source_url, "bytes": profile.archive_size,
            "sha256": archive_hash,
            "archive_root": profile.archive_root,
            "runtime_snapshot": {
                "file_count": profile.runtime_file_count,
                "uncompressed_bytes": profile.runtime_uncompressed_bytes,
                "subtrees": list(_RUNTIME_PREFIXES),
            },
            "http_evidence": {
                "last_modified": profile.last_modified, "etag": profile.etag,
                "etag_semantics": "not_a_sha256", "x_amz_version_id": profile.amz_version_id,
            },
        }, "sdk": metadata,
        "python": {"version": py["version"], "architecture": py["architecture"]},
        "vendor_required_packages": packages, "selected_files": verified, "required_probes": probe_results,
        "abi": abi,
        "capabilities": {
            "help": "invocable", "conversion": "not_run", "quantization": "not_run", "metadata_export": "not_run",
            "cpu_execution": "not_run", "cpu_backend": "candidate_present", "htp_prepare": "candidate_present",
            "htp_execution": "not_run",
            "htp_prepare_note": "Candidate files and documentation are not execution evidence.",
            "device": "not_run", "game": "not_run",
        },
    }
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return receipt, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = probe(args.archive, args.sdk_root, args.python, args.output)
    except (ProbeError, OSError) as exc:
        print(f"QAIRT probe failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"receipt": str(args.output), "profile": receipt["profile"], "help": "invocable"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

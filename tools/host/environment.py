#!/usr/bin/env python3
"""Preflight and create the repository's baseline host virtual environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VENV = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "tools" / "device" / "requirements-host.txt"
MINIMUM_PYTHON = (3, 10)
LOCKED_REQUIREMENT = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)")
PROBE = (
    "import json,platform,struct,sys,sysconfig;"
    "print(json.dumps({'version':[sys.version_info.major,sys.version_info.minor,"
    "sys.version_info.micro],'machine':platform.machine(),"
    "'platform':sysconfig.get_platform(),'pointer_bits':struct.calcsize('P')*8}))"
)


class HostEnvironmentError(Exception):
    """A deterministic host-environment validation or setup failure."""


def _display_output(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "no diagnostic output").strip()


def _run(
    argv: Sequence[str],
    timeout: int,
    env: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostEnvironmentError(f"could not run {argv[0]!r}: {exc}") from exc


def _resolve_python(python_executable: Path) -> Path:
    if not python_executable.exists():
        raise HostEnvironmentError(f"Python executable does not exist: {python_executable}")
    if not python_executable.is_file():
        raise HostEnvironmentError(f"Python executable is not a file: {python_executable}")
    return python_executable.resolve()


def _pip_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
        environment.pop(name, None)
    # pip --isolated still honors PIP_CONFIG_FILE. os.devnull disables all
    # configuration files, including global/site files with install targets.
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def _normalise_architecture(
    interpreter_platform: object, machine: object, pointer_bits: object
) -> str:
    if pointer_bits != 64:
        raise HostEnvironmentError(
            f"unsupported Python pointer width {pointer_bits!r}; a 64-bit interpreter is required"
        )
    platform_value = str(interpreter_platform).strip().lower().replace("_", "-")
    if platform_value == "win-amd64":
        return "AMD64"
    if platform_value == "win-arm64":
        return "ARM64"
    if platform_value.startswith("win"):
        raise HostEnvironmentError(
            f"unsupported Python platform {interpreter_platform!r}; "
            "expected win-amd64 or win-arm64"
        )

    # Non-Windows hosts use this fallback for repository tests. On Windows,
    # sysconfig identifies the selected interpreter ISA even under emulation.
    value = str(machine).strip().upper()
    if value in {"AMD64", "X86_64"}:
        return "AMD64"
    if value in {"ARM64", "AARCH64"}:
        return "ARM64"
    raise HostEnvironmentError(
        f"unsupported Python architecture {machine!r}; expected AMD64 or ARM64"
    )


def preflight(python_executable: Path) -> dict[str, object]:
    """Validate one explicitly selected interpreter without changing it."""
    selected = _resolve_python(python_executable)
    probe = _run([str(selected), "-I", "-c", PROBE], timeout=30)
    if probe.returncode != 0:
        raise HostEnvironmentError(
            f"Python probe failed for {selected}: {_display_output(probe)}"
        )
    try:
        payload = json.loads(probe.stdout.strip())
        version_parts = payload["version"]
        version = tuple(int(part) for part in version_parts)
        if len(version) != 3:
            raise ValueError("version must contain three components")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HostEnvironmentError(f"Python probe returned invalid data for {selected}") from exc
    if version[:2] < MINIMUM_PYTHON:
        rendered = ".".join(str(part) for part in version)
        raise HostEnvironmentError(
            f"Python {rendered} is unsupported; Python 3.10 or newer is required"
        )
    architecture = _normalise_architecture(
        payload.get("platform"), payload.get("machine"), payload.get("pointer_bits")
    )

    pip = _run(
        [str(selected), "-I", "-m", "pip", "--version"],
        timeout=30,
        env=_pip_environment(),
    )
    if pip.returncode != 0:
        raise HostEnvironmentError(
            f"pip is unavailable for {selected}: {_display_output(pip)}"
        )
    pip_version = pip.stdout.strip()
    if not pip_version:
        raise HostEnvironmentError(f"pip returned no version information for {selected}")
    return {
        "python": str(selected),
        "version": ".".join(str(part) for part in version),
        "architecture": architecture,
        "pip": pip_version,
    }


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _normalise_distribution_name(name: object) -> str:
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def _baseline_requirements() -> dict[str, tuple[str, str]]:
    try:
        lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HostEnvironmentError(
            f"could not read baseline requirements file {REQUIREMENTS}: {exc}"
        ) from exc
    expected: dict[str, tuple[str, str]] = {}
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.partition("#")[0].strip()
        if not line:
            continue
        match = LOCKED_REQUIREMENT.fullmatch(line)
        if match is None:
            raise HostEnvironmentError(
                f"baseline requirement at line {line_number} is not an exact name==version pin"
            )
        name, version = match.groups()
        key = _normalise_distribution_name(name)
        if key in expected:
            raise HostEnvironmentError(f"duplicate baseline requirement: {name}")
        expected[key] = (name, version)
    if not expected:
        raise HostEnvironmentError("baseline requirements file contains no exact pins")
    return expected


def _verify_baseline_distributions(
    created_python: Path, expected: dict[str, tuple[str, str]]
) -> None:
    listed = _run(
        [
            str(created_python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "list",
            "--format=json",
        ],
        timeout=120,
        env=_pip_environment(),
    )
    if listed.returncode != 0:
        raise HostEnvironmentError(
            "could not inspect installed baseline distributions: "
            f"{_display_output(listed)}"
        )
    try:
        payload = json.loads(listed.stdout)
        if not isinstance(payload, list):
            raise TypeError("pip list payload must be a list")
        installed = {
            _normalise_distribution_name(item["name"]): str(item["version"])
            for item in payload
            if isinstance(item, dict)
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HostEnvironmentError("pip list returned invalid distribution data") from exc
    for key, (name, required_version) in expected.items():
        actual_version = installed.get(key)
        if actual_version != required_version:
            rendered = actual_version if actual_version is not None else "missing"
            raise HostEnvironmentError(
                f"baseline distribution {name} expected {required_version}, found {rendered}"
            )


def initialise(python_executable: Path, venv: Path) -> tuple[dict[str, object], Path]:
    """Create and provision a new venv, refusing every pre-existing target."""
    # Do not resolve the final component: lexists must also see broken symlinks
    # and reparse points rather than following them to a missing destination.
    target = Path(os.path.abspath(os.fspath(venv)))
    if os.path.lexists(target):
        raise HostEnvironmentError(
            f"virtual environment target already exists; refusing to overwrite: {target}"
        )
    info = preflight(python_executable)
    expected = _baseline_requirements()

    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise HostEnvironmentError(
            f"virtual environment target already exists; refusing to overwrite: {target}"
        ) from exc
    except OSError as exc:
        raise HostEnvironmentError(
            f"could not reserve virtual environment target {target}: {exc}"
        ) from exc

    create = _run([str(info["python"]), "-I", "-m", "venv", str(target)], timeout=180)
    if create.returncode != 0:
        raise HostEnvironmentError(
            f"virtual environment creation failed for {target}: {_display_output(create)}"
        )
    created_python = _venv_python(target)
    if not created_python.is_file():
        raise HostEnvironmentError(
            f"virtual environment was created without its expected interpreter: {created_python}"
        )
    install = _run(
        [
            str(created_python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "--disable-pip-version-check",
            "install",
            "--require-virtualenv",
            "-r",
            str(REQUIREMENTS),
        ],
        timeout=600,
        env=_pip_environment(),
    )
    if install.returncode != 0:
        raise HostEnvironmentError(
            f"baseline requirements installation failed in {target}: {_display_output(install)}"
        )
    verify = _run(
        [str(created_python), "-I", "-m", "pip", "--isolated", "check"],
        timeout=120,
        env=_pip_environment(),
    )
    if verify.returncode != 0:
        raise HostEnvironmentError(
            f"installed requirements failed pip check in {target}: {_display_output(verify)}"
        )
    _verify_baseline_distributions(created_python, expected)
    return info, created_python


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or initialise the Windows baseline Python environment."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "init"):
        child = subparsers.add_parser(command)
        child.add_argument(
            "--python",
            type=Path,
            required=True,
            help="explicit path to the Python executable to probe or use",
        )
        if command == "init":
            child.add_argument("--venv", type=Path, default=DEFAULT_VENV)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            info = preflight(args.python)
            print(
                f"OK: Python {info['version']} ({info['architecture']}); "
                f"pip available; executable={info['python']}"
            )
        else:
            info, created_python = initialise(args.python, args.venv)
            print(
                f"OK: created {created_python.parent.parent} with Python "
                f"{info['version']} ({info['architecture']}) and installed "
                f"{REQUIREMENTS.name}"
            )
    except HostEnvironmentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

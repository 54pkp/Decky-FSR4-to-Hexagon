#!/usr/bin/env python3
"""Check or create the pinned Windows QAIRT/P6 Python frontend environment."""

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
REQUIREMENTS = Path(__file__).resolve().parent / "requirements-frontend.txt"
REQUIRED_PYTHON = (3, 12, 14)
LOCKED_REQUIREMENT = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)")
PROBE = (
    "import json,platform,struct,sys,sysconfig;"
    "print(json.dumps({'version':[sys.version_info.major,sys.version_info.minor,"
    "sys.version_info.micro],'implementation':platform.python_implementation(),"
    "'machine':platform.machine(),"
    "'platform':sysconfig.get_platform(),'pointer_bits':struct.calcsize('P')*8}))"
)


class FrontendEnvironmentError(Exception):
    """A deterministic QAIRT frontend environment failure."""


def _display_output(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "no diagnostic output").strip()


def _pip_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PIP_TARGET", "PIP_PREFIX", "PIP_USER"):
        environment.pop(name, None)
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def _run(
    argv: Sequence[str], timeout: int, env: Optional[Mapping[str, str]] = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv), stdin=subprocess.DEVNULL, text=True, capture_output=True,
            check=False, timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FrontendEnvironmentError(f"could not run {argv[0]!r}: {exc}") from exc


def _normalise_name(name: object) -> str:
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def requirements() -> dict[str, tuple[str, str]]:
    try:
        lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise FrontendEnvironmentError(
            f"could not read frontend requirements {REQUIREMENTS}: {exc}"
        ) from exc
    expected: dict[str, tuple[str, str]] = {}
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.partition("#")[0].strip()
        if not line:
            continue
        match = LOCKED_REQUIREMENT.fullmatch(line)
        if match is None:
            raise FrontendEnvironmentError(
                f"frontend requirement at line {line_number} is not an exact name==version pin"
            )
        name, version = match.groups()
        key = _normalise_name(name)
        if key in expected:
            raise FrontendEnvironmentError(f"duplicate frontend requirement: {name}")
        expected[key] = (name, version)
    if not expected:
        raise FrontendEnvironmentError("frontend requirements contain no exact pins")
    return expected


def _resolve_python(python_executable: Path) -> Path:
    if not python_executable.exists():
        raise FrontendEnvironmentError(
            f"Python executable does not exist: {python_executable}"
        )
    if not python_executable.is_file():
        raise FrontendEnvironmentError(f"Python executable is not a file: {python_executable}")
    return python_executable.resolve()


def preflight(python_executable: Path) -> dict[str, str]:
    selected = _resolve_python(python_executable)
    probe = _run([str(selected), "-I", "-c", PROBE], timeout=30)
    if probe.returncode != 0:
        raise FrontendEnvironmentError(
            f"Python probe failed for {selected}: {_display_output(probe)}"
        )
    try:
        payload = json.loads(probe.stdout.strip())
        version = tuple(int(part) for part in payload["version"])
        if len(version) != 3:
            raise ValueError("version must contain three components")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrontendEnvironmentError(
            f"Python probe returned invalid data for {selected}"
        ) from exc
    rendered = ".".join(str(part) for part in version)
    if version != REQUIRED_PYTHON:
        required = ".".join(str(part) for part in REQUIRED_PYTHON)
        raise FrontendEnvironmentError(
            f"Python {rendered} is unsupported; QAIRT frontend requires exactly {required}"
        )
    if payload.get("implementation") != "CPython":
        raise FrontendEnvironmentError(
            "unsupported Python implementation; QAIRT frontend requires CPython"
        )
    if payload.get("pointer_bits") != 64 or str(payload.get("platform")).lower() != "win-amd64":
        raise FrontendEnvironmentError(
            "unsupported Python architecture; QAIRT frontend requires 64-bit win-amd64"
        )
    pip = _run(
        [str(selected), "-I", "-m", "pip", "--version"],
        timeout=30, env=_pip_environment(),
    )
    if pip.returncode != 0 or not pip.stdout.strip():
        raise FrontendEnvironmentError(
            f"pip is unavailable for {selected}: {_display_output(pip)}"
        )
    return {"python": str(selected), "version": rendered, "architecture": "AMD64"}


def _venv_python(venv: Path) -> Path:
    return venv / "Scripts" / "python.exe"


def _verify_distributions(
    created_python: Path, expected: dict[str, tuple[str, str]]
) -> None:
    listed = _run(
        [str(created_python), "-I", "-m", "pip", "--isolated", "list", "--format=json"],
        timeout=120, env=_pip_environment(),
    )
    if listed.returncode != 0:
        raise FrontendEnvironmentError(
            f"could not inspect installed frontend distributions: {_display_output(listed)}"
        )
    try:
        payload = json.loads(listed.stdout)
        if not isinstance(payload, list):
            raise TypeError("pip list payload must be a list")
        installed = {
            _normalise_name(item["name"]): str(item["version"])
            for item in payload if isinstance(item, dict)
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FrontendEnvironmentError("pip list returned invalid distribution data") from exc
    for key, (name, required_version) in expected.items():
        actual = installed.get(key)
        if actual != required_version:
            raise FrontendEnvironmentError(
                f"frontend distribution {name} expected {required_version}, "
                f"found {actual if actual is not None else 'missing'}"
            )


def initialise(python_executable: Path, venv: Path) -> tuple[dict[str, str], Path]:
    target = Path(os.path.abspath(os.fspath(venv)))
    if os.path.lexists(target):
        raise FrontendEnvironmentError(
            f"virtual environment target already exists; refusing to overwrite: {target}"
        )
    info = preflight(python_executable)
    expected = requirements()
    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FrontendEnvironmentError(
            f"virtual environment target already exists; refusing to overwrite: {target}"
        ) from exc
    except OSError as exc:
        raise FrontendEnvironmentError(
            f"could not reserve virtual environment target {target}: {exc}"
        ) from exc
    create = _run([info["python"], "-I", "-m", "venv", str(target)], timeout=180)
    if create.returncode != 0:
        raise FrontendEnvironmentError(
            f"virtual environment creation failed for {target}: {_display_output(create)}"
        )
    created_python = _venv_python(target)
    if not created_python.is_file():
        raise FrontendEnvironmentError(
            f"virtual environment was created without its expected interpreter: {created_python}"
        )
    install = _run(
        [str(created_python), "-I", "-m", "pip", "--isolated",
         "--disable-pip-version-check", "install", "--require-virtualenv",
         "-r", str(REQUIREMENTS)],
        timeout=900, env=_pip_environment(),
    )
    if install.returncode != 0:
        raise FrontendEnvironmentError(
            f"frontend requirements installation failed in {target}: {_display_output(install)}"
        )
    checked = _run(
        [str(created_python), "-I", "-m", "pip", "--isolated", "check"],
        timeout=120, env=_pip_environment(),
    )
    if checked.returncode != 0:
        raise FrontendEnvironmentError(
            f"installed frontend requirements failed pip check in {target}: "
            f"{_display_output(checked)}"
        )
    _verify_distributions(created_python, expected)
    return info, created_python


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check or initialise the pinned Windows QAIRT/P6 frontend environment."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "init"):
        child = commands.add_parser(command)
        child.add_argument("--python", required=True, type=Path)
        if command == "init":
            child.add_argument("--venv", required=True, type=Path)
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
            info, created = initialise(args.python, args.venv)
            print(
                f"OK: created {created.parent.parent} with Python {info['version']} "
                f"({info['architecture']}) and installed {REQUIREMENTS.name}"
            )
    except FrontendEnvironmentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

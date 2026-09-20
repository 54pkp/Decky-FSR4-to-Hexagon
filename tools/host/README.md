# Windows host environment

`environment.py` checks one explicitly selected Python executable and can create
the repository baseline virtual environment. It requires Python 3.10 or newer,
accepts AMD64 and ARM64 interpreters, verifies `pip`, and reports the detected
version and architecture. It never selects `py`, searches for Python, or assumes
a Codex installation path.

From the repository root, use the full path of the interpreter you chose:

```powershell
$python = 'C:\Path With Spaces\Python312\python.exe'
& $python tools/host/environment.py check --python $python
& $python tools/host/environment.py init --python $python --venv .venv
```

`check` is read-only and can inspect an existing environment by passing its
interpreter, for example `--python .\.venv\Scripts\python.exe`. `init` refuses
any target path that already exists rather than replacing or modifying it. It
creates the target with `venv`, installs `tools/device/requirements-host.txt`,
and runs `pip check`. The target is reserved before `venv` starts, and pip runs
in isolated mode so user configuration and `PIP_*` install settings do not
redirect the baseline dependencies; pip configuration files are disabled for
the provisioning subprocesses. The exact pinned distributions are then read
back from the new environment. If creation, installation, or dependency verification
fails after the target is created, the partial target is preserved for manual
inspection and removal; a later `init` will refuse to overwrite it.

After a successful initialisation, run the host suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

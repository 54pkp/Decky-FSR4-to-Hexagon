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

Installation is an attempted provisioning step, not proof that network access or
a suitable package cache exists. It installs only the baseline requirements; the
separate reference, FSR extraction, and QAIRT environments have their own pinned
dependencies and are not created by this command.

After a successful initialisation, run the host suite with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

The suite has grown since the original 2026-09-22 audit. The formerly
unconditional Windows file-symlink skip now performs an in-place capability
probe: capable hosts execute the safety assertion, while incapable hosts emit
the actual exception type, errno, winerror, and text. Consult `docs/STATUS.md`
for the current counts rather than treating skipped tests as passed.

## Existing test environments

These are separate, already-provisioned local environments, not an implemented
aggregate runner. Their ignored directories are machine-local; a fresh checkout
must provision the relevant dependencies before using its command.

| Environment | Audited purpose and versions | Dependency source |
| --- | --- | --- |
| `.venv` | Python 3.12.14; baseline schema, host, model, replay, and file-handling tests; jsonschema 4.26.0 | [`requirements-host.txt`](../device/requirements-host.txt) |
| `local/venvs/reference` | Python 3.12.14; P5 ONNX/ORT CPU reference; NumPy 2.2.6, ONNX 1.18.0, ONNX Runtime 1.22.0 | [`requirements-reference.txt`](../reference/requirements-reference.txt) and the [P5 guide](../reference/README.md) |
| `local/venvs/fsr-extract` | Python 3.12.14; P7 extraction and P8 pass0 checks; NumPy 2.2.6, jsonschema 4.26.0 | [P7/P8 guide](../fsr/README.md); no checked-in full rebuild lock yet |
| `local/venvs/qairt-2.49.0.260730` | Python 3.12.14 AMD64; P3 probe, P4 ABI tests, and P6 small graph; 33 QAIRT pins plus ONNX 1.18.0 and protobuf 7.36.2 | [`requirements-frontend.txt`](../qairt/requirements-frontend.txt), [`environment.py`](../qairt/environment.py), and the [QAIRT guide](../qairt/README.md); transitive/native closure and execution receipt binding remain separate R work |

Run the environments explicitly from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\local\venvs\reference\Scripts\python.exe -m unittest discover -s tests/reference -p "test_*.py" -v
.\local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests/fsr -p "test_*.py" -v
.\local\venvs\qairt-2.49.0.260730\Scripts\python.exe -m unittest tests.qairt.test_environment tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline -v
```

Or run all four explicit environments in fixed order and publish a machine-readable report:

```powershell
.\.venv\Scripts\python.exe tools\host\verify_environments.py --baseline-python .\.venv\Scripts\python.exe --reference-python .\local\venvs\reference\Scripts\python.exe --fsr-python .\local\venvs\fsr-extract\Scripts\python.exe --qairt-python .\local\venvs\qairt-2.49.0.260730\Scripts\python.exe --output artifacts\multi-venv-NEW.json
```

Missing/invalid environments are `not_run` and yield exit 2; started suites that fail or time out are `failed` and yield exit 1. Later suites still run. Skip counts remain separate from passes; exit 0 means all four suites completed without test failures, not that every assertion ran. Parent tests are classified once even when `subTest` emits multiple events; the report preserves the raw event counts separately. The aggregate totals are execution observations and include overlap between suites. The runner never installs dependencies or creates environments. Its timeout only establishes the direct worker result—not descendant-process quiescence—and output hashes/tails cover the fixed file-size snapshot selected after that worker ends; later descendant output is excluded and counted separately when observed.

The specialized commands complement the baseline result; they do not turn its
skips into one automatic 233/233 run. None of these host commands is a device,
HTP, complete FSR4, or game test.

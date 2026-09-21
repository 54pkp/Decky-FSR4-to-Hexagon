# Decky FSR4 to Hexagon

[中文](README.md) | English

This project studies running an FSR4 neural-network partition on a Qualcomm Hexagon NPU in a Snapdragon Linux handheld, with the GPU responsible for features, temporal processing, reconstruction, and writeback. The first target remains AYN Odin 3 / Snapdragon 8 Elite / Armada OS.

> This is currently a Windows host-preparation and offline-validation project, not a usable upscaler. No Odin 3 has been connected, and there is no complete FSR4 path, HTP execution, GPU pipeline, game adapter, deployment tool, or Decky plugin. [STATUS](docs/STATUS.md) is the only authoritative current-status page.

## Evidence available today

- M0 host-side device-profile schema, a read-only Linux collector, offline validation/redaction, and synthetic numerical and lifecycle replay tools.
- A locally pinned official QAIRT Community 2.49.0.260730 package and isolated environment. The repository-owned `Conv -> Add -> ReLU` graph has completed real W8A8/B32 conversion, metadata checks, and a Windows QNN CPU comparison. It is not FSR4, and the target HTP backend was not executed.
- Five public FSR v07 `i8_quality` source files have been verified and extracted into a 100-array NPZ plus graph spec. P8 only compared the fixed small-sample preprocessing `pass0` convolution with an independent scalar CPU implementation at zero LSB. Passes 1–13, FSR ONNX/QDQ, DLC, a v79 context, an official golden, and GPU/HTP execution remain undone.
- The 2026-09-22 audit baseline command ran 233 tests: 199 passed and 34 skipped. Three dedicated environments ran 33 of those skipped tests, and the remaining behavior received one manual check. This is not a single automatic 233/233 result.

Local SDKs, models, and generated artifacts stay in Git-ignored directories and are not distributed with the source. STATUS links to the fixed asset digests and batch evidence.

## Windows quick check

Select an explicit Python 3.10+ executable and run from the repository root:

```powershell
$python = 'C:\Path With Spaces\Python312\python.exe'
& $python tools/host/environment.py check --python $python
& $python tools/host/environment.py init --python $python --venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

`init` only creates a new target and attempts to install the pinned baseline requirements. It does not guarantee that a package cache or network is available, and it does not provision the dedicated QAIRT, ONNX Runtime, or NumPy environments. Do not initialize over an existing `.venv`; use its interpreter for the read-only `check`. See the [host environment guide](tools/host/README.md).

## Documentation entry points

- [Documentation map](docs/README.md)
- [Sole current status](docs/STATUS.md)
- [Device-free R fixes, F real-FSR offline work, and E engineering candidates](docs/roadmap/HOST_PREPARATION.md)
- [Device D batches](docs/roadmap/DEVICE_EXECUTION.md)
- [Closed H/P host batches](docs/roadmap/COMPLETED_HOST_BATCHES.md)
- [Lightweight collaboration rules](docs/ai/MULTI_AGENT_WORKFLOW.md)

## Current operational warnings

- R01–R03 fixed the P5 create race, P6 publication race, and strict encoding bitwidth/symmetry parsing with deterministic regressions. Every P6 run still requires a separate work directory.
- M0 still has check-then-replace path races and can leave partial redaction output after a failure. Do not run it in an untrusted directory or treat failed output as publishable.
- Every artifact-producing command should use a new path. Recheck input and output SHA-256 values against its receipt afterward. Device, game, performance, and quality conclusions remain `not_run`.

## Upstreams and license boundaries

Primary research references include [fsr4-hexagon](https://github.com/puzzled-pancake/fsr4-hexagon), [rp6-npu-unlock](https://github.com/puzzled-pancake/rp6-npu-unlock), and [hexscale](https://github.com/drewano/hexscale). Upstream experiments do not replace device or game validation here.

This repository's license has not been selected. AMD models, Qualcomm SDK/runtime components, firmware, game files, and upstream code remain under their own terms. This repository does not distribute those proprietary assets and is not an official AMD, Qualcomm, NVIDIA, Valve, AYN, or Decky project.

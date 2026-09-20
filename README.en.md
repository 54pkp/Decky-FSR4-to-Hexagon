# Decky FSR4 to Hexagon

[中文](README.md) | English

This project explores running **FSR4 neural inference on Qualcomm Hexagon NPUs** in Snapdragon Linux handhelds, while the GPU handles feature preparation, temporal processing, reconstruction, and writeback. The first research target is **AYN Odin 3 / Snapdragon 8 Elite / Armada OS**, initially through a game's DLSS Super Resolution interface, with Steam and an optional Decky management UI considered later.

> **Current stage: only M0 host tools, synthetic CPU references/replay tools, and design documents exist; there is no upscaling runtime.**
> No Odin 3 is connected or tested. Current evidence is limited to Windows, anonymous fixtures, offline checks, and CPU host tests. There is no installable plugin, validated game, HTP/QNN NPU result, or performance data, so this project cannot claim that FSR4 works on a Hexagon NPU.

## What exists

- A `draft-0` device-profile schema.
- `tools/device/collect.py`, a read-only unprivileged Linux collector that does not install software, elevate privileges, modify firmware, unlock hardware, or open a DSP session.
- `tools/device/profile_tools.py` for offline profile validation and public redaction.
- Synthetic-only manifest validation, affine-int8, and integer-grid spatial references under `tools/model/`.
- An incomplete same-frame identity/single-in-flight CPU lifecycle replay under `tools/replay/`.
- Anonymous fixtures and device/model/replay Python regression tests that run on Windows.

These tools establish device facts and test file-handling boundaries. They do not implement FSR4 model execution, a GPU/NPU graphics pipeline, game integration, a launcher, or a Decky plugin. The NPU would also perform only part of the complete upscaling algorithm.

## Windows host check

Python 3.10+ is required. From the repository root, run:

```powershell
python -m pip install -r tools/device/requirements-host.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

This unified device-free check validates only the Python tools, synthetic CPU references, and fixture behavior. It is not Odin 3, CDSP/FastRPC, HTP, complete FSR4, or game validation. Live device collection is Linux-only; see [`tools/device/README.md`](tools/device/README.md).

## Development entry points

- [Current status and work queue](docs/STATUS.md)
- [Lightweight collaboration rules](docs/ai/MULTI_AGENT_WORKFLOW.md)
- [Single-run prompt](docs/ai/SINGLE_RUN_PROMPT.md)
- [Resumable Goal prompt](docs/ai/GOAL_PROMPT.md)

Consult the [detailed roadmap and research entry point](docs/roadmap/README.md) only when implementing a specific milestone. Always distinguish source review, compilation, host tests, device tests, and game tests.

## Upstreams and license boundaries

- [fsr4-hexagon](https://github.com/puzzled-pancake/fsr4-hexagon): FSR4/Hexagon experiments and model-porting research.
- [rp6-npu-unlock](https://github.com/puzzled-pancake/rp6-npu-unlock): NPU research for a specific RP6 platform, not an Odin 3 installation procedure.
- [drewano/hexscale](https://github.com/drewano/hexscale): Vulkan, QNN service, and diagnostics reference.
- [54pkp/hexscale](https://github.com/54pkp/hexscale): related QNN and management-tool reference.

This repository's license has not been selected. AMD models, Qualcomm SDK/runtime components, firmware, game files, and upstream code remain under their own terms. This repository does not distribute those proprietary assets and is not an official AMD, Qualcomm, NVIDIA, Valve, AYN, or Decky project. Upstream experiments do not replace device or game validation here.

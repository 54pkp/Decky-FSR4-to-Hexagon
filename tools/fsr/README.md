# P7 pinned FSR material intake

`intake.py` is a Windows/CPU wrapper around one pinned upstream extractor. It
accepts only explicit paths, verifies the exact five public source files and
extractor by size, SHA-256, and content/version markers, then runs a copied
extractor against a temporary SDK-shaped tree. It never searches for inputs and
never overwrites the requested output directory.

The source mirror is pinned to
`Rolaand-Jayz/FSR-4.0.2-reference@c5e34b4b7128ffeb152f80cbdb6d715d577ec289`;
the extractor is pinned to
`puzzled-pancake/fsr4-hexagon@8c7a972ab70e5693828a856da71ce711232af463`.
The output parent must already exist and must not traverse a symlink, junction,
or other reparse point.

```powershell
.\.venv\Scripts\python.exe tools/fsr/intake.py `
  --sdk-root C:\path\to\FidelityFX-SDK `
  --extractor C:\path\to\fsr4-hexagon\model\extract\build_weights.py `
  --python C:\path\to\python-with-numpy.exe `
  --output artifacts\p7-fsr-v07
```

Only `fsr4_quality_weights.npz`, `graph_spec.json`, and
`intake_receipt.json` are published. The receipt binds the source and extractor
URLs/commits to all input and output hashes. Generated artifacts remain ignored
by the repository. Before publication the selected `--python` checks all 100
NPZ arrays without pickle/object dtypes, including the required pass-0 and scale
table shapes/dtypes; the graph spec must have 11 bin tensors, 58 declarations,
and 13 calls. Publication uses a completed same-parent staging directory and an
atomic final rename. A successful host extraction does not establish official
FSR4 equivalence, QNN/HTP execution, device behavior, game integration, quality,
or performance.

## P8 pass-0 host CPU cross-check

`pass0_check.py` consumes an explicit P7 publication directory and the pinned
upstream `fsr4_sim.py`. Before importing the simulator it verifies the P7
receipt and both artifact hashes, plus the simulator SHA-256 for upstream commit
`8c7a972ab70e5693828a856da71ce711232af463`. It runs a fixed 4x6x8 float16 HWC
feature sample (seven non-zero feature lanes and the required zero lane), then
compares upstream `pass0` with a separate scalar FKYXC implementation. The
predefined final int8 tolerance is zero LSB. It also requires a bit-exact
repeat, a changed output after one fixed effective-channel mutation, all-zero
channel-7 weights, and an unchanged output after poisoning that zero lane with
a finite non-zero value.

```powershell
.\local\venvs\fsr-extract\Scripts\python.exe tools/fsr/pass0_check.py `
  --p7-directory artifacts/p7-fsr-v07-accepted `
  --simulator research/fsr4-hexagon/model/sim/fsr4_sim.py `
  --output artifacts/p8-pass0-receipt.json
```

The JSON receipt is published only after all checks pass and an existing output
is never replaced. It records layouts, shape/dtype, quantization scale,
input/output hashes, and the measured/tolerated LSB difference. This is only a
host CPU cross-check of pass-0 using the same fixed public weight source. It is
not an official golden, complete FSR4, ONNX, QNN/HTP, device, or game result.

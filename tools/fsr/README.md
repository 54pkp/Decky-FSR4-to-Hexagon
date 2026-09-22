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
  --output artifacts\p7-fsr-v07-YOUR-NEW-RUN-ID
```

Only `fsr4_quality_weights.npz`, `graph_spec.json`, and
`intake_receipt.json` are published. The receipt binds the source and extractor
URLs/commits to all input and output hashes. Receipt schema v2 also binds the
selected interpreter hash and runtime identity, the imported NumPy version, the
complete normalized extractor argv, and an exact `ALL GATES PASSED` stdout
line from the pinned extractor. The environment is summarized both before and
after extraction and any drift rejects publication. Ephemeral staging paths are
represented by a hash-bound placeholder, never presented as reproducible input.
Generated artifacts remain ignored by the repository. Before publication the selected `--python` checks all 100
NPZ arrays without pickle/object dtypes, including the required pass-0 and scale
table shapes/dtypes; the graph spec must have 11 bin tensors, 58 declarations,
and 13 calls. Publication uses a completed same-parent staging directory and an
atomic final rename. A successful host extraction does not establish official
FSR4 equivalence, QNN/HTP execution, device behavior, game integration, quality,
or performance.

## Versioned artifact index

`artifact_index.json` is the source-controlled trust selector for P7/P8
receipts. `artifact_index.py` loads it with a closed, versioned schema and
rejects duplicate keys, unknown or missing fields, malformed hashes, ambiguous
current entries, and a current P8 entry that does not bind the current P7 or
zero-LSB tolerance. Artifact directories remain ignored local data: their names
are never evidence and do not appear in the index.

The current P7 receipt is `b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b`;
the current R10b P8 receipt is `2a4c3960304dd19a2c00d70bcbe1309fad23b19017638250e15ce2263cbf8ede`.
The earlier zero-LSB P8 receipt
`4170b2824a5242b1bdfaac6bb39fbc06e23963e323e568f26bdbc5113a7769b6`
is historical/stale because it binds the pre-R10a P7 receipt. The legacy
one-LSB receipt
`67e80e4f030165995167b974016ef77fd76757bdce6a2164579ffac72f213f33`
is also historical/stale and cannot be selected as current zero-LSB evidence.
Known wrapper/validation intermediates are classified audit-temporary. Any
unlisted receipt remains untrusted rather than being inferred current from its
filename.

## P8 pass-0 host CPU cross-check

`pass0_check.py` consumes an explicit P7 publication directory and the pinned
upstream `fsr4_sim.py`. Its production contract selects P7 from the fixed
artifact index, then matches the selected directory's receipt by digest; a
directory name alone cannot select evidence. Before importing the simulator it verifies the P7
receipt is the accepted R10a v2 receipt with SHA-256
`b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b`.
It also verifies that receipt's exact source URL/commit, extractor
URL/commit/content identity, environment/stdout gates, two output entries, and
both selected artifact hashes. Merely self-consistent replacement receipts and
the older wrapper/validated/v1 receipts are rejected. The simulator SHA-256 is
separately pinned for upstream commit
`8c7a972ab70e5693828a856da71ce711232af463`. It runs a fixed 4x6x8 float16 HWC
feature sample (seven non-zero feature lanes and the required zero lane), then
compares upstream `pass0` with a separate scalar FKYXC implementation. The
predefined final int8 tolerance is zero LSB. It also requires a bit-exact
repeat, a changed output after one fixed effective-channel mutation, all-zero
channel-7 weights, and an unchanged output after poisoning that zero lane with
a finite non-zero value.

```powershell
.\local\venvs\fsr-extract\Scripts\python.exe tools/fsr/pass0_check.py `
  --p7-directory artifacts/p7-fsr-v07-r10a-20260922 `
  --simulator research/fsr4-hexagon/model/sim/fsr4_sim.py `
  --output artifacts/p8-pass0-YOUR-NEW-RUN-ID-receipt.json
```

The JSON receipt is published only after all checks pass and an existing output
is never replaced. It records layouts, shape/dtype, quantization scale,
input/output hashes, the accepted P7 receipt hash, and the measured/tolerated
LSB difference. This is only a NumPy host-CPU cross-check of pass-0 using the
same fixed public weight source. It is not an official golden, complete FSR4,
ONNX, QNN/HTP, device, or game result.

The output parent must already exist and every run must use a new `.json` path.
Do not use or overwrite the local legacy `artifacts/p8-pass0-receipt.json`.
That one-LSB file and the previously audited P8 receipt with SHA-256
`4170b2824a5242b1bdfaac6bb39fbc06e23963e323e568f26bdbc5113a7769b6`
are historical and invalid for the R10b trust chain because they predate the
accepted R10a P7 receipt. Generate a new P8 receipt; never trust an artifact
directory name or an old internally consistent receipt.

`pass0` is only the FP16 eight-channel preprocessing convolution that produces
the INT8 16-channel network input. The simulator's pass1–13 graph is not invoked
by this tool. The P7 NPZ/graph are extracted weights and graph description, not
an ONNX model or a complete executable FSR4 package.

## F01 pass1–13 inventory

`pass_manifest.json` is a versioned, machine-validated inventory rather than an
implementation. It binds the current P7/P8 receipt digests, P7 weights and graph
hashes, and pinned simulator commit/content. Each pass records its operator,
primary and skip topology, fixed HWC tensor shape/dtype, CPU weight aliases and
shapes, quantization format, graph call arguments, and expected-result status.
`pass_manifest.py` rejects incomplete, reordered, disconnected, overstated, or
source-mismatched inventories and can hash-check explicit ignored P7/simulator
paths without discovering them automatically.

The root fixture is a deterministic signed-int8 `8x8x16` HWC tensor chosen so
both downscales remain non-empty; it is not a real 1080p frame or game input.
P7 graph declarations use source logical `W,H,C,N`, while the CPU inventory
separately names activation `HWC`, regular-weight `OIHW`, and transposed-weight
`IOHW` layouts. Rounding, saturation, multiply order, and per-call behavior are
marked simulator-derived; zero point and independent operator-source
verification remain unknown because the pinned local sources do not include the
referenced `ml2code_runtime` operator implementation. Every pass1–13 independent
expected source/hash therefore remains `unknown`. F01 does not run or implement
these passes and proves no numerical equivalence, official golden, QNN/HTP,
device, game, quality, or performance result.

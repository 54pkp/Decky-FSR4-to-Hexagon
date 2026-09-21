# Pinned QAIRT 2.49 Windows host probe

This probe accepts four explicit paths and never searches `PATH` for an SDK,
tool, or interpreter. It verifies the pinned community archive, `sdk.yaml`,
notices, selected scripts and Windows binaries before invoking the three
official Python entry points with `--help`.

The pinned source is Qualcomm Software Center QAIRT Community 2.49.0.260730:
`https://softwarecenter.qualcomm.com/api/download/software/sdks/Qualcomm_AI_Runtime_Community/All/2.49.0.260730/v2.49.0.260730.zip`.
The local logical archive name is `qairt-community-2.49.0.260730.zip`; the
server download name is `v2.49.0.260730.zip`. The receipt records the observed
Last-Modified, ETag, and S3 version id alongside the SHA-256. The ETag is
explicitly provenance metadata, not a SHA-256 digest.

```powershell
& .\.venv\Scripts\python.exe tools/qairt/probe.py `
  --archive downloads/qairt-community-2.49.0.260730.zip `
  --sdk-root sdks/qairt/2.49.0.260730 `
  --python local/venvs/qairt-2.49.0.260730/Scripts/python.exe `
  --output artifacts/P3/qairt-2.49.0.260730-host-probe-YOUR-NEW-RUN-ID.json
```

The output is created atomically and an existing destination is never
overwritten. SDK paths and the output parent must not traverse reparse points.
The output parent must already exist; use a new receipt filename for every run
and verify its archive/SDK hashes before relying on it.
The child environment removes inherited vendor SDK variables, then supplies
only the pinned SDK roots, SDK Python/library/tool paths, venv Scripts,
`VIRTUAL_ENV`, and UTF-8 controls. The parent environment is unchanged.
After hashing the ZIP through one held file handle, the probe validates every
member path (including duplicate and symlink rejection) and extracts the
archive's fixed `qairt/2.49.0.260730` runtime into a private temporary
snapshot: 2,698 files and 971,685,250 uncompressed bytes across Windows
`bin`, Windows `lib`, and `lib/python`. Metadata parsing, dependency checks,
`--help`, SDK roots, `PYTHONPATH`, DLL/tool `PATH`, and ABI inspection all use
that archive-derived snapshot, never the expanded SDK's runtime paths. The
expanded selected files and archive are rechecked before receipt publication.
Existing ancestors of the expanded SDK and output parent must not be reparse
points; on Windows they remain open without delete-sharing for the probe and
atomic publication window.

`--help` success means only that converter, quantizer, and DLC metadata entry
points are invocable. It does not prove conversion, quantization, metadata
export, CPU execution, HTP preparation/execution, device behavior, or game
integration. CPU and HTP files are only offline-inspected candidates. The
95-MiB `QnnHtp.dll` is presence/hash checked but is not parsed past the ABI
inspector's 16-MiB safety limit; bounded `QnnHtpNetRunExtensions.dll` supplies
the fourth x86-64 PE candidate.

## P6 small-graph W8A8 pipeline

`small_graph_pipeline.py` consumes only explicit SDK, interpreter, model,
work, output, and P3-receipt paths. The work and output roots must not already
exist; the work path must contain no whitespace because its absolute raw paths
are written into the QAIRT calibration list. For example:

```powershell
& .\local\venvs\qairt-2.49.0.260730\Scripts\python.exe tools/qairt/small_graph_pipeline.py `
  --sdk-root sdks/qairt/2.49.0.260730 `
  --qairt-python local/venvs/qairt-2.49.0.260730/Scripts/python.exe `
  --reference-python local/venvs/reference/Scripts/python.exe `
  --model tools/reference/fixtures/conv_add_relu.onnx `
  --work-root artifacts/P6-work-YOUR-NEW-RUN-ID `
  --output-root artifacts/P6-result-YOUR-NEW-RUN-ID `
  --p3-receipt artifacts/P3/qairt-2.49.0.260730-final-host-probe.json
```

It fixes conversion and W8A8/B32 quantization to target `HTP`, validates the
generated encoding JSON and DLC-info CSV, and then executes the DLC using the
Windows `QnnCpu.dll` plus `QnnModelDlc.dll`. A success receipt is published
only after all three CPU outputs pass the predeclared `atol=0.01, rtol=0`
comparison. Failures preserve the work directory and logs but do not publish a
success output. HTP execution, device, FSR, and game validation remain
`not_run`.

The two parent directories must already exist; both selected roots must be new,
and the absolute work path must contain no whitespace. The pipeline does not
install the QAIRT or reference dependencies, so both explicit interpreters must
already be provisioned. After success, verify `success_receipt.json` and its
bound file hashes before retaining the result.

Each publisher now uses a private, randomly named staging directory beside the
target. If another publisher wins the final rename, the loser removes only its
own staging directory and preserves the winner's output and receipt. Metadata
validation still accepts some malformed bitwidth and boolean representations;
until R03 closes that issue, do not treat acceptance of hand-edited encoding
JSON as trustworthy evidence. Unique work roots remain mandatory.

The P6 success receipt hashes the selected interpreter executables, scripts,
inputs, logs, and outputs, but it does not bind the complete installed Python
package closure or every expanded SDK dependency. P3's probe executes an
archive-derived private snapshot; P6 instead invokes tools and libraries from
the explicitly selected expanded SDK root. Do not infer that a P3 snapshot
receipt alone reproduces P6. Closing that environment/receipt binding is still
an R-series hardening task.

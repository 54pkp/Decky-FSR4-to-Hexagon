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
  --output artifacts/P3/qairt-2.49.0.260730-host-probe.json
```

The output is created atomically and an existing destination is never
overwritten. SDK paths and the output parent must not traverse reparse points.
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

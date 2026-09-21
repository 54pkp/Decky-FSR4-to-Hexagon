# Offline ABI inspector

`inspector.py` performs bounded, read-only structural inspection of one PE or ELF
file using only the Python standard library. It never loads or executes the file.

```powershell
.\.venv\Scripts\python.exe tools/abi/inspector.py path/to/library --expect-machine arm64
.\.venv\Scripts\python.exe tools/abi/inspector.py path/to/hexagon/library --expect-machine hexagon
.\.venv\Scripts\python.exe tools/abi/inspector.py path/to/library --sdk-version 2.50.0
```

The JSON report records format, machine, bitness, explicit SDK metadata (or
`unknown`), and ELF interpreter, `DT_NEEDED`, and `GLIBC_*` version requirements
when structurally available. ELF32/ELF64 and little-/big-endian layouts have
synthetic host regression coverage. Candidate classification requires binary
evidence: PE is Windows, while Android and Linux glibc ELF candidates require
distinctive interpreter/dependency/version evidence. Architecture and path names
are not ABI proof.

Exit code `0` means a report was produced, `2` is command-line usage error, and
`3` is an input, structure, unsupported-machine, or expected-machine error. A
successful report is not device, QNN/HTP, FSR4, game, or runtime validation.

`inventory.py` validates only the explicit P3-pinned QAIRT archive and writes a
deterministic inventory without searching `PATH`, expanded SDK directories, or
the rest of the disk:

```powershell
.\.venv\Scripts\python.exe tools/abi/inventory.py `
  --archive downloads/qairt-community-2.49.0.260730.zip `
  --output artifacts/qairt-abi-inventory.json
```

The complete ZIP namespace is checked for unsafe paths, case-insensitive
duplicates, and symlink/reparse entries while one archive handle remains open.
Only the fixed candidate allowlist is copied into a private temporary snapshot;
each present member must match its pinned size and SHA-256 before structural
inspection. Missing entries describe this exact archive only (including the
gcc9.3/Ubuntu V79 stubs and gcc11 `libcdsprpc.so`); a V81 file is never used as
a V79 fallback. The output keeps device matching `unknown` and execution
`not_run`, refuses to replace an existing file, and contains no absolute paths
or timestamps.

The output parent must already exist and must not traverse a reparse point. Use
a new output filename for every run, then verify the published report hash
before using it as evidence.

The selected allowlist is deliberately not a full SDK inventory. In particular,
the x86_64 Windows `QnnHtp.dll`, Android `libQnnHtpPrepare.so`, and OE gcc11.2
`libQnnHtpPrepare.so` exceed the inspector's 16 MiB safety limit. They remain
explicitly `not_run` in the inventory; this tool does not raise that bounded
parser limit merely to include them. A missing archive member also does not
prove it is absent from a BSP, FastRPC package, or device image.

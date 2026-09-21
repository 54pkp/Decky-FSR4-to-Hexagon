# Offline ABI inspector

`inspector.py` performs bounded, read-only structural inspection of one PE or ELF
file using only the Python standard library. It never loads or executes the file.

```powershell
python tools/abi/inspector.py path/to/library --expect-machine arm64
python tools/abi/inspector.py path/to/library --sdk-version 2.50.0
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

# External asset registry

`registry.py` performs a read-only integrity check within one explicit root. It
does not download, discover, load, or execute assets. Registry paths are logical
forward-slash relative paths; absolute paths, backslashes, traversal, symlinks,
junctions, and paths outside the selected root are rejected.

Run it from the repository root:

```powershell
.\.venv\Scripts\python.exe tools/assets/registry.py verify --root tools/assets/fixtures/complete --registry registry.json
```

Exit code `0` means the registry metadata matches the selected root, including
any honestly declared `missing` entries. Exit code `1` means the contract or a
file claim does not match. Exit code `2` means the registry JSON or selected
input could not be safely read. A successful result separately reports file
counts, `metadata_verified: true`, and `execution_gate: not_run`. It is not
evidence of model, SDK, HTP, device, or game execution.

The `external-asset-registry-v1` object has these required fields:

- component identity, `source_url`, `version_or_commit`, `platform`,
  `architecture`, and purpose;
- `notice` with status `present` plus a registered relative path, or status
  `unknown` plus a null path;
- one or more file records with unique logical names and paths. A `present`
  record has an exact lowercase SHA-256 and byte count with null
  `missing_reason`. A `missing` record has null hash and byte count plus a
  non-empty reason.

Registries are limited to 1 MiB, 256 records, 256 MiB of declared present
content, and bounded JSON depth. Each present file is limited to 64 MiB and
hashed with bounded streaming reads after its path and file identity are
checked.

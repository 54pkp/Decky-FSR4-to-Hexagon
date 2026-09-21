# M0 device-profile `draft-0` contract

This directory freezes the first host-testable M0 data contract. The schema uses
JSON Schema Draft 2020-12; the profile's `schema_version: "draft-0"` is the
project contract version and is not the JSON Schema dialect. Host tools require
Python 3.10 or newer and the exact dependency in `../requirements-host.txt`.
They must instantiate `jsonschema.Draft202012Validator` with a
`jsonschema.FormatChecker`. A missing or incompatible dependency is a fatal,
explicit error; tools must not fall back to a partial validator.

## Evidence boundary

An observation always contains `value`, `source`, `observed_at`, `status`, and
`failure`. A successful observation has `failure: null`. Every other status has
`value: null` and a failure with the same stable category. `missing` means the
named file or fixture entry was absent; `unavailable` means an optional command
or user-supplied path was not provided/installed; neither means unsupported.
`permission_denied`, `timeout`, and `command_failed` retain a bounded diagnostic,
the exit code when one exists, and whether stderr was truncated.

`source.evidence_ids` refers to entries in the top-level `evidence` array. Each
evidence entry identifies one collection item, a lower-case SHA-256, byte count,
truncation state, visibility, and a forward-slash path relative to the collector
output directory. Absolute paths, backslashes, empty paths, and any `..` segment
are invalid. Raw bytes live in files; they are never embedded in the profile.

The collector creates a new output directory containing exactly these required
artifacts (additional bounded evidence files are allowed):

```text
<output>/
  device-profile.json       # private profile only
  run-manifest.json
  evidence/
    <collection-item files>
```

`run-manifest.json` is an object with `schema_version`, `device_profile_id`,
`started_at`, `finished_at`, `collector_argv` (a string array), and `artifacts`.
Each artifact has a safe output-relative `path`, lower-case `sha256`, and
`byte_count`. It describes only files written in this new output directory.
The collector refuses an existing output path and never emits a public profile.

`profile_kind: "private"` requires `redaction: null`. Only the offline redaction
command may create `profile_kind: "public"`; it records policy `public-v1`, the
hash of the private input profile, and a timestamp. Modified evidence is written
as a new public artifact and receives its own hash. Private evidence that is not
published is removed from the public evidence list and from all
`source.evidence_ids`; a public profile must never pair altered content with an
original hash. Redaction replaces sensitive scalar fragments deterministically
within one run with `[REDACTED:<kind>]`, while retaining structure and diagnostic
categories. It covers usernames, host names, home/personal paths, serial-like
identifiers, and the same fragments inside bounded command output.

`gate` is the result of the report-level check; observation `status` describes
one field. They never substitute for one another. All repository fixtures and
examples set `example_only: true` and therefore must have `gate: "not_run"`.
Windows or fixture host tests may establish tool behavior only. They cannot set
an Odin 3 `device_test` gate to pass.

Unknown top-level fields, category fields, observation fields, evidence fields,
and fixture command fields are rejected. Adding contract fields therefore
requires a coordinated schema change rather than silent producer/consumer drift.

## Frozen CLI and exit codes

```text
python tools/device/collect.py --output <new-dir>
    [--steam-path <path>] [--proton-path <path>] [--guest-exe <path>]
    [--fixture-root <case-dir>]

python tools/device/profile_tools.py validate <profile> [--schema <schema>]
python tools/device/profile_tools.py redact <private-profile> --output <new-public-profile>
```

`--fixture-root` is test-only. Without `--schema`, offline validation uses
`tools/device/schema/device-profile.schema.json` resolved from the script, not
the current working directory.

Exit codes are shared by both programs:

- `0`: operation completed; individual collection failures may still be present.
- `1`: the profile does not satisfy the selected schema.
- `2`: CLI/input error, unsafe path, or refusal to overwrite.
- `3`: internal or I/O failure prevents a trustworthy result.

Diagnostics go to stderr. Structured data is written only to the explicitly
named output. No CLI writes an existing file or directory by default.

The current implementation still has documented check/open replacement races,
and redaction failure can leave a partial new file. Use trusted directories and
fresh destinations; only a successful command followed by hash/manifest
verification is evidence. See the current [STATUS](../../../docs/STATUS.md) for
the defect state.

## Frozen fixture and runner protocol

Every fixture case has this layout:

```text
<case-dir>/
  root/                       # relative mirror of /etc, /proc, /sys, /dev
  commands.json
  command-output/
  expected/device-profile.json
  private-profile.json        # optional redaction case
  expected/public-profile.json # optional redaction case
```

All fixture references are forward-slash relative paths contained by the case
directory, with no empty or `..` segment. The collector still writes generated
evidence only beneath the caller's new output directory.

`commands.json` is an array. Each record has exactly these fields:

```json
{
  "argv": ["getconf", "GNU_LIBC_VERSION"],
  "available": true,
  "exit_code": 0,
  "stdout_file": "command-output/getconf.stdout",
  "stderr_file": "command-output/getconf.stderr",
  "delay_ms": 0
}
```

`argv` is a non-empty array of strings and is matched exactly, including order.
`available` is boolean; `exit_code` is an integer or null; output file fields are
safe case-relative strings or null; `delay_ms` is a non-negative integer. No
other fields are accepted. Fixture mode reads these files as data and must never
execute a program from the fixture. An unmatched argv is reported as command
missing (`unavailable`). A delay beyond the collector timeout is reported as
`timeout` without sleeping beyond the configured test budget.

Production and fixture execution implement the same runner result:

```text
argv: list[str]
available: bool
exit_code: int | null
stdout: bounded bytes
stderr: bounded bytes
timed_out: bool
stdout_truncated: bool
stderr_truncated: bool
```

Only the production runner invokes `subprocess`, using an argv array, `shell`
disabled, a timeout, and bounded capture. A timeout must terminate the child,
wait for it, and record the outcome before collection continues. Field-level
errors do not abort unrelated collection items.

The output shape and runner protocol are frozen for FIRST_BATCH S0. Changes need
an explicit integrator-owned contract update (and an ADR if shared `draft-0`
semantics must change), with producer, consumer, fixture, and tests updated
together.

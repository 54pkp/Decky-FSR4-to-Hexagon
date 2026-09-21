# M0 read-only device collector

`collect.py` creates a private `draft-0` profile from bounded, read-only Linux
observations. It requires Python 3.10 or newer and an explicit, new output
directory:

```text
python tools/device/collect.py --output <new-dir>
    [--steam-path <path>] [--proton-path <path>] [--guest-exe <path>]
    [--fixture-root <case-dir>]
```

The output contains `device-profile.json`, `run-manifest.json`, and bounded raw
files under `evidence/`. The profile is private; use the separate offline tool
to validate or produce a public redacted profile. Existing output paths are
refused.

The collector reads standard Linux identity, OS, device-tree, SoC, remoteproc,
FastRPC, dma-heap, and graphics/runtime discovery points. It records node
metadata without opening device nodes. `bootc`, `vulkaninfo`, and `eglinfo` are
run only when installed. Steam, Proton, and guest executables are inspected only
when their paths are explicitly supplied. A missing item is recorded as an
observation failure and does not abort unrelated collection.

External commands use argv arrays with no shell, bounded output, and a timeout.
A timed-out child is terminated and waited for. File reads and directory
enumeration are bounded by time and size. The tool never installs software,
elevates privileges, writes firmware, unlocks hardware, changes configuration,
opens a DSP session, scans an account/home directory, or performs remote login.

## Fixture mode

`--fixture-root` is test-only and follows the frozen layout in
`schema/README.md`. Absolute Linux paths are mapped beneath `<case-dir>/root`.
Commands are exact matches from `commands.json`; command output is read as data
from the case directory. No fixture program is executed. An unmatched argv is
reported as `unavailable`, and a delay beyond the command timeout becomes
`timeout` without waiting for the full delay.

## Exit codes

- `0`: collection completed; individual observations may still have failed.
- `2`: CLI/input/unsafe fixture data error, or overwrite refusal.
- `3`: fatal internal or I/O error prevented a trustworthy report.

Schema validation is performed by `profile_tools.py`; its validation failure
uses exit code `1`. Fixture and Windows host checks establish tool behavior only.
They do not establish Odin 3, CDSP, FastRPC, HTP, device, or game validation.

Evidence validation and redaction now bind the already-open regular file back
to the initial profile-directory identity before reading it, rejecting a path
replacement that opens outside that directory. A failed redaction can still
leave a partial output until R05. Always choose a new output path and treat any
failed output as diagnostic residue rather than a publishable profile. These
Windows host checks do not replace live Linux/device validation.

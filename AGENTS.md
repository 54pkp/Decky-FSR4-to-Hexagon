# Repository guidance

## Start here

- Read `docs/STATUS.md` for current progress and the next eligible batch, then `docs/ai/MULTI_AGENT_WORKFLOW.md`. Use `docs/README.md` as the documentation map.
- Default environment: Windows, no attached Odin 3. Theory, offline tools, CPU tests and explicitly scoped Windows build/fixture work are allowed. Do not require a game, Linux/WSL or a device for an independent host batch.
- H1–H4 and P1–P8/P9a–c are completed historical preparation packages, not the active queue. Their completion never meant complete FSR4, HTP or game support.
- Active device-free work is specified in `docs/roadmap/HOST_PREPARATION.md`: R repairs/reproducibility, F real-model offline work, E bounded engineering preparation. Device-dependent D packages are in `docs/roadmap/DEVICE_EXECUTION.md`. Select only a package whose dependencies and environment are satisfied.
- M0–M9 remain technical milestone references, not a second competing task queue. Historical reports and `FIRST_BATCH.md` are evidence, not instructions to restart completed work.

## Repository and ownership

Prefer the current repository when its normalized origin matches `https://github.com/54pkp/Decky-FSR4-to-Hexagon.git`. Otherwise inspect only the current user's `Documents/GitHub/Decky-FSR4-to-Hexagon`; clone if absent, stop if occupied by unrelated content. Do not search the whole disk or overwrite a directory.

Inspect status before changing anything. Sync only a clean, fast-forwardable tree; preserve dirty or diverged state. Never reset, clean, force-push or include unrelated edits to manufacture success. Only the integrator stages, commits, merges, pushes and updates shared status/contracts. Verify GitHub identity and remote; do not use the historical `unknown` author.

## Roles

- Coordinator/integrator and communication: GPT-5.6 Sol / medium.
- Up to three independent workers: GPT-5.6 Sol / medium.
- Substantive code, tests, contracts or consequential acceptance/roadmap changes: GPT-6 Astra / medium review of the actual frozen diff and new files.
- Use Astra / xhigh only for a specific architecture decision, never Ultra by default. Small wording/link changes may use coordinator self-check.
- Select models through supported role/model parameters; a prompt or edited configuration does not switch an already running conversation. Disclose unavailable/mismatched roles instead of claiming compliance.
- Give workers bounded goals, exact owned paths and checks. Workers do not recursively delegate or mutate Git. Do not invent work to fill slots; respect lower host concurrency limits.

## Execution and documentation

1. Select one leaf batch from STATUS and its linked plan; name dependencies, scope, acceptance and exclusions. A grouping is not a single-run batch.
2. Implement or investigate only the requested behavior. A review/planning request does not authorize implementing the findings or starting the new queue.
3. Run relevant checks, obtain review where required, fix findings and recheck affected behavior.
4. Write one short batch note and update STATUS. Record the base revision, actual environment/backend, exact commands/exit codes, skips, failures, review and one next step.
5. Commit/push only within the user's authorization and repository workflow. Preserve failed-push evidence and local work; do not loop without new information. Single-run mode stops after that batch.

Do not create a Goal or automation unless the user explicitly requests it. For an explicitly requested Goal, freeze a bounded objective and batch subset at startup; never silently expand to all future R/F/E/D work. Hardware gates remain independent.

STATUS owns live progress, next action and evidence links. Plans own batch definitions/dependencies/acceptance. Tool READMEs own actual commands. Public READMEs own a concise capability summary. Historical dated reports retain their original conclusions; new findings get a new record, not rewritten history. Update only affected current pages and keep Chinese/English entry points aligned.

## Evidence and technical boundaries

Follow `docs/ai/IMPLEMENTATION_GUIDE.md`. Distinguish source review, build, host, device and game evidence. Never report CPU/mock/QNN CPU, XLSR, CAS or bilinear as FSR4 on HTP. Unknown measurements are unknown, not zero or pass. A skipped test is not a passed test.

Known audit defects remain open until their R batch has implementation and regression evidence. Do not infer that a historical complete batch has no defects. The local SDK, weights and venvs are ignored assets, not available automatically on a fresh clone; verify explicit paths rather than relying on personal cache locations.

- Target intent: Odin 3 / Snapdragon 8 Elite / Armada OS; actual image, SoC, GPU, HTP and PE/ELF loading chain remain unverified.
- Android ARM64 and Linux glibc ARM64 are not interchangeable. W8A8 describes weight/activation bitwidth; record signedness, scale/offset, granularity and external I/O separately.
- Same-frame baseline: one in-flight request per context; reject stale or mismatched output. Timeout/failure/close does not prove backend quiescence or permit early buffer release. Commit history only after valid consumption acknowledgement.
- Real-model CPU work uses identified, integrity-checked material. Public forks/mirrors may be used for personal experiments with necessary source/version/hash/notices; do not add a separate license-audit batch or redistribute external model/SDK/firmware/game assets.
- Keep large/private artifacts in ignored directories. Do not collect credentials, change system permissions/firmware, run unlock scripts or install Linux/WSL as incidental work.

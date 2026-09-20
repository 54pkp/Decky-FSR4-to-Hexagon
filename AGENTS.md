# Repository guidance

## Current scope and reading

Develop on Windows without an attached Odin 3. The current phase is theory, offline tools and CPU validation, not a functioning FSR4 upscaler. Do not require Linux, WSL, QNN, a game or a device to start a host package. Real model execution requires legitimate, identified assets; synthetic inputs never prove FSR4 equivalence.

Start with `docs/STATUS.md` and `docs/ai/MULTI_AGENT_WORKFLOW.md`, then relevant source/tests. Read contract sections and `docs/roadmap/` only when needed. `docs/reference/`, completed `FIRST_BATCH.md` and old validation reports are reference evidence, not a queue to restart. Current lightweight rules replace old per-milestone paperwork requirements.

## Coordination

- Coordinator and user communication: GPT-5.6 Sol / medium. Development pool: up to three GPT-5.6 Sol / medium workers. Batch reviewer: GPT-6 Astra / medium. Use Astra / xhigh only for a specific architecture decision; never default to Ultra.
- Delegate only independent bounded packages. Small changes may use one worker or the coordinator; do not invent work to fill slots. Give each worker its goal, allowed paths and checks in a short message, not full chat history.
- Verify selected model/effort through role configuration or explicit supported spawn parameters. Configuration files do not switch the current conversation's model.
- Only the integrator stages, commits, merges, pushes and updates shared status/contracts. Workers own non-overlapping paths, return concise evidence and never recursively delegate. Preserve existing changes.
- Review substantive code/contract batches against the actual frozen diff, including new files, plus relevant source/tests. Fixes require affected checks and focused re-review. Formatting/link-only edits need no Astra pass.

## Work and evidence

- Pick one small behavior from the active queue in STATUS (currently P1-P9; H1-H4 are complete). Read docs/roadmap/HOST_PREPARATION.md for its prerequisites and acceptance. Single-run mode finishes one batch, including fixes and handoff, then stops. Goal mode continues only the frozen active host-phase queue; completing it does not complete the hardware roadmap.
- Use one short batch record plus STATUS. Separate work-card, review-packet and handoff files are optional. Record goal, base revision/diff identity, actual environment/backend, commands/exit codes, result, review, gaps and next action. Hash external inputs/generated numerical artifacts when relevant, not every Markdown file.
- Follow `docs/ai/IMPLEMENTATION_GUIDE.md` for evidence definitions. Never report source inspection, build, CPU/mock, XLSR, CAS or bilinear results as FSR4 on HTP, device or game validation. Keep unavailable measurements unknown, not zero or pass.
- Keep schema, producer, consumer and tests consistent. Record routine choices in the batch note; create an ADR only for a consequential ABI, synchronization or licensing decision.
- Preserve history and upstream notices. Do not redistribute unverified model/SDK/firmware/game assets, collect credentials, modify firmware/system permissions or run unlock scripts as incidental work.

## Technical boundaries to retain

- Future target: AYN Odin 3, Snapdragon 8 Elite, Armada OS; actual image, SoC, graphics and PE/ELF loading chain remain unverified.
- Android ARM64 and Linux glibc ARM64 libraries are not interchangeable. NPU network execution still requires GPU preprocessing, temporal state, reconstruction and synchronization.
- Baseline: same-frame, one request in flight per context. Reject stale/mismatched output. Timeout does not prove work stopped or make in-flight buffers safe to release.
- Device/game tests remain `not_run` during this phase. Do not manufacture Linux evidence on Windows or treat skipped tests as passed.
- Keep private/large artifacts in ignored directories. Public Chinese/English READMEs must agree with actual status.

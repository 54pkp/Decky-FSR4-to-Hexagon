# Repository guidance for coding agents

These instructions apply to this repository. Follow the user's current task and preserve existing work. This repository contains early M0 host tooling and documentation, not a functioning upscaler.

## Read only the context needed

- Coordinator: read `docs/STATUS.md`, `docs/ai/MULTI_AGENT_WORKFLOW.md`, and the assigned milestone/work card. `docs/ai/FIRST_BATCH.md` is the completed first M0 host batch; do not restart it unless a specific regression requires it.
- Worker: read the assigned work-package card, relevant contract/milestone sections and necessary source. Do not ingest both READMEs, all milestones or the research archive by default.
- Reviewer: read the review packet, exact diff, relevant source and test evidence. A summary alone cannot establish correctness.
- Use `docs/ai/IMPLEMENTATION_GUIDE.md` for evidence definitions and `docs/reference/` only for relevant historical source claims. Expand context with targeted searches when correctness requires it.

The implementation guides are in Chinese; identifiers and interfaces remain language-neutral. Follow the user's language preference in reports.

## Model roles and coordination

- Default coordinator and day-to-day user communication: GPT-5.6 Sol, medium. Development workers: GPT-5.6 Sol, medium. Batch review: GPT-6 Astra, medium; architecture decisions: Astra, xhigh. Ultra is an explicit escalation, not a routine default. Respect the user's explicit selection.
- Project defaults and custom roles live in `.codex/`; verify the host actually applies them. A prompt mentioning a model does not switch models. If role selection is unavailable, use explicit supported model/effort parameters or report the limitation.
- Default to three independent development workers, then one focused review. Give each worker a bounded, non-overlapping package. If only one or two write packages are safe, use the remaining worker for a bounded read-only validation or compatibility task instead of creating conflicting edits. Worker/reviewer agents do not recursively delegate.
- Give workers small self-contained cards, not full chat history. Return concise results and evidence paths. After repeated attempts without new evidence, escalate a specific decision instead of repeating broad exploration.
- Shared checkout: one integrator owns Git index/commits and shared status/contracts/build entrypoints. Workers edit only assigned non-overlapping paths and their unique reports; no stage/commit/branch/merge/push or repository-wide formatting.
- Isolated worktrees may allow worker commits when explicitly assigned. Integrate serially and test the combined result. Only one owner runs target-device operations at a time.
- Freeze the review revision and include new/untracked files. Fixes invalidate review of affected code; recheck the changed scope. Only the integrator updates `docs/STATUS.md` after checking evidence.

## Work within the assigned milestone

- Split implementation into a small, verifiable work package. Do not implement the entire roadmap in one pass.
- Check prerequisite evidence before dependent hardware/game work. Missing hardware does not prevent useful host-side work, but must remain an explicit validation gap.
- Draft interfaces and suggested filenames are proposals, not existing APIs or executables. Inspect the working tree before using them.
- Keep changes in shared contracts, producers, consumers, tests, and examples consistent. Record significant design changes in an ADR using `docs/templates/adr.md`.
- Preserve independent work and other mods/configuration. Default branch names for new development branches use `codex/`, unless the user specifies otherwise.

## Non-negotiable technical distinctions

- AYN Odin 3/Armada is the first target, not a tested platform here. Record the actual image, SoC identity, graphics stack, and PE/ELF architecture.
- Android ARM64 libraries are not interchangeable with Linux glibc ARM64 libraries. Match proxy ABI to the actual Wine/Proton/FEX loading chain.
- The NPU executes the adapted neural network; GPU preprocessing, temporal state, reconstruction, and synchronization remain necessary.
- XLSR, CAS, bilinear output, a mock backend, and QNN CPU execution must never be reported as FSR4 on HTP.
- Source inspection, compilation, host tests, device tests, and game tests are separate evidence levels. Never invent measurements or mark unrun tests as passing.
- Baseline M4 is same-frame, one request in flight per context. Reject stale/mismatched outputs. A timeout does not prove that GPU/NPU work has stopped or that its buffers can be freed.
- Do not silently modify firmware, unlock the device, reset the DSP, or change system-wide permissions as an incidental step. Diagnose the actual failure and keep those operations outside ordinary runtime work packages.
- No unverified redistribution of models, SDK runtime libraries, firmware, or game files. Retain upstream notices and source provenance.

## Validation and completion

- Run checks appropriate to the change. Test real boundaries and failure behavior, not merely mocks that reproduce the implementation.
- Use work-package/review-packet templates plus the report/handoff templates in `docs/templates/`. Link existing evidence rather than duplicating logs. Record exact commands, exit codes, environment, revision, artifact hashes, and what was not run.
- Keep large raw artifacts, SDKs, model files, and game captures in ignored locations. Commit concise publishable reports; do not commit credentials or identifying device data unnecessarily.
- Update `docs/STATUS.md` only to the level supported by evidence. Documentation completion is not milestone implementation completion.
- Public README claims must match the status and evidence. Keep the public Chinese/English pages aligned.
- Archived research should retain its date and original conclusions; record new findings in current reports/ADRs instead of silently rewriting history.

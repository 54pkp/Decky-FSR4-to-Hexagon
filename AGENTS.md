# Repository guidance for coding agents

These instructions apply to this repository. Follow the user's current task and preserve existing work. This repository currently contains documentation, not a functioning upscaler.

## Read first

1. `README.md` or `README.en.md`: public scope and project status.
2. `docs/STATUS.md`: actual milestone implementation and validation state.
3. `docs/ai/IMPLEMENTATION_GUIDE.md`: work-package and handoff workflow.
4. `docs/architecture/CONTRACTS.md`: shared draft contracts.
5. The assigned document in `docs/roadmap/`: prerequisites, steps, and acceptance gates.
6. Relevant sections of `docs/reference/`: historical source evidence, not a current implementation claim.

The implementation guides are in Chinese; identifiers and interfaces remain language-neutral. Follow the user's language preference in reports.

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
- Use the report and handoff templates in `docs/templates/`. Record exact commands, exit codes, environment, commit, artifact hashes, and what was not run.
- Keep large raw artifacts, SDKs, model files, and game captures in ignored locations. Commit concise publishable reports; do not commit credentials or identifying device data unnecessarily.
- Update `docs/STATUS.md` only to the level supported by evidence. Documentation completion is not milestone implementation completion.
- Public README claims must match the status and evidence. Keep the public Chinese/English pages aligned.
- Archived research should retain its date and original conclusions; record new findings in current reports/ADRs instead of silently rewriting history.

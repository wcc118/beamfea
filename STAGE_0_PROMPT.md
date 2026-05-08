# Stage 0 hand-off prompt for Qwen3-Coder

Paste the contents of this file into Qwen3-Coder as the first prompt of the project. The skeleton is already in place; this prompt directs the LLM to *complete* stage 0 (mainly: fill in the remaining V2–V9 validation JSONs).

---

## Context to load before responding

Read in full, in this order:
1. `foundation_spec.md` (repo root)
2. `beamfea/conventions.md`
3. `tests/validation/README.md`
4. `tests/validation/V1_model.json` and `tests/validation/V1_expected.json` (worked examples)

Do not work from memory or summary. The full spec is short enough to keep in context for every task on this project.

## Task

Complete Stage 0 by generating the V2 through V9 (and V8b) validation case files, following the V1 worked example exactly:
- `tests/validation/V{N}_model.json`
- `tests/validation/V{N}_expected.json`

For each case, derive the expected values from the closed-form formulas listed in `foundation_spec.md` §11. Show your arithmetic in the response so I can spot-check before committing.

## Constraints

1. Do not implement any solver code, schema code, or assembly code. Stage 0 is data and structure only.
2. Use E = 10.3e6 psi, A = 1.0 in², Iz = 1.0 in⁴ unless a specific case calls for an override.
3. Match the JSON schema of V1 exactly. Pretty-print with 2-space indent.
4. For composite cases (V7 L-frame, V9 inclined element), state assumptions and hand-compute end forces; do not just write "TBD".
5. Sign conventions per `conventions.md`. If you are unsure of a sign for an expected reaction or end force, flag it explicitly in the `note` field of the check rather than guessing.

## Output

After generating files, print:
1. The list of files created
2. The arithmetic for each case's expected values
3. Any sign-convention checks you want me to verify before they are locked in

# AGENTS.md

## Standing Rules — Apply To Every Task

1. **No test mutation without permission.** You may add new tests. You may not remove, rename, restructure, or narrow the scope of existing tests, including parametrized loops. If an existing test fails, the failure is information — fix the code under test or fix the expected data, do not change the test structure to avoid the failure.

2. **No uncertainty masking.** If you cannot derive an expected value from first principles or a cited source, stop and write the question to STATUS.md. Do not commit values labeled "approximation," "actually," "check implementation," or any similar uncertainty markers. The phrase "I don't know how to derive this" is a valid output and stops the task cleanly.

3. **Python is the source of truth for arithmetic.** All numeric expected values in test files must be produced by evaluating a Python expression, not by hand calculation. Put the formula in a `formula` field as a string, evaluate it in Python, put the resulting value in the `value` field. The two must match by construction.

4. **Stage scope is binding.** Do not modify files outside the stage's declared scope. Do not "improve" code from earlier stages unless explicitly asked. Do not implement future stages partially.

5. **Cite, don't recall.** Stiffness matrices, shape functions, and FEA formulations must cite Cook 4th ed. or McGuire-Gallagher-Ziemer 2nd ed. with section/equation reference in the docstring. No formulas from training memory.

6. **Run pytest before reporting done.** "Done" means you ran pytest and it produced the result the stage acceptance criteria require. Paste the actual pytest output, do not summarize it.

## Quick ramp-up

1. Read `foundation_spec.md` — the contract. Every decision is pinned here.
2. Read `beamfea/conventions.md` — sign conventions and DOF ordering.
3. Check the current stage in `STAGE_0_PROMPT.md` before writing code.

**Do not proceed without the spec in context. Do not invent formulations.**

---

## Command reference

- `pip install -e ".[dev]"` — install package + dev deps (pytest, ruff, httpx, matplotlib)
- `pytest` — runs validation suite against `tests/validation/`
- `beamfea` — launches FastAPI server on **port 1337** (not 8000)

---

## Architecture

- **Data model:** Pydantic v2 schemas in `beamfea/schema.py`
- **Element:** stiffness matrix, transformation, end-release condensation (`beamfea/element.py`)
- **Assembly:** global K/F assembly via scipy.sparse CSR (`beamfea/assembly.py`)
- **Solver:** partitioned matrix solve with BC handling (`beamfea/solver.py`)
- **Postprocess:** end forces, SMD diagrams, GPF balance, stress (`beamfea/postprocess.py`)
- **API:** FastAPI server on port 1337 (`beamfea/api.py`)
- **I/O:** JSON load/save with schema versioning (`beamfea/io.py`)

---

## Critical conventions

- **DOF order:** [u, v, θz] per node; gdof = 3·node_id + k (zero-indexed nodes)
- **Sign convention:** tension +N, clockwise shear +V, sagging +M (cite `conventions.md` in every numerical module)
- **Units:** inch, lb, psi (no conversions in v1)
- **Textbook references:** Cook 4th ed. or McGuire-Gallagher-Ziemer 2nd ed. — cite in docstrings for all stiffness/shape-function formulas

---

## Validation suite

- **Location:** `tests/validation/`
- **Run:** `pytest` parametrizes over all V{1–9,8b} pairs
- **Format:** `V{N}_model.json` + `V{N}_expected.json`
- **Tolerance:** 0.01% relative error on all checks

---

## Build stages (stage N+1 only after N passes)

| Stage | Deliverable | Acceptance test |
|---|---|---|
| 0 | Skeleton, conventions, validation JSONs | CI green on empty failing tests |
| 1 | Pydantic data model | round-trip JSON identical |
| 2 | Element stiffness + assembly | hand-computed K matches for 0°, 90°, 45° |
| 3 | Loads + BCs | partition + nodal force assembly tested |
| 4 | Linear static solver | V1–V6 closed-form ≤ 0.01% error |
| 5 | Post-processing | SMD plots match textbooks; GPF residuals at 1e-6 |
| 6 | FastAPI on port 1337 | full pipeline drivable from curl |
| 7 | GUI | build cantilever-with-tip-load entirely in browser |
| 8 | File I/O + polish | save/load JSON, CSV results export |

---

## LLM-collaboration rules

1. Every numerical function gets a unit test with closed-form/hand-computed expected value before marking complete.
2. Stiffness matrices and shape-function integrals cite Cook or McGuire-Gallagher-Ziemer in docstrings — no formulas from memory.
3. Every module computing or displaying internal forces references `conventions.md §2` in its docstring header.
4. No silent unit conversions. No silent sign flips. Named transformations only.

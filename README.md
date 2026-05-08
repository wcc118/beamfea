# beamfea

Planar 2D beam-element finite element analysis. Pre-process, solve linear static, post-process deflections / reactions / shear-moment-axial diagrams / grid point force balance.

**Status:** stage 0 — skeleton only. No solver implemented. See `foundation_spec.md` for the full plan.

## Quick start (after implementation)

```bash
pip install -e ".[dev]"
pytest                    # runs validation suite
beamfea                   # launches GUI at http://localhost:1337
```

## For LLM agents working on this codebase

Read these in order, every session:
1. `foundation_spec.md` — the contract. Every decision is pinned here.
2. `beamfea/conventions.md` — sign conventions and DOF ordering. Cited from every numerical module.
3. The current stage's existing source files.

Do not proceed without the spec in context. Do not invent formulations. Cite Cook 4th ed. or McGuire-Gallagher-Ziemer 2nd ed. in docstrings for every stiffness / shape-function expression.

## Build stages

| Stage | Deliverable | Acceptance test |
|---|---|---|
| 0 | Skeleton, conventions, validation JSONs | CI green on empty failing tests; spec reviewed |
| 1 | Pydantic data model | round-trip JSON serialization identical |
| 2 | Element stiffness + assembly | hand-computed K matches for 0°, 90°, 45° |
| 3 | Loads + BCs | partition + nodal force assembly tested |
| 4 | Linear static solver | V1–V6 closed-form cases ≤ 0.01% error |
| 5 | Post-processing | SMD plots match textbooks; GPF residuals at 1e-6 |
| 6 | FastAPI on port 1337 | full pipeline drivable from curl |
| 7 | GUI | build cantilever-with-tip-load entirely in browser |
| 8 | File I/O + polish | save/load JSON, CSV results export |

Do not start stage N+1 until stage N's acceptance test passes.

## Port

The FastAPI server runs on **1337** (not 8000 — that's reserved on the target machine).

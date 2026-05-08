# Validation Suite

Closed-form benchmark cases. Each case is a pair:
- `V{N}_model.json` — input model (Pydantic Model schema, schema_version 1.0)
- `V{N}_expected.json` — expected results with quantities to check

`tests/test_solver.py::test_validation_case` parametrizes over every pair found here.

## Cases (per foundation_spec.md §11)

| Case | Description |
|---|---|
| V1 | Cantilever, L=120 in, fixed at i, P=1000 lb at j (−Y direction) |
| V2 | Cantilever, L=120 in, fixed at i, w=10 lb/in (−Y) |
| V3 | Simply supported, L=240 in, P=2000 lb at center |
| V4 | Simply supported, L=240 in, w=15 lb/in |
| V5 | Fixed-fixed, L=240 in, w=20 lb/in |
| V6 | Propped cantilever, L=240 in, w=10 lb/in |
| V7 | L-frame, two elements at 90°, tip load |
| V8 | Element with single Mz release |
| V8b | Element with both Mz releases (axial-only) |
| V9 | Inclined element at 30°, axial+transverse load |

Defaults unless overridden: E = 10.3e6 psi, A = 1.0 in², Iz = 1.0 in⁴.

## Expected-results JSON schema

```json
{
  "case_id": "V1",
  "tolerance_relative": 1e-4,
  "checks": [
    {"quantity": "displacement", "node_id": 1, "dof": "v", "value": -5.5890e+01},
    {"quantity": "reaction",     "node_id": 0, "dof": "v", "value":  1.0000e+03},
    {"quantity": "reaction",     "node_id": 0, "dof": "rz", "value":  1.2000e+05},
    {"quantity": "end_force",    "element_id": 0, "end": "i", "component": "M", "value":  1.2000e+05}
  ]
}
```

## Stage 0 task for the LLM

Generate all 10 model JSONs and all 10 expected-results JSONs. For each, compute the closed-form expected values **by hand** (show the arithmetic in the commit message), do not call into a solver — these files are the ground truth.

For V1: δ_tip = PL³/(3EI) = 1000 · 120³ / (3 · 10.3e6 · 1.0) = 55.890 in (negative in Y). Yes, the deflection is enormous because A=Iz=1.0 is unrealistic — that is intentional, the units check out, and this is what unit tests are for.

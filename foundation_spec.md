# Beam FEA Tool — Foundation Specification v1.0

This document is the contract. It is loaded into context for every code-generation task. Every numerical routine, every diagram, every API endpoint must conform to what is written here. When in doubt, this document wins.

---

## 1. Units (consistent set, enforced)

All inputs, internal computations, and outputs use:

| Quantity | Unit | Symbol |
|---|---|---|
| Length | inch | in |
| Force | pound | lb |
| Moment | pound-inch | lb·in |
| Stress, modulus | pounds per square inch | psi |
| Area | square inch | in² |
| Second moment of area | inch⁴ | in⁴ |
| Distributed load (transverse) | pounds per inch | lb/in |
| Distributed load (axial) | pounds per inch | lb/in |

The model layer rejects any input outside this set. No conversion logic in v1.

Default material: aluminum, E = 10.3e6 psi, ν = 0.33.

---

## 2. Coordinate system & sign conventions

**Global axes:** X right, Y up, Z out of the page (right-handed). All rotations follow right-hand rule about Z, so positive θz is counter-clockwise when viewed on screen.

**Element local axes:** for an element from node i to node j, local x̂ runs i→j. Local ŷ is local x̂ rotated 90° CCW. Local ẑ = global Z (out of page).

**Internal force sign convention** (this is what gets plotted):
- **Axial N:** positive in tension (element pulled apart).
- **Shear V:** positive when it rotates the element segment clockwise. Equivalently, on a cut face whose outward normal is +local-x, positive V points in +local-y.
- **Moment M:** sagging-positive. On a cut face whose outward normal is +local-x, positive M is a vector in +local-z (CCW when viewed from +z), which produces tension on the +local-y face — i.e., the "bottom" fiber if the beam is drawn left-to-right with local-y up.

These three are non-negotiable across the codebase. Any module computing or displaying internal forces cites this section in its docstring.

---

## 3. Degrees of freedom

3 DOF per node, ordered: **[u, v, θz]** = [translation X, translation Y, rotation about Z].

Global DOF index for node n, local dof k ∈ {0,1,2}: **gdof = 3·n + k**, with node IDs zero-indexed.

---

## 4. Element formulation

**Type:** Euler-Bernoulli planar frame element, 2 nodes, 6 DOF total. Order: [u_i, v_i, θz_i, u_j, v_j, θz_j].

**Per-element required properties:** length L (computed from node coords), elastic modulus E, cross-section area A, second moment Iz, optional end-releases (release_i_Mz: bool, release_j_Mz: bool).

**Local stiffness matrix** (no end releases), with α = EA/L, β = EI/L³:

```
K_local =
[  α      0         0       -α      0         0     ]
[  0    12β       6βL        0    -12β       6βL    ]
[  0    6βL     4βL²         0    -6βL     2βL²    ]
[ -α     0         0        α      0         0     ]
[  0   -12β      -6βL        0    12β      -6βL    ]
[  0    6βL     2βL²         0    -6βL     4βL²    ]
```

**Transformation:** standard 6×6 block-diagonal of two 3×3 rotation blocks using c = cos(θ), s = sin(θ) where θ is the angle of local x̂ from global X̂. K_global = Tᵀ · K_local · T.

**End releases:** when release_i_Mz or release_j_Mz is true, apply static condensation on the released rotational DOF *in local coordinates* before transformation. Standard textbook procedure (Cook 4th ed., §2.7, or McGuire-Gallagher-Ziemer Ch. 7); implement from the cited source, not from memory.

When both ends are released, the resulting element has only axial stiffness (becomes a truss bar). This is legal and silent — no warning, no error. Verify it falls out naturally from the condensation procedure.

---

## 5. Loads

**Nodal loads:** vector [Fx, Fy, Mz] applied at any node, accumulates additively into the global force vector at the node's DOFs.

**Element distributed loads (uniform only in v1):**
- w_axial: lb/in along local +x̂
- w_transverse: lb/in along local +ŷ

Converted to consistent nodal forces in local coordinates per Euler-Bernoulli shape functions:

```
Axial uniform w_a, length L:
  f_local_axial = [w_a·L/2, 0, 0, w_a·L/2, 0, 0]

Transverse uniform w_t, length L:
  f_local_trans = [0, w_t·L/2, w_t·L²/12, 0, w_t·L/2, -w_t·L²/12]
```

Sum, transform to global via Tᵀ, accumulate into global F.

The original distributed load values are *retained on the element* — needed in post-processing to recover the true internal force diagrams (which include the distributed-load contribution between nodes, not just the linear interpolation of end forces).

---

## 6. Boundary conditions

Per node, per DOF (u, v, θz independently): either free, or constrained to a prescribed value (zero or nonzero). Solver uses partitioned-matrix approach: split DOFs into free set F and constrained set C, solve K_FF · d_F = F_F − K_FC · d_C, recover reactions R_C = K_CF · d_F + K_CC · d_C − F_C_applied.

**GUI presets** (write equivalent NodalBC records into the model — no separate "preset" type stored):
- Pinned: u=0, v=0, θz free
- Fixed: u=0, v=0, θz=0
- Roller-X (allows X translation, blocks Y): v=0
- Roller-Y (allows Y translation, blocks X): u=0
- Custom: three independent checkboxes + value fields

---

## 7. Solver

Linear static. Assemble global K as scipy.sparse.csr_matrix. Solve with scipy.sparse.linalg.spsolve. Pre-solve checks:
- K_FF symmetry: assert ‖K−Kᵀ‖∞ < 1e-9·‖K‖∞
- No zero diagonal in K_FF (catches under-constrained models with a clean error message naming the offending DOF)

---

## 8. Post-processing — what gets computed

**Displacements:** full global d vector, reported per node as (u, v, θz).

**Reactions:** at every constrained DOF.

**Element end forces (local coordinates):** for each element,

    f_local = K_local · T · d_global_element − f_local_fixed_end

The subtraction of fixed-end forces is what makes the result represent *true internal forces* at the ends, accounting for distributed loads. These six numbers per element directly give axial, shear, moment at both ends.

**Internal force diagrams:** sampled at three points per element — i-end, midspan (centroid), j-end — using closed-form expressions:

```
For element with end forces (N_i, V_i, M_i) at the i-end and uniform loads w_a, w_t:
  N(x) = -N_i - w_a · x         (tension positive, x measured from i-end)
  V(x) =  V_i + w_t · x          (sign per §2)
  M(x) =  M_i + V_i·x + w_t·x²/2
```

Three-point sampling is sufficient for uniform loads (axial linear, shear linear, moment quadratic). Plot routine connects with appropriate curve order: straight line for N and V, parabola for M.

**Grid point force balance:** at each node, sum (a) all element end forces from elements connected to that node, transformed to global, (b) applied nodal loads, (c) reactions if constrained. Residual must be ≤ 1e-6 · max(|nodal force component|) for the model. Report per node.

**Combined stress per element** (max-magnitude fiber):
- σ_axial = N / A
- σ_bending,max = |M| · c / Iz where c = √(Iz/A) as a stand-in until section library lands. *Flag this in the UI as "approximate — exact c requires section geometry."*
- σ_combined = σ_axial ± σ_bending,max, reported at i-end, midspan, j-end.

**Reported maxima:** max |deflection| (location, value, direction), max |M|, max |V|, max |N|, max |σ_combined|, each with element ID and station.

---

## 9. Data model (Pydantic v2 schemas)

```
Node:        id: int, x: float, y: float
Material:    id: int, E: float, nu: float    (G = E/(2(1+nu)) computed; unused in EB but stored)
Element:     id: int, node_i: int, node_j: int, material_id: int,
             A: float, Iz: float,
             release_i_Mz: bool = False, release_j_Mz: bool = False
NodalBC:     node_id: int, dof: Literal["u","v","rz"], value: float
NodalLoad:   node_id: int, Fx: float = 0, Fy: float = 0, Mz: float = 0
ElementLoad: element_id: int, w_axial: float = 0, w_transverse: float = 0
Model:       name: str, nodes: List[Node], materials: List[Material],
             elements: List[Element], bcs: List[NodalBC],
             nodal_loads: List[NodalLoad], element_loads: List[ElementLoad]
```

---

## 10. JSON file format

Direct serialization of the `Model` Pydantic schema. Top-level key `"schema_version": "1.0"` for forward compatibility. Pretty-printed with 2-space indent. File extension `.beamfea.json`.

---

## 11. Validation suite (must pass before any release)

Each case has a JSON model file and an expected-results JSON; pytest loads, solves, asserts ≤ 0.01% relative error on the listed quantities.

E = 10.3e6 psi, A = 1.0 in², Iz = 1.0 in⁴ for all unless noted.

| Case | Geometry | Load | Check |
|---|---|---|---|
| V1 | Cantilever, L=120 in, fixed at i | P=1000 lb at j (−Y) | δ_tip = PL³/(3EI), R_y, M_fixed |
| V2 | Cantilever, L=120 in, fixed at i | w=10 lb/in (−Y) | δ_tip = wL⁴/(8EI), R_y, M_fixed, M(L/2) |
| V3 | Simply supported, L=240 in | P=2000 lb at center | δ_center = PL³/(48EI), M_center = PL/4 |
| V4 | Simply supported, L=240 in | w=15 lb/in | δ_center = 5wL⁴/(384EI), M_center = wL²/8 |
| V5 | Fixed-fixed, L=240 in | w=20 lb/in | M_ends = wL²/12, M_center = wL²/24 |
| V6 | Propped cantilever, L=240 in | w=10 lb/in | R_pin = 3wL/8, M_fixed = wL²/8 |
| V7 | L-frame, two elements at 90° | tip load | hand-checked end forces, GPF balance |
| V8 | Element with Mz release at one end | any | recovers simply-supported behavior |
| V8b | Both ends released, axial load only | P axial | δ = PL/(AE), zero transverse stiffness |
| V9 | Inclined element, 30° | axial+transverse load | tests transformation correctness |

---

## 12. GUI

Local FastAPI server, browser frontend at **http://localhost:1337**.

**Three panes:** left = model tree (collapsible nodes/elements/materials/BCs/loads with edit buttons); center = 2D canvas (SVG via D3, click-to-place nodes, click-two-nodes to create element, right-click node for BC/load modal); right = results pane (tabs: deflected shape, shear diagram, moment diagram, axial diagram, reactions table, GPF table, stress/maxima summary).

**Workflow:** modal — Build → Solve button → Results pane populates. Edit any input invalidates results; results pane greys out until next solve.

**Diagrams:** server renders Matplotlib PNGs and serves them; frontend just displays. Acceptable for v1, swap for Plotly later if interactive zoom on diagrams becomes desired.

---

## 13. Module layout

```
beamfea/
├── foundation_spec.md    # this file
├── pyproject.toml
├── README.md
├── beamfea/
│   ├── __init__.py
│   ├── conventions.md    # §2 of this doc, verbatim
│   ├── schema.py         # Pydantic models (§9)
│   ├── element.py        # local stiffness, transformation, end-release condensation
│   ├── loads.py          # consistent nodal force conversion
│   ├── assembly.py       # global K, F assembly
│   ├── solver.py         # BC partitioning, solve, reactions
│   ├── postprocess.py    # end forces, SMD sampling, GPF, stress, maxima
│   ├── io.py             # JSON load/save, schema versioning
│   ├── api.py            # FastAPI endpoints, port 1337
│   └── frontend/         # static HTML/JS/CSS
└── tests/
    ├── test_element.py
    ├── test_assembly.py
    ├── test_solver.py
    ├── test_postprocess.py
    └── validation/       # V1–V9 model + expected JSONs
```

---

## 14. LLM-collaboration rules (for Qwen3-Coder)

1. Every numerical function gets a unit test with a closed-form or hand-computed expected value *before* it's marked complete.
2. Element formulations, stiffness matrices, and shape-function integrals cite a textbook (Cook *Concepts and Applications of Finite Element Analysis* 4th ed., or McGuire/Gallagher/Ziemer *Matrix Structural Analysis* 2nd ed.) in the docstring. No formulas from training memory.
3. Every module computing or displaying internal forces references `conventions.md §2` in its docstring header.
4. No silent unit conversions. No silent sign flips. If a transformation is needed, it is named and visible.
5. Validation suite (§11) runs in CI on every commit. Red CI blocks merge.
6. The full `foundation_spec.md` is loaded into context for every code-generation task. Do not work from summary or memory.

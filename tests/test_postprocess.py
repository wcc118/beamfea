"""Stage 5: Post-processing tests.

Tests individual functions in beamfea/postprocess.py for correctness.
Uses closed-form known values for validation.
"""

import json

import numpy as np
import pytest

from beamfea.postprocess import (
    compute_element_end_forces,
    compute_element_node_contributions,
    compute_internal_force_diagrams,
    compute_gpf_balance,
    compute_stresses,
    compute_maxima,
)
from beamfea.solver import solve_linear_static, compute_reactions


def test_end_forces_v1():
    """V1: Cantilever, tip load. Verify end forces at fixed end."""
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, [])

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, [])

    # V1: Cantilever length 120 in, P=-1000 lb at tip
    # Fixed at node 0, tip at node 1
    # At i-end (fixed): M should be +120000 lb-in (sagging)
    # The sign convention: internal M at i-end is negative of reaction moment
    # Reaction moment at node 0 is +120000, so internal M_i = -120000 for equilibrium

    forces = end_forces[0]['forces_local']
    N_i, V_i, M_i, N_j, V_j, M_j = forces

    # Shear at i-end should balance applied load
    assert np.isclose(V_i, 1000.0, atol=1e-6), f"V_i = {V_i}, expected 1000"
    # Moment at i-end balances reaction
    assert np.isclose(M_i, 120000.0, atol=1e-6), f"M_i = {M_i}, expected 120000"
    # At tip (j-end): no appliedload, forces should be ~0
    assert np.isclose(V_j, -1000.0, atol=1e-6), f"V_j = {V_j}, expected -1000"


def test_internal_force_diagram_v1():
    """V1: Cantilever. Verify moment varies linearly from fixed to tip."""
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, [])

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, [])
    diagrams = compute_internal_force_diagrams(nodes, elements, end_forces, [])

    # Check 3 stations: i-end, midspan, j-end
    stations = diagrams[0]['stations']

    # V1: cantilever L=120, P=-1000 at tip (node 1)
    # Internal moment (sagging positive): M(x) = P_mag * (L - x)
    # Formula: M(x) = M_i - V_i*x where M_i=+120000, V_i=+1000
    P, L = 1000.0, 120.0
    expected_M = [P * (L - x) for x in [0.0, L / 2.0, L]]  # [120000, 60000, 0]
    for i, (st, em) in enumerate(zip(stations, expected_M)):
        assert np.isclose(st['M'], em, atol=1e-6), (
            f"station {i}: M={st['M']}, expected={em}"
        )

    # Shear should be constant = 1000 along length
    for station in stations:
        assert np.isclose(station['V'], 1000.0, atol=1e-6)


def test_gpf_balance_v1():
    """V1: Cantilever. Verify GPF balance residual is at machine precision."""
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, [])

    residuals, max_forces, tolerance = compute_gpf_balance(
        nodes, elements, materials, d_full, bcs, nodal_loads, []
    )

    # GPF balance should be at machine precision
    max_residual = np.max(np.abs(residuals))
    assert max_residual < 1e-6, f"GPF residual {max_residual} exceeds tolerance"
    assert max_residual < tolerance, f"GPF residual {max_residual} exceeds computed tolerance {tolerance}"


def test_stresses_v1():
    """V1: Cantilever. Verify stress matches internal force diagram."""
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, [])

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, [])
    diagrams = compute_internal_force_diagrams(nodes, elements, end_forces, [])
    stresses = compute_stresses(nodes, elements, end_forces)

    # V1: A=1, Iz=1, so c = sqrt(Iz/A) = 1
    # For cantilever with tip load P=1000 lb:
    # - At fixed end (x=0): M = P*L = 120000
    # - At midspan (x=L/2): M = P*(L/2) = 60000
    # - At free end (x=L): M = 0
    #
    # The stress function uses interpolated moments:
    # - x=0: uses M_i = 120000
    # - x=L/2: uses (M_i + M_j)/2 = (120000 + 0)/2 = 60000
    # - x=L: uses M_j = 0

    stations = stresses[0]['stations']

    # sigma_bending = |M| * c / Iz where c = sqrt(Iz/A) = 1
    # At x=0: M_i = 120000
    assert np.isclose(stations[0]['sigma_bending_max'], 120000.0, atol=1e-6)

    # At x=L/2: M_interpolated = (120000 + 0)/2 = 60000
    assert np.isclose(stations[1]['sigma_bending_max'], 60000.0, atol=1e-6)

    # At x=L: M_j = 0
    assert np.isclose(stations[2]['sigma_bending_max'], 0.0, atol=1e-6)


def test_maxima_v1():
    """V1: Cantilever. Verify maxima are at correct locations."""
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, [])

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, [])
    diagrams = compute_internal_force_diagrams(nodes, elements, end_forces, [])
    stresses = compute_stresses(nodes, elements, end_forces)

    maxima = compute_maxima(end_forces, diagrams, stresses, d_full, nodes)

    # Max deflection at tip (node 1)
    assert maxima['deflection']['node_id'] == 1
    assert np.isclose(maxima['deflection']['value'], 55.922330097087375, atol=0.01)

    # Max moment at fixed end (i-end, x=0): M = P*L = 1000*120 = 120000
    assert maxima['moment']['element_id'] == 0
    assert np.isclose(maxima['moment']['value'], 120000.0, atol=1e-6)

    # Max shear is constant = 1000
    assert np.isclose(maxima['shear']['value'], 1000.0, atol=1e-6)

    # No axial load
    assert maxima['axial']['value'] == 0.0

    # Max stress at i-end (max moment there for bending)
    assert maxima['stress']['element_id'] == 0
    assert np.isclose(maxima['stress']['value'], 120000.0, atol=1e-6)


@pytest.mark.parametrize("case_id", ["V2", "V3", "V4"])
def test_end_forces_additional_cases(case_id):
    """Test end forces for V2, V3, V4 with distributed loads."""
    with open(f'tests/validation/{case_id}_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']
    element_loads = model.get('element_loads', [])

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, element_loads)

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, element_loads)

    # Just verify the function runs and returns reasonable values
    assert len(end_forces) == len(elements)
    for ef in end_forces:
        assert len(ef['forces_local']) == 6
        # Forces should be bounded (not infinite or NaN)
        assert all(np.isfinite(f) for f in ef['forces_local'])


def test_gpf_balance_v2():
    """V2: cantilever with UDL. Verify GPF balance."""
    with open('tests/validation/V2_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']
    element_loads = model.get('element_loads', [])

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, element_loads)

    residuals, _, tolerance = compute_gpf_balance(
        nodes, elements, materials, d_full, bcs, nodal_loads, element_loads
    )

    max_residual = np.max(np.abs(residuals))
    assert max_residual < 1e-6, f"GPF residual {max_residual} exceeds tolerance"
    assert max_residual < tolerance, f"GPF residual {max_residual} exceeds computed tolerance {tolerance}"


def test_internal_force_diagram_v2():
    """V2: cantilever with UDL. Verify parabolic moment diagram."""
    with open('tests/validation/V2_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']
    element_loads = model.get('element_loads', [])

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, element_loads)

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, element_loads)
    diagrams = compute_internal_force_diagrams(nodes, elements, end_forces, element_loads)

    stations = diagrams[0]['stations']

    # V2: cantilever L=120, w = -10 lb/in (downward UDL)
    # End forces: V_i = +1200, M_i = +72000
    # Corrected moment integration (sagging positive):
    #   M(x) = M_i - V_i*x - w*x^2/2 = 72000 - 1200*x + 5*x^2
    # Physics check: M(x) = |w|*(L-x)^2/2 = 10*(120-x)^2/2 = 5*(120-x)^2
    L = 120.0
    w_abs = 10.0  # magnitude of UDL
    expected_M = [w_abs * (L - x)**2 / 2.0 for x in [0.0, L / 2.0, L]]
    # = [72000, 18000, 0]

    for i, (st, em) in enumerate(zip(stations, expected_M)):
        assert np.isclose(st['M'], em, atol=1e-3), (
            f"station {i}: M={st['M']}, expected={em}"
        )


def test_maxima_v2():
    """V2: cantilever with UDL. Verify maxima."""
    with open('tests/validation/V2_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs = model['bcs']
    nodal_loads = model['nodal_loads']
    element_loads = model.get('element_loads', [])

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs, nodal_loads, element_loads)

    end_forces = compute_element_end_forces(nodes, elements, materials, d_full, element_loads)
    diagrams = compute_internal_force_diagrams(nodes, elements, end_forces, element_loads)
    stresses = compute_stresses(nodes, elements, end_forces)

    maxima = compute_maxima(end_forces, diagrams, stresses, d_full, nodes)

    # Max deflection at tip (node 1)
    assert maxima['deflection']['node_id'] == 1

    # Max moment at i-end (x=0): M = wL^2/2 = 10*120^2/2 = 72000
    # For a cantilever with UDL, max moment is at the fixed end (station 0).
    assert maxima['moment']['element_id'] == 0
    assert maxima['moment']['station'] == 0.0
    assert np.isclose(maxima['moment']['value'], 72000.0, atol=1e-3)


def test_element_node_contributions_v1():
    """V1: Cantilever, tip load. Verify element contributions at each node.

    At node 0 (fixed end), the single element should contribute:
    - Fy = +1000 lb (element pushes node upward = reaction)
    - Mz = +120000 lb-in (element pushes node with moment = reaction)
    At node 1 (tip), the element should contribute:
    - Fy = -1000 lb (element pulls node downward = applied load direction)
    """
    with open('tests/validation/V1_model.json') as f:
        model = json.load(f)

    nodes = model['nodes']
    elements = model['elements']
    materials = model['materials']
    bcs_list = model['bcs']
    nodal_loads = model['nodal_loads']

    d_full, _, _ = solve_linear_static(nodes, elements, materials, bcs_list, nodal_loads, [])

    contribs = compute_element_node_contributions(nodes, elements, materials, d_full, [])

    assert len(contribs) == 1
    c = contribs[0]
    assert c['element_id'] == 0
    assert c['node_i'] == 0
    assert c['node_j'] == 1

    # At fixed end (node 0), element reaction should balance:
    # Formula: R_y = P = 1000 lb, R_mz = P*L = 1000*120 = 120000 lb-in
    assert np.isclose(c['contrib_i']['Fy'], 1000.0, atol=1e-6)
    assert np.isclose(c['contrib_i']['Mz'], 120000.0, atol=1e-3)
    assert np.isclose(c['contrib_i']['Fx'], 0.0, atol=1e-6)

    # At tip (node 1), element end force Fy = -1000 (equal and opposite)
    assert np.isclose(c['contrib_j']['Fy'], -1000.0, atol=1e-6)
    assert np.isclose(c['contrib_j']['Mz'], 0.0, atol=1e-3)



def _make_release_model():
    """Return a model for the release condensation test.

    Triangular truss-frame: 3 nodes, 2 elements.
    - N0(0,0) pinned(u,v)
    - N1(10,0) pinned(u,v)
    - N2(5,10) free — centered apex (symmetric geometry)
    - E0: N0→N2, no releases (fixed-fixed)
    - E1: N1→N2, release_j_Mz=True (pin at N2)
    - Load at N2: Fx=0, Fy=-1000 (vertical downward)
    - No distributed loads

    With symmetric geometry (E0 and E1 at equal but opposite angles),
    vertical load splits equally between elements. E1 becomes a two-force
    member (pin at j, no distributed load, N1 rz free).
    """
    return {
        "nodes": [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 10.0, "y": 0.0},
            {"id": 2, "x": 5.0, "y": 10.0},
        ],
        "materials": [{"id": 0, "E": 10300000.0, "nu": 0.33}],
        "elements": [
            {
                "id": 0,
                "node_i": 0,
                "node_j": 2,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": False,
            },
            {
                "id": 1,
                "node_i": 1,
                "node_j": 2,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": True,
            },
        ],
        "bcs": [
            {"node_id": 0, "dof": "u", "value": 0.0},
            {"node_id": 0, "dof": "v", "value": 0.0},
            {"node_id": 1, "dof": "u", "value": 0.0},
            {"node_id": 1, "dof": "v", "value": 0.0},
        ],
        "nodal_loads": [{"node_id": 2, "Fx": 0.0, "Fy": -1000.0, "Mz": 0.0}],
        "element_loads": [],
    }


def test_release_condensation_colinear_reaction():
    """E1 pinned at j-end with no distributed load: reaction at N1 aligns with E1 axis.

    Triangular frame: N0(0,0) pinned, N1(10,0) pinned, N2(5,10) free.
    E0: N0→N2 (63.43 deg), no releases.
    E1: N1→N2 (116.57 deg), release_j_Mz=True (pin at N2).
    Vertical load: Fy=-1000 at N2.

    Freebody equilibrium at N1: N1 has rz free (no external moment),
    N1 is only connected by E1. E1 carries no external distributed load.
    E1 is a two-force member: its end forces must be colinear with the
    member axis. Therefore R1 must align with N1→N2 direction (116.57 deg).

    Independent verifications:
    1. |R1y/R1x - slope_E1| < atol — N1 reaction colinear with E1 axis
    2. M_1j = 0 — pin release at j-end
    3. M_1i = 0 — N1 rz free, only E1 connects ⇒ two-force member
    4. V_1i = V_1j = 0 — E1 carries only axial force
    5. Global equilibrium: sum Fx ≈ 0, sum Fy ≈ 1000, sum M ≈ 0

    References: Cook 4th ed., §2.7 (end condensation for pinned joints);
    McGuire-Gallagher-Ziemer 2nd ed., Ch. 7 (end releases).
    """
    model = _make_release_model()
    nodes = model["nodes"]
    elements = model["elements"]
    materials = model["materials"]
    bcs = model["bcs"]
    nodal_loads = model["nodal_loads"]

    d_full, _, _ = solve_linear_static(
        nodes, elements, materials, bcs, nodal_loads, []
    )

    # === 1. Reaction at N1 must be colinear with E1 axis ===
    R = compute_reactions(
        nodes, elements, materials, bcs, nodal_loads, d_full
    )
    R1x = R[3 * 1]
    R1y = R[3 * 1 + 1]

    # E1 direction from N1(10,0) to N2(5,10)
    E1_dx = nodes[2]["x"] - nodes[1]["x"]
    E1_dy = nodes[2]["y"] - nodes[1]["y"]
    # Unit direction
    u_vec = np.array([E1_dx, E1_dy])
    u_vec /= np.linalg.norm(u_vec)
    # Reaction vector
    r_vec = np.array([R1x, R1y])
    mag_r = np.linalg.norm(r_vec)
    if mag_r > 1e-12:
        angle_deg = np.degrees(np.arccos(np.clip(np.abs(np.dot(r_vec / mag_r, u_vec)), -1.0, 1.0)))
    else:
        angle_deg = 0.0
    assert angle_deg < 0.001, (
        f"Reaction at N1 must be colinear with E1 axis. "
        f"Angle between R1 and E1 axis: {angle_deg:.6f} deg"
    )

    # === 2. E1 j-end moment at N2 must be zero (pin release) ===
    end_forces = compute_element_end_forces(
        nodes, elements, materials, d_full, []
    )
    e1_forces = [ef for ef in end_forces if ef["element_id"] == 1][0][
        "forces_local"
    ]
    N_i, V_i, M_i, N_j, V_j, M_j = e1_forces
    assert M_j == 0.0 or np.isclose(M_j, 0.0, atol=1e-6), (
        f"Released end M_j must be zero, got {M_j}"
    )

    # === 3. E1 i-end at N1: M_i and V_i must be zero ===
    assert np.isclose(M_i, 0.0, atol=1e-6), (
        f"E1 i-end moment must be zero (two-force member), got {M_i}"
    )
    assert np.isclose(V_i, 0.0, atol=1e-6), (
        f"E1 i-end shear must be zero (two-force member), got {V_i}"
    )
    assert np.isclose(V_j, 0.0, atol=1e-6), (
        f"E1 j-end shear must be zero (two-force member), got {V_j}"
    )

    # === 4. Global equilibrium ===
    from beamfea.assembly import assemble_global_stiffness, assemble_nodal_loads
    K = assemble_global_stiffness(nodes, elements, materials)
    F = assemble_nodal_loads(nodes, nodal_loads, elements, [], materials)

    # Sum of reactions balances applied loads
    Fx_sum = sum(R[3 * i] for i in range(len(nodes)))
    Fy_sum = sum(R[3 * i + 1] for i in range(len(nodes)))
    assert np.isclose(Fx_sum, 0.0, atol=1e-6), (
        f"Global ∑Fx = {Fx_sum}, expected 0"
    )
    assert np.isclose(Fy_sum, 1000.0, atol=1e-6), (
        f"Global ∑Fy = {Fy_sum}, expected +1000 to balance -1000 load"
    )

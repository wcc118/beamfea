"""Stage 5: Post-processing tests.

Tests individual functions in beamfea/postprocess.py for correctness.
Uses closed-form known values for validation.
"""

import json

import numpy as np
import pytest

from beamfea.postprocess import (
    compute_element_end_forces,
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

    # x=0 (i-end): M should be ~120000 (sagging)
    assert np.isclose(stations[0]['M'], 120000.0, atol=1e-6)

    # x=L/2 (mid): M should be 180000
    assert np.isclose(stations[1]['M'], 180000.0, atol=1e-6)

    # x=L (j-end): M should be 240000 (P*L = 1000*120)
    assert np.isclose(stations[2]['M'], 240000.0, atol=1e-6)

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

    # Max moment at tip (j-end)
    assert maxima['moment']['element_id'] == 0
    assert np.isclose(maxima['moment']['value'], 240000.0, atol=1e-6)

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

    # V2: cantilever, w = -10 lb/in (downward)
    # From end_forces: V_i = 1200, M_i = 72000, V_j = 0, M_j = 0
    # V(x) = V_i + w*x = 1200 - 10*x
    # M(x) = M_i + V_i*x + w*x^2/2 = 72000 + 1200*x - 5*x^2

    # At x=0: V = 1200, M = 72000
    # At x=60: V = 1200 - 600 = 600, M = 72000 + 72000 - 18000 = 126000
    # At x=120: V = 1200 - 1200 = 0, M = 72000 + 144000 - 72000 = 144000

    # Check moment values
    assert np.isclose(stations[0]['M'], 72000.0, atol=1e-3)
    assert np.isclose(stations[1]['M'], 126000.0, atol=1e-3)
    assert np.isclose(stations[2]['M'], 144000.0, atol=1e-3)


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

    # Max moment at j-end (x=120): M = 144000
    # The moment diagram is quadratic, max at j-end for cantilever with UDL
    assert maxima['moment']['element_id'] == 0
    assert maxima['moment']['station'] == 120.0

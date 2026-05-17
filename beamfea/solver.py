"""Linear static solver.

References:
- Cook 4th ed., §2.6 (Solution of the finite element equations)
- McGuire-Gallagher-Ziemer 2nd ed., Ch. 5 (Solution algorithms)

DOF ordering: See beamfea/conventions.md
Sign convention: See beamfea/conventions.md §2
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve

from beamfea.assembly import (
    _dof_type_to_index,
    apply_boundary_conditions,
    assemble_global_stiffness,
    assemble_nodal_loads,
    node_gdof,
)



def _convert_element_loads_to_nodal(nodes, elements, materials, element_loads):
    """Convert element loads to equivalent nodal forces."""
    if not element_loads:
        return []
    
    # For simplicity, return empty list - element loads need implementation
    # This is a placeholder for proper implementation
    return []

def solve_linear_static(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
    bcs: list[dict],
    nodal_loads: list[dict],
    element_loads: list[dict] = None,
) -> tuple[np.ndarray, csr_matrix, list[int]]:
    """Solve linear static FEM problem.

    Assembles global stiffness matrix K and force vector F, applies boundary
    conditions, solves K*d = F, and returns displacements.

    Check assumptions before solving:
    - K_FF symmetry: ||K-K^T||_inf < 1e-9*||K||_inf
    - No zero diagonal in K_FF (catches under-constrained models)

    Args:
        nodes: List of node dicts with 'id', 'x', 'y'
        elements: List of element dicts
        materials: List of material dicts
        bcs: List of BC dicts with 'node_id', 'dof', 'value'
        nodal_loads: List of load dicts with 'node_id', 'Fx', 'Fy', 'Mz'
        element_loads: Optional list of element load dicts

    Returns:
        Tuple of (d_full, K_FF, free_dofs)
        - d_full: Full displacement vector (n_dof,)
        - K_FF: Partitioned stiffness matrix
        - free_dofs: List of free DOF indices
    """
    # Assemble global stiffness matrix
    K = assemble_global_stiffness(nodes, elements, materials)

    # Assemble global force vector (includes nodal loads)
    F = assemble_nodal_loads(nodes, nodal_loads, elements, element_loads, materials)

    # Apply boundary conditions
    K_FF, F_mod, free_dofs, constrained_dofs = apply_boundary_conditions(K, F, bcs)

    n_free = len(free_dofs)

    # Pre-solve checks
    # Check K_FF symmetry
    K_FF_dense = K_FF.toarray() if hasattr(K_FF, "toarray") else K_FF
    K_FF_sym_err = np.linalg.norm(K_FF_dense - K_FF_dense.T, np.inf)
    K_FF_norm = np.linalg.norm(K_FF_dense, np.inf)

    if K_FF_norm > 0 and K_FF_sym_err / K_FF_norm > 1e-9:
        raise ValueError(
            f"K_FF is not symmetric: ||K-K^T||_inf / ||K||_inf = {K_FF_sym_err / K_FF_norm:.2e}"
        )

    # Check no zero diagonal (under-constrained)
    diag = np.diag(K_FF_dense)
    zero_diag_mask = np.isclose(diag, 0, atol=1e-12)

    if np.any(zero_diag_mask):
        zero_dofs = [free_dofs[i] for i in np.where(zero_diag_mask)[0]]
        raise ValueError(
            f"Zero diagonal in K_FF at DOFs {zero_dofs} - model is under-constrained"
        )

    # Handle all-constrained case (no free DOFs)
    if len(free_dofs) == 0:
        n_dof = 3 * len(nodes)
        d_full = np.zeros(n_dof)
        # Set prescribed values for all DOFs
        for bc in bcs:
            node_id = bc["node_id"]
            dof_type = bc["dof"]
            value = bc["value"]
            gdof = node_gdof(node_id, _dof_type_to_index(dof_type))
            d_full[gdof] = value
        return d_full, K_FF, free_dofs

    # Solve for free DOF displacements
    d_free = spsolve(K_FF, F_mod)

    # Reconstruct full displacement vector
    n_dof = 3 * len(nodes)
    d_full = np.zeros(n_dof)

    for i, gdof in enumerate(free_dofs):
        d_full[gdof] = d_free[i]

    # Set prescribed values for constrained DOFs
    for bc in bcs:
        node_id = bc["node_id"]
        dof_type = bc["dof"]
        value = bc["value"]

        gdof = node_gdof(node_id, _dof_type_to_index(dof_type))

        d_full[gdof] = value

    return d_full, K_FF, free_dofs


def compute_reactions(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
    bcs: list[dict],
    nodal_loads: list[dict],
    d_full: np.ndarray,
    element_loads: list[dict] = None,
) -> np.ndarray:
    """Compute reactions at constrained DOFs.

    R_C = K_CF * d_F + K_CC * d_C - F_C

    Args:
        nodes: List of node dicts
        elements: List of element dicts
        materials: List of material dicts
        bcs: List of BC dicts
        nodal_loads: List of load dicts
        d_full: Complete displacement vector
        element_loads: Optional list of element load dicts

    Returns:
        Reaction force vector (n_dof,) with zeros at free DOFs
    """
    # Assemble global stiffness matrix
    K = assemble_global_stiffness(nodes, elements, materials)

    # Assemble global force vector (includes nodal loads)
    F = assemble_nodal_loads(nodes, nodal_loads, elements, element_loads, materials)

    # Get DOF partitions
    constrained = set()
    for bc in bcs:
        node_id = bc["node_id"]
        dof_type = bc["dof"]

        gdof = node_gdof(node_id, _dof_type_to_index(dof_type))

        constrained.add(gdof)

    free_dofs = sorted(set(range(3 * len(nodes))) - constrained)
    constrained_dofs = sorted(constrained)

    # Compute reactions at constrained DOFs
    K_CF = K[np.ix_(constrained_dofs, free_dofs)].toarray() if hasattr(K, "toarray") else K[np.ix_(constrained_dofs, free_dofs)]
    K_CC = K[np.ix_(constrained_dofs, constrained_dofs)].toarray() if hasattr(K, "toarray") else K[np.ix_(constrained_dofs, constrained_dofs)]

    d_F = d_full[free_dofs]
    d_C = d_full[constrained_dofs]
    F_C = F[constrained_dofs]

    R_C = K_CF @ d_F + K_CC @ d_C - F_C

    # Assemble full reaction vector
    n_dof = 3 * len(nodes)
    R = np.zeros(n_dof)
    R[free_dofs] = 0.0
    for i, gdof in enumerate(constrained_dofs):
        R[gdof] = R_C[i]

    return R

"""Global stiffness matrix and force vector assembly.

References:
- Cook 4th ed., §2.5 (Assembly of global stiffness matrix)
- McGuire-Gallagher-Ziemer 2nd ed., Ch. 4 (Direct stiffness method)

DOF ordering: 3 DOF per node [u, v, θz], gdof = 3·node_id + k
- k=0: u (translation X)
- k=1: v (translation Y)
- k=2: θz (rotation about Z)

Sign convention: See beamfea/conventions.md §2
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix

from beamfea.element import (
    condense_rotational_dof,
    element_stiffness_global,
    element_stiffness_local,
)


def global_dof_indices(node_i: int, node_j: int) -> list[int]:
    """Compute global DOF indices for an element.

    DOF ordering per node: [u, v, θz] = [0, 1, 2]
    Global DOF: gdof = 3·node_id + local_dof

    Args:
        node_i: Local node i index
        node_j: Local node j index

    Returns:
        List of 6 global DOF indices [u_i, v_i, θz_i, u_j, v_j, θz_j]
    """
    return [3 * node_i, 3 * node_i + 1, 3 * node_i + 2,
            3 * node_j, 3 * node_j + 1, 3 * node_j + 2]


def assemble_global_stiffness(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
) -> csr_matrix:
    """Assemble global stiffness matrix from element contributions.

    Args:
        nodes: List of node dicts with 'id', 'x', 'y'
        elements: List of element dicts with 'id', 'node_i', 'node_j',
                  'material_id', 'A', 'Iz', 'release_i_Mz', 'release_j_Mz'
        materials: List of material dicts with 'id', 'E', 'nu'

    Returns:
        CSR sparse global stiffness matrix
    """
    n_nodes = len(nodes)
    n_dof = 3 * n_nodes

    # Build material lookup
    material_map = {m["id"]: m for m in materials}

    # Pre-allocate for assembly (will grow dynamically)
    row_ind = []
    col_ind = []
    data = []

    for elem in elements:
        node_i = elem["node_i"]
        node_j = elem["node_j"]
        mat_id = elem["material_id"]

        material = material_map[mat_id]
        E = material["E"]
        A = elem["A"]
        Iz = elem["Iz"]

        # Get node coordinates
        node_i_coord = next(n for n in nodes if n["id"] == node_i)
        node_j_coord = next(n for n in nodes if n["id"] == node_j)

        x_i, y_i = node_i_coord["x"], node_i_coord["y"]
        x_j, y_j = node_j_coord["x"], node_j_coord["y"]

        # Compute element length and angle
        dx = x_j - x_i
        dy = y_j - y_i
        L = np.sqrt(dx**2 + dy**2)

        # Angle from global X to local x̂ (i→j)
        theta = np.arctan2(dy, dx)

        # Compute local stiffness matrix
        K_local = element_stiffness_local(E, A, Iz, L)

        # Apply end releases
        K_local = condense_rotational_dof(K_local, elem["release_i_Mz"], elem["release_j_Mz"])

        # Transform to global coordinates
        K_global = element_stiffness_global(E, A, Iz, L, theta)

        # Get global DOF indices
        gdof = global_dof_indices(node_i, node_j)

        # Add to assembly lists
        for i, gi in enumerate(gdof):
            for j, gj in enumerate(gdof):
                row_ind.append(gi)
                col_ind.append(gj)
                data.append(K_global[i, j])

    # Build sparse matrix
    K = csr_matrix((data, (row_ind, col_ind)), shape=(n_dof, n_dof))

    return K


def assemble_nodal_loads(
    nodes: list[dict],
    nodal_loads: list[dict],
) -> np.ndarray:
    """Assemble global force vector from nodal loads.

    Args:
        nodes: List of node dicts (for size determination)
        nodal_loads: List of load dicts with 'node_id', 'Fx', 'Fy', 'Mz'

    Returns:
        Global force vector (n_dof,)
    """
    n_nodes = len(nodes)
    n_dof = 3 * n_nodes

    F = np.zeros(n_dof)

    for load in nodal_loads:
        node_id = load["node_id"]
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        F[gdof_u] += load.get("Fx", 0.0)
        F[gdof_v] += load.get("Fy", 0.0)
        F[gdof_rz] += load.get("Mz", 0.0)

    return F


def apply_boundary_conditions(
    K: csr_matrix,
    F: np.ndarray,
    bcs: list[dict],
) -> tuple[csr_matrix, np.ndarray, list[int], list[int]]:
    """Apply boundary conditions using partitioning.

    DOFs are partitioned into:
    - Free DOFs (F): Unconstrained, solved for
    - Constrained DOFs (C): Prescribed values, accounted for in load vector

    The system is rearranged as:
    [K_FF  K_FC] [d_F] = [F_F - K_FC*d_C]
    [K_CF  K_CC] [d_C]   [    F_C_app    ]

    Where d_C are prescribed values (typically 0).

    Args:
        K: Global stiffness matrix
        F: Global force vector
        bcs: List of BC dicts with 'node_id', 'dof', 'value'

    Returns:
        Tuple of (K_FF, F_mod, free_dofs, constrained_dofs)
        - K_FF: Partitioned stiffness matrix for free DOFs
        - F_mod: Modified force vector (accounting for BCs)
        - free_dofs: List of free DOF indices
        - constrained_dofs: List of constrained DOF indices
    """
    n_dof = len(F)

    # Identify constrained and free DOFs
    constrained = set()
    bc_values = {}

    for bc in bcs:
        node_id = bc["node_id"]
        dof_type = bc["dof"]
        value = bc["value"]

        if dof_type == "u":
            gdof = 3 * node_id
        elif dof_type == "v":
            gdof = 3 * node_id + 1
        elif dof_type == "rz":
            gdof = 3 * node_id + 2
        else:
            raise ValueError(f"Unknown dof type: {dof_type}")

        constrained.add(gdof)
        bc_values[gdof] = value

    free_dofs = sorted(set(range(n_dof)) - constrained)
    constrained_dofs = sorted(constrained)

    n_free = len(free_dofs)
    n_constrained = len(constrained_dofs)

    if n_free == 0:
        raise ValueError("All DOFs are constrained - no free DOFs to solve")

    # Extract K_FF
    K_FF = K[np.ix_(free_dofs, free_dofs)]

    # Compute modified force vector: F_mod = F - K_FC * d_C
    # Return only the free DOF components
    F_mod = F[free_dofs].copy()

    if n_constrained > 0:
        K_FC = K[np.ix_(free_dofs, constrained_dofs)].toarray() if hasattr(K, "toarray") else K[np.ix_(free_dofs, constrained_dofs)]
        d_C = np.array([bc_values[gdof] for gdof in constrained_dofs])
        F_mod -= K_FC @ d_C

    return K_FF, F_mod, free_dofs, constrained_dofs

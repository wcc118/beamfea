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
    transformation_matrix,
)
from beamfea.loads import fixed_end_forces_local


def _transform_local_to_global(K_local: np.ndarray, theta: float) -> np.ndarray:
    """Transform a (possibly condensed) local stiffness to global coords.

    K_global = T^T * K_local * T

    When end releases are present, K_local is the condensed 6x6 matrix
    from condense_rotational_dof, not the full unreleased matrix.
    The rotation matrix T is standard 6x6 block-diagonal of two 3x3
    rotation blocks.

    Args:
        K_local: 6x6 local stiffness (condensed if releases present)
        theta: angle from global X to local x_hat (radians)

    Returns:
        6x6 global stiffness matrix
    """
    T = transformation_matrix(theta)
    return T.T @ K_local @ T


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

        # Apply end releases (static condensation in local coords)
        if elem.get("release_i_Mz") or elem.get("release_j_Mz"):
            K_local = condense_rotational_dof(K_local, elem["release_i_Mz"], elem["release_j_Mz"])

        # Transform to global coordinates
        if elem.get("release_i_Mz") or elem.get("release_j_Mz"):
            K_global = _transform_local_to_global(K_local, theta)
        else:
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
    elements: list[dict] = None,
    element_loads: list[dict] = None,
    materials: list[dict] = None,
) -> np.ndarray:
    """Assemble global force vector from nodal and element loads.

    Element loads are converted to consistent nodal forces using fixed-end
    force formulas.

    Args:
        nodes: List of node dicts with 'id', 'x', 'y'
        nodal_loads: List of load dicts with 'node_id', 'Fx', 'Fy', 'Mz'
        elements: List of element dicts (needed for element load conversion)
        element_loads: List of element load dicts with 'element_id',
                       'w_axial', 'w_transverse'
        materials: List of material dicts

    Returns:
        Global force vector (n_dof,)
    """
    n_nodes = len(nodes)
    n_dof = 3 * n_nodes

    F = np.zeros(n_dof)

    # Add nodal loads
    for load in nodal_loads:
        node_id = load["node_id"]
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        F[gdof_u] += load.get("Fx", 0.0)
        F[gdof_v] += load.get("Fy", 0.0)
        F[gdof_rz] += load.get("Mz", 0.0)

    # Add element loads (converted to condensed nodal forces)
    if element_loads:
        # Build element and material maps
        element_map = {e["id"]: e for e in elements} if elements else {}
        material_map = {m["id"]: m for m in materials} if materials else {}

        for load in element_loads:
            elem_id = load["element_id"]
            elem = element_map.get(elem_id)
            if not elem:
                continue

            node_i = elem["node_i"]
            node_j = elem["node_j"]
            mat_id = elem["material_id"]
            mat = material_map.get(mat_id, {"E": 10.3e6})
            E = mat.get("E", 10.3e6)

            x_i = next(n["x"] for n in nodes if n["id"] == node_i)
            y_i = next(n["y"] for n in nodes if n["id"] == node_i)
            x_j = next(n["x"] for n in nodes if n["id"] == node_j)
            y_j = next(n["y"] for n in nodes if n["id"] == node_j)

            dx = x_j - x_i
            dy = y_j - y_i
            L = (dx**2 + dy**2)**0.5

            w_axial = load.get("w_axial", 0.0)
            w_transverse = load.get("w_transverse", 0.0)
            release_i = elem.get("release_i_Mz", False)
            release_j = elem.get("release_j_Mz", False)
            
            # Element angle for coordinate transformation
            theta = np.arctan2(dy, dx)

            # Compute condensed fixed-end forces in local frame
            # static redistribution for release handling, matching existing K-condensation)
            f_fixed_local = fixed_end_forces_local(E, A=elem["A"], Iz=elem["Iz"], L=L, w_axial=w_axial, w_transverse=w_transverse, release_i=release_i, release_j=release_j)

            # Transform condensed nodal forces to global
            T = transformation_matrix(theta)
            f_global = T @ f_fixed_local

            # Apply to global DOFs
            gdof_i = 3 * node_i
            gdof_j = 3 * node_j
            for i in range(6):
                k = gdof_i + i if i < 3 else gdof_j + (i - 3)
                F[k] += f_global[i]

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
        # All DOFs constrained - return empty K_FF
        # Solver should handle by setting d=0 and computing R=-F
        return csr_matrix((0, 0), dtype=float), np.array([]), [], sorted(constrained)

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


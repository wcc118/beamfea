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


def node_gdof(node_id: int, local_dof: int) -> int:
    """Compute global DOF index for a single node DOF.

    DOF ordering per node: [u, v, θz] = [0, 1, 2]
    Global DOF: gdof = 3·node_id + local_dof

    Args:
        node_id: Node index (zero-based)
        local_dof: Local DOF index (0=u, 1=v, 2=rz)

    Returns:
        Global DOF index
    """
    return 3 * node_id + local_dof


def node_dof_names() -> list[str]:
    """Return DOF name mapping for a single node.

    Returns:
        List of DOF names ["u", "v", "rz"] corresponding to local indices 0, 1, 2
    """
    return ["u", "v", "rz"]


def _dof_type_to_index(dof_type: str) -> int:
    """Convert a DOF type string to its local index.

    Args:
        dof_type: One of "u", "v", "rz"

    Returns:
        Local DOF index (0, 1, or 2)

    Raises:
        ValueError: If dof_type is not recognized
    """
    names = node_dof_names()
    try:
        return names.index(dof_type)
    except ValueError:
        raise ValueError(f"Unknown dof type: {dof_type}")


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
    return [node_gdof(node_i, k) for k in range(3)] + \
           [node_gdof(node_j, k) for k in range(3)]


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

    For inclined elements, nodal loads are transformed to element-local coordinates
    to properly decompose axial and transverse components, then transformed back
    to global coordinates using the transpose of the displacement transformation
    matrix (F_global = T^T @ F_local) to ensure equilibrium is satisfied.

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

    # Build element map for load transformation
    element_map = {e["id"]: e for e in elements} if elements else {}

    # Add nodal loads
    # For inclined elements, transform loads to account for element angle
    for load in nodal_loads:
        node_id = load["node_id"]
        Fx_global = load.get("Fx", 0.0)
        Fy_global = load.get("Fy", 0.0)
        Mz_global = load.get("Mz", 0.0)

        # Find elements connected to this node
        if elements is not None:
            connected_elements = [
                elem for elem in elements
                if elem["node_i"] == node_id or elem["node_j"] == node_id
            ]
        else:
            connected_elements = []

        if not connected_elements:
            # No elements connected - apply load directly (original behavior)
            gdof_u = node_gdof(node_id, 0)
            gdof_v = node_gdof(node_id, 1)
            gdof_rz = node_gdof(node_id, 2)
            F[gdof_u] += Fx_global
            F[gdof_v] += Fy_global
            F[gdof_rz] += Mz_global
        elif len(connected_elements) == 1:
            # Single element - transform load based on element angle
            elem = connected_elements[0]
            node_i = elem["node_i"]
            node_j = elem["node_j"]
            x_i = next(n["x"] for n in nodes if n["id"] == node_i)
            y_i = next(n["y"] for n in nodes if n["id"] == node_i)
            x_j = next(n["x"] for n in nodes if n["id"] == node_j)
            y_j = next(n["y"] for n in nodes if n["id"] == node_j)

            dx = x_j - x_i
            dy = y_j - y_i
            L = (dx**2 + dy**2)**0.5

            if L > 0:
                theta = np.arctan2(dy, dx)

                # Rotation matrix (same as in element.py)
                c = np.cos(theta)
                s = np.sin(theta)

                # Transform load to local coordinates
                # F_local = T @ F_global (where T rotates global to local)
                # This decomposes the global load into axial and transverse components
                Fx_local = Fx_global * c + Fy_global * s
                Fy_local = -Fx_global * s + Fy_global * c
                Mz_local = Mz_global

                # Apply local force components to appropriate global DOFs
                # The element stiffness is in local coordinates, but we're assembling
                # the global force vector. We need to transform local forces back to
                # global coordinates using F_global = T^T @ F_local (transformation transpose).
                # 
                # For a node at angle theta from global X to local x_hat (i->j):
                # - Fx_local is axial (along element)
                # - Fy_local is transverse (perpendicular to element)
                # 
                # The force transformation is:
                # F[u_global] = cos(theta)*Fx_local - sin(theta)*Fy_local
                # F[v_global] = sin(theta)*Fx_local + cos(theta)*Fy_local
                #
                # This ensures equilibrium is satisfied in global coordinates.
                # Mz is the same in both systems (rotation about Z axis).

                # Determine if this node is i or j for proper DOF mapping
                if node_i == node_id:
                    # Node is i-end
                    gdof_u = node_gdof(node_id, 0)
                    gdof_v = node_gdof(node_id, 1)
                else:
                    # Node is j-end: same transformation (element has ONE local system)
                    gdof_u = node_gdof(node_id, 0)
                    gdof_v = node_gdof(node_id, 1)
                gdof_rz = node_gdof(node_id, 2)

                # Transform local forces to global
                F[gdof_u] += Fx_local * c - Fy_local * s
                F[gdof_v] += Fx_local * s + Fy_local * c
                F[gdof_rz] += Mz_local
            else:
                # L = 0, degenerate element - apply load directly
                gdof_u = node_gdof(node_id, 0)
                gdof_v = node_gdof(node_id, 1)
                gdof_rz = node_gdof(node_id, 2)
                F[gdof_u] += Fx_global
                F[gdof_v] += Fy_global
                F[gdof_rz] += Mz_global
        else:
            # Multiple elements connected - use first element for transformation
            # In a real FEM code, this would require more sophisticated handling
            elem = connected_elements[0]
            node_i = elem["node_i"]
            node_j = elem["node_j"]
            x_i = next(n["x"] for n in nodes if n["id"] == node_i)
            y_i = next(n["y"] for n in nodes if n["id"] == node_i)
            x_j = next(n["x"] for n in nodes if n["id"] == node_j)
            y_j = next(n["y"] for n in nodes if n["id"] == node_j)

            dx = x_j - x_i
            dy = y_j - y_i
            L = (dx**2 + dy**2)**0.5

            if L > 0:
                theta = np.arctan2(dy, dx)
                c = np.cos(theta)
                s = np.sin(theta)

                # The transformation is the same for both i and j ends
                # (element has ONE local coordinate system)
                Fx_local = Fx_global * c + Fy_global * s
                Fy_local = -Fx_global * s + Fy_global * c

                gdof_u = node_gdof(node_id, 0)
                gdof_v = node_gdof(node_id, 1)
                gdof_rz = node_gdof(node_id, 2)

                # Transform local forces to global using F_global = T^T @ F_local
                F[gdof_u] += Fx_local * c - Fy_local * s
                F[gdof_v] += Fx_local * s + Fy_local * c
                F[gdof_rz] += Mz_global
            else:
                gdof_u = node_gdof(node_id, 0)
                gdof_v = node_gdof(node_id, 1)
                gdof_rz = node_gdof(node_id, 2)
                F[gdof_u] += Fx_global
                F[gdof_v] += Fy_global
                F[gdof_rz] += Mz_global

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
            for i in range(6):
                target_node = node_i if i < 3 else node_j
                local_idx = i if i < 3 else i - 3
                k = node_gdof(target_node, local_idx)
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

        gdof = node_gdof(node_id, _dof_type_to_index(dof_type))

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


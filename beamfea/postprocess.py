"""Post-processing: end forces, internal force diagrams, GPF balance, stress, maxima.

Sign conventions: See beamfea/conventions.md §2
- Axial N: positive in tension (element pulled apart)
- Shear V: positive when rotating element segment clockwise
- Moment M: sagging-positive

Element end forces per foundation_spec.md §8:
    f_local = K_local · T · d_global_element − f_local_fixed_end

Refs: Cook 4th ed., §2.3 (beam stiffness)
      McGuire-Gallagher-Ziemer 2nd ed., Ch. 5 (Beam elements)
"""

from __future__ import annotations

import numpy as np

from beamfea.assembly import assemble_global_stiffness, assemble_nodal_loads
from beamfea.element import (
    condense_rotational_dof,
    element_stiffness_local,
    transformation_matrix,
)


def compute_element_end_forces(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
    d_full: np.ndarray,
    element_loads: list[dict] = None,
) -> list[dict]:
    """Compute internal forces at element ends (local coordinates).

    For each element, returns [N_i, V_i, M_i, N_j, V_j, M_j] where:
    - N: axial force (tension positive)
    - V: shear force (clockwise positive per §2)
    - M: bending moment (sagging positive per §2)

    Formula: f_local = K_local · T · d_element - f_fixed_end

    Args:
        nodes: List of node dicts with 'id', 'x', 'y'
        elements: List of element dicts
        materials: List of material dicts with 'id', 'E', 'nu'
        d_full: Full displacement vector from solver
        element_loads: Optional list of element load dicts with w_axial, w_transverse

    Returns:
        List of dicts per element with 'element_id' and 'forces_local'
    """
    material_map = {m["id"]: m for m in materials}
    element_map = {e["id"]: e for e in elements}
    loads_map = {load["element_id"]: load for load in (element_loads or [])}

    results = []

    for elem in elements:
        elem_id = elem["id"]
        node_i = elem["node_i"]
        node_j = elem["node_j"]
        mat_id = elem["material_id"]

        material = material_map[mat_id]
        E = material["E"]
        A = elem["A"]
        Iz = elem["Iz"]

        node_i_coord = next(n for n in nodes if n["id"] == node_i)
        node_j_coord = next(n for n in nodes if n["id"] == node_j)

        x_i, y_i = node_i_coord["x"], node_i_coord["y"]
        x_j, y_j = node_j_coord["x"], node_j_coord["y"]

        dx = x_j - x_i
        dy = y_j - y_i
        L = np.sqrt(dx**2 + dy**2)

        theta = np.arctan2(dy, dx)

        K_local = element_stiffness_local(E, A, Iz, L)

        # Apply same condensation used during assembly so f = K*d is consistent
        release_i = elem.get("release_i_Mz", False)
        release_j = elem.get("release_j_Mz", False)
        if release_i or release_j:
            K_local = condense_rotational_dof(K_local, release_i, release_j)

        T = transformation_matrix(theta)

        gdof = [3 * node_i, 3 * node_i + 1, 3 * node_i + 2,
                3 * node_j, 3 * node_j + 1, 3 * node_j + 2]
        d_element = d_full[gdof]

        f_fixed = np.zeros(6)
        load = loads_map.get(elem_id)
        if load:
            w_axial = load.get("w_axial", 0.0)
            w_transverse = load.get("w_transverse", 0.0)

            if w_axial != 0:
                f_fixed[0] = w_axial * L / 2
                f_fixed[3] = w_axial * L / 2

            if w_transverse != 0:
                f_fixed[1] = w_transverse * L / 2
                f_fixed[2] = w_transverse * L**2 / 12
                f_fixed[4] = w_transverse * L / 2
                f_fixed[5] = -w_transverse * L**2 / 12

        # Transform global displacements to local frame before K_local multiplication
        d_local = T @ d_element
        f_local = K_local @ d_local - f_fixed

        # Released ends carry zero moment by definition
        if release_i:
            f_local[2] = 0.0
        if release_j:
            f_local[5] = 0.0

        results.append({
            "element_id": elem_id,
            "forces_local": f_local.tolist()
        })

    return results


def compute_internal_force_diagrams(
    nodes: list[dict],
    elements: list[dict],
    element_end_forces: list[dict],
    element_loads: list[dict] = None,
) -> list[dict]:
    """Compute internal force diagrams sampled at 3 points per element.

    Sampling stations: i-end (x=0), midspan (x=L/2), j-end (x=L)

    Internal force functions derived from equilibrium of segment [0, x],
    where N_i, V_i, M_i are the element end-forces at the i-node from
    ``compute_element_end_forces`` (forces the node applies to the element):

        N(x) = -N_i - w_a · x           (tension positive)
        V(x) =  V_i + w_t · x           (CW-positive per conventions.md §2)
        M(x) =  M_i - V_i·x - w_t·x²/2 (sagging-positive per conventions.md §2)

    The sign on V_i and w_t in the moment equation is negative because
    a positive (upward) shear at the i-end produces a moment that
    *decreases* the sagging moment as x increases (see Cook 4th ed. §2.3,
    McGuire-Gallagher-Ziemer 2nd ed. Ch. 5 sign-convention discussion).

    Args:
        nodes: List of node dicts
        elements: List of element dicts
        element_end_forces: Output from compute_element_end_forces
        element_loads: Optional element load dicts

    Returns:
        List of dicts with element_id and 'stations' array of 3 points
    """
    element_map = {e["id"]: e for e in elements}
    loads_map = {load["element_id"]: load for load in (element_loads or [])}
    forces_map = {f["element_id"]: np.array(f["forces_local"]) for f in element_end_forces}

    results = []

    for elem in elements:
        elem_id = elem["id"]
        node_i = elem["node_i"]
        node_j = elem["node_j"]

        node_i_coord = next(n for n in nodes if n["id"] == node_i)
        node_j_coord = next(n for n in nodes if n["id"] == node_j)

        x_i, y_i = node_i_coord["x"], node_i_coord["y"]
        x_j, y_j = node_j_coord["x"], node_j_coord["y"]

        dx = x_j - x_i
        dy = y_j - y_i
        L = np.sqrt(dx**2 + dy**2)

        forces = forces_map.get(elem_id, np.zeros(6))
        N_i, V_i, M_i = forces[0], forces[1], forces[2]

        load = loads_map.get(elem_id, {})
        w_axial = load.get("w_axial", 0.0)
        w_transverse = load.get("w_transverse", 0.0)

        stations = []

        for x in [0.0, L / 2.0, L]:
            N = -N_i - w_axial * x
            V = V_i + w_transverse * x
            M = M_i - V_i * x - w_transverse * x**2 / 2.0

            dx_global = (x / L) * dx if L > 0 else 0.0
            dy_global = (x / L) * dy if L > 0 else 0.0
            x_global = x_i + dx_global
            y_global = y_i + dy_global

            stations.append({
                "x_global": x_global,
                "y_global": y_global,
                "x_local": x,
                "N": N,
                "V": V,
                "M": M
            })

        results.append({
            "element_id": elem_id,
            "stations": stations
        })

    return results


def compute_gpf_balance(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
    d_full: np.ndarray,
    bcs: list[dict],
    nodal_loads: list[dict],
    element_loads: list[dict] = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Compute grid point force balance residuals.

    At each node, sum:
        (a) all element end forces transformed to global
        (b) applied nodal loads
        (c) reactions if constrained

    Residual = K@d - F_applied - R
    Should be ~0 for equilibrium.

    Args:
        nodes: List of node dicts
        elements: List of element dicts
        materials: List of material dicts
        d_full: Full displacement vector
        bcs: List of BC dicts
        nodal_loads: List of nodal load dicts
        element_loads: Optional element load dicts

    Returns:
        Tuple of (residuals, max_forces, tolerance)
        - residuals: per-node residual vector [rx1, ry1, rm1, rx2, ...]
        - max_forces: max |Force| component per node
        - tolerance: 1e-6 * max(max_forces)
    """
    n_nodes = len(nodes)
    n_dof = 3 * n_nodes

    K = assemble_global_stiffness(nodes, elements, materials)
    F = assemble_nodal_loads(nodes, nodal_loads, elements, element_loads, materials)

    R = np.zeros(n_dof)

    constrained = set()
    bc_values = {}

    for bc in bcs:
        node_id = bc["node_id"]
        dof_type = bc["dof"]

        if dof_type == "u":
            gdof = 3 * node_id
        elif dof_type == "v":
            gdof = 3 * node_id + 1
        elif dof_type == "rz":
            gdof = 3 * node_id + 2
        else:
            raise ValueError(f"Unknown dof type: {dof_type}")

        constrained.add(gdof)
        bc_values[gdof] = bc["value"]

    constrained_dofs_list = sorted(constrained)
    free_dofs = sorted(set(range(n_dof)) - set(constrained_dofs_list))

    if len(constrained_dofs_list) > 0 and len(free_dofs) > 0:
        K_CF = K[np.ix_(constrained_dofs_list, free_dofs)].toarray()
        K_CC = K[np.ix_(constrained_dofs_list, constrained_dofs_list)].toarray()

        d_F = d_full[free_dofs]
        d_C = d_full[constrained_dofs_list]
        F_C = F[constrained_dofs_list]

        R_C = K_CF @ d_F + K_CC @ d_C - F_C

        for i, gdof in enumerate(constrained_dofs_list):
            R[gdof] = R_C[i]

    Kd = K @ d_full

    max_forces = np.zeros(n_nodes)

    for node_id in range(n_nodes):
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        idx = [gdof_u, gdof_v, gdof_rz]

        F_node = F[idx]
        R_node = R[idx]

        F_abs_sum = np.sum(np.abs(F_node)) + np.sum(np.abs(R_node))

        max_forces[node_id] = F_abs_sum

    tolerance = 1e-6 * np.max(max_forces) if np.max(max_forces) > 0 else 1e-12

    residuals = Kd - (F + R)

    return residuals, max_forces, tolerance


def compute_element_node_contributions(
    nodes: list[dict],
    elements: list[dict],
    materials: list[dict],
    d_full: np.ndarray,
    element_loads: list[dict] = None,
) -> list[dict]:
    """Compute per-element force contributions at each node in global coords.

    For each element, transforms the local end-force vector to global
    coordinates via T^T, then splits into node-i and node-j contributions.
    This enables free-body-diagram breakdowns at any node.

    The sign convention: the contribution is the force the element exerts
    *on the node* (i.e. the internal force vector in the global frame at
    the element end attached to that node).

    Ref: Cook 4th ed. §2.3 -- f_global = T^T * f_local

    Args:
        nodes: List of node dicts
        elements: List of element dicts
        materials: List of material dicts
        d_full: Full displacement vector from solver
        element_loads: Optional element load dicts

    Returns:
        List of dicts, one per element:
        {
            "element_id": int,
            "node_i": int,
            "node_j": int,
            "forces_global": [Fx_i, Fy_i, Mz_i, Fx_j, Fy_j, Mz_j],
            "contrib_i": {"Fx": float, "Fy": float, "Mz": float},
            "contrib_j": {"Fx": float, "Fy": float, "Mz": float},
        }
    """
    material_map = {m["id"]: m for m in materials}
    loads_map = {load["element_id"]: load for load in (element_loads or [])}

    results = []

    for elem in elements:
        elem_id = elem["id"]
        ni_id = elem["node_i"]
        nj_id = elem["node_j"]
        mat = material_map[elem["material_id"]]
        E, A, Iz = mat["E"], elem["A"], elem["Iz"]

        ni = next(n for n in nodes if n["id"] == ni_id)
        nj = next(n for n in nodes if n["id"] == nj_id)
        dx = nj["x"] - ni["x"]
        dy = nj["y"] - ni["y"]
        L = np.sqrt(dx**2 + dy**2)
        theta = np.arctan2(dy, dx)

        K_local = element_stiffness_local(E, A, Iz, L)
        release_i = elem.get("release_i_Mz", False)
        release_j = elem.get("release_j_Mz", False)
        if release_i or release_j:
            K_local = condense_rotational_dof(K_local, release_i, release_j)
        T = transformation_matrix(theta)

        gdof = [3 * ni_id, 3 * ni_id + 1, 3 * ni_id + 2,
                3 * nj_id, 3 * nj_id + 1, 3 * nj_id + 2]
        d_elem = d_full[gdof]

        f_fixed = np.zeros(6)
        load = loads_map.get(elem_id)
        if load:
            wa = load.get("w_axial", 0.0)
            wt = load.get("w_transverse", 0.0)
            if wa != 0:
                f_fixed[0] = wa * L / 2
                f_fixed[3] = wa * L / 2
            if wt != 0:
                f_fixed[1] = wt * L / 2
                f_fixed[2] = wt * L**2 / 12
                f_fixed[4] = wt * L / 2
                f_fixed[5] = -wt * L**2 / 12

        d_local = T @ d_elem
        f_local = K_local @ d_local - f_fixed
        if release_i:
            f_local[2] = 0.0
        if release_j:
            f_local[5] = 0.0
        f_global = T.T @ f_local

        results.append({
            "element_id": elem_id,
            "node_i": ni_id,
            "node_j": nj_id,
            "forces_global": f_global.tolist(),
            "contrib_i": {
                "Fx": f_global[0],
                "Fy": f_global[1],
                "Mz": f_global[2],
            },
            "contrib_j": {
                "Fx": f_global[3],
                "Fy": f_global[4],
                "Mz": f_global[5],
            },
        })

    return results


def compute_stresses(
    nodes: list[dict],
    elements: list[dict],
    element_end_forces: list[dict],
) -> list[dict]:
    """Compute combined stress at element stations.

    Stress formulas:
        σ_axial = N / A
        σ_bending,max = |M| · c / Iz  where c = √(Iz/A)
        σ_combined = σ_axial ± σ_bending,max

    Args:
        nodes: List of node dicts
        elements: List of element dicts
        element_end_forces: Output from compute_element_end_forces

    Returns:
        List of dicts with element_id and 'stations' array
    """
    element_map = {e["id"]: e for e in elements}
    forces_map = {f["element_id"]: np.array(f["forces_local"]) for f in element_end_forces}

    results = []

    for elem in elements:
        elem_id = elem["id"]
        node_i = elem["node_i"]
        node_j = elem["node_j"]

        node_i_coord = next(n for n in nodes if n["id"] == node_i)
        node_j_coord = next(n for n in nodes if n["id"] == node_j)

        x_i, y_i = node_i_coord["x"], node_i_coord["y"]
        x_j, y_j = node_j_coord["x"], node_j_coord["y"]

        dx = x_j - x_i
        dy = y_j - y_i
        L = np.sqrt(dx**2 + dy**2)

        elem_props = element_map[elem_id]
        A = elem_props["A"]
        Iz = elem_props["Iz"]
        c = np.sqrt(Iz / A)

        forces = forces_map.get(elem_id, np.zeros(6))
        N_i, V_i, M_i = forces[0], forces[1], forces[2]
        N_j, V_j, M_j = forces[3], forces[4], forces[5]

        stations = []

        for x, N_end, M_end in [(0.0, N_i, M_i), (L / 2.0, (N_i + N_j) / 2, (M_i + M_j) / 2), (L, N_j, M_j)]:
            sigma_axial = N_end / A
            sigma_bending_max = abs(M_end) * c / Iz if Iz > 0 else 0.0

            stations.append({
                "x_local": x,
                "sigma_axial": sigma_axial,
                "sigma_bending_max": sigma_bending_max,
                "sigma_combined_plus": sigma_axial + sigma_bending_max,
                "sigma_combined_minus": sigma_axial - sigma_bending_max
            })

        results.append({
            "element_id": elem_id,
            "stations": stations
        })

    return results


def compute_maxima(
    element_end_forces: list[dict],
    internal_force_diagrams: list[dict],
    stresses: list[dict],
    d_full: np.ndarray,
    nodes: list[dict],
) -> dict:
    """Compute global maxima of key quantities with locations.

    Returns max of:
        - max |v| (transverse deflection, in) with location
        - max |u| (axial displacement, in) with location
        - max |rz| (rotation, rad) with location
        - |M| (bending moment, lb-in)
        - |V| (shear force, lb)
        - |N| (axial force, lb)
        - |σ_combined| (max combined stress, psi)

    Args:
        element_end_forces: Output from compute_element_end_forces
        internal_force_diagrams: Output from compute_internal_force_diagrams
        stresses: Output from compute_stresses
        d_full: Full displacement vector
        nodes: List of node dicts

    Returns:
        Dict with keys: transverse_deflection, axial_displacement, max_rotation,
        moment, shear, axial, stress.
    """
    node_map = {n["id"]: n for n in nodes}

    # --- Maximum transverse deflection: max |v| across all nodes ---
    # Transverse deflection is the meaningful serviceability parameter for 2D beams.
    # Per Cook 4th ed., §2.3 and McGuire-Gallagher-Ziemer 2nd ed., Ch. 5,
    # the Hermite shape functions relate nodal v values to the deflection curve.
    transverse_max = 0.0
    transverse_loc = {"node_id": 0, "direction": "v"}
    transverse_vec = np.zeros(3)

    for node_id in range(len(nodes)):
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        u, v, rz = d_full[gdof_u], d_full[gdof_v], d_full[gdof_rz]

        abs_v = abs(v)

        if abs_v > transverse_max:
            transverse_max = abs_v
            transverse_loc = {"node_id": node_id, "direction": "v"}
            transverse_vec = np.array([u, v, rz])

    # --- Maximum axial displacement: max |u| across all nodes ---
    axial_disp_max = 0.0
    axial_disp_loc = {"node_id": 0}
    axial_disp_vec = np.zeros(3)

    for node_id in range(len(nodes)):
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        u, v, rz = d_full[gdof_u], d_full[gdof_v], d_full[gdof_rz]

        abs_u = abs(u)

        if abs_u > axial_disp_max:
            axial_disp_max = abs_u
            axial_disp_loc = {"node_id": node_id}
            axial_disp_vec = np.array([u, v, rz])

    # --- Maximum rotation: max |rz| across all nodes ---
    rotation_max = 0.0
    rotation_loc = {"node_id": 0}
    rotation_vec = np.zeros(3)

    for node_id in range(len(nodes)):
        gdof_u = 3 * node_id
        gdof_v = 3 * node_id + 1
        gdof_rz = 3 * node_id + 2

        u, v, rz = d_full[gdof_u], d_full[gdof_v], d_full[gdof_rz]

        abs_rz = abs(rz)

        if abs_rz > rotation_max:
            rotation_max = abs_rz
            rotation_loc = {"node_id": node_id}
            rotation_vec = np.array([u, v, rz])

    moment_max = 0.0
    moment_loc = {"element_id": 0, "station": 0.0}

    for diag in internal_force_diagrams:
        elem_id = diag["element_id"]
        for station in diag["stations"]:
            M = abs(station["M"])
            if M > moment_max:
                moment_max = M
                moment_loc = {"element_id": elem_id, "station": station["x_local"]}

    shear_max = 0.0
    shear_loc = {"element_id": 0, "station": 0.0}

    for diag in internal_force_diagrams:
        elem_id = diag["element_id"]
        for station in diag["stations"]:
            V = abs(station["V"])
            if V > shear_max:
                shear_max = V
                shear_loc = {"element_id": elem_id, "station": station["x_local"]}

    axial_max = 0.0
    axial_loc = {"element_id": 0, "station": 0.0}

    for diag in internal_force_diagrams:
        elem_id = diag["element_id"]
        for station in diag["stations"]:
            N = abs(station["N"])
            if N > axial_max:
                axial_max = N
                axial_loc = {"element_id": elem_id, "station": station["x_local"]}

    stress_max = 0.0
    stress_loc = {"element_id": 0, "station": 0.0, "type": "plus"}

    for stress in stresses:
        elem_id = stress["element_id"]
        for station in stress["stations"]:
            sigma_plus = abs(station["sigma_combined_plus"])
            sigma_minus = abs(station["sigma_combined_minus"])

            if sigma_plus > stress_max:
                stress_max = sigma_plus
                stress_loc = {"element_id": elem_id, "station": station["x_local"], "type": "plus"}

            if sigma_minus > stress_max:
                stress_max = sigma_minus
                stress_loc = {"element_id": elem_id, "station": station["x_local"], "type": "minus"}

    # Coordinates of node with max transverse deflection
    transverse_node_pos = node_map[transverse_loc["node_id"]]

    return {
        "transverse_deflection": {
            "value": transverse_max,
            "node_id": transverse_loc["node_id"],
            "x": transverse_node_pos["x"],
            "y": transverse_node_pos["y"],
            "displacement_vector": transverse_vec.tolist()
        },
        "axial_displacement": {
            "value": axial_disp_max,
            "node_id": axial_disp_loc["node_id"],
            "x": node_map[axial_disp_loc["node_id"]]["x"],
            "y": node_map[axial_disp_loc["node_id"]]["y"],
            "displacement_vector": axial_disp_vec.tolist()
        },
        "max_rotation": {
            "value": rotation_max,
            "node_id": rotation_loc["node_id"],
            "x": node_map[rotation_loc["node_id"]]["x"],
            "y": node_map[rotation_loc["node_id"]]["y"],
            "displacement_vector": rotation_vec.tolist()
        },
        "moment": {
            "value": moment_max,
            "element_id": moment_loc["element_id"],
            "station": moment_loc["station"]
        },
        "shear": {
            "value": shear_max,
            "element_id": shear_loc["element_id"],
            "station": shear_loc["station"]
        },
        "axial_force": {
            "value": axial_max,
            "element_id": axial_loc["element_id"],
            "station": axial_loc["station"]
        },
        "stress": {
            "value": stress_max,
            "element_id": stress_loc["element_id"],
            "station": stress_loc["station"],
            "type": stress_loc["type"]
        }
    }


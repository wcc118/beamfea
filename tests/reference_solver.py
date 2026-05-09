"""Reference FEA solver for generating expected values.

A simple, brute-force, dense-matrix solver for 2D beam/frame elements.

References:
- Cook 4th ed., §2.5 (Assembly of global stiffness matrix)
- Logan, A First Course in the Finite Element Method, §4 (Planar frame elements)

DOF ordering: [u, v, θz] per node, gdof = 3·node_id + k
"""

import numpy as np


def _global_dof_indices(node_i, node_j):
    """Get global DOF indices for an element."""
    return [3 * node_i, 3 * node_i + 1, 3 * node_i + 2,
            3 * node_j, 3 * node_j + 1, 3 * node_j + 2]


def _element_stiffness_local(E, A, Iz, L):
    """Compute local stiffness matrix for Euler-Bernoulli beam element."""
    alpha = E * A / L
    beta = E * Iz / L**3
    
    K = np.zeros((6, 6))
    K[0, 0] = alpha
    K[0, 3] = -alpha
    K[3, 0] = -alpha
    K[3, 3] = alpha
    
    K[1, 1] = 12 * beta
    K[1, 2] = 6 * beta * L
    K[1, 4] = -12 * beta
    K[1, 5] = 6 * beta * L
    K[2, 1] = 6 * beta * L
    K[2, 2] = 4 * beta * L**2
    K[2, 4] = -6 * beta * L
    K[2, 5] = 2 * beta * L**2
    K[4, 1] = -12 * beta
    K[4, 2] = -6 * beta * L
    K[4, 4] = 12 * beta
    K[4, 5] = -6 * beta * L
    K[5, 1] = 6 * beta * L
    K[5, 2] = 2 * beta * L**2
    K[5, 4] = -6 * beta * L
    K[5, 5] = 4 * beta * L**2
    
    return K


def _transformation_matrix(theta):
    """Compute coordinate transformation matrix."""
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    T = np.zeros((6, 6))
    T[0:3, 0:3] = R
    T[3:6, 3:6] = R
    return T


def _element_stiffness_global(E, A, Iz, L, theta):
    """Compute global stiffness matrix for beam element."""
    K_local = _element_stiffness_local(E, A, Iz, L)
    T = _transformation_matrix(theta)
    return T.T @ K_local @ T


def _element_fixed_end_forces(w_axial, w_transverse, L):
    """Compute fixed-end forces for uniform distributed loads."""
    f = np.zeros(6)
    if w_axial != 0:
        f[0] = w_axial * L / 2
        f[3] = w_axial * L / 2
    if w_transverse != 0:
        f[1] = w_transverse * L / 2
        f[2] = w_transverse * L**2 / 12
        f[4] = w_transverse * L / 2
        f[5] = -w_transverse * L**2 / 12
    return f


def _assembled_K_F(nodes, elements, materials, nodal_loads, element_loads):
    """Assemble global K and F from model data."""
    n_nodes = len(nodes)
    n_dof = 3 * n_nodes
    K = np.zeros((n_dof, n_dof))
    F = np.zeros(n_dof)
    
    material_map = {m['id']: m for m in materials}
    element_map = {e['id']: e for e in elements}
    
    # Add nodal loads
    for load in nodal_loads:
        node_id = load['node_id']
        gdof_u = 3 * node_id
        F[gdof_u] += load.get('Fx', 0)
        F[gdof_u + 1] += load.get('Fy', 0)
        F[gdof_u + 2] += load.get('Mz', 0)
    
    # Add element loads and stiffness
    for elem in elements:
        node_i = elem['node_i']
        node_j = elem['node_j']
        mat = material_map[elem['material_id']]
        E, A, Iz = mat['E'], elem['A'], elem['Iz']
        
        x_i, y_i = nodes[node_i]['x'], nodes[node_i]['y']
        x_j, y_j = nodes[node_j]['x'], nodes[node_j]['y']
        
        dx, dy = x_j - x_i, y_j - y_i
        L = np.sqrt(dx**2 + dy**2)
        theta = np.arctan2(dy, dx)
        
        # Global element stiffness
        K_elem = _element_stiffness_global(E, A, Iz, L, theta)
        
        # Global DOF indices
        gdof = _global_dof_indices(node_i, node_j)
        
        # Assemble
        for i, gi in enumerate(gdof):
            for j, gj in enumerate(gdof):
                K[gi, gj] += K_elem[i, j]
        
        # Element loads → fixed-end forces
        elem_load = next((el for el in element_loads if el['element_id'] == elem['id']), None)
        if elem_load:
            w_a = elem_load.get('w_axial', 0)
            w_t = elem_load.get('w_transverse', 0)
            f_elem = _element_fixed_end_forces(w_a, w_t, L)
            
            T = _transformation_matrix(theta)
            f_global = T @ f_elem
            
            for i, gi in enumerate(gdof):
                F[gi] += f_global[i]
    
    return K, F


def _apply_bc(K, F, bcs):
    """Apply boundary conditions by partitioning."""
    n_dof = len(F)
    
    constrained = set()
    bc_values = {}
    
    for bc in bcs:
        node_id = bc['node_id']
        dof = bc['dof']
        value = bc['value']
        
        if dof == 'u':
            gdof = 3 * node_id
        elif dof == 'v':
            gdof = 3 * node_id + 1
        elif dof == 'rz':
            gdof = 3 * node_id + 2
        else:
            raise ValueError(f"Unknown DOF: {dof}")
        
        constrained.add(gdof)
        bc_values[gdof] = value
    
    free_dofs = sorted(set(range(n_dof)) - constrained)
    constrained_dofs = sorted(constrained)
    
    # Extract K_FF and F_F
    K_FF = K[np.ix_(free_dofs, free_dofs)]
    F_F = F[free_dofs]
    
    # Account for boundary conditions
    if constrained_dofs:
        K_FC = K[np.ix_(free_dofs, constrained_dofs)]
        d_C = np.array([bc_values[gdof] for gdof in constrained_dofs])
        F_F = F_F - K_FC @ d_C
    
    return K_FF, F_F, free_dofs, constrained_dofs, bc_values


def solve_reference(nodes, elements, materials, bcs, nodal_loads, element_loads):
    """Solve using reference solver.
    
    Returns:
        d_full: full displacement vector
        reactions: reaction force vector
    """
    n_dof = 3 * len(nodes)
    
    K, F = _assembled_K_F(nodes, elements, materials, nodal_loads, element_loads)
    
    K_FF, F_mod, free_dofs, constrained_dofs, bc_values = _apply_bc(K, F, bcs)
    
    # Solve
    d_free = np.linalg.solve(K_FF, F_mod)
    
    # Reconstruct full displacement
    d_full = np.zeros(n_dof)
    for i, gdof in enumerate(free_dofs):
        d_full[gdof] = d_free[i]
    for gdof, val in bc_values.items():
        d_full[gdof] = val
    
    # Compute reactions: R = K·d - F
    R = K @ d_full - F
    
    return d_full, R

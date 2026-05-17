"""Consistent nodal force conversion for distributed element loads.

Sign conventions: see beamfea/conventions.md.
- Axial N: positive in tension
- Transverse load w: positive upward (consistent with global +Y)
- Fixed-end forces: positive when the load pushes the element end (Newton's 3rd;
  these are the forces the supports exert ON the element, so reaction forces
  are their negation).

Shape functions and fixed-end force formulas per Cook 4th ed. §2.3
(beam element with distributed loading) and
McGuire-Gallagher-Ziemer 2nd ed. Ch. 5.

Static condensation of fixed-end forces for released DOFs follows
Cook 4th ed. §2.7 (hinged-end beam elements).

References:
- Cook, Concepts and Applications of Finite Element Analysis, 4th ed., §2.3, §2.7
- McGuire, Gallagher, Ziemer, Structural Matrix Analysis, 2nd ed., Ch. 5
"""

from __future__ import annotations

import numpy as np

from beamfea.element import element_stiffness_local


def fixed_end_forces_local(
    E: float,
    A: float,
    Iz: float,
    L: float,
    w_axial: float = 0.0,
    w_transverse: float = 0.0,
    release_i: bool = False,
    release_j: bool = False,
) -> np.ndarray:
    """Compute condensed fixed-end force vector for distributed element loads.

    For an Euler-Bernoulli beam element with distributed axial load w_axial
    (lb/in, tension-positive) and distributed transverse load w_transverse
    (lb/in, upward-positive), this returns the fixed-end force vector in
    local coordinates [Fi, Fi_y, Mi_j, Fj, Fj_y, Mj].

    Fixed-end forces are the nodal force vector that would result if both
    ends of the element were fully fixed (no translation, no rotation).
    These represent the forces the supports exert *on* the element.

    If end releases are present (pin releases), the fixed-end forces are
    statically condensed so that the released DOFs carry zero force,
    consistent with the element stiffness condensation.

    **Axial load (Cook 4th ed. §2.3, eq. 2.3.12):**

    For uniform axial load w_axial:
    - Both ends share the total axial load equally: f[0] = f[3] = w_axial * L / 2

    **Transverse load (Cook 4th ed. §2.3, eq. 2.3.13):**

    For uniform transverse load w_transverse (upward positive):
    - Shear at each end: f[1] = f[4] = w_transverse * L / 2
    - Moment at i-end: f[2] = +w_transverse * L^2 / 12
    - Moment at j-end:   f[5] = -w_transverse * L^2 / 12

    The sign convention for moments follows sagging-positive per
    conventions.md §2 and Cook 4th ed. §2.3.

    **Release condensation (Cook 4th ed. §2.7):**

    When a rotational DOF is released (pinned), the corresponding
    fixed-end moment is redistributed to the remaining DOFs via
    static condensation:

    f_cond[keep] = f_fe[keep] - K[keep, release] * f_fe[release] / K[release, release]

    This ensures that f_cond[release] = 0 (moment is zero at a pinned end)
    and that equilibrium is preserved for the unreleased DOFs.

    Args:
        E: Young's modulus (psi)
        A: Cross-sectional area (in^2)
        Iz: Area moment of inertia (in^4)
        L: Element length (in)
        w_axial: Uniform axial load (lb/in, tension-positive)
        w_transverse: Uniform transverse load (lb/in, upward-positive)
        release_i: True if element has a pin release at node i (release θz_i)
        release_j: True if element has a pin release at node j (release θz_j)

    Returns:
        6-element fixed-end force vector in local coordinates:
        [F_x_i, F_y_i, M_z_i, F_x_j, F_y_j, M_z_j]

    DOF ordering: [0]=u_i, [1]=v_i, [2]=θz_i, [3]=u_j, [4]=v_j, [5]=θz_j

    Ref: Cook 4th ed. §2.3 (fixed-end force formulas), §2.7 (static condensation)
    """
    # Full fixed-end forces in local coordinates (fully fixed element)
    f_fe = np.zeros(6)

    # Axial fixed-end forces: each end carries half the total load
    if w_axial != 0.0:
        f_fe[0] = w_axial * L / 2.0
        f_fe[3] = w_axial * L / 2.0

    # Transverse fixed-end forces (Cook 4th ed., eq. 2.3.13)
    if w_transverse != 0.0:
        f_fe[1] = w_transverse * L / 2.0
        f_fe[2] = w_transverse * L**2 / 12.0
        f_fe[4] = w_transverse * L / 2.0
        f_fe[5] = -w_transverse * L**2 / 12.0

    # Condense for end releases
    if not release_i and not release_j:
        return f_fe

    # Build local stiffness for condensation
    K_local = element_stiffness_local(E, A, Iz, L)

    f_cond = f_fe.copy()

    # Condense iteratively: release_i (DOF 2) then release_j (DOF 5)
    # Each condensation redistributes the fixed-end force at the released DOF
    # to the remaining DOFs via: f[keep] -= K[keep,rel] * f[rel] / K[rel,rel]
    release_order = []
    if release_i:
        release_order.append((2, [0, 1, 3, 4, 5]))  # condense θz_i
    if release_j:
        release_order.append((5, [0, 1, 2, 3, 4]))  # condense θz_j

    # Rebuild f_cond from original f_fe to ensure correctness when both ends released
    # Using original f_fe ensures correct redistribution for both DOFs simultaneously
    f_cond = f_fe.copy()

    for rel_dof, keep_dofs in release_order:
        k_vec = K_local[np.ix_(keep_dofs, [rel_dof])].ravel()
        k_scalar = K_local[rel_dof, rel_dof]
        f_cond[keep_dofs] -= k_vec * f_fe[rel_dof] / k_scalar

    return f_cond


def fixed_end_forces_global(
    E: float,
    A: float,
    Iz: float,
    L: float,
    theta: float,
    w_axial: float = 0.0,
    w_transverse: float = 0.0,
    release_i: bool = False,
    release_j: bool = False,
) -> np.ndarray:
    """Compute condensed fixed-end force vector transformed to global coordinates.

    Convenience wrapper around fixed_end_forces_local that additionally
    returns the condensed local-frame fixed-end forces.

    Args:
        E: Young's modulus (psi)
        A: Cross-sectional area (in^2)
        Iz: Area moment of inertia (in^4)
        L: Element length (in)
        theta: Angle from global X to local x_hat (radians)
        w_axial: Uniform axial load (lb/in, tension-positive)
        w_transverse: Uniform transverse load (lb/in, upward-positive)
        release_i: True if element has a pin release at node i (release θz_i)
        release_j: True if element has a pin release at node j (release θz_j)

    Returns:
        6-element fixed-end force vector in global coordinates:
        [F_x_i, F_y_i, Mz_i, F_x_j, F_y_j, Mz_j]

    Ref: Cook 4th ed. §2.3 -- f_global = T @ f_local for fixed-end forces
    """
    from beamfea.element import transformation_matrix

    f_local = fixed_end_forces_local(
        E, A, Iz, L, w_axial, w_transverse, release_i, release_j
    )

    T = transformation_matrix(theta)
    return T @ f_local




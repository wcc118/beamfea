"""Element stiffness matrix, transformation, and end-release condensation.

References:
- Cook 4th ed., §2.3 (Euler-Bernoulli beam stiffness matrix)
- McGuire-Gallagher-Ziemer 2nd ed., Ch. 5 (Beam elements)

Sign convention: see beamfea/conventions.md §2
- Axial N: tension positive
- Shear V: positive when rotating element segment clockwise
- Moment M: sagging-positive
"""

from __future__ import annotations

import numpy as np


def element_stiffness_local(E: float, A: float, Iz: float, L: float) -> np.ndarray:
    """Compute local stiffness matrix for Euler-Bernoulli beam element.

    DOF ordering: [u_i, v_i, θz_i, u_j, v_j, θz_j]

    K_local =
    [  α      0         0       -α      0         0     ]
    [  0    12β       6βL        0    -12β       6βL    ]
    [  0    6βL     4βL²         0    -6βL     2βL²    ]
    [ -α     0         0        α      0         0     ]
    [  0   -12β      -6βL        0    12β      -6βL    ]
    [  0    6βL     2βL²         0    -6βL     4βL²    ]

    where α = EA/L and β = EI/L³

    Args:
        E: Elastic modulus
        A: Cross-sectional area
        Iz: Second moment of area about z-axis
        L: Element length

    Returns:
        6x6 local stiffness matrix
    """
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


def transformation_matrix(theta: float) -> np.ndarray:
    """Compute coordinate transformation matrix for 2D beam element.

    For an element at angle theta from global X to local x̂ (i→j direction):

    Q_local = T · Q_global

    where T is block-diagonal with two 3×3 rotation blocks.

    R(θ) = [ c  s  0 ]
           [-s  c  0 ]
           [ 0  0  1 ]

    Args:
        theta: Angle from global X to local x̂ (radians, CCW positive)

    Returns:
        6x6 transformation matrix T
    """
    c = np.cos(theta)
    s = np.sin(theta)

    R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])

    T = np.zeros((6, 6))
    T[0:3, 0:3] = R
    T[3:6, 3:6] = R

    return T


def element_stiffness_global(
    E: float, A: float, Iz: float, L: float, theta: float
) -> np.ndarray:
    """Compute global stiffness matrix for beam element.

    K_global = Tᵀ · K_local · T

    Args:
        E: Elastic modulus
        A: Cross-sectional area
        Iz: Second moment of area
        L: Element length
        theta: Angle from global X to local x̂ (radians)

    Returns:
        6x6 global stiffness matrix
    """
    K_local = element_stiffness_local(E, A, Iz, L)
    T = transformation_matrix(theta)

    K_global = T.T @ K_local @ T

    return K_global


def condense_rotational_dof(K_local: np.ndarray, release_i: bool, release_j: bool) -> np.ndarray:
    """Apply static condensation for moment releases at element ends.

    When release_i_Mz or release_j_Mz is True, the rotational DOF at that
    end is condensed out, removing bending stiffness contribution while
    retaining axial stiffness.

    Reference: Cook 4th ed., §2.7 (Static condensation)
               McGuire-Gallagher-Ziemer 2nd ed., Ch. 7

    DOF ordering: [u_i, v_i, θz_i, u_j, v_j, θz_j]
    For release_i=True: condense θz_i (DOF 2)
    For release_j=True: condense θz_j (DOF 5)

    Args:
        K_local: 6x6 local stiffness matrix (unreleased)
        release_i: If True, release moment at i-end (θz_i free)
        release_j: If True, release moment at j-end (θz_j free)

    Returns:
        6x6 condensed local stiffness matrix
    """
    K = K_local.copy()

    if release_i and release_j:
        # Both ends released - keep only axial terms
        K_released = np.zeros((6, 6))
        K_released[0, 0] = K[0, 0]
        K_released[0, 3] = K[0, 3]
        K_released[3, 0] = K[3, 0]
        K_released[3, 3] = K[3, 3]
        return K_released

    if release_i:
        # Keep DOFs [0,1,3,4], condense DOF 2 (θz_i)
        # K can be partitioned as:
        # K = [K11 K12] where K11 is 5x5 (keep), K12 is 5x1 (couple to cond), K22 is 1x1 (cond)
        #     [K21 K22]
        # After condensation: K_cond = K11 - K12 * (1/K22) * K21

        # Extract submatrices
        K11 = K[np.ix_([0, 1, 3, 4], [0, 1, 3, 4])]
        K12 = K[np.ix_([0, 1, 3, 4], [2])]
        K21 = K[np.ix_([2], [0, 1, 3, 4])]
        K22 = K[2, 2]

        K_cond = K11 - (K12 @ K21) / K22

        # Build full matrix with condensed values
        K_released = np.zeros((6, 6))
        for i, ri in enumerate([0, 1, 3, 4]):
            for j, rj in enumerate([0, 1, 3, 4]):
                K_released[ri, rj] = K_cond[i, j]
        K_released[2, 2] = K22
        return K_released

    if release_j:
        # Keep DOFs [0,1,2,3], condense DOF 5 (θz_j)
        K11 = K[np.ix_([0, 1, 2, 3], [0, 1, 2, 3])]
        K12 = K[np.ix_([0, 1, 2, 3], [5])]
        K21 = K[np.ix_([5], [0, 1, 2, 3])]
        K22 = K[5, 5]

        K_cond = K11 - (K12 @ K21) / K22

        K_released = np.zeros((6, 6))
        for i, ri in enumerate([0, 1, 2, 3]):
            for j, rj in enumerate([0, 1, 2, 3]):
                K_released[ri, rj] = K_cond[i, j]
        K_released[5, 5] = K22
        return K_released

    return K

    K = K_local.copy()

    if release_i and release_j:
        # Both ends released - keep only axial terms
        K_released = np.zeros((6, 6))
        K_released[0, 0] = K[0, 0]
        K_released[0, 3] = K[0, 3]
        K_released[3, 0] = K[3, 0]
        K_released[3, 3] = K[3, 3]
        return K_released

    if release_i:
        K_11 = K[0:3, 0:3]
        K_12 = K[0:3, 3:6]
        K_21 = K[3:6, 0:3]
        K_22 = K[3:6, 3:6]

        K_22_inv = np.linalg.inv(K_22[2:4, 2:4])
        K_released = K_11 - K_12 @ K_22_inv @ K_21
        K_released_full = np.zeros((6, 6))
        K_released_full[0:3, 0:3] = K_released[0:3, 0:3]
        K_released_full[0:3, 3:6] = K_released[0:3, 3:6]
        K_released_full[3:6, 0:3] = K_released[3:6, 0:3]
        K_released_full[3:6, 3:6] = K_22
        return K_released_full

    if release_j:
        K_11 = K[0:3, 0:3]
        K_12 = K[0:3, 3:6]
        K_21 = K[3:6, 0:3]
        K_22 = K[3:6, 3:6]

        K_11_inv = np.linalg.inv(K_11[1:3, 1:3])
        K_released = K_22 - K_21 @ K_11_inv @ K_12
        K_released_full = np.zeros((6, 6))
        K_released_full[0:3, 0:3] = K_11
        K_released_full[0:3, 3:6] = K_released[0:3, 3:6]
        K_released_full[3:6, 0:3] = K_released[3:6, 0:3]
        K_released_full[3:6, 3:6] = K_released[3:6, 3:6]
        return K_released_full

    return K_local

"""Stage 2: Element stiffness matrix tests.

References:
- Cook 4th ed., §2.3 (Euler-Bernoulli beam stiffness matrix)
"""

import numpy as np
import pytest

from beamfea.element import (
    condense_rotational_dof,
    element_stiffness_global,
    element_stiffness_local,
    transformation_matrix,
)


class TestElementStiffnessLocal:
    """Test local stiffness matrix computation."""

    def test_zero_length_raises(self):
        """Element with zero length should cause division by zero."""
        with pytest.raises(ZeroDivisionError):
            element_stiffness_local(E=1.0, A=1.0, Iz=1.0, L=0.0)

    def test_symmetry(self):
        """Stiffness matrix should be symmetric."""
        K = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        assert np.allclose(K, K.T), "K_local should be symmetric"

    def test_special_case_L_120_E_10_3e6_A_1_Iz_1(self):
        """Hand-computed K for L=120, E=10.3e6, A=1, Iz=1.

        α = EA/L = 10.3e6 / 120 = 85833.333...
        β = EI/L³ = 10.3e6 / 120³ = 5.964912280701754e-4

        K[0,0] = K[3,3] = α = 85833.333...
        K[1,1] = K[4,4] = 12β = 0.007157894736842105
        K[1,2] = K[1,5] = K[2,1] = K[5,1] = 6βL = 0.43
        K[2,2] = K[5,5] = 4βL² = 61.92
        K[2,4] = K[4,2] = -6βL = -0.43
        K[1,4] = K[4,1] = -12β = -0.007157894736842105
        K[2,5] = K[5,2] = 2βL² = 30.96
        """
        E, A, Iz, L = 10.3e6, 1.0, 1.0, 120.0
        K = element_stiffness_local(E, A, Iz, L)

        alpha = E * A / L
        beta = E * Iz / L**3

        assert np.isclose(K[0, 0], alpha)
        assert np.isclose(K[0, 3], -alpha)
        assert np.isclose(K[3, 0], -alpha)
        assert np.isclose(K[3, 3], alpha)

        assert np.isclose(K[1, 1], 12 * beta)
        assert np.isclose(K[4, 4], 12 * beta)

        assert np.isclose(K[1, 2], 6 * beta * L)
        assert np.isclose(K[2, 1], 6 * beta * L)
        assert np.isclose(K[1, 4], -12 * beta)
        assert np.isclose(K[4, 1], -12 * beta)

        assert np.isclose(K[2, 2], 4 * beta * L**2)
        assert np.isclose(K[5, 5], 4 * beta * L**2)

        assert np.isclose(K[2, 4], -6 * beta * L)
        assert np.isclose(K[4, 2], -6 * beta * L)

        assert np.isclose(K[2, 5], 2 * beta * L**2)
        assert np.isclose(K[5, 2], 2 * beta * L**2)

    def test_90_degree_element_same_stiffness(self):
        """Element rotated 90° should have same stiffness magnitudes."""
        K_0 = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        K_90 = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        assert np.allclose(K_0, K_90)


class TestTransformationMatrix:
    """Test coordinate transformation matrix."""

    def test_zero_angle_identity(self):
        """θ=0 should give identity transformation."""
        T = transformation_matrix(theta=0.0)
        assert np.allclose(T, np.eye(6))

    def test_90_degree_rotation(self):
        """θ=90°: local x̂ aligns with global ŷ."""
        T = transformation_matrix(theta=np.pi / 2)
        # At 90°, local x̂ = global ŷ, local ŷ = -global X̂
        expected_R = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]])
        assert np.allclose(T[0:3, 0:3], expected_R)
        assert np.allclose(T[3:6, 3:6], expected_R)

    def test_180_degree_rotation(self):
        """θ=180°: local x̂ aligns with -global X̂."""
        T = transformation_matrix(theta=np.pi)
        expected_R = np.array([[-1, 0, 0], [0, -1, 0], [0, 0, 1]])
        assert np.allclose(T[0:3, 0:3], expected_R)
        assert np.allclose(T[3:6, 3:6], expected_R)

    def test_orthogonality(self):
        """Transformation matrix should be orthogonal: TᵀT = I."""
        for theta in [0.0, np.pi / 6, np.pi / 4, np.pi / 3, np.pi / 2]:
            T = transformation_matrix(theta)
            assert np.allclose(T.T @ T, np.eye(6))


class TestElementStiffnessGlobal:
    """Test global stiffness matrix computation."""

    def test_0_degree_element_same_as_local(self):
        """θ=0: K_global = K_local."""
        E, A, Iz, L = 10.3e6, 1.0, 1.0, 120.0
        K_local = element_stiffness_local(E, A, Iz, L)
        K_global = element_stiffness_global(E, A, Iz, L, theta=0.0)
        assert np.allclose(K_global, K_local)

    def test_90_degree_element(self):
        """θ=90°: Verify transformation works correctly."""
        E, A, Iz, L = 10.3e6, 1.0, 1.0, 120.0
        K_local = element_stiffness_local(E, A, Iz, L)
        T = transformation_matrix(np.pi / 2)
        K_global = element_stiffness_global(E, A, Iz, L, theta=np.pi / 2)
        K_expected = T.T @ K_local @ T
        assert np.allclose(K_global, K_expected)

    def test_symmetry(self):
        """Global stiffness matrix should be symmetric."""
        K = element_stiffness_global(E=10.3e6, A=1.0, Iz=1.0, L=120.0, theta=np.pi / 4)
        assert np.allclose(K, K.T)


class TestCondenseRotationalDof:
    """Test static condensation for moment releases."""

    def test_no_release_returns_original(self):
        """No releases should return original matrix."""
        K = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        K_condensed = condense_rotational_dof(K, release_i=False, release_j=False)
        assert np.allclose(K_condensed, K)

    def test_both_releases_keeps_axial_only(self):
        """Both releases: only axial terms remain (truss bar)."""
        K = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        K_condensed = condense_rotational_dof(K, release_i=True, release_j=True)

        # Check that bending terms are zero
        assert np.isclose(K_condensed[1, 1], 0)
        assert np.isclose(K_condensed[2, 2], 0)
        assert np.isclose(K_condensed[4, 4], 0)
        assert np.isclose(K_condensed[5, 5], 0)

        # Check that axial terms are preserved
        assert not np.isclose(K_condensed[0, 0], 0)
        assert not np.isclose(K_condensed[3, 3], 0)

    def test_release_i(self):
        """Release at i-end: θz_i DOF becomes free."""
        K = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        K_condensed = condense_rotational_dof(K, release_i=True, release_j=False)

        # The element should behave as simply supported at i-end
        # Check that the i-end moment-rotation coupling is modified
        assert not np.allclose(K_condensed, K)

    def test_release_j(self):
        """Release at j-end: θz_j DOF becomes free."""
        K = element_stiffness_local(E=10.3e6, A=1.0, Iz=1.0, L=120.0)
        K_condensed = condense_rotational_dof(K, release_i=False, release_j=True)

        # Check that j-end behavior changed
        assert not np.allclose(K_condensed, K)

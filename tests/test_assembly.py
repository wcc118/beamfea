"""Assembly and load tests for Stage 3.

References:
- Cook 4th ed., §2.5 (Assembly of global stiffness matrix)
"""

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from beamfea.assembly import (
    apply_boundary_conditions,
    assemble_global_stiffness,
    assemble_nodal_loads,
    global_dof_indices,
)


class TestGlobalDofIndices:
    """Test global DOF index computation."""

    def test_node_0(self):
        """Node 0 DOFs should be [0, 1, 2]."""
        assert global_dof_indices(0, 0) == [0, 1, 2, 0, 1, 2]

    def test_node_1(self):
        """Node 1 DOFs should be [3, 4, 5, 3, 4, 5]."""
        assert global_dof_indices(1, 1) == [3, 4, 5, 3, 4, 5]

    def test_nodes_0_and_1(self):
        """Node 0 and 1 DOFs should be [0,1,2,3,4,5]."""
        assert global_dof_indices(0, 1) == [0, 1, 2, 3, 4, 5]


class TestAssembleGlobalStiffness:
    """Test global stiffness matrix assembly."""

    def test_single_element_zero_angle(self):
        """Single horizontal element, should match hand-computed K."""
        nodes = [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 120.0, "y": 0.0},
        ]
        materials = [{"id": 0, "E": 10.3e6, "nu": 0.33}]
        elements = [
            {
                "id": 0,
                "node_i": 0,
                "node_j": 1,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": False,
            }
        ]

        K = assemble_global_stiffness(nodes, elements, materials)

        # Should be 6x6 (2 nodes × 3 DOF)
        assert K.shape == (6, 6)
        assert isinstance(K, csr_matrix)

        # Check symmetry
        K_dense = K.toarray()
        assert np.allclose(K_dense, K_dense.T)

    def test_two_elements_in_series(self):
        """Two elements in series should give 9x9 matrix."""
        nodes = [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 120.0, "y": 0.0},
            {"id": 2, "x": 240.0, "y": 0.0},
        ]
        materials = [{"id": 0, "E": 10.3e6, "nu": 0.33}]
        elements = [
            {
                "id": 0,
                "node_i": 0,
                "node_j": 1,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": False,
            },
            {
                "id": 1,
                "node_i": 1,
                "node_j": 2,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": False,
            },
        ]

        K = assemble_global_stiffness(nodes, elements, materials)

        # Should be 9x9 (3 nodes × 3 DOF)
        assert K.shape == (9, 9)

    def test_v1_cantilever_assembly(self):
        """V1: Single cantilever element."""
        nodes = [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 120.0, "y": 0.0},
        ]
        materials = [{"id": 0, "E": 10.3e6, "nu": 0.33}]
        elements = [
            {
                "id": 0,
                "node_i": 0,
                "node_j": 1,
                "material_id": 0,
                "A": 1.0,
                "Iz": 1.0,
                "release_i_Mz": False,
                "release_j_Mz": False,
            }
        ]

        K = assemble_global_stiffness(nodes, elements, materials)

        # Expected DOF count: 2 nodes × 3 = 6
        assert K.shape == (6, 6)

        # Check specific values (same as element stiffness at θ=0)
        # α = EA/L = 10.3e6/120 = 85833.333
        # 12β = 12×EI/L³ = 12×10.3e6/120³ = 0.007157...
        K_dense = K.toarray()
        assert np.isclose(K_dense[0, 0], 10.3e6 / 120, rtol=1e-6)


class TestAssembleNodalLoads:
    """Test global force vector assembly."""

    def test_single_load(self):
        """Single point load at node 1."""
        nodes = [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 120.0, "y": 0.0},
        ]
        loads = [{"node_id": 1, "Fx": 0.0, "Fy": -1000.0, "Mz": 0.0}]

        F = assemble_nodal_loads(nodes, loads)

        # Should be 6 DOFs
        assert F.shape == (6,)

        # Fy at node 1 should be -1000 (DOF index 4 = 3×1 + 1)
        assert np.isclose(F[4], -1000.0)

    def test_multiple_loads(self):
        """Multiple loads should sum."""
        nodes = [
            {"id": 0, "x": 0.0, "y": 0.0},
            {"id": 1, "x": 120.0, "y": 0.0},
        ]
        loads = [
            {"node_id": 0, "Fx": 100.0, "Fy": 0.0, "Mz": 0.0},
            {"node_id": 1, "Fx": 0.0, "Fy": -1000.0, "Mz": 50.0},
        ]

        F = assemble_nodal_loads(nodes, loads)

        # Fx at node 0 (DOF 0)
        assert np.isclose(F[0], 100.0)

        # Fy at node 1 (DOF 4)
        assert np.isclose(F[4], -1000.0)

        # Mz at node 1 (DOF 5)
        assert np.isclose(F[5], 50.0)


class TestApplyBoundaryConditions:
    """Test boundary condition application."""

    def test_fixed_node(self):
        """Fix all DOFs at node 0."""
        K = csr_matrix(np.eye(6))
        F = np.ones(6)
        bcs = [
            {"node_id": 0, "dof": "u", "value": 0.0},
            {"node_id": 0, "dof": "v", "value": 0.0},
            {"node_id": 0, "dof": "rz", "value": 0.0},
        ]

        K_FF, F_mod, free_dofs, constrained_dofs = apply_boundary_conditions(K, F, bcs)

        assert constrained_dofs == [0, 1, 2]
        assert free_dofs == [3, 4, 5]
        assert K_FF.shape == (3, 3)
        # F_mod should be the modified force vector for free DOFs only
        assert F_mod.shape == (3,)
        assert np.allclose(F_mod, [1.0, 1.0, 1.0])

    def test_simple_support(self):
        """Pin at node 0 (u=0, v=0), roller at node 1 (v=0)."""
        K = np.eye(6)
        F = np.ones(6)
        bcs = [
            {"node_id": 0, "dof": "u", "value": 0.0},
            {"node_id": 0, "dof": "v", "value": 0.0},
            {"node_id": 1, "dof": "v", "value": 0.0},
        ]

        K_FF, F_mod, free_dofs, constrained_dofs = apply_boundary_conditions(K, F, bcs)

        assert constrained_dofs == [0, 1, 4]
        assert free_dofs == [2, 3, 5]
        assert K_FF.shape == (3, 3)

    def test_nonzero_prescribed_value(self):
        """Nonzero prescribed displacement."""
        K = np.eye(6)
        F = np.ones(6)
        bcs = [{"node_id": 0, "dof": "u", "value": 0.1}]

        K_FF, F_mod, free_dofs, constrained_dofs = apply_boundary_conditions(K, F, bcs)

        # With prescribed u=0.1 at DOF 0, F_mod should adjust
        assert constrained_dofs == [0]
        assert free_dofs == [1, 2, 3, 4, 5]

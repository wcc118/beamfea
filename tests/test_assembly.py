"""Stage 2/3: global K and F assembly tests."""

import pytest


@pytest.mark.skip(reason="Stage 2/3 not yet implemented")
def test_global_K_symmetric():
    """Assembled K is symmetric to within 1e-9 relative."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2/3 not yet implemented")
def test_global_K_size():
    """K has shape (3*N_nodes, 3*N_nodes)."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2/3 not yet implemented")
def test_nodal_load_assembly():
    """Nodal loads land on the correct DOF indices per gdof = 3*node + k."""
    raise NotImplementedError

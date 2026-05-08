"""Stage 2: element stiffness, transformation, end-release tests."""

import pytest


@pytest.mark.skip(reason="Stage 2 not yet implemented")
def test_element_stiffness_horizontal():
    """Hand-computed K for a horizontal element matches K_local (T = identity)."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2 not yet implemented")
def test_element_stiffness_vertical():
    """K for a 90° element matches expected after transformation."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2 not yet implemented")
def test_element_stiffness_45deg():
    """K for a 45° element matches expected after transformation."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2 not yet implemented")
def test_end_release_single():
    """Single Mz release recovers a pinned-fixed beam stiffness."""
    raise NotImplementedError


@pytest.mark.skip(reason="Stage 2 not yet implemented")
def test_end_release_both_axial_only():
    """Both ends released → only axial stiffness remains (truss bar)."""
    raise NotImplementedError

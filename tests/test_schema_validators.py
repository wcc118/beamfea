"""Tests for Pydantic validators on Element and Material schemas.

Ensures that physically invalid parameter values (non-positive E, A, Iz,
or out-of-range nu) are rejected at model construction time.
"""

import pytest
from pydantic import ValidationError

from beamfea.schema import Element, Material


class TestMaterialValidators:
    """Validators on Material.E and Material.nu."""

    def test_E_positive_accepted(self):
        """Positive E is accepted."""
        m = Material(id=1, E=30e6, nu=0.3)
        assert m.E == 30e6

    def test_E_zero_rejected(self):
        """E == 0 raises ValidationError."""
        with pytest.raises(ValidationError, match="E must be > 0"):
            Material(id=1, E=0, nu=0.3)

    def test_E_negative_rejected(self):
        """Negative E raises ValidationError."""
        with pytest.raises(ValidationError, match="E must be > 0"):
            Material(id=1, E=-100, nu=0.3)

    def test_nu_valid_accepted(self):
        """nu in (0, 0.5) is accepted."""
        m = Material(id=1, E=30e6, nu=0.33)
        assert m.nu == 0.33

    def test_nu_zero_rejected(self):
        """nu == 0 raises ValidationError."""
        with pytest.raises(ValidationError, match="nu must be in \\(0, 0.5\\)"):
            Material(id=1, E=30e6, nu=0)

    def test_nu_negative_rejected(self):
        """Negative nu raises ValidationError."""
        with pytest.raises(ValidationError, match="nu must be in \\(0, 0.5\\)"):
            Material(id=1, E=30e6, nu=-0.1)

    def test_nu_half_rejected(self):
        """nu == 0.5 raises ValidationError (exclusive upper bound)."""
        with pytest.raises(ValidationError, match="nu must be in \\(0, 0.5\\)"):
            Material(id=1, E=30e6, nu=0.5)

    def test_nu_above_half_rejected(self):
        """nu > 0.5 raises ValidationError."""
        with pytest.raises(ValidationError, match="nu must be in \\(0, 0.5\\)"):
            Material(id=1, E=30e6, nu=0.6)


class TestElementValidators:
    """Validators on Element.A and Element.Iz."""

    VALID_KWARGS = {
        "id": 1,
        "node_i": 0,
        "node_j": 1,
        "material_id": 1,
        "A": 1.0,
        "Iz": 1.0,
    }

    def test_A_positive_accepted(self):
        """Positive A is accepted."""
        e = Element(**self.VALID_KWARGS)
        assert e.A == 1.0

    def test_A_zero_rejected(self):
        """A == 0 raises ValidationError."""
        kwargs = {**self.VALID_KWARGS, "A": 0}
        with pytest.raises(ValidationError, match="A must be > 0"):
            Element(**kwargs)

    def test_A_negative_rejected(self):
        """Negative A raises ValidationError."""
        kwargs = {**self.VALID_KWARGS, "A": -5.0}
        with pytest.raises(ValidationError, match="A must be > 0"):
            Element(**kwargs)

    def test_Iz_positive_accepted(self):
        """Positive Iz is accepted."""
        e = Element(**self.VALID_KWARGS)
        assert e.Iz == 1.0

    def test_Iz_zero_rejected(self):
        """Iz == 0 raises ValidationError."""
        kwargs = {**self.VALID_KWARGS, "Iz": 0}
        with pytest.raises(ValidationError, match="Iz must be > 0"):
            Element(**kwargs)

    def test_Iz_negative_rejected(self):
        """Negative Iz raises ValidationError."""
        kwargs = {**self.VALID_KWARGS, "Iz": -2.0}
        with pytest.raises(ValidationError, match="Iz must be > 0"):
            Element(**kwargs)

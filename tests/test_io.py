"""Stage 6: Model I/O tests.

Parametrized round-trip test over all validation JSONs.
"""

import json
from pathlib import Path

import pytest

from beamfea.io import load_model, save_model
from beamfea.schema import Model

VALIDATION_DIR = Path(__file__).parent / "validation"


def _validation_cases():
    """Discover V*_model.json files."""
    if not VALIDATION_DIR.exists():
        return []
    return sorted(VALIDATION_DIR.glob("V*_model.json"))


@pytest.mark.skipif(not _validation_cases(), reason="Validation cases not found")
@pytest.mark.parametrize("model_path", _validation_cases())
def test_io_round_trip(model_path: Path, tmp_path: Path):
    """Load, save to tmp, reload, assert equality."""
    # Load original
    model1 = load_model(model_path)

    # Save to temp
    temp_path = tmp_path / f"{model_path.stem}_roundtrip.beamfea.json"
    save_model(model1, temp_path)

    # Reload
    model2 = load_model(temp_path)

    # Assert equality
    assert model1 == model2


def test_io_invalid_schema_version(tmp_path: Path):
    """Loading file with wrong schema_version raises."""
    invalid = {"schema_version": "99.0", "name": "test", "nodes": [], "materials": [],
               "elements": [], "bcs": [], "nodal_loads": [], "element_loads": []}

    path = tmp_path / "invalid.beamfea.json"
    with open(path, "w") as f:
        json.dump(invalid, f)

    with pytest.raises(ValueError, match="Unsupported schema_version"):
        load_model(path)

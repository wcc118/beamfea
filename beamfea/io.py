"""JSON load/save for Model objects. File extension: .beamfea.json.

Schema versioning per foundation_spec.md section 10.
Top-level "schema_version": "1.0".
Pretty-printed, 2-space indent.
"""

from __future__ import annotations

import json
from pathlib import Path

from beamfea.schema import Model


def load_model(path: str | Path) -> Model:
    """Load a Model from a JSON file.

    Args:
        path: Path to .beamfea.json file

    Returns:
        Model object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If schema_version doesn't match
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    # Validate schema_version
    if data.get("schema_version") != "1.0":
        raise ValueError(
            f"Unsupported schema_version: {data.get('schema_version')}. "
            "Expected '1.0'."
        )

    return Model(**data)


def save_model(model: Model, path: str | Path) -> None:
    """Save a Model to a JSON file.

    Args:
        model: Model to save
        path: Output path (.beamfea.json)
    """
    path = Path(path)
    data = model.model_dump()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

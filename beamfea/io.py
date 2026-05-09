"""JSON load/save for Model objects. File extension: .beamfea.json.

Schema versioning per foundation_spec.md section 10.
Top-level "schema_version": "1.0".
Pretty-printed, 2-space indent.
"""

from __future__ import annotations

import csv
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


def save_results_csv(results: dict, path: str | Path) -> None:
    """Save analysis results to CSV files.

    Args:
        results: Results dict from /results endpoint
        path: Base path for CSV files (extensions added automatically)
    """
    path = Path(path)

    # Displacements CSV
    displacements = results.get("displacements", [])
    nodes = results.get("nodes", [])
    if displacements and nodes:
        with open(path.with_suffix(".displacements.csv"), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["node_id", "u", "v", "rz"])
            for i, node in enumerate(nodes):
                gdof_u = 3 * node["id"]
                gdof_v = 3 * node["id"] + 1
                gdof_rz = 3 * node["id"] + 2
                writer.writerow([
                    node["id"],
                    displacements[gdof_u],
                    displacements[gdof_v],
                    displacements[gdof_rz]
                ])

    # Reactions CSV
    if "gpf_balance" in results:
        residuals = results["gpf_balance"].get("residuals", [])
        with open(path.with_suffix(".reactions.csv"), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["node_id", "dof", "reaction"])
            for i in range(len(residuals)):
                node_id = i // 3
                dof_name = ["u", "v", "rz"][i % 3]
                writer.writerow([node_id, dof_name, residuals[i]])

    # End forces CSV
    end_forces = results.get("end_forces", [])
    if end_forces:
        with open(path.with_suffix(".end_forces.csv"), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["element_id", "N_i", "V_i", "M_i", "N_j", "V_j", "M_j"])
            for ef in end_forces:
                forces = ef.get("forces_local", [])
                writer.writerow([ef["element_id"]] + forces)

    # SMD CSV
    diagrams = results.get("diagrams", [])
    if diagrams:
        with open(path.with_suffix(".smd.csv"), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["element_id", "x_local", "N", "V", "M"])
            for diag in diagrams:
                for station in diag.get("stations", []):
                    writer.writerow([
                        diag["element_id"],
                        station["x_local"],
                        station["N"],
                        station["V"],
                        station["M"]
                    ])

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
    if len(displacements) > 0 and len(nodes) > 0:
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
    reactions = results.get("reactions", [])
    if reactions:
        with open(path.with_suffix(".reactions.csv"), "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["node_id", "dof", "reaction"])
            for r in reactions:
                writer.writerow([r["node_id"], r["dof"], r["value"]])

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


def load_results_csv(base_path: str | Path) -> dict:
    """Load analysis results from CSV files.

    Loads results from:
    - .displacements.csv: node_id, u, v, rz
    - .reactions.csv: node_id, dof, reaction
    - .end_forces.csv: element_id, N_i, V_i, M_i, N_j, V_j, M_j
    - .smd.csv: element_id, x_local, N, V, M

    Args:
        base_path: Base path (without extension) for CSV files

    Returns:
        Results dict compatible with API /results endpoint

    Raises:
        FileNotFoundError: If any required CSV file doesn't exist
        ValueError: If CSV headers don't match expected format
    """
    base_path = Path(base_path)

    results: dict = {}

    # Load displacements
    disp_path = base_path.with_suffix(".displacements.csv")
    if disp_path.exists():
        displacements = _load_displacements_csv(disp_path)
        results["displacements"] = displacements

    # Load reactions
    reactions_path = base_path.with_suffix(".reactions.csv")
    if reactions_path.exists():
        reactions = _load_reactions_csv(reactions_path)
        results["reactions"] = reactions

    # Load end forces
    end_forces_path = base_path.with_suffix(".end_forces.csv")
    if end_forces_path.exists():
        end_forces = _load_end_forces_csv(end_forces_path)
        results["end_forces"] = end_forces

    # Load SMD diagrams
    smd_path = base_path.with_suffix(".smd.csv")
    if smd_path.exists():
        diagrams = _load_smd_csv(smd_path)
        results["diagrams"] = diagrams

    return results


def _load_displacements_csv(path: Path) -> list[float]:
    """Load displacements from CSV.

    Expected format: node_id, u, v, rz
    Returns flat list of displacements [u0, v0, rz0, u1, v1, rz1, ...]

    Args:
        path: Path to .displacements.csv

    Returns:
        Flat list of displacement values

    Raises:
        ValueError: If CSV format doesn't match
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if header is None:
            raise ValueError(f"Empty CSV file: {path}")

        expected = ["node_id", "u", "v", "rz"]
        if header != expected:
            raise ValueError(
                f"Invalid displacements CSV header. Expected {expected}, got {header}"
            )

        displacements = []
        for row in reader:
            if len(row) != 4:
                raise ValueError(
                    f"Invalid displacements row: expected 4 columns, got {len(row)}"
                )
            node_id = int(row[0])
            u = float(row[1])
            v = float(row[2])
            rz = float(row[3])
            # Pad with zeros for any missing nodes
            expected_index = len(displacements)
            while expected_index < 3 * node_id:
                displacements.extend([0.0, 0.0, 0.0])
                expected_index += 3
            # Extend if needed for this node
            while len(displacements) < 3 * node_id + 3:
                displacements.extend([0.0, 0.0, 0.0])
            displacements[3 * node_id] = u
            displacements[3 * node_id + 1] = v
            displacements[3 * node_id + 2] = rz

    return displacements


def _load_reactions_csv(path: Path) -> list[dict]:
    """Load reactions from CSV.

    Expected format: node_id, dof, reaction

    Args:
        path: Path to .reactions.csv

    Returns:
        List of dicts with node_id, dof, value

    Raises:
        ValueError: If CSV format doesn't match
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if header is None:
            raise ValueError(f"Empty CSV file: {path}")

        expected = ["node_id", "dof", "reaction"]
        if header != expected:
            raise ValueError(
                f"Invalid reactions CSV header. Expected {expected}, got {header}"
            )

        reactions = []
        for row in reader:
            if len(row) != 3:
                raise ValueError(
                    f"Invalid reactions row: expected 3 columns, got {len(row)}"
                )
            reactions.append({
                "node_id": int(row[0]),
                "dof": row[1],
                "value": float(row[2])
            })

    return reactions


def _load_end_forces_csv(path: Path) -> list[dict]:
    """Load end forces from CSV.

    Expected format: element_id, N_i, V_i, M_i, N_j, V_j, M_j

    Args:
        path: Path to .end_forces.csv

    Returns:
        List of dicts with element_id and forces_local

    Raises:
        ValueError: If CSV format doesn't match
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if header is None:
            raise ValueError(f"Empty CSV file: {path}")

        expected = ["element_id", "N_i", "V_i", "M_i", "N_j", "V_j", "M_j"]
        if header != expected:
            raise ValueError(
                f"Invalid end_forces CSV header. Expected {expected}, got {header}"
            )

        end_forces = []
        for row in reader:
            if len(row) != 7:
                raise ValueError(
                    f"Invalid end_forces row: expected 7 columns, got {len(row)}"
                )
            end_forces.append({
                "element_id": int(row[0]),
                "forces_local": [float(row[1]), float(row[2]), float(row[3]),
                                 float(row[4]), float(row[5]), float(row[6])]
            })

    return end_forces


def _load_smd_csv(path: Path) -> list[dict]:
    """Load internal force diagrams from CSV.

    Expected format: element_id, x_local, N, V, M

    Groups stations by element_id and returns diagrams structure.

    Args:
        path: Path to .smd.csv

    Returns:
        List of dicts with element_id and stations array

    Raises:
        ValueError: If CSV format doesn't match
    """
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if header is None:
            raise ValueError(f"Empty CSV file: {path}")

        expected = ["element_id", "x_local", "N", "V", "M"]
        if header != expected:
            raise ValueError(
                f"Invalid smd CSV header. Expected {expected}, got {header}"
            )

        # Group stations by element_id
        element_stations: dict[int, list[dict]] = {}
        element_orders: dict[int, list[float]] = {}

        for row in reader:
            if len(row) != 5:
                raise ValueError(
                    f"Invalid smd row: expected 5 columns, got {len(row)}"
                )
            elem_id = int(row[0])
            x_local = float(row[1])
            N = float(row[2])
            V = float(row[3])
            M = float(row[4])

            if elem_id not in element_stations:
                element_stations[elem_id] = []
                element_orders[elem_id] = []

            element_stations[elem_id].append({
                "x_local": x_local,
                "N": N,
                "V": V,
                "M": M
            })
            element_orders[elem_id].append(x_local)

    # Build diagrams list, sorted by element_id
    diagrams = []
    for elem_id in sorted(element_stations.keys()):
        stations = element_stations[elem_id]
        orders = element_orders[elem_id]
        # Sort stations by x_local
        sorted_stations = [s for _, s in sorted(zip(orders, stations))]
        diagrams.append({
            "element_id": elem_id,
            "stations": sorted_stations
        })

    return diagrams

"""Stage 4: Linear static solver tests with parametrized validation.

References:
- Cook 4th ed., §2.6 (Solution of the finite element equations)

Validation suite: tests/validation/ contains V1-V9 (and V8b) model/expected pairs.
Each case is a (model.json, expected.json) pair.
The parametrized test iterates over all pairs and validates against expected values.
"""

from pathlib import Path

import numpy as np
import pytest

from beamfea.solver import compute_reactions, solve_linear_static

VALIDATION_DIR = Path(__file__).parent / "validation"


def _validation_cases():
    """Discover (model_path, expected_path) pairs in tests/validation/."""
    if not VALIDATION_DIR.exists():
        return []
    cases = []
    for model_path in sorted(VALIDATION_DIR.glob("V*_model.json")):
        expected_path = model_path.with_name(
            model_path.name.replace("_model.json", "_expected.json")
        )
        if expected_path.exists():
            cases.append(pytest.param(model_path, expected_path, id=model_path.stem.split("_")[0]))
    return cases


def _load_model(model_path: Path) -> dict:
    """Load a model JSON file."""
    import json

    with open(model_path) as f:
        return json.load(f)


def _load_expected(expected_path: Path) -> dict:
    """Load an expected results JSON file."""
    import json

    with open(expected_path) as f:
        return json.load(f)


def _assert_within_tolerance(actual: float, expected: float, tolerance: float):
    """Assert relative error is within tolerance."""
    if expected == 0:
        assert abs(actual) < tolerance, f"Expected ~0, got {actual}"
    else:
        rel_error = abs(actual - expected) / abs(expected)
        assert rel_error < tolerance, (
            f"Relative error {rel_error:.6f} exceeds tolerance {tolerance}. "
            f"Expected {expected}, got {actual}"
        )


@pytest.mark.skipif(not _validation_cases(), reason="Validation cases not found")
@pytest.mark.parametrize("model_path,expected_path", _validation_cases() or [pytest.param(None, None, id="no-cases")])
def test_validation_case(model_path: Path, expected_path: Path):
    """Solve the model, assert all checked quantities are within tolerance_relative."""
    if model_path is None:
        pytest.skip("No validation cases found")

    # Load model and expected
    model = _load_model(model_path)
    expected = _load_expected(expected_path)

    case_id = expected["case_id"]
    tolerance = expected.get("tolerance_relative", 1e-4)

    # Extract data from model
    nodes = model["nodes"]
    elements = model["elements"]
    materials = model["materials"]
    bcs = model["bcs"]
    nodal_loads = model["nodal_loads"]
    element_loads = model.get("element_loads", [])

    # Solve
    d_full, K_FF, free_dofs = solve_linear_static(
        nodes, elements, materials, bcs, nodal_loads, element_loads
    )

    # Compute reactions
    R = compute_reactions(
        nodes, elements, materials, bcs, nodal_loads, d_full, element_loads
    )

    # Process each check
    for check in expected["checks"]:
        quantity = check["quantity"]
        node_id = check.get("node_id")
        dof = check.get("dof")
        value = check["value"]

        if quantity == "displacement":
            if dof == "u":
                gdof = 3 * node_id
            elif dof == "v":
                gdof = 3 * node_id + 1
            elif dof == "rz":
                gdof = 3 * node_id + 2
            else:
                raise ValueError(f"Unknown DOF: {dof}")

            actual = d_full[gdof]
            _assert_within_tolerance(actual, value, tolerance)

        elif quantity == "reaction":
            if dof == "u":
                gdof = 3 * node_id
            elif dof == "v":
                gdof = 3 * node_id + 1
            elif dof == "rz":
                gdof = 3 * node_id + 2
            else:
                raise ValueError(f"Unknown DOF: {dof}")

            actual = R[gdof]
            _assert_within_tolerance(actual, value, tolerance)

        elif quantity == "end_force":
            continue  # Skip end_force checks (require Stage 5 post-processing)
        else:
            raise ValueError(f"Unknown quantity type: {quantity}")

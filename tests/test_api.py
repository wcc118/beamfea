"""Stage 6: API endpoint tests using FastAPI TestClient."""

import json

import pytest
from fastapi.testclient import TestClient

from beamfea.api import app, models, solve_results

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Clear models and solve_results before each test."""
    models.clear()
    solve_results.clear()
    yield


def test_health():
    """GET /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_model_v1():
    """POST /model accepts valid Model JSON, returns model_id."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    response = client.post("/model", json=v1_data)
    assert response.status_code == 200
    result = response.json()
    assert "model_id" in result
    assert isinstance(result["model_id"], str)


def test_post_invalid_model():
    """POST /model rejects invalid Model with 422."""
    response = client.post("/model", json={"invalid": "data"})
    assert response.status_code == 422


def test_solve_v1():
    """POST /solve/{model_id} runs solver and returns status solved."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    post_response = client.post("/model", json=v1_data)
    model_id = post_response.json()["model_id"]

    solve_response = client.post(f"/solve/{model_id}")
    assert solve_response.status_code == 200
    assert solve_response.json() == {"status": "solved"}


def test_results_v1():
    """GET /results/{model_id} returns cached results."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    post_response = client.post("/model", json=v1_data)
    model_id = post_response.json()["model_id"]

    client.post(f"/solve/{model_id}")

    results_response = client.get(f"/results/{model_id}")
    assert results_response.status_code == 200
    results = results_response.json()
    assert "displacements" in results
    assert "maxima" in results

    # Check displacement at node 1, v DOF
    # V1: delta_tip = -PL^3/(3EI) = -1000 * 120^3 / (3 * 10.3e6 * 1.0) = -55.9223...
    d_v_node1 = results["displacements"][4]  # node 1, v DOF = 3*1 + 1 = 4
    expected = -1000 * 120**3 / (3 * 10.3e6 * 1.0)
    assert abs(d_v_node1 - expected) < 0.01


def test_results_not_solved():
    """GET /results/{model_id} returns 404 if not solved."""
    post_response = client.post("/model", json={"name": "test", "nodes": [],
                                                "materials": [], "elements": [],
                                                "bcs": [], "nodal_loads": [],
                                                "element_loads": []})
    model_id = post_response.json()["model_id"]

    response = client.get(f"/results/{model_id}")
    assert response.status_code == 404


def test_diagram_v1():
    """GET /diagram/{model_id}/0/moment returns PNG."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    post_response = client.post("/model", json=v1_data)
    model_id = post_response.json()["model_id"]

    client.post(f"/solve/{model_id}")

    response = client.get(f"/diagram/{model_id}/0/moment")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    # PNG magic number
    content = response.content
    assert content[0:4] == b"\x89PNG"
    assert len(content) > 1000  # Reasonable PNG size


def test_diagram_invalid_kind():
    """GET /diagram with invalid kind returns 422 (FastAPI validation)."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    post_response = client.post("/model", json=v1_data)
    model_id = post_response.json()["model_id"]

    client.post(f"/solve/{model_id}")

    response = client.get(f"/diagram/{model_id}/0/bogus")
    assert response.status_code == 422


def test_diagram_element_not_found():
    """GET /diagram with non-existent element returns 404."""
    with open("tests/validation/V1_model.json") as f:
        v1_data = json.load(f)

    post_response = client.post("/model", json=v1_data)
    model_id = post_response.json()["model_id"]

    client.post(f"/solve/{model_id}")

    response = client.get(f"/diagram/{model_id}/999/moment")
    assert response.status_code == 404

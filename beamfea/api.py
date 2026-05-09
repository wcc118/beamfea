"""FastAPI server. Port 1337. Endpoints per foundation_spec.md §12.

Endpoints:
- GET /health → {"status": "ok"}
- POST /model → store Model, return {model_id: "<uuid>"}
- POST /solve/{model_id} → run solver + post-processing, cache results
- GET /results/{model_id} → return cached results JSON
- GET /diagram/{model_id}/{element_id}/{kind} → PNG SMD diagram
"""

from __future__ import annotations

import uuid
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from beamfea.postprocess import (
    compute_element_end_forces,
    compute_gpf_balance,
    compute_internal_force_diagrams,
    compute_maxima,
    compute_stresses,
)
from beamfea.schema import Model
from beamfea.solver import solve_linear_static

app = FastAPI(title="beamfea API", version="0.1.0")

# In-memory storage
models: dict[str, Model] = {}
solve_results: dict[str, dict] = {}


def _model_to_dicts(model: Model) -> dict:
    """Convert Pydantic Model to dict format for existing functions."""
    return {
        "name": model.name,
        "nodes": [n.model_dump() for n in model.nodes],
        "materials": [m.model_dump() for m in model.materials],
        "elements": [e.model_dump() for e in model.elements],
        "bcs": [b.model_dump() for b in model.bcs],
        "nodal_loads": [l.model_dump() for l in model.nodal_loads],
        "element_loads": [l.model_dump() for l in model.element_loads],
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/model")
def post_model(model: Model) -> dict[str, str]:
    """Store a Model, return model_id."""
    model_id = str(uuid.uuid4())
    models[model_id] = model
    return {"model_id": model_id}


@app.post("/solve/{model_id}")
def post_solve(model_id: str) -> dict[str, str]:
    """Run solver and post-processing, cache results."""
    if model_id not in models:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    model = models[model_id]
    dicts = _model_to_dicts(model)

    try:
        # Run solver
        d_full, K_FF, free_dofs = solve_linear_static(
            nodes=dicts["nodes"],
            elements=dicts["elements"],
            materials=dicts["materials"],
            bcs=dicts["bcs"],
            nodal_loads=dicts["nodal_loads"],
            element_loads=dicts["element_loads"],
        )

        # Run post-processing
        end_forces = compute_element_end_forces(
            nodes=dicts["nodes"],
            elements=dicts["elements"],
            materials=dicts["materials"],
            d_full=d_full,
            element_loads=dicts["element_loads"],
        )

        diagrams = compute_internal_force_diagrams(
            nodes=dicts["nodes"],
            elements=dicts["elements"],
            element_end_forces=end_forces,
            element_loads=dicts["element_loads"],
        )

        residuals, max_forces, tolerance = compute_gpf_balance(
            nodes=dicts["nodes"],
            elements=dicts["elements"],
            materials=dicts["materials"],
            d_full=d_full,
            bcs=dicts["bcs"],
            nodal_loads=dicts["nodal_loads"],
            element_loads=dicts["element_loads"],
        )

        stresses = compute_stresses(
            nodes=dicts["nodes"],
            elements=dicts["elements"],
            element_end_forces=end_forces,
        )

        maxima = compute_maxima(
            element_end_forces=end_forces,
            internal_force_diagrams=diagrams,
            stresses=stresses,
            d_full=d_full,
            nodes=dicts["nodes"],
        )

        # Cache results
        solve_results[model_id] = {
            "status": "solved",
            "displacements": d_full.tolist(),
            "end_forces": end_forces,
            "diagrams": diagrams,
            "gpf_balance": {
                "residuals": residuals.tolist(),
                "max_forces": max_forces.tolist(),
                "tolerance": tolerance,
            },
            "stresses": stresses,
            "maxima": maxima,
        }

        return {"status": "solved"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/results/{model_id}")
def get_results(model_id: str) -> dict:
    """Return cached results."""
    if model_id not in solve_results:
        raise HTTPException(status_code=404, detail=f"Results for {model_id} not found")

    return solve_results[model_id]


@app.get("/diagram/{model_id}/{element_id}/{kind}")
def get_diagram(
    model_id: str,
    element_id: int,
    kind: Literal["axial", "shear", "moment"],
) -> Response:
    """Render SMD diagram as PNG."""
    if model_id not in solve_results:
        raise HTTPException(status_code=404, detail=f"Results for {model_id} not found")

    results = solve_results[model_id]
    diagrams = results["diagrams"]

    # Find the element's diagram
    element_diagram = None
    for diag in diagrams:
        if diag["element_id"] == element_id:
            element_diagram = diag
            break

    if element_diagram is None:
        raise HTTPException(
            status_code=404,
            detail=f"Element {element_id} not found in results"
        )

    # Get the data to plot
    stations = element_diagram["stations"]
    x_local = [s["x_local"] for s in stations]

    if kind == "axial":
        values = [s["N"] for s in stations]
        label = "Axial Force (lb)"
    elif kind == "shear":
        values = [s["V"] for s in stations]
        label = "Shear Force (lb)"
    elif kind == "moment":
        values = [s["M"] for s in stations]
        label = "Bending Moment (lb-in)"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {kind}")

    # Render with matplotlib
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x_local, values, "-o", markersize=4)
    ax.set_xlabel("Station (in)")
    ax.set_ylabel(label)
    ax.set_title(f"Element {element_id} - {kind.capitalize()} Force Diagram")
    ax.grid(True)

    # Save to PNG
    from io import BytesIO
    png_buf = BytesIO()
    fig.savefig(png_buf, format="png", bbox_inches="tight")
    png_buf.seek(0)
    plt.close(fig)

    return Response(content=png_buf.read(), media_type="image/png")

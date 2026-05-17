"""Pydantic v2 data model for the beamfea Model.

To be implemented in Stage 1. See foundation_spec.md §9 for the schema.
Conventions: see beamfea/conventions.md.
"""

from typing import Literal

from pydantic import BaseModel


class Node(BaseModel):
    """A node in the 2D planar structure.

    Represents a node in the 2D planar structure with x and y coordinates.
    """
    id: int
    x: float
    y: float


class Material(BaseModel):
    """Material properties.

    Elastic modulus E and Poisson's ratio nu. Shear modulus G is computed as E/(2(1+nu)).
    """
    id: int
    E: float
    nu: float


class Element(BaseModel):
    """A 2-node Euler-Bernoulli beam element.

    Properties: length L (computed from node coords), E, A, Iz, optional end-releases.
    Optional ``depth`` gives the cross-section depth in the strong-axis direction;
    used by stress computation to set the extreme-fiber distance c = depth / 2.
    Per Cook 4th ed. §2.3: σ = N/A ± M·c/Iz, where c is the distance from the
    neutral axis to the extreme fiber.
    """
    id: int
    node_i: int
    node_j: int
    material_id: int
    A: float
    Iz: float
    release_i_Mz: bool = False
    release_j_Mz: bool = False
    depth: float | None = None


class NodalBC(BaseModel):
    """Constrains a displacement DOF at a node.

    Constrains a displacement DOF (u, v, or rz) at a node to a prescribed value.
    """
    node_id: int
    dof: Literal["u", "v", "rz"]
    value: float


class NodalLoad(BaseModel):
    """Concentrated load applied at a node.

    Concentrated load [Fx, Fy, Mz] applied at a node.
    """
    node_id: int
    Fx: float = 0
    Fy: float = 0
    Mz: float = 0


class ElementLoad(BaseModel):
    """Element distributed load (uniform only in v1).

    Distributed loads on an element:
    - w_axial: lb/in along local +x̂
    - w_transverse: lb/in along local +ŷ
    """
    element_id: int
    w_axial: float = 0
    w_transverse: float = 0


class Model(BaseModel):
    """Top-level model container.

    Top-level model container with all components.
    """
    schema_version: str = "1.0"
    name: str
    nodes: list[Node]
    materials: list[Material]
    elements: list[Element]
    bcs: list[NodalBC]
    nodal_loads: list[NodalLoad]
    element_loads: list[ElementLoad]

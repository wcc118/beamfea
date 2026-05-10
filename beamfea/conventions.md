# Conventions

This file is referenced by every module that computes or displays internal forces, displacements, or reactions. Its contents are §2 of `foundation_spec.md`, reproduced here so that source files can cite a path-stable single-source-of-truth.

## Coordinate system

**Global axes:** X right, Y up, Z out of the page (right-handed). All rotations follow right-hand rule about Z, so positive θz is counter-clockwise when viewed on screen.

**Element local axes:** for an element from node i to node j, local x̂ runs i→j. Local ŷ is local x̂ rotated 90° CCW. Local ẑ = global Z (out of page).

## Internal force sign convention

This is what gets plotted on shear-moment-axial diagrams.

- **Axial N:** positive in tension (element pulled apart).
- **Shear V:** positive when it rotates the element segment clockwise. On a cut face whose outward normal is +local-x (right face of left segment), the internal shear force in -local-y direction is taken as positive V (i.e., the right segment pushes the left segment's right face downward). This is the standard structural-analysis convention where positive V and positive dM/dx have opposite signs: dM/dx = -V.
- **Moment M:** sagging-positive. On a cut face whose outward normal is +local-x, positive M is a vector in +local-z (CCW when viewed from +z), which produces tension on the +local-y face — i.e., the "bottom" fiber if the beam is drawn left-to-right with local-y up.

## Degrees of freedom

3 DOF per node, ordered: **[u, v, θz]** = [translation X, translation Y, rotation about Z].

Global DOF index for node n, local dof k ∈ {0,1,2}: **gdof = 3·n + k**, with node IDs zero-indexed.

## Units (consistent set, enforced)

inch, pound, lb·in, psi, in², in⁴, lb/in. No conversions. No exceptions in v1.

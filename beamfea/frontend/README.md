# Frontend (Stage 7)

Static HTML/JS/CSS served by FastAPI from this directory. To be built in Stage 7.

Layout per foundation_spec.md §12:
- Three panes: model tree (left), 2D SVG canvas (center), results tabs (right)
- D3 for the canvas (click-to-place node, click-two-nodes for element, right-click for BC/load)
- Server-rendered Matplotlib PNGs for SMD diagrams
- Modal Build → Solve → Results workflow
- Server runs on port 1337, frontend at http://localhost:1337

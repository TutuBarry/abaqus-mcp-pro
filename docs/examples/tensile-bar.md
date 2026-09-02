# Tensile Bar Example

A tensile bar analysis with necking behavior using Abaqus MCP Pro.

## Scripts

- `examples/abaqus_tensile_bar_classic.py` — Full tensile bar model
- `examples/run_tensile_step1.py` — Step 1: Geometry and material
- `examples/run_tensile_step2.py` — Step 2: Mesh and BCs
- `examples/run_tensile_step3.py` — Step 3: Job and post-processing
- `examples/show_tensile_result_viewport.py` — Visualization

## What It Does

1. Creates a cylindrical tensile specimen
2. Assigns elastic-plastic material properties
3. Applies fixed BC at one end and displacement at the other
4. Generates mesh
5. Runs a static analysis
6. Extracts stress-strain curve and necking visualization

## Running the Example

Ask your AI client:

> "Run the tensile bar example step by step from the examples directory"

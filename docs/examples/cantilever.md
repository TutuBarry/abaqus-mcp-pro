# Cantilever Beam Example

A classic cantilever beam static analysis using Abaqus MCP Pro.

## Script

The example script is at `examples/abaqus_cantilever_classic.py`.

## What It Does

1. Creates a rectangular beam part
2. Assigns elastic steel material
3. Applies encastre BC at one end
4. Applies pressure load on top surface
5. Generates mesh
6. Creates and submits a static analysis job
7. Extracts displacement and stress results

## Running the Example

1. Start Abaqus/CAE and activate the MCP bridge
2. Ask your AI client:

> "Run the cantilever beam example from the examples directory"

Or run directly in Abaqus:

```bash
abaqus cae script=examples/abaqus_cantilever_classic.py
```

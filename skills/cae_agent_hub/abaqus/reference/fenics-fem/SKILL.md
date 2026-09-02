---
name: fenics-fem
description: >
  Use this Skill to solve PDEs with the finite element method using FEniCS/dolfinx:
  weak form formulation, mesh generation with gmsh, Poisson/elasticity problems,
  boundary conditions, and paraview export.
tags:
  - physics
  - finite-element
  - FEniCS
  - PDE
  - numerical-methods
version: "1.0.0"
authors:
  - name: awesome-rosetta-skills contributors
    github: "@xjtulyc"
license: "MIT"
platforms:
  - claude-code
  - codex
  - gemini-cli
  - cursor
dependencies:
  python:
    - fenics-dolfinx>=0.6
    - gmsh>=4.11
    - pyvista>=0.39
    - numpy>=1.23
    - petsc4py>=3.18
last_updated: "2026-03-17"
status: stable
---

# FEniCS Finite Element Method for PDEs

> **TL;DR** — Solve partial differential equations with the Finite Element Method (FEM)
> using FEniCS/dolfinx. Derive the weak form, generate meshes with gmsh, apply
> Dirichlet/Neumann boundary conditions, solve Poisson or elasticity problems,
> and export results to XDMF/VTK for ParaView.

---

## When to Use

Use this Skill when you need to:

- Solve elliptic, parabolic, or hyperbolic PDEs on complex geometries
- Implement custom weak forms for multi-physics problems
- Apply mixed Dirichlet/Neumann/Robin boundary conditions
- Perform convergence studies on successively refined meshes
- Export solutions for publication-quality visualization in ParaView

Do **not** use this Skill when:
- You need a quick 1D finite-difference solution → use SciPy `solve_bvp`
- You want a spectral method for periodic domains → use pseudo-spectral libraries
- You need GPU-accelerated large-scale CFD → consider OpenFOAM or Fluidity

---

## Background & Key Concepts

### Variational (Weak) Form

The FEM converts a strong-form PDE into an integral equation by multiplying by a
test function v and integrating by parts. For Poisson's equation:

**Strong form:** −∇²u = f in Ω,  u = uD on ΓD,  ∇u·n = g on ΓN

**Weak form:** Find u ∈ H¹(Ω) such that for all v ∈ H¹₀(Ω):
∫_Ω ∇u·∇v dx = ∫_Ω f v dx + ∫_ΓN g v ds

### Function Spaces

| Space | dolfinx name | Use case |
|---|---|---|
| Continuous Galerkin deg 1 | `("Lagrange", 1)` | Scalar fields, temperature |
| Continuous Galerkin deg 2 | `("Lagrange", 2)` | Higher accuracy, elasticity displacement |
| Discontinuous Galerkin | `("DG", 0)` | Cell-wise constants, flux |
| Nédélec (edge elements) | `("Nedelec1st", 1)` | Electromagnetics, H(curl) |

### Convergence and Error

For Lagrange P1 elements on a quasi-uniform mesh of size h:
- L² error: O(h²)  (one order above approximation degree)
- H¹ error: O(h)

---

## Environment Setup

```bash
# Recommended: use conda with conda-forge (dolfinx + gmsh are complex to compile)
conda create -n fenics-env python=3.11 -y
conda activate fenics-env
conda install -c conda-forge fenics-dolfinx mpich petsc4py gmsh pyvista -y

# Verify installation
python -c "import dolfinx; print('dolfinx version:', dolfinx.__version__)"
python -c "import gmsh; print('gmsh version:', gmsh.__version__)"

# For Docker users (simplest approach)
docker pull dolfinx/dolfinx:stable
docker run -it --rm -v $(pwd):/work dolfinx/dolfinx:stable bash
```

---

## Core Workflow

### Step 1 — Poisson Equation on Unit Square

```python
"""
Solve −∇²u = f on the unit square [0,1]×[0,1]
with homogeneous Dirichlet BC u=0 on ∂Ω.

Manufactured solution: u_exact = sin(πx)sin(πy)
Source term:           f = 2π² sin(πx)sin(πy)
"""

from mpi4py import MPI
import numpy as np
from dolfinx import mesh, fem, io
from dolfinx.fem.petsc import LinearProblem
import ufl


def solve_poisson_unit_square(n_cells: int = 32, degree: int = 1) -> dict:
    """
    Solve the Poisson equation −∇²u = f on the unit square.

    Args:
        n_cells: Number of cells in each direction (total cells = 2*n_cells²).
        degree:  Polynomial degree of Lagrange finite elements.

    Returns:
        Dictionary with keys: uh (solution), L2_error, H1_error.
    """
    # --- Mesh ---
    domain = mesh.create_unit_square(
        MPI.COMM_WORLD, n_cells, n_cells, mesh.CellType.triangle
    )

    # --- Function space ---
    V = fem.functionspace(domain, ("Lagrange", degree))

    # --- Exact solution for manufactured source term ---
    x = ufl.SpatialCoordinate(domain)
    u_exact_expr = ufl.sin(ufl.pi * x[0]) * ufl.sin(ufl.pi * x[1])
    f_expr       = 2.0 * ufl.pi**2 * u_exact_expr

    # --- Dirichlet BC: u = 0 on all boundaries ---
    def boundary_all(x):
        return (
            np.isclose(x[0], 0.0) | np.isclose(x[0], 1.0) |
            np.isclose(x[1], 0.0) | np.isclose(x[1], 1.0)
        )

    boundary_dofs = fem.locate_dofs_geometrical(V, boundary_all)
    u0 = fem.Function(V)
    u0.x.array[:] = 0.0
    bc = fem.dirichletbc(u0, boundary_dofs)

    # --- Variational problem ---
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    a = ufl.inner(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = f_expr * v * ufl.dx

    # --- Solve ---
    problem = LinearProblem(a, L, bcs=[bc],
                            petsc_options={"ksp_type": "cg", "pc_type": "hypre"})
    uh = problem.solve()

    # --- Compute errors ---
    diff = uh - u_exact_expr
    L2_error = float(fem.assemble_scalar(fem.form(ufl.inner(diff, diff) * ufl.dx)) ** 0.5)
    H1_error = float(fem.assemble_scalar(
        fem.form(ufl.inner(ufl.grad(diff), ufl.grad(diff)) * ufl.dx)
    ) ** 0.5)

    print(f"n_cells={n_cells}, degree={degree}: "
          f"L2={L2_error:.2e}, H1={H1_error:.2e}")
    return {"uh": uh, "L2_error": L2_error, "H1_error": H1_error}


def convergence_study() -> None:
    """Run convergence study with successive mesh refinement."""
    print("Convergence study for Poisson on unit square:")
    print(f"{'N':>6}  {'L2 error':>12}  {'H1 error':>12}  {'L2 rate':>8}")
    prev_L2 = None
    for n in [4, 8, 16, 32, 64]:
        result = solve_poisson_unit_square(n_cells=n, degree=1)
        L2 = result["L2_error"]
        rate = (np.log(prev_L2 / L2) / np.log(2.0)) if prev_L2 else float("nan")
        print(f"{n:>6}  {L2:>12.4e}  {result['H1_error']:>12.4e}  {rate:>8.2f}")
        prev_L2 = L2
```

### Step 2 — Linear Elasticity

```python
"""
Solve linear elasticity on a 2D beam under body force (gravity).

Strong form: −div(σ(u)) = f in Ω
σ(u) = λ tr(ε(u)) I + 2μ ε(u)   (Hooke's law, Lamé form)
ε(u) = ½(∇u + ∇uᵀ)             (small-strain tensor)
"""

from mpi4py import MPI
import numpy as np
from dolfinx import mesh, fem, io
from dolfinx.fem.petsc import LinearProblem
import ufl


def solve_linear_elasticity(
    nx: int = 40,
    ny: int = 10,
    E: float = 210e9,     # Young's modulus (Pa), steel
    nu: float = 0.3,      # Poisson's ratio
    rho: float = 7850.0,  # Density (kg/m³)
    g: float = 9.81,      # Gravitational acceleration (m/s²)
    output_xdmf: str = "elasticity.xdmf",
) -> None:
    """
    Solve 2D linear elasticity (plane stress) on a rectangular beam.

    The left end is clamped (u=0), a body force f=(0,-ρg) is applied.
    Exports solution to XDMF for ParaView.

    Args:
        nx:          Cells in x direction.
        ny:          Cells in y direction.
        E:           Young's modulus in Pa.
        nu:          Poisson's ratio.
        rho:         Material density in kg/m³.
        g:           Gravity magnitude in m/s².
        output_xdmf: Output file path.
    """
    # Lamé parameters
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu  = E / (2.0 * (1.0 + nu))

    domain = mesh.create_rectangle(
        MPI.COMM_WORLD,
        [np.array([0.0, 0.0]), np.array([1.0, 0.25])],
        [nx, ny],
        cell_type=mesh.CellType.triangle,
    )

    # Vector function space (displacement u ∈ R²)
    V = fem.functionspace(domain, ("Lagrange", 1, (2,)))

    # Strain and stress tensors
    def epsilon(u):
        return ufl.sym(ufl.nabla_grad(u))

    def sigma(u):
        return lam * ufl.nabla_div(u) * ufl.Identity(2) + 2 * mu * epsilon(u)

    # Body force: gravity
    f = fem.Constant(domain, np.array([0.0, -rho * g]))

    # Clamped BC on left boundary x=0
    def left_boundary(x):
        return np.isclose(x[0], 0.0)

    boundary_dofs = fem.locate_dofs_geometrical(V, left_boundary)
    u_D = fem.Function(V)
    u_D.x.array[:] = 0.0
    bc = fem.dirichletbc(u_D, boundary_dofs)

    # Variational formulation
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    a = ufl.inner(sigma(u), epsilon(v)) * ufl.dx
    L = ufl.inner(f, v) * ufl.dx

    # Solve
    problem = LinearProblem(a, L, bcs=[bc],
                            petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
    uh = problem.solve()
    uh.name = "Displacement"

    # Compute von Mises stress for visualization
    s = sigma(uh) - (1.0 / 3) * ufl.tr(sigma(uh)) * ufl.Identity(2)
    von_mises = ufl.sqrt(1.5 * ufl.inner(s, s))
    W = fem.functionspace(domain, ("DG", 0))
    vm_expr = fem.Expression(von_mises, W.element.interpolation_points())
    vm_func = fem.Function(W)
    vm_func.interpolate(vm_expr)
    vm_func.name = "VonMises"

    # Export to XDMF
    with io.XDMFFile(MPI.COMM_WORLD, output_xdmf, "w") as xdmf:
        xdmf.write_mesh(domain)
        xdmf.write_function(uh)
        xdmf.write_function(vm_func)

    max_disp = np.max(np.abs(uh.x.array))
    print(f"Max displacement: {max_disp:.4e} m")
    print(f"Solution written to {output_xdmf}")


if __name__ == "__main__":
    solve_linear_elasticity()
```

### Step 3 — gmsh Mesh Generation and Import into dolfinx

```python
"""
Use gmsh to generate a structured mesh of a disk with a hole,
then import into dolfinx for FEM analysis.
"""

import gmsh
import numpy as np
from mpi4py import MPI
from dolfinx.io.gmshio import model_to_mesh
from dolfinx import fem, io
import ufl
from dolfinx.fem.petsc import LinearProblem


def create_annular_mesh(
    r_inner: float = 0.2,
    r_outer: float = 1.0,
    mesh_size: float = 0.05,
    output_msh: str = "annulus.msh",
) -> None:
    """
    Create a 2D annular mesh (disk with circular hole) using gmsh.

    Args:
        r_inner:   Inner radius (hole).
        r_outer:   Outer radius.
        mesh_size: Target mesh element size.
        output_msh: Output .msh file path.
    """
    gmsh.initialize()
    gmsh.model.add("annulus")

    # Outer disk
    outer = gmsh.model.occ.addDisk(0, 0, 0, r_outer, r_outer)
    # Inner disk (hole)
    inner = gmsh.model.occ.addDisk(0, 0, 0, r_inner, r_inner)

    # Boolean cut: outer minus inner
    gmsh.model.occ.cut([(2, outer)], [(2, inner)])
    gmsh.model.occ.synchronize()

    # Mesh size field
    gmsh.model.mesh.setSize(gmsh.model.getEntities(0), mesh_size)

    # Physical groups (needed for dolfinx boundary conditions)
    surfaces = gmsh.model.getEntities(2)
    for _, tag in surfaces:
        gmsh.model.addPhysicalGroup(2, [tag], tag)
        gmsh.model.setPhysicalName(2, tag, f"domain_{tag}")

    curves = gmsh.model.getBoundary(surfaces, oriented=False)
    for dim, tag in curves:
        gmsh.model.addPhysicalGroup(1, [abs(tag)], abs(tag))
        gmsh.model.setPhysicalName(1, abs(tag), f"boundary_{abs(tag)}")

    gmsh.model.mesh.generate(2)
    gmsh.model.mesh.optimize("Netgen")
    gmsh.write(output_msh)
    gmsh.finalize()
    print(f"Annular mesh written to {output_msh}")


def solve_poisson_annulus(msh_file: str = "annulus.msh") -> None:
    """
    Import gmsh mesh and solve Poisson equation on the annular domain.

    BC: u=1 on inner boundary, u=0 on outer boundary.
    """
    gmsh.initialize()
    gmsh.open(msh_file)

    domain, cell_tags, facet_tags = model_to_mesh(
        gmsh.model, MPI.COMM_WORLD, 0, gdim=2
    )
    gmsh.finalize()

    V = fem.functionspace(domain, ("Lagrange", 2))

    # Locate facets for BCs by geometric criterion
    def inner_boundary(x):
        return np.sqrt(x[0]**2 + x[1]**2) < 0.25

    def outer_boundary(x):
        return np.sqrt(x[0]**2 + x[1]**2) > 0.9

    dofs_inner = fem.locate_dofs_geometrical(V, inner_boundary)
    dofs_outer = fem.locate_dofs_geometrical(V, outer_boundary)

    u_inner = fem.Function(V); u_inner.x.array[:] = 1.0
    u_outer = fem.Function(V); u_outer.x.array[:] = 0.0

    bcs = [
        fem.dirichletbc(u_inner, dofs_inner),
        fem.dirichletbc(u_outer, dofs_outer),
    ]

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    a = ufl.inner(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = fem.Constant(domain, 0.0) * v * ufl.dx  # Laplace: f=0

    problem = LinearProblem(a, L, bcs=bcs)
    uh = problem.solve()
    uh.name = "u"

    with io.XDMFFile(MPI.COMM_WORLD, "annulus_solution.xdmf", "w") as xdmf:
        xdmf.write_mesh(domain)
        xdmf.write_function(uh)
    print("Annulus Laplace solution saved to annulus_solution.xdmf")
```

---

## Advanced Usage

### Steady Stokes Flow (Velocity-Pressure)

```python
"""
Solve the steady Stokes equations (viscous flow at Re→0) on a channel.

−μ ∇²u + ∇p = f
∇·u = 0

Uses Taylor-Hood P2/P1 elements (LBB-stable mixed formulation).
"""

from mpi4py import MPI
import numpy as np
from dolfinx import mesh, fem
from dolfinx.fem.petsc import LinearProblem
import ufl


def solve_stokes_channel(
    nx: int = 64,
    ny: int = 16,
    mu: float = 1.0,      # dynamic viscosity
    U_max: float = 1.0,   # max inlet velocity
) -> None:
    """
    Solve steady Stokes flow in a 2D channel.
    Parabolic inlet profile, no-slip walls, stress-free outlet.
    """
    domain = mesh.create_rectangle(
        MPI.COMM_WORLD,
        [np.array([0.0, 0.0]), np.array([4.0, 1.0])],
        [nx, ny],
        cell_type=mesh.CellType.triangle,
    )

    # Taylor-Hood P2/P1 elements
    P2 = fem.functionspace(domain, ("Lagrange", 2, (2,)))
    P1 = fem.functionspace(domain, ("Lagrange", 1))

    # Mixed space
    V_el = ufl.VectorElement("Lagrange", domain.ufl_cell(), 2)
    Q_el = ufl.FiniteElement("Lagrange", domain.ufl_cell(), 1)
    W = fem.functionspace(domain, ufl.MixedElement([V_el, Q_el]))

    (u, p) = ufl.TrialFunctions(W)
    (v, q) = ufl.TestFunctions(W)

    f = fem.Constant(domain, np.array([0.0, 0.0]))

    a = (mu * ufl.inner(ufl.grad(u), ufl.grad(v)) * ufl.dx
         - ufl.div(v) * p * ufl.dx
         + q * ufl.div(u) * ufl.dx)
    L = ufl.inner(f, v) * ufl.dx

    # No-slip on top and bottom walls
    def walls(x):
        return np.isclose(x[1], 0.0) | np.isclose(x[1], 1.0)

    # Parabolic inlet profile: u_x = 4*U_max*y*(1-y), u_y=0
    def inlet_velocity(x):
        vals = np.zeros((2, x.shape[1]))
        vals[0] = 4.0 * U_max * x[1] * (1.0 - x[1])
        return vals

    def inlet(x):
        return np.isclose(x[0], 0.0)

    W0, _ = W.sub(0).collapse()
    dofs_walls = fem.locate_dofs_geometrical((W.sub(0), W0), walls)
    dofs_inlet = fem.locate_dofs_geometrical((W.sub(0), W0), inlet)

    u_no_slip = fem.Function(W0); u_no_slip.x.array[:] = 0.0
    u_inflow  = fem.Function(W0); u_inflow.interpolate(inlet_velocity)

    bcs = [
        fem.dirichletbc(u_no_slip, dofs_walls,  W.sub(0)),
        fem.dirichletbc(u_inflow,  dofs_inlet,  W.sub(0)),
    ]

    problem = LinearProblem(a, L, bcs=bcs,
                            petsc_options={"ksp_type": "minres", "pc_type": "hypre"})
    wh = problem.solve()
    print("Stokes channel flow solved. Extract wh.sub(0) for velocity, wh.sub(1) for pressure.")
```

### Time-Dependent Heat Equation

```python
"""
Solve the unsteady heat equation with backward Euler time integration.
∂u/∂t − α∇²u = 0  (α = thermal diffusivity)
"""

from mpi4py import MPI
import numpy as np
from dolfinx import mesh, fem
from dolfinx.fem.petsc import LinearProblem
import ufl


def solve_heat_equation(
    nx: int = 40,
    alpha: float = 0.01,
    T_final: float = 1.0,
    dt: float = 0.01,
) -> None:
    """Solve 2D heat equation with Gaussian initial condition."""
    domain = mesh.create_unit_square(MPI.COMM_WORLD, nx, nx)
    V = fem.functionspace(domain, ("Lagrange", 1))

    u_n = fem.Function(V)
    x = fem.Expression(
        ufl.exp(-50.0 * ((ufl.SpatialCoordinate(domain)[0] - 0.5)**2
                         + (ufl.SpatialCoordinate(domain)[1] - 0.5)**2)),
        V.element.interpolation_points()
    )
    u_n.interpolate(x)

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dt_const = fem.Constant(domain, dt)

    a = (u * v + dt_const * alpha * ufl.inner(ufl.grad(u), ufl.grad(v))) * ufl.dx
    L = u_n * v * ufl.dx

    problem = LinearProblem(a, L, bcs=[],
                            petsc_options={"ksp_type": "cg", "pc_type": "hypre"})

    t = 0.0
    n_steps = int(T_final / dt)
    for step in range(n_steps):
        t += dt
        uh = problem.solve()
        u_n.x.array[:] = uh.x.array[:]
        if step % 20 == 0:
            max_u = np.max(np.abs(uh.x.array))
            print(f"t={t:.3f}: max(u)={max_u:.4f}")
    print("Heat equation time integration complete.")
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `PETSc error: KSP diverged` | Ill-conditioned system or wrong BC | Check BCs; try LU solver: `"ksp_type": "preonly", "pc_type": "lu"` |
| `dolfinx.fem.functionspace` not found | Old API (dolfinx < 0.6) | Use `FunctionSpace(domain, ("CG", 1))` for older versions |
| `gmsh: no surfaces found` | Forgot `synchronize()` after OCC operations | Call `gmsh.model.occ.synchronize()` before meshing |
| Negative Jacobian warning | Poor mesh quality | Call `gmsh.model.mesh.optimize("Netgen")` |
| `MixedElement` import error | Changed API in dolfinx 0.7+ | Use `basix.ufl.mixed_element` or `BlockedElement` |
| XDMF file not readable in ParaView | H5 file missing | Both `.xdmf` and `.h5` files must be in the same directory |
| Slow solve for large meshes | Dense direct solver | Switch to iterative solver with HYPRE preconditioner |

---

## External Resources

- FEniCS/dolfinx documentation: <https://docs.fenicsproject.org/>
- FEniCS tutorial (Langtangen & Logg): <https://fenicsproject.org/pub/tutorial/>
- gmsh documentation: <https://gmsh.info/doc/texinfo/gmsh.html>
- ParaView visualization: <https://www.paraview.org>
- Brenner & Scott, "The Mathematical Theory of Finite Element Methods", 3rd ed.

---

## Examples

### Example 1 — Full Poisson Convergence Study

```python
if __name__ == "__main__":
    print("=== Poisson Convergence Study ===")
    convergence_study()
    print()
    print("=== Poisson on Unit Square (n=64) ===")
    result = solve_poisson_unit_square(n_cells=64, degree=2)
    print(f"L2 error with P2 elements: {result['L2_error']:.2e}")
```

### Example 2 — Cantilever Beam Under Gravity

```python
if __name__ == "__main__":
    print("=== Linear Elasticity: Steel Cantilever Beam ===")
    solve_linear_elasticity(
        nx=80, ny=20,
        E=210e9,    # Steel Young's modulus
        nu=0.3,
        rho=7850.0,
        g=9.81,
        output_xdmf="steel_beam.xdmf",
    )
    print("Open steel_beam.xdmf in ParaView to visualize displacement and von Mises stress.")
```

### Example 3 — gmsh Annulus Mesh and Laplace Solve

```python
if __name__ == "__main__":
    print("=== gmsh Annular Mesh + Laplace Equation ===")
    create_annular_mesh(r_inner=0.2, r_outer=1.0, mesh_size=0.05)
    solve_poisson_annulus("annulus.msh")
    print("Open annulus_solution.xdmf in ParaView.")
```

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-03-17 | Initial release — Poisson, elasticity, Stokes, heat equation, gmsh integration |

"""Extended Abaqus API tools: loads, BCs, constraints, assembly, interactions, steps, mesh, output."""

from __future__ import annotations

from typing import Any

_run_python = None

def set_run_python(fn):
    global _run_python
    _run_python = fn


# =============================================================================
#  More Loads
# =============================================================================

async def create_concentrated_force(
    name: str,
    region_name: str,
    force: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a concentrated force on a vertex or reference point."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.ConcentratedForce(
        name={name!r}, createStepName={step_name!r},
        region=region, cf1={force[0]!r}, cf2={force[1]!r}, cf3={force[2]!r})
    result = {{"ok": True, "load": {name!r}, "force": list({force!r}), "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_moment_load(
    name: str,
    region_name: str,
    moment: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a moment load on a vertex or reference point."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.Moment(
        name={name!r}, createStepName={step_name!r},
        region=region, cm1={moment[0]!r}, cm2={moment[1]!r}, cm3={moment[2]!r})
    result = {{"ok": True, "load": {name!r}, "moment": list({moment!r}), "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_shell_edge_load(
    name: str,
    region_name: str,
    magnitude: float,
    direction: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a shell edge load (force per unit length)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.ShellEdgeLoad(
        name={name!r}, createStepName={step_name!r},
        region=region, magnitude={magnitude!r},
        direction={list(direction)!r})
    result = {{"ok": True, "load": {name!r}, "magnitude": {magnitude!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_line_load(
    name: str,
    region_name: str,
    magnitude: float,
    direction: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a line load (force per unit length) on an edge set."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.LineLoad(
        name={name!r}, createStepName={step_name!r},
        region=region, comp1={direction[0]!r}*{magnitude!r},
        comp2={direction[1]!r}*{magnitude!r},
        comp3={direction[2]!r}*{magnitude!r})
    result = {{"ok": True, "load": {name!r}, "magnitude": {magnitude!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_body_force(
    name: str,
    magnitude: float,
    direction: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a body force (force per unit volume) on the entire model."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.BodyForce(
        name={name!r}, createStepName={step_name!r},
        comp1={direction[0]!r}*{magnitude!r},
        comp2={direction[1]!r}*{magnitude!r},
        comp3={direction[2]!r}*{magnitude!r},
        distributionType=UNIFORM)
    result = {{"ok": True, "load": {name!r}, "magnitude": {magnitude!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_heat_flux_load(
    name: str,
    region_name: str,
    magnitude: float,
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a surface heat flux load."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.surfaces[{region_name!r}]
    model.SurfaceHeatFlux(
        name={name!r}, createStepName={step_name!r},
        region=region, magnitude={magnitude!r})
    result = {{"ok": True, "load": {name!r}, "magnitude": {magnitude!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_body_heat_flux(
    name: str,
    magnitude: float,
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a body heat flux (heat generation per unit volume)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    model.BodyHeatFlux(
        name={name!r}, createStepName={step_name!r},
        magnitude={magnitude!r})
    result = {{"ok": True, "load": {name!r}, "magnitude": {magnitude!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_connector_force(
    name: str,
    region_name: str,
    force: tuple[float, float, float],
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a connector force on a connector/wire set."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.ConnectorForce(
        name={name!r}, createStepName={step_name!r},
        region=region, f1={force[0]!r}, f2={force[1]!r}, f3={force[2]!r})
    result = {{"ok": True, "load": {name!r}, "force": list({force!r}), "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More BCs
# =============================================================================

async def create_symmetry_bc(
    name: str,
    region_name: str,
    symmetry_type: str = "ZSYMM",
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a symmetry boundary condition.

    Args:
        symmetry_type: "XSYMM", "YSYMM", "ZSYMM", "XASYMM", "YASYMM", "ZASYMM"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    sym_map = {{
        "XSYMM": XSYMM, "YSYMM": YSYMM, "ZSYMM": ZSYMM,
        "XASYMM": XASYMM, "YASYMM": YASYMM, "ZASYMM": ZASYMM,
    }}
    sym = sym_map.get({symmetry_type!r}, ZSYMM)
    model.SymmetryBC(
        name={name!r}, createStepName={step_name!r},
        region=region, symmetryType=sym)
    result = {{"ok": True, "bc": {name!r}, "type": {symmetry_type!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_pinned_bc(
    name: str,
    region_name: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a pinned BC (U1=U2=U3=0, rotations free)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.DisplacementBC(
        name={name!r}, createStepName={step_name!r},
        region=region, u1=0.0, u2=0.0, u3=0.0)
    result = {{"ok": True, "bc": {name!r}, "type": "pinned", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_velocity_bc(
    name: str,
    region_name: str,
    v1: float | None = None,
    v2: float | None = None,
    v3: float | None = None,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a velocity boundary condition."""
    kwargs = []
    if v1 is not None:
        kwargs.append(f"v1={v1!r}")
    if v2 is not None:
        kwargs.append(f"v2={v2!r}")
    if v3 is not None:
        kwargs.append(f"v3={v3!r}")
    kwargs_str = ", ".join(kwargs)
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.VelocityBC(
        name={name!r}, createStepName={step_name!r}, region=region, {kwargs_str})
    result = {{"ok": True, "bc": {name!r}, "type": "velocity", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_acceleration_bc(
    name: str,
    region_name: str,
    a1: float | None = None,
    a2: float | None = None,
    a3: float | None = None,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an acceleration boundary condition."""
    kwargs = []
    if a1 is not None:
        kwargs.append(f"a1={a1!r}")
    if a2 is not None:
        kwargs.append(f"a2={a2!r}")
    if a3 is not None:
        kwargs.append(f"a3={a3!r}")
    kwargs_str = ", ".join(kwargs)
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.AccelerationBC(
        name={name!r}, createStepName={step_name!r}, region=region, {kwargs_str})
    result = {{"ok": True, "bc": {name!r}, "type": "acceleration", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_temperature_bc(
    name: str,
    region_name: str,
    magnitude: float,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a temperature boundary condition."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.TemperatureBC(
        name={name!r}, createStepName={step_name!r},
        region=region, magnitude={magnitude!r})
    result = {{"ok": True, "bc": {name!r}, "type": "temperature", "magnitude": {magnitude!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_connector_displacement_bc(
    name: str,
    region_name: str,
    u1: float | None = None,
    u2: float | None = None,
    u3: float | None = None,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a connector displacement BC."""
    kwargs = []
    if u1 is not None:
        kwargs.append(f"u1={u1!r}")
    if u2 is not None:
        kwargs.append(f"u2={u2!r}")
    if u3 is not None:
        kwargs.append(f"u3={u3!r}")
    kwargs_str = ", ".join(kwargs)
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.ConnectorDisplacementBC(
        name={name!r}, createStepName={step_name!r}, region=region, {kwargs_str})
    result = {{"ok": True, "bc": {name!r}, "type": "connector_displacement", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More Constraints
# =============================================================================

async def create_rigid_body_constraint(
    name: str,
    region_name: str,
    ref_point_name: str = "",
    body_type: str = "BODY",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a rigid body constraint.

    Args:
        body_type: "BODY" or "PIN" (pin constrains only translational DOFs)
    """
    ref_block = ""
    if ref_point_name:
        ref_block = f"refPointRegion=model.rootAssembly.referencePoints[{ref_point_name!r}],"
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    pin_map = {{"BODY": BODY, "PIN": PIN}}
    pin = pin_map.get({body_type!r}, BODY)
    model.RigidBody(
        name={name!r}, {ref_block}
        bodyRegion=region, pinRegion=pin)
    result = {{"ok": True, "constraint": {name!r}, "type": "rigid_body", "body_type": {body_type!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_coupling_constraint(
    name: str,
    control_point: str,
    surface_name: str,
    coupling_type: str = "KINEMATIC",
    u1: bool = True,
    u2: bool = True,
    u3: bool = True,
    ur1: bool = True,
    ur2: bool = True,
    ur3: bool = True,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a coupling constraint between a reference point and a surface.

    Args:
        coupling_type: "KINEMATIC", "DISTRIBUTING", or "STRUCTURAL"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    cp = model.rootAssembly.sets[{control_point!r}]
    surf = model.rootAssembly.surfaces[{surface_name!r}]
    ct_map = {{"KINEMATIC": KINEMATIC, "DISTRIBUTING": DISTRIBUTING, "STRUCTURAL": STRUCTURAL}}
    ct = ct_map.get({coupling_type!r}, KINEMATIC)
    model.Coupling(
        name={name!r}, controlPoint=cp, surface=surf,
        influenceRadius=WHOLE_SURFACE, couplingType=ct,
        u1=ON if {u1!r} else OFF,
        u2=ON if {u2!r} else OFF,
        u3=ON if {u3!r} else OFF,
        ur1=ON if {ur1!r} else OFF,
        ur2=ON if {ur2!r} else OFF,
        ur3=ON if {ur3!r} else OFF)
    result = {{"ok": True, "constraint": {name!r}, "type": {coupling_type!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_mpc_constraint(
    name: str,
    mpc_type: str,
    control_point: str,
    surface_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an MPC constraint.

    Args:
        mpc_type: "BEAM", "LINK", "PIN", "TIE", "ELBOW", "SLIDER", "PLANAR", "REVOLUTE", "UNIVERSAL", "WELD"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    cp = model.rootAssembly.sets[{control_point!r}]
    surf = model.rootAssembly.surfaces[{surface_name!r}]
    mpc_map = {{
        "BEAM": BEAM_MPC, "LINK": LINK_MPC, "PIN": PIN_MPC,
        "TIE": TIE_MPC, "ELBOW": ELBOW_MPC, "SLIDER": SLIDER_MPC,
        "PLANAR": PLANAR_MPC, "REVOLUTE": REVOLUTE_MPC, "UNIVERSAL": UNIVERSAL_MPC,
        "WELD": WELD_MPC,
    }}
    mpc = mpc_map.get({mpc_type!r}, BEAM_MPC)
    model.MPC(
        name={name!r}, controlPoint=cp, surface=surf,
        mpcType=mpc, influenceRadius=WHOLE_SURFACE)
    result = {{"ok": True, "constraint": {name!r}, "mpc_type": {mpc_type!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_embedded_region(
    name: str,
    embedded_region: str,
    host_region: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an embedded region constraint (e.g., reinforcement in concrete)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    emb = model.rootAssembly.sets[{embedded_region!r}]
    host = model.rootAssembly.sets[{host_region!r}]
    model.EmbeddedRegion(
        name={name!r}, embeddedRegion=emb, hostRegion=host)
    result = {{"ok": True, "constraint": {name!r}, "embedded": {embedded_region!r}, "host": {host_region!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_equation_constraint(
    name: str,
    terms: list[tuple[float, str, int]],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a linear equation constraint.

    Args:
        terms: list of (coefficient, set_name, dof) tuples.
            e.g., [(1.0, "Set-1", 1), (-1.0, "Set-2", 1)] for u1(Set-1) = u1(Set-2)
    """
    terms_code = ", ".join(
        f"({coeff!r}, {set_name!r}, {dof!r})"
        for coeff, set_name, dof in terms
    )
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    model.Equation(
        name={name!r},
        terms=({terms_code}))
    result = {{"ok": True, "constraint": {name!r}, "num_terms": {len(terms)!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Assembly Operations
# =============================================================================

async def create_instance(
    part_name: str,
    instance_name: str = "",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an instance of a part in the assembly."""
    inst = instance_name if instance_name else part_name
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.Instance(
        name={inst!r}, part=model.parts[{part_name!r}], dependent=ON)
    result = {{"ok": True, "instance": {inst!r}, "part": {part_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def translate_instance(
    instance_name: str,
    vector: tuple[float, float, float],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Translate an instance in the assembly."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    inst.translate(vector={list(vector)!r})
    result = {{"ok": True, "instance": {instance_name!r}, "translation": list({vector!r})}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def rotate_instance(
    instance_name: str,
    axis_point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
    angle: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Rotate an instance around an axis by a given angle (degrees)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    inst.rotate(
        axisPoint={list(axis_point)!r},
        axisDirection={list(axis_direction)!r},
        angle={angle!r})
    result = {{"ok": True, "instance": {instance_name!r}, "angle": {angle!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_reference_point(
    point: tuple[float, float, float],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a reference point in the assembly."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    rp_id = model.rootAssembly.ReferencePoint(point={list(point)!r})
    result = {{"ok": True, "reference_point_id": rp_id.id, "point": list({point!r})}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Sets and Surfaces
# =============================================================================

async def create_set_by_face(
    set_name: str,
    instance_name: str,
    face_indices: list[int],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a set from faces of an instance."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    faces = inst.faces[{face_indices!r}]
    model.rootAssembly.Set(name={set_name!r}, faces=faces)
    result = {{"ok": True, "set": {set_name!r}, "faces": {face_indices!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_set_by_edges(
    set_name: str,
    instance_name: str,
    edge_indices: list[int],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a set from edges of an instance."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    edges = inst.edges[{edge_indices!r}]
    model.rootAssembly.Set(name={set_name!r}, edges=edges)
    result = {{"ok": True, "set": {set_name!r}, "edges": {edge_indices!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_set_by_vertices(
    set_name: str,
    instance_name: str,
    vertex_indices: list[int],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a set from vertices of an instance."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    vertices = inst.vertices[{vertex_indices!r}]
    model.rootAssembly.Set(name={set_name!r}, vertices=vertices)
    result = {{"ok": True, "set": {set_name!r}, "vertices": {vertex_indices!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_surface(
    surface_name: str,
    instance_name: str,
    face_indices: list[int],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a surface from faces of an instance."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    faces = inst.faces[{face_indices!r}]
    model.rootAssembly.Surface(
        name={surface_name!r}, side1Faces=faces)
    result = {{"ok": True, "surface": {surface_name!r}, "faces": {face_indices!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_surface_by_edges(
    surface_name: str,
    instance_name: str,
    edge_indices: list[int],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a surface from edges of an instance (for shell/beam)."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    edges = inst.edges[{edge_indices!r}]
    model.rootAssembly.Surface(
        name={surface_name!r}, side1Edges=edges)
    result = {{"ok": True, "surface": {surface_name!r}, "edges": {edge_indices!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def find_face_by_coordinate(
    instance_name: str,
    coordinate: tuple[float, float, float],
    tolerance: float = 0.01,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Find the face index of an instance closest to the given coordinate."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    target = {list(coordinate)!r}
    best_idx = -1
    best_dist = float("inf")
    for face in inst.faces:
        center = face.getCentroid()
        dist = ((center[0]-target[0])**2 + (center[1]-target[1])**2 + (center[2]-target[2])**2)**0.5
        if dist < best_dist:
            best_dist = dist
            best_idx = face.index
    if best_dist <= {tolerance!r}:
        result = {{"ok": True, "face_index": best_idx, "distance": best_dist, "coordinate": list({coordinate!r})}}
    else:
        result = {{"ok": True, "face_index": best_idx, "distance": best_dist, "warning": "Distance exceeds tolerance, verify the face"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def find_edge_by_coordinate(
    instance_name: str,
    coordinate: tuple[float, float, float],
    tolerance: float = 0.01,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Find the edge index of an instance closest to the given coordinate."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    target = {list(coordinate)!r}
    best_idx = -1
    best_dist = float("inf")
    for edge in inst.edges:
        center = edge.getCentroid()
        dist = ((center[0]-target[0])**2 + (center[1]-target[1])**2 + (center[2]-target[2])**2)**0.5
        if dist < best_dist:
            best_dist = dist
            best_idx = edge.index
    if best_dist <= {tolerance!r}:
        result = {{"ok": True, "edge_index": best_idx, "distance": best_dist, "coordinate": list({coordinate!r})}}
    else:
        result = {{"ok": True, "edge_index": best_idx, "distance": best_dist, "warning": "Distance exceeds tolerance, verify the edge"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Interactions / Contact
# =============================================================================

async def create_contact_property(
    name: str,
    friction_coefficient: float = 0.0,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a contact interaction property."""
    friction_block = ""
    if friction_coefficient > 0:
        friction_block = f"prop.TangentialBehavior(formulation=FRICTIONLESS)"
        friction_block = f"prop.TangentialBehavior(formulation=PENALTY, table=(({friction_coefficient!r},),))"
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    prop = model.ContactProperty(name={name!r})
    prop.NormalBehavior(allowSeparation=ON)
    {friction_block}
    result = {{"ok": True, "contact_property": {name!r}, "friction": {friction_coefficient!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_surface_to_surface_contact(
    name: str,
    master_surface: str,
    slave_surface: str,
    interaction_property: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a surface-to-surface contact interaction."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    master = model.rootAssembly.surfaces[{master_surface!r}]
    slave = model.rootAssembly.surfaces[{slave_surface!r}]
    model.SurfaceToSurfaceContactStd(
        name={name!r}, createStepName={step_name!r},
        master=master, slave=slave,
        interactionProperty={interaction_property!r})
    result = {{"ok": True, "interaction": {name!r}, "master": {master_surface!r}, "slave": {slave_surface!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_surface_to_surface_contact_exp(
    name: str,
    master_surface: str,
    slave_surface: str,
    interaction_property: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a surface-to-surface contact interaction for explicit analysis."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    master = model.rootAssembly.surfaces[{master_surface!r}]
    slave = model.rootAssembly.surfaces[{slave_surface!r}]
    model.SurfaceToSurfaceContactExp(
        name={name!r}, createStepName={step_name!r},
        master=master, slave=slave,
        interactionProperty={interaction_property!r})
    result = {{"ok": True, "interaction": {name!r}, "master": {master_surface!r}, "slave": {slave_surface!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_general_contact(
    name: str,
    interaction_property: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a general contact (all-inclusive) interaction."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.ContactStd(
        name={name!r}, createStepName={step_name!r},
        useAllstar=ON, interactionProperty={interaction_property!r})
    result = {{"ok": True, "interaction": {name!r}, "type": "general_contact"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_general_contact_exp(
    name: str,
    interaction_property: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a general contact for explicit analysis."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.ContactExp(
        name={name!r}, createStepName={step_name!r},
        useAllstar=ON, interactionProperty={interaction_property!r})
    result = {{"ok": True, "interaction": {name!r}, "type": "general_contact_exp"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More Step Types
# =============================================================================

async def create_explicit_step(
    name: str,
    time_period: float = 1.0,
    description: str = "",
    previous_step: str = "Initial",
    nlgeom: bool = True,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an Explicit Dynamics step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    nl = ON if {nlgeom!r} else OFF
    model = mdb.models[{model_name!r}]
    model.ExplicitDynamicsStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, timePeriod={time_period!r},
        nlgeom=nl)
    result = {{"ok": True, "step": {name!r}, "type": "explicit", "time_period": {time_period!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_heat_transfer_step(
    name: str,
    time_period: float = 1.0,
    description: str = "",
    previous_step: str = "Initial",
    initial_inc: float = 0.1,
    max_inc: float = 1.0,
    min_inc: float = 1e-5,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Heat Transfer step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.HeatTransferStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, timePeriod={time_period!r},
        initialInc={initial_inc!r}, maxInc={max_inc!r}, minInc={min_inc!r})
    result = {{"ok": True, "step": {name!r}, "type": "heat_transfer", "time_period": {time_period!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_coupled_temp_disp_step(
    name: str,
    time_period: float = 1.0,
    description: str = "",
    previous_step: str = "Initial",
    initial_inc: float = 0.1,
    max_inc: float = 1.0,
    min_inc: float = 1e-5,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Coupled Temperature-Displacement step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.CoupledTempDisplacementStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, timePeriod={time_period!r},
        initialInc={initial_inc!r}, maxInc={max_inc!r}, minInc={min_inc!r})
    result = {{"ok": True, "step": {name!r}, "type": "coupled_temp_disp", "time_period": {time_period!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_dynamic_implicit_step(
    name: str,
    time_period: float = 1.0,
    description: str = "",
    previous_step: str = "Initial",
    initial_inc: float = 0.1,
    max_inc: float = 1.0,
    min_inc: float = 1e-8,
    nlgeom: bool = False,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Dynamic Implicit step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    nl = ON if {nlgeom!r} else OFF
    model = mdb.models[{model_name!r}]
    model.ImplicitDynamicsStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, timePeriod={time_period!r},
        initialInc={initial_inc!r}, maxInc={max_inc!r}, minInc={min_inc!r},
        nlgeom=nl)
    result = {{"ok": True, "step": {name!r}, "type": "dynamic_implicit", "time_period": {time_period!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_static_riks_step(
    name: str,
    description: str = "",
    previous_step: str = "Initial",
    initial_arc_inc: float = 0.1,
    max_arc_inc: float = 1.0,
    min_arc_inc: float = 1e-8,
    max_increments: int = 100,
    nlgeom: bool = True,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Static Riks step (for post-buckling analysis)."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    nl = ON if {nlgeom!r} else OFF
    model = mdb.models[{model_name!r}]
    model.StaticRiksStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, nlgeom=nl,
        initialArcInc={initial_arc_inc!r}, maxArcInc={max_arc_inc!r},
        minArcInc={min_arc_inc!r}, maxNumInc={max_increments!r})
    result = {{"ok": True, "step": {name!r}, "type": "static_riks"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_buckle_step(
    name: str,
    num_modes: int = 10,
    description: str = "",
    previous_step: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Linear Buckle step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.BuckleStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, numEigen={num_modes!r})
    result = {{"ok": True, "step": {name!r}, "type": "buckle", "num_modes": {num_modes!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Output Requests
# =============================================================================

async def create_field_output_request(
    name: str = "F-Output-1",
    step_name: str = "",
    variables: list[str] | None = None,
    frequency: int = 1,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a field output request for a specific step.

    Args:
        variables: list of variable names, e.g. ["S", "E", "U", "RF"]
        frequency: output frequency (every N increments)
    """
    var_str = repr(variables) if variables else "('S', 'E', 'U', 'RF', 'CF')"
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    step_name = {step_name!r}
    if not step_name:
        steps = list(model.steps.keys())
        step_name = steps[-1] if steps else "Initial"
    model.fieldOutputRequests[{name!r}].setValues(
        variables={var_str}, frequency={frequency!r})
    result = {{"ok": True, "field_output": {name!r}, "step": step_name, "variables": {var_str}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_history_output_request(
    name: str = "H-Output-1",
    step_name: str = "",
    variables: list[str] | None = None,
    region_name: str = "",
    frequency: int = 1,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a history output request.

    Args:
        variables: list of variable names
        region_name: set name for the region (empty = whole model)
        frequency: output frequency (every N increments)
    """
    var_str = repr(variables) if variables else "('U', 'RF', 'CF')"
    region_block = ""
    if region_name:
        region_block = f"region=model.rootAssembly.sets[{region_name!r}],"
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    step_name = {step_name!r}
    if not step_name:
        steps = list(model.steps.keys())
        step_name = steps[-1] if steps else "Initial"
    model.historyOutputRequests[{name!r}].setValues(
        variables={var_str}, {region_block} frequency={frequency!r})
    result = {{"ok": True, "history_output": {name!r}, "step": step_name, "variables": {var_str}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Mesh Controls
# =============================================================================

async def seed_part(
    part_name: str,
    size: float,
    deviation_factor: float = 0.1,
    min_size_factor: float = 0.1,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Seed a part with a global element size."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    part = model.parts[{part_name!r}]
    part.seedPart(
        size={size!r},
        deviationFactor={deviation_factor!r},
        minSizeFactor={min_size_factor!r})
    result = {{"ok": True, "part": {part_name!r}, "seed_size": {size!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def set_element_type(
    part_name: str,
    elem_type: str = "C3D8R",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Set the element type for a part.

    Args:
        elem_type: e.g., "C3D8R", "C3D8", "C3D10", "CPS4R", "CPE4R", "S4R", "B31"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    part = model.parts[{part_name!r}]
    elem_types = (ElementType(elemCode={elem_type!r}, elemLibrary=STANDARD),)
    region = part.sets["All"]
    part.setElementType(regions=(region,), elemTypes=elem_types)
    result = {{"ok": True, "part": {part_name!r}, "element_type": {elem_type!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def set_mesh_control(
    part_name: str,
    algorithm: str = "MEDIAL_AXIS",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Set mesh control algorithm for a part.

    Args:
        algorithm: "MEDIAL_AXIS", "ADVANCING_FRONT", or "SWEEP"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    part = model.parts[{part_name!r}]
    algo_map = {{
        "MEDIAL_AXIS": MEDIAL_AXIS,
        "ADVANCING_FRONT": ADVANCING_FRONT,
        "SWEEP": SWEEP,
    }}
    algo = algo_map.get({algorithm!r}, MEDIAL_AXIS)
    part.setMeshControls(algorithm=algo)
    result = {{"ok": True, "part": {part_name!r}, "algorithm": {algorithm!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Amplitude
# =============================================================================

async def create_tabular_amplitude(
    name: str,
    data: list[tuple[float, float]],
    smooth: str = "SOLVER_DEFAULT",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a tabular amplitude.

    Args:
        data: list of (time/frequency, amplitude) tuples
        smooth: "SOLVER_DEFAULT", "STEP", "LINEAR", "SMOOTH"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    smooth_map = {{
        "SOLVER_DEFAULT": SOLVER_DEFAULT,
        "STEP": STEP, "LINEAR": LINEAR, "SMOOTH": SMOOTH,
    }}
    sm = smooth_map.get({smooth!r}, SOLVER_DEFAULT)
    model.TabularAmplitude(name={name!r}, data={data!r}, smooth=sm)
    result = {{"ok": True, "amplitude": {name!r}, "data_points": {len(data)!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_smooth_step_amplitude(
    name: str,
    data: list[tuple[float, float]],
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a smooth step amplitude."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.SmoothStepAmplitude(name={name!r}, data={data!r})
    result = {{"ok": True, "amplitude": {name!r}, "data_points": {len(data)!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_periodic_amplitude(
    name: str,
    frequency: float,
    start_time: float,
    max_amplitude: float,
    a0: float = 0.0,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a periodic (Fourier series) amplitude."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.PeriodicAmplitude(
        name={name!r}, frequency={frequency!r},
        start={start_time!r}, a_0={a0!r}, data=(({max_amplitude!r},),))
    result = {{"ok": True, "amplitude": {name!r}, "frequency": {frequency!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More Post-Processing
# =============================================================================

async def get_xy_data(
    odb_path: str,
    variable: str = "S",
    component: str = "Mises",
    node_label: int | None = None,
    element_label: int | None = None,
    step_name: str = "",
    frame_index: int = -1,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Extract XY data from an ODB.

    Args:
        node_label: node label for history-based extraction
        element_label: element label for element-based extraction
        frame_index: -1 for last frame
    """
    node_select = f"nodeLabel={node_label!r}" if node_label else ""
    elem_select = f"elementLabel={element_label!r}" if element_label else ""
    code = f"""
import json
try:
    from odbAccess import openOdb
    odb = openOdb({odb_path!r})
    step_name = {step_name!r}
    if not step_name:
        step_name = list(odb.steps.keys())[-1]
    step = odb.steps[step_name]
    frame = step.frames[{frame_index!r}]

    if {node_label is not None!r}:
        field = frame.fieldOutputs[{variable!r}]
        sub = field.getSubset(region=odb.rootAssembly.nodeSets["ALL NODES"], position=NODAL)
        values = []
        for v in sub.values:
            if v.nodeLabel == {node_label!r}:
                values.append({{"node": v.nodeLabel, "value": v.data}})
        result = {{"ok": True, "node": {node_label!r}, "values": values}}
    elif {element_label is not None!r}:
        field = frame.fieldOutputs[{variable!r}]
        sub = field.getSubset(position=INTEGRATION_POINT, elementType="ALL")
        values = []
        for v in sub.values:
            if v.elementLabel == {element_label!r}:
                values.append({{"element": v.elementLabel, "integration_point": v.integrationPoint, "value": v.data}})
        result = {{"ok": True, "element": {element_label!r}, "values": values}}
    else:
        result = {{"ok": False, "error": "Specify node_label or element_label"}}
    odb.close()
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def get_history_output(
    odb_path: str,
    variable: str = "",
    step_name: str = "",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Get history output data from an ODB."""
    code = f"""
import json
try:
    from odbAccess import openOdb
    odb = openOdb({odb_path!r})
    step_name = {step_name!r}
    if not step_name:
        step_name = list(odb.steps.keys())[-1]
    step = odb.steps[step_name]
    regions = list(step.historyRegions.keys())
    result = {{"ok": True, "step": step_name, "history_regions": regions}}
    if {variable!r}:
        for region_name in regions:
            region = step.historyRegions[region_name]
            if {variable!r} in region.historyOutputs:
                ho = region.historyOutputs[{variable!r}]
                data = [(t, v) for (t, v) in ho.data]
                result["data"] = data[:20]
                break
    odb.close()
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def get_node_coordinates(
    instance_name: str,
    node_label: int,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Get the coordinates of a specific node."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    node = inst.nodes[{node_label!r}]
    result = {{"ok": True, "node": {node_label!r}, "coordinates": node.coordinates}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def list_elements(
    instance_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """List elements in an instance with their type and connectivity."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    elements = []
    for elem in list(inst.elements)[:50]:
        elements.append({{
            "label": elem.label,
            "type": elem.type,
            "connectivity": list(elem.connectivity),
        }})
    result = {{"ok": True, "total": len(inst.elements), "sample": elements}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def list_nodes(
    instance_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """List nodes in an instance."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    inst = model.rootAssembly.instances[{instance_name!r}]
    nodes = []
    for node in list(inst.nodes)[:50]:
        nodes.append({{"label": node.label, "coordinates": node.coordinates}})
    result = {{"ok": True, "total": len(inst.nodes), "sample": nodes}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More Materials
# =============================================================================

async def create_hyperelastic_material(
    name: str,
    c10: float,
    c01: float = 0.0,
    d1: float = 0.0,
    density: float | None = None,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a hyperelastic (Mooney-Rivlin) material."""
    density_block = ""
    if density is not None:
        density_block = f"mat.Density(table=(({density!r},)),)"
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.Material(name={name!r})
    mat.Hyperelastic(
        type=MOONEY_RIVLIN, table=(({c10!r}, {c01!r}, {d1!r}),))
    {density_block}
    result = {{"ok": True, "material": {name!r}, "type": "hyperelastic_mooney_rivlin"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_viscoelastic_material(
    name: str,
    youngs_modulus: float,
    poisson_ratio: float,
    relaxation_data: list[tuple[float, float, float]],
    density: float | None = None,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a viscoelastic material with Prony series.

    Args:
        relaxation_data: list of (g_i, k_i, tau_i) Prony series terms
    """
    density_block = ""
    if density is not None:
        density_block = f"mat.Density(table=(({density!r},)),)"
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.Material(name={name!r})
    mat.Elastic(table=(({youngs_modulus!r}, {poisson_ratio!r}),))
    mat.Viscoelastic(table={relaxation_data!r})
    {density_block}
    result = {{"ok": True, "material": {name!r}, "type": "viscoelastic"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_thermal_expansion(
    material_name: str,
    expansion_coefficient: float,
    reference_temperature: float = 0.0,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Add thermal expansion to an existing material."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.materials[{material_name!r}]
    mat.Expansion(
        table=(({expansion_coefficient!r},),),
        zero={reference_temperature!r})
    result = {{"ok": True, "material": {material_name!r}, "expansion_coefficient": {expansion_coefficient!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_thermal_conductivity(
    material_name: str,
    conductivity: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Add thermal conductivity to an existing material."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.materials[{material_name!r}]
    mat.Conductivity(table=(({conductivity!r},),))
    result = {{"ok": True, "material": {material_name!r}, "conductivity": {conductivity!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_specific_heat(
    material_name: str,
    specific_heat: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Add specific heat to an existing material."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.materials[{material_name!r}]
    mat.SpecificHeat(table=(({specific_heat!r},),))
    result = {{"ok": True, "material": {material_name!r}, "specific_heat": {specific_heat!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_damage_initiation(
    material_name: str,
    fracture_strain: float,
    stress_triaxiality: float = 0.33,
    strain_rate: float = 0.0,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Add ductile damage initiation to a material."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    mat = model.materials[{material_name!r}]
    mat.DuctileDamageInitiation(
        table=(({fracture_strain!r}, {stress_triaxiality!r}, {strain_rate!r}),))
    result = {{"ok": True, "material": {material_name!r}, "fracture_strain": {fracture_strain!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  More Geometry
# =============================================================================

async def create_part_sphere(
    name: str,
    radius: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a 3D sphere part."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    sketch = model.ConstrainedSketch(name="__sk__", sheetSize=200.0)
    sketch.ArcByCenterEnds(center=(0.0, 0.0), point1=({radius!r}, 0.0), point2=(-{radius!r}, 0.0))
    sketch.Line(point1=(-{radius!r}, 0.0), point2=({radius!r}, 0.0))
    part = model.Part(name={name!r}, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidRevolve(sketch=sketch, angle=360.0)
    del model.sketches["__sk__"]
    result = {{"ok": True, "part": {name!r}, "radius": {radius!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_part_beam(
    name: str,
    length: float,
    point1: tuple[float, float, float] = (0.0, 0.0, 0.0),
    point2: tuple[float, float, float] = (0.0, 0.0, 0.0),
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a 3D wire (beam) part."""
    if point2 == (0.0, 0.0, 0.0):
        point2 = (length, 0.0, 0.0)
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    part = model.Part(name={name!r}, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.WirePolyLine(points=({list(point1)!r}, {list(point2)!r}))
    result = {{"ok": True, "part": {name!r}, "length": {length!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_part_plate(
    name: str,
    width: float,
    height: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a 3D shell (planar) part."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    sketch = model.ConstrainedSketch(name="__sk__", sheetSize=200.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=({width!r}, {height!r}))
    part = model.Part(name={name!r}, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShell(sketch=sketch)
    del model.sketches["__sk__"]
    result = {{"ok": True, "part": {name!r}, "width": {width!r}, "height": {height!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


# =============================================================================
#  Section Types
# =============================================================================

async def create_beam_section(
    name: str,
    material_name: str,
    profile_name: str = "",
    integration: str = "BEFORE_ANALYSIS",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a beam section.

    Args:
        integration: "BEFORE_ANALYSIS" or "DURING_ANALYSIS"
    """
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    int_map = {{"BEFORE_ANALYSIS": BEFORE_ANALYSIS, "DURING_ANALYSIS": DURING_ANALYSIS}}
    intv = int_map.get({integration!r}, BEFORE_ANALYSIS)
    profile_name = {profile_name!r}
    if profile_name:
        model.BeamSection(
            name={name!r}, material={material_name!r},
            integration=intv, profile=profile_name)
    else:
        model.BeamSection(
            name={name!r}, material={material_name!r},
            integration=intv, table=((1.0, 1.0, 1.0),))
    result = {{"ok": True, "section": {name!r}, "material": {material_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_shell_section(
    name: str,
    material_name: str,
    thickness: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a homogeneous shell section."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.HomogeneousShellSection(
        name={name!r}, material={material_name!r},
        thickness={thickness!r})
    result = {{"ok": True, "section": {name!r}, "material": {material_name!r}, "thickness": {thickness!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)

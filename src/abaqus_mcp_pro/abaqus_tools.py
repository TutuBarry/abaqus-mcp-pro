"""Specialized Abaqus API tools for common operations."""

from __future__ import annotations

from typing import Any

_run_python = None

def set_run_python(fn):
    global _run_python
    _run_python = fn


async def create_elastic_material(
    name: str,
    youngs_modulus: float,
    poisson_ratio: float,
    density: float | None = None,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a linear elastic material in Abaqus."""
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
    {density_block}
    result = {{"ok": True, "material": {name!r}, "model": {model_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_plastic_material(
    name: str,
    youngs_modulus: float,
    poisson_ratio: float,
    yield_stress: float,
    plastic_strain: float = 0.0,
    density: float | None = None,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an elasto-plastic material with isotropic hardening."""
    plastic_table = f"({yield_stress!r}, {plastic_strain!r})"
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
    mat.Plastic(table=({plastic_table}))
    {density_block}
    result = {{"ok": True, "material": {name!r}, "model": {model_name!r}, "yield_stress": {yield_stress!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def list_materials(
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """List all materials in the specified model."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    materials = []
    for name, mat in model.materials.items():
        info = {{"name": name}}
        if hasattr(mat, "elastic"):
            e = mat.elastic.table[0]
            info["elastic"] = {{"E": e[0], "nu": e[1]}}
        if hasattr(mat, "plastic"):
            p = mat.plastic.table[0]
            info["plastic"] = {{"yield_stress": p[0], "plastic_strain": p[1]}}
        if hasattr(mat, "density"):
            info["density"] = mat.density.table[0][0]
        materials.append(info)
    result = {{"ok": True, "materials": materials, "count": len(materials)}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_solid_section(
    name: str,
    material_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a homogeneous solid section."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.HomogeneousSolidSection(name={name!r}, material={material_name!r}, thickness=None)
    result = {{"ok": True, "section": {name!r}, "material": {material_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def assign_section(
    region_name: str,
    section_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Assign a section to a region."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.SectionAssignment(region=region, sectionName={section_name!r})
    result = {{"ok": True, "region": {region_name!r}, "section": {section_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_encastre_bc(
    name: str,
    region_name: str,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create an encastre (fully fixed) BC."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.sets[{region_name!r}]
    model.EncastreBC(name={name!r}, createStepName={step_name!r}, region=region)
    result = {{"ok": True, "bc": {name!r}, "type": "encastre", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_displacement_bc(
    name: str,
    region_name: str,
    u1: float | None = None,
    u2: float | None = None,
    u3: float | None = None,
    step_name: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a displacement BC."""
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
    model.DisplacementBC(name={name!r}, createStepName={step_name!r}, region=region, {kwargs_str})
    result = {{"ok": True, "bc": {name!r}, "type": "displacement", "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_pressure_load(
    name: str,
    pressure: float,
    region_name: str,
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a pressure load."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    region = model.rootAssembly.surfaces[{region_name!r}]
    model.Pressure(name={name!r}, createStepName={step_name!r}, region=region, magnitude={pressure!r})
    result = {{"ok": True, "load": {name!r}, "pressure": {pressure!r}, "region": {region_name!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_gravity_load(
    name: str,
    magnitude: float,
    direction: tuple,
    step_name: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a gravity load."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.Gravity(
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


async def create_tie(
    name: str,
    master_surface: str,
    slave_surface: str,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a tie constraint."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    master = model.rootAssembly.surfaces[{master_surface!r}]
    slave = model.rootAssembly.surfaces[{slave_surface!r}]
    model.Tie(name={name!r}, master=master, slave=slave)
    result = {{"ok": True, "tie": {name!r}, "master": {master_surface!r}, "slave": {slave_surface!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_static_step(
    name: str,
    description: str = "",
    previous_step: str = "Initial",
    nlgeom: bool = False,
    initial_inc: float = 0.1,
    max_inc: float = 1.0,
    min_inc: float = 1e-8,
    max_num_inc: int = 100,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Static, General step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    nl = ON if {nlgeom!r} else OFF
    model = mdb.models[{model_name!r}]
    model.StaticStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, nlgeom=nl,
        initialInc={initial_inc!r}, maxInc={max_inc!r},
        minInc={min_inc!r}, maxNumInc={max_num_inc!r})
    result = {{"ok": True, "step": {name!r}, "type": "static", "nlgeom": {nlgeom!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_modal_step(
    name: str,
    description: str = "",
    num_modes: int = 10,
    previous_step: str = "Initial",
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a Frequency (modal) analysis step."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    model.FrequencyStep(
        name={name!r}, previous={previous_step!r},
        description={description!r}, numEigen={num_modes!r})
    result = {{"ok": True, "step": {name!r}, "type": "modal", "num_modes": {num_modes!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_part_cube(
    name: str,
    width: float,
    height: float,
    depth: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a 3D deformable cube/box part."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    sketch = model.ConstrainedSketch(name="__sk__", sheetSize=200.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=({width!r}, {height!r}))
    part = model.Part(name={name!r}, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth={depth!r})
    del model.sketches["__sk__"]
    result = {{"ok": True, "part": {name!r}, "dims": [{width!r}, {height!r}, {depth!r}]}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_part_cylinder(
    name: str,
    radius: float,
    height: float,
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create a 3D deformable cylinder."""
    code = f"""
import json
try:
    from abaqus import mdb
    from abaqusConstants import *
    model = mdb.models[{model_name!r}]
    sketch = model.ConstrainedSketch(name="__sk__", sheetSize=200.0)
    sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=({radius!r}, 0.0))
    part = model.Part(name={name!r}, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth={height!r})
    del model.sketches["__sk__"]
    result = {{"ok": True, "part": {name!r}, "radius": {radius!r}, "height": {height!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def generate_mesh(
    model_name: str = "Model-1",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Generate mesh for the whole model."""
    code = f"""
import json
try:
    from abaqus import mdb
    model = mdb.models[{model_name!r}]
    model.rootAssembly.regenerate()
    model.rootAssembly.generateMesh()
    result = {{"ok": True, "message": "Mesh generated"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def get_field_output_summary(
    odb_path: str,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Get summary of field outputs in an ODB."""
    code = f"""
import json
try:
    from odbAccess import openOdb
    odb = openOdb({odb_path!r})
    steps = []
    for sname, step in odb.steps.items():
        frames_info = []
        for frame in step.frames:
            vars = list(frame.fieldOutputs.keys())
            frames_info.append({{"frame": frame.frameId, "time": frame.frameValue, "variables": vars}})
        steps.append({{"name": sname, "num_frames": len(step.frames), "frames": frames_info[:3]}})
    odb.close()
    result = {{"ok": True, "steps": steps}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def set_viewport_display(
    plot_type: str = "contour",
    variable: str = "S",
    component: str = "Mises",
    deformation_scale: float | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Set the viewport display type and variable.

    Args:
        plot_type: "contour", "symbol", "material", "undeformed"
        variable: Field output variable (e.g., "S", "U", "RF")
        component: Component (e.g., "Mises", "U1", "S11")
        deformation_scale: Deformation scale factor (None = auto)
    """
    deform_scale = f"deformationScaling=UNIFORM, uniformScaleFactor={deformation_scale!r}" if deformation_scale else "deformationScaling=AUTOMATIC"
    code = f"""
import json
try:
    from abaqus import *
    from abaqusConstants import *
    vp = session.viewports["Viewport: 1"]
    odb = vp.displayedObject
    if odb:
        vp.odbDisplay.setPrimaryVariable(
            variableLabel={variable!r},
            outputPosition=INTEGRATION_POINT,
            refinement=(COMPONENT, {component!r}))
        vp.odbDisplay.display.setValues(plotState=({plot_type.upper()!r},))
        vp.view.setValues({deform_scale})
        result = {{"ok": True, "plot_type": {plot_type!r}, "variable": {variable!r}, "component": {component!r}}}
    else:
        result = {{"ok": False, "error": "No ODB displayed in viewport"}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def set_viewport_view(
    view_type: str = "iso",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Set the camera view in the viewport.

    Args:
        view_type: "iso", "front", "back", "top", "bottom", "left", "right"
    """
    views = {
        "iso": ("session.viewports['Viewport: 1'].view.setValues("
                "projection=PARALLEL, "
                "cameraPosition=(1, 1, 1), "
                "cameraUpVector=(0, 1, 0))"),
        "front": ("session.viewports['Viewport: 1'].view.setValues("
                  "projection=PARALLEL, "
                  "cameraPosition=(0, 0, 100), "
                  "cameraUpVector=(0, 1, 0))"),
        "back": ("session.viewports['Viewport: 1'].view.setValues("
                 "projection=PARALLEL, "
                 "cameraPosition=(0, 0, -100), "
                 "cameraUpVector=(0, 1, 0))"),
        "top": ("session.viewports['Viewport: 1'].view.setValues("
                "projection=PARALLEL, "
                "cameraPosition=(0, 100, 0), "
                "cameraUpVector=(0, 0, -1))"),
        "bottom": ("session.viewports['Viewport: 1'].view.setValues("
                   "projection=PARALLEL, "
                   "cameraPosition=(0, -100, 0), "
                   "cameraUpVector=(0, 0, 1))"),
        "left": ("session.viewports['Viewport: 1'].view.setValues("
                 "projection=PARALLEL, "
                 "cameraPosition=(-100, 0, 0), "
                 "cameraUpVector=(0, 1, 0))"),
        "right": ("session.viewports['Viewport: 1'].view.setValues("
                  "projection=PARALLEL, "
                  "cameraPosition=(100, 0, 0), "
                  "cameraUpVector=(0, 1, 0))"),
    }
    view_code = views.get(view_type, views["iso"])
    # Build code using string concatenation to avoid f-string issues
    code = (
        "import json\n"
        "try:\n"
        "    from abaqus import *\n"
        "    from abaqusConstants import *\n"
        "    " + view_code + "\n"
        "    session.viewports['Viewport: 1'].viewport.setValues(applyOdb=True)\n"
        "    result = {'ok': True, 'view': '" + view_type + "'}\n"
        "except Exception as e:\n"
        "    result = {'ok': False, 'error': str(e), 'error_type': type(e).__name__}\n"
        'print("JSON_RESULT:", json.dumps(result))\n'
    )
    return await _run_python(code, timeout=timeout)



async def set_viewport_annotations(
    title: str = "",
    subtitle: str = "",
    legend: bool = True,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Set viewport annotations (title, legend, etc.).

    Args:
        title: Title text for the viewport
        subtitle: Subtitle text
        legend: Show/hide legend
    """
    code = f"""
import json
try:
    from abaqus import *
    from abaqusConstants import *
    vp = session.viewports["Viewport: 1"]
    vp.viewportAnnotationOptions.setValues(
        title=ON,
        titleText={title!r},
        subtitleText={subtitle!r},
        legend=ON if {legend!r} else OFF,
        state=ON)
    result = {{"ok": True, "title": {title!r}}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)


async def create_multiple_viewports(
    layout: str = "2x2",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create multiple viewports for side-by-side comparison.

    Args:
        layout: "2x2", "3x1", "1x3", "2x1", "1x2"
    """
    layouts = {
        "2x2": "session.viewports.changeLayout(2, 2)",
        "3x1": "session.viewports.changeLayout(3, 1)",
        "1x3": "session.viewports.changeLayout(1, 3)",
        "2x1": "session.viewports.changeLayout(2, 1)",
        "1x2": "session.viewports.changeLayout(1, 2)",
    }
    layout_code = layouts.get(layout, layouts["2x2"])
    code = f"""
import json
try:
    from abaqus import *
    from abaqusConstants import *
    {layout_code}
    vp_names = [vp.name for vp in session.viewports.values()]
    result = {{"ok": True, "layout": {layout!r}, "viewports": vp_names}}
except Exception as e:
    result = {{"ok": False, "error": str(e), "error_type": type(e).__name__}}
print("JSON_RESULT:", json.dumps(result))
"""
    return await _run_python(code, timeout=timeout)

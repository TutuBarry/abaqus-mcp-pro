"""Tests for abaqus_tools.py and abaqus_tools_extended.py.

Covers all async functions: verifies module structure, argument passing,
and that _run_python is called with correct code generation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import abaqus_mcp_pro.abaqus_tools as tools
import abaqus_mcp_pro.abaqus_tools_extended as tools_ext


# =============================================================================
# Module structure
# =============================================================================

class TestToolsModule:
    """Module-level _run_python / set_run_python."""

    def test_tools_has_run_python_default(self):
        assert tools._run_python is None

    def test_tools_set_run_python(self):
        fn = lambda x: x
        tools.set_run_python(fn)
        assert tools._run_python is fn
        tools.set_run_python(None)
        assert tools._run_python is None

    def test_tools_extended_has_run_python_default(self):
        assert tools_ext._run_python is None

    def test_tools_extended_set_run_python(self):
        fn = lambda x: x
        tools_ext.set_run_python(fn)
        assert tools_ext._run_python is fn
        tools_ext.set_run_python(None)
        assert tools_ext._run_python is None


# =============================================================================
# Test data
# Each case: (mod_name, func_name, kwargs, expected_substrings, special_import)
# special_import=True means code uses "import os, base64, json, sys" form
# =============================================================================

_TOOL_CASES = [
    ('tools', 'create_elastic_material',
    {
         'name': 'Steel',
         'youngs_modulus': 210000000000.0,
         'poisson_ratio': 0.3,
    },
     ['Material', 'Elastic', 'Steel'], False),
    ('tools', 'create_plastic_material',
    {
         'name': 'Aluminum',
         'youngs_modulus': 70000000000.0,
         'poisson_ratio': 0.33,
         'yield_stress': 250000000.0,
    },
     ['Material', 'Elastic', 'Plastic', 'Aluminum'], False),
    ('tools', 'list_materials',
    {},
     ['mdb.models'], False),
    ('tools', 'create_solid_section',
    {
         'name': 'Sec-1',
         'material_name': 'Steel',
    },
     ['HomogeneousSolidSection', 'Sec-1'], False),
    ('tools', 'assign_section',
    {
         'region_name': 'Set-1',
         'section_name': 'Sec-1',
    },
     ['SectionAssignment', 'Set-1', 'Sec-1'], False),
    ('tools', 'create_encastre_bc',
    {
         'name': 'BC-1',
         'region_name': 'Set-1',
         'step_name': 'Step-1',
    },
     ['EncastreBC', 'BC-1'], False),
    ('tools', 'create_displacement_bc',
    {
         'name': 'BC-1',
         'region_name': 'Set-1',
         'step_name': 'Step-1',
    },
     ['DisplacementBC', 'BC-1'], False),
    ('tools', 'create_pressure_load',
    {
         'name': 'Load-1',
         'region_name': 'Set-1',
         'pressure': 100000.0,
         'step_name': 'Step-1',
    },
     ['Pressure', 'Load-1'], False),
    ('tools', 'create_gravity_load',
    {
         'name': 'Grav-1',
         'magnitude': 9.81,
         'direction': (0, 0, -1),
         'step_name': 'Step-1',
    },
     ['Gravity', 'Grav-1'], False),
    ('tools', 'create_tie',
    {
         'name': 'Tie-1',
         'master_surface': 'Set-M',
         'slave_surface': 'Set-S',
    },
     ['Tie', 'Tie-1'], False),
    ('tools', 'create_static_step',
    {
         'name': 'Step-1',
    },
     ['StaticStep'], False),
    ('tools', 'create_modal_step',
    {
         'name': 'Step-1',
    },
     ['FrequencyStep'], False),
    ('tools', 'create_part_cube',
    {
         'name': 'Part-1',
         'width': 1.0,
         'height': 1.0,
         'depth': 1.0,
    },
     ['ConstrainedSketch', 'Part-1'], False),
    ('tools', 'create_part_cylinder',
    {
         'name': 'Cyl-1',
         'radius': 0.5,
         'height': 2.0,
    },
     ['ConstrainedSketch', 'Cyl-1'], False),
    ('tools', 'generate_mesh',
    {},
     ['generateMesh'], False),
    ('tools', 'get_field_output_summary',
    {
         'odb_path': 'result.odb',
    },
     ['openOdb', 'result.odb'], False),
    ('tools', 'set_viewport_display',
    {
         'plot_type': 'contour',
         'variable': 'S',
         'component': 'Mises',
    },
     ['viewport', 'setPrimaryVariable'], False),
    ('tools', 'set_viewport_view',
    {
         'view_type': 'front',
    },
     ['viewport'], False),
    ('tools', 'set_viewport_annotations',
    {
         'title': '',
         'subtitle': '',
         'legend': True,
    },
     ['viewport'], False),
    ('tools', 'create_multiple_viewports',
    {
         'layout': 'four',
    },
     ['viewport'], False),
    ('tools', 'capture_result_contours',
    {
         'odb_path': 'result.odb',
    },
     ['openOdb', 'result.odb'], True),
]

_EXT_CASES = [
    ('tools_ext', 'create_concentrated_force',
    {
         'name': 'F-1',
         'region_name': 'Set-1',
         'force': (1.0, 0.0, 0.0),
         'step_name': 'Step-1',
    },
     ['ConcentratedForce'], False),
    ('tools_ext', 'create_moment_load',
    {
         'name': 'M-1',
         'region_name': 'Set-1',
         'moment': (0.0, 0.0, 100.0),
         'step_name': 'Step-1',
    },
     ['Moment'], False),
    ('tools_ext', 'create_shell_edge_load',
    {
         'name': 'SEL-1',
         'region_name': 'Set-1',
         'magnitude': 1000.0,
         'direction': (0, 0, -1),
         'step_name': 'Step-1',
    },
     ['ShellEdgeLoad'], False),
    ('tools_ext', 'create_line_load',
    {
         'name': 'LL-1',
         'region_name': 'Set-1',
         'magnitude': 500,
         'direction': (0, -1, 0),
         'step_name': 'Step-1',
    },
     ['LineLoad'], False),
    ('tools_ext', 'create_body_force',
    {
         'name': 'BF-1',
         'magnitude': 1.0,
         'direction': (1.0, 0.0, 0.0),
         'step_name': 'Step-1',
    },
     ['BodyForce'], False),
    ('tools_ext', 'create_heat_flux_load',
    {
         'name': 'HF-1',
         'region_name': 'Set-1',
         'magnitude': 100.0,
         'step_name': 'Step-1',
    },
     ['SurfaceHeatFlux'], False),
    ('tools_ext', 'create_body_heat_flux',
    {
         'name': 'BHF-1',
         'magnitude': 50.0,
         'step_name': 'Step-1',
    },
     ['BodyHeatFlux'], False),
    ('tools_ext', 'create_connector_force',
    {
         'name': 'CF-1',
         'region_name': 'Set-1',
         'force': (0, 0, 500),
         'step_name': 'Step-1',
    },
     ['ConnectorForce'], False),
    ('tools_ext', 'create_symmetry_bc',
    {
         'name': 'Sym-1',
         'region_name': 'Set-1',
         'step_name': 'Step-1',
    },
     ['SymmetryBC'], False),
    ('tools_ext', 'create_pinned_bc',
    {
         'name': 'Pin-1',
         'region_name': 'Set-1',
         'step_name': 'Step-1',
    },
     ['DisplacementBC'], False),
    ('tools_ext', 'create_velocity_bc',
    {
         'name': 'V-1',
         'region_name': 'Set-1',
         'v1': 0.0,
         'v2': 0.0,
         'step_name': 'Step-1',
    },
     ['VelocityBC'], False),
    ('tools_ext', 'create_acceleration_bc',
    {
         'name': 'A-1',
         'region_name': 'Set-1',
         'a1': 0.0,
         'step_name': 'Step-1',
    },
     ['AccelerationBC'], False),
    ('tools_ext', 'create_temperature_bc',
    {
         'name': 'T-1',
         'region_name': 'Set-1',
         'magnitude': 100.0,
         'step_name': 'Step-1',
    },
     ['TemperatureBC'], False),
    ('tools_ext', 'create_connector_displacement_bc',
    {
         'name': 'CD-1',
         'region_name': 'Set-1',
         'step_name': 'Step-1',
    },
     ['ConnectorDisplacementBC'], False),
    ('tools_ext', 'create_rigid_body_constraint',
    {
         'name': 'RB-1',
         'region_name': 'Set-1',
         'ref_point_name': 'RP-1',
    },
     ['RigidBody'], False),
    ('tools_ext', 'create_coupling_constraint',
    {
         'name': 'Coup-1',
         'control_point': 'RP-1',
         'surface_name': 'Surf-1',
    },
     ['Coupling'], False),
    ('tools_ext', 'create_mpc_constraint',
    {
         'name': 'MPC-1',
         'mpc_type': 'TIE',
         'control_point': 'RP-1',
         'surface_name': 'Surf-1',
    },
     ['MPC'], False),
    ('tools_ext', 'create_embedded_region',
    {
         'name': 'Embed-1',
         'embedded_region': 'Set-In',
         'host_region': 'Set-Out',
    },
     ['EmbeddedRegion'], False),
    ('tools_ext', 'create_equation_constraint',
    {
         'name': 'Eq-1',
         'terms': [(1.0, 'Set-1', 1), (-1.0, 'Set-2', 1)],
    },
     ['Equation'], False),
    ('tools_ext', 'create_instance',
    {
         'part_name': 'Part-1',
         'instance_name': 'Inst-1',
    },
     ['Instance', 'Inst-1'], False),
    ('tools_ext', 'translate_instance',
    {
         'instance_name': 'Inst-1',
         'vector': (1.0, 0.0, 0.0),
    },
     ['translate'], False),
    ('tools_ext', 'rotate_instance',
    {
         'instance_name': 'Inst-1',
         'axis_point': (0.0, 0.0, 0.0),
         'axis_direction': (0, 1, 0),
         'angle': 90.0,
    },
     ['rotate'], False),
    ('tools_ext', 'create_reference_point',
    {
         'point': (0.0, 0.0, 0.0),
    },
     ['ReferencePoint'], False),
    ('tools_ext', 'create_set_by_face',
    {
         'set_name': 'Set-1',
         'instance_name': 'Part-1-1',
         'face_indices': [1],
    },
     ['Set', 'faces'], False),
    ('tools_ext', 'create_set_by_edges',
    {
         'set_name': 'EdgeSet',
         'instance_name': 'Part-1-1',
         'edge_indices': [1, 2],
    },
     ['Set', 'edges'], False),
    ('tools_ext', 'create_set_by_vertices',
    {
         'set_name': 'VtxSet',
         'instance_name': 'Part-1-1',
         'vertex_indices': [1],
    },
     ['Set', 'vertices'], False),
    ('tools_ext', 'create_surface',
    {
         'surface_name': 'Surf-1',
         'instance_name': 'Part-1-1',
         'face_indices': [1],
    },
     ['Surface', 'side1Faces'], False),
    ('tools_ext', 'create_surface_by_edges',
    {
         'surface_name': 'Surf-1',
         'instance_name': 'Part-1-1',
         'edge_indices': [1, 2, 3],
    },
     ['Surface', 'side1Edges'], False),
    ('tools_ext', 'find_face_by_coordinate',
    {
         'instance_name': 'Part-1-1',
         'coordinate': (0.0, 0.0, 0.0),
    },
     ['faces', 'getCentroid'], False),
    ('tools_ext', 'find_edge_by_coordinate',
    {
         'instance_name': 'Part-1-1',
         'coordinate': (0.0, 0.0, 0.0),
    },
     ['edges', 'getCentroid'], False),
    ('tools_ext', 'create_contact_property',
    {
         'name': 'IntProp-1',
    },
     ['ContactProperty'], False),
    ('tools_ext', 'create_surface_to_surface_contact',
    {
         'name': 'Std-1',
         'master_surface': 'Surf-M',
         'slave_surface': 'Surf-S',
         'interaction_property': 'IntProp-1',
         'step_name': 'Step-1',
    },
     ['SurfaceToSurfaceContactStd'], False),
    ('tools_ext', 'create_surface_to_surface_contact_exp',
    {
         'name': 'Exp-1',
         'master_surface': 'Surf-M',
         'slave_surface': 'Surf-S',
         'interaction_property': 'IntProp-1',
         'step_name': 'Step-1',
    },
     ['SurfaceToSurfaceContactExp'], False),
    ('tools_ext', 'create_general_contact',
    {
         'name': 'Gen-1',
         'interaction_property': 'IntProp-1',
    },
     ['ContactStd'], False),
    ('tools_ext', 'create_general_contact_exp',
    {
         'name': 'GenExp-1',
         'interaction_property': 'IntProp-1',
    },
     ['ContactExp'], False),
    ('tools_ext', 'create_explicit_step',
    {
         'name': 'ExpStep-1',
         'time_period': 0.1,
    },
     ['ExplicitDynamicsStep'], False),
    ('tools_ext', 'create_heat_transfer_step',
    {
         'name': 'HT-1',
         'time_period': 1.0,
    },
     ['HeatTransferStep'], False),
    ('tools_ext', 'create_coupled_temp_disp_step',
    {
         'name': 'CTD-1',
         'time_period': 1.0,
    },
     ['CoupledTempDisplacementStep'], False),
    ('tools_ext', 'create_dynamic_implicit_step',
    {
         'name': 'Dyn-1',
         'time_period': 1.0,
    },
     ['ImplicitDynamicsStep'], False),
    ('tools_ext', 'create_static_riks_step',
    {
         'name': 'Riks-1',
    },
     ['StaticRiksStep'], False),
    ('tools_ext', 'create_buckle_step',
    {
         'name': 'Buckle-1',
    },
     ['BuckleStep'], False),
    ('tools_ext', 'create_field_output_request',
    {
         'step_name': 'Step-1',
    },
     ['fieldOutputRequests'], False),
    ('tools_ext', 'create_history_output_request',
    {
         'step_name': 'Step-1',
         'region_name': 'Set-1',
         'variables': ['U', 'RF'],
    },
     ['historyOutputRequests'], False),
    ('tools_ext', 'seed_part',
    {
         'part_name': 'Part-1',
         'size': 0.1,
    },
     ['seedPart'], False),
    ('tools_ext', 'set_element_type',
    {
         'part_name': 'Part-1',
         'elem_type': 'C3D8R',
    },
     ['setElementType'], False),
    ('tools_ext', 'set_mesh_control',
    {
         'part_name': 'Part-1',
    },
     ['setMeshControls'], False),
    ('tools_ext', 'create_tabular_amplitude',
    {
         'name': 'Amp-1',
         'data': [(0.0, 0.0), (1.0, 1.0)],
    },
     ['TabularAmplitude'], False),
    ('tools_ext', 'create_smooth_step_amplitude',
    {
         'name': 'SSA-1',
         'data': [(0.0, 0.0), (1.0, 1.0)],
    },
     ['SmoothStepAmplitude'], False),
    ('tools_ext', 'create_periodic_amplitude',
    {
         'name': 'PA-1',
         'frequency': 10.0,
         'start_time': 0.0,
         'max_amplitude': 1.0,
    },
     ['PeriodicAmplitude'], False),
    ('tools_ext', 'get_xy_data',
    {
         'odb_path': 'r.odb',
         'variable': 'U',
         'component': 'Magnitude',
    },
     ['openOdb', 'fieldOutputs'], False),
    ('tools_ext', 'get_history_output',
    {
         'odb_path': 'r.odb',
         'variable': 'RF2',
    },
     ['openOdb', 'historyRegions'], False),
    ('tools_ext', 'get_node_coordinates',
    {
         'instance_name': 'Part-1-1',
         'node_label': 1,
    },
     ['node.coordinates'], False),
    ('tools_ext', 'list_elements',
    {
         'instance_name': 'Part-1-1',
    },
     ['elements'], False),
    ('tools_ext', 'list_nodes',
    {
         'instance_name': 'Part-1-1',
    },
     ['nodes'], False),
    ('tools_ext', 'create_hyperelastic_material',
    {
         'name': 'Rubber',
         'c10': 0.5,
         'c01': 0.1,
         'd1': 0.02,
    },
     ['Hyperelastic'], False),
    ('tools_ext', 'create_viscoelastic_material',
    {
         'name': 'Visco',
         'youngs_modulus': 1000000.0,
         'poisson_ratio': 0.3,
         'relaxation_data': [(0.5, 0.1, 1.0)],
    },
     ['Viscoelastic'], False),
    ('tools_ext', 'create_thermal_expansion',
    {
         'material_name': 'Al-Exp',
         'expansion_coefficient': 2.3e-05,
    },
     ['Expansion'], False),
    ('tools_ext', 'create_thermal_conductivity',
    {
         'material_name': 'Cu-Cond',
         'conductivity': 400.0,
    },
     ['Conductivity'], False),
    ('tools_ext', 'create_specific_heat',
    {
         'material_name': 'Water-Cp',
         'specific_heat': 4186.0,
    },
     ['SpecificHeat'], False),
    ('tools_ext', 'create_damage_initiation',
    {
         'material_name': 'Ductile',
         'fracture_strain': 0.1,
    },
     ['DuctileDamageInitiation'], False),
    ('tools_ext', 'create_part_sphere',
    {
         'name': 'Sphere-1',
         'radius': 1.0,
    },
     ['ConstrainedSketch', 'Sphere-1'], False),
    ('tools_ext', 'create_part_beam',
    {
         'name': 'Beam-1',
         'length': 1.0,
         'point1': (0, 0, 0),
         'point2': (1, 0, 0),
    },
     ['WirePolyLine', 'Beam-1'], False),
    ('tools_ext', 'create_part_plate',
    {
         'name': 'Plate-1',
         'width': 1.0,
         'height': 2.0,
    },
     ['ConstrainedSketch', 'Plate-1'], False),
    ('tools_ext', 'create_beam_section',
    {
         'name': 'BSec-1',
         'material_name': 'Steel',
    },
     ['BeamSection'], False),
    ('tools_ext', 'create_shell_section',
    {
         'name': 'SSec-1',
         'material_name': 'Steel',
         'thickness': 0.01,
    },
     ['HomogeneousShellSection'], False),
]

# =============================================================================
# Parametrized tests
# =============================================================================

@pytest.mark.parametrize(
    "mod_name,func_name,kwargs,substrings,special_import",
    _TOOL_CASES,
)
@pytest.mark.asyncio
async def test_tools_function(mod_name, func_name, kwargs, substrings, special_import):
    """Each abaqus_tools function calls _run_python with the right code."""
    mod = {"tools": tools, "tools_ext": tools_ext}[mod_name]
    mock_fn = AsyncMock(return_value=None)
    func = getattr(mod, func_name)
    with patch.object(mod, "_run_python", mock_fn):
        result = await func(**kwargs)
        mock_fn.assert_awaited_once()
        code_arg = mock_fn.call_args[0][0]
        if special_import:
            assert "import os" in code_arg
        else:
            assert "import json" in code_arg
        for sub in substrings:
            assert sub in code_arg, f"Expected {sub!r} in code string of {func_name}"
        assert 'result' in code_arg


@pytest.mark.parametrize(
    "mod_name,func_name,kwargs,substrings,special_import",
    _EXT_CASES,
)
@pytest.mark.asyncio
async def test_extended_function(mod_name, func_name, kwargs, substrings, special_import):
    """Each abaqus_tools_extended function calls _run_python with the right code."""
    mod = {"tools": tools, "tools_ext": tools_ext}[mod_name]
    mock_fn = AsyncMock(return_value=None)
    func = getattr(mod, func_name)
    with patch.object(mod, "_run_python", mock_fn):
        result = await func(**kwargs)
        mock_fn.assert_awaited_once()
        code_arg = mock_fn.call_args[0][0]
        assert "import json" in code_arg
        for sub in substrings:
            assert sub in code_arg, f"Expected {sub!r} in code string of {func_name}"
        assert 'result' in code_arg

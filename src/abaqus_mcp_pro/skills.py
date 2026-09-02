"""Skills registration for Abaqus MCP server.

This module provides:
- SKILLS: a dict of 26 core skills (short, curated content) used by tests and MCP resources.
- _collect_skill_files(): walk the skills/ directory and return file-system skill files.
- register_skill_resources(mcp): register both core and file-system skills as MCP resources.
"""

from __future__ import annotations

import os as _os
import re as _re


SKILLS = {
    "skills/index": "# Abaqus Skills Index\n\nThis is the master index of all available Abaqus skills.\n\nModeling: skills/geometry, skills/material, skills/mesh, skills/interaction\nSetup: skills/step, skills/boundary-condition, skills/load, skills/output, skills/amplitude, skills/field, skills/docs\nExecution: skills/job, skills/odb, skills/export\nAnalysis: skills/static-analysis, skills/modal-analysis, skills/contact-analysis, skills/dynamic-analysis, skills/thermal-analysis, skills/fatigue-analysis, skills/coupled-analysis\nOptimization: skills/optimization, skills/topology-optimization, skills/shape-optimization\nReference: skills/units\n",
    "skills/geometry": "# Geometry\n\nCreate parts in Abaqus/CAE.\n\nKey commands: mdb.models[].ConstrainedSketch, BaseSolidExtrude, BaseSolidRevolve\nDimensionality: THREE_D, TWO_D_PLANAR, AXISYMMETRIC\n",
    "skills/material": "# Material\n\nDefine material properties.\n\nElastic: mat.Elastic(table=((E, nu),))  # E in MPa\nPlastic: mat.Plastic(table=((sigma_y, 0.0),))\nDensity: mat.Density(table=((rho,),))  # tonne/mm^3\n\nCommon (SI-mm): Steel E=210000 MPa, nu=0.3, rho=7.85e-9\n",
    "skills/mesh": "# Mesh\n\nControl element types and seed sizes.\n\nCommon elements: C3D8R (brick), C3D10 (tet), S4R (shell), B31 (beam)\nSeed: p.seedPart(size=5.0)\nMesh: p.generateMesh()\nLearning Edition limit: 1000 nodes\n",
    "skills/interaction": "# Interaction\n\nContact: ContactProperty, TangentialBehavior, NormalBehavior, SurfaceToSurfaceContactStd\nTie: Tie(name, master, slave, positionToleranceMethod=COMPUTED)\nMaster: stiffer material, coarser mesh. Slave: softer material, finer mesh.\n",
    "skills/step": "# Step\n\nCreate analysis steps.\n\nStaticStep: nlgeom=ON, initialInc=0.1, maxInc=0.1, minInc=1e-8, maxNumInc=1000\nOther types: StaticRiksStep, FrequencyStep, ExplicitDynamicsStep, HeatTransferStep, CoupledTempDisplacementStep\n",
    "skills/boundary-condition": "# Boundary Condition\n\nEncastreBC: fully fixed\nDisplacementBC: u1=SET, u2=0.0, etc.\nSymmetry: XSYMM, YSYMM, ZSYMM, ENCASTRE, PINNED\nUse named sets (region=inst.sets['Set-Name']) instead of raw coordinates.\n",
    "skills/load": "# Load\n\nConcentratedForce: cf2=-1000.0 (N)\nPressure: magnitude=10.0 (MPa)\nGravity: comp2=-9810.0 (mm/s^2)\n",
    "skills/output": "# Output\n\nField output: fieldOutputRequests['F-Output-1'].setValues(variables=('S','U','RF','PEEQ','E'))\nHistory output: HistoryOutputRequest(name='H-Output-1', createStepName='Step-1', variables=('U1','RF1'), region=region)\nCommon: S (stress), U (disp), RF (reaction), PEEQ (plastic strain), NT (temperature), HFL (heat flux)\n",
    "skills/job": "# Job\n\nCreate: mdb.Job(name='Job-1', model='Model-1', numCpus=4, numDomains=4, memory=90, memoryUnits=PERCENTAGE)\nSubmit: job.submit(consistencyChecking=False); job.waitForCompletion()\nCommon failures: zero pivot (add BCs), negative eigenvalue (check stability), too many increments (reduce load), memory exceeded (coarser mesh)\n",
    "skills/odb": "# ODB\n\nRead results: from odbAccess import openOdb; odb = openOdb(path='job.odb', readOnly=True)\nAccess: step.frames[-1].fieldOutputs['S'].getScalarField(invariant=MISES)\nKey invariants: MISES, MaxPrincipal, MidPrincipal, MinPrincipal, Tresca\n",
    "skills/static-analysis": "# Static Analysis\n\nWorkflow: part -> material (E,nu) -> section -> assembly -> step (StaticStep) -> BCs/loads -> mesh -> job -> ODB\nUse nlgeom=ON for large deformations. Set initialInc=0.1, maxInc=0.1, minInc=1e-8, maxNumInc=1000 for nonlinear.\n",
    "skills/modal-analysis": "# Modal Analysis\n\nWorkflow: part -> material (MUST include density) -> assembly -> mesh -> FrequencyStep (numEigen=10, Lanczos) -> BCs only -> job -> extract frequencies\nFree-free: 6 rigid body modes at ~0 Hz\n",
    "skills/contact-analysis": "# Contact Analysis\n\nWorkflow: contact property (TangentialBehavior + NormalBehavior) -> master/slave surfaces -> SurfaceToSurfaceContactStd -> nlgeom=ON, smaller increments -> contact outputs (CSTRESS, CDISP, COPEN)\nMaster: stiffer material, coarser mesh. Slave: softer material, finer mesh.\n",
    "skills/dynamic-analysis": "# Dynamic Analysis\n\nSolver: < 10ms -> Explicit (ExplicitDynamicsStep), > 100ms -> Implicit (StaticStep with nlgeom)\nRequired: material MUST have density, initial conditions (velocity for drop tests)\nOutput: S, U, V, A, PEEQ, ALLKE, ALLIE, ETOTAL. Verify energy balance.\n",
    "skills/thermal-analysis": "# Thermal Analysis\n\nSteady-state: HeatTransferStep, steadyState=ON\nTransient: transient=ON, initialInc, maxInc\nRequired: conductivity (k) for all, specific heat (cp) + density for transient\nElements: DC3D8, DC3D10 (not C3D8)\n",
    "skills/fatigue-analysis": "# Fatigue Analysis\n\nNote: Abaqus has limited native fatigue. Workflow: structural analysis -> extract stress/strain -> apply fatigue criteria externally.\nApproaches: S-N (Basquin, high-cycle), e-N (Coffin-Manson, low-cycle), fracture mechanics (Paris law)\nMean stress correction: Goodman, Gerber, Soderberg, SWT\n",
    "skills/coupled-analysis": "# Coupled Analysis\n\nThermomechanical coupling.\nOne-way (sequential): thermal -> stress. Two-way: fully coupled (CoupledTempDisplacementStep).\nRequired: both mechanical (E, nu) AND thermal (k, alpha, T_ref).\nElements: C3D8T, C3D8RT, C3D10MT\n",
    "skills/optimization": "# Optimization\n\nGeneral optimization setup with Tosca.\nRequires: Full Abaqus license with Tosca module.\n",
    "skills/topology-optimization": "# Topology Optimization\n\nLightweight design. Define design area and frozen regions (BC/load areas).\nObjective: minimize compliance. Constraint: volume fraction (e.g. 0.3).\nSIMP penalty: 3.0. Manufacturing constraints: symmetry, member size, demold.\nRequires: Tosca license.\n",
    "skills/shape-optimization": "# Shape Optimization\n\nReduce stress concentration. Identify design surfaces, set movement limits, add smoothing.\nObjective: minimize max stress.\nRequires: Tosca license.\n",
    "skills/amplitude": "# Amplitude\n\nTabular: TabularAmplitude(name='Amp-1', timeSpan=STEP, data=((0.0,0.0),(1.0,1.0)))\nSmooth step: SmoothStepAmplitude(name='Amp-2', timeSpan=STEP, data=((0.0,0.0),(1.0,1.0)))\nApply: distributionType=UNIFORM, amplitude='Amp-1'\n",
    "skills/field": "# Field\n\nPredefined fields and initial conditions.\nTemperature: Temperature(name='InitTemp', createStepName='Initial', region=region, distributionType=UNIFORM, magnitudes=(20.0,))\nVelocity: Velocity(name='InitVel', createStepName='Initial', region=region, velocity2=-1000.0)\n",
    "skills/export": "# Export\n\nCSV: session.xyDataListFromField -> session.writeXYReport(fileName='output.csv')\nFormats: CSV, VTK, Field Report\n",
    "skills/units": "# Units\n\nAbaqus has no built-in unit system. Be consistent.\n\nSI-mm (most common): Length=mm, Force=N, Mass=tonne, Stress=MPa, Density=tonne/mm^3\nSteel: E=210000 MPa, nu=0.3, rho=7.85e-9, gravity=9810 mm/s^2\nSI-m: Length=m, Stress=Pa, Density=kg/m^3, E=Pa, gravity=9.81 m/s^2\n",
    "skills/docs": "# API Documentation\n\nDownload and manage abqpy API documentation.\nKey sources: Abaqus Scripting User's Guide, Abaqus Scripting Reference Manual, abqpy documentation\n",
}



def _collect_skill_files() -> list[tuple[str, str]]:
    """Walk skills/ directory and return (uri, file_path) tuples."""
    skills_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), 'skills')
    if not _os.path.isdir(skills_dir):
        return []
    result: list[tuple[str, str]] = []
    for root, _dirs, files in _os.walk(skills_dir):
        for fname in files:
            if fname == 'SKILL.md':
                full_path = _os.path.normpath(_os.path.join(root, fname))
                rel = _os.path.relpath(full_path, skills_dir).replace('\\', '/')
                uri = f'abaqus://skills/{rel}'
                result.append((uri, full_path))
    return result



def get_skill_count() -> int:
    """Return the number of core (inline) skills."""
    return len(SKILLS)



def register_skill_resources(mcp) -> None:
    """Register core skills and file-system skills as MCP resources.

    Args:
        mcp: An MCPServer instance.
    """
    # Register core skills from the SKILLS dict
    for key, content in SKILLS.items():
        uri = f'abaqus://{key}'
        desc = ''
        for line in content.splitlines():
            s = line.strip()
            if s.startswith('# ') and not s.startswith('## '):
                desc = s[2:].strip()
                break

        def _make_reader(c=content):
            def _reader():
                return c
            return _reader

        if desc:
            mcp.resource(uri, description=desc)(_make_reader())
        else:
            mcp.resource(uri)(_make_reader())

    # Register file-system SKILL.md files
    skill_files = _collect_skill_files()
    for uri, file_path in skill_files:
        description = None
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                first_lines = ''.join(fh.readline() for _ in range(20))
            m = _re.search(r'^description:\s*(.+)$', first_lines, _re.MULTILINE)
            if m:
                description = m.group(1).strip()
        except Exception:
            pass

        def _make_reader(fp):
            def _reader():
                with open(fp, 'r', encoding='utf-8') as fh:
                    return fh.read()
            return _reader

        if description:
            mcp.resource(uri, description=description)(_make_reader(file_path))
        else:
            mcp.resource(uri)(_make_reader(file_path))

    # Register combined skill list
    def _skill_list():
        lines = ['# Available Abaqus Skills', '']
        lines.append('## Core Skills (built-in)')
        for key in sorted(SKILLS.keys()):
            lines.append(f'- abaqus://{key}')
        lines.append('')
        lines.append('## File-system Skills')
        for uri, _ in sorted(skill_files):
            lines.append(f'- {uri}')
        return '\n'.join(lines)

    mcp.resource('abaqus://skills/list', description='Complete list of all available Abaqus skill resources with descriptions.')(_skill_list)
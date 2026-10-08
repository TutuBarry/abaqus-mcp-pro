"""Run with Abaqus Python; checks native ODB equilibrium, energy and contact output."""
import json
import sys
import math
from odbAccess import openOdb

odb = openOdb(sys.argv[1], readOnly=True)
try:
    step = list(odb.steps.values())[-1]
    frame = step.frames[-1]
    inst = list(odb.rootAssembly.instances.values())[0]
    rf = frame.fieldOutputs['RF']
    base = sum(float(v.data[2]) for v in rf.getSubset(region=inst.nodeSets['FIXED']).values)
    cap = sum(float(v.data[2]) for v in rf.getSubset(region=inst.nodeSets['LOADED']).values)
    energies = {}
    for region in step.historyRegions.values():
        for key in ('ALLSE', 'ALLAE', 'ALLPD', 'ALLFD'):
            if key in region.historyOutputs:
                energies[key] = region.historyOutputs[key].data[-1][1]
    contact = {}
    for name, field in frame.fieldOutputs.items():
        if name.split()[0] in ('CPRESS', 'COPEN', 'CSHEAR1', 'CSHEAR2', 'CSLIP1', 'CSLIP2'):
            values = [float(v.data) for v in field.values]
            contact[name] = {'min': min(values), 'max': max(values), 'count': len(values)}
    stress = [v.mises for v in frame.fieldOutputs['S'].values]
    balance = abs(base + cap) / max(abs(base), 1e-12)
    energy_ratio = energies['ALLAE'] / max(energies['ALLSE'], 1e-12)
    # Integrate nodal CPRESS over the known punch-bottom surface using lumped
    # projected face areas. Boundary cells are fractional nodal estimates,
    # not an exact reconstruction of the active contact boundary.
    coordinates = {n.label: tuple(float(x) for x in n.coordinates) for n in inst.nodes}
    pressure_field = next((f for k, f in frame.fieldOutputs.items() if k.split()[0] == 'CPRESS'), None)
    pressure = {v.nodeLabel: float(v.data) for v in pressure_field.values if v.instance.name == inst.name} if pressure_field else {}
    nodal_area = {}
    for element in inst.elementSets['PUNCH_BOTTOM'].elements:
        labels = list(element.connectivity)[:4]
        xy = [coordinates[n] for n in labels]
        area = abs(sum(xy[i][0]*xy[(i+1)%4][1]-xy[(i+1)%4][0]*xy[i][1] for i in range(4))) / 2
        for n in labels:
            nodal_area[n] = nodal_area.get(n, 0) + area/4
    threshold = max(max(pressure.values()) if pressure else 0, 1) * 1e-6
    active_area = sum(a for n,a in nodal_area.items() if pressure.get(n, 0) > threshold)
    integrated_force = sum(a * pressure.get(n, 0) for n,a in nodal_area.items())
    profile = [{'node':n, 'x_mm':coordinates[n][0], 'y_mm':coordinates[n][1],
                'pressure_MPa':pressure.get(n), 'tributary_projected_area_mm2':a}
               for n,a in sorted(nodal_area.items())]
    peeq = max([float(v.data) for v in frame.fieldOutputs['PEEQ'].values] or [0]) if 'PEEQ' in frame.fieldOutputs else None
    checks = {'completed_time': abs(frame.frameValue - 1) < 1e-6,
              'force_balance_1e-5': balance < 1e-5,
              'artificial_energy_below_5_percent': energy_ratio < .05,
              'contact_pressure_present': any(k.startswith('CPRESS') for k in contact),
              'nonnegative_contact_pressure': all(v['min'] >= -1e-6 for k,v in contact.items() if k.startswith('CPRESS')),
              'contact_opening_present': any(k.startswith('COPEN') for k in contact),
              'limited_penetration': all(v['min'] > -1e-4 for k,v in contact.items() if k.startswith('COPEN')),
              'finite_contact_metrics': active_area > 0 and math.isfinite(integrated_force)}
    if '--expect-plastic' in sys.argv:
        checks['plastic_strain_activated'] = peeq is not None and peeq > 0
        checks['plastic_dissipation_positive'] = energies.get('ALLPD', 0) > 0
    if '--expect-friction' in sys.argv:
        checks['friction_dissipation_positive'] = energies.get('ALLFD', 0) > 0
    record = {'checks': checks, 'passed': all(checks.values()), 'force_N': base, 'opposing_force_N': cap,
              'force_balance_relative': balance, 'artificial_energy_ratio': energy_ratio,
              'mises_MPa': [min(stress), max(stress)], 'contact': contact,
              'nodes': len(inst.nodes), 'elements': len(inst.elements), 'frames': len(step.frames)}
    record.update(energies=energies, peeq_max=peeq,
                  contact_area_projected_nodal_estimate_mm2=active_area,
                  pressure_integrated_force_estimate_N=integrated_force,
                  pressure_force_relative_difference=abs(integrated_force-base)/max(abs(base), 1e-12),
                  pressure_profile=profile,
                  averaging='Native integration-point Mises; native contact nodal pressure. Projected undeformed nodal area quadrature; no CAE contour averaging.')
    with open(sys.argv[2], 'w') as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps(record))
finally:
    odb.close()

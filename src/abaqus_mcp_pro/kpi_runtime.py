"""Standard-library-only KPI implementation shared by local and kernel execution."""


def query_odb(odb, queries):
    import math
    import abaqusConstants as constants

    invariants = {
        'magnitude': 'MAGNITUDE', 'mises': 'MISES', 'tresca': 'TRESCA',
        'press': 'PRESS', 'inv3': 'INV3', 'maxprincipal': 'MAX_PRINCIPAL',
        'midprincipal': 'MID_PRINCIPAL', 'minprincipal': 'MIN_PRINCIPAL',
    }

    def region_object(name):
        assembly = odb.rootAssembly
        if '/' in name:
            instance, name = name.split('/', 1)
            owners = [assembly.instances[instance]]
        else:
            owners = [assembly]
        matches = [getattr(owner, attr, {})[name] for owner in owners
                   for attr in ('nodeSets', 'elementSets') if name in getattr(owner, attr, {})]
        if len(matches) != 1:
            raise ValueError('Region must identify one set; use INSTANCE/SET for instance sets: ' + name)
        return matches[0]

    results = []
    for query in queries:
        meta = {}
        item = {'query_id': query.get('query_id', '?'), 'value': None,
                'unit': query.get('unit', ''), 'error': '', 'metadata': meta}
        try:
            steps = list(odb.steps.keys())
            if not steps:
                raise ValueError('ODB has no steps')
            step_name = query.get('step') or steps[0]
            step = odb.steps[step_name]  # Explicit invalid selections must fail.
            spec = query.get('frame', 'last')
            if spec in ('first', 'last'):
                index = 0 if spec == 'first' else len(step.frames) - 1
            elif isinstance(spec, int) and not isinstance(spec, bool):
                index = spec
            elif isinstance(spec, str) and spec.lstrip('-').isdigit():
                index = int(spec)
            else:
                raise ValueError('frame must be first, last, or an integer index')
            if index < 0:
                index += len(step.frames)
            if not 0 <= index < len(step.frames):
                raise ValueError('Frame index out of range')
            frame = step.frames[index]
            field_name = query.get('field', 'S')
            if field_name == 'FREQUENCY':
                frequency = float(frame.frequency)
                if not math.isfinite(frequency):
                    raise ValueError('Non-finite frequency')
                item['value'] = frequency
                meta.update(step=step_name, frame=index, field=field_name, mode=getattr(frame, 'mode', None))
                results.append(item)
                continue
            field = frame.fieldOutputs[field_name]
            region = query.get('region', '')
            if region:
                field = field.getSubset(region=region_object(region))
            position = query.get('position', '')
            if position:
                if position not in ('NODAL', 'INTEGRATION_POINT', 'ELEMENT_NODAL', 'CENTROID'):
                    raise ValueError('Unsupported output position: ' + position)
                field = field.getSubset(position=getattr(constants, position), readOnly=True)
            component = query.get('component', '')
            invariant = query.get('invariant', '')
            # Accept the documented legacy Magnitude/Mises component aliases.
            if component.lower().replace('_', '') in invariants and not invariant:
                invariant, component = component, ''
            if invariant and component:
                raise ValueError('Choose either component or invariant')
            if invariant:
                constant = invariants.get(invariant.lower().replace('_', ''))
                if constant is None:
                    raise ValueError('Unsupported invariant: ' + invariant)
                field = field.getScalarField(invariant=getattr(constants, constant))
            elif component:
                field = field.getScalarField(componentLabel=component)
            values = []
            section = query.get('section_point')
            for value in field.values:
                if section is not None and getattr(getattr(value, 'sectionPoint', None), 'number', None) != section:
                    continue
                try:
                    data = value.data
                except Exception:
                    data = value.dataDouble
                if not isinstance(data, (int, float)):
                    raise ValueError('Vector/tensor field requires a component or invariant')
                number = float(data)
                if not math.isfinite(number):
                    raise ValueError('Field contains non-finite data')
                values.append(number)
            if not values:
                raise ValueError('No values extracted')
            aggregation = query.get('aggregation', 'max')
            operations = {
                'max': lambda: max(values), 'min': lambda: min(values),
                'sum': lambda: math.fsum(values), 'avg': lambda: math.fsum(values) / len(values),
                'range': lambda: max(values) - min(values),
                'abs_max': lambda: max(abs(v) for v in values), 'raw': lambda: values,
            }
            if aggregation not in operations:
                raise ValueError('Unsupported aggregation: ' + aggregation)
            item['value'] = operations[aggregation]()
            meta.update(step=step_name, frame=index, frameValue=float(frame.frameValue),
                        field=field_name, region=region or 'ALL', position=position or 'STORED',
                        component=component, invariant=invariant, section_point=section,
                        value_count=len(values), aggregation=aggregation)
        except Exception as exc:
            item['error'] = str(exc)
        results.append(item)
    return results

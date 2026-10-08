"""Generate a reproducible small-block-on-large-base contact illustration (N, mm)."""
from pathlib import Path
import argparse
import math

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
parser.add_argument('--refinement', type=float, default=1)
parser.add_argument('--curved', action='store_true')
parser.add_argument('--friction', type=float, default=0)
parser.add_argument('--slide', type=float, default=0, help='Second-step horizontal punch displacement in mm')
parser.add_argument('--plastic', action='store_true', help='Illustrative hardening material; not a calibrated material')
args = parser.parse_args()
root = Path(args.output).resolve()
root.mkdir(parents=True, exist_ok=True)
if not 0.5 <= args.refinement <= 4:
    raise ValueError('refinement must be between 0.5 and 4')
if not math.isfinite(args.friction) or not 0 <= args.friction <= 1:
    raise ValueError('friction must be between 0 and 1')
if not math.isfinite(args.slide) or not 0 <= args.slide <= 1 or (args.slide and not args.friction):
    raise ValueError('slide must be between 0 and 1 and requires positive friction')
if args.plastic and not args.curved:
    raise ValueError('the illustrative plastic material requires --curved')
nodes, elements = [], []
def block(origin, size, divisions):
    nx, ny, nz = divisions
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                label = len(nodes) + 1
                ids[i, j, k] = label
                xyz = [origin[a] + size[a] * v / divisions[a] for a, v in enumerate((i, j, k))]
                nodes.append((label, *xyz))
    bottom, top = [], []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                conn = [ids[i+di, j+dj, k+dk] for di, dj, dk in
                        [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]]
                label = len(elements) + 1
                elements.append((label, *conn))
                if k == 0: bottom.append(label)
                if k == nz-1: top.append(label)
    return dict(bottom=bottom, top=top,
                base=[ids[i,j,0] for j in range(ny+1) for i in range(nx+1)],
                cap=[ids[i,j,nz] for j in range(ny+1) for i in range(nx+1)])

base = block((-10,-10,0), (20,20,8), tuple(round(v*args.refinement) for v in (16,16,6)))
base_nodes = len(nodes)
punch = block((-4,-4,8), (8,8,4), tuple(round(v*args.refinement) for v in (8,8,4)))
if args.curved:
    for i in range(base_nodes, len(nodes)):
        label, x, y, z = nodes[i]
        rise = 20 - math.sqrt(20**2 - x*x - y*y)
        nodes[i] = (label, x, y, z + rise * (12-z)/4)
lines = ['*HEADING', 'Localized square block contact, elastic steel, N-mm', '*NODE']
lines.extend(', '.join(map(str, row)) for row in nodes)
lines += ['*ELEMENT, TYPE=C3D8R, ELSET=BODY']
lines.extend(', '.join(map(str, row)) for row in elements)
def add_set(kind, name, values):
    lines.append('*' + kind + ', ' + kind + '=' + name)
    lines.extend(', '.join(map(str, values[i:i+16])) for i in range(0, len(values), 16))
add_set('NSET', 'FIXED', base['base'])
add_set('NSET', 'LOADED', punch['cap'])
add_set('ELSET', 'BASE_TOP', base['top'])
add_set('ELSET', 'PUNCH_BOTTOM', punch['bottom'])
lines += '''*SOLID SECTION, ELSET=BODY, MATERIAL=STEEL
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.3
*SURFACE, TYPE=ELEMENT, NAME=FOUNDATION
BASE_TOP, S2
*SURFACE, TYPE=ELEMENT, NAME=PUNCH
PUNCH_BOTTOM, S1
*SURFACE INTERACTION, NAME=FRICTIONLESS
*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=HARD
*CONTACT PAIR, INTERACTION=FRICTIONLESS, TYPE=SURFACE TO SURFACE, SMALL SLIDING
PUNCH, FOUNDATION
*BOUNDARY
FIXED, 1, 3
LOADED, 1, 2
*STEP, NAME=Indentation, NLGEOM=NO, INC=100
*STATIC
0.1, 1., 1e-7, 0.1
*BOUNDARY
LOADED, 3, 3, -0.02
*OUTPUT, FIELD
*NODE OUTPUT
U, RF
*ELEMENT OUTPUT
S, E
*CONTACT OUTPUT
CSTRESS, CDISP
*OUTPUT, HISTORY
*ENERGY OUTPUT
ALLSE, ALLAE
*END STEP'''.splitlines()
text = '\n'.join(lines) + '\n'
if args.curved:
    text = text.replace('210000, 0.3', '1000, 0.3').replace('NLGEOM=NO', 'NLGEOM=YES')
    text = text.replace('-0.02', '-0.2').replace('0.1, 1., 1e-7, 0.1', '0.02, 1., 1e-7, 0.1')
if args.plastic:
    text = text.replace('1000, 0.3\n', '1000, 0.3\n*PLASTIC\n5., 0.\n8., 0.1\n')
    text = text.replace('S, E\n', 'S, E, PEEQ\n')
if args.friction:
    text = text.replace('*SURFACE BEHAVIOR', '*FRICTION\n' + str(args.friction) + '\n*SURFACE BEHAVIOR')
    text = text.replace(', SMALL SLIDING', '')
    text = text.replace('PRESSURE-OVERCLOSURE=HARD', 'PRESSURE-OVERCLOSURE=HARD, DIRECT')
text = text.replace('ALLSE, ALLAE', 'ALLSE, ALLAE, ALLPD, ALLFD')
if args.slide:
    text += '''*STEP, NAME=Sliding, NLGEOM=YES, INC=200
*STATIC
0.02, 1., 1e-7, 0.1
*BOUNDARY
LOADED, 1, 1, {slide}
*OUTPUT, FIELD
*NODE OUTPUT
U, RF
*ELEMENT OUTPUT
S, E{plastic}
*CONTACT OUTPUT
CSTRESS, CDISP
*OUTPUT, HISTORY
*ENERGY OUTPUT
ALLSE, ALLAE, ALLPD, ALLFD
*END STEP
'''.format(slide=args.slide, plastic=', PEEQ' if args.plastic else '')
(root / 'analysis.inp').write_text(text, encoding='ascii')
print('Nodes:', len(nodes), 'Elements:', len(elements))

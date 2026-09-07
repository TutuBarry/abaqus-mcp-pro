"""Run pentagram star analysis and capture contour screenshots."""
import os
import sys
import base64

output_dir = os.path.join(os.path.dirname(__file__), "output", "pentagram_star")
cae_path = os.path.join(output_dir, "pentagram_star_3d.cae")

print("=== Opening CAE model ===")
from abaqus import openMdb
openMdb(cae_path)

from abaqus import mdb
print(f"Model: {mdb.models['Pentagram_Star_3D'].name}")

print("\n=== Submitting job ===")
job = mdb.jobs['pentagram_star_3d']
job.submit()
job.waitForCompletion()
print(f"Job status: {job.status}")

if job.status != 'COMPLETED':
    print("ERROR: Job did not complete successfully!")
    sys.exit(1)

print("\n=== Opening ODB ===")
from abaqus import session
from abaqusConstants import *

odb_path = os.path.join(output_dir, "pentagram_star_3d.odb")
vp_name = session.currentViewportName
vp = session.viewports[vp_name]

for odb_name in list(session.odbs.keys()):
    try:
        session.odbs[odb_name].close()
    except:
        pass

odb = session.openOdb(name=odb_path, readOnly=False)
vp.setValues(displayedObject=odb)
vp.odbDisplay.setFrame(step=0, frame=-1)

vp.odbDisplay.commonOptions.setValues(
    renderStyle=SHADED,
    visibleEdges=FEATURE,
    deformationScaling=UNIFORM,
    uniformScaleFactor=1.0,
)

print("\n=== Setting stress contour ===")
vp.odbDisplay.setPrimaryVariable(
    variableLabel="S",
    outputPosition=INTEGRATION_POINT,
    refinement=(INVARIANT, "Mises"),
)
vp.odbDisplay.contourOptions.setValues(
    contourStyle=CONTINUOUS,
    numIntervals=12,
    minAutoCompute=ON,
    maxAutoCompute=ON,
    showMinLocation=ON,
    showMaxLocation=ON,
)
vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
vp.view.fitView()

print("\n=== Capturing stress contour ===")
stress_path = os.path.join(output_dir, "pentagram_mises_stress.png")
session.printOptions.setValues(vpDecorations=True, vpBackground=False)
session.pngOptions.setValues(imageSize=(1600, 1000))
session.printToFile(
    fileName=stress_path,
    format=PNG,
    canvasObjects=(vp,),
)
print(f"Stress contour saved: {stress_path}")

print("\n=== Setting displacement contour ===")
vp.odbDisplay.setPrimaryVariable(
    variableLabel="U",
    outputPosition=NODAL,
    refinement=(INVARIANT, "Magnitude"),
)

print("\n=== Capturing displacement contour ===")
disp_path = os.path.join(output_dir, "pentagram_displacement.png")
session.printToFile(
    fileName=disp_path,
    format=PNG,
    canvasObjects=(vp,),
)
print(f"Displacement contour saved: {disp_path}")

print("\n=== Done ===")

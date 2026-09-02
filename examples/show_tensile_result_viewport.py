# -*- coding: utf-8 -*-
"""Open the classic tensile result in a visible Abaqus/CAE viewport.

Run with a GUI session:

    abaqus cae startup=examples/show_tensile_result_viewport.py

The script defaults to examples/output/classic_tensile and can be pointed at
other result files with ABAQUS_TENSILE_CAE and ABAQUS_TENSILE_ODB.
"""

from __future__ import print_function

import os

from abaqus import openMdb, session
from abaqusConstants import *
import visualization


try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

DEFAULT_WORK_DIR = os.environ.get(
    "ABAQUS_TENSILE_WORK_DIR",
    os.path.join(SCRIPT_DIR, "output", "classic_tensile"),
)
CAE_PATH = os.environ.get(
    "ABAQUS_TENSILE_CAE",
    os.path.join(DEFAULT_WORK_DIR, "classic_tensile_bar.cae"),
)
ODB_PATH = os.environ.get(
    "ABAQUS_TENSILE_ODB",
    os.path.join(DEFAULT_WORK_DIR, "classic_tensile_bar.odb"),
)


try:
    openMdb(pathName=CAE_PATH)
except Exception as exc:
    print("CAE open skipped; continuing with ODB display. Reason: %s" % exc)

odb = session.openOdb(name=ODB_PATH, path=ODB_PATH, readOnly=True)

viewport_name = "Viewport: 1"
if viewport_name not in session.viewports.keys():
    session.Viewport(name=viewport_name, origin=(0, 0), width=180, height=120)

viewport = session.viewports[viewport_name]
viewport.makeCurrent()
viewport.maximize()
viewport.setValues(displayedObject=odb)
viewport.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
viewport.odbDisplay.commonOptions.setValues(visibleEdges=FEATURE)
viewport.odbDisplay.contourOptions.setValues(contourType=LINE, numIntervals=12)
viewport.odbDisplay.setPrimaryVariable(
    variableLabel="S",
    outputPosition=INTEGRATION_POINT,
    refinement=(COMPONENT, "S11"),
)
viewport.view.setValues(session.views["Iso"])
viewport.view.fitView()

print("Visible Abaqus viewport is showing tensile S11 contours.")

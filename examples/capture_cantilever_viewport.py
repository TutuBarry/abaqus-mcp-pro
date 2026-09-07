import socket, json, uuid, base64, os, sys

def send_message(sock, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")

def read_message(sock):
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        nl = chunk.find(b"\n")
        if nl >= 0:
            chunks.append(chunk[:nl])
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))

def execute(code, timeout=60):
    sock = socket.create_connection(("127.0.0.1", 48152), timeout=timeout)
    sock.settimeout(timeout)
    payload = {"id": str(uuid.uuid4()), "method": "execute", "params": {"code": code, "timeout": timeout}}
    send_message(sock, payload)
    resp = read_message(sock)
    sock.close()
    return resp

odb_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\classic_cantilever\classic_cantilever_beam.odb"
out_dir = os.path.dirname(odb_path)

# --- Step 1: Open ODB, set deformed shape, display Mises stress ---
code_mises = r"""
from abaqus import session
from abaqusConstants import *
import sys

odb_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\classic_cantilever\classic_cantilever_beam.odb"
vp_name = session.currentViewportName
vp = session.viewports[vp_name]

try:
    for odb_name in list(session.odbs.keys()):
        session.odbs[odb_name].close()
except:
    pass

odb = session.openOdb(name=odb_path, readOnly=False)
vp.setValues(displayedObject=odb)

# Set to last frame of step[0] (Bending)
vp.odbDisplay.setFrame(step=0, frame=-1)

# Enable deformed shape with uniform scaling
vp.odbDisplay.commonOptions.setValues(
    renderStyle=SHADED,
    visibleEdges=FEATURE,
    deformationScaling=UNIFORM,
    uniformScaleFactor=1.0,
)

# Mises stress contour
vp.odbDisplay.setPrimaryVariable(
    variableLabel="S",
    outputPosition=INTEGRATION_POINT,
    refinement=(INVARIANT, "Mises"),
)

# Simple contour options
vp.odbDisplay.contourOptions.setValues(
    contourStyle=CONTINUOUS,
    numIntervals=12,
    minAutoCompute=ON,
    maxAutoCompute=ON,
    showMinLocation=ON,
    showMaxLocation=ON,
)

# **** Key: set plotState to show contours on deformed shape ****
vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))

vp.view.setValues(
    projection=PARALLEL,
    cameraPosition=(80, 60, 50),
    cameraUpVector=(0, 1, 0),
    cameraTarget=(50, 5, 5),
)
vp.view.fitView()
sys.stdout.flush()
result = {"odb_opened": True, "step": "Bending", "frame": "last", "variable": "S_Mises"}
"""

print("=== Opening ODB, deformed shape, Mises stress ===")
resp = execute(code_mises, timeout=60)
print(json.dumps(resp, indent=2, ensure_ascii=False))

if not resp.get("result", {}).get("ok"):
    print("ERROR: ODB setup failed, aborting")
    sys.exit(1)

# --- Capture function ---
capture_code = r"""
import os, base64, sys
from abaqus import session
import abaqusConstants

vp_name = session.currentViewportName
tmp_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\classic_cantilever\_temp_capture.png"
session.printToFile(fileName=tmp_path, format=abaqusConstants.PNG,
                    canvasObjects=(session.viewports[vp_name],))
sys.stdout.flush()
with open(tmp_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode("ascii")
result = {
    "success": True,
    "image_base64": image_base64,
    "size_bytes": int(len(image_base64) * 3 / 4),
}
"""

# --- Capture Mises ---
print("\n=== Capturing Mises stress viewport ===")
resp2 = execute(capture_code, timeout=60)
result2 = resp2.get("result", {}).get("return_value", {})
if result2.get("success"):
    image_b64 = result2.get("image_base64", "")
    stress_path = os.path.join(out_dir, "cantilever_mises_stress.png")
    with open(stress_path, "wb") as f:
        f.write(base64.b64decode(image_b64))
    print(f"Stress contour saved: {stress_path}  ({result2.get('size_bytes')} bytes)")
else:
    print("Mises capture failed:", json.dumps(resp2, indent=2, ensure_ascii=False))

# --- Step 2: Switch to displacement ---
code_disp = r"""
from abaqus import session
from abaqusConstants import *
import sys

vp = session.viewports[session.currentViewportName]
vp.odbDisplay.setPrimaryVariable(
    variableLabel="U",
    outputPosition=NODAL,
    refinement=(INVARIANT, "Magnitude"),
)
sys.stdout.flush()
result = {"switched": "U_Magnitude"}
"""

print("\n=== Switching to displacement magnitude ===")
resp3 = execute(code_disp, timeout=60)
print(json.dumps(resp3, indent=2, ensure_ascii=False))

# --- Capture displacement ---
print("\n=== Capturing displacement viewport ===")
resp4 = execute(capture_code, timeout=60)
result4 = resp4.get("result", {}).get("return_value", {})
if result4.get("success"):
    image_b64 = result4.get("image_base64", "")
    disp_path = os.path.join(out_dir, "cantilever_displacement.png")
    with open(disp_path, "wb") as f:
        f.write(base64.b64decode(image_b64))
    print(f"Displacement contour saved: {disp_path}  ({result4.get('size_bytes')} bytes)")
else:
    print("Displacement capture failed:", json.dumps(resp4, indent=2, ensure_ascii=False))

# Cleanup
try:
    os.remove(os.path.join(out_dir, "_temp_capture.png"))
except:
    pass
print("\n=== Done ===")

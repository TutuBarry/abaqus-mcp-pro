import socket, json, uuid, base64

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

# First open the ODB and display stress contour
code1 = r'''
from abaqus import session
from abaqusConstants import *

# Open the ODB in the current viewport
odb_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\classic_tensile\classic_tensile_bar.odb"
vp_name = session.currentViewportName
vp = session.viewports[vp_name]

# Open the ODB
odb = session.openOdb(name=odb_path, readOnly=True)
vp.setValues(displayedObject=odb)

# Show stress contour
vp.odbDisplay.setPrimaryVariable(
    variableLabel="S",
    outputPosition=INTEGRATION_POINT,
    refinement=(COMPONENT, "S11"),
)
vp.odbDisplay.commonOptions.setValues(renderStyle=SHADED)

result = {"odb_opened": True, "viewport": vp_name}
'''

print("=== Opening ODB and displaying stress ===")
resp = execute(code1, timeout=60)
print(json.dumps(resp, indent=2, ensure_ascii=False))

# Capture viewport
code2 = r'''
import os, tempfile, base64
from abaqus import session
import abaqusConstants

vp_name = session.currentViewportName
fmt = abaqusConstants.PNG

handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
tmp_path = handle.name
handle.close()

try:
    session.printToFile(fileName=tmp_path, format=fmt, canvasObjects=(session.viewports[vp_name],))
    with open(tmp_path, "rb") as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode("ascii")
    result = {
        "success": True,
        "viewport": vp_name,
        "image_base64": image_base64,
        "size_bytes": int(len(image_base64) * 3 / 4),
    }
finally:
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
'''

print("=== Capturing viewport ===")
resp2 = execute(code2, timeout=60)
result2 = resp2.get("result", {}).get("return_value", {})
if result2.get("success"):
    image_b64 = result2.get("image_base64", "")
    output_path = r"R:\100_Private\WQG\codex\ABAQUS MCP\abaqus-mcp-pro\examples\output\classic_tensile\viewport.png"
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(image_b64))
    print(f"Viewport saved: {output_path}, size: {result2.get('size_bytes')} bytes")
else:
    print("Capture failed:", json.dumps(resp2, indent=2, ensure_ascii=False))

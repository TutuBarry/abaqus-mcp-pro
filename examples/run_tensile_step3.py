import socket, json, uuid, os

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

# Step 3: Extract results
code3 = r'''
import os
import json
from odbAccess import openOdb

JOB_NAME = "classic_tensile_bar"
WORK_DIR = os.getcwd()
length = 100.0
area = 100.0
imposed_u1 = 1.0

odb_path = os.path.join(WORK_DIR, JOB_NAME + ".odb")
odb = openOdb(path=odb_path, readOnly=True)
step = odb.steps["Tension"]
frame = step.frames[-1]

stress = frame.fieldOutputs["S"]
displacement = frame.fieldOutputs["U"]
reaction = frame.fieldOutputs["RF"]
pulled_nodes = odb.rootAssembly.nodeSets["PULLED_END_NODES"]

total_rf1 = 0.0
for value in reaction.getSubset(region=pulled_nodes).values:
    total_rf1 += value.data[0]

s11_total = 0.0
s11_count = 0
max_mises = 0.0
for value in stress.values:
    s11_total += value.data[0]
    s11_count += 1
    if value.mises > max_mises:
        max_mises = value.mises

max_u1 = 0.0
for value in displacement.values:
    if abs(value.data[0]) > max_u1:
        max_u1 = abs(value.data[0])

engineering_strain = imposed_u1 / length
nominal_stress = abs(total_rf1) / area
apparent_modulus = nominal_stress / engineering_strain
average_s11 = s11_total / float(s11_count)

summary = {
    "case": "Classic 3D tensile bar, displacement-controlled static tension",
    "units": "N-mm-MPa",
    "geometry_mm": {"length": length, "width": 10.0, "height": 10.0, "area": area},
    "material": {"E_MPa": 210000.0, "nu": 0.30},
    "load": {"right_end_prescribed_U1_mm": imposed_u1},
    "boundary_condition": "left end encastre; right end U1=1 mm, lateral DOF free",
    "mesh": {"element_type": "C3D8R", "global_size_mm": 5.0},
    "results": {
        "engineering_strain": float(engineering_strain),
        "total_reaction_force_N": float(total_rf1),
        "nominal_stress_MPa": float(nominal_stress),
        "apparent_modulus_MPa": float(apparent_modulus),
        "average_S11_MPa": float(average_s11),
        "max_U1_mm": float(max_u1),
        "max_mises_stress_MPa": float(max_mises),
    },
    "files": {
        "cae": os.path.join(WORK_DIR, JOB_NAME + ".cae"),
        "odb": odb_path,
    },
}

odb.close()

result = summary
'''

print("=== Step 3: Extracting results ===")
resp = execute(code3, timeout=60)
print(json.dumps(resp, indent=2, ensure_ascii=False))

import socket, json, uuid, os, time

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

def execute(code, timeout=300):
    sock = socket.create_connection(("127.0.0.1", 48152), timeout=timeout)
    sock.settimeout(timeout)
    payload = {"id": str(uuid.uuid4()), "method": "execute", "params": {"code": code, "timeout": timeout}}
    send_message(sock, payload)
    resp = read_message(sock)
    sock.close()
    return resp

# Step 2: Submit and wait for job
code2 = r'''
from abaqus import mdb
import os

JOB_NAME = "classic_tensile_bar"
job = mdb.jobs[JOB_NAME]
job.submit(consistencyChecking=False)
job.waitForCompletion()
result = {"job_done": True, "job_name": JOB_NAME, "status": str(getattr(job, "status", "UNKNOWN"))}
'''

print("=== Step 2: Submitting job ===")
resp = execute(code2, timeout=300)
print(json.dumps(resp, indent=2, ensure_ascii=False))

import socket, json, uuid

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

sock = socket.create_connection(("127.0.0.1", 48152), timeout=30)
sock.settimeout(30)
code = "result = {'cwd': __import__('os').getcwd(), 'ok': True}"
payload = {"id": str(uuid.uuid4()), "method": "execute", "params": {"code": code, "timeout": 30}}
send_message(sock, payload)
resp = read_message(sock)
sock.close()
print(json.dumps(resp, indent=2, ensure_ascii=False))

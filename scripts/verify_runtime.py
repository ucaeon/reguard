"""Exercise the built web proxy with isolated stub services; no production ports."""

import json
import subprocess
import time
import urllib.request
import urllib.error
import uuid

suffix = uuid.uuid4().hex[:10]
network = "reguard-proxy-test-" + suffix
backend = network + "-backend"
web = network + "-web"


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], stderr=subprocess.PIPE, text=True
    ).strip()


stub = """
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, threading
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'port':self.server.server_port,'path':self.path}).encode())
    def log_message(self,*args): pass
for port in [8081,8082,8083]:
    threading.Thread(target=ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever,daemon=True).start()
threading.Event().wait()
"""
try:
    docker("network", "create", network)
    docker(
        "run",
        "-d",
        "--name",
        backend,
        "--network",
        network,
        "--network-alias",
        "member",
        "--network-alias",
        "safety",
        "--network-alias",
        "notification",
        "--entrypoint",
        "python",
        "reguard-airflow:3.1.8",
        "-c",
        stub,
    )
    docker(
        "run",
        "-d",
        "--name",
        web,
        "--network",
        network,
        "-p",
        "127.0.0.1::8080",
        "-e",
        "PUBLIC_DOMAIN=http://:8080",
        "reguard-web:validation",
    )
    port = json.loads(docker("inspect", web))[0]["NetworkSettings"]["Ports"][
        "8080/tcp"
    ][0]["HostPort"]
    origin = "http://127.0.0.1:" + port
    for _ in range(50):
        try:
            with urllib.request.urlopen(origin, timeout=1) as response:
                assert b"<html" in response.read()
                break
        except OSError:
            time.sleep(0.2)
    else:
        raise RuntimeError("Proxy startup timeout")
    for path, expected in [
        ("/api/v1/auth/csrf", 8081),
        ("/api/v1/me", 8081),
        ("/api/v1/me/products", 8081),
        ("/api/v1/me/notifications", 8083),
        ("/api/v1/me/notifications/csrf", 8083),
        ("/api/v1/products?q=test", 8082),
        ("/api/v1/recalls", 8082),
    ]:
        with urllib.request.urlopen(origin + path, timeout=5) as response:
            body = json.load(response)
            assert body == {"port": expected, "path": path}, body
    with urllib.request.urlopen(origin + "/reset-password?token=test") as response:
        assert b"<html" in response.read()
    try:
        urllib.request.urlopen(origin + "/actuator/health")
        raise AssertionError("Management endpoint exposed")
    except urllib.error.HTTPError as error:
        assert error.code == 404
    print(
        "PASS: same-origin API routing, notification route precedence, query strings, SPA deep links, management endpoint blocked"
    )
finally:
    for container in [web, backend]:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    subprocess.run(["docker", "network", "rm", network], capture_output=True)

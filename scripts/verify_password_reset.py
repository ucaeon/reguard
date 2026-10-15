from pathlib import Path
import json, os, socket, subprocess, time, urllib.request, urllib.error, uuid
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
env = {
    **os.environ,
    **{k: v for k, v in dotenv_values(root / ".env").items() if v is not None},
}
java = (
    str(Path(os.environ["JAVA_HOME"]) / "bin/java")
    if os.environ.get("JAVA_HOME")
    else "java"
)
users = []
processes = []
logs = []


def db(sql):
    return subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "reguard-local-postgres-1",
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "reguard_member",
            "-d",
            "reguard_member",
        ],
        input=sql,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def request(method, path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if not token and method not in ("GET", "HEAD", "OPTIONS"):
        with urllib.request.urlopen(
            "http://127.0.0.1:18081/api/v1/auth/csrf", timeout=10
        ) as csrf_response:
            csrf = json.load(csrf_response)
            headers[csrf["headerName"]] = csrf["token"]
            headers["Cookie"] = "; ".join(
                value.split(";", 1)[0]
                for value in csrf_response.headers.get_all("Set-Cookie", [])
            )
    req = urllib.request.Request(
        "http://127.0.0.1:18081/api/v1" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            status, data = res.status, res.read()
    except urllib.error.HTTPError as e:
        status, data = e.code, e.read()
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    return json.loads(data) if data else None


def start(service, port, extra=None):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
    log = open("/tmp/reguard-" + service + "-integration.log", "w")
    logs.append(log)
    p = subprocess.Popen(
        [
            java,
            "-jar",
            str(root / f"services/{service}/target/{service}-0.0.1-SNAPSHOT.jar"),
        ],
        env={**env, "SERVER_PORT": str(port), **(extra or {})},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    processes.append(p)
    for _ in range(120):
        if p.poll() is not None:
            raise RuntimeError(service + " startup failed; inspect its integration log")
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/actuator/health/readiness", timeout=2
            ) as res:
                if json.load(res)["status"] == "UP":
                    return p
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError(service + " readiness timeout")


import socketserver, threading, queue, email as email_module, email.policy, re

messages = queue.Queue()


class SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 localhost test SMTP\r\n")
        while line := self.rfile.readline():
            command = line.decode().strip().upper()
            if command.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-localhost\r\n250 8BITMIME\r\n")
            elif command == "DATA":
                self.wfile.write(b"354 End with dot\r\n")
                data = []
                while True:
                    row = self.rfile.readline()
                    if not row or row == b".\r\n":
                        break
                    data.append(row)
                messages.put(b"".join(data))
                self.wfile.write(b"250 accepted\r\n")
            elif command == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                break
            else:
                self.wfile.write(b"250 OK\r\n")


class Sink(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


sink = Sink(("127.0.0.1", 18025), SMTP)
thread = threading.Thread(target=sink.serve_forever, daemon=True)
thread.start()


def receive_token():
    msg = email_module.message_from_bytes(
        messages.get(timeout=10), policy=email.policy.default
    )
    body = msg.get_content()
    return re.search(r"token=([A-Za-z0-9_-]{43})", body).group(1)


try:
    start(
        "member-service",
        18081,
        {
            "ALERTS_ENABLED": "false",
            "MAIL_ENABLED": "true",
            "MAIL_FROM": "test@example.test",
            "SMTP_HOST": "127.0.0.1",
            "SMTP_PORT": "18025",
            "SMTP_AUTH": "false",
            "SMTP_STARTTLS": "false",
            "SMTP_SSL": "false",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "PASSWORD_RESET_URL": "http://localhost:3000/reset-password",
        },
    )
    address = f"reset-{uuid.uuid4().hex}@example.com"
    old = "Old-" + uuid.uuid4().hex
    new = "New-" + uuid.uuid4().hex
    request("POST", "/auth/signup/email/request", {"email": address}, expected=204)
    message = email_module.message_from_bytes(
        messages.get(timeout=10), policy=email.policy.default
    )
    code = re.search(r"(?<![0-9])[0-9]{6}(?![0-9])", message.get_content()).group(0)
    proof = request(
        "POST", "/auth/signup/email/verify", {"email": address, "code": code}
    )["verificationToken"]
    user = request(
        "POST",
        "/auth/signup",
        {
            "email": address,
            "password": old,
            "displayName": "reset test",
            "verificationToken": proof,
        },
        expected=201,
    )
    users.append(str(uuid.UUID(user["id"])))
    access = request("POST", "/auth/token", {"email": address, "password": old})[
        "accessToken"
    ]
    # Exercise the real safety/member connection with an authenticated account.
    with urllib.request.urlopen(
        "http://127.0.0.1:8082/api/v1/products?q=%EC%9A%B0%EC%9C%A0&size=1", timeout=15
    ) as response:
        product = json.load(response)["items"][0]
    catalog = request(
        "POST",
        "/me/products",
        {"registrationType": "CATALOG", "catalogProductId": product["id"]},
        token=access,
        expected=201,
    )
    assert catalog["catalogProductId"] == product["id"]
    assert catalog["identifierType"] == "KC_CERT_NO" and catalog["identifierValue"]
    catalog_path = "/me/products/" + catalog["id"]
    assert request("GET", catalog_path, token=access)["id"] == catalog["id"]
    request(
        "PATCH", catalog_path, {"productName": "forbidden"}, token=access, expected=400
    )
    request("PATCH", catalog_path, {"lotNumber": "INTEGRATION-TEST"}, token=access)
    assert request("GET", catalog_path, token=access)["lotNumber"] == "INTEGRATION-TEST"
    manual = request(
        "POST",
        "/me/products",
        {"registrationType": "MANUAL", "productName": "통합 점검 물건"},
        token=access,
        expected=201,
    )
    manual_path = "/me/products/" + manual["id"]
    assert (
        request("GET", manual_path + "/recalls", token=access)["lookupStatus"]
        == "INSUFFICIENT_DETAILS"
    )
    request("PATCH", manual_path, {"productName": "수정된 점검 물건"}, token=access)
    assert (
        request("GET", manual_path, token=access)["productName"] == "수정된 점검 물건"
    )
    stranger = "owner-check-" + uuid.uuid4().hex + "@example.test"
    request("POST", "/auth/signup/email/request", {"email": stranger}, expected=204)
    mail = email_module.message_from_bytes(
        messages.get(timeout=10), policy=email.policy.default
    )
    stranger_code = re.search(r"(?<![0-9])[0-9]{6}(?![0-9])", mail.get_content()).group(
        0
    )
    stranger_proof = request(
        "POST", "/auth/signup/email/verify", {"email": stranger, "code": stranger_code}
    )["verificationToken"]
    other = request(
        "POST",
        "/auth/signup",
        {
            "email": stranger,
            "password": old,
            "displayName": "권한 점검",
            "verificationToken": stranger_proof,
        },
        expected=201,
    )
    users.append(str(uuid.UUID(other["id"])))
    other_token = request("POST", "/auth/token", {"email": stranger, "password": old})[
        "accessToken"
    ]
    for method in ["GET", "PATCH", "DELETE"]:
        request(
            method,
            manual_path,
            {"productName": "unauthorized"} if method == "PATCH" else None,
            token=other_token,
            expected=404,
        )
    assert request("GET", "/me/products", token=other_token)["items"] == []
    for path in [catalog_path, manual_path]:
        request("DELETE", path, token=access, expected=204)
        request("GET", path, token=access, expected=404)
    print(
        "PASS: catalog/manual create, persisted edits, catalog identity protection, deletion, cross-account isolation"
    )
    expected = request(
        "POST", "/auth/password-reset/request", {"email": address}, expected=202
    )
    first = receive_token()
    unknown = request(
        "POST",
        "/auth/password-reset/request",
        {"email": f"unknown-{uuid.uuid4().hex}@example.com"},
        expected=202,
    )
    assert unknown == expected and messages.empty()
    request("POST", "/auth/password-reset/request", {"email": address}, expected=429)
    assert messages.empty()
    assert (
        db(f"SELECT count(*) FROM password_reset_tokens WHERE user_id='{users[0]}'")
        == "1"
    )
    import hashlib

    reset_bucket = hashlib.sha256(
        f"reset-account-minute:{address.lower()}".encode()
    ).hexdigest()
    db(
        f"UPDATE auth_request_limits SET expires_at=now()-interval '1 second' WHERE bucket_hash='{reset_bucket}'"
    )
    request("POST", "/auth/password-reset/request", {"email": address}, expected=202)
    second = receive_token()
    assert first != second
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": first, "newPassword": new},
        expected=400,
    )
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": second, "newPassword": "short"},
        expected=400,
    )
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": second, "newPassword": new},
        expected=204,
    )
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": second, "newPassword": new},
        expected=400,
    )
    request("GET", "/me", token=access, expected=401)
    request("POST", "/auth/token", {"email": address, "password": old}, expected=401)
    request("POST", "/auth/token", {"email": address, "password": new})
    db(
        f"UPDATE auth_request_limits SET expires_at=now()-interval '1 second' WHERE bucket_hash='{reset_bucket}'"
    )
    request("POST", "/auth/password-reset/request", {"email": address}, expected=202)
    expired = receive_token()
    db(
        f"UPDATE password_reset_tokens SET expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE user_id='{users[0]}'"
    )
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": expired, "newPassword": old},
        expected=400,
    )
    db(
        f"UPDATE auth_request_limits SET expires_at=now()-interval '1 second' WHERE bucket_hash='{reset_bucket}'"
    )
    request("POST", "/auth/password-reset/request", {"email": address}, expected=202)
    pending = receive_token()
    current = request("POST", "/auth/token", {"email": address, "password": new})[
        "accessToken"
    ]
    request(
        "POST",
        "/me/profile/password",
        {"currentPassword": new, "newPassword": old},
        token=current,
    )
    request(
        "POST",
        "/auth/password-reset/confirm",
        {"token": pending, "newPassword": new},
        expected=400,
    )
    request("GET", "/me", token=current, expected=401)
    request("POST", "/auth/token", {"email": address, "password": old})
    print(
        "PASS: profile password change revokes pending reset link and authenticated sessions"
    )
    print(
        "PASS: reset SMTP message, uniform unknown-email response, old-link invalidation, password validation, one-use token, token expiry, old-session revocation and new-password login; no external email sent"
    )
finally:
    for p in reversed(processes):
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
    for log in logs:
        log.close()
    sink.shutdown()
    sink.server_close()
    if users:
        ids = ",".join("'" + str(uuid.UUID(x)) + "'" for x in users)
        db(
            f"BEGIN; DELETE FROM password_reset_tokens WHERE user_id IN ({ids}); DELETE FROM access_tokens WHERE user_id IN ({ids}); DELETE FROM users WHERE id IN ({ids}); COMMIT;"
        )
    print("Reset test data removed.")

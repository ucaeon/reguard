from signup_fixture import verified_signup
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


try:
    safety = start("safety-service", 18082)
    start(
        "member-service",
        18081,
        {"SAFETY_BASE_URL": "http://127.0.0.1:18082", "ALERTS_ENABLED": "false"},
    )
    request("GET", "/me", expected=401)
    request("GET", "/me", token="fake", expected=401)
    suffix = uuid.uuid4().hex
    password = "Member-test-" + uuid.uuid4().hex
    tokens = []
    for n in range(2):
        email = f"reguard-test-{suffix}-{n}@example.com"
        user = verified_signup(
            request,
            {"email": email, "password": password, "displayName": "테스트"},
            expected=201,
        )
        users.append(str(uuid.UUID(user["id"])))
        assert "password" not in user and "passwordHash" not in user
        token = request(
            "POST", "/auth/token", {"email": email.upper(), "password": password}
        )["accessToken"]
        tokens.append(token)
        assert request("GET", "/me", token=token)["id"] == user["id"]
    email = f"reguard-test-{suffix}-0@example.com"
    verified_signup(
        request,
        {"email": email.upper(), "password": password, "displayName": "중복"},
        expected=409,
    )
    request(
        "POST",
        "/auth/signup",
        {"email": "invalid", "password": password, "displayName": "이름"},
        expected=400,
    )
    request(
        "POST",
        "/auth/token",
        {"email": email, "password": "wrong-password"},
        expected=401,
    )
    request(
        "POST",
        "/auth/signup",
        {"email": "a@example.com", "password": "가" * 25, "displayName": "이름"},
        expected=400,
    )
    assert (
        db(f"SELECT password_hash LIKE '$2%' FROM users WHERE id='{users[0]}';") == "t"
    )
    token = tokens[0]
    manual = request(
        "POST",
        "/me/products",
        {"registrationType": "MANUAL", "productName": "슬라임", "lotNumber": "A"},
        token,
        201,
    )
    path = "/me/products/" + manual["id"]
    for method, tail, body in [
        ("GET", "", None),
        ("PATCH", "", {"productName": "공격"}),
        ("DELETE", "", None),
        ("GET", "/recalls", None),
    ]:
        request(method, path + tail, body, tokens[1], 404)
    assert request("GET", "/me/products", token=tokens[1])["items"] == []
    request(
        "POST",
        "/me/products",
        {"registrationType": "MANUAL", "productName": "x", "userId": users[1]},
        token,
        400,
    )
    request("PATCH", path, {"expiryDate": "2027-02-30"}, token, 400)
    changed = request(
        "PATCH", path, {"lotNumber": None, "expiryDate": "2027-01-01"}, token
    )
    assert changed["lotNumber"] is None and changed["productName"] == "슬라임"
    assert (
        request("GET", path + "/recalls", token=token)["lookupStatus"]
        == "INSUFFICIENT_DETAILS"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "reguard-local-postgres-1",
            "psql",
            "-X",
            "-At",
            "-U",
            "reguard_safety",
            "-d",
            "reguard_safety",
            "-c",
            "SELECT product_id FROM recall_product_matches LIMIT 1",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert result, "Run food matching before this integration test"
    catalog = request(
        "POST",
        "/me/products",
        {"registrationType": "CATALOG", "catalogProductId": result},
        token,
        201,
    )
    catpath = "/me/products/" + catalog["id"]
    request("PATCH", catpath, {"productName": "조작"}, token, 400)
    linked = request("GET", catpath + "/recalls", token=token)
    assert linked["lookupStatus"] == "LOOKUP_COMPLETE" and linked["items"]
    assert all(x["eligibilityStatus"] == "NEEDS_CHECK" for x in linked["items"])
    request(
        "POST",
        "/me/products",
        {
            "registrationType": "CATALOG",
            "catalogProductId": "00000000-0000-0000-0000-000000000000",
        },
        token,
        404,
    )
    first = request("GET", "/me/products?size=1", token=token)
    second = request("GET", "/me/products?size=1&page=1", token=token)
    assert first["hasNext"] and first["items"][0]["id"] != second["items"][0]["id"]
    request("DELETE", path, token=token, expected=204)
    request("GET", path, token=token, expected=404)
    safety.terminate()
    safety.wait(timeout=15)
    assert (
        request(
            "POST",
            "/me/products",
            {"registrationType": "CATALOG", "catalogProductId": result},
            token,
            503,
        )["code"]
        == "SAFETY_UNAVAILABLE"
    )
    request("GET", catpath + "/recalls", token=token, expected=503)
    request("GET", "/me", token=token)
    request("POST", "/auth/logout", token=token, expected=204)
    request("GET", "/me", token=token, expected=401)
    db(
        f"UPDATE access_tokens SET expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE user_id='{users[1]}';"
    )
    request("GET", "/me", token=tokens[1], expected=401)
    print(
        "PASS: signup/login/hash, duplicate email, authentication, ownership isolation, CRUD, pagination, HTTP recall integration, Safety outage, logout and expiry"
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
    if users:
        ids = ",".join("'" + str(uuid.UUID(x)) + "'" for x in users)
        db(
            f"BEGIN; DELETE FROM alert_outbox WHERE user_id IN ({ids}); DELETE FROM password_reset_tokens WHERE user_id IN ({ids}); DELETE FROM access_tokens WHERE user_id IN ({ids}); DELETE FROM owned_products WHERE user_id IN ({ids}); DELETE FROM users WHERE id IN ({ids}); COMMIT;"
        )
        print("Test accounts and their data removed.")

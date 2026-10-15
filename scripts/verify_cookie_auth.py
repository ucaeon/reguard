from pathlib import Path
import hashlib, json, os, socket, subprocess, time, urllib.request, urllib.error, uuid
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
verification_emails = []
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


import http.cookiejar

jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def browser(method, path, body=None, csrf=None, port=18081, expected=200, extra=None):
    headers = {"Content-Type": "application/json", **(extra or {})}
    if csrf:
        headers[csrf["headerName"]] = csrf["token"]
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        with client.open(req, timeout=15) as res:
            status, data, response_headers = res.status, res.read(), res.headers
    except urllib.error.HTTPError as e:
        status, data, response_headers = e.code, e.read(), e.headers
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    return (json.loads(data) if data else None), response_headers


try:
    start(
        "member-service",
        18081,
        {"ALERTS_ENABLED": "false", "COOKIE_SECURE": "false", "MAIL_ENABLED": "false"},
    )
    start(
        "notification-service",
        18083,
        {
            "ALERTS_ENABLED": "false",
            "COOKIE_SECURE": "false",
            "MEMBER_BASE_URL": "http://127.0.0.1:18081",
        },
    )
    address = f"cookie-{uuid.uuid4().hex}@example.com"
    password = "Cookie-" + uuid.uuid4().hex
    signup = {"email": address, "password": password, "displayName": "cookie test"}
    assert (
        browser("POST", "/auth/signup", signup, expected=403)[0]["code"]
        == "CSRF_INVALID"
    )
    csrf, headers = browser("GET", "/auth/csrf")
    assert "no-store" in headers["Cache-Control"]
    assert any(
        c.name == "REGUARD_MEMBER_CSRF" and c.has_nonstandard_attr("HttpOnly")
        for c in jar
    )
    # Cookie tests seed only the email-delivery fixture; verification still uses the API.
    # SMTP delivery is covered by verify_password_reset.py.
    verification_emails.append(address)
    code = "123456"
    digest = hashlib.sha256(f"{address}:{code}".encode()).hexdigest()
    db(f"INSERT INTO signup_email_verifications(email,code_hash,expires_at) VALUES ('{address}','{digest}',now()+interval '10 minutes')")
    proof, _ = browser("POST", "/auth/signup/email/verify", {"email": address, "code": code}, csrf)
    signup["verificationToken"] = proof["verificationToken"]
    user, _ = browser("POST", "/auth/signup", signup, csrf, expected=201)
    users.append(user["id"])
    browser("POST", "/auth/login", signup, expected=403)
    login, headers = browser(
        "POST", "/auth/login", {"email": address, "password": password}, csrf
    )
    assert login["authentication"] == "COOKIE" and "accessToken" not in login
    auth_cookie = next(
        x for x in headers.get_all("Set-Cookie", []) if x.startswith("REGUARD_SESSION=")
    )
    assert (
        "HttpOnly" in auth_cookie
        and "SameSite=Lax" in auth_cookie
        and "Path=/" in auth_cookie
    )
    assert "Max-Age=" in auth_cookie and "Domain=" not in auth_cookie
    saved = next(c.value for c in jar if c.name == "REGUARD_SESSION")
    assert browser("GET", "/me")[0]["id"] == user["id"]
    manual = {"registrationType": "MANUAL", "productName": "cookie item"}
    browser("POST", "/me/products", manual, expected=403)
    browser("POST", "/me/products", manual, csrf, expected=403)
    csrf, _ = browser("GET", "/auth/csrf")
    tampered = {**csrf, "token": "invalid"}
    browser("POST", "/me/products", manual, tampered, expected=403)
    browser(
        "POST",
        "/me/products",
        manual,
        csrf,
        expected=400,
        extra={"Authorization": "Bearer " + saved},
    )
    item, _ = browser("POST", "/me/products", manual, csrf, expected=201)
    changed, _ = browser("PATCH", "/me/products/" + item["id"], {"productName":"updated cookie item"}, csrf)
    assert changed["productName"] == "updated cookie item"
    refreshed, _ = browser("GET", "/me/products")
    assert any(row["id"] == item["id"] and row["productName"] == "updated cookie item" for row in refreshed["items"])
    browser("DELETE", "/me/products/" + item["id"], expected=403)
    browser("DELETE", "/me/products/" + item["id"], csrf=csrf, expected=204)
    refreshed, _ = browser("GET", "/me/products")
    assert all(row["id"] != item["id"] for row in refreshed["items"])
    notification_id = str(uuid.uuid4())
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "reguard-local-postgres-1",
            "psql",
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "reguard_notification",
            "-d",
            "reguard_notification",
        ],
        input=f"INSERT INTO notifications(id,user_id,owned_product_id,recall_id,notification_type,title,message) VALUES ('{notification_id}','{user['id']}','{uuid.uuid4()}','{uuid.uuid4()}','TEST','test','test');",
        text=True,
        check=True,
        capture_output=True,
    )
    assert browser("GET", "/me/notifications", port=18083)[0]["items"]
    assert browser("GET", "/me/notifications/unread-count", port=18083)[0]["count"] == 1
    route = "/me/notifications/" + notification_id + "/read"
    browser("PATCH", route, port=18083, expected=403)
    browser("PATCH", route, csrf=csrf, port=18083, expected=403)
    ncsrf, _ = browser("GET", "/me/notifications/csrf", port=18083)
    assert browser("PATCH", route, csrf=ncsrf, port=18083)[0]["readAt"]
    assert browser("GET", "/me/notifications/unread-count", port=18083)[0]["count"] == 0
    _, cors = browser(
        "OPTIONS",
        "/me/products",
        extra={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-xsrf-token",
        },
    )
    assert (
        cors["Access-Control-Allow-Origin"] == "http://localhost:3000"
        and cors["Access-Control-Allow-Credentials"] == "true"
    )

    req = urllib.request.Request(
        "http://127.0.0.1:18081/api/v1/auth/csrf",
        headers={"Origin": "https://untrusted.example"},
    )
    try:
        client.open(req)
    except urllib.error.HTTPError as e:
        assert e.code == 403
    else:
        raise AssertionError("untrusted origin allowed")
    browser("POST", "/auth/logout", expected=403)
    browser("POST", "/auth/logout", csrf=csrf, expected=204)
    assert not any(c.name == "REGUARD_SESSION" for c in jar)
    browser("GET", "/me", expected=401)
    browser("GET", "/me/notifications", port=18083, expected=401)
    request("GET", "/me", token=saved, expected=401)

    csrf, _ = browser("GET", "/auth/csrf", extra={"Cookie": "REGUARD_SESSION=" + saved})
    browser("POST", "/auth/login", {"email": address, "password": password}, csrf)
    print(
        "PASS: cookie-only login and identity; CSRF absent/tampered/stale/wrong-service blocked; mixed credentials rejected; valid writes, logout/revocation, expired-cookie recovery and explicit CORS"
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
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "reguard-local-postgres-1",
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "reguard_notification",
                "-d",
                "reguard_notification",
            ],
            input=f"DELETE FROM notifications WHERE user_id IN ({ids});",
            text=True,
            check=True,
            capture_output=True,
        )
        db(
            f"BEGIN; DELETE FROM alert_outbox WHERE user_id IN ({ids}); DELETE FROM owned_products WHERE user_id IN ({ids}); DELETE FROM password_reset_tokens WHERE user_id IN ({ids}); DELETE FROM access_tokens WHERE user_id IN ({ids}); DELETE FROM users WHERE id IN ({ids}); COMMIT;"
        )
    for address in verification_emails:
        db(f"DELETE FROM signup_email_verifications WHERE email='{address}'")
    print("Cookie test accounts and records removed.")

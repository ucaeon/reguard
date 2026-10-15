"""Exercise the real local gateway and retained database across Pod replacement."""

import hashlib
import http.cookiejar
import json
import secrets
import time
import urllib.error
import urllib.request
from local_k3s import kube

ORIGIN = "http://127.0.0.1:13000"
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(method, path, body=None, expected=200):
    headers = {"Content-Type": "application/json", "Origin": ORIGIN}
    if method not in ("GET", "HEAD"):
        csrfpath = (
            "/me/notifications/csrf"
            if path.startswith("/me/notifications")
            else "/auth/csrf"
        )
        csrf = request("GET", csrfpath)
        headers[csrf["headerName"]] = csrf["token"]
    req = urllib.request.Request(
        ORIGIN + "/api/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with client.open(req, timeout=30) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, data = error.code, error.read()
    assert status == expected, (method, path, status, data[:200])
    return json.loads(data) if data else None


def db(sql, database="reguard_member"):
    return kube(
        "exec",
        "-i",
        "deployment/postgres",
        "--",
        "psql",
        "-X",
        "-qAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        database,
        "-d",
        database,
        input=sql,
    ).strip()


def main():
    email = "k3s-" + secrets.token_hex(6) + "@example.com"
    user = None
    password = secrets.token_urlsafe(20) + "A1!"
    try:
        before = db(
            "select count(*) from products; select count(*) from recalls;",
            "reguard_safety",
        )
        code = f"{secrets.randbelow(1000000):06d}"
        digest = hashlib.sha256(f"{email}:{code}".encode()).hexdigest()
        db(
            f"INSERT INTO signup_email_verifications(email,code_hash,expires_at) VALUES ('{email}','{digest}',now()+interval '10 minutes')"
        )
        proof = request(
            "POST", "/auth/signup/email/verify", {"email": email, "code": code}
        )
        user = request(
            "POST",
            "/auth/signup",
            {
                "email": email,
                "password": password,
                "displayName": "k3s 검증",
                "verificationToken": proof["verificationToken"],
            },
            201,
        )
        request("POST", "/auth/login", {"email": email, "password": password})
        assert request("GET", "/me")["id"] == user["id"]
        item = request(
            "POST",
            "/me/products",
            {
                "registrationType": "MANUAL",
                "productName": "허니 슬라임",
                "identifierType": "KC_CERT_NO",
                "identifierValue": "CB065R2649-4001",
            },
            201,
        )
        request(
            "PATCH", "/me/products/" + item["id"], {"productName": "허니 슬라임 검증"}
        )
        request("PUT", "/me/profile", {"displayName": "재시작 검증", "photo": None})
        request("PUT", "/me/notification-preferences", {"enabled": True})
        recalls = request("GET", "/recalls")
        assert recalls["items"]
        print(
            "PASS gateway: signup/login, item create/update, profile, preference, real recall list",
            flush=True,
        )
        # Restart storage and application processes, keeping the same browser session cookie.
        for name in ("postgres", "member", "safety", "notification"):
            kube("delete", "pod", "-l", "app=" + name, "--wait=true", "--timeout=180s")
            kube("rollout", "status", "deployment/" + name, "--timeout=300s")
        assert request("GET", "/me")["id"] == user["id"]
        assert request("GET", "/me/profile")["displayName"] == "재시작 검증"
        assert request("GET", "/me/notification-preferences")["enabled"]
        assert (
            request("GET", "/me/products/" + item["id"])["productName"]
            == "허니 슬라임 검증"
        )
        after = db(
            "select count(*) from products; select count(*) from recalls;",
            "reguard_safety",
        )
        assert all(
            int(a) >= int(b) for a, b in zip(after.splitlines(), before.splitlines())
        )
        print(
            "PASS Pod replacement: session, profile, preference, item and catalog persist",
            flush=True,
        )
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            notifications = request("GET", "/me/notifications")["items"]
            if notifications:
                break
            time.sleep(3)
        else:
            raise AssertionError("No actual matched recall notification arrived")
        notice = notifications[0]
        request("PATCH", "/me/notifications/" + notice["id"] + "/read")
        assert request("GET", "/me/notifications/unread-count")["count"] == 0
        print(
            "PASS actual recall match → Kafka → notification → read count", flush=True
        )
        request("DELETE", "/me/products/" + item["id"], expected=204)
        assert not request("GET", "/me/products")["items"]
        request("POST", "/auth/logout", expected=204)
        request("GET", "/me", expected=401)
        print("PASS delete/reload and logout", flush=True)
    finally:
        if user:
            uid = user["id"]
            db(
                f"DELETE FROM notifications WHERE user_id='{uid}';",
                "reguard_notification",
            )
            db(
                f"DELETE FROM alert_outbox WHERE user_id='{uid}'; DELETE FROM owned_products WHERE user_id='{uid}'; DELETE FROM password_reset_tokens WHERE user_id='{uid}'; DELETE FROM access_tokens WHERE user_id='{uid}'; DELETE FROM users WHERE id='{uid}';"
            )
        db(f"DELETE FROM signup_email_verifications WHERE email='{email}';")


if __name__ == "__main__":
    main()

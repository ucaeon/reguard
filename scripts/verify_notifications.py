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


def db(sql, database="reguard_member"):
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
            database,
            "-d",
            database,
        ],
        input=sql,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def request(method, path, body=None, token=None, expected=200, port=18081):
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
        f"http://127.0.0.1:{port}/api/v1" + path,
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


topic = "reguard.alert-test." + uuid.uuid4().hex
topic_created = False
fixture_product = str(uuid.uuid4())
fixture_recall = str(uuid.uuid4())
fixture_created = False


def kafka(*args, payload=None):
    return subprocess.run(
        ["docker", "exec", "-i", "reguard-events-kafka-1", *args],
        input=payload,
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def wait_for(check, description):
    for _ in range(100):
        result = check()
        if result:
            return result
        time.sleep(0.3)
    raise AssertionError(description + " timed out")


try:
    if (
        db("SELECT count(*) FROM owned_products WHERE registration_type='CATALOG'")
        != "0"
    ):
        raise RuntimeError(
            "Use a local test database without existing catalog-owned products to avoid scanning real users"
        )
    kafka(
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--create",
        "--topic",
        topic,
        "--partitions",
        "1",
        "--replication-factor",
        "1",
    )
    topic_created = True
    safety = start("safety-service", 18082)
    db(
        f"""BEGIN;
        INSERT INTO products(id,source,source_record_id,name,category) VALUES ('{fixture_product}','TEST_NOTIFICATION','{fixture_product}','알림 테스트 제품','FOOD');
        INSERT INTO recalls(id,source,source_recall_id,product_name,reason,raw_payload) VALUES ('{fixture_recall}','TEST_NOTIFICATION','{fixture_recall}','알림 테스트 제품','원인 A','{{}}');
        INSERT INTO recall_product_matches(id,recall_id,product_id,match_method,match_status,rule_version)
        VALUES (gen_random_uuid(),'{fixture_recall}','{fixture_product}','TEST','CONFIRMED','test');
        COMMIT;""",
        "reguard_safety",
    )
    fixture_created = True
    member = start(
        "member-service",
        18081,
        {
            "SAFETY_BASE_URL": "http://127.0.0.1:18082",
            "ALERTS_ENABLED": "true",
            "ALERT_TOPIC": topic,
            "ALERT_SCAN_DELAY_MS": "1000",
            "ALERT_PUBLISH_DELAY_MS": "500",
        },
    )
    notification_env = {
        "MEMBER_BASE_URL": "http://127.0.0.1:18081",
        "ALERTS_ENABLED": "true",
        "ALERT_TOPIC": topic,
        "ALERT_GROUP": topic,
    }
    notification = start("notification-service", 18083, notification_env)
    tokens = []
    for n in range(2):
        email = f"alert-test-{uuid.uuid4().hex}@example.com"
        password = "Test-" + uuid.uuid4().hex
        user = verified_signup(
            request,
            {"email": email, "password": password, "displayName": "알림 테스트"},
            expected=201,
        )
        users.append(str(uuid.UUID(user["id"])))
        tokens.append(
            request("POST", "/auth/token", {"email": email, "password": password})[
                "accessToken"
            ]
        )
    token = tokens[0]
    request("GET", "/me/notifications", expected=401, port=18083)
    product = fixture_product
    owned = request(
        "POST",
        "/me/products",
        {"registrationType": "CATALOG", "catalogProductId": product},
        token,
        201,
    )

    def alerts():
        return request("GET", "/me/notifications", token=token, port=18083)["items"]

    items = wait_for(alerts, "Kafka notification")
    assert (
        items[0]["ownedProductId"] == owned["id"]
        and items[0]["eligibilityStatus"] == "NEEDS_CHECK"
    )
    count = request("GET", "/me/notifications/unread-count", token=token, port=18083)[
        "count"
    ]
    assert count == len(items) and count > 0
    path = "/me/notifications/" + items[0]["id"] + "/read"
    request("PATCH", path, token=tokens[1], expected=404, port=18083)
    assert (
        request("GET", "/me/notifications", token=tokens[1], port=18083)["items"] == []
    )
    once = request("PATCH", path, token=token, port=18083)
    twice = request("PATCH", path, token=token, port=18083)
    assert once["readAt"] == twice["readAt"] and once["readAt"] is not None
    assert (
        request("GET", "/me/notifications/unread-count", token=token, port=18083)[
            "count"
        ]
        == count - 1
    )
    payload = db(
        f"SELECT payload::text FROM alert_outbox WHERE owned_product_id='{owned['id']}' LIMIT 1"
    )
    before = len(alerts())
    kafka(
        "/opt/kafka/bin/kafka-console-producer.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--topic",
        topic,
        payload=payload + "\n" + payload + "\n" + "invalid-json\n",
    )
    wait_for(
        lambda: db(
            f"SELECT count(*) FROM rejected_notification_events WHERE topic='{topic}'",
            "reguard_notification",
        )
        == "1",
        "quarantine",
    )
    assert len(alerts()) == before, "duplicate event created extra notification"

    db(
        f"UPDATE recalls SET reason='원인 B' WHERE id='{fixture_recall}'",
        "reguard_safety",
    )
    wait_for(
        lambda: any(x["recallVersion"] == 2 for x in alerts()),
        "revision 2 notification",
    )
    assert (
        request("GET", "/me/notifications/unread-count", token=token, port=18083)[
            "count"
        ]
        == 1
    )
    db(
        f"UPDATE recalls SET reason='원인 A' WHERE id='{fixture_recall}'",
        "reguard_safety",
    )
    wait_for(
        lambda: any(x["recallVersion"] == 3 for x in alerts()),
        "reverted content notification",
    )
    db(
        f"UPDATE recalls SET reason='원인 A' WHERE id='{fixture_recall}'",
        "reguard_safety",
    )
    assert (
        db(
            f"SELECT revision FROM recalls WHERE id='{fixture_recall}'",
            "reguard_safety",
        )
        == "3"
    )
    assert len(alerts()) == 3
    request("DELETE", "/me/products/" + owned["id"], token=token, expected=204)
    wait_for(lambda: not alerts(), "notification deletion")
    kafka(
        "/opt/kafka/bin/kafka-console-producer.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--topic",
        topic,
        payload=payload + "\ninvalid-json-after-delete\n",
    )
    wait_for(
        lambda: db(
            f"SELECT count(*) FROM rejected_notification_events WHERE topic='{topic}'",
            "reguard_notification",
        )
        == "2",
        "late-event processing",
    )
    assert not alerts(), "deleted notification resurrected"

    notification.terminate()
    notification.wait(timeout=15)
    second = request(
        "POST",
        "/me/products",
        {"registrationType": "CATALOG", "catalogProductId": product},
        token,
        201,
    )
    wait_for(
        lambda: db(
            f"SELECT count(*) FROM alert_outbox WHERE owned_product_id='{second['id']}' AND sent_at IS NOT NULL"
        )
        != "0",
        "outbox delivery",
    )
    notification = start("notification-service", 18083, notification_env)
    wait_for(
        lambda: any(x["ownedProductId"] == second["id"] for x in alerts()),
        "consumer catch-up",
    )
    request("POST", "/auth/logout", token=token, expected=204)
    request("GET", "/me/notifications", token=token, expected=401, port=18083)
    member.terminate()
    member.wait(timeout=15)
    request("GET", "/me/notifications", token=tokens[1], expected=503, port=18083)
    print(
        "PASS: Member → outbox → Kafka → Notification; ownership, unread/read idempotency, duplicate events, malformed quarantine, consumer restart, revision re-alerts, deletion/late replay, logout, auth outage"
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
            f"BEGIN; DELETE FROM notifications WHERE user_id IN ({ids}); DELETE FROM deleted_owned_products WHERE user_id IN ({ids}); DELETE FROM rejected_notification_events WHERE topic='{topic}'; COMMIT;",
            "reguard_notification",
        )
        db(
            f"BEGIN; DELETE FROM alert_outbox WHERE user_id IN ({ids}); DELETE FROM access_tokens WHERE user_id IN ({ids}); DELETE FROM owned_products WHERE user_id IN ({ids}); DELETE FROM users WHERE id IN ({ids}); COMMIT;"
        )
    if fixture_created:
        db(
            f"BEGIN; DELETE FROM recall_product_matches WHERE recall_id='{fixture_recall}'; DELETE FROM recalls WHERE id='{fixture_recall}'; DELETE FROM products WHERE id='{fixture_product}'; COMMIT;",
            "reguard_safety",
        )
    if topic_created:
        kafka(
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--delete",
            "--topic",
            topic,
        )
    print("Temporary accounts, notification records and Kafka test topic removed.")

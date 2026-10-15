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
schema = "manual_test_" + uuid.uuid4().hex
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
        input="SET search_path TO " + schema + "; " + sql,
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
        env={
            **env,
            "SERVER_PORT": str(port),
            "SPRING_DATASOURCE_URL": "jdbc:postgresql://127.0.0.1:15432/reguard_"
            + service.split("-")[0]
            + "?currentSchema="
            + schema,
            "SPRING_FLYWAY_DEFAULT_SCHEMA": schema,
            **(extra or {}),
        },
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
    for database in ("reguard_member", "reguard_safety", "reguard_notification"):
        db("CREATE SCHEMA " + schema, database)
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
        INSERT INTO recalls(id,source,source_recall_id,product_name,reason,raw_payload) VALUES ('{fixture_recall}','FOOD_I0490','{fixture_recall}','알림 테스트 제품','원인 A','{{"PRDLST_REPORT_NO":"999888777"}}');
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
            execute=db,
            expected=201,
        )
        users.append(str(uuid.UUID(user["id"])))
        tokens.append(
            request("POST", "/auth/token", {"email": email, "password": password})[
                "accessToken"
            ]
        )
    token = tokens[0]
    boundary = "reguard-test-boundary"
    upload = (
        "--"
        + boundary
        + '\r\nContent-Disposition: form-data; name="image"; filename="fake.png"\r\nContent-Type: image/png\r\n\r\nnot-a-photo\r\n--'
        + boundary
        + "--\r\n"
    ).encode()
    for headers, expected in [({}, 403), ({"Authorization": "Bearer " + token}, 400)]:
        req = urllib.request.Request(
            "http://127.0.0.1:18081/api/v1/me/products/extract-label",
            data=upload,
            headers={
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                **headers,
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("invalid photo accepted")
        except urllib.error.HTTPError as error:
            assert error.code == expected
    candidate_recall = str(uuid.uuid4())
    db(
        f"INSERT INTO recalls(id,source,source_recall_id,product_name,company_name,raw_payload) VALUES ('{candidate_recall}','SAFETY_RECALL','{candidate_recall}','완구','테스트업체','{{\"certNum\":\"TEST-123\",\"recallModelName\":\"슬라임 X\"}}')",
        "reguard_safety",
    )

    def match(body):
        return request("POST", "/recalls/match", body, port=18082)["items"]

    assert match({"productName": "완구"}) == []
    assert (
        match(
            {"productName": "완구", "companyName": "다른업체", "modelName": "슬라임 X"}
        )
        == []
    )
    assert match({"productName": "완구", "companyName": "테스트업체"}) == []
    candidates = match(
        {"productName": "완구", "companyName": "테스트업체", "modelName": "슬라임 X"}
    )
    assert len(candidates) == 1 and candidates[0]["matchStatus"] == "CANDIDATE"
    candidates = match(
        {
            "productName": "입력 제품",
            "identifierType": "KC_CERT_NO",
            "identifierValue": "test-123",
        }
    )
    assert len(candidates) == 1 and candidates[0]["eligibilityStatus"] == "NEEDS_CHECK"
    assert (
        match(
            {
                "productName": "완구",
                "companyName": "테스트업체",
                "modelName": "슬라임 X",
                "identifierType": "KC_CERT_NO",
                "identifierValue": "TEST-999",
            }
        )
        == []
    )
    request("GET", "/me/notifications", expected=401, port=18083)
    product = fixture_product
    owned = request(
        "POST",
        "/me/products",
        {
            "registrationType": "MANUAL",
            "productName": "직접 입력 제품",
            "identifierType": "FOOD_REPORT_NO",
            "identifierValue": "999888777",
        },
        token,
        201,
    )

    matched = request("GET", "/me/products/" + owned["id"] + "/recalls", token=token)
    assert matched["lookupStatus"] == "LOOKUP_COMPLETE"
    assert matched["items"][0]["matchStatus"] == "CONFIRMED"
    assert matched["items"][0]["recall"]["id"] == fixture_recall
    mismatch = request(
        "POST",
        "/recalls/match",
        {
            "productName": "알림 테스트 제품",
            "companyName": "업체",
            "identifierType": "FOOD_REPORT_NO",
            "identifierValue": "111222",
        },
        port=18082,
    )
    assert mismatch["items"] == []

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
    new_recall = str(uuid.uuid4())
    db(
        f"INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload) VALUES ('{new_recall}','FOOD_I0490','{new_recall}','신규 회수','{{\"PRDLST_REPORT_NO\":\"999888777\"}}')",
        "reguard_safety",
    )
    wait_for(
        lambda: any(x["recallId"] == new_recall for x in alerts()),
        "new recall after registration",
    )
    before_edit = len(alerts())
    request(
        "PATCH", "/me/products/" + owned["id"], {"identifierValue": "111222"}, token
    )
    db(
        f"UPDATE recalls SET reason='등록정보 변경 후 리콜 수정' WHERE id='{new_recall}'",
        "reguard_safety",
    )
    time.sleep(2)
    assert len(alerts()) == before_edit
    assert (
        request("GET", "/me/products/" + owned["id"] + "/recalls", token=token)["items"]
        == []
    )
    request(
        "PATCH", "/me/products/" + owned["id"], {"identifierValue": "999888777"}, token
    )
    wait_for(
        lambda: any(
            x["recallId"] == new_recall and x["recallVersion"] == 2 for x in alerts()
        ),
        "edited manual identity rematching",
    )
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
        "PASS: manual existing/new/revised recalls, conservative KC candidates, identity edits, catalog regression; Member → outbox → Kafka → Notification; ownership, unread/read idempotency, duplicate events, malformed quarantine, consumer restart, revision re-alerts, deletion/late replay, logout, auth outage"
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
    for database in ("reguard_member", "reguard_safety", "reguard_notification"):
        db("DROP SCHEMA IF EXISTS " + schema + " CASCADE", database)
    if topic_created:
        kafka(
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--delete",
            "--topic",
            topic,
        )
    print("Isolated test schemas and Kafka test topic removed.")

from pathlib import Path
import json, os, subprocess, time, urllib.request, urllib.parse, urllib.error, socket
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
port = 18082
with socket.socket() as s:
    s.bind(("127.0.0.1", port))
env = {
    **os.environ,
    **{k: v for k, v in dotenv_values(root / ".env").items() if v is not None},
    "SERVER_PORT": str(port),
}
java = (
    str(Path(os.environ["JAVA_HOME"]) / "bin/java")
    if os.environ.get("JAVA_HOME")
    else "java"
)


def request(params):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/v1/products?" + urllib.parse.urlencode(params),
        timeout=60,
    ) as r:
        return json.load(r)


with open("/tmp/reguard-search-smoke.log", "w") as log:
    p = subprocess.Popen(
        [
            java,
            "-jar",
            str(
                root
                / "services/safety-service/target/safety-service-0.0.1-SNAPSHOT.jar"
            ),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            if p.poll() is not None:
                raise RuntimeError("service failed; see smoke log")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/actuator/health/readiness", timeout=2
                ) as r:
                    if json.load(r)["status"] == "UP":
                        break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("readiness timeout")
        first = request({"q": "비타민", "size": 2})
        assert len(first["items"]) == 2 and first["hasNext"]
        assert all("imageUrl" in x and x["identifiers"] for x in first["items"])
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/products/" + first["items"][0]["id"],
            timeout=10,
        ) as response:
            assert json.load(response) == first["items"][0]
        for product_id, status, code in [
            ("00000000-0000-0000-0000-000000000000", 404, "PRODUCT_NOT_FOUND"),
            ("not-a-uuid", 400, "INVALID_REQUEST"),
        ]:
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/products/" + product_id, timeout=10
                )
            except urllib.error.HTTPError as e:
                assert e.code == status and json.load(e)["code"] == code
            else:
                raise AssertionError("invalid detail request accepted")
        second = request({"q": "비타민", "size": 2, "page": 1})
        assert not (
            {x["id"] for x in first["items"]} & {x["id"] for x in second["items"]}
        )
        filtered = request({"q": "비타민", "category": "HEALTH_SUPPLEMENT", "size": 2})
        assert filtered["items"] and all(
            x["category"] == "HEALTH_SUPPLEMENT" for x in filtered["items"]
        )
        identifier = first["items"][0]["identifiers"][0]["value"]
        found = request({"q": identifier, "size": 100})
        assert first["items"][0]["id"] in [x["id"] for x in found["items"]]
        empty = request({"q": "REGUARD_NO_MATCH_6f09ac"})
        assert empty["items"] == [] and not empty["hasNext"]
        try:
            request({"q": "비타민", "size": 101})
        except urllib.error.HTTPError as e:
            assert e.code == 400 and json.load(e)["code"] == "INVALID_REQUEST"
        else:
            raise AssertionError("invalid request accepted")

        def read_path(path):
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/" + path, timeout=30
            ) as response:
                return json.load(response)

        recalls = read_path("recalls?size=2")
        assert len(recalls["items"]) == 2 and recalls["hasNext"]
        detail = read_path("recalls/" + recalls["items"][0]["id"])
        assert detail == recalls["items"][0] and "rawPayload" not in detail
        next_recalls = read_path("recalls?size=2&page=1")
        assert not (
            {x["id"] for x in recalls["items"]}
            & {x["id"] for x in next_recalls["items"]}
        )
        product_recalls = read_path("products/" + first["items"][0]["id"] + "/recalls")
        assert "items" in product_recalls
        for path, status in [
            ("recalls/00000000-0000-0000-0000-000000000000", 404),
            ("products/00000000-0000-0000-0000-000000000000/recalls", 404),
            ("recalls/not-a-uuid", 400),
            ("recalls?size=101", 400),
        ]:
            try:
                read_path(path)
            except urllib.error.HTTPError as e:
                assert e.code == status
            else:
                raise AssertionError("invalid recall request accepted")
        matched = subprocess.run(
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
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if matched:
            linked = read_path("products/" + matched + "/recalls")["items"]
            assert linked and all(
                x["eligibilityStatus"] == "NEEDS_CHECK" for x in linked
            )
            assert all(x["matchStatus"] in ("CONFIRMED", "CANDIDATE") for x in linked)
        print(
            "PASS: recall list/detail/product recalls, matching response, pagination and errors"
        )
        print(
            "PASS: real PostgreSQL detail, missing/malformed IDs, search, identifiers, pagination, category, no results, validation"
        )
    finally:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()

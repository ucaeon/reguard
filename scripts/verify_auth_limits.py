import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from dotenv import dotenv_values
import psycopg

root = Path(__file__).resolve().parents[1]
env = {**dotenv_values(root / ".env"), **os.environ}
schema = "auth_limit_test_" + uuid.uuid4().hex
port = 18181
config = dict(
    host=env.get("DB_HOST", "127.0.0.1"),
    port=env.get("DB_PORT", "15432"),
    dbname="reguard_member",
    user="reguard_member",
    password=env["MEMBER_DB_PASSWORD"],
)
process = None


def sql(statement, values=()):
    with psycopg.connect(**config, options="-c search_path=" + schema) as connection:
        return (
            connection.execute(statement, values).fetchall()
            if statement.startswith("SELECT")
            else connection.execute(statement, values)
        )


def post(email, path="token", password="wrong-password"):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/v1/auth/csrf"
    ) as response:
        csrf = json.load(response)
        cookie = "; ".join(
            v.split(";", 1)[0] for v in response.headers.get_all("Set-Cookie", [])
        )
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/auth/" + path,
        data=json.dumps({"email": email, "password": password}).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
            csrf["headerName"]: csrf["token"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


try:
    with psycopg.connect(**config) as connection:
        connection.execute("CREATE SCHEMA " + schema)
    with open("/tmp/reguard-auth-limit-test.log", "w") as log:
        java = (
            str(Path(env["JAVA_HOME"]) / "bin/java") if env.get("JAVA_HOME") else "java"
        )
        runtime = {
            **env,
            "SERVER_PORT": str(port),
            "ALERTS_ENABLED": "false",
            "MAIL_ENABLED": "false",
            "SPRING_FLYWAY_DEFAULT_SCHEMA": schema,
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://{config['host']}:{config['port']}/reguard_member?currentSchema={schema}",
        }
        process = subprocess.Popen(
            [
                java,
                "-jar",
                str(
                    root
                    / "services/member-service/target/member-service-0.0.1-SNAPSHOT.jar"
                ),
            ],
            env=runtime,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Test server exited")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/actuator/health/readiness", timeout=1
                ):
                    break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("Readiness timeout")
        email = "limit@example.com"
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            statuses = list(pool.map(lambda _: post(email), range(12)))
        assert statuses.count(401) == 10 and statuses.count(429) == 2, statuses
        assert post(email.upper(), "login") == 429
        assert post("other@example.com") == 401
        key = hashlib.sha256(("login-account:" + email).encode()).hexdigest()
        assert (
            sql(
                "SELECT attempts FROM auth_request_limits WHERE bucket_hash=%s", (key,)
            )[0][0]
            == 10
        )
        sql(
            "UPDATE auth_request_limits SET expires_at=now()-interval '1 second' WHERE bucket_hash=%s",
            (key,),
        )
        assert post(email) == 401
        # Account changes cannot bypass the shared IP budget.
        ipkey = hashlib.sha256(b"auth-ip:127.0.0.1").hexdigest()
        sql("UPDATE auth_request_limits SET attempts=60 WHERE bucket_hash=%s", (ipkey,))
        assert post("third@example.com") == 429
        sql(
            "UPDATE auth_request_limits SET expires_at=now()-interval '1 second' WHERE bucket_hash=%s",
            (ipkey,),
        )
        assert post("third@example.com") == 401
        print(
            "PASS: concurrent account limits, failure persistence, normalized identity, both login routes, independent accounts, IP limits, expiry recovery"
        )
finally:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    with psycopg.connect(**config) as connection:
        connection.execute("DROP SCHEMA IF EXISTS " + schema + " CASCADE")

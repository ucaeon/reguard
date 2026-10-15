"""Boot built service images against disposable schemas without exposing ports."""

import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
env = {**dotenv_values(root / ".env"), **os.environ}
schema = "image_test_" + uuid.uuid4().hex
containers = []
databases = []


def db(service, statement):
    name = "reguard_" + service
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "reguard-local-postgres-1",
            "psql",
            "-Xq",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            name,
            "-d",
            name,
        ],
        input=statement,
        text=True,
        capture_output=True,
        check=True,
    )


try:
    for service, port in [("member", 8081), ("safety", 8082), ("notification", 8083)]:
        db(service, "CREATE SCHEMA " + schema)
        databases.append(service)
        name = "reguard-image-test-" + service + "-" + uuid.uuid4().hex[:8]
        settings = {
            "SERVER_ADDRESS": "0.0.0.0",
            "SERVER_PORT": str(port),
            "DB_HOST": "postgres",
            "DB_PORT": "5432",
            service.upper() + "_DB_PASSWORD": env[service.upper() + "_DB_PASSWORD"],
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://postgres:5432/reguard_{service}?currentSchema={schema}",
            "SPRING_FLYWAY_DEFAULT_SCHEMA": schema,
            "ALERTS_ENABLED": "false",
            "MAIL_ENABLED": "false",
            "SPRING_KAFKA_LISTENER_AUTO_STARTUP": "false",
        }
        # Pass secrets by inherited environment rather than putting values in CLI arguments.
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "reguard-local_default",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "768m",
            "--health-interval",
            "2s",
        ]
        for key in settings:
            command += ["-e", key]
        command += ["reguard-" + service + ":validation"]
        containers.append(name)
        subprocess.run(
            command, env={**os.environ, **settings}, capture_output=True, check=True
        )
        for _ in range(80):
            info = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
            if info["State"]["Health"]["Status"] == "healthy":
                break
            if not info["State"]["Running"]:
                raise RuntimeError(service + " exited")
            time.sleep(1)
        else:
            raise RuntimeError(service + " readiness timed out")
        assert info["Config"]["User"] == "10001:10001"
        assert not info["HostConfig"]["PortBindings"]
        print(
            "PASS:",
            service,
            "image, non-root/read-only startup, migrations, DB readiness, no exposed host port",
        )
finally:
    for name in containers:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    for service in databases:
        db(service, "DROP SCHEMA IF EXISTS " + schema + " CASCADE")

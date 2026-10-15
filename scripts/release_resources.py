"""Portable single-node manifests. No workstation or Docker-container discovery."""

import base64
import json
import re
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit
from k3s_resources import deployment

CLAIMS = {
    "postgres": "12Gi",
    "metadata": "4Gi",
    "kafka": "8Gi",
    "airflow-data": "8Gi",
    "airflow-state": "1Gi",
    "airflow-logs": "2Gi",
    "spark-checkpoints": "2Gi",
    "caddy-data": "1Gi",
    "caddy-config": "1Gi",
    "database-backups": "8Gi",
}
WORKLOADS = [
    "postgres",
    "metadata",
    "kafka",
    "member",
    "safety",
    "notification",
    "api-server",
    "dag-processor",
    "scheduler",
    "spark",
    "web",
]
PASSWORDS = [
    "POSTGRES_PASSWORD",
    "MEMBER_DB_PASSWORD",
    "SAFETY_DB_PASSWORD",
    "NOTIFICATION_DB_PASSWORD",
    "AIRFLOW_DB_PASSWORD",
    "AIRFLOW_JWT_SECRET",
]


def new_secrets():
    return {
        **{k: secrets.token_urlsafe(32) for k in PASSWORDS},
        "AIRFLOW_FERNET_KEY": base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode(),
        "FOOD_SAFETY_API_KEY": "",
        "SAFETY_KOREA_API_KEY": "",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
    }


def validate(config, credentials):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", config["namespace"]):
        raise ValueError("Invalid namespace")
    origin = urlsplit(config["origin"])
    if (
        origin.path
        or origin.query
        or origin.fragment
        or origin.username
        or not origin.hostname
    ):
        raise ValueError("origin must contain only scheme and host")
    if config["mode"] == "local-test":
        if origin.scheme != "http" or origin.hostname not in ("127.0.0.1", "localhost"):
            raise ValueError("local-test requires a loopback HTTP origin")
    elif config["mode"] == "production":
        if (
            origin.scheme != "https"
            or origin.port
            or origin.hostname in ("localhost", "127.0.0.1")
        ):
            raise ValueError("production requires an HTTPS domain on port 443")
        for key in (
            "FOOD_SAFETY_API_KEY",
            "SAFETY_KOREA_API_KEY",
            "SMTP_USERNAME",
            "SMTP_PASSWORD",
        ):
            if not credentials.get(key):
                raise ValueError("Missing production credential: " + key)
        if not config.get("smtp_host") or not config.get("mail_from"):
            raise ValueError("Production mail settings are required")
    else:
        raise ValueError("mode must be production or local-test")
    for key in PASSWORDS + ["AIRFLOW_FERNET_KEY"]:
        if len(credentials.get(key, "")) < 32:
            raise ValueError("Missing or short secret: " + key)
    if len(base64.urlsafe_b64decode(credentials["AIRFLOW_FERNET_KEY"])) != 32:
        raise ValueError("Invalid Fernet key")


def resources(config, credentials, images):
    validate(config, credentials)
    namespace = config["namespace"]
    objects = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}
    ]

    def add(kind, name, **fields):
        version = {
            "Deployment": "apps/v1",
            "Job": "batch/v1",
            "CronJob": "batch/v1",
        }.get(kind, "v1")
        obj = {
            "apiVersion": version,
            "kind": kind,
            "metadata": {"name": name, "namespace": namespace},
            **fields,
        }
        objects.append(obj)
        return obj

    storage_class = config.get(
        "storage_class",
        "reguard-retained" if config["mode"] == "production" else "local-path",
    )
    if storage_class == "reguard-retained":
        objects.append(
            {
                "apiVersion": "storage.k8s.io/v1",
                "kind": "StorageClass",
                "metadata": {"name": storage_class},
                "provisioner": "rancher.io/local-path",
                "reclaimPolicy": "Retain",
                "volumeBindingMode": "WaitForFirstConsumer",
            }
        )
    for claim, size in CLAIMS.items():
        add(
            "PersistentVolumeClaim",
            claim,
            spec={
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": storage_class,
                "resources": {"requests": {"storage": size}},
            },
        )
    for name, port in [
        ("postgres", 5432),
        ("metadata", 5432),
        ("kafka", 9092),
        ("api-server", 8080),
        ("member", 8081),
        ("safety", 8082),
        ("notification", 8083),
        ("web", 8080),
    ]:
        spec = {
            "selector": {"app": name},
            "ports": [{"port": port, "targetPort": port}],
        }
        if name == "web" and config["mode"] == "local-test":
            spec.update(type="NodePort")
            spec["ports"][0]["nodePort"] = 30080
        elif name == "web":
            spec["ports"] = [
                {"name": "http", "port": 80, "targetPort": 80},
                {"name": "https", "port": 443, "targetPort": 443},
            ]
        add("Service", name, spec=spec)

    def deploy(
        name,
        image,
        env,
        storage=(),
        limit=("1000m", "768Mi"),
        probe=None,
        args=None,
        secure=False,
        uid=None,
    ):
        mounts = [{"name": claim, "mountPath": path} for claim, path in storage]
        volumes = [
            {"name": claim, "persistentVolumeClaim": {"claimName": claim}}
            for claim, path in storage
        ]
        if secure:
            mounts.append({"name": "tmp", "mountPath": "/tmp"})
            volumes.append({"name": "tmp", "emptyDir": {}})
        deployment(
            name, images[image], env, mounts, volumes, limit, probe, args, add, secure
        )
        pod = objects[-1]["spec"]["template"]["spec"]
        pod["containers"][0]["imagePullPolicy"] = "Never"
        for init in pod.get("initContainers", []):
            init["image"] = images["postgres"]
            init["imagePullPolicy"] = "Never"
        if uid is not None:
            pod["securityContext"] = {
                "fsGroup": uid,
                "fsGroupChangePolicy": "OnRootMismatch",
            }
            pod.setdefault("initContainers", []).append(
                {
                    "name": "volume-permissions",
                    "image": images["postgres"],
                    "imagePullPolicy": "Never",
                    "command": [
                        "sh",
                        "-ec",
                        "; ".join(
                            "chown " + str(uid) + ":0 " + path for _, path in storage
                        ),
                    ],
                    "securityContext": {"runAsUser": 0},
                    "volumeMounts": mounts,
                    "resources": {
                        "requests": {"cpu": "10m", "memory": "16Mi"},
                        "limits": {"cpu": "100m", "memory": "64Mi"},
                    },
                }
            )
        return pod

    pg = {k: credentials[k] for k in PASSWORDS[:4]}
    pg.update(
        POSTGRES_USER="reguard_admin",
        POSTGRES_DB="postgres",
        PGDATA="/var/lib/postgresql/data/pgdata",
    )
    deploy(
        "postgres",
        "postgres",
        pg,
        [("postgres", "/var/lib/postgresql/data")],
        ("1500m", "768Mi"),
        {"exec": {"command": ["pg_isready", "-U", "reguard_admin", "-d", "postgres"]}},
    )
    # The metadata database uses the upstream image without application initialization scripts.
    deploy(
        "metadata",
        "metadata",
        {
            "POSTGRES_USER": "airflow",
            "POSTGRES_DB": "airflow",
            "POSTGRES_PASSWORD": credentials["AIRFLOW_DB_PASSWORD"],
            "PGDATA": "/var/lib/postgresql/data/pgdata",
        },
        [("metadata", "/var/lib/postgresql/data")],
        ("500m", "384Mi"),
        {"exec": {"command": ["pg_isready", "-U", "airflow"]}},
    )
    kafka = {
        "KAFKA_NODE_ID": "1",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        "KAFKA_LISTENERS": "INTERNAL://:9092,CONTROLLER://:9093",
        "KAFKA_ADVERTISED_LISTENERS": "INTERNAL://kafka:9092",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT",
        "KAFKA_INTER_BROKER_LISTENER_NAME": "INTERNAL",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@127.0.0.1:9093",
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR": "1",
        "KAFKA_AUTO_CREATE_TOPICS_ENABLE": "false",
        "KAFKA_LOG_DIRS": "/var/lib/kafka/data",
        "KAFKA_HEAP_OPTS": "-Xms256m -Xmx512m",
        "CLUSTER_ID": "MkU3OEVBNTcwNTJENDM2Qk",
    }
    deploy(
        "kafka",
        "kafka",
        kafka,
        [("kafka", "/var/lib/kafka/data")],
        ("1500m", "1280Mi"),
        {"tcpSocket": {"port": 9092}},
        uid=1000,
    )
    common = {
        "SERVER_ADDRESS": "0.0.0.0",
        "DB_HOST": "postgres",
        "DB_PORT": "5432",
        "COOKIE_SECURE": str(config["mode"] == "production").lower(),
        "WEB_ALLOWED_ORIGINS": config["origin"],
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "ALERTS_ENABLED": "true",
        "SAFETY_BASE_URL": "http://safety:8082",
        "MEMBER_BASE_URL": "http://member:8081",
    }
    for name, port in [("member", 8081), ("safety", 8082), ("notification", 8083)]:
        key = name.upper() + "_DB_PASSWORD"
        env = {**common, key: credentials[key], "SERVER_PORT": str(port)}
        if name == "member":
            env.update(
                MAIL_ENABLED=str(config["mode"] == "production").lower(),
                SMTP_HOST=config.get("smtp_host", ""),
                SMTP_PORT=str(config.get("smtp_port", 587)),
                SMTP_USERNAME=credentials.get("SMTP_USERNAME", ""),
                SMTP_PASSWORD=credentials.get("SMTP_PASSWORD", ""),
                MAIL_FROM=config.get("mail_from", ""),
                PASSWORD_RESET_URL=config["origin"] + "/?view=reset-password",
            )
        deploy(
            name,
            name,
            env,
            probe={"httpGet": {"path": "/actuator/health/readiness", "port": port}},
            secure=True,
        )
    airflow = {
        "AIRFLOW__CORE__EXECUTOR": "LocalExecutor",
        "AIRFLOW__CORE__LOAD_EXAMPLES": "false",
        "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION": "true",
        "AIRFLOW__CORE__PARALLELISM": "2",
        "AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG": "2",
        "AIRFLOW__CORE__DEFAULT_TIMEZONE": "Asia/Seoul",
        "AIRFLOW__CORE__AUTH_MANAGER": "airflow.api_fastapi.auth.managers.simple.simple_auth_manager.SimpleAuthManager",
        "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS": "operator:admin",
        "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE": "/opt/airflow/state/ui-passwords.json",
        "AIRFLOW__CORE__EXECUTION_API_SERVER_URL": "http://api-server:8080/execution/",
        "AIRFLOW__API__BASE_URL": "http://api-server:8080",
        "AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK": "true",
        "AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL": "30",
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "postgresql+psycopg2://airflow:"
        + quote(credentials["AIRFLOW_DB_PASSWORD"], safe="")
        + "@metadata:5432/airflow",
        "AIRFLOW__CORE__FERNET_KEY": credentials["AIRFLOW_FERNET_KEY"],
        "AIRFLOW__API_AUTH__JWT_SECRET": credentials["AIRFLOW_JWT_SECRET"],
        "REGUARD_DATA_ROOT": "/opt/reguard/data/airflow",
        "REGUARD_STATE_ROOT": "/opt/airflow/state/ingestion",
        "FOOD_SAFETY_API_KEY": credentials.get("FOOD_SAFETY_API_KEY", ""),
        "SAFETY_KOREA_API_KEY": credentials.get("SAFETY_KOREA_API_KEY", ""),
        "DB_HOST": "postgres",
        "DB_PORT": "5432",
        "SAFETY_DB_PASSWORD": credentials["SAFETY_DB_PASSWORD"],
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
    }
    storage = [
        ("airflow-data", "/opt/reguard/data/airflow"),
        ("airflow-state", "/opt/airflow/state"),
        ("airflow-logs", "/opt/airflow/logs"),
    ]
    for name in ("api-server", "dag-processor", "scheduler"):
        probe = (
            {"httpGet": {"path": "/api/v2/monitor/health", "port": 8080}}
            if name == "api-server"
            else (
                {"httpGet": {"path": "/health", "port": 8974}}
                if name == "scheduler"
                else {
                    "exec": {
                        "command": [
                            "airflow",
                            "jobs",
                            "check",
                            "--job-type",
                            "DagProcessorJob",
                            "--local",
                        ]
                    }
                }
            )
        )
        deploy(name, "airflow", airflow, storage, probe=probe, args=[name], uid=50000)
    deploy(
        "spark",
        "spark",
        {
            "DB_HOST": "postgres",
            "DB_PORT": "5432",
            "SAFETY_DB_PASSWORD": credentials["SAFETY_DB_PASSWORD"],
            "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        },
        [("spark-checkpoints", "/checkpoints")],
        ("2000m", "1536Mi"),
        {
            "exec": {
                "command": [
                    "python",
                    "-c",
                    "import socket; socket.create_connection(('127.0.0.1',4040),3).close()",
                ]
            }
        },
    )
    # Separate HTTP readiness endpoint avoids redirect/TLS dependencies in Kubernetes probes.
    web = deploy(
        "web",
        "web",
        {
            "PUBLIC_DOMAIN": (
                config["origin"] if config["mode"] == "production" else "http://:8080"
            )
        },
        [("caddy-data", "/data"), ("caddy-config", "/config")],
        ("500m", "128Mi"),
        {"httpGet": {"path": "/health", "port": 8081}},
    )
    if config["mode"] == "production":
        web["containers"][0]["ports"] = [
            {"containerPort": 80, "hostPort": 80},
            {"containerPort": 443, "hostPort": 443},
        ]
    template = Path(__file__).resolve().parent / "backup.json"
    if not template.exists():
        template = Path(__file__).resolve().parents[1] / "infra/release/backup.json"
    backup = json.loads(template.read_text())
    backup["metadata"]["namespace"] = namespace
    backup["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0][
        "image"
    ] = images["postgres"]
    objects.append(backup)
    return objects

"""Kubernetes resources for the single-node local migration."""

import hashlib
import json
from pathlib import Path


def env_of(container):
    return dict(entry.split("=", 1) for entry in container["Config"]["Env"])


def resources(source, ROOT, NAMESPACE):
    from dotenv import dotenv_values

    objects = [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}
    ]

    def add(kind, name, **fields):
        obj = {
            "apiVersion": "apps/v1" if kind == "Deployment" else "v1",
            "kind": kind,
            "metadata": {"name": name, "namespace": NAMESPACE},
            **fields,
        }
        objects.append(obj)
        return obj

    def service(name, port, nodeport=None):
        spec = {
            "selector": {"app": name},
            "ports": [{"port": port, "targetPort": port}],
        }
        if nodeport:
            spec.update(type="NodePort")
            spec["ports"][0]["nodePort"] = nodeport
        add("Service", name, spec=spec)

    for name, port in [
        ("postgres", 5432),
        ("metadata", 5432),
        ("kafka", 9092),
        ("api-server", 8080),
        ("member", 8081),
        ("safety", 8082),
        ("notification", 8083),
    ]:
        service(name, port)
    service("web", 8080, 30080)
    for name, container in source.items():
        environment = env_of(container)
        image = container["Config"]["Image"]
        mounts = []
        volumes = []
        for index, mount in enumerate(
            sorted(container["Mounts"], key=lambda mount: mount["Destination"])
        ):
            dest = mount["Destination"]
            if mount["Type"] == "volume" and mount.get("Name", "").startswith(
                "reguard-"
            ):
                claim = mount["Name"].replace("_", "-")
                if not any(
                    o["kind"] == "PersistentVolumeClaim"
                    and o["metadata"]["name"] == claim
                    for o in objects
                ):
                    objects.append(
                        {
                            "apiVersion": "v1",
                            "kind": "PersistentVolume",
                            "metadata": {"name": claim},
                            "spec": {
                                "capacity": {"storage": "20Gi"},
                                "accessModes": ["ReadWriteOnce"],
                                "persistentVolumeReclaimPolicy": "Retain",
                                "storageClassName": "",
                                "hostPath": {
                                    "path": "/persistent/" + mount["Name"],
                                    "type": "Directory",
                                },
                                "claimRef": {"namespace": NAMESPACE, "name": claim},
                            },
                        }
                    )
                    add(
                        "PersistentVolumeClaim",
                        claim,
                        spec={
                            "accessModes": ["ReadWriteOnce"],
                            "storageClassName": "",
                            "volumeName": claim,
                            "resources": {"requests": {"storage": "20Gi"}},
                        },
                    )
                volumes.append(
                    {"name": f"v{index}", "persistentVolumeClaim": {"claimName": claim}}
                )
            elif mount["Type"] == "bind":
                original = mount["Source"].removeprefix("/host_mnt")
                relative = Path(original).relative_to(ROOT)
                volumes.append(
                    {
                        "name": f"v{index}",
                        "hostPath": {
                            "path": "/workspace/" + str(relative),
                            "type": "Directory" if Path(original).is_dir() else "File",
                        },
                    }
                )
            else:
                continue
            mounts.append(
                {"name": f"v{index}", "mountPath": dest, "readOnly": not mount["RW"]}
            )
        if name in ("api-server", "scheduler", "dag-processor"):
            environment["AIRFLOW__CORE__EXECUTION_API_SERVER_URL"] = (
                "http://api-server:8080/execution/"
            )
            environment["AIRFLOW__API__BASE_URL"] = "http://api-server:8080"
        if name == "kafka":
            environment["KAFKA_ADVERTISED_LISTENERS"] = (
                "INTERNAL://kafka:9092,EXTERNAL://kafka:19092"
            )
            environment["KAFKA_CONTROLLER_QUORUM_VOTERS"] = "1@127.0.0.1:9093"
        limits = {
            "postgres": ("1500m", "768Mi"),
            "metadata": ("500m", "384Mi"),
            "kafka": ("1500m", "1280Mi"),
            "spark": ("2000m", "1536Mi"),
        }.get(name, ("1000m", "768Mi"))
        probe = None
        if name in ("postgres", "metadata"):
            probe = {
                "exec": {"command": ["pg_isready", "-U", environment["POSTGRES_USER"]]}
            }
        elif name == "api-server":
            probe = {"httpGet": {"path": "/api/v2/monitor/health", "port": 8080}}
        elif name == "scheduler":
            probe = {"httpGet": {"path": "/health", "port": 8974}}
        elif name == "kafka":
            probe = {"tcpSocket": {"port": 9092}}
        elif name == "spark":
            probe = {
                "exec": {
                    "command": [
                        "python",
                        "-c",
                        "import socket; socket.create_connection(('127.0.0.1',4040),3).close()",
                    ]
                }
            }
        elif name == "dag-processor":
            probe = {
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
        deployment(
            name,
            image,
            environment,
            mounts,
            volumes,
            limits,
            probe,
            container["Config"].get("Cmd"),
            add,
        )
    common = {
        "SERVER_ADDRESS": "0.0.0.0",
        "DB_HOST": "postgres",
        "DB_PORT": "5432",
        "COOKIE_SECURE": "false",
        "WEB_ALLOWED_ORIGINS": "http://localhost:13000,http://127.0.0.1:13000",
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "ALERTS_ENABLED": "true",
        "SAFETY_BASE_URL": "http://safety:8082",
        "MEMBER_BASE_URL": "http://member:8081",
    }
    db = env_of(source["postgres"])
    for name, port in [("member", 8081), ("safety", 8082), ("notification", 8083)]:
        key = name.upper() + "_DB_PASSWORD"
        environment = {**common, key: db[key], "SERVER_PORT": str(port)}
        if name == "member":
            local = dotenv_values(ROOT / ".env")
            environment.update(
                {
                    key: value
                    for key, value in local.items()
                    if value is not None
                    and (
                        key.startswith("SMTP_") or key in ("MAIL_ENABLED", "MAIL_FROM")
                    )
                }
            )
            environment["PASSWORD_RESET_URL"] = (
                "http://localhost:13000/?view=reset-password"
            )
        deployment(
            name,
            "reguard-" + name + ":validation",
            environment,
            [{"name": "tmp", "mountPath": "/tmp"}],
            [{"name": "tmp", "emptyDir": {}}],
            ("1000m", "768Mi"),
            {"httpGet": {"path": "/actuator/health/readiness", "port": port}},
            None,
            add,
            secure=True,
        )
    deployment(
        "web",
        "reguard-web:validation",
        {"PUBLIC_DOMAIN": "http://:8080"},
        [],
        [],
        ("500m", "128Mi"),
        {"httpGet": {"path": "/", "port": 8080}},
        None,
        add,
    )
    return objects


def deployment(
    name, image, env, mounts, volumes, limits, probe, command, add, secure=False
):
    config = {}
    secret = {}
    for key, value in env.items():
        (
            secret
            if any(
                word in key for word in ("PASSWORD", "SECRET", "KEY", "CONN", "TOKEN")
            )
            else config
        )[key] = value
    add("ConfigMap", name + "-env", data=config)
    add("Secret", name + "-env", type="Opaque", stringData=secret)
    container = {
        "name": name,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "envFrom": [
            {"configMapRef": {"name": name + "-env"}},
            {"secretRef": {"name": name + "-env"}},
        ],
        "volumeMounts": mounts,
        "resources": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": limits[0], "memory": limits[1]},
        },
    }
    if command:
        container["args"] = command
    if probe:
        container["readinessProbe"] = {
            **probe,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 6,
        }
        container["startupProbe"] = {
            **probe,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 30,
        }
        live = probe
        if secure:
            live = {
                "httpGet": {
                    "path": "/actuator/health/liveness",
                    "port": int(env["SERVER_PORT"]),
                }
            }
        container["livenessProbe"] = {
            **live,
            "periodSeconds": 30,
            "timeoutSeconds": 5,
            "failureThreshold": 6,
        }
    if probe and name == "dag-processor":
        # Airflow CLI imports are expensive under a burstable node's baseline CPU quota.
        for kind in ("readinessProbe", "startupProbe", "livenessProbe"):
            container[kind]["timeoutSeconds"] = 30
            container[kind]["periodSeconds"] = 60
    if secure:
        container["securityContext"] = {
            "runAsNonRoot": True,
            "runAsUser": 10001,
            "readOnlyRootFilesystem": True,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        }
    add(
        "Deployment",
        name,
        spec={
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {
                    "labels": {"app": name},
                    "annotations": {
                        "reguard/config-digest": hashlib.sha256(
                            json.dumps(env, sort_keys=True).encode()
                        ).hexdigest()
                    },
                },
                "spec": {
                    "automountServiceAccountToken": False,
                    "terminationGracePeriodSeconds": 120,
                    "containers": [container],
                    "volumes": volumes,
                    **(
                        {
                            "initContainers": [
                                {
                                    "name": "wait-for-database",
                                    "image": "postgres:17.11-bookworm",
                                    "command": [
                                        "sh",
                                        "-ec",
                                        "until pg_isready -h postgres -U reguard_"
                                        + name
                                        + " -d reguard_"
                                        + name
                                        + "; do sleep 2; done",
                                    ],
                                    "securityContext": {
                                        "runAsUser": 10001,
                                        "runAsNonRoot": True,
                                        "allowPrivilegeEscalation": False,
                                        "capabilities": {"drop": ["ALL"]},
                                    },
                                    "resources": {
                                        "requests": {"cpu": "10m", "memory": "16Mi"},
                                        "limits": {"cpu": "100m", "memory": "64Mi"},
                                    },
                                }
                            ]
                        }
                        if secure
                        else {}
                    ),
                },
            },
        },
    )

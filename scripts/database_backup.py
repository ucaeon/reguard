"""Store dumps in a server Docker volume; verify restores in disposable memory storage."""

import argparse
from datetime import datetime, timezone
import re
import subprocess
import time
import uuid


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, **kwargs)


def identifier(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", value):
        raise argparse.ArgumentTypeError("Invalid Docker or database identifier")
    return value


def transfer(producer, consumer):
    with subprocess.Popen(
        producer, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as source:
        with subprocess.Popen(
            consumer,
            stdin=source.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as target:
            source.stdout.close()
            _, error = target.communicate()
            source_error = source.stderr.read()
            source.wait()
            if source.returncode or target.returncode:
                raise RuntimeError(
                    "Backup transfer failed: " + (source_error + error).decode()[-1500:]
                )


def dump(args):
    return [
        "docker",
        "exec",
        args.container,
        "pg_dump",
        "-U",
        args.user,
        "-d",
        args.database,
        "-Fc",
        "--no-owner",
        "--no-acl",
    ]


def create(args):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{args.database}-{stamp}-{uuid.uuid4().hex[:8]}.dump"
    docker("volume", "create", args.volume)
    transfer(
        dump(args),
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "-v",
            args.volume + ":/backup",
            args.image,
            "sh",
            "-ec",
            'umask 077; cat > /backup/"$1".partial; pg_restore --list /backup/"$1".partial >/dev/null; mv /backup/"$1".partial /backup/"$1"',
            "sh",
            name,
        ],
    )
    args.backup = name
    verify(args)
    # Rotate only after the new dump has passed a full restore check.
    docker(
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        args.volume + ":/backup",
        args.image,
        "find",
        "/backup",
        "-name",
        args.database + "-*.dump",
        "-type",
        "f",
        "-mtime",
        "+" + str(args.keep_days),
        "-delete",
    )
    print("Created", name, "in Docker volume", args.volume)


def verify(args):
    scratch = "reguard-restore-test-" + uuid.uuid4().hex[:12]
    try:
        docker(
            "run",
            "-d",
            "--name",
            scratch,
            "--network",
            "none",
            "--tmpfs",
            "/var/lib/postgresql/data:rw,size=4g",
            "--tmpfs",
            "/tmp:rw,size=2g",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            args.image,
        )
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", scratch, "pg_isready", "-U", "postgres"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Restore target did not become ready")
        if args.backup:
            producer = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                args.volume + ":/backup:ro",
                args.image,
                "cat",
                "/backup/" + args.backup,
            ]
        else:
            producer = dump(args)
        transfer(
            producer,
            [
                "docker",
                "exec",
                "-i",
                scratch,
                "sh",
                "-ec",
                "cat > /tmp/restore.dump; pg_restore --exit-on-error --no-owner --no-acl -U postgres -d postgres /tmp/restore.dump",
            ],
        )
        # Count every restored table; this also detects unreadable relations after restoration.
        query = "SELECT format('SELECT %L AS table_name, count(*) FROM %I.%I;', schemaname||'.'||tablename,schemaname,tablename) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename;"
        commands = docker(
            "exec", scratch, "psql", "-XAt", "-U", "postgres", "-c", query
        ).stdout
        counts = docker(
            "exec",
            "-i",
            scratch,
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            input=commands,
        ).stdout.decode()
        if not counts.strip():
            raise RuntimeError("Restore contained no application tables")
        print(
            "PASS restore",
            args.database,
            "—",
            len(counts.splitlines()),
            "tables readable; constraints restored",
        )
        print(counts.strip())
    finally:
        subprocess.run(["docker", "rm", "-f", scratch], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify"])
    parser.add_argument("--container", type=identifier, required=True)
    parser.add_argument("--database", type=identifier, required=True)
    parser.add_argument("--user", type=identifier, required=True)
    parser.add_argument("--volume", type=identifier, default="reguard-backups")
    parser.add_argument("--image", default="postgres:17.11-bookworm")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument(
        "--backup", type=identifier, help="Verify an existing dump in the backup volume"
    )
    args = parser.parse_args()
    if args.keep_days < 1:
        parser.error("keep-days must be positive")
    if args.action == "create":
        create(args)
    else:
        verify(args)


if __name__ == "__main__":
    main()

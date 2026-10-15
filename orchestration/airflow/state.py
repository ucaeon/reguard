"""Durable state, file locking and database connections."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import psycopg
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def root():
    folder = Path(os.environ.get("REGUARD_DATA_ROOT", "/opt/reguard/data/airflow"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


@contextmanager
def lock(name):
    path = root() / "locks" / (hashlib.sha256(name.encode()).hexdigest() + ".lock")
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def state_db():
    folder = Path(os.environ.get("REGUARD_STATE_ROOT", str(root())))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "state.sqlite"
    legacy = root() / "state.sqlite"
    with (folder / "migration.lock").open("a") as migration_lock:
        fcntl.flock(migration_lock, fcntl.LOCK_EX)
        if not path.exists() and legacy.exists() and path.resolve() != legacy.resolve():
            temporary = folder / "state.migration.sqlite"
            source = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
            target = sqlite3.connect(temporary)
            try:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("STATE_MIGRATION_INTEGRITY_FAILED")
            finally:
                target.close()
                source.close()
            temporary.replace(path)
    connection = sqlite3.connect(path, timeout=30)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS requests(provider TEXT,service TEXT,at REAL,incremental INTEGER)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS request_time ON requests(at)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS watermarks(source TEXT PRIMARY KEY,day TEXT,completed_at TEXT)"
        )
        with connection:
            yield connection
    finally:
        connection.close()


def database():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "postgres"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname="reguard_safety",
        user="reguard_safety",
        password=os.environ["SAFETY_DB_PASSWORD"],
        connect_timeout=10,
        options="-c statement_timeout=30000",
    )

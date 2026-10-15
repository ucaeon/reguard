"""Snapshot pipeline recovery files on the server after ingestion has been stopped."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import uuid


def stopped(containers):
    for container in containers:
        state = subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            text=True,
        ).strip()
        if state != "false":
            raise RuntimeError(
                "Stop ingestion and Spark before snapshotting: " + container
            )


def snapshot(state, checkpoints, cache, destination):
    sources = [
        Path(state).resolve(),
        Path(checkpoints).resolve(),
        Path(cache).resolve(),
    ]
    destination = Path(destination).resolve()
    if any(
        destination == source or source in destination.parents for source in sources
    ):
        raise ValueError("Backup destination must be outside the source paths")
    if not sources[0].is_file() or not all(p.is_dir() for p in sources[1:]):
        raise ValueError("All recovery sources must exist")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination, prefix=".partial-") as temporary:
        folder = Path(temporary)
        with closing(sqlite3.connect(f"file:{sources[0]}?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(folder / "state.sqlite")) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Invalid state snapshot")
        for name, path in [("checkpoints", sources[1]), ("cache", sources[2])]:
            if any(p.is_symlink() for p in path.rglob("*")):
                raise ValueError("Recovery sources must not contain symlinks")
            shutil.copytree(path, folder / name)
        manifest = {}
        for path in folder.rglob("*"):
            if path.is_file():
                with path.open("rb") as source:
                    manifest[str(path.relative_to(folder))] = hashlib.file_digest(
                        source, "sha256"
                    ).hexdigest()
        (folder / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        verify(folder)
        result = destination / ("pipeline-" + uuid.uuid4().hex)
        folder.rename(result)
        return result


def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    actual = {
        str(p.relative_to(folder))
        for p in folder.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if set(manifest) != actual:
        raise RuntimeError("Snapshot file inventory differs")
    for name, digest in manifest.items():
        path = folder / name
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise RuntimeError("Unsafe snapshot path")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise RuntimeError("Snapshot checksum mismatch: " + name)
    with closing(
        sqlite3.connect(f"file:{folder/'state.sqlite'}?mode=ro&immutable=1", uri=True)
    ) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Invalid SQLite snapshot")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    for option in ["state-db", "checkpoints", "cache", "destination"]:
        create.add_argument("--" + option, required=True)
    create.add_argument(
        "--stopped-container",
        action="append",
        required=True,
        help="Supply each ingestion writer and Spark container; all must be stopped",
    )
    check = sub.add_parser("verify")
    check.add_argument("folder")
    args = parser.parse_args()
    if args.action == "create":
        stopped(args.stopped_container)
        print(snapshot(args.state_db, args.checkpoints, args.cache, args.destination))
    else:
        verify(args.folder)
        print("PASS: snapshot checksums and SQLite integrity")


if __name__ == "__main__":
    main()

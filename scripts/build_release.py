"""Build an immutable, offline-importable release from this source tree."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,63}", args.version):
        parser.error("Use an immutable lowercase release identifier")
    args.output.mkdir(parents=True, exist_ok=False)
    bases = json.loads((ROOT / "infra/release/bases.json").read_text())
    images = {}
    for name in (
        "member",
        "safety",
        "notification",
        "web",
        "airflow",
        "spark",
        "postgres",
        "metadata",
        "kafka",
    ):
        tag = "reguard-" + name + ":" + args.version
        if (
            subprocess.run(
                ["docker", "image", "inspect", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        ):
            raise SystemExit("Refusing to overwrite image tag: " + tag)
        if name in ("metadata", "kafka"):
            source = bases["POSTGRES" if name == "metadata" else "KAFKA"]
            subprocess.run(
                ["docker", "pull", "--platform", "linux/arm64", source], check=True
            )
            subprocess.run(["docker", "tag", source, tag], check=True)
        else:
            file = (
                "infra/runtime/Service.Dockerfile"
                if name in ("member", "safety", "notification")
                else (
                    "infra/runtime/Web.Dockerfile"
                    if name == "web"
                    else "infra/release/" + name.capitalize() + ".Dockerfile"
                )
            )
            cmd = [
                "docker",
                "build",
                "--platform",
                "linux/arm64",
                "-f",
                str(ROOT / file),
                "-t",
                tag,
            ]
            for key, value in bases.items():
                cmd += ["--build-arg", key + "=" + value]
            if name in ("member", "safety", "notification"):
                cmd += ["--build-arg", "SERVICE=" + name + "-service"]
            subprocess.run(cmd + [str(ROOT)], check=True)
        info = json.loads(run("docker", "image", "inspect", tag))[0]
        if info["Architecture"] != "arm64":
            raise SystemExit("Unexpected image architecture")
        archive = args.output / (name + ".tar")
        subprocess.run(["docker", "image", "save", "-o", str(archive), tag], check=True)
        images[name] = {
            "tag": tag,
            "id": info["Id"],
            "archive": archive.name,
            "sha256": checksum(archive),
        }
        print("Packaged " + name, flush=True)
    helpers = {}
    for name in (
        "release_install.py",
        "release_resources.py",
        "release_recovery.py",
        "k3s_resources.py",
    ):
        shutil.copyfile(ROOT / "scripts" / name, args.output / name)
        helpers[name] = checksum(args.output / name)
    for name in ("bootstrap.sh", "config.example.json", "backup.json"):
        shutil.copyfile(ROOT / "infra/release" / name, args.output / name)
        helpers[name] = checksum(args.output / name)
    lock = {
        "version": args.version,
        "platform": "linux/arm64",
        "k3s": "v1.35.5-k3s1",
        "bases": bases,
        "images": images,
        "files": helpers,
    }
    (args.output / "release.json").write_text(json.dumps(lock, indent=2) + "\n")
    print("Release ready: " + str(args.output))


if __name__ == "__main__":
    main()

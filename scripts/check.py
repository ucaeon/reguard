"""Run repeatable checks without contacting providers or modifying live databases."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SUITES = (
    "pipelines/collectors/tests",
    "pipelines/spark/tests",
    "pipelines/bootstrap/tests",
    "orchestration/airflow/tests",
    "scripts",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "python", "java", "web"), default="all")
    args = parser.parse_args()
    commands = []
    if args.suite in {"all", "python"}:
        commands.extend((ROOT, [sys.executable, "-m", "unittest", "discover", "-s", suite, "-v"])
                        for suite in PYTHON_SUITES)
    if args.suite in {"all", "java"}:
        commands.append((ROOT, ["./mvnw", "-B", "-ntp", "test"]))
    if args.suite in {"all", "web"}:
        commands.extend((ROOT / "web", ["npm", "run", script])
                        for script in ("test", "test:ui", "build"))
    for directory, command in commands:
        print(f"CHECK {directory.relative_to(ROOT)}: {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=directory, check=True)
    print("All selected checks passed. Live API, database and recovery checks are separate.")


if __name__ == "__main__":
    main()

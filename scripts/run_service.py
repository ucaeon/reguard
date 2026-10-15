"""Load dotenv as data, preserving explicit environment overrides."""
import os
from pathlib import Path
import sys
from dotenv import dotenv_values


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"member", "safety", "notification"}:
        raise SystemExit("Usage: run_service.py member|safety|notification")
    root = Path(__file__).resolve().parents[1]
    env = {**{k: v for k, v in dotenv_values(root / ".env").items() if v is not None}, **os.environ}
    java = str(Path(env["JAVA_HOME"]) / "bin/java") if env.get("JAVA_HOME") else "java"
    service = sys.argv[1] + "-service"
    jar = root / "services" / service / "target" / (service + "-0.0.1-SNAPSHOT.jar")
    os.execvpe(java, [java, "-jar", str(jar)], env)


if __name__ == "__main__":
    main()

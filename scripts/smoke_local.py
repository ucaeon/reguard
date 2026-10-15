from pathlib import Path
import json, os, socket, subprocess, time, urllib.request
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
env = {
    **os.environ,
    **{k: v for k, v in dotenv_values(root / ".env").items() if v is not None},
}
processes = []
logs = []
try:
    for name, port in [("member", 8081), ("safety", 8082), ("notification", 8083)]:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
        logdir = root / "logs"
        logdir.mkdir(exist_ok=True)
        log = (logdir / f"{name}-smoke.log").open("w")
        logs.append(log)
        service_env = {**env, "SERVER_PORT": str(port), "SERVER_ADDRESS": "127.0.0.1"}
        proc = subprocess.Popen(
            [
                "java",
                "-jar",
                str(
                    root
                    / f"services/{name}-service/target/{name}-service-0.0.1-SNAPSHOT.jar"
                ),
            ],
            env=service_env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"{name} exited; see its log")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/actuator/health/readiness", timeout=2
                ) as response:
                    if json.load(response)["status"] == "UP":
                        print(f"{name}: readiness including DB is UP", flush=True)
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError(f"{name} readiness timed out")
finally:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    for log in logs:
        log.close()

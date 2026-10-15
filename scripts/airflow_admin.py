import argparse
import json
from pathlib import Path
import subprocess

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "enable", "disable", "login-file"])
    args = parser.parse_args()
    command = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / "orchestration/airflow/compose.yml"),
        "exec",
        "-T",
        "api-server",
        "cat",
        "/opt/airflow/state/ui-passwords.json",
    ]
    credentials = json.loads(
        subprocess.check_output(command, stderr=subprocess.DEVNULL)
    )
    if args.action == "login-file":
        path = ROOT / "data/airflow/ui-login.txt"
        path.write_text(
            "URL: http://localhost:18080\nUsername: admin\nPassword: "
            + credentials["admin"]
            + "\n"
        )
        path.chmod(0o600)
        print(path)
        return
    with httpx.Client(base_url="http://127.0.0.1:18080", timeout=30) as client:
        response = client.post(
            "/auth/token",
            json={"username": "admin", "password": credentials["admin"]},
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        response = client.get("/api/v2/dags", params={"limit": 100})
        response.raise_for_status()
        for dag in response.json()["dags"]:
            name = dag["dag_id"]
            if not name.startswith("reguard_"):
                continue
            if args.action in {"enable", "disable"}:
                changed = client.patch(
                    "/api/v2/dags/" + name, json={"is_paused": args.action == "disable"}
                )
                changed.raise_for_status()
                print(name, args.action)
            else:
                runs = client.get(
                    "/api/v2/dags/" + name + "/dagRuns",
                    params={"limit": 5, "order_by": "-run_after"},
                )
                runs.raise_for_status()
                print(
                    json.dumps(
                        {
                            "dag": name,
                            "paused": dag["is_paused"],
                            "runs": [
                                {"id": r["dag_run_id"], "state": r["state"]}
                                for r in runs.json()["dag_runs"]
                            ],
                        },
                        ensure_ascii=False,
                    )
                )


if __name__ == "__main__":
    main()

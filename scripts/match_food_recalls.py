from pathlib import Path
import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="reguard-local-postgres-1")
    args = parser.parse_args()
    rule = Path(__file__).resolve().parents[1] / "pipelines/spark/food_matching.sql"
    sql = "BEGIN; SELECT pg_advisory_xact_lock(72648301);\n" + 'CREATE TEMP TABLE matching_scope ON COMMIT DROP AS SELECT id AS recall_id FROM recalls;' + rule.read_text() + "\nCOMMIT;"
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            args.container,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "reguard_safety",
            "-d",
            "reguard_safety",
        ],
        input=sql,
        text=True,
        check=True,
    )


if __name__ == "__main__":
    main()

from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / ".env.airflow"
if not path.exists():
    password = secrets.token_hex(24)
    path.write_text(
        "POSTGRES_PASSWORD=" + password + "\n"
        "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:"
        + password
        + "@metadata:5432/airflow\n"
        "AIRFLOW__API_AUTH__JWT_SECRET=" + secrets.token_hex(32) + "\n"
        "AIRFLOW__API__SECRET_KEY=" + secrets.token_hex(32) + "\n"
    )
    path.chmod(0o600)
(ROOT / "data/airflow").mkdir(parents=True, exist_ok=True)
print("Local Airflow settings ready; secrets were not printed.")

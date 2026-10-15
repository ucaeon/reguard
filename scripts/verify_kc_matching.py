import os
from pathlib import Path

from dotenv import dotenv_values
import psycopg

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    with psycopg.connect(
        host=env.get("DB_HOST", "127.0.0.1"),
        port=env.get("DB_PORT", "15432"),
        dbname="reguard_safety",
        user="reguard_safety",
        password=env["SAFETY_DB_PASSWORD"],
    ) as connection:
        connection.execute("SET LOCAL search_path=pg_temp")
        connection.execute(
            "CREATE TEMP TABLE recalls(id uuid, source text, raw_payload jsonb)"
        )
        connection.execute(
            "CREATE TEMP TABLE products(id uuid, source text, model_name text)"
        )
        connection.execute(
            "CREATE TEMP TABLE product_identifiers(product_id uuid,identifier_type text,identifier_value text)"
        )
        connection.execute(
            "CREATE TEMP TABLE recall_product_matches(id uuid,recall_id uuid,product_id uuid,match_method text,match_status text,rule_version text, UNIQUE(recall_id,product_id))"
        )
        recall = "00000000-0000-0000-0000-000000000010"
        connection.execute(
            "INSERT INTO recalls VALUES (%s,'SAFETY_RECALL',%s::jsonb)",
            (
                recall,
                '{"certNum":"CB001-1234","recallModelName":"(품명) 허니 슬라임 / 다른 상품"}',
            ),
        )
        for index, model, cert in [
            (1, "허니 슬라임", "CB001-1234"),
            (2, "다른 슬라임", "CB001-1234"),
            (3, "허니 슬라임", "CB002-1234"),
        ]:
            product = f"00000000-0000-0000-0000-{index:012d}"
            connection.execute(
                "INSERT INTO products VALUES (%s,'SAFETY_KC',%s)", (product, model)
            )
            connection.execute(
                "INSERT INTO product_identifiers VALUES (%s,'KC_CERT_NO',%s)",
                (product, cert),
            )
        connection.execute("CREATE TEMP TABLE matching_scope ON COMMIT DROP AS SELECT id AS recall_id FROM recalls;")
        connection.execute((ROOT / "pipelines/spark/kc_matching.sql").read_text())
        rows = connection.execute(
            "SELECT product_id,match_status,rule_version FROM recall_product_matches"
        ).fetchall()
        assert [(str(p), s, v) for p, s, v in rows] == [
            ("00000000-0000-0000-0000-000000000001", "CANDIDATE", "kc-cert-model-v3")
        ]
        for model, expected in [
            ("허니 슬라임 / 다른 상품", 1),
            ("허니 슬라임; 다른 상품", 1),
            ("(제품명) 허니 슬라임", 1),
            ("허니 슬라임/다른 상품", 0),
            ("허니 슬라임 PLUS", 0),
            ("", 0),
        ]:
            connection.execute("UPDATE recalls SET raw_payload=jsonb_set(raw_payload,'{recallModelName}',to_jsonb(%s::text))", (model,))
            connection.execute("DROP TABLE kc_proposed")
            connection.execute((ROOT / "pipelines/spark/kc_matching.sql").read_text())
            assert connection.execute("SELECT count(*) FROM recall_product_matches").fetchone()[0] == expected, model
        connection.rollback()
    print(
        "PASS: label prefix matches; different model/certificate excluded; temporary tables rolled back"
    )


if __name__ == "__main__":
    main()

import subprocess


def reject(statement, condition):
    return (
        "DO $test$ BEGIN BEGIN "
        + statement
        + "; EXCEPTION WHEN "
        + condition
        + " THEN RETURN; END; RAISE EXCEPTION 'Expected "
        + condition
        + "'; END $test$;"
    )


u = "00000000-0000-0000-0000-000000000001"
p = "00000000-0000-0000-0000-000000000002"
r = "00000000-0000-0000-0000-000000000003"
x = "00000000-0000-0000-0000-000000000004"
y = "00000000-0000-0000-0000-000000000005"
queries = {
    "member": [
        f"INSERT INTO users(id,email,display_name) VALUES ('{u}','schema-test@example.invalid','Schema test')",
        f"INSERT INTO owned_products(id,user_id,registration_type,product_name) VALUES ('{p}','{u}','MANUAL','Manual item')",
        f"INSERT INTO owned_products(id,user_id,catalog_product_id,registration_type,product_name) VALUES ('{r}','{u}','{x}','CATALOG','Catalog item')",
        reject(
            f"INSERT INTO owned_products(id,user_id,registration_type,product_name) VALUES ('{x}','{y}','MANUAL','Orphan')",
            "foreign_key_violation",
        ),
        reject(
            f"INSERT INTO owned_products(id,user_id,registration_type,product_name) VALUES ('{x}','{u}','CATALOG','Missing catalog')",
            "check_violation",
        ),
        reject(
            f"INSERT INTO owned_products(id,user_id,catalog_product_id,registration_type,product_name) VALUES ('{x}','{u}','{y}','MANUAL','Unexpected catalog')",
            "check_violation",
        ),
        reject(
            f"INSERT INTO owned_products(id,user_id,registration_type,product_name,identifier_type) VALUES ('{x}','{u}','MANUAL','Partial identifier','BARCODE')",
            "check_violation",
        ),
    ],
    "safety": [
        f"INSERT INTO products(id,source,source_record_id,name,category) VALUES ('{p}','TEST','record-1','Test product','FOOD')",
        f"INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload) VALUES ('{r}','TEST','recall-1','Unlinked recall','{{}}')",
        reject(
            f"INSERT INTO products(id,source,source_record_id,name,category) VALUES ('{x}','TEST','record-1','Duplicate','FOOD')",
            "unique_violation",
        ),
        reject(
            f"INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload) VALUES ('{x}','TEST','recall-1','Duplicate','{{}}')",
            "unique_violation",
        ),
        f"INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value) VALUES ('{x}','{p}','BARCODE','001234')",
        reject(
            f"INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value) VALUES ('{y}','{p}','BARCODE','001234')",
            "unique_violation",
        ),
        reject(
            f"INSERT INTO product_identifiers(id,product_id,identifier_type,identifier_value) VALUES ('{y}','{y}','BARCODE','001235')",
            "foreign_key_violation",
        ),
        f"INSERT INTO recall_product_matches(id,recall_id,product_id,match_method,match_status,rule_version) VALUES ('{x}','{r}','{p}','IDENTIFIER','CONFIRMED','v1')",
        reject(
            f"INSERT INTO recall_product_matches(id,recall_id,product_id,match_method,match_status,rule_version) VALUES ('{y}','{r}','{p}','NAME','CANDIDATE','v1')",
            "unique_violation",
        ),
        reject(
            f"INSERT INTO recall_product_matches(id,recall_id,product_id,match_method,match_status,rule_version) VALUES ('{y}','{y}','{p}','NAME','CANDIDATE','v1')",
            "foreign_key_violation",
        ),
        reject(
            f"INSERT INTO recall_product_matches(id,recall_id,product_id,match_method,match_status,rule_version) VALUES ('{y}','{r}','{y}','NAME','CANDIDATE','v1')",
            "foreign_key_violation",
        ),
        reject(
            f"INSERT INTO recalls(id,source,source_recall_id,product_name,raw_payload) VALUES ('{y}','TEST','recall-2','Bad payload','[]')",
            "check_violation",
        ),
    ],
    "notification": [
        f"INSERT INTO notifications(id,user_id,owned_product_id,recall_id,notification_type,title,message) VALUES ('{u}','{p}','{r}','{x}','NEW_RECALL','Title','Message')",
        reject(
            f"INSERT INTO notifications(id,user_id,owned_product_id,recall_id,notification_type,title,message) VALUES ('{y}','{p}','{r}','{x}','NEW_RECALL','Title','Message')",
            "unique_violation",
        ),
        reject(
            f"INSERT INTO notifications(id,user_id,owned_product_id,recall_id,notification_type,title,message,eligibility_status) VALUES ('{y}','{p}','{r}','{x}','UPDATE','Title','Message','INVALID')",
            "check_violation",
        ),
    ],
}
for name, statements in queries.items():
    sql = "BEGIN;\n" + ";\n".join(statements) + ";\nROLLBACK;\n"
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "reguard-local-postgres-1",
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "reguard_" + name,
            "-d",
            "reguard_" + name,
        ],
        input=sql,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(name + ": " + result.stderr)
    print(f"{name}: {len(statements)} checks passed; fixtures rolled back")

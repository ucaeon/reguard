import hashlib
import secrets
import subprocess


def verification_token(email, request, execute=None):
    """Seed email delivery only; obtain the signup proof through the real API."""
    email = email.strip().lower()
    if not email.endswith("@example.com"):
        raise ValueError("Fixtures require an example.com address")
    code = f"{secrets.randbelow(1000000):06d}"
    digest = hashlib.sha256(f"{email}:{code}".encode()).hexdigest()
    quoted = email.replace("'", "''")
    statement = f"INSERT INTO signup_email_verifications(email,code_hash,expires_at) VALUES ('{quoted}','{digest}',now()+interval '10 minutes') ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,proof_hash=NULL,attempts=0"

    def local_execute(sql):
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "reguard-local-postgres-1",
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "reguard_member",
                "-d",
                "reguard_member",
            ],
            input=sql,
            text=True,
            capture_output=True,
            check=True,
        )

    execute = execute or local_execute
    execute(statement)
    try:
        return request(
            "POST", "/auth/signup/email/verify", {"email": email, "code": code}
        )["verificationToken"]
    except Exception:
        execute(f"DELETE FROM signup_email_verifications WHERE email='{quoted}'")
        raise


def verified_signup(request, payload, execute=None, expected=201):
    email = payload["email"].strip().lower()
    token = verification_token(email, request, execute)
    try:
        return request(
            "POST",
            "/auth/signup",
            {**payload, "verificationToken": token},
            expected=expected,
        )
    finally:
        statement = (
            "DELETE FROM signup_email_verifications WHERE email='"
            + email.replace("'", "''")
            + "'"
        )
        if execute:
            execute(statement)
        else:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    "reguard-local-postgres-1",
                    "psql",
                    "-X",
                    "-q",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "reguard_member",
                    "-d",
                    "reguard_member",
                ],
                input=statement,
                text=True,
                capture_output=True,
                check=True,
            )

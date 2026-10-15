import sys, json, secrets, hashlib, time, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_local_k3s as api
from release_install import Cluster
import argparse

parser = argparse.ArgumentParser(
    description="Exercise an isolated release environment; email delivery is not tested."
)
parser.add_argument("action", choices=["create", "verify", "delete"])
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--kubeconfig", type=Path, required=True)
parser.add_argument("--state", type=Path, required=True)
args = parser.parse_args()
config = json.loads(args.config.read_text())
if config["mode"] != "local-test" or not config["origin"].startswith(
    "http://127.0.0.1:"
):
    raise SystemExit(
        "This fixture test is restricted to isolated loopback environments"
    )
cluster = Cluster(args.kubeconfig, config["namespace"])
api.kube = cluster.call
api.ORIGIN = config["origin"]
statepath = args.state
if args.action == "create":
    email = "portable-" + secrets.token_hex(5) + "@example.com"
    password = secrets.token_urlsafe(20) + "A1!"
    code = "123456"
    digest = hashlib.sha256(f"{email}:{code}".encode()).hexdigest()
    api.db(
        f"INSERT INTO signup_email_verifications(email,code_hash,expires_at) VALUES ('{email}','{digest}',now()+interval '10 minutes')"
    )
    proof = api.request(
        "POST", "/auth/signup/email/verify", {"email": email, "code": code}
    )
    api.request(
        "POST",
        "/auth/signup",
        {
            "email": email,
            "password": password,
            "displayName": "이전 전",
            "verificationToken": proof["verificationToken"],
        },
        201,
    )
    api.request("POST", "/auth/login", {"email": email, "password": password})
    item = api.request(
        "POST",
        "/me/products",
        {
            "registrationType": "MANUAL",
            "productName": "복원 검증 완구",
            "identifierType": "KC_CERT_NO",
            "identifierValue": "CB065R2649-4001",
        },
        201,
    )
    api.request(
        "PATCH", "/me/products/" + item["id"], {"productName": "수정된 복원 검증 완구"}
    )
    api.request("PUT", "/me/profile", {"displayName": "독립 환경 검증", "photo": None})
    api.request("PUT", "/me/notification-preferences", {"enabled": True})
    fd = __import__("os").open(
        statepath,
        __import__("os").O_WRONLY | __import__("os").O_CREAT | __import__("os").O_EXCL,
        0o600,
    )
    with __import__("os").fdopen(fd, "w") as f:
        json.dump({"email": email, "password": password, "item": item["id"]}, f)
    print("PASS signup/login, manual registration, edit, profile, preferences")
else:
    state = json.loads(statepath.read_text())
    api.request(
        "POST", "/auth/login", {"email": state["email"], "password": state["password"]}
    )
    assert api.request("GET", "/me/profile")["displayName"] == "독립 환경 검증"
    assert (
        api.request("GET", "/me/products/" + state["item"])["productName"]
        == "수정된 복원 검증 완구"
    )
    assert api.request("GET", "/me/notification-preferences")["enabled"]
    print("PASS restored login, profile, edited item, notification preference")
    if args.action == "delete":
        api.request("DELETE", "/me/products/" + state["item"], expected=204)
        assert not api.request("GET", "/me/products")["items"]
        api.request("POST", "/auth/logout", expected=204)
        api.request("GET", "/me", expected=401)
        print("PASS deletion and logout")

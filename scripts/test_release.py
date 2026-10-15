import json
from pathlib import Path
import tempfile
import tarfile
import io
from unittest.mock import patch, Mock
from types import SimpleNamespace
import unittest
from release_resources import new_secrets, resources, validate, WORKLOADS, CLAIMS
from release_install import verify_bundle, digest
from release_recovery import validate_snapshot, restore


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.credentials = new_secrets()
        self.config = {
            "namespace": "reguard",
            "mode": "local-test",
            "origin": "http://127.0.0.1:14000",
        }
        self.images = {
            name: "docker.io/library/reguard-" + name + "@sha256:" + "a" * 64
            for name in [
                "postgres",
                "metadata",
                "kafka",
                "member",
                "safety",
                "notification",
                "airflow",
                "spark",
                "web",
            ]
        }

    def test_no_host_mounts_and_all_images_immutable(self):
        objects = resources(self.config, self.credentials, self.images)
        text = json.dumps(objects)
        self.assertNotIn("hostPath", text)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/workspace", text)
        deployments = [o for o in objects if o["kind"] == "Deployment"]
        self.assertEqual(set(WORKLOADS), {d["metadata"]["name"] for d in deployments})
        for d in deployments:
            pod = d["spec"]["template"]["spec"]
            for c in pod["containers"] + pod.get("initContainers", []):
                self.assertIn("@sha256:", c["image"])
                self.assertEqual("Never", c["imagePullPolicy"])
        self.assertEqual(
            set(CLAIMS),
            {
                o["metadata"]["name"]
                for o in objects
                if o["kind"] == "PersistentVolumeClaim"
            },
        )

    def test_credentials_not_in_config_maps(self):
        for o in resources(self.config, self.credentials, self.images):
            if o["kind"] == "ConfigMap":
                for value in self.credentials.values():
                    if value:
                        self.assertNotIn(value, json.dumps(o))

    def test_production_requires_https_and_provider_credentials(self):
        self.config["mode"] = "production"
        with self.assertRaises(ValueError):
            validate(self.config, self.credentials)
        self.config["origin"] = "https://reguard.example.com"
        with self.assertRaises(ValueError):
            validate(self.config, self.credentials)
        self.credentials.update(
            {
                k: "configured"
                for k in [
                    "FOOD_SAFETY_API_KEY",
                    "SAFETY_KOREA_API_KEY",
                    "SMTP_USERNAME",
                    "SMTP_PASSWORD",
                ]
            }
        )
        self.config.update(smtp_host="smtp.example.com", mail_from="me@example.com")
        validate(self.config, self.credentials)
        objects = resources(self.config, self.credentials, self.images)
        member = next(
            o
            for o in objects
            if o["kind"] == "ConfigMap" and o["metadata"]["name"] == "member-env"
        )
        self.assertEqual("true", member["data"]["COOKIE_SECURE"])
        web = next(
            o
            for o in objects
            if o["kind"] == "Deployment" and o["metadata"]["name"] == "web"
        )
        self.assertEqual(
            [80, 443],
            [
                p["hostPort"]
                for p in web["spec"]["template"]["spec"]["containers"][0]["ports"]
            ],
        )

    def test_test_mode_rejects_public_origin(self):
        self.config["origin"] = "http://example.com"
        with self.assertRaises(ValueError):
            validate(self.config, self.credentials)

    def test_bundle_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "image.tar").write_bytes(b"original")
            lock = {
                "platform": "linux/arm64",
                "files": {},
                "images": {
                    "web": {"archive": "image.tar", "sha256": digest(p / "image.tar")}
                },
            }
            (p / "release.json").write_text(json.dumps(lock))
            verify_bundle(p)
            (p / "image.tar").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_bundle(p)

    def test_snapshot_rejects_wrong_secrets_before_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "release.json").write_text("{}")
            (p / "secret").write_text("new")
            (p / "snapshot.json").write_text(
                json.dumps(
                    {
                        "release_sha256": digest(p / "release.json"),
                        "credentials_sha256": "wrong",
                    }
                )
            )
            with self.assertRaises(ValueError):
                validate_snapshot(p, p, p / "secret")

    def test_snapshot_rejects_traversal_and_corrupt_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "release.json").write_text("{}")
            (p / "secret").write_text("credential")
            files = {}
            for name in CLAIMS:
                archive = p / (name + ".tar")
                with tarfile.open(archive, "w") as tar:
                    entry = tarfile.TarInfo(
                        "../outside" if name == "postgres" else "safe"
                    )
                    entry.size = 1
                    tar.addfile(entry, io.BytesIO(b"x"))
                files[archive.name] = digest(archive)
            (p / "snapshot.json").write_text(
                json.dumps(
                    {
                        "release_sha256": digest(p / "release.json"),
                        "credentials_sha256": digest(p / "secret"),
                        "files": files,
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "Unsafe snapshot"):
                validate_snapshot(p, p, p / "secret")
            (p / "postgres.tar").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_snapshot(p, p, p / "secret")

    def test_restore_never_overwrites_existing_workloads(self):
        cluster = Mock()
        cluster.call.return_value = json.dumps(
            {"items": [{"metadata": {"name": "postgres"}}]}
        )
        args = SimpleNamespace(
            snapshot=Path("snapshot"), bundle=Path("bundle"), secrets=Path("secrets")
        )
        with patch("release_recovery.validate_snapshot"):
            with self.assertRaisesRegex(ValueError, "new namespace"):
                restore(cluster, args, self.config, self.credentials, self.images, {})
        cluster.apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()

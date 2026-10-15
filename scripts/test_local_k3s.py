import unittest
from unittest.mock import patch
import local_k3s
from k3s_resources import deployment as make_deployment


class MigrationSafetyTest(unittest.TestCase):
    def test_apply_refuses_running_source_before_any_mutation(self):
        with (
            patch.object(
                local_k3s,
                "source_config",
                return_value={"postgres": {"State": {"Running": True}}},
            ),
            patch.object(local_k3s, "kube") as kube,
        ):
            with self.assertRaisesRegex(RuntimeError, "Stop source writers"):
                local_k3s.apply()
            kube.assert_not_called()

    def test_secrets_not_in_configmap_and_db_liveness_not_used_for_java(self):
        objects = []

        def add(kind, name, **fields):
            objects.append({"kind": kind, **fields})

        make_deployment(
            "member",
            "local:test",
            {
                "SERVER_PORT": "8081",
                "DB_HOST": "postgres",
                "MEMBER_DB_PASSWORD": "private",
            },
            [],
            [],
            ("1", "768Mi"),
            {"httpGet": {"path": "/actuator/health/readiness", "port": 8081}},
            None,
            add,
            secure=True,
        )
        config, secret, deployment = objects
        self.assertNotIn("MEMBER_DB_PASSWORD", config["data"])
        self.assertEqual(secret["stringData"]["MEMBER_DB_PASSWORD"], "private")
        template = deployment["spec"]["template"]["spec"]
        self.assertFalse(template["automountServiceAccountToken"])
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual(
            template["containers"][0]["livenessProbe"]["httpGet"]["path"],
            "/actuator/health/liveness",
        )

    def test_active_airflow_task_prevents_source_stop(self):
        with patch.object(local_k3s, "run", return_value="1") as run:
            with self.assertRaisesRegex(RuntimeError, "tasks still active"):
                local_k3s.stop_source()
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pipeline_backup import snapshot, verify, stopped


class PipelineBackupTest(unittest.TestCase):
    def test_wal_snapshot_and_corruption_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoints = root / "checkpoints"
            checkpoints.mkdir()
            (checkpoints / "offset").write_text("42")
            cache = root / "cache"
            cache.mkdir()
            (cache / "response").write_text("source payload")
            with sqlite3.connect(root / "state.sqlite") as source:
                source.execute("PRAGMA journal_mode=WAL")
                source.execute("CREATE TABLE watermark(day TEXT)")
                source.execute("INSERT INTO watermark VALUES ('2026-10-15')")
                source.commit()
                result = snapshot(
                    root / "state.sqlite", checkpoints, cache, root / "backups"
                )
                verify(result)
                with sqlite3.connect(result / "state.sqlite") as restored:
                    self.assertEqual(
                        restored.execute("SELECT day FROM watermark").fetchone()[0],
                        "2026-10-15",
                    )
                (result / "checkpoints/offset").write_text("43")
                with self.assertRaises(RuntimeError):
                    verify(result)

    def test_running_writer_rejected(self):
        with patch("pipeline_backup.subprocess.check_output", return_value="true\n"):
            with self.assertRaises(RuntimeError):
                stopped(["spark"])

    def test_unknown_container_is_not_accepted(self):
        with patch(
            "pipeline_backup.subprocess.check_output",
            side_effect=RuntimeError("missing"),
        ):
            with self.assertRaises(RuntimeError):
                stopped(["missing"])


if __name__ == "__main__":
    unittest.main()

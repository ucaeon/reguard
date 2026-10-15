import unittest
from unittest.mock import Mock

from pipelines.spark.matching import match_sources


class MatchingScopeTest(unittest.TestCase):
    def test_only_affected_source_family_runs(self):
        for sources, expected in [
            ({"FOOD_I0030"}, ["food_matching.sql"]),
            ({"SAFETY_RECALL"}, ["kc_matching.sql"]),
            ({"FOOD_I1250", "FOOD_I0490", "SAFETY_KC"},
             ["food_matching.sql", "kc_matching.sql"]),
            (set(), []),
        ]:
            with self.subTest(sources=sources):
                cursor = Mock()
                self.assertEqual(match_sources(cursor, sources), expected)
                self.assertEqual(cursor.execute.call_count, len(expected) + (3 if sources else 0))
                for call in cursor.execute.call_args_list:
                    self.assertNotIn("COMMIT;", call.args[0])
                    self.assertNotIn("BEGIN;", call.args[0])

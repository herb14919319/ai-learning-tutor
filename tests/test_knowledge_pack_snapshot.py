"""Knowledge Pack behaviour (module API and HTTP) must match the pre-R4 snapshot exactly."""

import json
import unittest

from tests.knowledge_pack_snapshot import FIXTURE, capture


class KnowledgePackSnapshotTest(unittest.TestCase):
    maxDiff = None

    def test_behaviour_matches_pre_r4_snapshot(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(capture(), ensure_ascii=False))
        for pack_id in expected:
            with self.subTest(pack=pack_id):
                self.assertEqual(actual[pack_id], expected[pack_id])
        self.assertEqual(set(actual), set(expected))


if __name__ == "__main__":
    unittest.main()

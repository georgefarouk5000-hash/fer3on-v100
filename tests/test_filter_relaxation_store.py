# =============================================================================
# FER3ON V6 Recovery+ — filter_relaxation store persistence tests
# =============================================================================

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFilterRelaxationStore(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._analytics_dir = os.path.join(self._tmpdir.name, "analytics")
        self._store_file = os.path.join(self._analytics_dir, "filter_relaxation.json")
        self._patcher_dir = mock.patch(
            "brain.filter_relaxation.ANALYTICS_DIR", self._analytics_dir
        )
        self._patcher_file = mock.patch(
            "brain.filter_relaxation.STORE_FILE", self._store_file
        )
        self._patcher_dir.start()
        self._patcher_file.start()

    def tearDown(self):
        self._patcher_file.stop()
        self._patcher_dir.stop()
        self._tmpdir.cleanup()

    def test_file_creation(self):
        from brain.filter_relaxation import _ensure_store

        self.assertFalse(os.path.exists(self._store_file))
        _ensure_store()
        self.assertTrue(os.path.isdir(self._analytics_dir))
        self.assertTrue(os.path.exists(self._store_file))
        with open(self._store_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"filter_stats": {}, "history": []})

    def test_file_saving(self):
        from brain.filter_relaxation import _ensure_store, _save_store

        _ensure_store()
        payload = {
            "filter_stats": {"QUALITY_GATE": {"total": 2, "false_rejections": 1}},
            "history": [{"factor": 0.95}],
        }
        _save_store(payload)
        with open(self._store_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved, payload)

    def test_file_loading(self):
        from brain.filter_relaxation import _load_store

        os.makedirs(self._analytics_dir, exist_ok=True)
        expected = {
            "filter_stats": {"RSI": {"total": 5, "false_rejections": 2}},
            "history": [],
        }
        with open(self._store_file, "w", encoding="utf-8") as f:
            json.dump(expected, f)
        loaded = _load_store()
        self.assertEqual(loaded, expected)

    def test_no_recursion(self):
        from brain import filter_relaxation as fr

        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(100)
        try:
            fr._ensure_store()
            fr._save_store({"filter_stats": {"A": {"total": 1}}, "history": []})
            fr._load_store()
            fr._ensure_store()
            fr._save_store(fr._load_store())
        finally:
            sys.setrecursionlimit(old_limit)

        self.assertLessEqual(
            len(fr._ensure_store.__code__.co_names),
            10,
        )
        self.assertNotIn("_save_store", fr._ensure_store.__code__.co_names)
        self.assertNotIn("_ensure_store", fr._save_store.__code__.co_names)

    def test_corrupted_file_rebuild(self):
        from brain.filter_relaxation import _load_store

        os.makedirs(self._analytics_dir, exist_ok=True)
        with open(self._store_file, "w", encoding="utf-8") as f:
            f.write("{not valid json")

        loaded = _load_store()
        self.assertEqual(loaded, {"filter_stats": {}, "history": []})
        with open(self._store_file, "r", encoding="utf-8") as f:
            rebuilt = json.load(f)
        self.assertEqual(rebuilt, {"filter_stats": {}, "history": []})

    def test_no_crash_on_round_trip(self):
        from brain.filter_relaxation import _load_store, _save_store

        data = _load_store()
        data["filter_stats"]["TEST"] = {"total": 3, "false_rejections": 1}
        _save_store(data)
        reloaded = _load_store()
        self.assertEqual(reloaded["filter_stats"]["TEST"]["total"], 3)


if __name__ == "__main__":
    unittest.main()

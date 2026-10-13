"""Regression tests for isolated Edge TTS import precedence."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "termux" / "tts-launcher-play"
player = SourceFileLoader("tts_launcher_isolated_import", str(SCRIPT)).load_module()


class IsolatedEdgeTests(unittest.TestCase):
    def test_vendor_preferred_without_overwriting_global_modules(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "edge-tts-7.3.1"
            folder.mkdir()
            with patch.object(player, "EDGE_TTS_DIR", folder), \
                 patch.object(player.sys, "path", list(sys.path)):
                self.assertTrue(player.prefer_isolated_edge_tts())
                self.assertEqual(player.sys.path[0], str(folder))
                self.assertTrue(player.prefer_isolated_edge_tts())
                self.assertEqual(player.sys.path.count(str(folder)), 1)

    def test_missing_vendor_does_not_change_path(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(player, "EDGE_TTS_DIR", Path(td) / "missing"), \
                 patch.object(player.sys, "path", list(sys.path)):
                before = list(player.sys.path)
                self.assertFalse(player.prefer_isolated_edge_tts())
                self.assertEqual(before, player.sys.path)


if __name__ == "__main__":
    unittest.main()

"""Experimental TTS imports the isolated Edge TTS package when installed."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "termux" / "tts-launcher-stream"
stream = SourceFileLoader("edge_tts_stream_vendor", str(MODULE_PATH)).load_module()


class IsolatedStreamTests(unittest.TestCase):
    def test_isolated_package_takes_import_precedence(self):
        with tempfile.TemporaryDirectory() as td:
            location = Path(td) / "edge-tts-7.3.1"
            location.mkdir()
            with patch.object(stream, "EDGE_TTS_DIR", location), \
                 patch.object(stream.sys, "path", list(sys.path)):
                self.assertTrue(stream.prefer_isolated_edge_tts())
                self.assertEqual(stream.sys.path[0], str(location))
                self.assertTrue(stream.prefer_isolated_edge_tts())
                self.assertEqual(stream.sys.path.count(str(location)), 1)

    def test_missing_isolated_package_is_harmless(self):
        with tempfile.TemporaryDirectory() as td:
            location = Path(td) / "missing"
            with patch.object(stream, "EDGE_TTS_DIR", location), \
                 patch.object(stream.sys, "path", list(sys.path)):
                before = list(stream.sys.path)
                self.assertFalse(stream.prefer_isolated_edge_tts())
                self.assertEqual(before, stream.sys.path)

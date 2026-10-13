"""Tests run without a phone, audio generation, or Termux installed."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "termux" / "tts-launcher-play"
script = SourceFileLoader("tts_launcher_play", str(SCRIPT)).load_module()


class ChunkingTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(script.split_chunks(" \n\n "), [])

    def test_short(self):
        self.assertEqual(script.split_chunks("Привет, мир!"), ["Привет, мир!"])

    def test_long_text_preserved(self):
        input_text = ("Одно предложение. Второе предложение! " * 200).strip()
        chunks = script.split_chunks(input_text, 520, 1250)
        self.assertGreater(len(chunks), 2)
        self.assertLessEqual(len(chunks[0]), 520)
        self.assertTrue(all(len(c) <= 1250 for c in chunks[1:]))
        self.assertEqual(" ".join(" ".join(chunks).split()), " ".join(input_text.split()))

    def test_no_spaces(self):
        text = "А" * 2800
        self.assertEqual("".join(script.split_chunks(text)), text)

    def test_track_ownership(self):
        self.assertTrue(script.owned_track("Status: Playing\nTrack: tts-launcher-abc-0000.mp3", "abc"))
        self.assertFalse(script.owned_track("Status: Playing\nTrack: tts-launcher-xyz-0000.mp3", "abc"))
        self.assertFalse(script.owned_track("Status: Playing\nTrack: audiobook.mp3"))

    def test_only_our_track_is_stopped(self):
        with patch.object(script, "media_info", return_value="Status: Playing\nTrack: unrelated.mp3"), \
             patch.object(script, "command") as cmd:
            script.stop_owned("abc")
            cmd.assert_not_called()

    def test_state_token(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned"):
                script.claim("first")
                self.assertTrue(script.still_active("first"))
                script.claim("second")
                script.clear_if_active("first")
                self.assertTrue(script.still_active("second"))
                script.clear_if_active("second")
                self.assertFalse(script.still_active("second"))


if __name__ == "__main__":
    unittest.main()

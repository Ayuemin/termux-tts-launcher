"""Tests for bounded, safe recovery of orphaned temporary audio."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
script = SourceFileLoader("tts_launcher_cleanup", str(ROOT / "termux" / "tts-launcher-play")).load_module()


class StaleAudioCleanupTests(unittest.TestCase):
    def test_only_old_launcher_directories_are_removed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            old = base / "tts-launcher-old"
            new = base / "tts-launcher-new"
            unrelated = base / "other-project"
            for directory in (old, new, unrelated):
                directory.mkdir()
                (directory / "sample.mp3").write_bytes(b"MP3")
            timestamp = time.time() - script.STALE_AUDIO_SECONDS - 120
            os.utime(old, (timestamp, timestamp))
            os.utime(unrelated, (timestamp, timestamp))
            with patch.object(script.tempfile, "gettempdir", return_value=td):
                script.cleanup_stale_audio_dirs()
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertTrue(unrelated.exists())

    def test_symlink_to_old_directory_is_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            outside = base / "outside"
            outside.mkdir()
            (outside / "important.txt").write_text("keep")
            symlink = base / "tts-launcher-danger"
            symlink.symlink_to(outside, target_is_directory=True)
            timestamp = time.time() - script.STALE_AUDIO_SECONDS - 120
            os.utime(outside, (timestamp, timestamp))
            with patch.object(script.tempfile, "gettempdir", return_value=td):
                script.cleanup_stale_audio_dirs()
            self.assertTrue((outside / "important.txt").exists())
            self.assertTrue(symlink.is_symlink())

    def test_missing_temp_root_is_harmless(self):
        with patch.object(script.tempfile, "gettempdir", return_value="/nonexistent/tts-launcher-test-dir"):
            script.cleanup_stale_audio_dirs()

    def test_timing_report_is_replaced_not_appended(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch.object(script, "STATE_DIR", base), \
                 patch.object(script, "ACTIVE_FILE", base / "active"), \
                 patch.object(script, "LOCK_FILE", base / "active.lock"), \
                 patch.object(script, "TIMING_FILE", base / "last-timing.txt"), \
                 patch.object(script, "EVENTS_FILE", base / "last-events.log"), \
                 patch.object(script, "stop_owned"):
                self.assertTrue(script.toggle_session("test"))
                script.record_first_play("test", 1.0, 1.1, 2.1, 2.2, 2)
                script.record_first_play("test", 3.0, 3.1, 4.1, 4.2, 4)
                report = script.TIMING_FILE.read_text()
                self.assertEqual(report.count("segments="), 1)
                self.assertIn("segments=4", report)
                script.clear_if_active("test")

    def test_event_log_rotates_and_stays_small(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch.object(script, "STATE_DIR", base), \
                 patch.object(script, "EVENTS_FILE", base / "last-events.log"):
                script.EVENTS_FILE.write_text("x" * (16 * 1024 + 5))
                script.log_event("test_event")
                report = script.EVENTS_FILE.read_text()
                self.assertLess(len(report), 1024)
                self.assertIn("test_event", report)


if __name__ == "__main__":
    unittest.main()

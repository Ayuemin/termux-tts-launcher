"""Tests run without a phone, audio generation, or Termux installed."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
import tempfile
import subprocess
import threading
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

    def test_quick_start_forty_words(self):
        text = " ".join(["тестовое" for _ in range(40)])
        parts = script.split_chunks(text)
        self.assertGreater(len(parts), 1)
        self.assertLessEqual(len(parts[0]), 155)
        self.assertEqual(" ".join(parts), text)

    def test_first_claim_skips_player_check(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned") as stop:
                self.assertTrue(script.toggle_session("first"))
                stop.assert_not_called()
                self.assertFalse(script.toggle_session("second"))
                stop.assert_called_once_with("first")

    def test_synthesize_uses_edge_tts_python_api_not_cli(self):
        class FakeCommunicate:
            def __init__(self, text, voice):
                self.text, self.voice = text, voice
            async def save(self, path):
                Path(path).write_bytes(b"MP3")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "fragment.mp3"
            fake = SimpleNamespace(Communicate=FakeCommunicate)
            with patch.object(script, "edge_tts", fake), \
                 patch.object(script, "still_active", return_value=True), \
                 patch.object(script, "command", side_effect=AssertionError("CLI called")):
                self.assertEqual(script.synthesize("тест", target, "x"), target)
                self.assertEqual(target.read_bytes(), b"MP3")

    def test_timing_contains_no_clipboard_text(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "TIMING_FILE", Path(td) / "last-timing.txt"):
                self.assertTrue(script.toggle_session("example"))
                script.record_first_play("example", 1.0, 1.2, 2.4, 2.7, 2)
                report = script.TIMING_FILE.read_text()
                self.assertIn("first_play_request_ms=1700", report)
                self.assertIn("segments=2", report)
                self.assertNotIn("тест", report)

    def test_second_tap_stops_instead_of_restart(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned") as stop:
                self.assertTrue(script.toggle_session("first"))
                self.assertTrue(script.still_active("first"))
                self.assertFalse(script.toggle_session("second"))
                self.assertFalse(script.still_active("first"))
                self.assertFalse(script.still_active("second"))
                stop.assert_called_once_with("first")
                self.assertTrue(script.toggle_session("third"))
                self.assertTrue(script.still_active("third"))
                script.clear_if_active("first")
                self.assertTrue(script.still_active("third"))
                script.clear_if_active("third")
                self.assertFalse(script.still_active("third"))

    def test_stop_during_synthesis_even_if_input_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned"):
                self.assertTrue(script.toggle_session("old"))
                with patch.object(script, "split_chunks", side_effect=AssertionError("synthesis attempted")):
                    self.assertEqual(script.run(""), 0)
                self.assertFalse(script.still_active("old"))

    def test_stale_session_is_replaced_not_cancelled(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned"):
                script.ACTIVE_FILE.write_text("old 12345", encoding="ascii")
                with patch.object(script.os, "kill", side_effect=ProcessLookupError), \
                     patch.object(script, "media_info", return_value="No track currently!"):
                    self.assertTrue(script.toggle_session("fresh"))
                self.assertTrue(script.still_active("fresh"))

    def test_orphan_audio_is_stopped_not_restarted(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "EVENTS_FILE", Path(td) / "events.log"), \
                 patch.object(script.os, "kill", side_effect=ProcessLookupError), \
                 patch.object(script, "media_info", return_value="Status: Playing\nTrack: tts-launcher-old-0000.mp3"), \
                 patch.object(script, "stop_owned") as stop:
                script.ACTIVE_FILE.write_text("old 12345", encoding="ascii")
                self.assertFalse(script.toggle_session("new"))
                self.assertFalse(script.ACTIVE_FILE.exists())
                stop.assert_called_once_with("old")
                self.assertIn("tap_stop_orphan", script.EVENTS_FILE.read_text())

    def test_lost_media_info_does_not_restart_orphan_audio(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script.os, "kill", side_effect=ProcessLookupError), \
                 patch.object(script, "media_info", side_effect=subprocess.TimeoutExpired("info", 12)), \
                 patch.object(script, "stop_owned"):
                script.ACTIVE_FILE.write_text("old 12345", encoding="ascii")
                self.assertFalse(script.toggle_session("new"))
                self.assertFalse(script.ACTIVE_FILE.exists())

    def test_status_failure_keeps_marker_and_does_not_log_clipboard(self):
        with tempfile.TemporaryDirectory() as td:
            def fake_synthesize(chunk, path, run_id, markers=None, origin=None):
                path.write_bytes(b"MP3")
                return path
            def fake_play(path, run_id, on_started=None):
                if on_started:
                    on_started()
                raise RuntimeError("status unavailable")
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "TIMING_FILE", Path(td) / "timing.txt"), \
                 patch.object(script, "EVENTS_FILE", Path(td) / "events.log"), \
                 patch.object(script.importlib.util, "find_spec", return_value=object()), \
                 patch.object(script.shutil, "which", return_value="player"), \
                 patch.object(script, "synthesize", side_effect=fake_synthesize), \
                 patch.object(script, "play_file", side_effect=fake_play):
                with self.assertRaises(RuntimeError):
                    script.run("Секретный текст из буфера")
                self.assertTrue(script.ACTIVE_FILE.exists())
                self.assertIn("player_status_uncertain", script.EVENTS_FILE.read_text())
                self.assertNotIn("Секретный", script.EVENTS_FILE.read_text())
                self.assertNotIn("Секретный", script.TIMING_FILE.read_text())

    def test_cancelled_session_cannot_start_media(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "command", side_effect=AssertionError("played after stop")):
                self.assertTrue(script.toggle_session("old"))
                script.ACTIVE_FILE.unlink()
                script.play_file(Path(td) / "audio.mp3", "old")

    def test_stop_while_player_starting_does_not_resurrect_audio(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"):
                self.assertTrue(script.toggle_session("old"))
                started = threading.Event()
                release = threading.Event()
                calls = []
                failures = []
                def media_command(args, timeout=12):
                    calls.append(tuple(args))
                    if args[1] == "play":
                        started.set()
                        if not release.wait(timeout=3):
                            raise TimeoutError("test player hung")
                        return SimpleNamespace(returncode=0, stdout="Now Playing: test.mp3", stderr="")
                    return SimpleNamespace(returncode=0, stdout="Stopped", stderr="")
                def play():
                    try:
                        script.play_file(Path(td) / "tts-launcher-old-0000.mp3", "old")
                    except Exception as exc:
                        failures.append(exc)
                def stop():
                    try:
                        script.toggle_session("second")
                    except Exception as exc:
                        failures.append(exc)
                with patch.object(script, "command", side_effect=media_command), \
                     patch.object(script, "media_info", return_value="Status: Playing\nTrack: tts-launcher-old-0000.mp3"):
                    worker = threading.Thread(target=play)
                    stopper = threading.Thread(target=stop)
                    worker.start()
                    self.assertTrue(started.wait(timeout=2))
                    stopper.start()
                    release.set()
                    worker.join(timeout=3)
                    stopper.join(timeout=3)
                    self.assertFalse(worker.is_alive())
                    self.assertFalse(stopper.is_alive())
                    self.assertEqual(failures, [])
                    self.assertIn(("termux-media-player", "stop"), calls)
                    self.assertFalse(script.ACTIVE_FILE.exists())

    def test_legacy_token_is_stopped_once(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned"):
                script.ACTIVE_FILE.write_text("legacy", encoding="ascii")
                self.assertFalse(script.toggle_session("new"))
                self.assertTrue(script.toggle_session("third"))

    def test_empty_first_tap_does_not_leave_active_marker(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(script, "STATE_DIR", Path(td)), \
                 patch.object(script, "ACTIVE_FILE", Path(td) / "active"), \
                 patch.object(script, "LOCK_FILE", Path(td) / "lock"), \
                 patch.object(script, "stop_owned"), \
                 patch.object(script.importlib.util, "find_spec", return_value=object()), \
                 patch.object(script.shutil, "which", return_value="player"):
                self.assertEqual(script.run(""), 1)
                self.assertFalse(script.ACTIVE_FILE.exists())


if __name__ == "__main__":
    unittest.main()

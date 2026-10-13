"""Check first-packet measurements without Android or a network."""
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
script = SourceFileLoader("tts_launcher_timing", str(ROOT / "termux" / "tts-launcher-play")).load_module()


class NetworkTimingTests(unittest.TestCase):
    def test_first_fragment_produces_unchanged_mp3_bytes_and_numeric_timings(self):
        class FakeCommunicate:
            def __init__(self, text, voice):
                pass
            async def stream(self):
                yield {"type": "WordBoundary", "text": "private text"}
                yield {"type": "audio", "data": b"abc"}
                yield {"type": "audio", "data": b"xyz"}
            async def save(self, path):
                raise AssertionError("The first fragment must record stream packet times")
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "fragment.mp3"
            metrics = {}
            with patch.object(script, "edge_tts", SimpleNamespace(Communicate=FakeCommunicate)), \
                 patch.object(script, "still_active", return_value=True):
                script.synthesize("secret copied text", dest, "run", metrics, script.time.monotonic())
            self.assertEqual(dest.read_bytes(), b"abcxyz")
            self.assertEqual(metrics["first_attempt_number"], 1)
            for key in ("first_synthesis_start_ms", "first_stream_request_ms",
                        "first_stream_event_ms", "first_audio_packet_ms", "first_synthesis_done_ms"):
                self.assertIsInstance(metrics[key], int)
                self.assertGreaterEqual(metrics[key], 0)
            self.assertLessEqual(metrics["first_audio_packet_ms"], metrics["first_synthesis_done_ms"])
            self.assertNotIn("secret", str(metrics))
            self.assertNotIn("private", str(metrics))

    def test_other_fragments_retain_original_save_method(self):
        class FakeCommunicate:
            def __init__(self, text, voice):
                pass
            async def save(self, path):
                Path(path).write_bytes(b"original")
            async def stream(self):
                raise AssertionError("Later fragments must keep the save() path")
                yield
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "later.mp3"
            with patch.object(script, "edge_tts", SimpleNamespace(Communicate=FakeCommunicate)), \
                 patch.object(script, "still_active", return_value=True):
                script.synthesize("test", dest, "run")
            self.assertEqual(dest.read_bytes(), b"original")

    def test_report_contains_metrics_but_not_user_text(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch.object(script, "STATE_DIR", base), \
                 patch.object(script, "ACTIVE_FILE", base / "active"), \
                 patch.object(script, "LOCK_FILE", base / "lock"), \
                 patch.object(script, "TIMING_FILE", base / "timing.txt"), \
                 patch.object(script, "EVENTS_FILE", base / "events.log"), \
                 patch.object(script, "stop_owned"):
                self.assertTrue(script.toggle_session("run"))
                marks = {"first_stream_event_ms": 1000, "first_audio_packet_ms": 1250,
                         "first_synthesis_done_ms": 1500, "unused_secret": "not-for-logs"}
                script.record_first_play("run", 1.0, 1.01, 2.5, 2.6, 3, marks)
                report = (base / "timing.txt").read_text()
                self.assertIn("first_audio_packet_ms=1250", report)
                self.assertIn("first_audio_ready_ms=1500", report)
                self.assertNotIn("not-for-logs", report)
                self.assertNotIn("unused_secret", report)
                script.clear_if_active("run")


if __name__ == "__main__":
    unittest.main()

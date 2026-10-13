"""Exercise real loopback HTTP framing and cancellation with fake TTS data."""
import asyncio
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'termux' / 'tts-launcher-stream'
stream = SourceFileLoader('streaming_tts', str(SCRIPT)).load_module()
TOKEN = 'a' * 32


class FakeCommunicate:
    def __init__(self, text, voice):
        self.text, self.voice = text, voice

    async def stream(self):
        yield {'type': 'WordBoundary', 'data': None}
        yield {'type': 'audio', 'data': b'ABC'}
        yield {'type': 'audio', 'data': b'XYZ'}


async def request(port, route):
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    writer.write(f'GET /{route}/{TOKEN} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode())
    await writer.drain()
    result = await asyncio.wait_for(reader.read(), 2)
    writer.close()
    await writer.wait_closed()
    return result


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.patchers = [patch.object(stream, 'STATE_DIR', self.base),
                         patch.object(stream, 'LOG_PATH', self.base / 'events.log')]
        for p in self.patchers:
            p.start()
        self.server_obj = stream.AudioStreamServer('private text', 0, TOKEN,
                                                    SimpleNamespace(Communicate=FakeCommunicate))
        self.server = await asyncio.start_server(self.server_obj.client, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    async def test_health_and_authentication(self):
        response = await request(self.port, 'health')
        self.assertIn(b'204 No Content', response)
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        writer.write(b'GET /stream/INVALID HTTP/1.1\r\nHost: localhost\r\n\r\n')
        await writer.drain()
        self.assertIn(b'404 Not Found', await reader.read())
        writer.close()
        await writer.wait_closed()

    async def test_mp3_bytes_stream_in_chunked_http_without_text_logging(self):
        result = await request(self.port, 'stream')
        self.assertTrue(result.startswith(b'HTTP/1.1 200 OK'))
        self.assertIn(b'Transfer-Encoding: chunked', result)
        self.assertIn(b'3\r\nABC\r\n3\r\nXYZ\r\n0\r\n\r\n', result)
        log = (self.base / 'events.log').read_text()
        self.assertNotIn('private', log)
        self.assertIn('first_audio_packet_ms_', log)
        self.assertTrue(self.server_obj.finished.is_set())

    async def test_duplicate_stream_refused(self):
        await request(self.port, 'stream')
        result = await request(self.port, 'stream')
        self.assertIn(b'409 Conflict', result)

    async def test_stop_endpoint_stops_before_stream(self):
        result = await request(self.port, 'stop')
        self.assertIn(b'204 No Content', result)
        self.assertTrue(self.server_obj.finished.is_set())


class BasicTests(unittest.TestCase):
    def test_token_checks(self):
        self.assertTrue(stream.valid_token('0123456789abcdef' * 2))
        self.assertFalse(stream.valid_token('xyz'))
        self.assertFalse(stream.valid_token('a' * 31))

    def test_bounded_log(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / 'last-events.log'
            with patch.object(stream, 'STATE_DIR', Path(td)), patch.object(stream, 'LOG_PATH', log):
                log.write_bytes(b'x' * (17 * 1024))
                stream.log_event('test')
                self.assertLess(log.stat().st_size, 500)

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import engine


class NetworkDeadlineTests(unittest.TestCase):
    def test_real_worker_returns_response_bytes_without_network_access(self):
        raw = engine.fetch('data:application/json,%7B%22ok%22%3Atrue%7D', timeout=10, attempts=1)
        self.assertEqual(json.loads(raw), {'ok': True})

    def test_stalled_worker_is_stopped_within_total_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / 'stalled.py'
            worker.write_text('import time\ntime.sleep(20)\n', encoding='utf-8')
            started = time.monotonic()
            with patch.object(engine, 'NETWORK_WORKER', worker):
                with self.assertRaisesRegex(engine.FetchError, 'total time limit') as raised:
                    engine.fetch('https://example.com/?key=private-test-key', timeout=0.2)
            self.assertLess(time.monotonic() - started, 5)
            self.assertNotIn('private-test-key', str(raised.exception))
            self.assertNotIn('example.com', str(raised.exception))

    def test_worker_errors_preserve_status_and_requests_travel_through_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / 'failure.py'
            worker.write_text(
                'import json,sys\n'
                'assert len(sys.argv) == 1\n'
                'job=json.load(sys.stdin)\n'
                'assert job["payload"] == {"test": True}\n'
                'assert "private-test-key" in job["url"]\n'
                'sys.stderr.write(json.dumps({"message":"HTTP 403: Access denied", "status":403}))\n'
                'sys.exit(2)\n', encoding='utf-8')
            with patch.object(engine, 'NETWORK_WORKER', worker):
                with self.assertRaisesRegex(engine.FetchError, 'Access denied') as raised:
                    engine.fetch('https://example.com/?key=private-test-key', {'test': True}, timeout=10)
            self.assertEqual(raised.exception.status, 403)
            self.assertNotIn('private-test-key', str(raised.exception))

"""Failed API requests must retain evidence without claiming a completed run."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import validate_api_video as validator


class VideoEvidenceTests(unittest.TestCase):
    def test_http_failure_keeps_response_and_server_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / 'validate_api_video.py'
            script.write_bytes(Path(validator.__file__).read_bytes())
            video = root / 'fixture.mp4'
            video.write_bytes(b'Client evidence fixture; no actual video inference.')
            health = Mock()
            health.json.return_value = {'status': 'ok'}
            failure = Mock(status_code=500, text='Internal Server Error')
            failure.raise_for_status.side_effect = requests.HTTPError('500 server error')
            status = Mock()
            status.json.return_value = {'state': 'error', 'frames_processed': 330,
                                        'frames_total': 515, 'error': 'MemoryError'}
            with patch.object(validator, '__file__', str(script)), \
                    patch.object(sys, 'argv', [str(script), str(video), '--label', 'failed']), \
                    patch.object(validator.requests, 'get', side_effect=[health, status]), \
                    patch.object(validator.requests, 'post', return_value=failure) as post:
                with self.assertRaises(requests.HTTPError):
                    validator.main()
            output = root / 'diagnostics/api-runs/failed'
            evidence = json.loads((output / 'failure.json').read_text())
            self.assertEqual(evidence['status'], 'failed')
            self.assertEqual(evidence['http_status'], 500)
            self.assertEqual(evidence['last_api_status']['frames_processed'], 330)
            self.assertEqual((output / 'response.json').read_text(), 'Internal Server Error')
            self.assertFalse((output / 'summary.json').exists())
            self.assertEqual(post.call_count, 1)  # No cancellation or retry sent.


if __name__ == '__main__':
    unittest.main()

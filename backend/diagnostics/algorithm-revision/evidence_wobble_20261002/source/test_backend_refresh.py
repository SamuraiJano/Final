"""The backend refresh handshake must not interrupt an active inference run."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main


class BackendRefreshTests(unittest.TestCase):
    def setUp(self):
        self.token = patch.dict("os.environ", {"FRUIT_REFRESH_TOKEN": "test-token"})
        self.token.start()

    def tearDown(self):
        main.cancel_backend_refresh("test-token")
        self.token.stop()

    def test_refresh_requires_launcher_token(self):
        with self.assertRaises(HTTPException) as raised:
            main.prepare_backend_refresh("wrong-token")
        self.assertEqual(raised.exception.status_code, 403)

    def test_active_run_blocks_refresh(self):
        main.analysis_lock.acquire()
        try:
            with self.assertRaises(HTTPException) as raised:
                main.prepare_backend_refresh("test-token")
            self.assertEqual(raised.exception.status_code, 409)
        finally:
            main.analysis_lock.release()

    def test_refresh_reserves_inference_slot_until_cancelled(self):
        self.assertEqual(main.prepare_backend_refresh("test-token"), {"status": "ready"})
        self.assertFalse(main.analysis_lock.acquire(blocking=False))
        self.assertEqual(main.cancel_backend_refresh("test-token"), {"status": "cancelled"})
        self.assertTrue(main.analysis_lock.acquire(blocking=False))
        main.analysis_lock.release()


if __name__ == "__main__":
    unittest.main()

"""Tests that every AI request goes through Kylon. No network, no real key."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_client  # noqa: E402


class KylonClient(unittest.TestCase):

    def setUp(self):
        # Ignore any real .env and any keys set on this computer.
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch("ai_client.ENV_FILE", Path(self.tmp.name) / "missing.env"),
            mock.patch.dict(os.environ, {}, clear=True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_requests_go_to_kylon_proxy(self):
        os.environ["KYLON_API_KEY"] = "test-kylon-key"
        client = ai_client.make_client()
        self.assertEqual(str(client.base_url), "https://api.kylon.io/proxy/anthropic/")

    def test_kylon_key_is_sent_as_x_api_key(self):
        os.environ["KYLON_API_KEY"] = "test-kylon-key"
        self.assertEqual(ai_client.make_client().auth_headers,
                         {"X-Api-Key": "test-kylon-key"})

    def test_other_anthropic_credentials_are_never_sent(self):
        os.environ.update({
            "KYLON_API_KEY": "test-kylon-key",
            "ANTHROPIC_API_KEY": "should-not-be-used",
            "ANTHROPIC_AUTH_TOKEN": "should-not-be-used-either",
            "ANTHROPIC_BASE_URL": "https://somewhere-else.example",
        })
        client = ai_client.make_client()
        self.assertEqual(client.auth_headers, {"X-Api-Key": "test-kylon-key"})
        self.assertIn("api.kylon.io", str(client.base_url))

    def test_base_url_can_be_changed_in_env(self):
        os.environ.update({"KYLON_API_KEY": "k", "KYLON_BASE_URL": "https://test.kylon.io/p"})
        self.assertEqual(str(ai_client.make_client().base_url), "https://test.kylon.io/p/")

    def test_missing_key_gives_friendly_message(self):
        with self.assertRaises(SystemExit) as stop:
            ai_client.make_client()
        self.assertIn("KYLON_API_KEY", str(stop.exception))
        self.assertIn("--use-sample", str(stop.exception))

    def test_model_defaults_and_can_be_changed(self):
        self.assertEqual(ai_client.model_name(), "claude-opus-5-5")
        os.environ["CLAUDE_MODEL"] = "some-other-model"
        self.assertEqual(ai_client.model_name(), "some-other-model")


if __name__ == "__main__":
    unittest.main()

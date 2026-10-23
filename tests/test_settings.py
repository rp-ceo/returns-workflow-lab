import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from settings import load_local_env


class LocalSettingsTests(unittest.TestCase):
    def test_local_settings_never_execute_commands_or_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            marker = Path(directory) / "unexpected"
            path.write_text(
                'OPENAI_API_KEY=sk-test-local\nOPENAI_MODEL="model-local"\nUNRELATED=$(touch '
                + str(marker)
                + ")\n"
            )
            with patch.dict(
                os.environ, {"OPENAI_MODEL": "model-environment"}, clear=True
            ):
                load_local_env(path)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-test-local")
                self.assertEqual(os.environ["OPENAI_MODEL"], "model-environment")
                self.assertNotIn("UNRELATED", os.environ)
            self.assertFalse(marker.exists())

    def test_invalid_key_message_does_not_reveal_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.local"
            path.write_text("OPENAI_API_KEY=not-a-key-private-value\n")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError) as failure:
                    load_local_env(path)
            self.assertNotIn("private-value", str(failure.exception))

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from src.shared.dotenv import _parse_env_line, load_dotenv_from_repo


class DotenvLoaderTests(TestCase):
    def test_parse_env_line_handles_comments_exports_and_quotes(self) -> None:
        self.assertIsNone(_parse_env_line(""))
        self.assertIsNone(_parse_env_line("# comment"))
        self.assertEqual(_parse_env_line("export KEY=value"), ("KEY", "value"))
        self.assertEqual(_parse_env_line('NAME="demo value"'), ("NAME", "demo value"))
        self.assertEqual(_parse_env_line("RAW=abc=123"), ("RAW", "abc=123"))

    def test_load_dotenv_from_repo_respects_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# sample",
                        "EXISTING=from_file",
                        "NEW_VALUE=loaded",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"EXISTING": "keep"}, clear=False):
                loaded = load_dotenv_from_repo(env_path)
                self.assertTrue(loaded)
                self.assertEqual(os.environ["EXISTING"], "keep")
                self.assertEqual(os.environ["NEW_VALUE"], "loaded")

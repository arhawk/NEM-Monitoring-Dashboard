from __future__ import annotations

from unittest import TestCase

import pytest

from src.publisher.qc.runner import run_validate
from src.publisher.qc.rules import MART_PATH, STAGING_CONSOLIDATED_PATH


@pytest.mark.integration
class QcIntegrationTests(TestCase):
    def test_tracked_data_validate_passes_or_warns_only(self) -> None:
        if not MART_PATH.exists() or not STAGING_CONSOLIDATED_PATH.exists():
            self.skipTest("Tracked mart/staging artifacts are not available.")
        exit_code = run_validate(write_reports=False)
        self.assertEqual(exit_code, 0)

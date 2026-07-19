from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import pandas as pd

from src.publisher.data.cleaning import clean_consolidated_data


class CleanConsolidatedDataTests(TestCase):
    def test_clean_consolidated_data_preserves_facility_code(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "raw.csv"
            output_path = root / "clean.csv"
            pd.DataFrame(
                [
                    {
                        "timestamp": "2025-10-25 00:00:00+11:00",
                        "facility_code": "ADP",
                        "Power (MW)": 1.0,
                        "Emissions (tonnes)": 0.0,
                        "Price ($/MWh)": 100.0,
                        "Demand (MW)": 20000.0,
                    },
                    {
                        "timestamp": "2025-10-25 00:05:00+11:00",
                        "facility_code": "ADP",
                        "Power (MW)": pd.NA,
                        "Emissions (tonnes)": pd.NA,
                        "Price ($/MWh)": 101.0,
                        "Demand (MW)": 20010.0,
                    },
                ]
            ).to_csv(input_path, index=False)

            cleaned = clean_consolidated_data(input_path, output_path)

        self.assertIn("facility_code", cleaned.columns)
        self.assertEqual(cleaned["facility_code"].iloc[0], "ADP")

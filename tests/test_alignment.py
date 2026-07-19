from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import pandas as pd

from src.publisher.data.alignment import (
    build_facility_metadata,
    build_publish_dataset,
    find_nger_candidates,
    infer_state_from_coords,
    score_name_similarity,
    select_best_nger_match,
)


class AlignmentHelperTests(TestCase):
    def test_infer_state_from_coords_murray_is_nsw(self) -> None:
        self.assertEqual(infer_state_from_coords(-36.24683, 148.1902), "NSW")

    def test_score_name_similarity_prefers_close_names(self) -> None:
        close = score_name_similarity("Poatina", "Poatina Hydro Power Station")
        far = score_name_similarity("Murray", "Imangara (Murray Downs)")
        self.assertGreater(close, far)

    def test_murray_rejects_weak_short_name_nger_matches(self) -> None:
        oe_row = pd.Series(
            {
                "facility_code": "MURRAY",
                "facility_name": "Murray",
                "lat": -36.24683,
                "lng": 148.1902,
            }
        )
        nger_df = pd.DataFrame(
            [
                {
                    "facilityName": "Imangara (Murray Downs)",
                    "state": "NT",
                    "primaryFuel": "Diesel",
                },
                {
                    "facilityName": "Murray Island Remote Generation",
                    "state": "QLD",
                    "primaryFuel": "Diesel",
                },
            ]
        )
        candidates = find_nger_candidates(oe_row, nger_df)
        self.assertEqual(len(candidates), 2)
        self.assertIsNone(select_best_nger_match(oe_row, candidates))

    def test_same_state_multiple_candidates_picks_best_similarity(self) -> None:
        oe_row = pd.Series(
            {
                "facility_code": "HUMEV",
                "facility_name": "Hume",
                "lat": -36.104,
                "lng": 147.984,
            }
        )
        nger_df = pd.DataFrame(
            [
                {"facilityName": "Hume Power Station", "state": "NSW", "primaryFuel": "Hydro"},
                {"facilityName": "Hume Hydro", "state": "NSW", "primaryFuel": "Hydro"},
                {"facilityName": "Unrelated Facility", "state": "VIC", "primaryFuel": "Gas"},
            ]
        )
        candidates = find_nger_candidates(oe_row, nger_df)
        best = select_best_nger_match(oe_row, candidates)
        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(best["facilityName"], "Hume Power Station")
        self.assertEqual(best["state"], "NSW")


class BuildFacilityMetadataTests(TestCase):
    def test_unmatched_nger_still_keeps_facility_with_inferred_state(self) -> None:
        oe_df = pd.DataFrame(
            [
                {
                    "facility_code": "ADP",
                    "facility_name": "Adelaide Desalination",
                    "lat": -35.096948,
                    "lng": 138.484061,
                }
            ]
        )
        nger_df = pd.DataFrame(columns=["facilityName", "state", "primaryFuel"])
        cer_df = pd.DataFrame(columns=["powerStation", "state", "fuelSource"])

        grouped = build_facility_metadata(oe_df, nger_df, cer_df)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped.iloc[0]["facility_code"], "ADP")
        self.assertEqual(grouped.iloc[0]["state"], "SA")
        self.assertEqual(grouped.iloc[0]["fuel_list"], [])

    def test_murray_metadata_uses_inferred_nsw_without_nger(self) -> None:
        oe_df = pd.DataFrame(
            [
                {
                    "facility_code": "MURRAY",
                    "facility_name": "Murray",
                    "lat": -36.24683,
                    "lng": 148.1902,
                }
            ]
        )
        nger_df = pd.DataFrame(
            [
                {
                    "facilityName": "Imangara (Murray Downs)",
                    "state": "NT",
                    "primaryFuel": "Diesel",
                },
                {
                    "facilityName": "Murray Island Remote Generation",
                    "state": "QLD",
                    "primaryFuel": "Diesel",
                },
            ]
        )
        cer_df = pd.DataFrame(columns=["powerStation", "state", "fuelSource"])

        grouped = build_facility_metadata(oe_df, nger_df, cer_df)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped.iloc[0]["state"], "NSW")
        self.assertEqual(grouped.iloc[0]["fuel_list"], [])


class BuildPublishDatasetTests(TestCase):
    def test_build_publish_dataset_keeps_unmatched_nger_and_unique_pk(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cleaned_path = root / "consolidated_data_cleaned.csv"
            facility_list_path = root / "facility_list_clean.csv"
            nger_path = root / "NGER_data_clean.csv"
            cer_path = root / "CER_data_clean.csv"
            output_path = root / "data_for_publish.csv"

            pd.DataFrame(
                [
                    {
                        "timestamp": "2025-10-25 00:00:00+11:00",
                        "Price ($/MWh)": 100.0,
                        "Demand (MW)": 20000.0,
                        "facility_code": "MURRAY",
                        "Power (MW)": 10.0,
                        "Emissions (tonnes)": 0.0,
                    },
                    {
                        "timestamp": "2025-10-25 00:00:00+11:00",
                        "Price ($/MWh)": 100.0,
                        "Demand (MW)": 20000.0,
                        "facility_code": "ADP",
                        "Power (MW)": 5.0,
                        "Emissions (tonnes)": 0.0,
                    },
                ]
            ).to_csv(cleaned_path, index=False)
            pd.DataFrame(
                [
                    {
                        "facility_code": "MURRAY",
                        "facility_name": "Murray",
                        "lat": -36.24683,
                        "lng": 148.1902,
                    },
                    {
                        "facility_code": "ADP",
                        "facility_name": "Adelaide Desalination",
                        "lat": -35.096948,
                        "lng": 138.484061,
                    },
                ]
            ).to_csv(facility_list_path, index=False)
            pd.DataFrame(
                [
                    {
                        "facilityName": "Imangara (Murray Downs)",
                        "state": "NT",
                        "primaryFuel": "Diesel",
                    },
                    {
                        "facilityName": "Murray Island Remote Generation",
                        "state": "QLD",
                        "primaryFuel": "Diesel",
                    },
                ]
            ).to_csv(nger_path, index=False)
            pd.DataFrame(columns=["powerStation", "state", "fuelSource"]).to_csv(
                cer_path, index=False
            )

            merged = build_publish_dataset(
                cleaned_path,
                facility_list_path,
                nger_path,
                cer_path,
                output_path,
            )

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged["facility_code"].nunique(), 2)
        self.assertFalse(merged.duplicated(subset=["facility_code", "timestamp"]).any())

        murray = merged.loc[merged["facility_code"] == "MURRAY"].iloc[0]
        adp = merged.loc[merged["facility_code"] == "ADP"].iloc[0]
        self.assertEqual(murray["state"], "NSW")
        self.assertEqual(adp["state"], "SA")

from __future__ import annotations

from datetime import datetime

from .data import build_publish_dataset, clean_consolidated_data
from .fetch import fetch_and_build_consolidated_data
from .publish import MEASURE_CSV, run_publisher_loop
from src.shared.paths import data_path


RAW_CONSOLIDATED_PATH = data_path("consolidated_data_total.csv")
CLEANED_PATH = data_path("consolidated_data_cleaned.csv")
PUBLISH_PATH = MEASURE_CSV
FACILITY_LIST_PATH = data_path("facility_list.csv")
NGER_PATH = data_path("NGER_data_aug.csv")
CER_PATH = data_path("CER_data_aug.csv")


def prepare_data_artifacts() -> None:
    if not RAW_CONSOLIDATED_PATH.exists() or not FACILITY_LIST_PATH.exists():
        fetch_and_build_consolidated_data(
            date_start=datetime(2025, 10, 24, 23, 0, 0),
            date_end=datetime(2025, 10, 31, 22, 59, 59),
        )

    clean_consolidated_data(RAW_CONSOLIDATED_PATH, CLEANED_PATH)
    build_publish_dataset(CLEANED_PATH, FACILITY_LIST_PATH, NGER_PATH, CER_PATH, PUBLISH_PATH)


def main() -> None:
    if not PUBLISH_PATH.exists():
        prepare_data_artifacts()
    run_publisher_loop(PUBLISH_PATH)


if __name__ == "__main__":
    main()

from __future__ import annotations

import pandas as pd

from .data import (
    build_publish_dataset,
    clean_facility_metadata_artifacts,
    clean_consolidated_data,
    clean_facility_list,
    fetch_and_clean_facility_metadata_artifacts,
)
from .fetch import fetch_and_build_consolidated_data
from .publish import run_publisher_loop
from src.shared.config import get_fetch_date_end, get_fetch_date_start
from src.shared.paths import mart_data_path, raw_data_path, staging_data_path


RAW_OE_DIR = raw_data_path("open_electricity")
RAW_CONSOLIDATED_PATH = RAW_OE_DIR / "consolidated_data_total.csv"
RAW_FACILITY_LIST_PATH = RAW_OE_DIR / "facility_list.csv"
STAGING_OE_DIR = staging_data_path("open_electricity")
STAGING_CONSOLIDATED_PATH = STAGING_OE_DIR / "consolidated_data_cleaned.csv"
STAGING_FACILITY_LIST_PATH = STAGING_OE_DIR / "facility_list_clean.csv"
PUBLISH_PATH = mart_data_path("data_for_publish.csv")
FACILITY_METADATA_STAGING_DIR = staging_data_path("facility_metadata")
NGER_PATH = FACILITY_METADATA_STAGING_DIR / "NGER_data_clean.csv"
CER_PATH = FACILITY_METADATA_STAGING_DIR / "CER_data_clean.csv"


def prepare_data_artifacts() -> None:
    if not NGER_PATH.exists() or not CER_PATH.exists():
        fetch_and_clean_facility_metadata_artifacts()
    else:
        clean_facility_metadata_artifacts()

    if not RAW_CONSOLIDATED_PATH.exists() or not RAW_FACILITY_LIST_PATH.exists():
        fetch_and_build_consolidated_data(
            date_start=get_fetch_date_start(),
            date_end=get_fetch_date_end(),
        )

    STAGING_FACILITY_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean_facility_list(pd.read_csv(RAW_FACILITY_LIST_PATH)).to_csv(
        STAGING_FACILITY_LIST_PATH, index=False
    )
    clean_consolidated_data(RAW_CONSOLIDATED_PATH, STAGING_CONSOLIDATED_PATH)
    build_publish_dataset(
        STAGING_CONSOLIDATED_PATH,
        STAGING_FACILITY_LIST_PATH,
        NGER_PATH,
        CER_PATH,
        PUBLISH_PATH,
    )


def main() -> None:
    if not PUBLISH_PATH.exists():
        prepare_data_artifacts()
    run_publisher_loop(PUBLISH_PATH)


if __name__ == "__main__":
    main()

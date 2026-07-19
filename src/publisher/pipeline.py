from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import pandas as pd

from src.publisher.qc.runner import run_validate
from src.shared.config import get_fetch_date_end, get_fetch_date_start
from src.shared.paths import mart_data_path, raw_data_path, staging_data_path

from .data import (
    build_publish_dataset,
    clean_facility_metadata_artifacts,
    clean_consolidated_data,
    clean_facility_list,
    fetch_and_clean_facility_metadata_artifacts,
)
from .fetch import fetch_and_build_consolidated_data
from .publish import run_publisher_loop


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

STAGE_ORDER = ("fetch", "stage", "mart", "validate", "publish")


@dataclass
class PipelineOptions:
    through: str = "validate"
    force_fetch: bool = False
    force_rebuild: bool = False
    with_publish: bool = False


def run_fetch(*, force_fetch: bool = False) -> None:
    if force_fetch or not NGER_PATH.exists() or not CER_PATH.exists():
        fetch_and_clean_facility_metadata_artifacts()
    elif not force_fetch:
        clean_facility_metadata_artifacts()

    if (
        force_fetch
        or not RAW_CONSOLIDATED_PATH.exists()
        or not RAW_FACILITY_LIST_PATH.exists()
    ):
        fetch_and_build_consolidated_data(
            date_start=get_fetch_date_start(),
            date_end=get_fetch_date_end(),
        )


def run_stage(*, force_rebuild: bool = False) -> None:
    if not RAW_FACILITY_LIST_PATH.exists() or not RAW_CONSOLIDATED_PATH.exists():
        raise FileNotFoundError(
            "Raw Open Electricity artifacts are missing. Run the fetch stage first."
        )

    raw_nger = raw_data_path("facility_metadata", "NGER_data.csv")
    raw_cer = raw_data_path("facility_metadata", "CER_data.csv")
    if force_rebuild or not NGER_PATH.exists() or not CER_PATH.exists():
        if raw_nger.exists() and raw_cer.exists():
            clean_facility_metadata_artifacts()
        else:
            fetch_and_clean_facility_metadata_artifacts()

    STAGING_FACILITY_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean_facility_list(pd.read_csv(RAW_FACILITY_LIST_PATH)).to_csv(
        STAGING_FACILITY_LIST_PATH, index=False
    )
    clean_consolidated_data(RAW_CONSOLIDATED_PATH, STAGING_CONSOLIDATED_PATH)


def run_mart(*, force_rebuild: bool = False) -> None:
    if not force_rebuild and PUBLISH_PATH.exists():
        return
    if (
        not STAGING_CONSOLIDATED_PATH.exists()
        or not STAGING_FACILITY_LIST_PATH.exists()
    ):
        raise FileNotFoundError(
            "Staging artifacts are missing. Run the stage step first."
        )
    if not NGER_PATH.exists() or not CER_PATH.exists():
        raise FileNotFoundError(
            "Staged metadata artifacts are missing. Run the stage step first."
        )
    build_publish_dataset(
        STAGING_CONSOLIDATED_PATH,
        STAGING_FACILITY_LIST_PATH,
        NGER_PATH,
        CER_PATH,
        PUBLISH_PATH,
    )


def run_publish() -> None:
    if not PUBLISH_PATH.exists():
        raise FileNotFoundError(
            f"Publish artifact not found at {PUBLISH_PATH}. Run mart/validate first."
        )
    run_publisher_loop(PUBLISH_PATH)


def prepare_data_artifacts(
    *, force_fetch: bool = False, force_rebuild: bool = False
) -> None:
    run_fetch(force_fetch=force_fetch)
    run_stage(force_rebuild=force_rebuild)
    run_mart(force_rebuild=force_rebuild)


def run_pipeline(options: PipelineOptions) -> int:
    stages = list(STAGE_ORDER)
    through = options.through
    if options.with_publish:
        through = "publish"
    if through not in stages:
        raise ValueError(f"Unknown stage: {through}")

    last_index = stages.index(through)
    selected = stages[: last_index + 1]

    if "fetch" in selected:
        run_fetch(force_fetch=options.force_fetch)
    if "stage" in selected:
        run_stage(force_rebuild=options.force_rebuild)
    if "mart" in selected:
        run_mart(force_rebuild=options.force_rebuild or "mart" in selected)
    if "validate" in selected:
        exit_code = run_validate()
        if exit_code != 0:
            return exit_code
    if "publish" in selected:
        run_publish()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NEM data pipeline stages.")
    parser.add_argument(
        "--through",
        choices=STAGE_ORDER,
        default="validate",
        help="Run pipeline through this stage (default: validate).",
    )
    parser.add_argument(
        "--with-publish",
        action="store_true",
        help="Run through publish after validate passes.",
    )
    parser.add_argument(
        "--force-fetch",
        action="store_true",
        help="Re-fetch raw artifacts even when cached raw files exist.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild staged and mart artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    options = PipelineOptions(
        through=args.through,
        force_fetch=args.force_fetch,
        force_rebuild=args.force_rebuild,
        with_publish=args.with_publish,
    )
    return run_pipeline(options)


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from src.shared.paths import data_path, repo_path


def clean_nger_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the Assignment 1 NGER cleaning rules."""
    cleaned = df.copy()
    cleaned = cleaned[cleaned["facilityName"].notna()]
    cleaned = cleaned[cleaned["importantNotes"].isna()]

    drop_columns = [
        column
        for column in ("reportingEntity", "importantNotes", "electricityProductionGJ", "gridConnected", "grid")
        if column in cleaned.columns
    ]
    if drop_columns:
        cleaned = cleaned.drop(columns=drop_columns)

    cleaned = cleaned[cleaned["type"] != "C"]
    return cleaned.reset_index(drop=True)


def clean_cer_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the Assignment 1 CER cleaning rules."""
    cleaned = df.copy()
    cleaned["powerStation"] = cleaned["powerStation"].astype("string").str.split("-", n=1).str[0].str.strip()

    if "postcode" in cleaned.columns:
        cleaned["postcode"] = cleaned["postcode"].astype("Int64")

    if "Approval date" in cleaned.columns:
        cleaned.loc[cleaned["inSheet"] == "Approved", "year"] = (
            cleaned["Approval date"].astype("string").str.split("-", n=1).str[0].astype("Int64")
        )
    if "Committed Date (Month/Year)" in cleaned.columns:
        cleaned.loc[cleaned["inSheet"] == "Committed", "year"] = (
            cleaned["Committed Date (Month/Year)"].astype("string").str.split("-", n=1).str[0].astype("Int64")
        )

    keep_columns = list(cleaned.columns[:5]) + [cleaned.columns[-1]]
    cleaned = cleaned.loc[:, keep_columns]
    return cleaned.reset_index(drop=True)


def clean_assignment1_artifacts(
    source_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Read raw Assignment 1 CSVs, clean them, and write the clean outputs."""
    source_dir = Path(source_dir) if source_dir is not None else Path(os.getenv("ASSIGNMENT1_DATA_DIR", data_path()))
    output_dir = Path(output_dir) if output_dir is not None else data_path()

    nger_raw_path = source_dir / "NGER_data.csv"
    cer_raw_path = source_dir / "CER_data.csv"
    if not nger_raw_path.exists() or not cer_raw_path.exists():
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)

    nger_clean = clean_nger_data(pd.read_csv(nger_raw_path))
    cer_clean = clean_cer_data(pd.read_csv(cer_raw_path))

    nger_clean.to_csv(output_dir / "NGER_data_clean.csv", index=False, encoding="utf-8-sig")
    cer_clean.to_csv(output_dir / "CER_data_clean.csv", index=False, encoding="utf-8-sig")

    return {
        "nger": nger_clean,
        "cer": cer_clean,
    }


def load_assignment1_csv(path: str | Path) -> pd.DataFrame:
    """
    Load the preferred clean Assignment 1 CSV, falling back to the legacy
    augmented artifact stored under backup/data when the clean file is absent.
    """
    path = Path(path)
    if path.exists():
        return pd.read_csv(path)

    legacy_name = path.name.replace("_clean", "_aug")
    legacy_path = repo_path("backup", "data", legacy_name)
    if legacy_path.exists():
        return pd.read_csv(legacy_path)

    raise FileNotFoundError(f"Could not find {path} or legacy fallback {legacy_path}")


__all__ = [
    "clean_assignment1_artifacts",
    "clean_cer_data",
    "clean_nger_data",
    "load_assignment1_csv",
]

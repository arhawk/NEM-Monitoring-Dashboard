from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    class _MissingRequests:
        class exceptions:  # type: ignore[valid-type]
            HTTPError = RuntimeError

        def get(self, *args, **kwargs):
            raise ModuleNotFoundError("requests is required for Assignment 1 fetches")

    requests = _MissingRequests()

from src.shared.paths import raw_data_path, staging_data_path


NGER_API_URLS = [
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0075?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0076?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0077?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0078?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0079?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0080?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0081?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0082?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0083?select%3D%2A",
    "https://api.cer.gov.au/datahub-public/v1/api/ODataDataset/NGER/dataset/ID0243?select%3D%2A",
]

CER_XLSX_URL = "https://cer.gov.au/document/power-stations-and-projects-status"


def clean_nger_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the Assignment 1 NGER cleaning rules."""
    cleaned = df.copy()
    if "facilityName" in cleaned.columns:
        cleaned["facilityName"] = cleaned["facilityName"].astype("string").str.strip()
    if "type" in cleaned.columns:
        cleaned["type"] = cleaned["type"].astype("string").str.strip()
    if "importantNotes" in cleaned.columns:
        cleaned["importantNotes"] = cleaned["importantNotes"].replace({"N/A": pd.NA, "-": pd.NA})
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
    return cleaned.drop_duplicates().reset_index(drop=True)


def clean_cer_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the Assignment 1 CER cleaning rules."""
    cleaned = df.copy()
    cleaned["powerStation"] = cleaned["powerStation"].astype("string").str.split("-", n=1).str[0].str.strip()
    if "state" in cleaned.columns:
        cleaned["state"] = cleaned["state"].astype("string").str.strip()
    if "fuelSource" in cleaned.columns:
        cleaned["fuelSource"] = cleaned["fuelSource"].astype("string").str.strip()

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
    return cleaned.drop_duplicates().reset_index(drop=True)


def fetch_nger_raw_data(output_dir: str | Path | None = None) -> pd.DataFrame:
    """Download the remote NGER source datasets and write data/NGER_data.csv."""
    output_dir = Path(output_dir) if output_dir is not None else raw_data_path("assignment1")
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    standard_columns: list[str] | None = None

    for year_offset, api_url in enumerate(NGER_API_URLS):
        response = requests.get(api_url, timeout=120)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        df["year"] = 2015 + year_offset

        if standard_columns is None:
            standard_columns = df.columns.tolist()
        else:
            df = df.reindex(columns=standard_columns, fill_value=pd.NA)
        records.extend(df.to_dict("records"))

    combined = pd.DataFrame.from_records(records)
    combined = combined.replace({"-": None, "N/A": None})
    combined.to_csv(output_dir / "NGER_data.csv", index=False, encoding="utf-8-sig")
    return combined


def fetch_cer_raw_data(output_dir: str | Path | None = None) -> pd.DataFrame:
    """Download the remote CER XLSX and write data/CER_data.csv."""
    output_dir = Path(output_dir) if output_dir is not None else raw_data_path("assignment1")
    output_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(CER_XLSX_URL, timeout=120)
    response.raise_for_status()
    workbook = BytesIO(response.content)

    approved_df = pd.read_excel(
        workbook,
        sheet_name=0,
        skiprows=3,
        skipfooter=1,
    ).iloc[:, 1:]
    approved_df["inSheet"] = "Approved"

    workbook.seek(0)
    committed_df = pd.read_excel(
        workbook,
        sheet_name=1,
        skiprows=3,
        skipfooter=1,
    )
    committed_df["inSheet"] = "Committed"

    workbook.seek(0)
    probable_df = pd.read_excel(
        workbook,
        sheet_name=2,
        skiprows=3,
        skipfooter=1,
    )
    probable_df["inSheet"] = "Probable"

    approved_df.columns = ["powerStation", "state", "postcode", "MWCapacity", "fuelSource"] + approved_df.columns.tolist()[5:]
    committed_df.columns = ["powerStation", "state", "MWCapacity", "fuelSource"] + committed_df.columns.tolist()[4:]
    probable_df.columns = ["powerStation", "state", "MWCapacity", "fuelSource"] + probable_df.columns.tolist()[4:]

    combined = pd.concat([approved_df, committed_df, probable_df], ignore_index=True)
    combined.to_csv(output_dir / "CER_data.csv", index=False, encoding="utf-8-sig")
    return combined


def clean_assignment1_artifacts(
    source_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Read raw Assignment 1 CSVs, clean them, and write the clean outputs."""
    default_source_dir = raw_data_path("assignment1")
    default_output_dir = staging_data_path("assignment1")
    source_dir = Path(source_dir) if source_dir is not None else Path(os.getenv("ASSIGNMENT1_DATA_DIR", default_source_dir))
    output_dir = Path(output_dir) if output_dir is not None else default_output_dir

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


def fetch_and_clean_assignment1_artifacts(output_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Fetch the remote Assignment 1 source files, then clean them into CSV artifacts."""
    raw_output_dir = Path(output_dir) if output_dir is not None else raw_data_path("assignment1")
    staging_output_dir = staging_data_path("assignment1")
    nger_raw = fetch_nger_raw_data(output_dir=raw_output_dir)
    cer_raw = fetch_cer_raw_data(output_dir=raw_output_dir)
    nger_clean = clean_nger_data(nger_raw)
    cer_clean = clean_cer_data(cer_raw)
    staging_output_dir.mkdir(parents=True, exist_ok=True)
    nger_clean.to_csv(staging_output_dir / "NGER_data_clean.csv", index=False, encoding="utf-8-sig")
    cer_clean.to_csv(staging_output_dir / "CER_data_clean.csv", index=False, encoding="utf-8-sig")
    return {
        "nger_raw": nger_raw,
        "cer_raw": cer_raw,
        "nger": nger_clean,
        "cer": cer_clean,
    }


def load_assignment1_csv(path: str | Path) -> pd.DataFrame:
    """
    Load the staged Assignment 1 CSV, falling back to the staged layer mirror
    when callers still pass an equivalent clean filename.
    """
    path = Path(path)
    if path.exists():
        return pd.read_csv(path)

    staged_path = staging_data_path("assignment1", path.name)
    if staged_path.exists():
        return pd.read_csv(staged_path)

    raise FileNotFoundError(f"Could not find {path} or staged fallback {staged_path}")


__all__ = [
    "clean_assignment1_artifacts",
    "clean_cer_data",
    "fetch_and_clean_assignment1_artifacts",
    "fetch_cer_raw_data",
    "fetch_nger_raw_data",
    "clean_nger_data",
    "load_assignment1_csv",
]

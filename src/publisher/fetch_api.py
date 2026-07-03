from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import StringIO
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytz
import requests

from .paths import data_path


CACHE_FILE = data_path("facility_data_cache.json")
cache_lock = threading.Lock()


def get_api_key() -> str:
    """Read the Open Electricity API key only when remote fetches are needed."""
    api_key = os.getenv("OPEN_ELECTRICITY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPEN_ELECTRICITY_API_KEY is required to fetch data from the Open Electricity API."
        )
    return api_key


def load_cache() -> dict[str, dict[str, Any]]:
    """Load cached data from JSON file and restore datetime/DataFrame objects."""
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            for key, value in data.items():
                parts = key.split("|")
                if len(parts) != 4:
                    print(f"Invalid cache key: {key}, skipped")
                    continue
                value["date_start"] = datetime.fromisoformat(value["date_start"])
                value["date_end"] = datetime.fromisoformat(value["date_end"])
                consolidated_io = StringIO(value["consolidated_data"])
                value["consolidated_data"] = pd.read_json(consolidated_io, orient="split")
            return data
    except FileNotFoundError:
        return {}


def save_cache(cache: dict[str, dict[str, Any]]) -> None:
    """Save cache to JSON (thread-safe), converting non-serializable objects first."""
    with cache_lock:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable_cache: dict[str, dict[str, Any]] = {}
        for key, value in cache.items():
            serializable_cache[key] = {
                "date_start": value["date_start"].isoformat(),
                "date_end": value["date_end"].isoformat(),
                "consolidated_data": value["consolidated_data"].to_json(orient="split"),
            }
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(serializable_cache, f, indent=2)


def create_session() -> requests.Session:
    """Create a reusable HTTP session to reduce connection overhead."""
    session = requests.Session()
    session.headers = {"Authorization": f"Bearer {get_api_key()}"}
    return session


def fetch_response(session: requests.Session, api: str, params: dict[str, Any] | None = None):
    """Fetch HTTP response with error handling."""
    try:
        response = session.get(api, params=params)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as errh:
        if errh.response.status_code == 416:
            return None
    except Exception as err:
        print(f"Request error: {err}")
        return None


def fetch_facility_list() -> pd.DataFrame:
    """Retrieve list of facilities from API (filtered by network 'NEM')."""
    session = create_session()
    params = {"network_id": "NEM"}
    api = "https://api.openelectricity.org.au/v4/facilities/"
    response = fetch_response(session, api, params)
    session.close()

    if not response:
        return pd.DataFrame()

    rows = []
    for facility in response.json()["data"]:
        row = {
            "facility_code": facility["code"],
            "facility_name": facility["name"],
        }
        if "location" in facility:
            row["lat"] = facility["location"]["lat"]
            row["lng"] = facility["location"]["lng"]
        rows.append(row)
    return pd.DataFrame(rows)


def _get_data(response, data_type: str) -> pd.DataFrame:
    """Parse raw API response into structured DataFrame for a specific metric type."""
    rows = []
    data_dict = {"power": 0, "emissions": 1, "price": 0, "demand": 1}
    sydney_tz = pytz.timezone("Australia/Sydney")

    try:
        json_data = response.json()
        for unit in json_data["data"][data_dict[data_type]]["results"]:
            for time_slot in unit["data"]:
                ts_raw, value = time_slot
                ts_datetime = None

                if isinstance(ts_raw, (int, float)):
                    ts_datetime = datetime.fromtimestamp(ts_raw / 1000, tz=sydney_tz)
                else:
                    ts_parsed = datetime.fromisoformat(ts_raw)
                    if ts_parsed.tzinfo is None:
                        ts_datetime = sydney_tz.localize(ts_parsed, is_dst=None)
                    else:
                        ts_datetime = ts_parsed.astimezone(sydney_tz)

                rows.append(
                    {
                        "code": unit["name"],
                        "timestamp": ts_datetime.isoformat(),
                        "value": value,
                    }
                )

        data = pd.DataFrame(rows)
        data["timestamp"] = pd.to_datetime(data["timestamp"], format="ISO8601", utc=False)
        return data.groupby("timestamp")["value"].sum().reset_index()
    except Exception as e:
        print(f"Data parsing error: {e}")
        return pd.DataFrame()


def _get_params(response) -> tuple[str, str]:
    """Extract metric parameters from the request URL."""
    parsed_url = urlparse(response.request.url)
    request_params = parse_qs(parsed_url.query)
    return request_params["metrics"][0], request_params["metrics"][1]


def fetch_data(response, facility_code: str) -> pd.DataFrame:
    """Merge two metric datasets (e.g., power + emissions) for a facility."""
    if response is None:
        return pd.DataFrame()

    colnames = {
        "power": "Power (MW)",
        "emissions": "Emissions (tonnes)",
        "price": "Price ($/MWh)",
        "demand": "Demand (MW)",
    }

    col1, col2 = _get_params(response)
    data1 = _get_data(response, col1)
    data2 = _get_data(response, col2)

    data1.rename(columns={"value": colnames[col1]}, inplace=True)
    data2.rename(columns={"value": colnames[col2]}, inplace=True)
    consolidated_data = pd.merge(data1, data2, on="timestamp", how="outer")
    consolidated_data["facility_code"] = facility_code
    return consolidated_data


def process_facility(f_code: str, date_start: datetime, date_end: datetime, cache: dict[str, Any]) -> pd.DataFrame:
    """Process data for a single facility (thread-safe), using cache when possible."""
    print(f"Processing facility: {f_code}")
    data_sources = {
        "facility": {
            "api_url": "https://api.openelectricity.org.au/v4/data/facilities/NEM",
            "metrics": ["power", "emissions"],
        },
        "market": {
            "api_url": "https://api.openelectricity.org.au/v4/market/network/NEM",
            "metrics": ["price", "demand"],
        },
    }

    source_data: dict[str, pd.DataFrame] = {}
    session = create_session()

    try:
        for source_type, config in data_sources.items():
            cache_key = f"{source_type}|{f_code}|{date_start.isoformat()}|{date_end.isoformat()}"

            if cache_key in cache:
                source_data[source_type] = cache[cache_key]["consolidated_data"]
                continue

            params = {
                "facility_code": f_code,
                "metrics": config["metrics"],
                "interval": "5m",
                "date_start": date_start,
                "date_end": date_end,
            }
            response = fetch_response(session, config["api_url"], params)
            source_df = fetch_data(response, f_code)

            if not source_df.empty:
                with cache_lock:
                    cache[cache_key] = {
                        "date_start": date_start,
                        "date_end": date_end,
                        "consolidated_data": source_df,
                    }

            source_data[source_type] = source_df

        facility_df = source_data["facility"]
        market_df = source_data["market"]

        if not facility_df.empty and not market_df.empty:
            merged_df = pd.merge(facility_df, market_df, on=["timestamp", "facility_code"], how="outer")
        elif not facility_df.empty:
            merged_df = facility_df
        elif not market_df.empty:
            merged_df = market_df
        else:
            merged_df = pd.DataFrame()

        return merged_df
    finally:
        session.close()


def fetch_and_build_consolidated_data(
    *,
    date_start: datetime,
    date_end: datetime,
    max_workers: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch all facility data and persist the raw artifacts."""
    cache = load_cache()
    facility_list = fetch_facility_list()
    if facility_list.empty:
        return facility_list, pd.DataFrame()

    all_merged_dfs: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_facility, f_code, date_start, date_end, cache): f_code
            for f_code in facility_list["facility_code"]
        }
        for future in as_completed(futures):
            f_code = futures[future]
            try:
                merged_df = future.result()
                if not merged_df.empty:
                    all_merged_dfs.append(merged_df)
            except Exception as e:
                print(f"Error processing facility {f_code}: {e}")

    consolidated_data = pd.concat(all_merged_dfs, ignore_index=True) if all_merged_dfs else pd.DataFrame()
    save_cache(cache)

    facility_list_path = data_path("facility_list.csv")
    consolidated_path = data_path("consolidated_data_total.csv")
    facility_list_path.parent.mkdir(parents=True, exist_ok=True)
    facility_list.to_csv(facility_list_path, index=False)
    consolidated_data.to_csv(consolidated_path, index=False)
    return facility_list, consolidated_data

from __future__ import annotations

import os
from typing import Any

import pandas as pd
from types import SimpleNamespace

try:
    import requests
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    class _MissingSession:
        def __init__(self, *args, **kwargs):
            self.headers = {}

        def get(self, *args, **kwargs):
            raise ModuleNotFoundError("requests is required for publisher HTTP fetches")

        def close(self) -> None:
            return None

    class _MissingHTTPError(Exception):
        def __init__(self, *args, **kwargs):
            self.response = SimpleNamespace(status_code=0)

    requests = SimpleNamespace(
        Session=_MissingSession,
        exceptions=SimpleNamespace(HTTPError=_MissingHTTPError),
    )


def get_api_key() -> str:
    """Read the Open Electricity API key only when remote fetches are needed."""
    api_key = os.getenv("OPEN_ELECTRICITY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPEN_ELECTRICITY_API_KEY is required to fetch data from the Open Electricity API."
        )
    return api_key


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


__all__ = ["get_api_key", "create_session", "fetch_response", "fetch_facility_list"]

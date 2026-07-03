from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python versions with pytz only
    ZoneInfo = None


def _get_data(response, data_type: str) -> pd.DataFrame:
    """Parse raw API response into structured DataFrame for a specific metric type."""
    rows = []
    data_dict = {"power": 0, "emissions": 1, "price": 0, "demand": 1}
    sydney_tz = ZoneInfo("Australia/Sydney") if ZoneInfo is not None else None

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
                        if sydney_tz is None:
                            ts_datetime = ts_parsed
                        else:
                            ts_datetime = ts_parsed.replace(tzinfo=sydney_tz)
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


__all__ = ["_get_data", "_get_params", "fetch_data"]

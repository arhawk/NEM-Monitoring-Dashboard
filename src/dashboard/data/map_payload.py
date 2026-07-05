from __future__ import annotations

from typing import Any, Dict

from ..settings import FUEL_GROUP_COLORS
from . import _classify_fuel_group, _coerce_float, _signature_metric_value


def _marker_color(fuel_list: Any) -> str:
    if fuel_list in FUEL_GROUP_COLORS:
        return FUEL_GROUP_COLORS[str(fuel_list)]
    return FUEL_GROUP_COLORS[_classify_fuel_group(fuel_list)]


def _marker_radius(info: Dict[str, Any], display_mode: str) -> float:
    value = _signature_metric_value(info.get(display_mode))
    if value is None:
        return 6.0
    return max(5.5, min(16.0, 6.0 + abs(value) ** 0.5))


def _marker_popup_html(info: Dict[str, Any], fac_code: str) -> str:
    import html

    from . import _format_optional_metric

    return " ".join(
        f"""
        <b>{html.escape(str(info.get("facility_name", fac_code)))}</b><br>
        Facility Code: {html.escape(str(fac_code))}<br>
        Region: {html.escape(str(info.get("state", "Unknown Region")))}<br>
        Fuel Group: {html.escape(str(info.get("fuel_group", _classify_fuel_group(info.get("fuel_list")))))}<br>
        Fuel Type: {html.escape(str(info.get("fuel_list", "Unknown")))}<br>
        Last Payload Time: {html.escape(str(info.get("timestamp", "Unknown")))}<br>
        Power Output: {html.escape(_format_optional_metric(info.get("power_value"), "MW"))}<br>
        CO2 Emissions: {html.escape(_format_optional_metric(info.get("emission_value"), "tCO2e"))}<br>
        Current Price: {html.escape(_format_optional_metric(info.get("price_per_mwh"), "$/MWh"))}<br>
        Grid Demand: {html.escape(_format_optional_metric(info.get("demand_mw"), "MW"))}
        """.split()
    )


def _marker_fingerprint(info: Dict[str, Any], display_mode: str) -> tuple:
    return (
        _signature_metric_value(info.get("power_value")),
        _signature_metric_value(info.get("emission_value")),
        _signature_metric_value(info.get("price_per_mwh")),
        _signature_metric_value(info.get("demand_mw")),
        str(info.get("timestamp", "")),
    )


def _build_static_signature(records: Dict[str, Dict[str, Any]]) -> tuple:
    return tuple(
        sorted(
            (
                fac_code,
                round(lat, 5),
                round(lng, 5),
                str(info.get("state", "")),
                str(info.get("fuel_list", "")),
                str(info.get("facility_name", fac_code)),
            )
            for fac_code, info in records.items()
            if (lat := _coerce_float(info.get("lat"))) is not None
            and (lng := _coerce_float(info.get("lng"))) is not None
        )
    )


def _build_operational_signature(records: Dict[str, Dict[str, Any]]) -> tuple:
    return tuple(
        sorted(
            (
                fac_code,
                str(info.get("timestamp", "")),
                _signature_metric_value(info.get("power_value")),
                _signature_metric_value(info.get("emission_value")),
                _signature_metric_value(info.get("price_per_mwh")),
                _signature_metric_value(info.get("demand_mw")),
            )
            for fac_code, info in records.items()
            if _coerce_float(info.get("lat")) is not None
            and _coerce_float(info.get("lng")) is not None
        )
    )


def _build_map_signature(
    records: Dict[str, Dict[str, Any]],
    display_mode: str,
    selected_fuel: str,
    selected_region: str,
) -> tuple:
    return (
        _build_static_signature(records),
        (
            display_mode,
            selected_fuel,
            selected_region,
            _build_operational_signature(records),
        ),
    )


def _build_marker_payload(
    records: Dict[str, Dict[str, Any]],
    display_mode: str,
    selected_fuel: str,
    selected_region: str,
) -> Dict[str, Any]:
    markers = []
    for fac_code, info in sorted(records.items()):
        lat = _coerce_float(info.get("lat"))
        lng = _coerce_float(info.get("lng"))
        if lat is None or lng is None:
            continue
        markers.append(
            {
                "facility_code": fac_code,
                "facility_name": info.get("facility_name", fac_code),
                "lat": lat,
                "lng": lng,
                "fuel_group": info.get("fuel_group")
                or _classify_fuel_group(info.get("fuel_list")),
                "color": _marker_color(info.get("fuel_group") or info.get("fuel_list")),
                "radius": round(_marker_radius(info, display_mode), 2),
                "fingerprint": _marker_fingerprint(info, display_mode),
                "state": info.get("state"),
                "fuel_list": info.get("fuel_list"),
                "timestamp": info.get("timestamp"),
                "power_value": _signature_metric_value(info.get("power_value")),
                "emission_value": _signature_metric_value(info.get("emission_value")),
                "price_per_mwh": _signature_metric_value(info.get("price_per_mwh")),
                "demand_mw": _signature_metric_value(info.get("demand_mw")),
            }
        )

    return {
        "static_signature": _build_static_signature(records),
        "operational_signature": _build_operational_signature(records),
        "display_mode": display_mode,
        "selected_fuel": selected_fuel,
        "selected_region": selected_region,
        "legend": [
            {"label": label, "color": color}
            for label, color in FUEL_GROUP_COLORS.items()
        ],
        "markers": markers,
    }


__all__ = [
    "_marker_color",
    "_marker_radius",
    "_marker_popup_html",
    "_marker_fingerprint",
    "_build_static_signature",
    "_build_operational_signature",
    "_build_map_signature",
    "_build_marker_payload",
]

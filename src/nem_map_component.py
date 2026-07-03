from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit.components.v1 as components


_FRONTEND_DIR = Path(__file__).resolve().parent / "nem_map_component_frontend"
_component_func = components.declare_component("nem_facility_map", path=str(_FRONTEND_DIR))


def render_nem_facility_map(
    marker_payload: Dict[str, Any],
    *,
    height: int = 730,
    key: str = "nem-facility-map",
) -> Any:
    return _component_func(
        marker_payload=marker_payload,
        height=height,
        default={},
        key=key,
    )

from __future__ import annotations

from typing import Dict

import pandas as pd

from .._compat import st


def _render_table(filtered_snapshot: Dict[str, Dict[str, str]]) -> None:
    st.subheader("Facility Data Preview")
    if not filtered_snapshot:
        st.info("No matching records in the current cache.")
        return
    preview = pd.DataFrame(filtered_snapshot.values())
    cols = [
        "facility_code",
        "facility_name",
        "state",
        "fuel_group",
        "fuel_list",
        "power_value",
        "emission_value",
        "price_per_mwh",
        "demand_mw",
        "timestamp",
    ]
    existing = [col for col in cols if col in preview.columns]
    st.dataframe(preview[existing].sort_values("facility_code"), width="stretch", height=260)


__all__ = ["_render_table"]

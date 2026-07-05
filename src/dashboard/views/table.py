from __future__ import annotations

from typing import Dict

import pandas as pd

from .._compat import st


def _render_table(filtered_snapshot: Dict[str, Dict[str, str]]) -> None:
    st.subheader("Facility Data Preview")
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
    preview = pd.DataFrame.from_records(list(filtered_snapshot.values()), columns=cols)
    existing = [col for col in cols if col in preview.columns]
    st.dataframe(
        preview[existing].sort_values("facility_code"), width="stretch", height=260
    )


__all__ = ["_render_table"]

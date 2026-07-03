from __future__ import annotations

import html
import textwrap
from typing import Any, Dict, List

from ..data import _build_current_trend_cards, _format_optional_metric
from .._compat import components, st
from ..runtime import DashboardRuntime


def _build_current_trend_html(message: Dict[str, Any]) -> str:
    facility_name = html.escape(str(message.get("facility_name") or message.get("facility_code") or "Unknown Facility"))
    facility_code = html.escape(str(message.get("facility_code") or ""))
    timestamp = html.escape(str(message.get("timestamp") or ""))
    details = " | ".join(part for part in (facility_code, timestamp) if part)
    cards = _build_current_trend_cards(message)
    card_items = []
    for card in cards:
        card_items.append(
            f"""
            <div style="
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 12px;
                min-width: 0;
            ">
              <div style="font-size: 0.74rem; color: #64748b; font-weight: 600; line-height: 1.2; margin-bottom: 4px;">
                {html.escape(card["label"])}
              </div>
              <div style="font-size: 0.96rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
                {html.escape(card["value"])}
              </div>
            </div>
            """
        )

    detail_html = f'<div style="font-size: 0.8rem; color: #64748b; margin-top: 4px;">{details}</div>' if details else ""
    return textwrap.dedent(
        f"""
        <div style="
            border: 1px solid #dbe4ee;
            border-radius: 14px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            padding: 12px 14px 14px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-top: 2px;
        ">
          <div style="font-size: 0.92rem; color: #0f172a; font-weight: 700; line-height: 1.2;">
            Current Facility: {facility_name}
          </div>
          {detail_html}
          <div style="
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
          ">
            {''.join(card_items)}
          </div>
        </div>
        """
    ).strip()


def _render_current_trend(messages: List[Dict[str, Any]]) -> None:
    from ..data import _get_latest_trend_message

    latest = _get_latest_trend_message(messages)
    if latest is None:
        st.subheader("Current Facility")
        st.info("No MQTT messages available for current trend yet.")
        return

    components.html(_build_current_trend_html(latest), height=220, scrolling=False)


def _render_header(runtime: DashboardRuntime, stats: Dict[str, Any], snapshot: Dict[str, Dict[str, Any]]) -> None:
    st.title("⚡ National Electricity Market (NEM) Facility Real-time Monitoring Dashboard")
    st.caption("Live MQTT stream with bounded in-memory cache. No live CSV storage is used.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Power Output MW", f"{stats['total_power']}")
    with col2:
        st.metric("Total CO2 Emissions tCO2e", _format_optional_metric(stats["total_emission"], "tCO2e"))
    with col3:
        st.metric("Median Price $/MWh", _format_optional_metric(stats["median_price"], "$/MWh"))
    with col4:
        st.metric("Median Grid Demand MW", _format_optional_metric(stats["median_demand"], "MW"))


__all__ = [
    "_build_current_trend_html",
    "_render_current_trend",
    "_render_header",
]

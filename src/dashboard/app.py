from __future__ import annotations

from .render import configure_page, render_dashboard
from .runtime import get_runtime, set_active_runtime


def main() -> None:
    set_active_runtime(get_runtime())
    configure_page()
    render_dashboard()


__all__ = ["main"]

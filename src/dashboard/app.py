from __future__ import annotations

from .render import configure_page, render_dashboard


def main() -> None:
    configure_page()
    render_dashboard()


__all__ = ["main"]


from __future__ import annotations

from types import SimpleNamespace


class _SessionState(dict):
    def __getattr__(self, key: str):
        return self[key]

    def __setattr__(self, key: str, value) -> None:
        self[key] = value


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyStreamlit(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__()
        self.session_state = _SessionState()
        self.sidebar = _DummyContext()

    def set_page_config(self, *args, **kwargs):
        return None

    def title(self, *args, **kwargs):
        return None

    def header(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def columns(self, count: int):
        return [_DummyContext() for _ in range(count)]

    def metric(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def selectbox(self, *args, **kwargs):
        return kwargs.get("index", 0)

    def write(self, *args, **kwargs):
        return None

    def button(self, *args, **kwargs):
        return False

    def markdown(self, *args, **kwargs):
        return None

    def badge(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def json(self, *args, **kwargs):
        return None

    def rerun(self):
        return None

    def fragment(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def cache_resource(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


def _dummy_html(*args, **kwargs):
    return None


def _dummy_declare_component(*args, **kwargs):
    def component(**component_kwargs):
        return component_kwargs.get("default", {})

    return component


try:  # pragma: no cover - exercised when Streamlit is installed
    import streamlit as st  # type: ignore
    from streamlit.components import v1 as components  # type: ignore
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    st = _DummyStreamlit()
    components = SimpleNamespace(
        html=_dummy_html, declare_component=_dummy_declare_component
    )


__all__ = ["st", "components"]

"""Read-only LLM analytics overlay on mart publish data."""

from src.llm.pipeline import QueryResult, run_llm_query

__all__ = ["QueryResult", "run_llm_query"]

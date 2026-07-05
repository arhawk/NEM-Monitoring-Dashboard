from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
STAGING_DATA_DIR = DATA_DIR / "staging"
MART_DATA_DIR = DATA_DIR / "mart"
CACHE_DATA_DIR = DATA_DIR / "cache"


def repo_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)


def raw_data_path(*parts: str) -> Path:
    return RAW_DATA_DIR.joinpath(*parts)


def staging_data_path(*parts: str) -> Path:
    return STAGING_DATA_DIR.joinpath(*parts)


def mart_data_path(*parts: str) -> Path:
    return MART_DATA_DIR.joinpath(*parts)


def cache_data_path(*parts: str) -> Path:
    return CACHE_DATA_DIR.joinpath(*parts)


__all__ = [
    "PROJECT_ROOT",
    "DATA_DIR",
    "RAW_DATA_DIR",
    "STAGING_DATA_DIR",
    "MART_DATA_DIR",
    "CACHE_DATA_DIR",
    "repo_path",
    "data_path",
    "raw_data_path",
    "staging_data_path",
    "mart_data_path",
    "cache_data_path",
]

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)

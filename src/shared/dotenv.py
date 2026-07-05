from __future__ import annotations

import os
from pathlib import Path


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]

    return key, value


def load_dotenv_from_repo(
    env_path: str | Path | None = None, *, override: bool = False
) -> bool:
    """
    Load environment variables from the repository root .env file if present.

    Existing environment variables are preserved unless override=True is passed.
    """
    if env_path is None:
        repo_root = Path(__file__).resolve().parents[2]
        env_path = repo_root / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        return False

    loaded = False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
            loaded = True
    return loaded


__all__ = ["load_dotenv_from_repo"]

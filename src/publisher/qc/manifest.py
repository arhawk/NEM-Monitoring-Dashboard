from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.shared.config import get_fetch_date_end, get_fetch_date_start
from src.shared.paths import PROJECT_ROOT

from . import PIPELINE_VERSION


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _api_key_present() -> bool:
    try:
        from src.shared.config import get_open_electricity_api_key

        get_open_electricity_api_key()
        return True
    except RuntimeError:
        return False


def build_manifest(
    *,
    artifacts: dict[str, Path],
    row_counts: dict[str, int],
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_meta = {}
    for name, path in artifacts.items():
        artifact_meta[name] = {
            "path": str(path.relative_to(PROJECT_ROOT))
            if path.is_absolute()
            else str(path),
            "sha256": _sha256(path),
            "rows": row_counts.get(name),
            "exists": path.exists(),
        }

    return {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "fetch_window": {
            "start": get_fetch_date_start().isoformat(),
            "end": get_fetch_date_end().isoformat(),
        },
        "api_key_present": _api_key_present(),
        "artifacts": artifact_meta,
        "row_counts": row_counts,
    }


def write_manifest(
    manifest: dict[str, Any], reports_dir: Path, run_id: str
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest_path = reports_dir / "manifest_latest.json"
    stamped_path = reports_dir / f"manifest_{run_id}.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True)
    latest_path.write_text(payload + "\n", encoding="utf-8")
    stamped_path.write_text(payload + "\n", encoding="utf-8")
    return latest_path, stamped_path


__all__ = ["build_manifest", "write_manifest"]

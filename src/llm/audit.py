from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_audit_log(payload: dict, audit_dir: Path) -> Path:
    audit_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    path = audit_dir / f"{timestamp}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


__all__ = ["write_audit_log"]

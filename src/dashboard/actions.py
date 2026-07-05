from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - exercised in dependency-light test envs

    class _MissingRequests:
        def request(self, *args, **kwargs):
            raise ModuleNotFoundError("requests is required for GitHub Actions control")

    requests = SimpleNamespace(request=_MissingRequests().request)

from ._compat import st
from .settings import (
    AUTO_START_COOLDOWN_SECONDS,
    AUTO_START_PUBLISHER,
    ENABLE_GITHUB_ACTIONS_CONTROL,
    GITHUB_OWNER,
    GITHUB_REF,
    GITHUB_REPO,
    GITHUB_TOKEN,
    GITHUB_WORKFLOW_FILE,
)


GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
AUTO_START_SESSION_KEY = "_github_actions_auto_start_attempted"
AUTO_START_LAST_RESULT_SESSION_KEY = "_github_actions_auto_start_last_result"
LAST_TRIGGER_RESULT_SESSION_KEY = "_github_actions_last_trigger_result"
LAST_RUNS_SESSION_KEY = "_github_actions_last_runs"


@dataclass(frozen=True)
class WorkflowRun:
    id: int
    status: str
    conclusion: Optional[str]
    created_at: datetime
    html_url: Optional[str]
    run_number: Optional[int]

    @property
    def is_running(self) -> bool:
        return self.status in {"queued", "in_progress"}

    @property
    def is_recent_completion(self) -> bool:
        return self.status == "completed"


def is_github_actions_control_enabled() -> bool:
    return ENABLE_GITHUB_ACTIONS_CONTROL


def _session_state() -> Dict[str, Any]:
    return st.session_state


def _set_session_value(key: str, value: Any) -> None:
    _session_state()[key] = value


def _get_session_value(key: str, default: Any = None) -> Any:
    return _session_state().get(key, default)


def _github_headers() -> Dict[str, str]:
    token = GITHUB_TOKEN
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _github_request(
    method: str,
    path: str,
    *,
    params: Dict[str, Any] | None = None,
    json_body: Dict[str, Any] | None = None,
) -> requests.Response:
    url = f"{GITHUB_API_BASE}{path}"
    response = requests.request(
        method,
        url,
        headers=_github_headers(),
        params=params,
        json=json_body,
        timeout=20,
    )
    if response.status_code >= 400:
        message = response.text.strip()
        raise RuntimeError(
            f"GitHub API {method} {path} failed with {response.status_code}: {message}"
        )
    return response


def _parse_run(raw: Dict[str, Any]) -> WorkflowRun:
    created_at_raw = str(raw.get("created_at") or "")
    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    return WorkflowRun(
        id=int(raw["id"]),
        status=str(raw.get("status") or "unknown"),
        conclusion=raw.get("conclusion"),
        created_at=created_at,
        html_url=raw.get("html_url"),
        run_number=raw.get("run_number"),
    )


def _workflow_runs_endpoint() -> str:
    return f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW_FILE}/runs"


def _workflow_dispatch_endpoint() -> str:
    return f"/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW_FILE}/dispatches"


def get_recent_or_running_publisher_runs() -> List[Dict[str, Any]]:
    if not is_github_actions_control_enabled():
        return []

    response = _github_request(
        "GET",
        _workflow_runs_endpoint(),
        params={"branch": GITHUB_REF, "per_page": 20},
    )
    payload = response.json()
    runs = [_parse_run(item) for item in payload.get("workflow_runs", [])]
    runs_sorted = sorted(runs, key=lambda run: run.created_at, reverse=True)
    parsed = [
        {
            "id": run.id,
            "status": run.status,
            "conclusion": run.conclusion,
            "created_at": run.created_at,
            "html_url": run.html_url,
            "run_number": run.run_number,
        }
        for run in runs_sorted
    ]
    _set_session_value(LAST_RUNS_SESSION_KEY, parsed)
    return parsed


def _format_run_label(run: Dict[str, Any]) -> str:
    created_at = run.get("created_at")
    created_at_label = (
        created_at.isoformat()
        if isinstance(created_at, datetime)
        else str(created_at or "unknown time")
    )
    if run.get("status") == "completed":
        conclusion = run.get("conclusion") or "completed"
        return f"{conclusion} at {created_at_label}"
    return f"{run.get('status', 'unknown')} at {created_at_label}"


def _find_blocking_run(
    runs: List[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    now = datetime.now(timezone.utc)
    cooldown = AUTO_START_COOLDOWN_SECONDS
    if cooldown <= 0:
        cooldown = 0

    for run in runs:
        status = run.get("status")
        if status in {"queued", "in_progress"}:
            return run, f"A publisher run is already {status}."

        if status == "completed":
            created_at = run.get("created_at")
            if isinstance(created_at, datetime):
                age_seconds = (now - created_at).total_seconds()
                if age_seconds < cooldown:
                    return (
                        run,
                        f"A publisher run started {int(age_seconds)} seconds ago, inside the cooldown window.",
                    )

    return None, None


def _build_trigger_result(
    *,
    triggered: bool,
    message: str,
    run: Dict[str, Any] | None = None,
    error: str | None = None,
) -> Dict[str, Any]:
    result = {
        "triggered": triggered,
        "message": message,
        "error": error,
        "run": run,
    }
    _set_session_value(LAST_TRIGGER_RESULT_SESSION_KEY, result)
    return result


def trigger_publisher_workflow(duration_seconds: int = 600) -> Dict[str, Any]:
    if not is_github_actions_control_enabled():
        return _build_trigger_result(
            triggered=False, message="GitHub Actions control is disabled."
        )

    try:
        runs = get_recent_or_running_publisher_runs()
        blocking_run, blocking_message = _find_blocking_run(runs)
        if blocking_run is not None:
            return _build_trigger_result(
                triggered=False,
                message=blocking_message or "A publisher run is already active.",
                run=blocking_run,
            )

        response = _github_request(
            "POST",
            _workflow_dispatch_endpoint(),
            json_body={
                "ref": GITHUB_REF,
                "inputs": {"duration_seconds": str(max(0, duration_seconds))},
            },
        )
        if response.status_code not in {201, 204}:
            raise RuntimeError(
                f"Unexpected GitHub dispatch status: {response.status_code}"
            )

        message = f"Triggered GitHub Actions publisher for {max(0, duration_seconds)} seconds."
        return _build_trigger_result(triggered=True, message=message)
    except Exception as exc:
        return _build_trigger_result(
            triggered=False,
            message="Failed to trigger GitHub Actions publisher.",
            error=str(exc),
        )


def maybe_auto_start_publisher() -> Dict[str, Any]:
    if not is_github_actions_control_enabled():
        return _build_trigger_result(
            triggered=False, message="GitHub Actions control is disabled."
        )

    if not AUTO_START_PUBLISHER:
        return _build_trigger_result(triggered=False, message="Auto-start is disabled.")

    if _get_session_value(AUTO_START_SESSION_KEY, False):
        cached_result = _get_session_value(AUTO_START_LAST_RESULT_SESSION_KEY)
        if isinstance(cached_result, dict):
            return cached_result
        return _build_trigger_result(
            triggered=False, message="Auto-start already evaluated in this session."
        )

    _set_session_value(AUTO_START_SESSION_KEY, True)
    result = trigger_publisher_workflow(duration_seconds=600)
    _set_session_value(AUTO_START_LAST_RESULT_SESSION_KEY, result)
    return result


def describe_publisher_workflow_status() -> Optional[str]:
    runs = _get_session_value(LAST_RUNS_SESSION_KEY)
    if not isinstance(runs, list) or not runs:
        try:
            runs = get_recent_or_running_publisher_runs()
        except Exception:
            return None

    if not runs:
        return None

    latest = runs[0]
    return _format_run_label(latest)


def get_last_trigger_result() -> Optional[Dict[str, Any]]:
    result = _get_session_value(LAST_TRIGGER_RESULT_SESSION_KEY)
    return result if isinstance(result, dict) else None


def get_last_runs() -> List[Dict[str, Any]]:
    runs = _get_session_value(LAST_RUNS_SESSION_KEY)
    return runs if isinstance(runs, list) else []


__all__ = [
    "AUTO_START_PUBLISHER",
    "describe_publisher_workflow_status",
    "get_last_runs",
    "get_last_trigger_result",
    "get_recent_or_running_publisher_runs",
    "is_github_actions_control_enabled",
    "maybe_auto_start_publisher",
    "trigger_publisher_workflow",
]

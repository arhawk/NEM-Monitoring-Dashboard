from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from src.shared.paths import repo_path

from . import PIPELINE_VERSION


def _status_color(status: str) -> str:
    if status == "pass":
        return "#1b7f3b"
    if status == "warn":
        return "#b8860b"
    return "#b00020"


def build_report_payload(
    summary: dict[str, Any],
    *,
    run_id: str,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": summary["overall_status"],
        "passed": summary["passed"],
        "failed": summary["failed"],
        "warnings": summary["warnings"],
        "checks": summary["checks"],
        "manifest": manifest or {},
    }


def write_json_report(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_markdown_report(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# QC Report",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Pipeline version: `{payload['pipeline_version']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Overall status: **{payload['overall_status'].upper()}**",
        f"- Passed: {payload['passed']} | Failed: {payload['failed']} | Warnings: {payload['warnings']}",
        "",
        "## Checks",
        "",
        "| ID | Name | Status | Severity | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in payload["checks"]:
        message = str(check.get("message", "")).replace("|", "\\|")
        lines.append(
            f"| {check['id']} | {check['name']} | {check['status']} | {check['severity']} | {message} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html_report(payload: dict[str, Any], path: Path) -> None:
    status = payload["overall_status"]
    rows = []
    for check in payload["checks"]:
        color = _status_color(check["status"])
        rows.append(
            "<tr>"
            f"<td>{escape(str(check['id']))}</td>"
            f"<td>{escape(str(check['name']))}</td>"
            f"<td style='color:{color};font-weight:600'>{escape(str(check['status']))}</td>"
            f"<td>{escape(str(check['severity']))}</td>"
            f"<td>{escape(str(check.get('message', '')))}</td>"
            "</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>QC Report {escape(payload["run_id"])}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }}
    .banner {{ padding: 1rem 1.25rem; border-radius: 8px; color: white; background: {_status_color(status)}; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <div class="banner">
    <h1>QC Report: {escape(status.upper())}</h1>
    <p>Run {escape(payload["run_id"])} | Pipeline {escape(payload["pipeline_version"])}</p>
  </div>
  <p>Generated at {escape(payload["generated_at"])}</p>
  <p>Passed {payload["passed"]} | Failed {payload["failed"]} | Warnings {payload["warnings"]}</p>
  <table>
    <thead>
      <tr><th>ID</th><th>Name</th><th>Status</th><th>Severity</th><th>Message</th></tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def write_qc_reports(
    payload: dict[str, Any],
    reports_dir: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Path]:
    reports_dir = reports_dir or repo_path("reports")
    run_id = run_id or payload["run_id"]
    stamped_json = reports_dir / f"qc_{run_id}.json"
    stamped_md = reports_dir / f"qc_{run_id}.md"
    stamped_html = reports_dir / f"qc_{run_id}.html"
    latest_json = reports_dir / "qc_latest.json"
    latest_md = reports_dir / "qc_latest.md"
    latest_html = reports_dir / "qc_latest.html"

    write_json_report(payload, stamped_json)
    write_markdown_report(payload, stamped_md)
    write_html_report(payload, stamped_html)

    for src, dest in (
        (stamped_json, latest_json),
        (stamped_md, latest_md),
        (stamped_html, latest_html),
    ):
        shutil.copyfile(src, dest)

    return {
        "json": latest_json,
        "markdown": latest_md,
        "html": latest_html,
        "stamped_json": stamped_json,
        "stamped_md": stamped_md,
        "stamped_html": stamped_html,
    }


__all__ = [
    "build_report_payload",
    "write_html_report",
    "write_json_report",
    "write_markdown_report",
    "write_qc_reports",
]

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.shared.paths import repo_path

from .manifest import build_manifest, write_manifest
from .report import build_report_payload, write_qc_reports
from .rules import (
    MART_PATH,
    STAGING_CONSOLIDATED_PATH,
    load_qc_context,
    run_all_checks,
    should_fail_exit,
    summarize_checks,
)


def run_validate(
    *,
    mart_path: Path | None = None,
    staging_path: Path | None = None,
    thresholds_path: Path | None = None,
    baseline_path: Path | None = None,
    reports_dir: Path | None = None,
    write_reports: bool = True,
) -> int:
    reports_dir = reports_dir or repo_path("reports")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ctx = load_qc_context(
        mart_path=mart_path,
        staging_path=staging_path,
        thresholds_path=thresholds_path,
        baseline_path=baseline_path,
    )
    checks = run_all_checks(ctx)
    summary = summarize_checks(checks)

    manifest = build_manifest(
        artifacts={
            "mart": ctx.mart_path,
            "staging_consolidated": ctx.staging_path,
        },
        row_counts={
            "mart": len(ctx.mart),
            "staging_consolidated": len(ctx.staging),
            "mart_facilities": int(ctx.mart["facility_code"].nunique()),
        },
        run_id=run_id,
    )

    payload = build_report_payload(summary, run_id=run_id, manifest=manifest)

    if write_reports:
        write_qc_reports(payload, reports_dir=reports_dir, run_id=run_id)
        write_manifest(manifest, reports_dir, run_id)

    print(
        f"[QC] overall={summary['overall_status']} "
        f"passed={summary['passed']} failed={summary['failed']} warnings={summary['warnings']}"
    )
    for check in checks:
        if check.status != "pass":
            print(f"[QC] {check.id} {check.status}: {check.message}")

    return 1 if should_fail_exit(checks) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate mart artifacts and write QC reports."
    )
    parser.add_argument("--mart-path", type=Path, default=MART_PATH)
    parser.add_argument("--staging-path", type=Path, default=STAGING_CONSOLIDATED_PATH)
    parser.add_argument("--thresholds-path", type=Path, default=None)
    parser.add_argument("--baseline-path", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument(
        "--no-write", action="store_true", help="Skip writing report files."
    )
    args = parser.parse_args(argv)

    return run_validate(
        mart_path=args.mart_path,
        staging_path=args.staging_path,
        thresholds_path=args.thresholds_path,
        baseline_path=args.baseline_path,
        reports_dir=args.reports_dir,
        write_reports=not args.no_write,
    )


if __name__ == "__main__":
    sys.exit(main())

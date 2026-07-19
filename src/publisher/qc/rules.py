from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.publisher.data.alignment import get_state_bounds_map
from src.publisher.publish.mqtt_publish import load_measure_rows
from src.shared.paths import PROJECT_ROOT, mart_data_path, staging_data_path

from . import PIPELINE_VERSION


DEFAULT_THRESHOLDS_PATH = PROJECT_ROOT / "config" / "qc_thresholds.yaml"
DEFAULT_BASELINE_PATH = PROJECT_ROOT / "config" / "qc_baseline.yaml"

MART_PATH = mart_data_path("data_for_publish.csv")
STAGING_CONSOLIDATED_PATH = staging_data_path(
    "open_electricity", "consolidated_data_cleaned.csv"
)

SAMPLE_OFFENDERS_LIMIT = 10


@dataclass
class CheckResult:
    id: str
    name: str
    status: str
    severity: str
    metric: dict[str, Any] = field(default_factory=dict)
    threshold: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QcContext:
    mart: pd.DataFrame
    staging: pd.DataFrame
    mart_path: Path
    staging_path: Path
    thresholds: dict[str, Any]
    baseline: dict[str, Any]


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def _pass(check_id: str, name: str, severity: str, **kwargs: Any) -> CheckResult:
    return CheckResult(
        id=check_id,
        name=name,
        status="pass",
        severity=severity,
        metric=kwargs.get("metric", {}),
        threshold=kwargs.get("threshold", {}),
        message=kwargs.get("message", ""),
    )


def _fail(check_id: str, name: str, severity: str, **kwargs: Any) -> CheckResult:
    return CheckResult(
        id=check_id,
        name=name,
        status="fail",
        severity=severity,
        metric=kwargs.get("metric", {}),
        threshold=kwargs.get("threshold", {}),
        message=kwargs.get("message", ""),
    )


def _warn(check_id: str, name: str, **kwargs: Any) -> CheckResult:
    return CheckResult(
        id=check_id,
        name=name,
        status="warn",
        severity="warn",
        metric=kwargs.get("metric", {}),
        threshold=kwargs.get("threshold", {}),
        message=kwargs.get("message", ""),
    )


def check_mart_001_required_columns(ctx: QcContext) -> CheckResult:
    required = ctx.thresholds.get("mart", {}).get("required_columns", [])
    missing = [column for column in required if column not in ctx.mart.columns]
    if missing:
        return _fail(
            "MART-001",
            "required_columns_present",
            "error",
            metric={"missing_columns": missing},
            threshold={"required_columns": required},
            message=f"Missing columns: {missing}",
        )
    return _pass(
        "MART-001",
        "required_columns_present",
        "error",
        metric={"column_count": len(ctx.mart.columns)},
        threshold={"required_columns": required},
    )


def check_mart_002_primary_key_unique(ctx: QcContext) -> CheckResult:
    duplicates = int(ctx.mart.duplicated(subset=["facility_code", "timestamp"]).sum())
    threshold = {"max_duplicates": 0}
    if duplicates:
        return _fail(
            "MART-002",
            "primary_key_unique",
            "error",
            metric={"duplicates": duplicates},
            threshold=threshold,
            message=f"Found {duplicates} duplicate (facility_code, timestamp) rows",
        )
    return _pass(
        "MART-002",
        "primary_key_unique",
        "error",
        metric={"duplicates": 0},
        threshold=threshold,
    )


def check_mart_003_required_null_rates(ctx: QcContext) -> CheckResult:
    limits = ctx.thresholds.get("mart", {}).get("required_null_max_rate", {})
    rates = {
        column: float(ctx.mart[column].isna().mean())
        if column in ctx.mart.columns
        else 1.0
        for column in limits
    }
    offenders = {
        column: rate for column, rate in rates.items() if rate > limits[column]
    }
    if offenders:
        return _fail(
            "MART-003",
            "required_null_rates",
            "error",
            metric={"null_rates": rates, "offenders": offenders},
            threshold={"required_null_max_rate": limits},
            message=f"Null rate exceeded for: {list(offenders.keys())}",
        )
    return _pass(
        "MART-003",
        "required_null_rates",
        "error",
        metric={"null_rates": rates},
        threshold={"required_null_max_rate": limits},
    )


def check_mart_004_power_null_rate(ctx: QcContext) -> CheckResult:
    column = "Power (MW)"
    max_rate = float(ctx.thresholds.get("mart", {}).get("power_null_max_rate", 0.001))
    rate = float(ctx.mart[column].isna().mean()) if column in ctx.mart.columns else 1.0
    threshold = {"power_null_max_rate": max_rate}
    if rate > max_rate:
        return _fail(
            "MART-004",
            "power_null_rate",
            "error",
            metric={
                "null_rate": rate,
                "null_count": int(ctx.mart[column].isna().sum()),
            },
            threshold=threshold,
            message=f"Power (MW) null rate {rate:.4%} exceeds {max_rate:.4%}",
        )
    return _pass(
        "MART-004",
        "power_null_rate",
        "error",
        metric={"null_rate": rate},
        threshold=threshold,
    )


def check_mart_005_non_negative_metrics(ctx: QcContext) -> CheckResult:
    offenders: dict[str, int] = {}
    for column in ("Power (MW)", "Emissions (tonnes)"):
        if column not in ctx.mart.columns:
            continue
        numeric = pd.to_numeric(ctx.mart[column], errors="coerce")
        count = int((numeric < 0).sum())
        if count:
            offenders[column] = count
    if offenders:
        return _fail(
            "MART-005",
            "non_negative_metrics",
            "error",
            metric={"negative_counts": offenders},
            threshold={"min_value": 0},
            message=f"Negative values found: {offenders}",
        )
    return _pass(
        "MART-005",
        "non_negative_metrics",
        "error",
        metric={"negative_counts": {}},
        threshold={"min_value": 0},
    )


def check_mart_geo_001_state_bounds(ctx: QcContext) -> CheckResult:
    bounds_map = get_state_bounds_map()
    out_of_bounds = 0
    unknown_state = 0
    sample_codes: list[str] = []

    for _, row in ctx.mart.iterrows():
        state = row.get("state")
        if pd.isna(state) or str(state).strip() == "":
            continue
        state_key = str(state).strip()
        lat = row.get("lat")
        lng = row.get("lng")
        if pd.isna(lat) or pd.isna(lng):
            continue
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            out_of_bounds += 1
            continue

        box = bounds_map.get(state_key)
        if box is None:
            unknown_state += 1
            if len(sample_codes) < SAMPLE_OFFENDERS_LIMIT:
                sample_codes.append(str(row.get("facility_code", "")))
            continue

        lat_min, lat_max, lng_min, lng_max = box
        if not (lat_min <= lat_f <= lat_max and lng_min <= lng_f <= lng_max):
            out_of_bounds += 1
            if len(sample_codes) < SAMPLE_OFFENDERS_LIMIT:
                sample_codes.append(str(row.get("facility_code", "")))

    total_bad = out_of_bounds + unknown_state
    metric = {
        "out_of_state_bounds_count": out_of_bounds,
        "unknown_state_count": unknown_state,
        "sample_facility_codes": sample_codes,
    }
    if total_bad:
        return _fail(
            "MART-GEO-001",
            "coords_inside_declared_state_bounds",
            "error",
            metric=metric,
            threshold={"source": "alignment.get_state_bounds_map"},
            message=(
                f"{out_of_bounds} rows outside declared state bounds; "
                f"{unknown_state} rows with unknown state"
            ),
        )
    return _pass(
        "MART-GEO-001",
        "coords_inside_declared_state_bounds",
        "error",
        metric=metric,
        threshold={"source": "alignment.get_state_bounds_map"},
    )


def check_mart_007_optional_null_rates(ctx: QcContext) -> CheckResult:
    warn_limits = ctx.thresholds.get("mart", {}).get("optional_null_warn_rate", {})
    error_limits = ctx.thresholds.get("mart", {}).get("optional_null_error_rate", {})
    rates = {}
    for column in set(warn_limits) | set(error_limits):
        if column in ctx.mart.columns:
            rates[column] = float(ctx.mart[column].isna().mean())

    for column, limit in error_limits.items():
        rate = rates.get(column, 0.0)
        if rate > limit:
            return _fail(
                "MART-007",
                "optional_null_rates",
                "error",
                metric={"null_rates": rates},
                threshold={"optional_null_error_rate": error_limits},
                message=f"{column} null rate {rate:.2%} exceeds error limit {limit:.2%}",
            )

    warn_columns = {
        column: rate
        for column, rate in rates.items()
        if column in warn_limits and rate > warn_limits[column]
    }
    if warn_columns:
        return _warn(
            "MART-007",
            "optional_null_rates",
            metric={"null_rates": rates, "warn_columns": warn_columns},
            threshold={"optional_null_warn_rate": warn_limits},
            message=f"Optional null rates above warn threshold: {warn_columns}",
        )
    return _pass(
        "MART-007",
        "optional_null_rates",
        "warn",
        metric={"null_rates": rates},
        threshold={"optional_null_warn_rate": warn_limits},
    )


def check_mart_008_state_and_fuel_list(ctx: QcContext) -> CheckResult:
    state_null = (
        int(ctx.mart["state"].isna().sum())
        if "state" in ctx.mart.columns
        else len(ctx.mart)
    )
    if state_null:
        return _fail(
            "MART-008",
            "state_and_fuel_list",
            "error",
            metric={"state_null_count": state_null},
            threshold={"state_null_max": 0},
            message=f"Found {state_null} rows with null state",
        )
    return _pass(
        "MART-008",
        "state_and_fuel_list",
        "error",
        metric={"state_null_count": 0, "fuel_list_empty_allowed": True},
        threshold={"state_null_max": 0},
    )


def check_cons_001_facility_subset(ctx: QcContext) -> CheckResult:
    mart_codes = set(ctx.mart["facility_code"].astype(str))
    staging_codes = set(ctx.staging["facility_code"].astype(str))
    orphan = sorted(mart_codes - staging_codes)
    if orphan:
        return _fail(
            "CONS-001",
            "mart_facility_subset_of_staging",
            "error",
            metric={
                "orphan_facility_codes": orphan[:SAMPLE_OFFENDERS_LIMIT],
                "count": len(orphan),
            },
            threshold={"rule": "mart.facility_code subset staging.facility_code"},
            message=f"{len(orphan)} mart facility codes not in staging",
        )
    return _pass(
        "CONS-001",
        "mart_facility_subset_of_staging",
        "error",
        metric={"orphan_count": 0},
        threshold={"rule": "mart.facility_code subset staging.facility_code"},
    )


def check_cons_002_row_retention(ctx: QcContext) -> CheckResult:
    min_ratio = float(
        ctx.baseline.get(
            "staging_retention_min",
            ctx.thresholds.get("consistency", {}).get("staging_retention_min", 0.95),
        )
    )
    mart_rows = len(ctx.mart)
    staging_rows = len(ctx.staging)
    ratio = mart_rows / staging_rows if staging_rows else 0.0
    threshold = {
        "min_retention_ratio": min_ratio,
        "mart_rows": mart_rows,
        "staging_rows": staging_rows,
    }
    if ratio < min_ratio:
        return _fail(
            "CONS-002",
            "staging_row_retention",
            "error",
            metric={
                "retention_ratio": ratio,
                "mart_rows": mart_rows,
                "staging_rows": staging_rows,
            },
            threshold=threshold,
            message=f"Retention ratio {ratio:.4f} below minimum {min_ratio}",
        )
    return _pass(
        "CONS-002",
        "staging_row_retention",
        "error",
        metric={
            "retention_ratio": ratio,
            "mart_rows": mart_rows,
            "staging_rows": staging_rows,
        },
        threshold=threshold,
    )


def check_cons_003_staging_key_coverage(ctx: QcContext) -> CheckResult:
    staging_keys = set(
        zip(
            ctx.staging["facility_code"].astype(str),
            ctx.staging["timestamp"].astype(str),
            strict=False,
        )
    )
    mart_keys = list(
        zip(
            ctx.mart["facility_code"].astype(str),
            ctx.mart["timestamp"].astype(str),
            strict=False,
        )
    )
    orphan_count = sum(1 for key in mart_keys if key not in staging_keys)
    if orphan_count:
        return _fail(
            "CONS-003",
            "mart_keys_exist_in_staging",
            "error",
            metric={"orphan_key_count": orphan_count},
            threshold={"rule": "every mart (facility_code, timestamp) in staging"},
            message=f"{orphan_count} mart keys missing from staging consolidated data",
        )
    return _pass(
        "CONS-003",
        "mart_keys_exist_in_staging",
        "error",
        metric={"orphan_key_count": 0},
        threshold={"rule": "every mart (facility_code, timestamp) in staging"},
    )


def check_base_001_baseline_rows(ctx: QcContext) -> CheckResult:
    baseline_rows = int(ctx.baseline.get("mart_rows", 0))
    min_ratio = float(
        ctx.baseline.get(
            "mart_rows_min_ratio",
            ctx.thresholds.get("baseline", {}).get("mart_rows_min_ratio", 0.9),
        )
    )
    min_rows = int(baseline_rows * min_ratio) if baseline_rows else 0
    mart_rows = len(ctx.mart)
    threshold = {
        "baseline_mart_rows": baseline_rows,
        "mart_rows_min_ratio": min_ratio,
        "min_rows": min_rows,
    }
    if baseline_rows and mart_rows < min_rows:
        return _fail(
            "BASE-001",
            "baseline_row_count",
            "error",
            metric={"mart_rows": mart_rows, "min_rows": min_rows},
            threshold=threshold,
            message=f"mart_rows {mart_rows} below baseline minimum {min_rows}",
        )
    return _pass(
        "BASE-001",
        "baseline_row_count",
        "error",
        metric={"mart_rows": mart_rows, "min_rows": min_rows},
        threshold=threshold,
    )


def check_pub_001_power_zero_publishable(ctx: QcContext) -> CheckResult:
    from src.publisher.publish.mqtt_publish import normalize_ts

    sample_size = int(ctx.thresholds.get("publish", {}).get("sample_size", 500))
    power = pd.to_numeric(ctx.mart["Power (MW)"], errors="coerce")
    zero_sample = ctx.mart.loc[power == 0].head(sample_size)
    rows = load_measure_rows(ctx.mart_path)
    row_map = {(row["facility_code"], row["_ts_iso"]): row for row in rows}
    bad: list[str] = []
    for _, mrow in zero_sample.iterrows():
        key = (str(mrow["facility_code"]), normalize_ts(str(mrow["timestamp"])))
        pub_row = row_map.get(key)
        if pub_row is None or pub_row.get("power_value") != 0.0:
            bad.append(str(mrow["facility_code"]))
    if bad:
        return _fail(
            "PUB-001",
            "power_zero_publishable",
            "error",
            metric={
                "bad_zero_power_count": len(bad),
                "sample_checked": len(zero_sample),
                "sample_facility_codes": bad[:SAMPLE_OFFENDERS_LIMIT],
            },
            threshold={"rule": "Power (MW)==0 must map to power_value=0.0"},
            message=f"{len(bad)} zero-power rows missing power_value=0.0 in publish mapping",
        )
    return _pass(
        "PUB-001",
        "power_zero_publishable",
        "error",
        metric={"zero_power_rows_checked": len(zero_sample), "bad_zero_power_count": 0},
        threshold={"rule": "Power (MW)==0 must map to power_value=0.0"},
    )


def check_pub_002_dashboard_required_fields(ctx: QcContext) -> CheckResult:
    from src.publisher.publish.mqtt_publish import normalize_ts

    sample_size = int(ctx.thresholds.get("publish", {}).get("sample_size", 500))
    power = pd.to_numeric(ctx.mart["Power (MW)"], errors="coerce")
    sample = ctx.mart.loc[power.notna()].head(sample_size)
    rows = load_measure_rows(ctx.mart_path)
    row_map = {(row["facility_code"], row["_ts_iso"]): row for row in rows}
    missing = 0
    for _, mrow in sample.iterrows():
        key = (str(mrow["facility_code"]), normalize_ts(str(mrow["timestamp"])))
        row = row_map.get(key)
        if row is None:
            missing += 1
            continue
        if not row.get("facility_code"):
            missing += 1
            continue
        if (
            row.get("lat") is None
            or row.get("lng") is None
            or row.get("power_value") is None
        ):
            missing += 1
    if missing:
        return _fail(
            "PUB-002",
            "dashboard_required_fields",
            "error",
            metric={"missing_required_count": missing, "sample_checked": len(sample)},
            threshold={"required": ["facility_code", "lat", "lng", "power_value"]},
            message=f"{missing} sampled rows missing dashboard-required publish fields",
        )
    return _pass(
        "PUB-002",
        "dashboard_required_fields",
        "error",
        metric={"missing_required_count": 0, "sample_checked": len(sample)},
        threshold={"required": ["facility_code", "lat", "lng", "power_value"]},
    )


ALL_CHECKS = [
    check_mart_001_required_columns,
    check_mart_002_primary_key_unique,
    check_mart_003_required_null_rates,
    check_mart_004_power_null_rate,
    check_mart_005_non_negative_metrics,
    check_mart_geo_001_state_bounds,
    check_mart_007_optional_null_rates,
    check_mart_008_state_and_fuel_list,
    check_cons_001_facility_subset,
    check_cons_002_row_retention,
    check_cons_003_staging_key_coverage,
    check_base_001_baseline_rows,
    check_pub_001_power_zero_publishable,
    check_pub_002_dashboard_required_fields,
]


def load_qc_context(
    *,
    mart_path: Path | None = None,
    staging_path: Path | None = None,
    thresholds_path: Path | None = None,
    baseline_path: Path | None = None,
) -> QcContext:
    mart_path = mart_path or MART_PATH
    staging_path = staging_path or STAGING_CONSOLIDATED_PATH
    thresholds = load_yaml(thresholds_path or DEFAULT_THRESHOLDS_PATH)
    baseline = load_yaml(baseline_path or DEFAULT_BASELINE_PATH)

    if not mart_path.exists():
        raise FileNotFoundError(f"Mart artifact not found: {mart_path}")
    if not staging_path.exists():
        raise FileNotFoundError(f"Staging artifact not found: {staging_path}")

    return QcContext(
        mart=pd.read_csv(mart_path),
        staging=pd.read_csv(staging_path),
        mart_path=mart_path,
        staging_path=staging_path,
        thresholds=thresholds,
        baseline=baseline,
    )


def run_all_checks(ctx: QcContext) -> list[CheckResult]:
    return [check(ctx) for check in ALL_CHECKS]


def summarize_checks(checks: list[CheckResult]) -> dict[str, Any]:
    errors = [
        check
        for check in checks
        if check.status == "fail" and check.severity == "error"
    ]
    warnings = [
        check for check in checks if check.status == "warn" or check.severity == "warn"
    ]
    passed = [check for check in checks if check.status == "pass"]
    overall = "fail" if errors else ("warn" if warnings else "pass")
    return {
        "overall_status": overall,
        "passed": len(passed),
        "failed": len(errors),
        "warnings": len(warnings),
        "checks": [check.to_dict() for check in checks],
    }


def should_fail_exit(checks: list[CheckResult]) -> bool:
    return any(check.status == "fail" and check.severity == "error" for check in checks)


__all__ = [
    "ALL_CHECKS",
    "CheckResult",
    "DEFAULT_BASELINE_PATH",
    "DEFAULT_THRESHOLDS_PATH",
    "MART_PATH",
    "PIPELINE_VERSION",
    "QcContext",
    "STAGING_CONSOLIDATED_PATH",
    "load_qc_context",
    "load_yaml",
    "run_all_checks",
    "should_fail_exit",
    "summarize_checks",
]

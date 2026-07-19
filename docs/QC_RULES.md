# QC Rules

This document defines the automated quality-control rules executed by `src/publisher/qc/`.

Thresholds are configured in [`config/qc_thresholds.yaml`](../config/qc_thresholds.yaml).  
Production baseline counts are configured in [`config/qc_baseline.yaml`](../config/qc_baseline.yaml).

## Rule summary

| ID | Name | Severity | Pass condition |
| --- | --- | --- | --- |
| MART-001 | `required_columns_present` | error | All required mart columns exist |
| MART-002 | `primary_key_unique` | error | `(facility_code, timestamp)` has zero duplicates |
| MART-003 | `required_null_rates` | error | Required columns null rate = 0% |
| MART-004 | `power_null_rate` | error | `Power (MW)` null rate <= 0.1% |
| MART-005 | `non_negative_metrics` | error | `Power (MW)` and `Emissions (tonnes)` are >= 0 |
| MART-GEO-001 | `coords_inside_declared_state_bounds` | error | Coordinates fall inside declared state's bounding box |
| MART-007 | `optional_null_rates` | warn/error | Optional null rates warn >5%, error >50% |
| MART-008 | `state_and_fuel_list` | error | `state` non-null; empty `fuel_list` (`[]`) allowed |
| CONS-001 | `mart_facility_subset_of_staging` | error | Mart facility codes are a subset of staging consolidated |
| CONS-002 | `staging_row_retention` | error | `mart_rows >= staging_rows * 0.95` |
| CONS-003 | `mart_keys_exist_in_staging` | error | Every mart `(facility_code, timestamp)` exists in staging |
| BASE-001 | `baseline_row_count` | error | `mart_rows >= baseline.mart_rows * 0.9` |
| PUB-001 | `power_zero_publishable` | error | Rows with `Power (MW)==0` map to `power_value=0.0` |
| PUB-002 | `dashboard_required_fields` | error | Sampled non-null power rows publish `facility_code`, `lat`, `lng`, `power_value` |

## MART-GEO-001 and `_STATE_BOUNDS`

Per-state coordinate validation uses the same hardcoded bounding boxes as metadata alignment:

- Source: `get_state_bounds_map()` in [`src/publisher/data/alignment.py`](../src/publisher/data/alignment.py)
- These boxes are **approximate rectangles**, not official administrative boundaries
- They were added for `infer_state_from_coords()` when NGER name matching is inconclusive
- QC checks the **declared** `state` column against the facility coordinates

Current state boxes (lat_min, lat_max, lng_min, lng_max):

| State | lat_min | lat_max | lng_min | lng_max |
| --- | --- | --- | --- | --- |
| ACT | -35.95 | -35.12 | 148.75 | 149.45 |
| TAS | -43.75 | -39.15 | 143.75 | 148.35 |
| WA | -35.25 | -13.50 | 112.85 | 129.05 |
| NT | -26.05 | -10.90 | 129.00 | 138.05 |
| SA | -38.15 | -25.95 | 128.95 | 141.05 |
| QLD | -29.25 | -9.95 | 137.95 | 153.55 |
| NSW | -37.55 | -27.95 | 140.95 | 153.65 |
| VIC | -39.25 | -33.85 | 140.85 | 150.05 |

## Outputs

Each validate run writes:

- `reports/qc_YYYYMMDDTHHMMSSZ.{json,md,html}`
- `reports/qc_latest.{json,md,html}`
- `reports/manifest_latest.json` (+ timestamped copy)

Manifest fields include `pipeline_version`, `git_commit`, UTC timestamp, fetch window, artifact sha256 hashes, row counts, and `api_key_present`.

## Updating thresholds or baseline

1. Edit `config/qc_thresholds.yaml` for rule thresholds.
2. After an approved production rebuild, update `config/qc_baseline.yaml` manually with new row counts.
3. Bump `PIPELINE_VERSION` in `src/publisher/qc/__init__.py` when rule IDs or stage contracts change.

## Tests

- Unit tests with fixtures: `tests/test_qc_rules.py` and `tests/fixtures/qc/`
- Integration test against tracked artifacts: `tests/test_qc_integration.py`
- CI runs pytest and a standalone validate step via `.github/workflows/ci.yml`

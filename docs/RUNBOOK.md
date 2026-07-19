# Pipeline Runbook

Use this runbook to run, validate, and troubleshoot the NEM data pipeline.

## Stages

| Stage | Command | Primary inputs | Primary outputs |
| --- | --- | --- | --- |
| `fetch` | `./scripts/run_pipeline.sh --through fetch` | Open Electricity API, CER/NGER sources | `data/raw/open_electricity/*`, `data/raw/facility_metadata/*` |
| `stage` | `./scripts/run_pipeline.sh --through stage` | Raw CSV artifacts | `data/staging/open_electricity/*`, `data/staging/facility_metadata/*` |
| `mart` | `./scripts/run_pipeline.sh --through mart` | Staged CSV artifacts | `data/mart/data_for_publish.csv` |
| `validate` | `./scripts/run_pipeline.sh --through validate` | Mart + staged consolidated CSV | `reports/qc_latest.{json,md,html}`, `reports/manifest_latest.json` |
| `publish` | `./scripts/run_pipeline.sh --with-publish` | Validated mart CSV | MQTT messages on `comp5339/task123/measurements/{facility_code}` |

Default behavior:

```bash
./scripts/run_pipeline.sh
```

This runs `fetch -> stage -> mart -> validate` and exits non-zero if QC fails.

## Common commands

```bash
# Validate existing artifacts only
python scripts/validate_mart.py

# Rebuild staging + mart, then validate
./scripts/run_pipeline.sh --force-rebuild

# Re-fetch raw data from upstream sources
./scripts/run_pipeline.sh --force-fetch --force-rebuild

# Validate, then publish over MQTT
./scripts/run_pipeline.sh --with-publish
```

Python equivalent:

```bash
python -m src.publisher.pipeline --through validate
python -m src.publisher.qc.runner
```

## Expected artifacts

| Path | Role |
| --- | --- |
| `data/raw/open_electricity/consolidated_data_total.csv` | Raw operational extract |
| `data/staging/open_electricity/consolidated_data_cleaned.csv` | Cleaned operational data |
| `data/mart/data_for_publish.csv` | Publish-ready joined dataset |
| `reports/qc_latest.json` | Latest structured pass/fail QC summary |
| `reports/manifest_latest.json` | Run lineage metadata |

## QC failure playbook

1. Read `reports/qc_latest.md` or `reports/qc_latest.html`.
2. Identify failing rule ID (for example `MART-002`, `MART-GEO-001`, `CONS-002`).
3. Use the rule definitions in [`docs/QC_RULES.md`](QC_RULES.md).
4. Rebuild upstream artifacts:
   - Schema/uniqueness/null issues: delete `data/mart/data_for_publish.csv`, rerun `--through mart validate`
   - Staging inconsistency: delete staging + mart, rerun `--through stage validate`
   - Raw freshness: rerun with `--force-fetch --force-rebuild`
5. Re-run validate and confirm `overall_status` is `pass` or warn-only.

## Logs and runtime notes

- Pipeline stage logs print to stdout/stderr from Python modules under `src/publisher/`.
- MQTT publish logs print `[MQTT]` lines from `src/publisher/publish/mqtt_publish.py`.
- The legacy publisher entrypoint `python scripts/run_publisher.py` does **not** auto-run QC. Prefer `./scripts/run_pipeline.sh` for reproducible runs.
- Local full stack demo remains `scripts/start_local.sh` or `docker compose up --build`.

## Environment

- `OPEN_ELECTRICITY_API_KEY` is required only when raw Open Electricity files are missing and fetch must call the API.
- `FETCH_DATE_START` / `FETCH_DATE_END` control the fetch window used during `fetch`.
- QC thresholds live in `config/qc_thresholds.yaml`.
- Production baseline counts live in `config/qc_baseline.yaml` and are updated manually after approved pipeline changes.

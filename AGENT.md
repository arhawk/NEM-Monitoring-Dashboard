# Codex Runbook

This file is for future Codex agents working in this repository. The goal is not to explain the product. The goal is to avoid rediscovering how this repo is inspected, run, verified, and deployed.

## 1. Project Overview and Architecture

- This repository maintains a NEM data pipeline with QC gates plus a Streamlit dashboard consumer over MQTT.
- `docker-compose.yml` starts Mosquitto, the publisher container, and the dashboard container as a local full stack. You can also run Mosquitto alone with `docker compose up -d mosquitto`.
- Preferred maintained pipeline entrypoint:
  - `./scripts/run_pipeline.sh` (fetch -> stage -> mart -> validate)
  - `python scripts/validate_mart.py` (QC only)
- Legacy publish entrypoints (no automatic QC gate):
  - `python scripts/run_publisher.py`
  - `python3 -m src.publisher.cli`
- The dashboard also has two practical entrypoints:
  - Wrapper entrypoint: `streamlit run app/streamlit_app.py`
  - Equivalent explicit form: `python3 -m streamlit run app/streamlit_app.py --server.port 8501`
- `src/publisher/` contains the real publisher implementation.
- `scripts/run_publisher.py` is only a wrapper and executes `src.publisher.cli`.
- `app/streamlit_app.py` is also a wrapper and executes `src.dashboard.app`.
- The publisher generates and reuses CSV and JSON artifacts under `data/`. Treat those files as run artifacts, not as the source of truth for code behavior.
- The dashboard consumes MQTT live data and stores a bounded in-memory cache via `src/shared/stream_cache.py`. It does not write the live stream back into a durable CSV history.

## 2. Required Tools and Secrets

Required tools:

- Python 3.10+
- `pip`
- Docker Desktop, Colima, or another Docker Engine with `docker compose`
  - On macOS without Docker Desktop: `brew install colima docker` then `colima start` before `docker compose`
  - See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#local-docker-with-colima-macos)

Prefer the repository virtual environment if it exists. The current repo includes `.venv`, but do not assume that will always be true.

Important repo-specific note:

- In this repository, Codex will often incorrectly conclude that `pytest` or `pandas` is missing if it runs commands outside the project virtual environment.
- Before reporting missing test dependencies, first try:

```bash
source .venv/bin/activate
```

- If `.venv` exists and activation succeeds, run verification commands inside that environment before claiming local automated validation is blocked.
- Do not treat system-interpreter failures as authoritative if `.venv` exists and has not been tried yet.

Important environment variables:

- `OPEN_ELECTRICITY_API_KEY`
  - Required when `data/raw/open_electricity/consolidated_data_total.csv` is unavailable and the publisher must fetch from the Open Electricity API.
  - Not required when an existing `data/raw/open_electricity/consolidated_data_total.csv` is intentionally being reused.
- `MQTT_BROKER` / `MQTT_PORT`
  - Used by both the publisher and dashboard.
  - Default fallback is `127.0.0.1` and `1883`.
- `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT`
  - Older compatible fallback names supported by both publisher and dashboard.
- `MQTT_SUBSCRIBE_TOPIC_FILTER`
  - The dashboard default subscription is `comp5339/task123/measurements/#`.
- `MQTT_PUBLISH_TOPIC_TEMPLATE`
  - Provided in `.env.example` for publisher topic formatting, default `comp5339/task123/measurements/{facility_code}`.
- `MQTT_USERNAME` / `MQTT_PASSWORD`
  - Only needed if the broker requires authentication.
- `MAX_STREAM_ROWS`
- `RESET_INTERVAL_HOURS`
- `REFRESH_INTERVAL_SECONDS`
  - Legacy generic refresh helper defaulting to `1`; dashboard fragments use dedicated main/sidebar intervals.
Important notes:

- The repo includes `.env.example`, but the code does not auto-load `.env`.
- Environment variables must be injected by the shell, IDE configuration, or deployment platform.
- Do not assume `.env` already exists. Copy it from `.env.example` when needed.

## 3. Local Startup Order

Always run commands from the repository root.

### 3.1 Prepare the Python Environment

If `.venv` already exists:

```bash
source .venv/bin/activate
```

If `.venv` does not exist:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### 3.2 Start the Local MQTT Broker

```bash
docker compose up -d
```

Useful checks:

```bash
docker compose ps
docker compose logs -f mosquitto
```

Notes:

- `docker compose up -d` starts Mosquitto, publisher, and dashboard when using the default compose file.
- `docker compose up -d mosquitto` starts only the broker for manual Python runs.
- The default local broker endpoint is `127.0.0.1:1883`.

### 3.3 Prepare Environment Variables

If you want a local template file:

```bash
cp .env.example .env
```

Then inject values using your shell or tooling. At minimum verify:

- `MQTT_BROKER=127.0.0.1`
- `MQTT_PORT=1883`
- `OPEN_ELECTRICITY_API_KEY=<your key>` when a fresh API fetch is required

### 3.4 Start the Publisher

Prefer the wrapper used by Render:

```bash
python scripts/run_publisher.py
```

Equivalent direct entrypoint:

```bash
python3 -m src.publisher.cli
```

Behavior to remember:

- If `data/raw/open_electricity/consolidated_data_total.csv` does not exist, the script fetches API data and then generates:
  - `data/raw/open_electricity/facility_list.csv`
  - `data/raw/open_electricity/consolidated_data_total.csv`
  - `data/staging/open_electricity/facility_list_clean.csv`
  - `data/staging/open_electricity/consolidated_data_cleaned.csv`
  - `data/staging/facility_metadata/NGER_data_clean.csv`
  - `data/staging/facility_metadata/CER_data_clean.csv`
  - `data/mart/data_for_publish.csv`
  - `data/cache/facility_data_cache.json`
- If `data/raw/open_electricity/consolidated_data_total.csv` already exists, the script reuses it and continues through the remaining cleaning and publish pipeline.
- The publisher defaults to `127.0.0.1:1883` and also supports `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT`.

### 3.5 Start the Streamlit Dashboard

Recommended command:

```bash
streamlit run app/streamlit_app.py
```

Explicit port form:

```bash
python3 -m streamlit run app/streamlit_app.py --server.port 8501
```

Open:

```text
http://127.0.0.1:8501
```

Notes:

- The dashboard defaults to the same broker at `127.0.0.1:1883`.
- The default subscription topic is `comp5339/task123/measurements/#`.
- If MQTT is connected but no new data arrives yet, the dashboard should show the waiting notice instead of replaying sample data.

## 4. Verification Steps

Minimum local verification order:

1. Confirm dependencies are installed in the currently active Python interpreter.
   In this repo, if `.venv` exists, activate it first with `source .venv/bin/activate` before deciding `pytest`, `pandas`, or other test dependencies are missing.
2. Confirm the broker is up:

```bash
docker compose ps
```

3. Start the publisher and verify it is processing and publishing.
4. Start the dashboard and open `http://127.0.0.1:8501`.
5. Confirm the page is not failing on import or rendering blank, and that the status reaches `Connected` or at least shows the waiting notice before live data arrives.

Test command:

```bash
pytest -q
python -m src.publisher.qc.runner --no-write
```

QC notes:

- Structured QC lives in `src/publisher/qc/` with thresholds in `config/qc_thresholds.yaml` and production baseline in `config/qc_baseline.yaml`.
- Fixture unit tests use `tests/fixtures/qc/`; integration tests validate tracked `data/mart/data_for_publish.csv`.
- CI runs pytest and a standalone QC validate step.

Test caveat:

- This test file depends on the active interpreter having packages such as `pandas`, `streamlit`, and `paho-mqtt` installed.
- In this repository, the first recovery step is to activate the checked-in virtual environment with `source .venv/bin/activate` if that directory exists.
- If the project virtual environment is not active, or dependencies are not installed in the current interpreter, `pytest -q tests/test_dashboard_logic.py` can fail during import. Do not claim tests passed in that situation.
- Do not report "pytest is not installed" or "pandas is missing" until you have verified whether `.venv` exists and retried from the activated environment.
- Do not treat `python3 -m unittest tests.test_dashboard_logic` or `pytest -q tests/test_dashboard_logic.py` failures from the system interpreter as final if `.venv` exists but was not activated first.

Useful extra checks:

- Confirm `data/mart/data_for_publish.csv` exists if publisher input generation matters.
- If validating a fresh API fetch path, deliberately decide whether existing run artifacts should be reused before deleting anything.

## 5. Deployment Procedure

This repository supports two frontend-only cloud targets for the dashboard:

- Render: `https://nem-monitoring-dashboard.onrender.com`
- Streamlit Cloud: `https://nem-monitoring-dashboard.streamlit.app`

Both targets host only the Streamlit dashboard frontend. The publisher still runs through GitHub Actions, and MQTT traffic is relayed through an external HiveMQ broker.

Render deployment:

- `render.yaml` defines one Python service:
  - `nem-dashboard`: web, start command `streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT`
- Use the existing `render.yaml`. Do not convert deployment to `docker-compose`.
- Provision an external MQTT broker separately. HiveMQ is the intended cloud broker for the demo path.
- Set broker connection variables on the Render dashboard service:
  - `MQTT_BROKER`
  - `MQTT_PORT`
  - `MQTT_USERNAME` / `MQTT_PASSWORD` if authentication is required
  - `MQTT_TLS=true` for the HiveMQ TLS port
  - `MQTT_SUBSCRIBE_TOPIC_FILTER=comp5339/task123/measurements/#`
- Set GitHub Actions control variables on the Render dashboard service:
  - `ENABLE_GITHUB_ACTIONS_CONTROL=true`
  - `AUTO_START_PUBLISHER=true`
  - `AUTO_START_COOLDOWN_SECONDS=600`
  - `GITHUB_TOKEN`
  - `GITHUB_OWNER`
  - `GITHUB_REPO`
  - `GITHUB_WORKFLOW_FILE=publish-mqtt-on-demand.yml`
  - `GITHUB_REF=main`
- Keep the dashboard Streamlit bind behavior as `0.0.0.0:$PORT`, which is already defined in `render.yaml`.

Streamlit Cloud deployment:

- Use the same Streamlit entrypoint: `app/streamlit_app.py`
- Set the same MQTT and GitHub Actions environment variables as above
- Point `MQTT_BROKER` at the external HiveMQ host and keep `MQTT_TLS=true` for the cloud broker

GitHub Actions:

- Keep the publisher workflow on `workflow_dispatch`
- Pass `PUBLISH_DURATION_SECONDS=600` so it exits naturally after 10 minutes

Deployment boundary to remember:

- `render.yaml` does not provision Mosquitto
- Neither Render nor Streamlit Cloud deploys the publisher worker
- The dashboard subscribes directly to the external HiveMQ broker
- Do not transplant the local `docker compose up -d` workflow into cloud deployment

## 6. Common Failure Modes and Fixes

### 6.1 Publisher Fails Because the API Key Is Missing

Cause:

- `data/raw/open_electricity/consolidated_data_total.csv` is missing, so the script needs to fetch from the Open Electricity API.

Fix:

- Set `OPEN_ELECTRICITY_API_KEY`.
- Or confirm that reusing an existing cached artifact is the intended path instead of forcing a fresh fetch.

### 6.2 Dashboard Cannot Connect to MQTT

Cause:

- The broker is not running, or host and port configuration is wrong.

Fix:

```bash
docker compose ps
docker compose logs -f mosquitto
```

Then verify:

- `MQTT_BROKER`
- `MQTT_PORT`
- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`

### 6.3 Render Dashboard Starts but No Live Data Appears

Cause:

- Render does not provide a broker.
- The dashboard is not pointing at the external HiveMQ broker used by the publisher workflow.

Fix:

- Set the same external MQTT connection values in the dashboard and the GitHub Actions workflow.
- Do not assume `localhost:1883` is valid on Render or in GitHub Actions.

### 6.4 Dashboard Only Shows Waiting Notice

Cause:

- The publisher is not successfully publishing.
- The dashboard subscription and publisher topic are mismatched.
Fix:

- Verify the publisher is running.
- Then verify:
  - `MQTT_SUBSCRIBE_TOPIC_FILTER`
  - `MQTT_PUBLISH_TOPIC_TEMPLATE`
- If the page never leaves the waiting notice, check that the publisher is actually publishing and that the broker is reachable.

### 6.5 Tests Fail Locally but the Code May Not Be the Problem

Cause:

- The current Python interpreter does not have project dependencies installed.

Fix:

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest -q tests/test_dashboard_logic.py
```

### 6.6 Behavior Changed After Editing Files Under `data/`

Cause:

- Many files under `data/` are generated artifacts or caches and should not be treated as long-term source code truth.

Fix:

- Separate static input data from generated run output before debugging.
- For behavior changes, inspect Python source and configuration first instead of trusting generated CSVs.

## 7. Rules for Future Codex Edits

Before changing behavior, read these files first:

- `README.md`
- `render.yaml`
- `docker-compose.yml`
- `src/publisher/`
- `src/dashboard/render.py`
- `tests/test_dashboard_logic.py`

Operating rules:

- Do not assume `.env` exists. Copy from `.env.example` when needed.
- For verification, do not stop at the system interpreter. If `.venv` exists, run `source .venv/bin/activate` before concluding `pytest` or Python packages are missing.
- Never treat a missing-package failure from `python3 -m unittest tests.test_dashboard_logic` or `pytest -q tests/test_dashboard_logic.py` as authoritative until the same check has been retried inside `.venv`, if `.venv` exists.
- Do not claim tests passed unless dependencies are installed in the actual active interpreter and the test command was really run.
- Treat generated files under `data/` as run artifacts, not as the authoritative basis for code changes.
- Preserve the split between local broker orchestration and Render deployment of the single dashboard service plus the external HiveMQ-backed workflow.
- When changing entrypoint behavior, remember external callers may use the wrapper entrypoints:
  - `python scripts/run_publisher.py`
  - `streamlit run app/streamlit_app.py`
- If you are changing MQTT, cache, fallback, or deployment behavior, inspect the actual environment-variable reads in `src/dashboard/runtime.py`, `src/dashboard/settings.py`, and `src/shared/stream_cache.py` before updating code or docs.

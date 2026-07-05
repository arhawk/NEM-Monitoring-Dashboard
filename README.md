# NEM Monitoring Dashboard

Python project that fetches National Electricity Market related data, prepares publishable records, streams them over MQTT, and renders a Streamlit dashboard with a live map, metrics, and a table. The repository is structured as a small data pipeline plus a frontend that subscribes to the pipeline output.

## Key Features

- Open Electricity API ingestion for operational electricity data
- CER and NGER facility metadata ingestion and matching
- Deterministic cleaning and staging into `data/raw/`, `data/staging/`, `data/mart/`, and `data/cache/`
- MQTT publish/subscribe flow using `comp5339/task123/measurements/{facility_code}`
- Streamlit dashboard with a custom facility map component, summary cards, filters, and a cache reset action
- Ruff-based formatting and lint checks for low-cost style and error detection
- Optional GitHub Actions control for hosted deployments
- Lightweight tests for the dashboard and dotenv loader

## Tech Stack

- Python 3.10+
- Streamlit
- Pandas and NumPy
- Paho MQTT
- Requests
- Folium and `streamlit-folium`
- Docker Compose for the local Mosquitto broker

## Repository Structure

- `app/streamlit_app.py`: Streamlit wrapper entrypoint
- `scripts/run_publisher.py`: publisher wrapper entrypoint
- `src/publisher/`: fetch, clean, align, and publish data
- `src/dashboard/`: runtime state, MQTT subscriber, and Streamlit rendering
- `src/shared/`: shared dotenv, config, paths, topics, and stream cache helpers
- `broker/`: Mosquitto configuration and runtime volumes
- `data/`: tracked sample artifacts plus generated pipeline outputs
- `docs/`: architecture, configuration, deployment, and troubleshooting notes
- `tests/`: logic tests for the dashboard, publisher, and pipeline smoke coverage

## Architecture

```mermaid
flowchart LR
  A[Open Electricity API] --> P[Publisher]
  B[CER and NGER metadata] --> P
  P --> C[data/raw and data/staging artifacts]
  P --> M[MQTT broker]
  M --> D[Streamlit dashboard]
  D --> S[Bounded in-memory StreamCache]
  S --> V[Metrics, trend card, map, table]
```

The runtime flow is:

1. `src/__init__.py` loads a repo-root `.env` file if one exists.
2. `scripts/run_publisher.py` calls `src.publisher.cli.main()`.
3. The publisher prepares CSV artifacts when `data/mart/data_for_publish.csv` is missing, then streams rows as MQTT messages.
4. `app/streamlit_app.py` calls `src.dashboard.app.main()`.
5. The dashboard starts an MQTT client, stores accepted messages in a bounded `StreamCache`, and renders from the latest cached snapshot.

## Runbook

### 1. Start

Create a virtual environment, then install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure environment variables in your shell or in a repo-root `.env` file.

The code loads `.env` automatically when `src` is imported, so you do not need a separate dotenv loader.

Copy `.env.example` as a starting point if you want a full list of supported variables and defaults.

Start the local MQTT broker.

```bash
docker compose up -d
```

Start the publisher in one terminal:

```bash
python scripts/run_publisher.py
```

Start the dashboard in a second terminal:

```bash
streamlit run app/streamlit_app.py
```

Open `http://127.0.0.1:8501`.

### 2. Verify

Run the low-cost checks first:

```bash
ruff format --check .
ruff check .
pytest -q
```

If you want a narrower smoke pass while iterating on the main flow, run:

```bash
pytest -q tests/test_pipeline_smoke.py tests/test_dashboard_logic.py tests/test_dotenv_loader.py
```

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full environment variable matrix.

The most important values are:

- `MQTT_BROKER` / `MQTT_PORT` and the legacy `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` aliases
- `MQTT_SUBSCRIBE_TOPIC_FILTER` and `MQTT_PUBLISH_TOPIC_TEMPLATE`
- `OPEN_ELECTRICITY_API_KEY`
- `PUBLISH_DURATION_SECONDS`
- `FACILITY_METADATA_DATA_DIR`
- `MAX_STREAM_ROWS` and `RESET_INTERVAL_HOURS`
- `MAIN_REFRESH_INTERVAL_SECONDS` and `SIDEBAR_REFRESH_INTERVAL_SECONDS`
- `ENABLE_GITHUB_ACTIONS_CONTROL`, `AUTO_START_PUBLISHER`, and `AUTO_START_COOLDOWN_SECONDS`

## External Dependency Boundaries

- MQTT broker: if the broker is unavailable, the publisher cannot deliver live rows and the dashboard stays disconnected. The dashboard can still render its current in-memory cache until that cache is cleared or the process restarts.
- Open Electricity API: if the API key is missing or the remote API is unreachable, the publisher cannot rebuild fresh raw Open Electricity artifacts. If `data/mart/data_for_publish.csv` already exists, the publisher can keep replaying that file.
- CER and NGER sources: if the CER/NGER downloads are unavailable, the publisher cannot rebuild the facility metadata layer. Existing staged files can still be reused until they are deleted.
- Streamlit: if the dashboard process restarts, the in-memory stream cache is lost because the current UI state is not persisted to disk.
- GitHub Actions API: workflow controls are optional. If `ENABLE_GITHUB_ACTIONS_CONTROL=true` but `GITHUB_TOKEN` is missing or invalid, the sidebar controls fail closed and the rest of the dashboard remains usable.

### 3. Troubleshoot

- Confirm Mosquitto is running with `docker compose ps`.
- Confirm the publisher is running and writing to `comp5339/task123/measurements/{facility_code}`.
- If the dashboard shows disconnected, verify `MQTT_BROKER` and `MQTT_PORT` point to the broker you actually started.
- If the dashboard stays empty, confirm the publisher has generated `data/mart/data_for_publish.csv` and that the current cache is not stale.
- If you need a clean rebuild, remove the generated CSV and JSON artifacts under `data/` before restarting the publisher.

## Deployment Notes

- `docker-compose.yml` only starts Mosquitto. It does not start the Python services.
- `render.yaml` deploys the Streamlit frontend as a web service.
- The cloud dashboard is frontend-only; live data still depends on an MQTT broker.
- GitHub Actions control is optional and only works when `ENABLE_GITHUB_ACTIONS_CONTROL=true` and `GITHUB_TOKEN` is configured.

## Known Limitations

- The publisher reuses `data/mart/data_for_publish.csv` if it already exists.
- When the publisher must rebuild raw Open Electricity artifacts, it uses the historical window defined in `src/publisher/cli.py`.
- The dashboard keeps live state in memory; it does not persist a durable event history.
- Several features depend on external services; see the boundary notes above for the failure mode of each one.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/data_pipeline_and_missing_values.md](docs/data_pipeline_and_missing_values.md)

# NEM Monitoring Dashboard

This repository contains a local reproduction flow for the NEM monitoring dashboard:

1. Build the derived data from the raw CSV inputs.
2. Publish the prepared rows over MQTT.
3. Run the Streamlit dashboard and subscribe to the live feed.
4. Keep the live stream in a bounded in-memory cache inside the dashboard process.

The repository includes a local `.venv` for convenience. You can use that environment or create a fresh `venv`. Only the MQTT broker is containerised with Docker.

## Requirements

- Python 3.10+ recommended
- Docker Desktop or Docker Engine with Docker Compose
- Internet access for the Open Electricity API used by `src/publisher/cli.py`

## Project Layout

- `src/publisher/`: fetch, cleaning, alignment, and MQTT publishing modules
- `src/dashboard/`: dashboard runtime, data shaping, render logic, and map payload generation
- `src/dashboard/actions.py`: optional GitHub Actions control layer for the cloud demo
- `src/shared/stream_cache.py`: shared bounded cache and environment helpers
- `scripts/run_publisher.py`: Render-friendly wrapper for the publisher entrypoint
- `app/streamlit_app.py`: Render-friendly wrapper for the Streamlit entrypoint
- `archive/`: historical Task-era scripts kept out of the active tree
- `data/`: input CSV files and generated run artifacts
- `broker/`: Mosquitto configuration and persistence directories
- `docker-compose.yml`: starts the Mosquitto broker only

## Setup

### 1. Create and activate a virtual environment

If the repository already contains `.venv`, you can use it directly:

```bash
source .venv/bin/activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv venv
.\\venv\\Scripts\\Activate.ps1
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

## Start the MQTT Broker

If you use Colima on macOS, start it first:

```bash
colima start
```

Check Colima status with:

```bash
colima status
```

Then run the broker container locally on `localhost:1883`:

```bash
docker compose up -d
```

If your Docker installation only provides the legacy CLI, use `docker-compose up -d` instead.

Useful checks:

```bash
docker compose ps
docker compose logs -f mosquitto
```

Use the `docker-compose` form here as well if that is the only one installed.

Stop the broker with:

```bash
docker compose down
```

Or `docker-compose down` with the legacy CLI.

If you want to stop Colima itself, run:

```bash
colima stop
```

## Local Mode

Use this when you want to run everything manually on your machine. GitHub Actions is not required.

### 1. Generate the publish dataset

Run the publisher from the repository root:

```bash
python scripts/run_publisher.py
```

What it does:

- if `data/data_for_publish.csv` already exists, reuses it and starts publishing immediately
- otherwise fetches facility and market data from the Open Electricity API
- writes `data/facility_list.csv`
- writes `data/consolidated_data_total.csv`
- writes `data/consolidated_data_cleaned.csv`
- writes `data/data_for_publish.csv`
- connects to MQTT broker at `127.0.0.1:1883`
- begins publishing rows to `comp5339/task123/measurements/{facility_code}`

The publisher uses `MQTT_PUBLISH_TOPIC_TEMPLATE`, defaulting to `comp5339/task123/measurements/{facility_code}`.

If `data/consolidated_data_total.csv` already exists, the script reuses it instead of fetching again.

### 2. Start the dashboard

Open a second terminal, activate the same `venv`, then run:

```bash
streamlit run app/streamlit_app.py
```

The dashboard connects to the same broker at `127.0.0.1:1883` and subscribes to:

- `comp5339/task123/measurements/#`

The local Streamlit server binds to `127.0.0.1`, so the browser URL will show `http://127.0.0.1:8501`.

To stop the local app processes, use `Ctrl+C` in each terminal.

### Local Mode Summary

- Run the publisher manually with `python scripts/run_publisher.py`
- Run the dashboard manually with `streamlit run app/streamlit_app.py`
- Keep `ENABLE_GITHUB_ACTIONS_CONTROL=false`
- Leave `AUTO_START_PUBLISHER=false`

### Dashboard Architecture

The Streamlit dashboard now uses MQTT as the live stream and stores the latest messages in a bounded in-memory cache.

The cache keeps only the latest `MAX_STREAM_ROWS` messages, defaults to `5520`, and resets itself every `RESET_INTERVAL_HOURS` hours, default `6`.

- `nem_facility_data.csv` is not used as live stream storage.
- The dashboard can start even if `nem_facility_data.csv` is missing.
- `nem_facility_data.csv` may still be kept as optional/static reference data or publisher input if you want it for offline inspection.

Dashboard behavior:

- The top cards are computed from the current cache snapshot.
- The sidebar filters affect the map and table.
- The trend chart is built from cached MQTT messages.
- If MQTT is unavailable, the page stays up and shows a friendly waiting or disconnected state.

The dashboard uses these environment variables:

- `MQTT_BROKER`
- `MQTT_PORT`
- `MQTT_TLS`
- `MQTT_SUBSCRIBE_TOPIC_FILTER`
- `MQTT_PUBLISH_TOPIC_TEMPLATE`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MAX_STREAM_ROWS`
- `RESET_INTERVAL_HOURS`
- `MAIN_REFRESH_INTERVAL_SECONDS`
- `SIDEBAR_REFRESH_INTERVAL_SECONDS`

## Cloud Demo Mode

Render should host only the Streamlit dashboard. The dashboard auto-triggers a GitHub Actions publisher workflow on first load, and that workflow publishes MQTT data to an external HiveMQ broker for 10 minutes before exiting naturally.

The repository includes a `render.yaml` blueprint for the dashboard service only. Render does not deploy Mosquitto, and it does not run a publisher worker in this mode.

Cloud demo flow:

1. Render starts the Streamlit dashboard service.
2. On first load, the dashboard checks GitHub Actions for the configured publisher workflow.
3. If no run is active and the cooldown window has expired, the dashboard dispatches the workflow once for the current browser session.
4. GitHub Actions runs `python scripts/run_publisher.py` with `PUBLISH_DURATION_SECONDS=600`.
5. The publisher sends MQTT data to the external HiveMQ broker.
6. The dashboard subscribes directly to that HiveMQ MQTT topic and refreshes live.
7. When the publisher exits after 10 minutes, the dashboard stays up and either waits for the next run or falls back to cached/sample data.

GitHub repository secrets required by the workflow:

- `MQTT_BROKER`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `OPEN_ELECTRICITY_API_KEY` if the workflow needs to rebuild publish data

Render environment variables for the dashboard:

- `MQTT_BROKER=<your HiveMQ host>`
- `MQTT_PORT=8883`
- `MQTT_USERNAME=<your HiveMQ username>`
- `MQTT_PASSWORD=<your HiveMQ password>`
- `MQTT_TLS=true`
- `MQTT_SUBSCRIBE_TOPIC_FILTER=comp5339/task123/measurements/#`
- `MQTT_PUBLISH_TOPIC_TEMPLATE=comp5339/task123/measurements/{facility_code}`
- `ENABLE_GITHUB_ACTIONS_CONTROL=true`
- `AUTO_START_PUBLISHER=true`
- `AUTO_START_COOLDOWN_SECONDS=600`
- `GITHUB_TOKEN=<fine-grained GitHub token>`
- `GITHUB_OWNER=arhawk`
- `GITHUB_REPO=NEM-Monitoring-Dashboard`
- `GITHUB_WORKFLOW_FILE=publish-mqtt-on-demand.yml`
- `GITHUB_REF=main`
- `MAX_STREAM_ROWS=5520`
- `RESET_INTERVAL_HOURS=6`
- `ENABLE_FALLBACK_REPLAY=true`
- `FALLBACK_STALE_SECONDS=30`

The dashboard service command remains `streamlit run app/streamlit_app.py`, using the default `$PORT` provided by Render. There is no Render worker in this deployment path.

## Run Artifacts

These files are generated during normal execution:

- `data/facility_data_cache.json`
- `data/facility_list.csv`
- `data/consolidated_data_total.csv`
- `data/consolidated_data_cleaned.csv`
- `data/data_for_publish.csv`

If you need a clean rerun, delete the generated files above and run `python3 -m src.publisher.cli` again.

Live dashboard output is not written to CSV anymore. The bounded MQTT cache lives only in memory.

## Common Issues

- Broker connection fails: confirm Docker is running and port `1883` is free.
- Dashboard shows no live data: make sure the publisher is still running and the broker is reachable.
- Dashboard says waiting for MQTT messages: verify the publisher is sending to the same topic the dashboard subscribes to.
- Old data is being reused: remove the generated CSVs if you want to regenerate the publisher input data.
- API requests fail: the data preparation step needs outbound network access.

## Environment File

Copy `.env.example` to `.env` if you want local environment overrides for broker settings, cache size, refresh cadence, or soft reset cadence.

`MAIN_REFRESH_INTERVAL_SECONDS` controls the main dashboard heartbeat for the metrics cards, current facility panel, map, and table.
`SIDEBAR_REFRESH_INTERVAL_SECONDS` controls the lightweight sidebar heartbeat that keeps `Messages since reset` current even when MQTT traffic is slow.

For cloud brokers that require encrypted transport, set:

- `MQTT_TLS=true`
- `MQTT_PORT=8883`

Leave `MQTT_TLS=false` for the local Mosquitto broker on `1883`.

If you want the GitHub Actions controls active in a local preview environment, set `ENABLE_GITHUB_ACTIONS_CONTROL=true` and provide a fine-grained `GITHUB_TOKEN` with Actions read/write permission for this repository only. Keep `AUTO_START_PUBLISHER=false` unless you want the dashboard to dispatch the workflow automatically on load.

Security note:

- Use a fine-grained GitHub token scoped to this repository only.
- Grant `Actions: Read and write`.
- Grant `Metadata: Read`.
- Do not commit the token.

## Architecture Note

This is a portfolio/demo architecture. If you later need durable history, the cache can be replaced with a proper storage layer such as PostgreSQL, TimescaleDB, or InfluxDB without changing the MQTT publishing model.

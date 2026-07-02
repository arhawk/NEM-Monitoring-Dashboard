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
- Internet access for the Open Electricity API used by `Task1-3_data&MQTT.py`

## Project Layout

- `Task1-3_data&MQTT.py`: downloads and cleans data, creates `data/data_for_publish.csv`, then publishes MQTT messages
- `Task4_appStreamlit.py`: subscribes to MQTT, keeps a bounded in-memory cache, and renders the dashboard
- `scripts/run_publisher.py`: Render-friendly wrapper for the publisher entrypoint
- `app/streamlit_app.py`: Render-friendly wrapper for the Streamlit entrypoint
- `Task5_continousCheckReport.py`: optional MQTT timing check utility
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

## Reproduce the Data Flow

### 1. Generate the publish dataset

Run the data preparation script from the repository root:

```bash
python3 "Task1-3_data&MQTT.py"
```

What it does:

- fetches facility and market data from the Open Electricity API
- writes `data/facility_list.csv`
- writes `data/consolidated_data_total.csv`
- writes `data/consolidated_data_cleaned.csv`
- writes `data/data_for_publish.csv`
- connects to MQTT broker at `127.0.0.1:1883`
- begins publishing rows to `comp5339/task123/measurements/{facility_code}`

If `data/consolidated_data_total.csv` already exists, the script reuses it instead of fetching again.

### 2. Start the dashboard

Open a second terminal, activate the same `venv`, then run:

```bash
python3 -m streamlit run app/streamlit_app.py --server.port 8501
```

The dashboard connects to the same broker at `127.0.0.1:1883` and subscribes to:

- `comp5339/task123/measurements/#`

The local Streamlit server binds to `127.0.0.1`, so the browser URL will show `http://127.0.0.1:8501`.

To stop the local app processes, use `Ctrl+C` in each terminal.

### Dashboard Architecture

The Streamlit dashboard now uses MQTT as the live stream and stores the latest messages in a bounded in-memory cache.

The cache keeps only the latest `MAX_STREAM_ROWS` messages, defaults to `1000`, and resets itself every `RESET_INTERVAL_HOURS` hours, default `6`.

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
- `MQTT_TOPIC`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MAX_STREAM_ROWS`
- `RESET_INTERVAL_HOURS`
- `REFRESH_INTERVAL_SECONDS`

## Render Deployment

Render should run the application as two separate services, not through `docker-compose`:

- Publisher service command: `python scripts/run_publisher.py`
- Dashboard service command: `streamlit run app/streamlit_app.py`

This keeps the broker orchestration local for development while allowing Render to manage the publisher and dashboard independently.

The repository includes a `render.yaml` blueprint with those two services. Configure `MQTT_BROKER` and `MQTT_PORT` in Render to point both services at your MQTT broker, because the blueprint does not deploy Mosquitto.

Suggested Render environment variables:

- `MQTT_BROKER=<your broker host>`
- `MQTT_PORT=1883`
- `MQTT_TOPIC=comp5339/task123/measurements/#`
- For the Streamlit service, keep the default `$PORT` that Render provides.

## Optional Timing Check

`Task5_continousCheckReport.py` can be used to verify that the MQTT stream is arriving at the expected cadence:

```bash
python3 Task5_continousCheckReport.py --host localhost --port 1883
```

## Run Artifacts

These files are generated during normal execution:

- `data/facility_data_cache.json`
- `data/facility_list.csv`
- `data/consolidated_data_total.csv`
- `data/consolidated_data_cleaned.csv`
- `data/data_for_publish.csv`

If you need a clean rerun, delete the generated files above and run `Task1-3_data&MQTT.py` again.

Live dashboard output is not written to CSV anymore. The bounded MQTT cache lives only in memory.

## Common Issues

- Broker connection fails: confirm Docker is running and port `1883` is free.
- Dashboard shows no live data: make sure `Task1-3_data&MQTT.py` is still running and the broker is reachable.
- Dashboard says waiting for MQTT messages: verify the publisher is sending to the same topic the dashboard subscribes to.
- Old data is being reused: remove the generated CSVs if you want to regenerate the publisher input data.
- API requests fail: the data preparation step needs outbound network access.

## Environment File

Copy `.env.example` to `.env` if you want local environment overrides for broker settings, cache size, refresh cadence, or soft reset cadence.

## Architecture Note

This is a portfolio/demo architecture. If you later need durable history, the cache can be replaced with a proper storage layer such as PostgreSQL, TimescaleDB, or InfluxDB without changing the MQTT publishing model.

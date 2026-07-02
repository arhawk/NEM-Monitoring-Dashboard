# NEM Monitoring Dashboard

This repository contains a local reproduction flow for the NEM monitoring dashboard:

1. Build the derived data from the raw CSV inputs.
2. Publish the prepared rows over MQTT.
3. Run the Streamlit dashboard and subscribe to the live feed.

The Python application stays local in a `venv`. Only the MQTT broker is containerised with Docker.

## Requirements

- Python 3.10+ recommended
- Docker Desktop or Docker Engine with Docker Compose
- Internet access for the Open Electricity API used by `Task1-3_data&MQTT.py`

## Project Layout

- `Task1-3_data&MQTT.py`: downloads and cleans data, creates `data/data_for_publish.csv`, then publishes MQTT messages
- `Task4_appStreamlit.py`: subscribes to MQTT and renders the dashboard
- `scripts/run_publisher.py`: Render-friendly wrapper for the publisher entrypoint
- `app/streamlit_app.py`: Render-friendly wrapper for the Streamlit entrypoint
- `Task5_continousCheckReport.py`: optional MQTT timing check utility
- `data/`: input CSV files and generated run artifacts
- `broker/`: Mosquitto configuration and persistence directories
- `docker-compose.yml`: starts the Mosquitto broker only

## Setup

### 1. Create and activate a virtual environment

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

### Dashboard Metrics Semantics

The four cards at the top of the Streamlit dashboard are live snapshot metrics from `Task4_appStreamlit.py`.

In this repository, a "snapshot" means the dashboard's current in-memory set of all known facilities, where each facility is represented by its latest received record. It does not mean a fixed time window, and it does not mean cumulative generation over time.

- `Total Power Output MW`: sums the latest `power_value` for every facility currently stored in memory. This is a snapshot total, not a cumulative energy counter, so it can increase or decrease as new facility readings arrive.
- `Total CO2 Emissions tCO2e`: sums the latest `emission_value` for every facility currently stored in memory. This also can move up or down in real time.
- `Median Price $/MWh`: computes the median of all positive `price_per_mwh` values currently stored in memory.
- `Median Grid Demand MW`: computes the median of all positive `demand_mw` values currently stored in memory.

Important behavior notes:

- These metrics are calculated from the latest facility snapshot held by the dashboard process, across all facilities that have been observed so far.
- The sidebar filters currently affect the map and the facility preview table, but they do not change the four top summary metrics.
- If you want `Total Power Output MW` to be monotonic, it would need a code change to track accumulated generation instead of the current snapshot sum.

## Render Deployment

Render should run the application as two separate services, not through `docker-compose`:

- Publisher service command: `python scripts/run_publisher.py`
- Dashboard service command: `streamlit run app/streamlit_app.py`

This keeps the broker orchestration local for development while allowing Render to manage the publisher and dashboard independently.

The repository includes a `render.yaml` blueprint with those two services. Configure `MQTT_BROKER_HOST` and `MQTT_BROKER_PORT` in Render to point both services at your MQTT broker, because the blueprint does not deploy Mosquitto.

Suggested Render environment variables:

- `MQTT_BROKER_HOST=<your broker host>`
- `MQTT_BROKER_PORT=1883`
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

## Common Issues

- Broker connection fails: confirm Docker is running and port `1883` is free.
- Dashboard shows no live data: make sure `Task1-3_data&MQTT.py` is still running and the broker is reachable.
- Old data is being reused: remove the generated CSVs and cache file under `data/`.
- API requests fail: the data preparation step needs outbound network access.

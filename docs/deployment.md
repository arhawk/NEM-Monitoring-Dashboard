# Deployment and Operations

This document collects the details that are useful for running the project, but are too operational for the main README.

## Local Deployment

The local stack has three pieces:

- MQTT broker: Mosquitto via `docker compose`
- Publisher: `python scripts/run_publisher.py`
- Dashboard: `streamlit run app/streamlit_app.py`

Recommended startup order:

1. Activate the virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start Mosquitto with `docker compose up -d`.
4. Start the publisher.
5. Start the dashboard in a second terminal.

The local broker defaults to `127.0.0.1:1883`.

## Cloud Deployment

The hosted dashboard is intentionally frontend-only:

- Render runs the Streamlit app from `app/streamlit_app.py`
- Streamlit Cloud runs the same Streamlit entrypoint
- GitHub Actions can run the publisher on demand
- The live data path uses an external MQTT broker such as HiveMQ

The repository includes `render.yaml` for Render. Its start command is:

```bash
streamlit run app/streamlit_app.py --server.address 0.0.0.0 --server.port $PORT
```

## Environment Variables

### Broker and MQTT

- `MQTT_BROKER`: broker host, default `127.0.0.1`
- `MQTT_PORT`: broker port, default `1883`
- `MQTT_TLS`: enable TLS when connecting to remote brokers
- `MQTT_USERNAME` and `MQTT_PASSWORD`: optional broker credentials
- `MQTT_SUBSCRIBE_TOPIC_FILTER`: dashboard subscription topic, default `comp5339/task123/measurements/#`
- `MQTT_PUBLISH_TOPIC_TEMPLATE`: publisher topic template, default `comp5339/task123/measurements/{facility_code}`

### Data Preparation

- `OPEN_ELECTRICITY_API_KEY`: required when the publisher needs to fetch fresh data from the API
- `PUBLISH_DURATION_SECONDS`: how long the timed publisher should run in cloud mode
- `ASSIGNMENT1_DATA_DIR`: optional source directory for raw Assignment 1 CSVs (`NGER_data.csv` and `CER_data.csv`)

The publisher now uses layered artifact folders under `data/`:

- `data/raw/open_electricity/`
- `data/raw/assignment1/`
- `data/staging/open_electricity/`
- `data/staging/assignment1/`
- `data/mart/`
- `data/cache/`

### Dashboard Runtime

- `MAX_STREAM_ROWS`: bounded cache size for live messages
- `RESET_INTERVAL_HOURS`: soft reset cadence for the dashboard cache
- `MAIN_REFRESH_INTERVAL_SECONDS`: refresh cadence for the main dashboard panel
- `SIDEBAR_REFRESH_INTERVAL_SECONDS`: refresh cadence for the sidebar
- `MQTT_MONITOR_INTERVAL_SECONDS`: background connection monitor interval

### Cloud Control

- `ENABLE_GITHUB_ACTIONS_CONTROL`: enables workflow control buttons in the dashboard
- `AUTO_START_PUBLISHER`: auto-dispatches the publisher workflow when control is enabled
- `AUTO_START_COOLDOWN_SECONDS`: cooldown before a repeated auto-start is allowed
- `GITHUB_TOKEN`: fine-grained token with Actions read/write access to this repository
- `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_WORKFLOW_FILE`, `GITHUB_REF`: workflow lookup settings

## Generated Artifacts

These files are created during normal publisher runs:

- `data/raw/assignment1/NGER_data.csv`
- `data/raw/assignment1/CER_data.csv`
- `data/raw/open_electricity/facility_list.csv`
- `data/raw/open_electricity/consolidated_data_total.csv`
- `data/staging/assignment1/NGER_data_clean.csv`
- `data/staging/assignment1/CER_data_clean.csv`
- `data/staging/open_electricity/facility_list_clean.csv`
- `data/staging/open_electricity/consolidated_data_cleaned.csv`
- `data/mart/data_for_publish.csv`
- `data/cache/facility_data_cache.json`

If you want a clean rebuild, remove the generated CSV and JSON artifacts before starting the publisher again.

## Common Issues

- Broker connection fails: confirm Docker is running and port `1883` is free.
- Dashboard stays disconnected: verify the publisher is running and the topic filter matches the publisher topic.
- API fetch fails: check `OPEN_ELECTRICITY_API_KEY` and network access.
- Old data keeps reappearing: delete the generated artifacts and rebuild the publish dataset.
- Cloud dashboard cannot control GitHub Actions: check `ENABLE_GITHUB_ACTIONS_CONTROL` and the `GITHUB_TOKEN` scopes.

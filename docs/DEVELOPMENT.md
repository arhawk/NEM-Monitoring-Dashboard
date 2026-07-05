# Development

## Prerequisites

- Python 3.10+
- `pip`
- Docker Compose

## Local Workflow

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Start the local MQTT broker.

```bash
docker compose up -d
```

4. Run the publisher.

```bash
python scripts/run_publisher.py
```

5. Run the dashboard in a second terminal.

```bash
streamlit run app/streamlit_app.py
```

## Working With Data Artifacts

The publisher reads and writes files under `data/`:

- `data/raw/open_electricity/`
- `data/raw/facility_metadata/`
- `data/staging/open_electricity/`
- `data/staging/facility_metadata/`
- `data/mart/data_for_publish.csv`
- `data/cache/facility_data_cache.json`

If you want a clean rebuild, remove the generated CSV and JSON artifacts before starting the publisher again.

## Entry Points

- `python scripts/run_publisher.py`
- `python -m src.publisher.cli`
- `streamlit run app/streamlit_app.py`

The wrapper scripts exist so the same code works in local terminals and on hosted platforms.

## Tests

Run the available checks with:

```bash
pytest -q tests/test_dashboard_logic.py tests/test_dotenv_loader.py
```

The repository does not define a separate lint or type-check command.

## Development Notes

- `src/__init__.py` loads a repo-root `.env` file when the package is imported.
- The dashboard uses a cached `DashboardRuntime`; restarting the Streamlit process is the cleanest way to reset process-level state.
- The map is rendered through a custom Streamlit component, so changes to the frontend live under `src/dashboard/components/nem_map_component_frontend/`.

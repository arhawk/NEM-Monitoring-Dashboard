# Development

Use [README.md](../README.md) as the canonical start, verify, and troubleshoot runbook.

## Data Artifact Lifecycle

The `data/` tree is a layered set of runtime artifacts, not source code.

| Path | Role | Producer | Can delete? | Rebuild path |
| --- | --- | --- | --- | --- |
| `data/raw/open_electricity/` | Raw Open Electricity extracts | Publisher fetch pipeline | Yes | Delete to force a fresh API fetch |
| `data/raw/facility_metadata/` | Raw CER and NGER downloads | Publisher fetch pipeline | Yes | Delete to re-download source files |
| `data/staging/open_electricity/` | Cleaned Open Electricity tables | Publisher cleaning pipeline | Yes | Delete to regenerate from `data/raw/open_electricity/` |
| `data/staging/facility_metadata/` | Cleaned CER and NGER tables | Publisher cleaning pipeline | Yes | Delete to regenerate from `data/raw/facility_metadata/` |
| `data/mart/data_for_publish.csv` | Publish-ready dataset consumed by the MQTT publisher | Publisher alignment pipeline | Yes | Delete to rebuild the full publish dataset |
| `data/cache/facility_data_cache.json` | Cached API payloads for the Open Electricity fetcher | Publisher runtime cache | Yes | Delete to force cache warm-up on next run |

Practical rules:

- Treat the code under `src/`, `app/`, `scripts/`, `tests/`, `docs/`, and `broker/` as source of truth.
- Treat the `data/` directories above as derived artifacts.
- It is safe to delete any of the generated files above when you want a clean rebuild; the publisher will recreate them on demand.
- Rebuilding `data/raw/` can be expensive because it depends on external API and download availability.

## Local Docker With Colima (macOS)

Use [Colima](https://github.com/abiosoft/colima) when you want `docker compose` on macOS without Docker Desktop. Colima provides the Docker engine; this repository still uses the same Compose commands afterward.

### Install

```bash
brew install colima docker docker-compose
```

Optional: confirm the CLI works.

```bash
colima version
docker compose version
```

### First-Time Start

```bash
colima start
```

Default profile is usually enough for this repo (Mosquitto on port `1883`, optional publisher/dashboard containers). If you want an explicit profile:

```bash
colima start --cpu 2 --memory 4 --disk 20
```

Verify the daemon is reachable:

```bash
docker ps
```

Expected: command succeeds with an empty or running container list. If you see `Cannot connect to the Docker daemon`, Colima is not running yet.

### Run This Project

From the repository root, after Colima is up:

**One command (creates `.venv`, copies `.env` if missing, starts the stack):**

```bash
chmod +x scripts/start_local.sh
./scripts/start_local.sh
```

**Or Compose only:**

```bash
docker compose up --build
```

Open `http://127.0.0.1:8501`.

**Broker only** (publisher and dashboard run on the host with Python):

```bash
docker compose up -d mosquitto
python scripts/run_publisher.py
streamlit run app/streamlit_app.py
```

### Day-To-Day Commands

```bash
colima status          # is the VM running?
docker compose ps      # are nem-mosquitto / publisher / dashboard up?
docker compose logs -f mosquitto
docker compose down    # stop project containers
colima stop            # stop the Colima VM (optional)
```

### Common Colima Issues

| Symptom | Fix |
| --- | --- |
| `Cannot connect to the Docker daemon` | Run `colima start`, then retry `docker ps` |
| Port `1883` already in use | Stop the other broker or change the host port mapping in `docker-compose.yml` |
| Colima started but compose is slow on first run | Normal on first `docker compose up --build`; images are being pulled/built |
| Switched from Docker Desktop | Run `colima start` and ensure `docker context` points at Colima (`docker context ls`) |

Colima is a local development option only. Cloud deployment still uses external MQTT brokers; see [DEPLOYMENT.md](DEPLOYMENT.md).

## Entry Points

- `python scripts/run_publisher.py`
- `python -m src.publisher.cli`
- `streamlit run app/streamlit_app.py`

The wrapper scripts exist so the same code works in local terminals and on hosted platforms.

## Tests

Run the available checks with:

```bash
ruff format --check .
ruff check .
pytest -q
```

## Development Notes

- `src/__init__.py` loads a repo-root `.env` file when the package is imported.
- The dashboard uses a cached `DashboardRuntime`; restarting the Streamlit process is the cleanest way to reset process-level state.
- The map is rendered through a custom Streamlit component, so frontend changes live under `src/dashboard/components/nem_map_component_frontend/`.
- If you are debugging data freshness, delete `data/mart/data_for_publish.csv` and the cache JSON, then restart the publisher so it rebuilds from upstream inputs.


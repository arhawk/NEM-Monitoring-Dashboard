# Portfolio Guide

Use this document when presenting the project in interviews, on a resume, or in a portfolio site.

## One-Line Pitch

Built an end-to-end Australian National Electricity Market monitoring system that ingests multi-source energy data, publishes facility-level measurements over MQTT, and renders a live Streamlit dashboard with a custom Leaflet map.

## What Problem It Solves

Energy market operators and analysts need a consolidated view of facility-level generation and emissions signals across regions and fuel types. This project demonstrates how to:

1. Collect data from heterogeneous sources
2. Clean and align records into a publishable dataset
3. Stream updates in near real time
4. Present the stream in an operator-friendly dashboard

## Architecture Talking Points

### 1. Data Pipeline (`src/publisher/`)

- **Ingestion**: Open Electricity API for operational metrics; CER/NGER for facility metadata
- **Layered storage**: `data/raw/` → `data/staging/` → `data/mart/`
- **Deterministic transforms**: cleaning, deduplication, and metadata joins are isolated in testable modules
- **Configurable fetch window**: `FETCH_DATE_START` and `FETCH_DATE_END` remove hard-coded date ranges

### 2. Streaming Layer (MQTT + cache)

- **Publisher**: emits one JSON record per facility to `comp5339/task123/measurements/{facility_code}`
- **Subscriber**: dashboard listens on `comp5339/task123/measurements/#`
- **Bounded cache**: `StreamCache` caps memory with `MAX_STREAM_ROWS`
- **Resilience**: background reconnect monitor and periodic soft reset
- **Persistence**: optional disk snapshot (`STREAM_CACHE_SNAPSHOT_PATH`) restores the latest cached messages after process restarts

### 3. Dashboard (`src/dashboard/`)

- **Streamlit fragments** refresh the main panel and sidebar independently
- **Custom map component** (`nem_map_component_frontend/`) uses Leaflet for facility-level geospatial context
- **Operational sidebar** exposes MQTT status, filters, and reset controls

## Demo Paths

### Local Full Stack

```bash
docker compose up --build
```

Open `http://127.0.0.1:8501`.

### Cloud Demo (Render + GitHub Actions)

1. Deploy the dashboard with `render.yaml`
2. Configure dashboard env vars for your MQTT broker
3. Trigger `publish-mqtt-on-demand.yml` to stream demo data for a timed window
4. Optionally enable sidebar GitHub Actions controls with `ENABLE_GITHUB_ACTIONS_CONTROL=true`

## Engineering Evidence

| Area | Where to point reviewers |
| --- | --- |
| CI | `.github/workflows/ci.yml` |
| Tests | `tests/test_dashboard_logic.py`, `tests/test_portfolio_features.py` |
| Lint/format | `pyproject.toml`, Ruff in CI |
| Deployment | `render.yaml`, `docker-compose.yml`, `Dockerfile` |
| Docs | `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md` |

## Suggested Resume Bullets

- Built a Python data pipeline that ingests Open Electricity API and government facility metadata, stages layered CSV artifacts, and publishes aligned facility records over MQTT.
- Implemented a Streamlit real-time dashboard with a custom Leaflet map component, bounded in-memory stream cache, reconnect monitoring, and optional disk snapshot persistence.
- Added CI, Docker Compose full-stack orchestration, and Render deployment support for reproducible demos.

## Common Interview Questions

**Why MQTT instead of polling a database?**

MQTT fits event-style facility updates and keeps the dashboard decoupled from the publisher. The dashboard can subscribe without knowing how the dataset was produced.

**How do you prevent unbounded memory growth?**

`StreamCache` uses a fixed-size deque (`MAX_STREAM_ROWS`). Old messages drop off automatically while the latest facility snapshot remains available for map and table rendering.

**What happens when the broker disconnects?**

The runtime marks status as disconnected, retries on a cooldown, and keeps serving the last cached snapshot until a soft reset or process restart clears it.

**What would you add next?**

- Timeseries database for durable history
- Prometheus metrics for publisher throughput and dashboard lag
- Authentication in front of the Streamlit app for public demos

## Files Worth Screenshots

1. Dashboard map with facility markers and legend
2. Sidebar showing MQTT connected status and filters
3. `data/` directory showing raw/staging/mart layers
4. GitHub Actions CI passing on a PR

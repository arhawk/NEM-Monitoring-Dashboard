# Configuration

Environment variables are read from the process environment. `src/__init__.py` also loads a repo-root `.env` file if one exists.

If a value is missing or blank, the code falls back to the default below. For numeric settings, malformed values also fall back to the default instead of crashing at import time.

## MQTT And Broker

| Variable | Default | Scope | Notes |
| --- | --- | --- | --- |
| `MQTT_BROKER` | `127.0.0.1` | Publisher, dashboard | Primary broker host |
| `MQTT_BROKER_HOST` | `127.0.0.1` | Publisher, dashboard | Legacy host alias, used only when `MQTT_BROKER` is unset |
| `MQTT_PORT` | `1883` | Publisher, dashboard | Primary broker port |
| `MQTT_BROKER_PORT` | `1883` | Publisher, dashboard | Legacy port alias, used only when `MQTT_PORT` is unset |
| `MQTT_TLS` | `false` | Publisher, dashboard | Accepts `1`, `true`, `yes`, or `on` |
| `MQTT_USERNAME` | unset | Publisher, dashboard | Optional broker username |
| `MQTT_PASSWORD` | unset | Publisher, dashboard | Optional broker password |
| `MQTT_SUBSCRIBE_TOPIC_FILTER` | `comp5339/task123/measurements/#` | Dashboard | Subscription filter used by the live UI |
| `MQTT_PUBLISH_TOPIC_TEMPLATE` | `comp5339/task123/measurements/{facility_code}` | Publisher | Topic template used when publishing messages |

## Data Fetching And Publishing

| Variable | Default | Scope | Notes |
| --- | --- | --- | --- |
| `OPEN_ELECTRICITY_API_KEY` | required | Publisher | Needed only when the publisher must fetch fresh Open Electricity data |
| `PUBLISH_DURATION_SECONDS` | `0` | Publisher | `0` means run continuously; positive values enable timed publish mode |
| `FACILITY_METADATA_DATA_DIR` | `data/raw/facility_metadata` | Publisher | Optional override for the raw CER/NGER source directory |
| `FETCH_DATE_START` | `2025-10-24T23:00:00` | Publisher | ISO datetime used when fetching Open Electricity data |
| `FETCH_DATE_END` | `2025-10-31T22:59:59` | Publisher | ISO datetime used when fetching Open Electricity data |

## Dashboard Runtime

| Variable | Default | Scope | Notes |
| --- | --- | --- | --- |
| `MAX_STREAM_ROWS` | `5520` | Dashboard | Maximum number of cached MQTT messages |
| `RESET_INTERVAL_HOURS` | `6` | Dashboard | Soft-reset interval for the in-memory cache |
| `MAIN_REFRESH_INTERVAL_SECONDS` | `1` | Dashboard | Refresh cadence for the main Streamlit fragment |
| `SIDEBAR_REFRESH_INTERVAL_SECONDS` | `1` | Dashboard | Refresh cadence for the sidebar fragment |
| `MQTT_MONITOR_INTERVAL_SECONDS` | `5` | Dashboard | Background monitor interval for reconnect and soft-reset checks |
| `STREAM_CACHE_SNAPSHOT_PATH` | `data/cache/stream_cache_snapshot.json` | Dashboard | Disk snapshot path; set to `off` to disable persistence |
| `STREAM_CACHE_PERSIST_EVERY_MESSAGES` | `100` | Dashboard | Snapshot write frequency while messages are streaming in |

## GitHub Actions Control

| Variable | Default | Scope | Notes |
| --- | --- | --- | --- |
| `ENABLE_GITHUB_ACTIONS_CONTROL` | `false` | Dashboard | Shows workflow controls in the sidebar |
| `AUTO_START_PUBLISHER` | `false` | Dashboard | Auto-dispatches the publisher workflow once per session |
| `AUTO_START_COOLDOWN_SECONDS` | `600` | Dashboard | Cooldown window used to suppress repeated dispatches |
| `GITHUB_TOKEN` | unset | Dashboard | Required for workflow API calls |
| `GITHUB_OWNER` | `arhawk` | Dashboard | Repository owner used by the workflow API client |
| `GITHUB_REPO` | `NEM-Monitoring-Dashboard` | Dashboard | Repository name used by the workflow API client |
| `GITHUB_WORKFLOW_FILE` | `publish-mqtt-on-demand.yml` | Dashboard | Workflow file used for lookups and dispatches |
| `GITHUB_REF` | `main` | Dashboard | Branch used for workflow lookup and dispatch |

## Defaulting Rules

- Primary variable names win over legacy aliases.
- Legacy MQTT aliases are kept for compatibility with older shells and deployment environments.
- Blank strings are treated the same as unset values.
- Invalid numeric values fall back to the documented default.
- `OPEN_ELECTRICITY_API_KEY` is only required on the fetch path; loading modules that do not fetch remote data does not require it.


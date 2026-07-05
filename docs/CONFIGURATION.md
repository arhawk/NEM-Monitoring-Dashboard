# Configuration

Environment variables are read directly from the process environment. `src/__init__.py` also loads a repo-root `.env` file if one exists.

## MQTT And Broker

| Variable | Default | Used By | Notes |
| --- | --- | --- | --- |
| `MQTT_BROKER` | `127.0.0.1` | Publisher, dashboard | Preferred broker host |
| `MQTT_BROKER_HOST` | `127.0.0.1` | Publisher, dashboard | Legacy fallback when `MQTT_BROKER` is unset |
| `MQTT_PORT` | `1883` | Publisher, dashboard | Preferred broker port |
| `MQTT_BROKER_PORT` | `1883` | Publisher, dashboard | Legacy fallback when `MQTT_PORT` is unset |
| `MQTT_TLS` | `false` | Publisher, dashboard | Enables TLS when set to `1`, `true`, `yes`, or `on` |
| `MQTT_USERNAME` | unset | Publisher, dashboard | Optional broker username |
| `MQTT_PASSWORD` | unset | Publisher, dashboard | Optional broker password |
| `MQTT_SUBSCRIBE_TOPIC_FILTER` | `comp5339/task123/measurements/#` | Dashboard | Subscription wildcard |
| `MQTT_PUBLISH_TOPIC_TEMPLATE` | `comp5339/task123/measurements/{facility_code}` | Publisher | Topic template used for publish messages |

## Data Fetching And Publishing

| Variable | Default | Used By | Notes |
| --- | --- | --- | --- |
| `OPEN_ELECTRICITY_API_KEY` | unset | Publisher | Required when raw Open Electricity data must be fetched |
| `PUBLISH_DURATION_SECONDS` | `0` | Publisher | Timed publish mode; `0` means run continuously |
| `FACILITY_METADATA_DATA_DIR` | unset | Publisher | Optional source directory for raw `NGER_data.csv` and `CER_data.csv` |

## Dashboard Runtime

| Variable | Default | Used By | Notes |
| --- | --- | --- | --- |
| `MAX_STREAM_ROWS` | `5520` | Dashboard | Maximum number of cached MQTT messages |
| `RESET_INTERVAL_HOURS` | `6` | Dashboard | Soft-reset interval for the in-memory cache |
| `MAIN_REFRESH_INTERVAL_SECONDS` | `1` | Dashboard | Refresh cadence for the main fragment |
| `SIDEBAR_REFRESH_INTERVAL_SECONDS` | `1` | Dashboard | Refresh cadence for the sidebar fragment |
| `MQTT_MONITOR_INTERVAL_SECONDS` | `5` | Dashboard | Background monitor interval |

## GitHub Actions Control

| Variable | Default | Used By | Notes |
| --- | --- | --- | --- |
| `ENABLE_GITHUB_ACTIONS_CONTROL` | `false` | Dashboard | Shows workflow controls in the sidebar |
| `AUTO_START_PUBLISHER` | `false` | Dashboard | Auto-dispatches the publisher workflow once per session |
| `AUTO_START_COOLDOWN_SECONDS` | `600` | Dashboard | Cooldown window used to block repeated dispatches |
| `GITHUB_TOKEN` | unset | Dashboard | Required for workflow API calls |
| `GITHUB_OWNER` | `arhawk` | Dashboard | Repository owner used for Actions API calls |
| `GITHUB_REPO` | `NEM-Monitoring-Dashboard` | Dashboard | Repository name used for Actions API calls |
| `GITHUB_WORKFLOW_FILE` | `publish-mqtt-on-demand.yml` | Dashboard | Workflow file name |
| `GITHUB_REF` | `main` | Dashboard | Branch used for workflow lookup and dispatch |

## Notes

- The code does not ship a `.env.example` file.
- Environment variables can be injected from the shell, CI, hosting platform, or a local `.env` file.
- The dashboard and publisher both accept the legacy `MQTT_BROKER_HOST` and `MQTT_BROKER_PORT` names for compatibility.

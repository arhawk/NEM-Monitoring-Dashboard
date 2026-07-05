# Data Pipeline and Missing Values

This note describes the current repository implementation. It is intentionally limited to what the code actually does.

## End-to-End Flow

1. Fetch raw electricity and facility data from the Open Electricity API.
2. Download CER and NGER metadata if the raw files are missing.
3. Clean and stage the data into layered CSV artifacts under `data/`.
4. Merge operational rows with facility metadata.
5. Write the publish-ready CSV to `data/mart/data_for_publish.csv`.
6. Publish MQTT messages from the CSV.
7. Subscribe to the live stream in the Streamlit dashboard and render from the latest cached snapshot.

## Raw And Staged Artifacts

- `data/raw/open_electricity/`: raw Open Electricity extracts
- `data/raw/facility_metadata/`: raw CER and NGER downloads
- `data/staging/open_electricity/`: cleaned Open Electricity tables
- `data/staging/facility_metadata/`: cleaned metadata tables
- `data/mart/`: publish-ready data
- `data/cache/`: publisher cache state

## Cleaning Rules

The main cleaning functions live in `src/publisher/data/cleaning.py` and `src/publisher/data/facility_metadata.py`.

### Operational Data

- Negative `Power (MW)` and `Emissions (tonnes)` values are replaced with `0`.
- Facilities with both `Power (MW)` and `Emissions (tonnes)` entirely missing are dropped.
- Partial gaps in those two series are filled by splitting the gap into a forward-fill half and a backward-fill half.
- `Price ($/MWh)` and `Demand (MW)` keep missing values as `NaN`.

### Facility Metadata

- `facility_code` and `facility_name` are trimmed and deduplicated.
- NGER rows with notes or type `C` are removed by the current cleaning rules.
- CER station names are normalised by stripping suffixes after `-`.
- The staging step keeps the columns needed for the publish dataset and map rendering.

## Publish Payload

The MQTT publisher reads `data/mart/data_for_publish.csv` and emits JSON messages with:

- `facility_code`
- `facility_name`
- `timestamp`
- `state`
- `fuel_list`
- `power_value`
- `emission_value`
- `price_per_mwh`
- `demand_mw`
- `lat`
- `lng`
- `unit`
- sequencing and timing fields used by the publisher loop

The publish topic template defaults to `comp5339/task123/measurements/{facility_code}`.

## Dashboard Receive Path

The dashboard accepts only messages that contain valid:

- `facility_code`
- `lat`
- `lng`
- `power_value`

After normalization, messages are stored in the bounded in-memory `StreamCache` and aggregated into:

- the latest snapshot used for metrics and filtering
- the trend card shown above the map
- the table preview
- the map payload consumed by the custom component

## Notes

- Missing data is shown as `N/A` in the dashboard where appropriate.
- The dashboard does not persist a historical event log.
- The current publisher rebuild path uses a hard-coded historical Open Electricity window in `src/publisher/cli.py` when the raw consolidated file is absent.
- the map

### 6.3 What "Real-Time" Means Here

In this project, "real-time" means that the dashboard consumes messages as they arrive on the MQTT broker and renders the latest cached state on a repeating refresh cycle.

That is different from hard real-time processing:

- the publisher streams one JSON record per row over MQTT
- the dashboard receives each message in the MQTT `on_message` callback
- the UI reruns on a fixed interval and redraws from the in-memory cache

The timestamps in the system have different meanings:

- `timestamp` is the business timestamp from the source data
- `sent_mono_ns` is when the publisher sent the MQTT message
- `received_at` is when the dashboard stored the message in cache

So the dashboard is best described as **near-real-time** or **live-streamed**:

- the transport is live
- the UI is updated continuously
- the source measurements may still represent historical 5-minute intervals from the API
- the display is not a hard real-time control loop

This distinction matters when reading charts or tables:

- `timestamp` tells you when the measurement belongs in the source timeline
- `received_at` tells you when the dashboard learned about it
- the visible latency between them is expected and depends on publishing cadence, broker delivery, and Streamlit refresh timing

## 7. Dashboard Rendering

### 7.1 Metric Cards

The top cards show aggregated values from the current snapshot:

- total power output
- total CO2 emissions
- median price
- median grid demand

Missing optional values are not treated as zero:

- if no valid samples exist, the card shows `N/A`
- if valid samples exist, the aggregate is computed only from those samples

### 7.2 Table View

The table shows the latest record per facility and includes the core operational columns.

For missing optional values:

- they remain blank or missing in the underlying data
- they are not fabricated as zeros

### 7.3 Trend Chart

The trend chart is built from recent MQTT messages.

Missing values are handled as gaps:

- numeric conversion uses missing markers instead of zero-fill
- the SVG line breaks at missing points
- absent data does not draw a fake flat line at zero

### 7.4 Map View

The map shows facility markers with a popup and tooltip.

The cache signature now includes the fields that affect what the user sees:

- coordinates
- facility name
- state
- fuel type
- timestamp
- power value
- emission value
- price
- demand

This ensures the map refreshes when a facility’s displayed values change, even if the coordinates do not.

Missing display values are shown as `N/A` in the popup instead of `0`.

## 8. Missing-Value Policy by Stage

| Stage | Required fields | Optional fields | Behavior |
| --- | --- | --- | --- |
| Raw API ingestion | `facility_code`, `lat`, `lng`, `power_value` for dashboard acceptance | `emission_value`, `price_per_mwh`, `demand_mw` | Accept required fields, preserve optional missing values |
| Cleaning | Valid timestamps, stable schema, non-negative core metrics | Optional market metrics | Preserve `NaN` for genuinely missing data |
| Publishing | Core payload fields and coordinates | Optional metrics | Publish `None`/missing optional metrics as-is |
| Subscription | `facility_code`, `lat`, `lng`, `power_value` | Optional metrics | Skip invalid records, keep optional fields missing |
| Dashboard rendering | Snapshot must contain at least one valid facility row | Optional metrics | Show `N/A`, ignore missing values in aggregates |

## 9. Report vs Current Code

The report describes the intended pipeline and the current code follows that overall design, with one important clarification:

- the dashboard currently preserves missing optional metrics as missing values rather than converting them to zero

That clarification is important because it keeps these two cases separate:

- actual measured zero
- no data available

This is the correct interpretation for downstream charts, summary cards, and map popups.

## 10. Practical Notes

- `data/mart/data_for_publish.csv` is the cleaned publish-ready artifact.
- `nem_facility_data.csv` is not used as live dashboard storage anymore; the dashboard relies on MQTT plus in-memory cache.
- The system is designed to keep running even if the MQTT broker drops temporarily, but publish confirmation is required before advancing the data cursor.

## 11. Files to Read Next

- `src/publisher/`
- `src/dashboard/`
- `archive/`
- `README.md`
- `tests/test_dashboard_logic.py`

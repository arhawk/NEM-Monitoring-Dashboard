# NEM Monitoring Dashboard Data Pipeline and Missing-Value Policy

This document describes the end-to-end data flow for the project, from data retrieval to cleaning, publishing, subscription, and dashboard rendering.

It is written against two sources of truth:

- the current repository implementation
- the assignment report in `A2Report.pdf`

Where the report and current code differ in wording or behavior, this document calls that out explicitly.

The active implementation is CSV-artifact-backed plus MQTT-backed for live delivery. It does not currently persist the stream into SQLite, PostgreSQL, or Parquet; those are optional future extensions rather than part of the present pipeline.

## 1. End-to-End Flow

The project follows a simple pipeline:

1. Fetch raw electricity and facility data from the Open Electricity API.
2. Clean and standardize the data.
3. Merge operational data with Assignment 1 static metadata.
4. Publish the cleaned rows as MQTT messages.
5. Subscribe to the live stream in the dashboard.
6. Render tables, charts, and maps from the latest cached messages.

The two main code entry points are:

- `src/publisher/`: data retrieval, cleaning, integration, and MQTT publishing
- `src/dashboard/`: MQTT subscription, in-memory caching, and Streamlit visualization
- `src/shared/stream_cache.py`: shared bounded cache utilities

## 2. Data Retrieval

### 2.1 Source Endpoints

The project uses the Open Electricity API endpoints described in the report:

- `/v4/facilities/`
  - returns facility code, facility name, and coordinates
  - used to build the facility base table
- `/v4/data/facilities/NEM`
  - returns per-facility operational time-series data
  - used for `power_value` and `emission_value`
- `/v4/market/network/NEM`
  - returns market-wide time-series data
  - used for `price_per_mwh` and `demand_mw`

The data is restricted to the NEM network via the `network=NEM` filter.

### 2.2 Time Window and Granularity

The report states that the pipeline retrieves one week of 5-minute records and normalizes timestamps into Sydney time.

In the repository, the cleaned output preserves:

- a single facility-level primary key
- ISO 8601 timestamps
- timezone-aware Sydney timestamps

## 3. Cleaning and Standardization

The repository now uses a layered artifact model:

- **raw**: upstream files with minimal transformation
- **staging**: cleaned, typed, and deduplicated tables
- **mart**: publish-ready output

Cleaning happens in staging before MQTT publishing, so the stream already carries normalized rows.

### 3.1 Schema Normalization

The cleaned dataset consolidates:

- facility identity and coordinates
- operational metrics
- market metrics
- Assignment 1 metadata such as fuel type and state

The intended integrated schema is centered on:

- `facility_code`
- `facility_name`
- `timestamp`
- `lat`
- `lng`
- `state`
- `fuel_list`
- `power_value`
- `emission_value`
- `price_per_mwh`
- `demand_mw`

### 3.2 Missing and Invalid Value Policy

The project uses a three-way policy for core operational data:

- **negative `Power (MW)` or `Emissions (tonnes)` values** are treated as invalid and normalized to `0`
- **fully missing `Power (MW)` and `Emissions (tonnes)` for a facility** cause that facility to be dropped
- **partial gaps in `Power (MW)` and `Emissions (tonnes)`** are filled with the existing split strategy
  - first half of the gap uses forward fill
  - second half uses backward fill

For optional market data:

- `Price ($/MWh)` and `Demand (MW)` keep missing semantics as `NaN` / `None`
- these fields are not force-filled to zero
- dashboard rendering shows them as missing, not as real zero values

The important distinction is:

- `0` means a real measured zero or a cleaned invalid negative value
- `NaN` or `None` means the value was missing or not available

### 3.3 Missing-Value Handling in the Current Code

The repository matches that policy:

- `src/publisher/data/cleaning.py` replaces negative core values with `0`
- `src/publisher/data/cleaning.py` drops facilities where both `Power (MW)` and `Emissions (tonnes)` are fully missing
- `src/publisher/data/cleaning.py` preserves partial gaps in core series using the split fill strategy
- `src/publisher/data/cleaning.py` keeps optional market fields as `NaN` / `None`
- `src/dashboard/` keeps optional metrics missing and shows them as `N/A`

This means the live system keeps missing data visible as missing, rather than silently turning it into a fabricated numeric value.

### 3.4 Artifact Layout

The pipeline writes artifacts to:

- `data/raw/open_electricity/` for facility and time-series source extracts
- `data/raw/assignment1/` for downloaded NGER and CER inputs
- `data/staging/open_electricity/` for cleaned facility and time-series tables
- `data/staging/assignment1/` for cleaned Assignment 1 tables
- `data/mart/` for the publish-ready MQTT input CSV
- `data/cache/` for runtime cache state

## 4. Integration with Assignment 1

The operational data is combined with static metadata from Assignment 1:

- `facility_code` is the integration key
- `facility_name` is used for fuzzy matching and grouping
- static fields such as `state`, `lat`, `lng`, and `fuel_list` are attached to the operational rows

The report describes this as a merge between:

- Open Electricity operational data
- NGER / CER static metadata

The current pipeline keeps the same intent:

- static facility context is attached once
- dynamic metrics are updated on each incoming record
- records without valid coordinates are not useful for map rendering and are skipped in the dashboard

## 5. MQTT Publishing

### 5.1 Topic Design

Published measurement messages use:

- `comp5339/task123/measurements/{facility_code}`

This is configured via the publisher's `MQTT_PUBLISH_TOPIC_TEMPLATE`.

This allows the dashboard to subscribe with:

- `comp5339/task123/measurements/#`

This is configured via the dashboard's `MQTT_SUBSCRIBE_TOPIC_FILTER`.

### 5.2 Message Payload

Each published payload contains:

- `seq`
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
- `sent_mono_ns`
- `slot_mono_ns`

The monotonic timestamps are included for auditability and to show that the publisher follows a fixed time schedule.

### 5.3 Ordering and Retry Behavior

The report states that the stream should be globally ordered and emitted with a strict 0.1-second cadence.

The current publisher keeps that behavior and additionally makes the commit point safer:

- rows are sorted by `(timestamp, facility_code)`
- the publisher sends rows in deterministic order
- the cursor is advanced only after publish confirmation
- if publish fails, the current row is retried on the next polling cycle

This prevents silent message loss when the broker is unavailable or temporarily overloaded.

## 6. Subscription and In-Memory Cache

`src/dashboard/` subscribes to the MQTT wildcard topic and decodes each JSON payload.

### 6.1 Validation on Receive

A message is accepted only if core fields are valid:

- `facility_code`
- `lat`
- `lng`
- `power_value`

If any of these are missing or malformed, the message is discarded.

Optional metrics remain optional:

- `emission_value`
- `price_per_mwh`
- `demand_mw`

### 6.2 Cache Model

The dashboard keeps the latest messages in an in-memory bounded cache:

- the cache is keyed by `facility_code`
- the latest message per facility overwrites older values
- the cache size is bounded
- the cache can be soft-reset on a timer

This cache is the source for:

- metric cards
- the data table
- the trend chart
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

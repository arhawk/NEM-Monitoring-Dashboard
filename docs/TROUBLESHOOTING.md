# Troubleshooting

## Dashboard Shows Disconnected

- Confirm Mosquitto is running with `docker compose ps`.
- Confirm the publisher is running.
- Check that `MQTT_BROKER` and `MQTT_PORT` point to the broker you are actually using.
- Check that the dashboard subscription topic matches the publisher topic prefix.

## Dashboard Never Shows Live Data

- The dashboard only renders messages that match `comp5339/task123/measurements/#` by default.
- Make sure the publisher is emitting to `comp5339/task123/measurements/{facility_code}` or a compatible template.
- If the current cache is stale, use the reset button in the sidebar or restart the Streamlit process.

## Publisher Cannot Fetch Fresh Data

- Set `OPEN_ELECTRICITY_API_KEY`.
- Check network access to the Open Electricity and CER endpoints.
- Verify that any hosted environment allows outbound HTTP access.

## Publisher Reuses Old Data

- The publisher prefers `data/mart/data_for_publish.csv` when that file already exists.
- Delete the generated CSV and JSON artifacts in `data/` if you need a rebuild from source inputs.

## GitHub Actions Controls Are Hidden

- Set `ENABLE_GITHUB_ACTIONS_CONTROL=true`.
- Provide `GITHUB_TOKEN` with Actions API access.
- Confirm the configured repository and workflow names match the actual GitHub repository.

## Import Errors In Local Development

- Activate the project virtual environment before running tests or Streamlit.
- Reinstall dependencies with `pip install -r requirements.txt` if the active interpreter is missing packages.
- The repository is written for Python 3.10 or newer.

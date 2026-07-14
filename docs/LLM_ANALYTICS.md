# LLM Analytics

Read-only analytics overlay for the NEM monitoring dashboard mart dataset. This module answers natural-language questions against `data/mart/data_for_publish.csv` without modifying the MQTT publisher or Streamlit dashboard.

## What It Does

1. Load a capped sample of mart data.
2. Ask Google Gemini (via Google AI Studio REST API) to generate a single pandas expression that assigns to `result`.
3. Validate the generated code with AST checks.
4. Execute the code in a constrained namespace (`df`, `pd` only).
5. Summarize the result and write an audit log.

## What It Does Not Do

- It does not modify the cleaning pipeline.
- It does not publish to MQTT.
- It does not write back to mart or staging files.
- CI does not call the real Google AI API.

## Configuration

Add these optional variables to your environment or `.env` file:

```bash
ENABLE_LLM_ANALYTICS=true
GOOGLE_AI_API_KEY=your-google-ai-studio-key
GOOGLE_AI_MODEL=gemini-2.0-flash
LLM_MAX_ROWS=5000
LLM_AUDIT_DIR=data/cache/llm_runs
```

Get an API key from [Google AI Studio](https://aistudio.google.com/apikey).

`GOOGLE_AI_API_KEY` also accepts the alias `GEMINI_API_KEY` for compatibility with Google SDK examples.

`ENABLE_LLM_ANALYTICS` defaults to `false`. The pipeline fails closed when analytics is disabled or `GOOGLE_AI_API_KEY` is missing.

The CLI loads variables from the repository root `.env` file automatically when present.

LLM analytics uses the Gemini REST API through the existing `requests` dependency only. It does not install `google-genai` or upgrade `websockets`, so it can coexist with `pyppeteer` in the same virtual environment.

Each CLI run performs one Gemini request by default and prints progress to stderr while loading data, calling the API, and executing pandas code. The default request timeout is 30 seconds (`LLM_REQUEST_TIMEOUT_SECONDS`).

## CLI Usage

From the repository root:

```bash
python scripts/run_llm_query.py "Which state has the highest average emissions?"
python scripts/run_llm_query.py "Top 5 facilities by average power output"
python scripts/run_llm_query.py "How does price correlate with demand?"
```

Example output:

```text
Question: Which state has the highest average emissions?
Generated code: result = df.groupby("state")["Emissions (tonnes)"].mean().sort_values(ascending=False)
Result (2 items):
QLD    8.0
NSW    4.0
Summary: QLD has the highest average emissions in the loaded sample.
Audit log: data/cache/llm_runs/2026-07-14T04-30-00.123456+00-00.json
```

## Safety Model

- Generated code is parsed with `ast` and rejected if it contains imports, file I/O helpers, `exec`, `eval`, or forbidden names.
- Only assignment to `result` is allowed.
- Execution uses a copied DataFrame and a 5-second timeout.
- DataFrame and Series outputs are truncated for display and audit previews.
- Every CLI run writes an audit JSON file, including failures.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `LLM analytics is disabled` | Set `ENABLE_LLM_ANALYTICS=true` |
| `GOOGLE_AI_API_KEY is required` | Provide a valid Google AI Studio API key in `.env` or your shell |
| `OPENAI_API_KEY is required` | You are on an old revision; run `git pull` and switch to `GOOGLE_AI_API_KEY` |
| `Mart data file not found` | Run the publisher pipeline to generate `data/mart/data_for_publish.csv` |
| Validation failed after retry | Rephrase the question or inspect the audit log for the rejected code |
| `pyppeteer` / `websockets` conflict after an older install | Remove `google-genai` if present, then run `pip install 'websockets>=10.0,<11.0'` |
| CLI appears stuck with no output | Check stderr progress lines; verify network access to `generativelanguage.googleapis.com` |
| Request timed out | Lower `LLM_MAX_ROWS`, increase `LLM_REQUEST_TIMEOUT_SECONDS`, or retry later |
| `429 Too Many Requests` | Wait 30-60 seconds and retry; free-tier Gemini quotas are easy to exhaust with back-to-back calls |

## Manual Smoke Test

After setting `ENABLE_LLM_ANALYTICS=true` and `GOOGLE_AI_API_KEY`, run the three CLI examples above against an existing mart file. Confirm each run prints a summary and creates a JSON file under `data/cache/llm_runs/`.

## Tests

```bash
pytest tests/test_llm_pipeline.py -q
```

The test suite mocks the LLM client and does not require network access.

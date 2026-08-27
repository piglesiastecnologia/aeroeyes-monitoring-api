# AeroEyes Monitoring API

Monitoring API for the AeroEyes Distributed Monitoring Platform, responsible
for monitoring sessions, attention-event ingestion, and operational context.

## Requirements

- Python 3.11 or newer

## Local setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package with its test dependencies:

```bash
python -m pip install -e ".[test]"
```

Run the API locally:

```bash
python -m uvicorn aeroeyes_monitoring_api.main:app --reload
```

The shallow liveness endpoint is available at `GET /health`:

```json
{
  "status": "ok",
  "service": "aeroeyes-monitoring-api"
}
```

## Tests

Run the complete test suite:

```bash
python -m pytest
```

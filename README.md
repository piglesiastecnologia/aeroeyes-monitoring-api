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

## Monitoring sessions

Create an active monitoring session with no request body:

```http
POST /sessions
```

The API returns `201 Created`, a `Location` header, and the new session:

```json
{
  "session_id": "019...",
  "status": "ACTIVE",
  "started_at": "2026-08-27T12:00:00Z",
  "ended_at": null
}
```

Retrieve or complete the session using its UUIDv7 identity:

```http
GET /sessions/{session_id}
POST /sessions/{session_id}/complete
```

Completion is idempotent. Repeated completion requests return the existing
completed session and preserve its original `ended_at` value.

Sessions are temporarily stored only in process memory. They are lost whenever
the application restarts, and the API must run with a single worker during this
MVP phase. PostgreSQL will replace this temporary storage in a later increment.

## Tests

Run the complete test suite:

```bash
python -m pytest
```

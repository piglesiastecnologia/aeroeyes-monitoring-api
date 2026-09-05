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

Install the package with its test and migration dependencies:

```bash
python -m pip install -e ".[test,migration]"
```

Run the API locally:

```bash
export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
python -m alembic upgrade head
python -m uvicorn aeroeyes_monitoring_api.main:create_app --factory --reload
```

`CORS_ALLOWED_ORIGINS` is a comma-separated list of explicit browser origins.
No origin, including localhost, is enabled implicitly.

The shallow liveness endpoint is available at `GET /health`:

```json
{
  "status": "ok",
  "service": "aeroeyes-monitoring-api"
}
```

## PostgreSQL database foundation

PostgreSQL is the runtime persistence store. The initial schema contains only
monitoring sessions and attention events. Normal application startup requires
`DATABASE_URL`; there is no automatic fallback to in-memory persistence.

Set `DATABASE_URL` when running migrations, using the synchronous Psycopg 3
SQLAlchemy URL format:

```bash
export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
```

Use local development credentials and do not commit secrets or `.env` files.
Apply or revert the schema with Alembic:

```bash
python -m alembic upgrade head
python -m alembic downgrade base
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

Sessions are stored in PostgreSQL and remain available across application
restarts and multiple application instances using the same database.

## Attention-event ingestion

Submit an immutable attention event to its monitoring session:

```http
POST /sessions/{session_id}/events
```

The producer owns the UUIDv7 `event_id` and event occurrence time. The API owns
`received_at`. A first ingestion returns `201 Created`; an identical replay of
the same event in the same session returns `200 OK` with
`status: "already_processed"` and the original stored event. Reusing an event ID
with changed semantics or another session returns `409 Conflict`.

Events are append-only. A completed session still accepts a late-delivered event
when its producer timestamp falls within the session's inclusive start/end
window.

Event storage and event-ID arbitration use PostgreSQL. Session validation and
event acceptance share the transaction owned by a per-operation unit of work,
so persistence and replay protection do not depend on process-local locks.

## Tests

Run the complete test suite:

```bash
python -m pytest
```

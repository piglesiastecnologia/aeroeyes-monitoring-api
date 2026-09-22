# AeroEyes Monitoring API

[Português](README.md) · [English](README.en.md)

REST backend for the **AeroEyes Monitoring System**. The API manages monitoring
sessions and flight context, ingests semantic attention transitions, exposes
Web read models, and integrates AviationWeather.gov METAR data.

## Role in the PUC-Rio MVP

The project follows **Sprint 3 scenario 1.1**:

```text
AeroEyes Web → Monitoring API → AviationWeather Data API
                            ↘ PostgreSQL
```

This repository is the developed backend and one of the two public delivery
repositories. The Attention Core is optional: it may publish events to the API,
but it is not required to prove the Web → API → external API flow.

The canonical diagram and complete evidence matrix are maintained in
[`aeroeyes-web`](https://github.com/piglesiastecnologia/aeroeyes-web) under
`docs/architecture` and `docs/delivery`.

## Responsibilities

- create, retrieve, and complete monitoring sessions;
- maintain one flight context per session;
- persist sessions, context, and attention events in PostgreSQL;
- arbitrate idempotent attention-event ingestion;
- expose latest attention state and a bounded recent-event window;
- retrieve METAR server-side and return a normalized contract;
- enable CORS only for explicitly configured origins.

## HTTP contracts

| Method | Route | Responsibility |
| --- | --- | --- |
| `GET` | `/health` | Service liveness |
| `POST` | `/sessions` | Create an active session |
| `GET` | `/sessions/{session_id}` | Retrieve a session |
| `POST` | `/sessions/{session_id}/complete` | Complete a session idempotently |
| `GET` | `/sessions/{session_id}/context` | Retrieve flight context |
| `PUT` | `/sessions/{session_id}/context` | Replace flight context |
| `DELETE` | `/sessions/{session_id}/context` | Remove flight context |
| `GET` | `/sessions/{session_id}/weather` | Retrieve normalized current METAR |
| `POST` | `/sessions/{session_id}/events` | Ingest an attention event |
| `GET` | `/sessions/{session_id}/attention-state` | Read the latest semantic transition |
| `GET` | `/sessions/{session_id}/events?limit=10` | Read recent events, newest first |

Interactive API documentation is available at `/docs` while the app is running.

## Persistence and consistency

PostgreSQL is the required runtime store. `DATABASE_URL` must use a synchronous
SQLAlchemy URL with Psycopg 3; there is no automatic in-memory fallback.

Sessions, context, and events are validated and persisted inside transactional
units of work. Events are immutable: the first submission returns
`201 Created`; an identical replay returns `200 OK` as already processed; reuse
of an `event_id` with different content or session ownership returns
`409 Conflict`.

A completed session accepts only late events whose `occurred_at` lies within
that session's inclusive start/end interval.

## AviationWeather integration

The weather route calls the public
`GET https://aviationweather.gov/api/data/metar` resource server-side. The
browser never calls the provider directly. The API validates station and
payload data, maps provider failures, and returns only the normalized AeroEyes
contract to the Web.

The result is current operational weather, including for completed sessions.
It is not historical, is not persisted or cached in the MVP, and does not feed
attention classification.

Public weather data requires no account or API key. Provider documentation
also describes request limits and no direct browser CORS support:
<https://aviationweather.gov/data/api/>.

## Local execution

Requirements:

- Python 3.11 or newer;
- PostgreSQL.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,migration]"

export DATABASE_URL="postgresql+psycopg://aeroeyes:local-password@localhost:5432/aeroeyes"
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"

python -m alembic upgrade head
python -m uvicorn aeroeyes_monitoring_api.main:create_app --factory --reload
```

`CORS_ALLOWED_ORIGINS` is a comma-separated list. No origin, including
localhost, is enabled implicitly.

## Migrations

```bash
python -m alembic upgrade head
python -m alembic downgrade base
```

Use local credentials and never commit secrets or `.env` files.

## Docker and composition

The root `Dockerfile` builds the image used by the `aeroeyes-web` composition.
PostgreSQL becomes healthy first, a one-shot `migrate` service applies
`alembic upgrade head`, and only then does the API start.

Standalone build:

```bash
docker build -t aeroeyes-monitoring-api .
```

The Web repository is the canonical entry point for the full environment.

## Validation

```bash
python -m pytest
python -m pip check
python -m compileall -q src
```

CI runs migrations and tests against real PostgreSQL, checks dependencies and
source compilation, and builds the Docker image.

## Declared limits

- Academic experimental MVP; not certified aviation or medical software.
- Current METAR is not retained as historical weather.
- Events are semantic transitions, not video, landmarks, or raw EAR.
- The API cannot prove that a local producer remains alive after its last event.
